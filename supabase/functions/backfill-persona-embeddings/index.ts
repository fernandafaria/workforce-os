// supabase/functions/backfill-persona-embeddings/index.ts
//
// Generates Voyage AI embeddings for personas that don't yet have one.
// Idempotent: only processes WHERE embedding IS NULL.
//
// Invocation (service_role required):
//   POST /functions/v1/backfill-persona-embeddings
//   Body: { "limit": 150, "dry_run": false }
//
// Used to backfill the 150 Febrain personas the first time they enter
// the canonical match_personas() flow.

import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const SUPABASE_URL = Deno.env.get("SUPABASE_URL") || "";
const SUPABASE_SERVICE_ROLE_KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") || "";
const VOYAGE_API_KEY = Deno.env.get("VOYAGE_API_KEY") || "";

const EMBEDDING_MODEL = "voyage-4";
const EMBEDDING_DIMENSIONS = 1024;
const MAX_INPUT_CHARS = 16000;

interface BackfillRequest {
  limit?: number;
  dry_run?: boolean;
  slug?: string;
}

interface PersonaRow {
  id: string;
  slug: string;
  name: string;
  role: string | null;
  persona_md: string;
}

async function embed(text: string): Promise<number[]> {
  const resp = await fetch("https://api.voyageai.com/v1/embeddings", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${VOYAGE_API_KEY}`,
    },
    body: JSON.stringify({
      model: EMBEDDING_MODEL,
      input: text.slice(0, MAX_INPUT_CHARS),
      input_type: "document",
      output_dimension: EMBEDDING_DIMENSIONS,
    }),
  });
  if (!resp.ok) {
    throw new Error(`Voyage API ${resp.status}: ${await resp.text()}`);
  }
  const data = await resp.json();
  return data.data?.[0]?.embedding;
}

function personaText(p: PersonaRow): string {
  const header = `${p.name}${p.role ? " — " + p.role : ""}`;
  return `${header}\n\n${p.persona_md}`;
}

Deno.serve(async (req) => {
  if (req.method !== "POST") return new Response("Method not allowed", { status: 405 });

  // verify_jwt: true already validated the JWT signature. We additionally
  // require the role claim to be "service_role" so authenticated end-users
  // can't trigger an expensive Voyage backfill.
  const authHeader = req.headers.get("Authorization") || "";
  const token = authHeader.replace(/^Bearer\s+/, "");
  try {
    const payload = JSON.parse(atob(token.split(".")[1] ?? ""));
    if (payload?.role !== "service_role") {
      return new Response(JSON.stringify({ error: "service_role required" }), {
        status: 401,
        headers: { "Content-Type": "application/json" },
      });
    }
  } catch {
    return new Response(JSON.stringify({ error: "invalid token" }), {
      status: 401,
      headers: { "Content-Type": "application/json" },
    });
  }

  const body: BackfillRequest = await req.json().catch(() => ({}));
  const limit = body.limit ?? 200;
  const dryRun = body.dry_run ?? false;

  const supabase = createClient(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY);

  let query = supabase
    .from("personas")
    .select("id, slug, name, role, persona_md")
    .is("embedding", null)
    .eq("status", "canonical")
    .limit(limit);
  if (body.slug) query = query.eq("slug", body.slug);

  const { data: rows, error } = await query;
  if (error) {
    return new Response(JSON.stringify({ error: error.message }), {
      status: 500,
      headers: { "Content-Type": "application/json" },
    });
  }

  if (dryRun) {
    return new Response(
      JSON.stringify({
        dry_run: true,
        would_process: rows?.length ?? 0,
        slugs: rows?.map((r) => r.slug) ?? [],
      }),
      { status: 200, headers: { "Content-Type": "application/json" } },
    );
  }

  const succeeded: string[] = [];
  const failed: { slug: string; error: string }[] = [];

  for (const p of rows ?? []) {
    try {
      const text = personaText(p as PersonaRow);
      if (text.trim().length < 50) {
        failed.push({ slug: p.slug, error: "persona_md too short" });
        continue;
      }
      const vec = await embed(text);
      if (!vec || vec.length !== EMBEDDING_DIMENSIONS) {
        failed.push({ slug: p.slug, error: `bad embedding dims=${vec?.length}` });
        continue;
      }
      const { error: updErr } = await supabase
        .from("personas")
        .update({ embedding: vec, updated_at: new Date().toISOString() })
        .eq("id", p.id);
      if (updErr) {
        failed.push({ slug: p.slug, error: updErr.message });
      } else {
        succeeded.push(p.slug);
      }
    } catch (e) {
      failed.push({ slug: p.slug, error: (e as Error).message });
    }
  }

  return new Response(
    JSON.stringify({
      model: EMBEDDING_MODEL,
      dimensions: EMBEDDING_DIMENSIONS,
      total: rows?.length ?? 0,
      succeeded: succeeded.length,
      failed: failed.length,
      failed_details: failed,
    }),
    { status: 200, headers: { "Content-Type": "application/json" } },
  );
});
