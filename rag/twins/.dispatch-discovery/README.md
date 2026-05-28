# Discovery — file-triggered dispatch

Drop a `.yml` file here to enqueue a Discovery run. The
`.github/workflows/discovery-cron.yml` workflow picks it up on push to
`claude/**` or `main`, inserts a row into `discovery_runs` (Supabase),
and the queue drainer (also in the same workflow, runs every 12h)
processes it on its next tick.

Use this when you want an agent to fire-and-forget a Discovery sweep
without going through the `/discovery` UI.

## File format

```yaml
# Single dispatch:
company_id: <uuid>           # required — multi-tenant
user_id: <uuid>              # required — owner of the run
slug: claire-vo              # required — matches rag/twins/persons/<slug>.yaml
name: "Claire Vo"            # required — public name
usernames: [clairevo]        # ≥1 unless skip_maigret=true
wayback_domains: [claire.com]
enable_itunes: true
enable_firecrawl_podcasts: true
skip_maigret: false
```

Or multiple in one file:

```yaml
runs:
  - { company_id: ..., user_id: ..., slug: a, name: "A", usernames: [a] }
  - { company_id: ..., user_id: ..., slug: b, name: "B", usernames: [b] }
```

## Naming convention

`<ISO-date>-<seq>-<slug>.yml` — keeps history readable, sorts latest-first.
Example: `2026-04-30-001-claire-vo.yml`.

## What happens next

1. Push triggers `enqueue` job → inserts row(s) into `discovery_runs`
   with `status='queued'`, `triggered_by='file_dispatch'`.
2. Same workflow's `drain` job (or the next 12h cron tick) runs Maigret
   + Wayback + iTunes + Firecrawl on the queued run, persists candidates
   to `discovery_candidates`.
3. Operator reviews candidates at `/discovery/<run_id>` and approves the
   real ones. Approved candidates auto-apply to the twin spec and a
   draft PR is opened.
