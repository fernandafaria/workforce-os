# Entrepreneur Digital Twins — Phase 1 MVP

Synthetic twins of real non-digital entrepreneurs, built from public corpus
(interviews, podcasts, talks, LinkedIn, books) so Product + Design can do
discovery at scale before spending 30 real interviews.

> Architected in war-room 2026-04-21 by @claire (orchestrator) with
> @hamel, @harrison, @jason, @shreya, @simon. Full plan, dissent log, and
> ethics gate live in `projects/memory/decisions-log.md`.

## Pipeline

```
 person.yaml ──▶ ingest_person ──▶ corpus_chunk (SQLite/Supabase)
                    │                    │
                    │                    ▼
                    │               build_twin ──▶ twin (EntrepreneurTwin)
                    │                                 │
                    ▼                                 ▼
              corpus_search ◀────── chat_with_twin  eval_twin
                                         │                │
                                         ▼                ▼
                                  interview_turn     eval_run (Hamel gate)
```

Every arrow is a module in this directory. SQLite is the local MVP store;
the mirror schema in `supabase/migrations/074_entrepreneur_twins.sql`
gives cloud parity when we need shared runs.

## Quickstart (5 minutes, no network)

```bash
# 1. Validate the example person spec
python -m rag.twins.ingest_person \
    rag/twins/persons/example-distribuidor.yaml --dry-run

# 2. Actually ingest (still offline — source is a local .md)
python -m rag.twins.ingest_person \
    rag/twins/persons/example-distribuidor.yaml --holdout-ratio 0.2

# 3. Build the twin (requires ANTHROPIC_API_KEY; use --dry-run otherwise)
python -m rag.twins.build_twin example-distribuidor --dry-run

# 4. Mock chat (no API — echoes corpus hits so the tool loop is visible)
python -m rag.twins.chat_with_twin <twin_id> --mock

# 5. Mock eval (no API — trivially returns cosine=1.0 so the plumbing runs)
python -m rag.twins.eval_twin <twin_id> --mock
```

## Agent-vs-agent interviews (`interview_archetype`)

Teresa-style continuous discovery: interviewer agent + twin agent (with
`corpus_search`). Profile detection and prompt templates live in
`interview_profile.py`.

| Mode | Cohort | CLI |
|------|--------|-----|
| `population` | `arch-a/b/c/d/e-*` consumers | `interview_archetype <twin_id> --mode population` |
| `marketing_buyer` | `arch-mkt-*`, CMO YAMLs (`marketing-pros-br`) | `interview_marketing_buyer <twin_id>` or `--mode marketing-buyer` |

Requires `twin_id` (UUID) in `twins.db` after ingest + build. Marketing
discovery program (Insights/Lab): see
`company/SyntheticPerson/syntheticperson-ai/46-ASPASIA-IZA-ROADMAP-ORCHESTRATION.md` §4.

```bash
python3 -m rag.twins.interview_marketing_buyer <twin_id> --turns 8 --mock
```

Aspasia/Iza skills: `aspasia/skills/RESEARCH-STACK.md`, `iza/skills/RESEARCH-STACK.md`.

## Self-hosted runner

Full Mode runs on a self-hosted GitHub Actions runner (DO droplet) with
label `twins`. GitHub's shared `ubuntu-latest` pool is avoided because
it intermittently blocks YouTube outbound and occasionally ignores
`timeout-minutes`. One-time setup + ops notes live in
[`SELF_HOSTED_RUNNER.md`](SELF_HOSTED_RUNNER.md). Once registered, every
`mode=full` dispatch — UI- or file-triggered — lands on the droplet.

## Local run (`run_twin_local.sh`)

For one-off debugging or when you'd rather not go through GitHub, run
the exact same pipeline locally:

```bash
export OPENAI_API_KEY=... ANTHROPIC_API_KEY=... VOYAGE_API_KEY=...
bash rag/twins/run_twin_local.sh mrv-rubens-menin
```

Same flags as `run_all` (`--dry-run`, `--skip-transcribe`,
`--skip-build-eval`). Prints the acceptance summary at the end, writes
`rag/twins/run_all_report.json` + `rag/twins/twins.db`.

## Batch orchestrator (`run_all.py`)

`run_all.py` drives the full pipeline (transcribe → ingest → build → eval)
across every `persons/*.yaml` spec. Always start with `--dry-run` to see
the plan before paying anything:

```bash
# plan-only (no network, no API)
python -m rag.twins.run_all --dry-run

# first 3 specs end-to-end (requires yt-dlp, OPENAI_API_KEY,
# ANTHROPIC_API_KEY, VOYAGE_API_KEY)
python -m rag.twins.run_all --limit 3

# one specific slug (end-to-end)
python -m rag.twins.run_all --only mrv-rubens-menin

# refresh build+eval without re-fetching audio
python -m rag.twins.run_all --skip-transcribe

# stop after ingest (useful when calibrating the corpus, no API cost)
python -m rag.twins.run_all --skip-build-eval
```

Orchestrator guarantees:

- **URL sanity check** flags YouTube channel/handle URLs (`youtube.com/@…`)
  that look like a channel rather than a specific episode — so yt-dlp
  never accidentally downloads an entire channel.
- **Per-spec isolation** — a failure in one person doesn't abort the batch.
- **Consolidated report** at `rag/twins/run_all_report.json` (gitignored)
  with per-person stage durations, notes, and a final summary of how
  many twins passed the Hamel gate.
- **Cost control** via `--limit N` — always cap the first real run.

## MVP status

| Piece                  | Module                 | MVP?  | Notes                                    |
| ---------------------- | ---------------------- | ----- | ---------------------------------------- |
| Structured schema      | `schema.py`            | ✅    | 25 fields, Pydantic, versioned           |
| SQLite storage         | `storage.py`           | ✅    | All writes go through this module        |
| Corpus ingestion       | `ingest_person.py`     | ✅    | Firecrawl (URL) + local paths            |
| Twin extraction        | `build_twin.py`        | ✅    | Anthropic tool-use, single-pass          |
| Retrieval tool         | `corpus_search.py`     | ✅    | Voyage cosine + keyword fallback         |
| Turn-based chat        | `chat_with_twin.py`    | ✅    | Anthropic + tool loop + SQLite log       |
| Holdout cosine eval    | `eval_twin.py`         | ✅    | Hamel layer 1; layers 2+3 are Phase 2    |
| Composite (archetypes) | —                      | ❌    | Phase 2 — cluster by decision fingerprint |
| Stylometry eval        | —                      | ❌    | Phase 2 — sentence length, jargon ratio  |
| LLM-as-judge eval      | —                      | ❌    | Phase 2 — pairwise preference, <65% hit  |
| Observer/synthesizer   | —                      | ❌    | Phase 3 — only if manual synth stalls    |

## Ethics & LGPD

Agreed in war-room (Claire's ruling, written to `projects/memory/`):

1. **Composite twins are the default.** Build arc hetypes from 3–5 people
   sharing a decision fingerprint; anonymize publicly.
2. **Nominal twins (real name) require either**:
   - explicit written authorization on file, OR
   - a public-figure + clearly-public-statement exception (talks, press,
     podcasts) — flagged as `authorization: public_figure` in the spec.
3. **Right-to-delete.** If a person requests removal, we expunge corpus
   within 15 days and deprecate the derived twins (`status: deprecated`).
   The `authorization: denied` value on ingestion refuses the pipeline
   outright.
4. **No republication.** Twin outputs are for internal discovery only —
   they never leave the product/research loop as "quotes from person X".

Before ingesting anyone, answer the three LGPD questions in the project
root `CLAUDE.md` / `SETUP_AUTH.md`. Not optional.

## Production gate (Hamel)

`schema.passes_production_gate(twin)` returns `(bool, reasons)`. A twin may
only be promoted to `production` when:

- `corpus.source_count ≥ 3`
- `len(corpus.source_types) ≥ 2`
- `corpus.total_tokens ≥ 10_000`
- `eval_scores["holdout_cosine_p70"] ≥ 0.75`

Layer 2 (stylometry divergence ≤ 20%) and layer 3 (LLM-judge hit rate ≤
65%) are tracked in the roadmap and will tighten this gate before any
real interviewer hits a production twin. Until then, use `eval_passed`
for discovery work — it means the basic fidelity check runs green.

## Roadmap

1. Fernanda picks the anchor vertical (depends on prior war-room output).
2. Shreya lists 20 public entrepreneurs in that vertical. **Done** — see
   `persons/_backlog.md` (30 candidates covering mid-market SP food +
   adjacent verticals, all `authorization: public_figure`).
3. Phase 1 MVP cycle on 1 person → Lenny does a 30-min interview → human
   review → calibrate.
4. Phase 2: cluster to 5 archetypes, build composite twins, wire layers
   2 + 3 of the eval harness.
5. Phase 3: 20 interviews, humans synthesize, decide whether the
   observer agent earns its place.

Go/no-go at D+70: did twin-assisted discovery produce insights that were
confirmed by ≥3 real validation interviews? If not, kill the twin project
and do Paul Graham's 30 calls.

## Transcription pipeline

Every backlog spec under `persons/<slug>.yaml` carries a mix of `url:`
(YouTube channels, podcasts, LinkedIn) and `path:` (pending local
transcripts under `_corpus/<slug>/`). `rag/twins/transcribe.py` turns
each `url:` into a `path:` transcript:

```
URL ──[yt-dlp]──▶ audio.m4a
    ──[OpenAI Whisper API]──▶ text
    ──[render markdown header]──▶ _corpus/<slug>/<descriptor>.md
```

```bash
# single URL
python -m rag.twins.transcribe \
    --url https://www.youtube.com/watch?v=XXX \
    --out rag/twins/persons/_corpus/mrv-rubens-menin/os-socios-2022.md \
    --source-date 2022-08-11 --source-type podcast --title "Os Sócios #142"

# batch: every media URL in a person spec
python -m rag.twins.transcribe --spec rag/twins/persons/mrv-rubens-menin.yaml

# dry run — just print what would happen, no network
python -m rag.twins.transcribe --spec <file> --dry-run
```

Design rules enforced by the implementation:

- **Graceful**: missing `yt-dlp` or `openai` raises a clear actionable
  error; we never silently skip a source.
- **Cached**: audio + transcripts keyed by URL hash under
  `rag/twins/.transcribe_cache/`. Re-runs are cheap + idempotent.
- **Honest on unsupported URLs**: Spotify / Apple Podcasts web URLs
  are DRM-protected and rejected up-front — use the show's RSS or
  YouTube mirror instead.
- **Provenance header**: every transcript starts with a YAML front
  matter (source_url, source_date, source_type, duration_sec,
  language, whisper_model). Chunker ignores front matter, embeddings
  stay clean, audit stays traceable.
- **Rate-limit aware**: bounded retries with exponential backoff on
  the Whisper call.

Out of scope for v1 (tracked as Phase 2):
- Speaker diarization (pyannote — header already carries the TODO).
- Paywall bypass for Valor/Exame — those stay on `path:` + manual drop.

## Extending to all Febrain personas (architectural roadmap)

The `ingest → chunk → embed → store → retrieve` pipeline here is generic.
It was designed for entrepreneur twins, but **any persona backed by a real
person** (Lenny Rachitsky, April Dunford, Claire Vo, Hamel Husain,
Teresa Torres, …) can use the exact same pipeline to build a grounded
corpus instead of being driven only by the `persona_md` hand-authored
markdown.

Proposed standard (discussed with Fernanda, April 2026):

1. Each real-person persona under `teams/*/agents/*.md` gains a sibling
   `teams/*/agents/<slug>.sources.yaml` using the same `SourceSpec`
   schema as twins.
2. The sync step (`product/supabase/seed_personas_skills.py`) learns to
   also drive the transcription worker + embed sources → populate a new
   `persona_sources` table mirroring `twin_corpus_chunk`.
3. The existing `persona_md` (hand-authored, canonical) becomes the
   system prompt; the embedded sources become the RAG substrate the
   persona retrieves from during real work — just like a twin does with
   `corpus_search`.

This is an additive change, doesn't touch the current markdown
authorship, and unifies how all personas get grounded in real public
statements. Decision to pursue this is scope for a separate RFC — not
part of the twins MVP PR.
