"""
transcribe — audio/video URL → markdown transcript for the twin corpus.

Consumes `url:` entries (and optional `title:`) from a backlog spec under
`rag/twins/persons/<slug>.yaml` and writes transcripts at the local path
pattern `rag/twins/persons/_corpus/<slug>/<descriptor>.md`, ready to be
consumed by `ingest_person.run`.

Pipeline
--------
    URL ──[yt-dlp]──▶ audio.m4a
        ──[OpenAI Whisper API]──▶ text
        ──[render markdown + header]──▶ _corpus/<slug>/<descriptor>.md

Design rules (aligned with README §"Transcription pipeline")
-----------------------------------------------------------
  * **Graceful degradation.** yt-dlp and `openai` are optional imports;
    without either, we fail fast with an actionable message instead of
    silently skipping sources (bad twin = silent-failure Shreya risk).
  * **Cache by content.** URL hash → cached audio + cached transcript.
    Never retranscribe the same URL. Makes re-runs cheap + idempotent.
  * **Honest on unsupported URLs.** Spotify web URLs are DRM-protected
    and yt-dlp refuses them; Apple Podcasts is similar. We detect these
    hosts and raise a clear error rather than attempting a scrape.
  * **Provenance header.** Every transcript starts with a YAML front
    matter block containing source_url, source_date, source_type,
    duration_sec, language, whisper_model. Chunker + quality scorer
    already ignore markdown front matter, so embeddings stay clean.
  * **Rate-limit aware.** Bounded retries with exponential backoff on
    the Whisper call; no concurrent requests from the same process.

Scope NOT covered (by design, as discussed in war-room)
-------------------------------------------------------
  * No paywall bypass for Valor/Exame/etc. Articles marked `path:` in
    the spec must be copy-pasted by a human operator.
  * No speaker diarization in v1. Whisper returns monolithic text; we
    leave a TODO in the header for Phase 2 when we wire pyannote.
  * No Spotify/Apple Podcasts. If we need those, we use the RSS feed
    URL where the podcast is also distributed (most shows are multi-host).

Usage
-----
    # single URL
    python -m rag.twins.transcribe \\
        --url https://www.youtube.com/watch?v=abc \\
        --out rag/twins/persons/_corpus/mrv-rubens-menin/os-socios-2022.md \\
        --source-date 2022-08-11 --source-type podcast --title "Os Sócios — ep.142"

    # batch: iterate every `url:` source in a backlog spec
    python -m rag.twins.transcribe --spec rag/twins/persons/mrv-rubens-menin.yaml

    # dry run
    python -m rag.twins.transcribe --spec <file> --dry-run
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Errors and host classification
# ---------------------------------------------------------------------------


class TranscribeError(RuntimeError):
    """Raised for any irrecoverable transcribe failure (bad URL, missing dep,
    API error past retries)."""


_UNSUPPORTED_HOSTS = {
    # DRM-protected or anti-bot protected beyond yt-dlp's normal handling.
    # If a show is only here, use its RSS feed host instead.
    "open.spotify.com",
    "spotify.com",
    "podcasts.apple.com",
}

_PLAUSIBLE_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "youtu.be",
    "m.youtube.com",
    "vimeo.com",
    "soundcloud.com",
}

# Hosts that yt-dlp struggles with but a self-hosted Cobalt instance handles
# natively. Only treated as supported when COBALT_API_URL is configured.
_COBALT_ONLY_HOSTS = {
    "tiktok.com",
    "www.tiktok.com",
    "vm.tiktok.com",
    "instagram.com",
    "www.instagram.com",
    "twitter.com",
    "x.com",
    "www.x.com",
    "bsky.app",
    "reddit.com",
    "www.reddit.com",
    "twitch.tv",
    "www.twitch.tv",
    "clips.twitch.tv",
    "facebook.com",
    "www.facebook.com",
    "fb.watch",
    "pinterest.com",
    "www.pinterest.com",
    "tumblr.com",
    "snapchat.com",
    "www.snapchat.com",
    "loom.com",
    "www.loom.com",
    "streamable.com",
    "dailymotion.com",
    "www.dailymotion.com",
}


def _classify_host(url: str) -> str:
    """Return "supported" | "plausible" | "unsupported". "plausible" means
    yt-dlp should handle it but we haven't confirmed in this repo yet."""
    host = (urlparse(url).hostname or "").lower()
    if host in _UNSUPPORTED_HOSTS:
        return "unsupported"
    if host in _PLAUSIBLE_HOSTS:
        return "supported"
    if host in _COBALT_ONLY_HOSTS and os.environ.get("COBALT_API_URL"):
        return "supported"
    return "plausible"


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------


_DEFAULT_CACHE = Path(os.environ.get("TWINS_TRANSCRIBE_CACHE", "rag/twins/.transcribe_cache"))


def _url_hash(url: str) -> str:
    return hashlib.sha1(url.strip().encode("utf-8")).hexdigest()[:16]


def _audio_cache_path(url: str, cache_dir: Path | None = None) -> Path:
    d = cache_dir or _DEFAULT_CACHE
    return d / "audio" / f"{_url_hash(url)}.m4a"


def _transcript_cache_path(url: str, cache_dir: Path | None = None) -> Path:
    d = cache_dir or _DEFAULT_CACHE
    return d / "transcripts" / f"{_url_hash(url)}.json"


# ---------------------------------------------------------------------------
# Audio download
# ---------------------------------------------------------------------------


@dataclass
class AudioInfo:
    path: Path
    duration_sec: int | None
    title: str | None


def _download_audio(url: str, cache_dir: Path | None = None) -> AudioInfo:
    """Pull audio at the best available quality (m4a). When COBALT_API_URL
    is set, try Cobalt first and fall back to yt-dlp on failure; otherwise
    go straight to yt-dlp."""
    dest = _audio_cache_path(url, cache_dir)
    dest.parent.mkdir(parents=True, exist_ok=True)

    if dest.exists() and dest.stat().st_size > 0:
        log.info("audio cache hit url=%s path=%s", url, dest)
        return AudioInfo(path=dest, duration_sec=None, title=None)

    cobalt_api = os.environ.get("COBALT_API_URL")
    host = (urlparse(url).hostname or "").lower()
    cobalt_eligible = cobalt_api and (
        host in _COBALT_ONLY_HOSTS
        or os.environ.get("COBALT_PREFER", "").lower() in {"1", "true", "yes"}
    )
    if cobalt_eligible:
        try:
            return _download_audio_via_cobalt(url, dest, cobalt_api)
        except Exception as e:
            log.warning("cobalt failed for %s, falling back to yt-dlp: %s", url, e)

    return _download_audio_via_ytdlp(url, dest)


def _download_audio_via_ytdlp(url: str, dest: Path) -> AudioInfo:
    if not _has_yt_dlp():
        raise TranscribeError(
            "yt-dlp not installed. Install with `pip install yt-dlp` "
            "(or drop the .md transcript manually under _corpus/<slug>/)."
        )
    cmd = [
        "yt-dlp",
        "-f",
        "bestaudio[ext=m4a]/bestaudio/best",
        "--no-playlist",
        "--quiet",
        "--no-warnings",
        "--print-to-file",
        "%(duration)s\\n%(title)s",
        str(dest) + ".meta",
        "-o",
        str(dest),
        url,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if result.returncode != 0:
        raise TranscribeError(f"yt-dlp failed for {url}: {result.stderr.strip()[:400]}")
    duration, title = _read_meta_sidecar(Path(str(dest) + ".meta"))
    return AudioInfo(path=dest, duration_sec=duration, title=title)


def _download_audio_via_cobalt(url: str, dest: Path, api_url: str) -> AudioInfo:
    from rag.cobalt_client import download_audio as cobalt_download

    api_key = os.environ.get("COBALT_API_KEY") or None
    info = cobalt_download(url, dest, api_url=api_url, api_key=api_key)
    return AudioInfo(path=info.path, duration_sec=info.duration_sec, title=info.title)


def _has_yt_dlp() -> bool:
    try:
        result = subprocess.run(["yt-dlp", "--version"], capture_output=True, timeout=5)
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _read_meta_sidecar(sidecar: Path) -> tuple[int | None, str | None]:
    if not sidecar.exists():
        return None, None
    try:
        lines = sidecar.read_text(encoding="utf-8").splitlines()
        duration_raw = lines[0] if lines else ""
        title = lines[1] if len(lines) > 1 else None
        try:
            duration = int(float(duration_raw))
        except (TypeError, ValueError):
            duration = None
        return duration, title
    except Exception:
        return None, None


# ---------------------------------------------------------------------------
# Whisper transcription
# ---------------------------------------------------------------------------


# Whisper backend priority:
#   1. Local (WHISPER_LOCAL=1): openai/whisper-large-v3-turbo via transformers
#   2. Groq API (GROQ_API_KEY set): free whisper-large-v3 via OpenAI-compatible API
#   3. OpenAI API (OPENAI_API_KEY set): whisper-1 fallback
_GROQ_BASE_URL = "https://api.groq.com/openai/v1"
_GROQ_WHISPER_MODEL = "whisper-large-v3"
_OPENAI_WHISPER_MODEL = "whisper-1"
_LOCAL_WHISPER_MODEL = "openai/whisper-large-v3-turbo"
_WHISPER_MODEL = os.environ.get("WHISPER_MODEL", "")  # empty = auto-detect by backend
_WHISPER_LANGUAGE = os.environ.get("WHISPER_LANGUAGE", "pt")
_WHISPER_LOCAL = os.environ.get("WHISPER_LOCAL", "0") == "1"


@dataclass
class TranscriptionResult:
    text: str
    language: str
    model: str


def _transcribe_local(audio_path: Path) -> TranscriptionResult:
    """Transcribe audio locally using whisper-large-v3-turbo via transformers."""
    try:
        import torch
        from transformers import pipeline as hf_pipeline
    except ImportError as e:
        raise TranscribeError(
            "transformers and torch required for local Whisper. `pip install transformers torch`"
        ) from e

    model_id = _WHISPER_MODEL or _LOCAL_WHISPER_MODEL
    device = "cuda" if torch.cuda.is_available() else "cpu"
    log.info("local whisper model=%s device=%s", model_id, device)
    pipe = hf_pipeline(
        "automatic-speech-recognition",
        model=model_id,
        device=device,
        generate_kwargs={"language": _WHISPER_LANGUAGE, "task": "transcribe"},
    )
    out = pipe(str(audio_path), chunk_length_s=30, batch_size=8)
    text = out["text"] if isinstance(out, dict) else str(out)
    return TranscriptionResult(text=text, language=_WHISPER_LANGUAGE, model=model_id)


def _transcribe_audio(
    audio_path: Path, *, url: str, cache_dir: Path | None = None
) -> TranscriptionResult:
    """Transcribe audio with cache. Backend priority: local → Groq → OpenAI."""
    cache_file = _transcript_cache_path(url, cache_dir)
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    if cache_file.exists():
        log.info("transcript cache hit url=%s", url)
        data = json.loads(cache_file.read_text(encoding="utf-8"))
        return TranscriptionResult(
            text=data["text"],
            language=data.get("language", _WHISPER_LANGUAGE),
            model=data.get("model", _GROQ_WHISPER_MODEL),
        )

    # Local inference path: set WHISPER_LOCAL=1 to run whisper-large-v3-turbo on-device.
    if _WHISPER_LOCAL:
        result = _transcribe_local(audio_path)
        cache_file.write_text(
            json.dumps(
                {"text": result.text, "language": result.language, "model": result.model},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return result

    try:
        import openai  # type: ignore[import-not-found]
    except ImportError as e:
        raise TranscribeError(
            "openai SDK not installed. `pip install openai` (Whisper API)."
        ) from e

    groq_key = os.environ.get("GROQ_API_KEY", "").strip()
    openai_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if groq_key:
        backend = "groq"
        client = openai.OpenAI(api_key=groq_key, base_url=_GROQ_BASE_URL)
        model = _WHISPER_MODEL or _GROQ_WHISPER_MODEL
    elif openai_key:
        backend = "openai"
        client = openai.OpenAI(api_key=openai_key)
        model = _WHISPER_MODEL or _OPENAI_WHISPER_MODEL
    else:
        raise TranscribeError(
            "No transcription backend available. Set WHISPER_LOCAL=1 (local), "
            "GROQ_API_KEY (Groq API), or OPENAI_API_KEY (OpenAI API)."
        )
    log.info("whisper backend=%s model=%s", backend, model)
    result = _whisper_with_retries(client, audio_path, model=model)

    cache_file.write_text(
        json.dumps(
            {"text": result.text, "language": result.language, "model": result.model},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return result


def _whisper_with_retries(
    client, audio_path: Path, *, model: str, max_retries: int = 3
) -> TranscriptionResult:
    backoff = 2.0
    last_err: Exception | None = None
    for attempt in range(1, max_retries + 1):
        try:
            with audio_path.open("rb") as f:
                resp = client.audio.transcriptions.create(
                    model=model,
                    file=f,
                    language=_WHISPER_LANGUAGE,
                    response_format="verbose_json",
                )
            language = getattr(resp, "language", _WHISPER_LANGUAGE) or _WHISPER_LANGUAGE
            text = getattr(resp, "text", "") or ""
            return TranscriptionResult(text=text, language=language, model=model)
        except Exception as e:
            last_err = e
            log.warning("whisper attempt %d/%d failed: %s", attempt, max_retries, e)
            time.sleep(backoff)
            backoff *= 2
    raise TranscribeError(f"Whisper failed after {max_retries} attempts: {last_err}")


# ---------------------------------------------------------------------------
# Markdown rendering
# ---------------------------------------------------------------------------


def render_transcript_markdown(
    *,
    text: str,
    url: str,
    title: str | None,
    source_type: str,
    source_date: str | None,
    duration_sec: int | None,
    language: str,
    model: str,
) -> str:
    """Compose the transcript .md — YAML header + prose.

    The header keys are what `ingest_person.score_quality` ignores (pure
    text is what gets chunked/embedded). Keeping metadata visible helps
    downstream audit + LGPD traceability.
    """
    header_lines = [
        "---",
        f"source_url: {url}",
        f"title: {title or '(untitled)'}",
        f"source_type: {source_type}",
    ]
    if source_date:
        header_lines.append(f"source_date: {source_date}")
    if duration_sec is not None:
        header_lines.append(f"duration_sec: {duration_sec}")
    header_lines.extend(
        [
            f"language: {language}",
            f"whisper_model: {model}",
            "speaker_diarization: none  # v1 does not segment; Phase 2 TODO",
            "---",
            "",
        ]
    )
    return "\n".join(header_lines) + text.strip() + "\n"


# ---------------------------------------------------------------------------
# YouTube captions (preferred — no audio download, no bot block)
# ---------------------------------------------------------------------------


_YT_VIDEO_ID_RE = re.compile(
    r"(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/shorts/)([\w\-]+)",
    re.IGNORECASE,
)


def _youtube_video_id(url: str) -> str | None:
    """Extract the 11-char video id from a YouTube URL. None if not YouTube."""
    match = _YT_VIDEO_ID_RE.search(url)
    return match.group(1) if match else None


def _fetch_youtube_captions(
    url: str, *, preferred_langs=("pt", "pt-BR", "en")
) -> TranscriptionResult | None:
    """Fetch YouTube auto-captions via the youtube-transcript-api endpoint.

    This hits `youtubei.googleapis.com/.../get_transcript` — a different path
    than audio-download, with much weaker bot-detection. Works from cloud IPs
    that yt-dlp is blocked on.

    Compatible with youtube-transcript-api >= 1.0 (class was restructured
    into an instance with `list()` / `fetch()` methods). Earlier versions
    used class methods `list_transcripts()` / `get_transcript()` which are
    no longer available.

    Returns None if:
      - URL is not YouTube
      - No captions available for this video
      - youtube-transcript-api is not installed
      - API call fails for any reason (caller falls back to yt-dlp+Whisper)
    """
    video_id = _youtube_video_id(url)
    if not video_id:
        return None
    try:
        from youtube_transcript_api import YouTubeTranscriptApi  # type: ignore[import-not-found]
    except ImportError:
        log.debug("youtube-transcript-api not installed; skipping captions path")
        return None

    api = YouTubeTranscriptApi()

    # New API (1.0+): api.list(video_id) returns TranscriptList supporting
    # find_manually_created_transcript / find_generated_transcript, same as
    # the old class-method API.
    try:
        transcripts = api.list(video_id)
    except Exception as e:
        log.info("captions list failed video=%s err=%s", video_id, e)
        return None

    # Preference: manually-authored > auto-generated, within language order.
    picked = None
    for lang in preferred_langs:
        try:
            picked = transcripts.find_manually_created_transcript([lang])
            break
        except Exception:
            pass
    if picked is None:
        for lang in preferred_langs:
            try:
                picked = transcripts.find_generated_transcript([lang])
                break
            except Exception:
                pass
    if picked is None:
        log.info("no captions in preferred langs for video=%s", video_id)
        return None

    try:
        fetched = picked.fetch()
    except Exception as e:
        log.info("captions fetch failed video=%s err=%s", video_id, e)
        return None

    # 1.0+ returns FetchedTranscript with .snippets (each has .text), older
    # versions returned list[dict] with key "text". Handle both.
    if hasattr(fetched, "snippets"):
        text_parts = [s.text.strip() for s in fetched.snippets if getattr(s, "text", None)]
    else:
        text_parts = [e.get("text", "").strip() for e in fetched if e.get("text")]
    text = " ".join(text_parts).strip()
    if not text:
        return None
    return TranscriptionResult(
        text=text,
        language=getattr(picked, "language_code", preferred_langs[0]),
        model="youtube-captions",
    )


# ---------------------------------------------------------------------------
# Public API — single URL
# ---------------------------------------------------------------------------


def transcribe_url(
    url: str,
    out_path: Path,
    *,
    title: str | None = None,
    source_type: str = "podcast",
    source_date: str | None = None,
    cache_dir: Path | None = None,
    skip_existing: bool = True,
    prefer_captions: bool = True,
) -> Path:
    """Download audio at `url`, transcribe, write markdown at `out_path`.

    Transcription backend order (for YouTube URLs):
      1. YouTube captions via youtube-transcript-api (fast, free, survives
         cloud IPs). Prefers PT/PT-BR, then EN.
      2. yt-dlp audio download + OpenAI Whisper API (full audio, better
         nuance, but blocked from many cloud IPs in 2025+).
      3. Raise TranscribeError with actionable message.

    `prefer_captions=False` skips step 1 (useful when you want nuance capture
    and have working yt-dlp).

    Returns the written path. Idempotent: if out_path exists and is non-empty
    and `skip_existing=True`, returns immediately. Uses audio + transcript
    cache to avoid repeat work across runs.
    """
    if skip_existing and out_path.exists() and out_path.stat().st_size > 0:
        log.info("out exists, skipping url=%s path=%s", url, out_path)
        return out_path

    host_class = _classify_host(url)
    if host_class == "unsupported":
        raise TranscribeError(
            f"host not supported by transcribe (DRM/anti-bot): {url}. "
            "Use the show's RSS/YouTube URL instead."
        )

    transcript: TranscriptionResult | None = None
    duration_sec: int | None = None
    video_title: str | None = None

    # Step 1: try captions (cheap, quick, survives cloud IPs)
    if prefer_captions and _youtube_video_id(url):
        transcript = _fetch_youtube_captions(url)
        if transcript is not None:
            log.info("captions path used url=%s chars=%d", url, len(transcript.text))

    # Step 2: fall back to yt-dlp + Whisper if captions unavailable
    if transcript is None:
        audio = _download_audio(url, cache_dir=cache_dir)
        transcript = _transcribe_audio(audio.path, url=url, cache_dir=cache_dir)
        duration_sec = audio.duration_sec
        video_title = audio.title

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        render_transcript_markdown(
            text=transcript.text,
            url=url,
            title=title or video_title,
            source_type=source_type,
            source_date=source_date,
            duration_sec=duration_sec,
            language=transcript.language,
            model=transcript.model,
        ),
        encoding="utf-8",
    )
    log.info(
        "wrote transcript path=%s chars=%d model=%s",
        out_path,
        len(transcript.text),
        transcript.model,
    )
    return out_path


# ---------------------------------------------------------------------------
# Public API — batch over a person spec
# ---------------------------------------------------------------------------


@dataclass
class BatchResult:
    spec_id: str
    attempted: int
    written: int
    skipped_existing: int
    skipped_unsupported: int
    failed: int
    errors: list[str]


def transcribe_spec(
    spec_path: Path,
    *,
    dry_run: bool = False,
    cache_dir: Path | None = None,
    corpus_base: Path | None = None,
) -> BatchResult:
    """Walk a person YAML, transcribe every `url:` source.

    For URL sources we only transcribe media types (podcast, interview,
    talk). For `article`, `release`, `linkedin` and `book` the raw text
    route is different — ingest handles URL → text via Firecrawl, not
    through Whisper. Those sources are left alone here.
    """
    from rag.twins.ingest_person import load_person_spec

    spec = load_person_spec(spec_path)
    corpus_root = (corpus_base or Path("rag/twins/persons/_corpus")) / spec.id

    attempted = 0
    written = 0
    skipped_existing = 0
    skipped_unsupported = 0
    failed = 0
    errors: list[str] = []

    AUDIO_TYPES = {"podcast", "interview", "talk", "video"}

    for i, src in enumerate(spec.sources):
        if not src.url or src.type not in AUDIO_TYPES:
            continue
        attempted += 1
        host_class = _classify_host(src.url)
        if host_class == "unsupported":
            skipped_unsupported += 1
            errors.append(f"[{i}] unsupported host: {src.url}")
            continue

        out_name = _slugify_descriptor(src.title, fallback=f"{src.type}-{_url_hash(src.url)}")
        out_path = corpus_root / f"{out_name}.md"

        if out_path.exists() and out_path.stat().st_size > 0:
            skipped_existing += 1
            continue

        if dry_run:
            log.info(
                "[dry] would transcribe url=%s → %s (type=%s date=%s)",
                src.url,
                out_path,
                src.type,
                src.date,
            )
            continue

        try:
            transcribe_url(
                src.url,
                out_path,
                title=src.title,
                source_type=src.type,
                source_date=src.date,
                cache_dir=cache_dir,
            )
            written += 1
        except TranscribeError as e:
            failed += 1
            errors.append(f"[{i}] {src.url}: {e}")
            log.warning("transcribe failed url=%s err=%s", src.url, e)

    return BatchResult(
        spec_id=spec.id,
        attempted=attempted,
        written=written,
        skipped_existing=skipped_existing,
        skipped_unsupported=skipped_unsupported,
        failed=failed,
        errors=errors,
    )


def _slugify_descriptor(text: str | None, *, fallback: str) -> str:
    if not text:
        return fallback
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:60] or fallback


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    grp = p.add_mutually_exclusive_group(required=True)
    grp.add_argument("--url", help="Single media URL to transcribe")
    grp.add_argument("--spec", type=Path, help="Person YAML spec (batch mode)")
    p.add_argument("--out", type=Path, help="Output transcript path (single-URL mode)")
    p.add_argument("--title", default=None)
    p.add_argument("--source-type", default="podcast", choices=["podcast", "interview", "talk"])
    p.add_argument("--source-date", default=None)
    p.add_argument("--cache-dir", type=Path, default=None)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--verbose", action="store_true")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if args.url:
        if not args.out:
            raise SystemExit("--out is required when using --url")
        if args.dry_run:
            print(f"[dry] would transcribe {args.url} → {args.out}")
            return 0
        transcribe_url(
            args.url,
            args.out,
            title=args.title,
            source_type=args.source_type,
            source_date=args.source_date,
            cache_dir=args.cache_dir,
        )
        return 0

    report = transcribe_spec(args.spec, dry_run=args.dry_run, cache_dir=args.cache_dir)
    print(
        json.dumps(
            {
                "spec_id": report.spec_id,
                "attempted": report.attempted,
                "written": report.written,
                "skipped_existing": report.skipped_existing,
                "skipped_unsupported": report.skipped_unsupported,
                "failed": report.failed,
                "errors": report.errors[:20],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if report.failed == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
