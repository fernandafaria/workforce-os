-- ============================================================================
-- Workforce OS — Migration 002: move populational archetypes to their proper home
-- ============================================================================
--
-- Forty "Arquétipo populacional" entries previously lived in the `twin` +
-- `twin_person` tables (authorization='archetype_synthetic') by historical
-- accident — they share infrastructure with cognitive twins of real people
-- but represent something semantically different: aggregated demographic
-- segments synthesized for Voice-of-Customer research.
--
-- The `synthetic_personas` table was designed for exactly this purpose
-- (demographics / psychographics / behavioral / voice jsonb columns,
-- summary, brief, confidence, pinned flag) but had been sitting empty.
--
-- This migration:
--   1. Copies each archetype twin → synthetic_personas row, owned by
--      the workspace founder (admfaria@gmail.com — the schema requires
--      a non-null user_id with FK to auth.users; treating these as her
--      personal library entries until a "library" pattern is added).
--   2. Marks the original twin rows as ``deprecated`` (audit trail,
--      not deletion) so the `twin` table now means "cognitive twins of
--      real people" going forward.
--
-- Idempotent: ``ON CONFLICT (user_id, slug) DO NOTHING`` for inserts and
-- the UPDATE WHERE status='draft' is a no-op on re-run.
--
-- Applied to production: 2026-05-28
-- Result: 40 archetypes moved, 40 twins deprecated, 63 public_figure
-- twins left untouched.
-- ============================================================================

-- Step 1 — Copy archetypes into synthetic_personas.
-- Only specify columns without defaults; the rest (headline, demographics,
-- psychographics, behavioral, voice, summary, confidence, pinned,
-- created_at, updated_at) use their column defaults.
INSERT INTO public.synthetic_personas (
    user_id, slug, headline, summary, brief, model_ref
)
SELECT
    '2640c7af-8167-4e26-9bab-0260e456a3e4'::uuid                     AS user_id,
    tp.id                                                            AS slug,
    COALESCE(t.archetype_label, tp.name_public)                      AS headline,
    LEFT(COALESCE(t.schema_json ->> 'notes', ''), 2000)              AS summary,
    jsonb_build_object(
        'origin', 'twin_archetype_migration_2026_05_28',
        'twin_id', t.id,
        'twin_person_id', tp.id,
        'archetype_label', t.archetype_label,
        'sources', COALESCE(t.schema_json -> 'sources', '[]'::jsonb),
        'notes', COALESCE(t.schema_json -> 'notes', 'null'::jsonb)
    )                                                                AS brief,
    'pending-synthesis'                                              AS model_ref
FROM public.twin t
JOIN public.twin_person tp ON tp.id = t.person_id
WHERE tp.authorization = 'archetype_synthetic'
ON CONFLICT (user_id, slug) DO NOTHING;

-- Step 2 — Deprecate the source twin rows (keep them, do not delete).
UPDATE public.twin t
SET
    status      = 'deprecated',
    updated_at  = now(),
    schema_json = COALESCE(t.schema_json, '{}'::jsonb)
                  || jsonb_build_object(
                       'deprecated_reason', 'moved to synthetic_personas (migration 002)',
                       'deprecated_at', now()
                     )
FROM public.twin_person tp
WHERE tp.id = t.person_id
  AND tp.authorization = 'archetype_synthetic'
  AND t.status = 'draft';
