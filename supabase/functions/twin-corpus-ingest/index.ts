// supabase/functions/twin-corpus-ingest/index.ts
//
// Stage 2 of twin creation: fetch URL sources, extract main text, chunk,
// embed (Voyage-4 1024d), upsert into twin_corpus_chunk.
//
// Idempotent: skips source URLs already present in twin_corpus_chunk
// for the same person_id (override with force=true). Marks ~15% of new
// chunks as `holdout=true` randomly so a future eval has unseen data.
//
// Auth: requires Supabase service_role JWT.
//
// Body: { twin_id: uuid, max_sources?: number, force?: boolean }
// Returns:
//   { twin_id, person_id, sources_processed, sources_skipped,
//     sources_failed: [{url, reason}], chunks_created, holdout_count }

import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const SUPABASE_URL = Deno.env.get("SUPABASE_URL") || "";
const SUPABASE_SERVICE_ROLE_KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") || "";
const VOYAGE_API_KEY = Deno.env.get("VOYAGE_API_KEY") || "";

const EMBEDDING_MODEL = "voyage-4";
const EMBEDDING_DIMENSIONS = 1024;
const TARGET_CHUNK_CHARS = 6000; // ~1500 tokens
const CHUNK_OVERLAP_CHARS = 600;
const HOLDOUT_RATIO = 0.15;
const FETCH_TIMEOUT_MS = 20000;
const USER_AGENT = "WorkforceOS-TwinIngest/1.0 (+https://workforce-os)";

interface IngestRequest {
  twin_id: string;
  max_sources?: number;
  force?: boolean;
}

interface Source {
  url?: string;
  path?: string;
  type?: string;
  date?: string;
  title?: string;
  first_person?: boolean;
}

interface FailedSource {
  url: string;
  reason: string;
}

function requireServiceRole(req: Request): Response | null {
  const authHeader = req.headers.get("Authorization") || "";
  const token = authHeader.replace(/^Bearer\s+/, "");
  try {
    const payload = JSON.parse(atob(token.split(".")[1] ?? ""));
    if (payload?.role !== "service_role") {
      return jsonResponse({ error: "service_role required" }, 401);
    }
  } catch {
    return jsonResponse({ error: "invalid token" }, 401);
  }
  return null;
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

// Very simple HTML → text extraction. Strips script/style, then tags.
// Not as good as Firecrawl but good enough for an MVP on talks/blogs/wiki.
function htmlToText(html: string): string {
  return html
    .replace(/<script[\s\S]*?<\/script>/gi, " ")
    .replace(/<style[\s\S]*?<\/style>/gi, " ")
    .replace(/<noscript[\s\S]*?<\/noscript>/gi, " ")
    .replace(/<!--[\s\S]*?-->/g, " ")
    .replace(/<\/(p|div|section|article|h[1-6]|li|br)>/gi, "\n")
    .replace(/<br\s*\/?>/gi, "\n")
    .replace(/<[^>]+>/g, " ")
    .replace(/&nbsp;/g, " ")
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/\r\n?/g, "\n")
    .replace(/[ \t]+/g, " ")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

async function fetchUrl(url: string): Promise<{ text: string } | { error: string }> {
  try {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS);
    const resp = await fetch(url, {
      headers: { "User-Agent": USER_AGENT, Accept: "text/html,application/xhtml+xml" },
      redirect: "follow",
      signal: controller.signal,
    });
    clearTimeout(timeout);
    if (!resp.ok) return { error: `HTTP ${resp.status}` };
    const ct = resp.headers.get("content-type") || "";
    if (!ct.includes("html") && !ct.includes("text")) {
      return { error: `unsupported content-type: ${ct}` };
    }
    const html = await resp.text();
    const text = htmlToText(html);
    if (text.length < 200) return { error: "extracted text too short" };
    return { text };
  } catch (e) {
    return { error: (e as Error).message };
  }
}

function chunkText(text: string): string[] {
  const chunks: string[] = [];
  let i = 0;
  while (i < text.length) {
    const end = Math.min(i + TARGET_CHUNK_CHARS, text.length);
    let cut = end;
    // Prefer to cut on paragraph boundary if one exists in last 20% of chunk
    if (end < text.length) {
      const searchStart = i + Math.floor(TARGET_CHUNK_CHARS * 0.8);
      const para = text.lastIndexOf("\n\n", end);
      if (para > searchStart) cut = para;
    }
    const piece = text.slice(i, cut).trim();
    if (piece.length > 100) chunks.push(piece);
    if (cut >= text.length) break;
    i = Math.max(cut - CHUNK_OVERLAP_CHARS, i + 1);
  }
  return chunks;
}

async function embed(text: string): Promise<number[] | null> {
  if (!VOYAGE_API_KEY) return null;
  try {
    const resp = await fetch("https://api.voyageai.com/v1/embeddings", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${VOYAGE_API_KEY}`,
      },
      body: JSON.stringify({
        model: EMBEDDING_MODEL,
        input: text.slice(0, 16000),
        input_type: "document",
        output_dimension: EMBEDDING_DIMENSIONS,
      }),
    });
    if (!resp.ok) {
      console.error(`Voyage error ${resp.status}: ${await resp.text()}`);
      return null;
    }
    const data = await resp.json();
    return data.data?.[0]?.embedding ?? null;
  } catch (e) {
    console.error("Voyage embed failed", e);
    return null;
  }
}

function estimateTokens(text: string): number {
  return Math.ceil(text.length / 4);
}

Deno.serve(async (req) => {
  if (req.method !== "POST") return new Response("Method not allowed", { status: 405 });
  const denied = requireServiceRole(req);
  if (denied) return denied;
  if (!VOYAGE_API_KEY) return jsonResponse({ error: "VOYAGE_API_KEY not set" }, 503);

  const body: IngestRequest = await req.json().catch(() => ({ twin_id: "" }));
  if (!body.twin_id) return jsonResponse({ error: "twin_id required" }, 400);

  const supabase = createClient(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY);

  // Load twin
  const { data: twin, error: twinErr } = await supabase
    .from("twin")
    .select("id, person_id, schema_json")
    .eq("id", body.twin_id)
    .single();
  if (twinErr || !twin) {
    return jsonResponse({ error: `twin not found: ${twinErr?.message}` }, 404);
  }

  const personId: string | null = twin.person_id;
  if (!personId) return jsonResponse({ error: "twin has no person_id" }, 400);

  const sources: Source[] = (twin.schema_json?.sources ?? []) as Source[];
  if (sources.length === 0) {
    return jsonResponse({ error: "twin has no sources to ingest" }, 400);
  }

  // What URLs are already ingested?
  const { data: existingChunks } = await supabase
    .from("twin_corpus_chunk")
    .select("source_url")
    .eq("person_id", personId);
  const seenUrls = new Set<string>(
    (existingChunks ?? []).map((c) => c.source_url).filter((u): u is string => !!u),
  );

  const candidates = sources.filter((s) => !!s.url);
  const toProcess = body.max_sources ? candidates.slice(0, body.max_sources) : candidates;

  const failed: FailedSource[] = [];
  let chunksCreated = 0;
  let holdoutCount = 0;
  let sourcesProcessed = 0;
  let sourcesSkipped = 0;

  for (const src of toProcess) {
    const url = src.url!;
    if (!body.force && seenUrls.has(url)) {
      sourcesSkipped++;
      continue;
    }

    const fetched = await fetchUrl(url);
    if ("error" in fetched) {
      failed.push({ url, reason: fetched.error });
      continue;
    }

    const chunks = chunkText(fetched.text);
    if (chunks.length === 0) {
      failed.push({ url, reason: "no chunks produced" });
      continue;
    }

    for (const chunkText_ of chunks) {
      const embedding = await embed(chunkText_);
      if (!embedding) {
        failed.push({ url, reason: "embedding failed" });
        continue;
      }
      const holdout = Math.random() < HOLDOUT_RATIO;
      const row = {
        person_id: personId,
        source_url: url,
        source_type: src.type ?? null,
        source_date: src.date ?? null,
        first_person: src.first_person ?? null,
        text: chunkText_,
        token_count: estimateTokens(chunkText_),
        quality_score: 0.7, // baseline; eval/refine in a later pass
        holdout,
        embedding,
      };
      const { error: insErr } = await supabase.from("twin_corpus_chunk").insert(row);
      if (insErr) {
        failed.push({ url, reason: `insert: ${insErr.message}` });
        continue;
      }
      chunksCreated++;
      if (holdout) holdoutCount++;
    }
    sourcesProcessed++;
  }

  return jsonResponse({
    twin_id: body.twin_id,
    person_id: personId,
    sources_total: sources.length,
    sources_with_url: candidates.length,
    sources_processed: sourcesProcessed,
    sources_skipped: sourcesSkipped,
    sources_failed: failed,
    chunks_created: chunksCreated,
    holdout_count: holdoutCount,
    model: EMBEDDING_MODEL,
    dimensions: EMBEDDING_DIMENSIONS,
  });
});
