# Self-hosted runner — twins pipeline

The twins Full Mode pipeline runs on a self-hosted GitHub Actions runner
labeled `twins` (instead of GitHub's shared `ubuntu-latest` pool). Reasons:

- GitHub's shared runners block outbound YouTube access roughly half the
  time — yt-dlp returns 403/429 and the pipeline quietly produces empty
  corpora.
- Shared runners occasionally stall for hours without respecting
  `timeout-minutes`.
- Full Mode is 15-40 min wall-clock per twin; consistent runners matter.

The workflow (`.github/workflows/twins-run.yml`) targets
`runs-on: [self-hosted, twins]` so every Full Mode run — whether triggered
via Actions UI or via commit to `rag/twins/.dispatch/*.yml` — lands on the
droplet.

## One-time setup on the droplet

1. **Create or reuse an Ubuntu 22.04 droplet** (1 vCPU / 2 GB RAM is
   sufficient; 4 GB comfortable for concurrent Whisper chunks).
2. **Get a runner registration token**:
   - Go to https://github.com/fernandafaria/febrain/settings/actions/runners/new
   - Choose **Linux x64**. Copy the `./config.sh --token ...` value.
3. **SSH and run the setup script**:

   ```bash
   ssh root@<droplet-ip>
   curl -fsSL \
     https://raw.githubusercontent.com/fernandafaria/febrain/main/scripts/setup-twins-runner.sh \
     | bash -s -- <RUNNER_TOKEN>
   ```

   The script:
   - Installs Python 3 + `ffmpeg` + `yt-dlp` + pip deps used by the
     workflow.
   - Creates a `runner` user and installs `actions/runner` v2.321.0 under
     `/opt/twins-runner`.
   - Registers the runner with labels `self-hosted,twins,Linux,X64`.
   - Starts the runner as a systemd service (`svc.sh install/start`), so it
     survives reboots.
   - Probes `yt-dlp` against a known Menin URL; warns loudly if YouTube
     still blocks this droplet.

4. **Verify**:
   - https://github.com/fernandafaria/febrain/settings/actions/runners
     shows the runner with status **Idle**.
   - On the droplet: `systemctl status actions.runner.fernandafaria-febrain.*`
     is active and streaming logs at `/opt/twins-runner/_diag/`.

## Secrets

Secrets continue to come from **repo-level Actions secrets** — GitHub
injects them into the runner environment at job start. Nothing extra lives
on the droplet filesystem.

Required for `mode=full`:

- `OPENAI_API_KEY`
- `ANTHROPIC_API_KEY`
- `VOYAGE_API_KEY`

Optional (enables article URL ingestion via Firecrawl):

- `FIRECRAWL_API_KEY`

## Triggering a run

Same two paths as before — neither requires UI access to the droplet:

**Commit-triggered (agents / automation)**

```bash
cat > rag/twins/.dispatch/2026-04-30-001-mrv-FULL.yml <<EOF
slug: mrv-rubens-menin
mode: full
confirm_full_mode: true
EOF
git add rag/twins/.dispatch/ && git commit -m "dispatch: menin full" && git push
```

The workflow fires on push (path filter on `rag/twins/.dispatch/*.yml`),
lands on the droplet because of `runs-on: [self-hosted, twins]`, runs
transcribe + ingest + build + eval, uploads the acceptance summary and
artifacts.

**Manual (GitHub UI)**

Actions tab → "Twins — run pipeline" → Run workflow → slug + mode.

## Common issues

- **"No runner matching labels [self-hosted, twins]"** — runner stopped or
  registration token expired. On droplet: `svc.sh status`, regenerate token
  if needed, rerun `./config.sh --token ... --replace`.
- **yt-dlp fails post-setup** — sometimes DO IP ranges temporarily make the
  block-list. `yt-dlp --update` on the droplet usually unblocks. If not,
  enable a residential proxy via `HTTPS_PROXY` env var in the runner's
  service unit.
- **Concurrent runs** — the workflow has
  `concurrency.group: twins-run-<slug>` so two dispatches for the same
  slug serialize. Different slugs can run in parallel if the droplet has
  headroom.

## Operational notes

- **Cost**: droplet is fixed monthly cost; Whisper + Opus + Voyage are
  per-run variable (~$8-20 per twin).
- **Disk**: transcript cache under `/opt/twins-runner/_work/febrain/febrain/rag/twins/.transcribe_cache/`
  persists across runs — don't nuke it casually, every re-run saves money.
- **LGPD**: transcripts are gitignored (`rag/twins/.gitignore`). They live
  only on the droplet + GitHub artifact storage (7-day retention).
