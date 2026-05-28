# Twins Supabase Sync Guide

## Status

✅ **Migration Created:** `supabase/migrations/074a_entrepreneur_twins.sql`
✅ **Sync Script Created:** `rag/twins/sync_to_supabase.py`
⏳ **Blocked:** Awaiting Supabase DB password for direct SQL execution

## Schema

The Supabase schema (defined in migration 074a) has these tables:

- `twin_person` — metadata about the subject (name, archetype, authorization status)
- `twin_corpus_chunk` — chunks of source material with embeddings
- `twin` — the generated twin profile (JSON schema)
- `twin_eval_run` — evaluation scores from the quality gate
- `twin_interview_turn` — full transcript of interviews with the twin

## Workflow

### 1. Deploy Migration (CI/CD automatic)

When `supabase/migrations/074a_entrepreneur_twins.sql` is merged to main, GitHub Actions automatically runs Supabase migrations via the deploy pipeline.

**Current Status:** Migration is checked in and ready for deployment.

### 2. Run Sync Script

Once tables exist in Supabase, run:

```bash
# Set credentials
export SUPABASE_URL=https://ftlzbhmjjtetrchfcxtv.supabase.co
export SUPABASE_SERVICE_ROLE_KEY=<from GitHub secrets>

# Sync from local SQLite
python3 rag/twins/sync_to_supabase.py --db-path rag/twins/twins.db

# Or from runner artifact
python3 rag/twins/sync_to_supabase.py --db-path /tmp/run61/twins.db
```

**Output:**
```
✓ Synced 1 persons
✓ Synced 35 corpus chunks
✓ Synced 1 twins
✓ Synced 0 interview turns
✓ Synced 1 eval runs
```

## Next Steps (After Deploy)

### Manual Migration (if needed)

If migrations don't run via CI/CD, run manually:

```bash
# 1. Get database password (ask Fernanda)
export SUPABASE_DB_PASSWORD=<password>

# 2. Run migration via psql
PGPASSWORD=$SUPABASE_DB_PASSWORD psql \
  -h ftlzbhmjjtetrchfcxtv.db.supabase.co \
  -U postgres \
  -d postgres \
  -f supabase/migrations/074a_entrepreneur_twins.sql

# 3. Run sync
python3 rag/twins/sync_to_supabase.py
```

### Verify Sync in Supabase

```sql
-- Check persons synced
SELECT COUNT(*) as person_count FROM twin_person;

-- Check chunks synced
SELECT COUNT(*) as chunk_count, 
       SUM(token_count) as total_tokens
FROM twin_corpus_chunk;

-- Check twins
SELECT id, person_id, status, (schema_json->>'operator'->>'name') as operator_name
FROM twin;

-- Check evals
SELECT twin_id, passed, scores_json->>'p70' as p70_score
FROM twin_eval_run
ORDER BY created_at DESC;
```

## Quality Gate Notes

Current eval results (need improvement for production):

- **Eugene Yan:** p70=0.7191 (1.9% short of 0.75 threshold)
- **Alex-Xu:** p70=0.6597 (12% short, only 75% domain coverage)

### Improving Quality

To pass quality gates, twins need more/better sources:

1. Add more YouTube interviews / podcasts in YAML specs
2. Add LinkedIn posts, Twitter threads, Medium articles
3. Re-run `rag/twins/build_twin.py` on each updated spec
4. Check eval results in eval_run table

Example: Increase eugene-yan sources from 3 to 5-7 URLs, then rebuild.

## Architecture

```
Local SQLite                Supabase PostgreSQL
(rag/twins/twins.db)        (Cloud persistent)
├─ person                   ├─ twin_person
├─ corpus_chunk             ├─ twin_corpus_chunk  ← HNSW embeddings
├─ twin                     ├─ twin
├─ eval_run                 ├─ twin_eval_run
└─ interview_turn           └─ twin_interview_turn

    ↓ ↓ ↓ (sync_to_supabase.py)

Sync runs:
- Local: After rag/twins/build_twin.py completes
- CI/CD: After each GitHub Actions twins-run dispatch
- Manual: python3 rag/twins/sync_to_supabase.py
```

## Files Reference

| File | Purpose |
|------|---------|
| `supabase/migrations/074a_entrepreneur_twins.sql` | Supabase schema definition |
| `rag/twins/sync_to_supabase.py` | SQLite → Supabase sync script |
| `rag/twins/storage.py` | Local SQLite layer (unchanged) |
| `rag/twins/build_twin.py` | Builds twins, writes to SQLite |
| `.github/workflows/twins-run.yml` | CI/CD workflow that runs build_twin |

## Troubleshooting

**Error: "Could not find table 'public.twin_person'"**
→ Migration hasn't run yet. Wait for next deployment or apply manually.

**Error: "No API key found in request"**
→ SUPABASE_SERVICE_ROLE_KEY not set. Export it before running sync.

**Error: "SUPABASE_DB_PASSWORD not set"**
→ Needed only for manual SQL execution. Not needed for REST API sync.

**Sync synced 0 records**
→ Check `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` are correct.
→ Verify tables exist in Supabase console.

---

**Created:** 2026-04-24  
**Status:** Ready for deployment + sync (awaiting schema deployment)
