#!/usr/bin/env bash
# run_twin_local.sh — local end-to-end Full Mode run for one slug.
#
# Use this when you'd rather not deal with GitHub Actions runner stalls or
# YouTube IP blocks. Same pipeline as `twins-run.yml`, driven locally with
# your credentials.
#
# Usage:
#   export OPENAI_API_KEY=...
#   export ANTHROPIC_API_KEY=...
#   export VOYAGE_API_KEY=...
#   # optional for article URLs behind paywalls:
#   export FIRECRAWL_API_KEY=...
#
#   bash rag/twins/run_twin_local.sh mrv-rubens-menin
#
# Flags you can pass through:
#   --dry-run                 plan only, zero cost
#   --skip-transcribe         reuse cached _corpus/<slug>/*.md
#   --skip-build-eval         stop after ingest (no Anthropic/Voyage cost)
#
# Example:
#   bash rag/twins/run_twin_local.sh mrv-rubens-menin --dry-run

set -euo pipefail

SLUG="${1:-}"
shift || true

if [ -z "$SLUG" ]; then
  echo "usage: $0 <slug> [--dry-run] [--skip-transcribe] [--skip-build-eval]" >&2
  exit 2
fi

SPEC="rag/twins/persons/${SLUG}.yaml"
if [ ! -f "$SPEC" ]; then
  echo "::error:: spec not found: $SPEC" >&2
  exit 1
fi

# Detect mode from passed-through args (affects secret checks)
MODE="full"
for arg in "$@"; do
  [ "$arg" = "--dry-run" ] && MODE="dry-run"
done

# Preflight: required secrets for full mode
if [ "$MODE" = "full" ]; then
  missing=()
  for v in OPENAI_API_KEY ANTHROPIC_API_KEY VOYAGE_API_KEY; do
    if [ -z "${!v-}" ]; then missing+=("$v"); fi
  done
  if [ "${#missing[@]}" -gt 0 ]; then
    echo "::error:: missing env var(s): ${missing[*]}" >&2
    echo "export them before running full mode" >&2
    exit 1
  fi
fi

# Python deps — install only if any are missing (idempotent)
python -c "import yaml, httpx, pydantic, anthropic, openai" 2>/dev/null || {
  echo "installing Python deps..."
  pip install --quiet pyyaml httpx pydantic anthropic openai firecrawl-py
}

# yt-dlp must be on PATH for full mode with YouTube URLs
if [ "$MODE" = "full" ]; then
  if ! command -v yt-dlp >/dev/null 2>&1; then
    echo "installing yt-dlp..."
    pip install --quiet yt-dlp
  fi

  # Preflight probe — fail fast if YouTube is blocked from this network
  echo "probing yt-dlp against YouTube..."
  probe_url="https://www.youtube.com/watch?v=cFvLFIM8roc"
  if ! yt-dlp --simulate --no-warnings --quiet --print "ok" "$probe_url" 2> /tmp/ytdlp.err; then
    echo "::error:: yt-dlp failed to reach YouTube from this machine" >&2
    echo "--- yt-dlp stderr ---" >&2
    cat /tmp/ytdlp.err >&2
    exit 1
  fi
  echo "✓ yt-dlp preflight OK"
fi

# Run the pipeline
args=(--only "$SLUG" --out rag/twins/run_all_report.json "$@")
if [ "$MODE" = "full" ]; then
  args+=(--strict-url-check)
fi

echo "invoking: python -m rag.twins.run_all ${args[*]}"
python -m rag.twins.run_all "${args[@]}"

# Pretty-print the report
if [ -f rag/twins/run_all_report.json ]; then
  echo
  echo "=== Acceptance summary ==="
  python - <<'PY'
import json, pathlib
data = json.loads(pathlib.Path("rag/twins/run_all_report.json").read_text())
for r in data:
    slug = r.get("slug", "?")
    print(f"\n{slug}")
    for stage in ("url_sanity", "transcribe", "ingest", "build", "eval_"):
        s = r.get(stage) or {}
        ok = s.get("ok")
        note = s.get("note", "")
        dur = s.get("duration_sec", 0)
        mark = "✅" if ok else ("❌" if ok is False else "—")
        print(f"  {mark} {stage:<12} {note[:100]}" + (f"  ({dur:.1f}s)" if dur else ""))
    gate = r.get("passed_gate")
    gate_mark = "✅ PASSED" if gate else ("❌ FAILED" if gate is False else "— (n/a)")
    print(f"  gate: {gate_mark}")
PY
  echo
  echo "Full report: rag/twins/run_all_report.json"
  echo "Twin SQLite: rag/twins/twins.db"
fi
