-- Workforce OS — Initial Schema
-- Migration 001: personas, memories, knowledge base

-- Enable pgvector extension (required for semantic search)
CREATE EXTENSION IF NOT EXISTS vector;

-- ============================================================================
-- Personas (FeBrain agent registry)
-- ============================================================================
CREATE TABLE IF NOT EXISTS personas (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    slug        TEXT UNIQUE NOT NULL,
    handle      TEXT NOT NULL,
    name        TEXT NOT NULL,
    prompt      TEXT NOT NULL DEFAULT '',
    home_team   TEXT,
    domains     TEXT[] DEFAULT '{}',
    is_active   BOOLEAN DEFAULT true,
    created_at  TIMESTAMPTZ DEFAULT now(),
    updated_at  TIMESTAMPTZ DEFAULT now()
);

-- Index for team filtering + search
CREATE INDEX IF NOT EXISTS idx_personas_team ON personas (home_team) WHERE home_team IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_personas_active ON personas (is_active) WHERE is_active = true;

-- Full-text search on persona name/handle/domains
CREATE INDEX IF NOT EXISTS idx_personas_search ON personas
    USING GIN (to_tsvector('simple', name || ' ' || handle || ' ' || array_to_string(domains, ' ')));

-- ============================================================================
-- Observational Memory (raw session captures)
-- ============================================================================
CREATE TABLE IF NOT EXISTS observational_memory (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     TEXT NOT NULL,
    session_type TEXT NOT NULL DEFAULT 'council',
    topic       TEXT,
    agents      TEXT[] DEFAULT '{}',
    raw_output  JSONB DEFAULT '{}',
    created_at  TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_om_user ON observational_memory (user_id);
CREATE INDEX IF NOT EXISTS idx_om_created ON observational_memory (created_at DESC);

-- ============================================================================
-- Distilled Memory (decisions, risks, actions extracted from sessions)
-- ============================================================================
CREATE TABLE IF NOT EXISTS distilled_memory (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     TEXT NOT NULL,
    memory_type TEXT NOT NULL DEFAULT 'decision',  -- decision, risk, action, insight, question
    content     TEXT NOT NULL,
    source_session UUID REFERENCES observational_memory(id) ON DELETE SET NULL,
    embedding   vector(1536),  -- Voyage AI embeddings (1536-dim)
    metadata    JSONB DEFAULT '{}',
    created_at  TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_dm_user ON distilled_memory (user_id);
CREATE INDEX IF NOT EXISTS idx_dm_type ON distilled_memory (memory_type);
CREATE INDEX IF NOT EXISTS idx_dm_embedding ON distilled_memory
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- ============================================================================
-- Knowledge Base (vertical-specific documents for RAG)
-- ============================================================================
CREATE TABLE IF NOT EXISTS knowledge_base (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    vertical    TEXT NOT NULL,
    title       TEXT NOT NULL,
    content     TEXT NOT NULL,
    source_url  TEXT,
    embedding   vector(1536),
    metadata    JSONB DEFAULT '{}',
    created_at  TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_kb_vertical ON knowledge_base (vertical);
CREATE INDEX IF NOT EXISTS idx_kb_embedding ON knowledge_base
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- ============================================================================
-- Memory search function (pgvector similarity)
-- ============================================================================
CREATE OR REPLACE FUNCTION search_memories(
    query_embedding vector(1536),
    user_id TEXT,
    memory_type_filter TEXT DEFAULT NULL,
    match_limit INT DEFAULT 10
)
RETURNS TABLE (
    id UUID,
    content TEXT,
    memory_type TEXT,
    similarity FLOAT,
    created_at TIMESTAMPTZ
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT
        dm.id,
        dm.content,
        dm.memory_type,
        1 - (dm.embedding <=> query_embedding) AS similarity,
        dm.created_at
    FROM distilled_memory dm
    WHERE dm.user_id = $2
      AND (memory_type_filter IS NULL OR dm.memory_type = memory_type_filter)
    ORDER BY dm.embedding <=> query_embedding
    LIMIT match_limit;
END;
$$;

-- ============================================================================
-- Persona matching function (hybrid: domain + semantic)
-- ============================================================================
CREATE OR REPLACE FUNCTION match_personas(
    query_embedding vector(1536),
    query_domain TEXT DEFAULT NULL,
    match_limit INT DEFAULT 5
)
RETURNS TABLE (
    slug TEXT,
    handle TEXT,
    name TEXT,
    home_team TEXT,
    source TEXT,
    score FLOAT
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT
        p.slug,
        p.handle,
        p.name,
        p.home_team,
        CASE
            WHEN query_domain IS NOT NULL AND query_domain = ANY(p.domains) THEN 'domain'
            ELSE 'semantic'
        END AS source,
        CASE
            WHEN query_domain IS NOT NULL AND query_domain = ANY(p.domains) THEN 0.9
            ELSE 0.5
        END AS score
    FROM personas p
    WHERE p.is_active = true
    ORDER BY score DESC
    LIMIT match_limit;
END;
$$;
