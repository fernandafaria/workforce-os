# Twins — file-triggered dispatch

Drop a `.yml` file here to fire `.github/workflows/twins-run.yml` autonomously
(on push to `claude/**` or `main`). Useful for agents that don't have
`workflow_dispatch` tooling.

**Safety guardrail**: file-triggered runs default to `dry-run`. To opt into
paying Full Mode, the dispatch file must set **both** `mode: full` **and**
`confirm_full_mode: true`. Without the confirmation flag, the workflow
coerces back to dry-run and emits a warning. The Actions tab form trigger
is still the cleanest path for ad-hoc Full Mode runs.

## File format

```yaml
# Single slug:
slug: mrv-rubens-menin        # matches rag/twins/persons/<slug>.yaml

# OR multiple slugs in one run (single workflow invocation processes all):
slugs:
  - predilecta-vinicius-rosa
  - bauducco-scaramussa
  - wickbold-fernanda

mode: dry-run                 # optional; "full" REQUIRES confirm_full_mode
confirm_full_mode: false      # required true for full mode on file trigger
skip_transcribe: false        # optional, default false
skip_build_eval: false        # optional, default false
```

## Naming convention

`<ISO-date>-<seq>-<slug>-dryrun.yml` — keeps history readable, sorts latest-first.
Example: `2026-04-22-001-mrv-rubens-menin-dryrun.yml`.

The workflow picks the **newest** `*.yml` here (by lexical sort) per run, so a
new push with a new filename always re-triggers with those inputs. Lexical
sort is intentional: `actions/checkout` resets all mtimes to the same value,
so `ls -t` returns arbitrary order. Keep the `YYYY-MM-DD-NNN-*` prefix so
lexical = chronological.

## Queueing & parallelism

A single push that creates N dispatch files = **1 workflow trigger**, not N.
That run picks the newest file and processes only that one. To dispatch
multiple personas via file trigger, push each dispatch file in its **own
commit/push** — each push is an independent trigger.

Runs are **serialized on the self-hosted `twins` runner** (single instance):
even N parallel triggers queue rather than run concurrently. Wall-clock for
N personas in full mode ≈ N × (typical per-persona duration). For true
parallelism, use `workflow_dispatch` from the Actions tab with multiple
provisioned runners (out of scope of file trigger).

Race-condition note: if two file-trigger runs are queued near-simultaneously
and both started before either picks its `spec_file`, both may resolve to
the same "newest" file. In practice, sequential push with one commit per
dispatch avoids this; if you need to batch, prefer the multi-slug `slugs:`
list inside a single dispatch file.
