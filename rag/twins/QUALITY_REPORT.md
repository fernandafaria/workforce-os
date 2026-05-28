# Twins Quality Gate Evaluation Report

**Generated:** 2026-04-24  
**Pipeline Runs:** #60 (eugene-yan), #61 (alex-xu)  
**Status:** 2/2 twins **FAILED** quality gate (both below p70 ≥ 0.75 threshold)

---

## Executive Summary

| Twin | Chunks | Tokens | p70 (target: 0.75) | Hit Rate (≥0.75) | Domain Coverage | Status |
|------|--------|--------|-------------------|-----------------|-----------------|--------|
| **Eugene Yan** | 35 | 21,867 | **0.7191** ⚠️ | 16.7% (1/6) | 100% ✓ | FAILED |
| **Alex-Xu** | 5 | 2,328 | **0.6597** ❌ | 0% (0/2) | 75% ⚠️ | FAILED |

**Takeaway:** Eugene Yan is salvageable (+0.031 p70 needed). Alex-Xu needs significant additional sources.

---

## Eugene Yan — CLOSE FAILURE (1.9% short)

### Data Profile
- **Sources:** 3 URLs (interview, LinkedIn, article)
- **Chunks:** 35 extracted from corpus
- **Tokens:** 21,867 total
- **Holdout:** 6 reserved for evaluation

### Evaluation Metrics
```
n: 6 eval queries
mean:          0.6912
median:        0.6791
p70:           0.7191  ⚠️ (1.91% below 0.75)
p30_low:       0.6360
hit_rate_075:  0.1667  (only 1 query hit ≥0.75)
```

### Root Cause Analysis
- **Quality:** Marginal. The twin understood operator domain well (100% coverage) but responses had moderate confidence.
- **Coverage:** 6 eval queries tested different aspects; only 1 had strong match (≥0.75).
- **Likely Issue:** Chunking may be too coarse, or sources don't cover all operator nuances.

### Fix Strategy (Priority: Medium)

1. **Add 2-3 more high-quality sources** (aim for 50+ chunks total):
   - Additional YouTube talks or podcast interviews
   - Blog posts or Medium articles on specific domains (ML, RecSys, strategy)
   - Twitter/LinkedIn threads on engineering decisions

2. **Adjust chunking parameters** in `build_twin.py`:
   - Reduce chunk size (current ~600 tokens/chunk is standard)
   - Increase overlap between chunks
   - Target: 45-50 chunks total

3. **Re-run evaluation**:
   ```bash
   python rag/twins/build_twin.py --slug eugene-yan --rebuild
   ```

4. **Expected result:** With better coverage, p70 should reach ~0.75-0.78.

---

## Alex-Xu — MAJOR FAILURE (12% short)

### Data Profile
- **Sources:** 1 URL only (article)
- **Chunks:** 5 extracted
- **Tokens:** 2,328 total
- **Holdout:** 2 reserved for evaluation

### Evaluation Metrics
```
n: 2 eval queries (very small sample!)
mean:          0.6409
median:        0.6409
p70:           0.6597  ❌ (12% below 0.75)
p30_low:       0.6220
hit_rate_075:  0.0000  (no queries hit ≥0.75)
operator_domain_coverage: 0.75  (missing 25% of domains)
```

### Root Cause Analysis
- **Severe data insufficiency:** Only 5 chunks from 1 source is not enough.
- **Domain gap:** 25% of operator domains not covered (missing 2 of 8 domains).
- **Sample size:** With only 2 eval queries, results are unreliable.
- **Known issue:** Alex-Xu YAML spec likely has only 1 source URL in person list.

### Fix Strategy (Priority: Critical)

1. **Add 4-5 more sources immediately**:
   - YouTube interviews (search: "Alex Xu system design" or "Alex Xu architecture")
   - Podcast appearances (Lex Fridman, Software Engineering Daily, etc)
   - Blog posts / Medium articles on bytebytego.com or personal blog
   - Twitter/LinkedIn posts on architecture and scaling
   - Book excerpts (if any published content available)

2. **Verify domain coverage**:
   - Ensure sources touch: system design, API design, database architecture, scaling, distributed systems, leadership, product thinking, teaching
   - Current gap: likely missing leadership/product/teaching domains

3. **Rebuild with expanded sources**:
   ```bash
   # Update: teams/ai-engineering/agents/alex-xu.yaml
   # Add sources:
   #   - url: https://www.youtube.com/watch?v=... (interview 1)
   #   - url: https://www.youtube.com/watch?v=... (interview 2)
   #   - url: https://podcast.example.com/... (podcast)
   #   - url: https://blog.example.com/... (blog post)
   
   python rag/twins/build_twin.py --slug alex-xu --rebuild
   ```

4. **Expected result:** With 5-6 sources, should reach 30+ chunks, p70 ≥ 0.75.

---

## Quality Gate Criteria

The `holdout_cosine` harness evaluates:

1. **Holdout Set Match** — 20% of chunks held out during training
2. **Cosine Similarity** — measures relevance of twin answers to eval queries
3. **Threshold:** p70 (70th percentile) must be ≥ 0.75

### Why High Confidence Matters

- p70 ≥ 0.75: "Twin's answers are highly relevant 70% of the time"
- p70 < 0.75: "Too many medium-confidence answers; not production-ready"
- hit_rate_075: Shows fraction of queries with high confidence

**Both twins pass functional gates** (no errors, all domains mapped), but **fail confidence gate**.

---

## Next Steps

### Immediate (Today)
- ✅ Created sync infrastructure (sync_to_supabase.py)
- ✅ Documented quality findings

### Short-term (This week)
1. Find and add sources for alex-xu (critical blocker)
2. Add supplementary sources for eugene-yan
3. Rebuild both twins
4. Verify p70 ≥ 0.75 on re-eval

### Medium-term (Next week)
1. Deploy Supabase migrations (via CI/CD)
2. Run sync script to persist twins to cloud
3. Set up monitoring dashboard for eval metrics
4. Document source collection workflow for other personas

### Future Improvements
- Expand to remaining 4 personas (demis-hassabis, jim-fan, sundar-pichai, tim-cook)
- Implement source quality scoring
- Add semantic dedup to avoid redundant chunks
- Create UI for source management

---

## Files

- `rag/twins/persons/eugene-yan.yaml` — Add 2-3 more sources
- `rag/twins/persons/alex-xu.yaml` — Add 4-5 more sources
- `rag/twins/build_twin.py` — Rerun with `--rebuild` flag
- `supabase/migrations/074a_entrepreneur_twins.sql` — Ready for deploy

---

## How to Add Sources

**Example: Adding YouTube interview to YAML**

```yaml
# teams/ai-engineering/agents/alex-xu.yaml
sources:
  - url: "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    type: "interview"
    date: "2024-01-15"
  - url: "https://www.youtube.com/watch?v=..." # Add more like this
    type: "interview"
    date: "2024-02-20"
  - url: "https://bytebytego.com/..." # Blog post
    type: "article"
    date: "2024-03-10"
```

Then rebuild:
```bash
python rag/twins/build_twin.py --slug alex-xu --rebuild
```

The pipeline will:
1. Fetch sources (Firecrawl)
2. Extract chunks
3. Generate embeddings (Voyage)
4. Evaluate quality gate
5. Report results to eval_run table

---

**Report Date:** 2026-04-24  
**Next Review:** After sources are added and rebuilt
