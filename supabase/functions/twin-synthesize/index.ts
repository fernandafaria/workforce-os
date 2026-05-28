// supabase/functions/twin-synthesize/index.ts
//
// Stage 3 of twin creation: read the ingested corpus, call Claude Opus
// 4.7 to synthesize a rich cognitive schema, merge into twin.schema_json.
//
// The synthesized block becomes the system prompt material when this
// twin participates in a Council session.
//
// Auth: requires Supabase service_role JWT.
// Body: { twin_id: uuid, max_chunks?: number }
// Returns:
//   { twin_id, synthesized, model, tokens_in?, tokens_out?, chunks_used }

import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const SUPABASE_URL = Deno.env.get("SUPABASE_URL") || "";
const SUPABASE_SERVICE_ROLE_KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") || "";
const ANTHROPIC_API_KEY = Deno.env.get("ANTHROPIC_API_KEY") || "";

const MODEL = "claude-opus-4-7";
const MAX_TOKENS = 4000;
const ANTHROPIC_VERSION = "2023-06-01";
const MAX_CHUNKS_DEFAULT = 25;
const MAX_CORPUS_CHARS = 90000; // ~22.5k tokens, leaves room for instructions
const MAX_CHUNK_CHARS_PER_BLOCK = 3500;

interface SynthRequest {
  twin_id: string;
  max_chunks?: number;
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
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

function buildPrompt(
  namePublic: string,
  archetype: string,
  notes: string,
  corpus: string,
): { system: string; user: string } {
  const system = `Você é um sintetizador de identidade cognitiva. Sua tarefa é, dado um corpus de fala/escrita em primeira pessoa de uma pessoa real, extrair um modelo cognitivo destilado que outro modelo de linguagem possa usar como prompt-de-sistema para responder *como* essa pessoa em conversas de conselho executivo.

Retorne **apenas JSON válido** (sem markdown, sem comentários), com esta estrutura exata:

{
  "identity": "1 parágrafo (3-5 frases) em terceira pessoa: quem é, o que faz, o que defende e por quê",
  "voice": {
    "tone": "ex: didático-direto, contrarian-respeitoso, pragmático-impaciente",
    "register": "ex: formal-técnico, informal-coloquial, mix culto+gírias",
    "language": "português | inglês | bilíngue",
    "language_quirks": ["expressão recorrente 1", "..."]
  },
  "decision_patterns": ["padrão 1 em forma de regra heurística", "..."],
  "biases": ["viés/crença forte 1", "..."],
  "signature_phrases": ["frase literal recorrente 1", "..."],
  "do": ["o que essa pessoa SIM faz/diz em conselho", "..."],
  "dont": ["o que essa pessoa NÃO faz/diz", "..."],
  "topics_mastery": [
    {"topic": "área 1", "depth": "core|adjacent|opinionated_outsider"},
    {"topic": "..."}
  ],
  "archetype_match_confidence": 0.0
}

Regras:
- Use apenas o que aparece no corpus. Não invente. Se algo não está no corpus, omita.
- "signature_phrases" devem ser frases curtas literais ou quase-literais — não paráfrases.
- "archetype_match_confidence" é float [0,1]: quanto o que você extraiu confirma o archetype declarado.
- Tudo conciso. Cada lista ≤ 8 itens.`;

  const user = `PESSOA: ${namePublic}
ARCHETYPE DECLARADO: ${archetype}
NOTAS DE CONTEXTO: ${notes}

CORPUS (extratos em primeira pessoa quando possível):
---
${corpus}
---

Produza o JSON conforme especificado.`;

  return { system, user };
}

interface AnthropicTextBlock {
  type: string;
  text?: string;
}

interface AnthropicResponse {
  content?: AnthropicTextBlock[];
  usage?: { input_tokens?: number; output_tokens?: number };
  error?: { message?: string };
}

async function callClaude(
  system: string,
  user: string,
): Promise<{ json: unknown; tokens_in?: number; tokens_out?: number } | { error: string }> {
  const resp = await fetch("https://api.anthropic.com/v1/messages", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "x-api-key": ANTHROPIC_API_KEY,
      "anthropic-version": ANTHROPIC_VERSION,
    },
    body: JSON.stringify({
      model: MODEL,
      max_tokens: MAX_TOKENS,
      system,
      messages: [{ role: "user", content: user }],
    }),
  });
  if (!resp.ok) {
    return { error: `Anthropic ${resp.status}: ${await resp.text()}` };
  }
  const data: AnthropicResponse = await resp.json();
  if (data.error) return { error: data.error.message ?? "anthropic error" };
  const textBlock = (data.content ?? []).find((b) => b.type === "text");
  const text = (textBlock?.text ?? "").trim();
  // Extract first balanced JSON object
  const start = text.indexOf("{");
  const end = text.lastIndexOf("}");
  if (start < 0 || end < 0 || end < start) {
    return { error: "no JSON in response", json: text } as unknown as { error: string };
  }
  let parsed: unknown;
  try {
    parsed = JSON.parse(text.slice(start, end + 1));
  } catch (e) {
    return { error: `JSON parse: ${(e as Error).message}` };
  }
  return {
    json: parsed,
    tokens_in: data.usage?.input_tokens,
    tokens_out: data.usage?.output_tokens,
  };
}

Deno.serve(async (req) => {
  if (req.method !== "POST") return new Response("Method not allowed", { status: 405 });
  const denied = requireServiceRole(req);
  if (denied) return denied;
  if (!ANTHROPIC_API_KEY) return jsonResponse({ error: "ANTHROPIC_API_KEY not set" }, 503);

  const body: SynthRequest = await req.json().catch(() => ({ twin_id: "" }));
  if (!body.twin_id) return jsonResponse({ error: "twin_id required" }, 400);

  const supabase = createClient(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY);

  const { data: twin, error: twinErr } = await supabase
    .from("twin")
    .select("id, person_id, archetype_label, schema_json")
    .eq("id", body.twin_id)
    .single();
  if (twinErr || !twin) {
    return jsonResponse({ error: `twin not found: ${twinErr?.message}` }, 404);
  }

  const personId: string | null = twin.person_id;
  if (!personId) return jsonResponse({ error: "twin has no person_id" }, 400);

  const { data: personRow } = await supabase
    .from("twin_person")
    .select("name_public, archetype_label, notes, authorization")
    .eq("id", personId)
    .single();
  const namePublic: string = personRow?.name_public ?? "Unknown";
  const archetype: string = twin.archetype_label ?? personRow?.archetype_label ?? "";
  const notes: string = personRow?.notes ?? twin.schema_json?.notes ?? "";

  if ((personRow?.authorization ?? "") !== "public_figure") {
    return jsonResponse(
      { error: `MVP only synthesizes public_figure twins (got '${personRow?.authorization}')` },
      403,
    );
  }

  const maxChunks = body.max_chunks ?? MAX_CHUNKS_DEFAULT;
  const { data: chunks } = await supabase
    .from("twin_corpus_chunk")
    .select("text, source_url, source_type, source_date, first_person, quality_score")
    .eq("person_id", personId)
    .eq("holdout", false)
    .order("first_person", { ascending: false })
    .order("quality_score", { ascending: false })
    .limit(maxChunks);

  if (!chunks || chunks.length === 0) {
    return jsonResponse({ error: "no embedded corpus chunks; run twin-corpus-ingest first" }, 400);
  }

  // Assemble corpus with source headers, respecting char budget
  let assembled = "";
  let used = 0;
  for (const c of chunks) {
    const header = `\n\n[${c.source_type ?? "src"} | ${c.source_date ?? "?"} | first_person=${c.first_person ?? "?"}]\n`;
    const piece = (c.text as string).slice(0, MAX_CHUNK_CHARS_PER_BLOCK);
    if (assembled.length + header.length + piece.length > MAX_CORPUS_CHARS) break;
    assembled += header + piece;
    used++;
  }

  const { system, user } = buildPrompt(namePublic, archetype, notes, assembled);
  const result = await callClaude(system, user);
  if ("error" in result) {
    return jsonResponse({ error: result.error }, 502);
  }

  const synthesized = result.json as Record<string, unknown>;
  const nowIso = new Date().toISOString();
  const mergedSchema = {
    ...(twin.schema_json ?? {}),
    synthesized,
    synthesized_model: MODEL,
    synthesized_at: nowIso,
    synthesized_chunks_used: used,
  };

  const { error: updErr } = await supabase
    .from("twin")
    .update({
      schema_json: mergedSchema,
      updated_at: nowIso,
    })
    .eq("id", body.twin_id);
  if (updErr) {
    return jsonResponse({ error: `update failed: ${updErr.message}` }, 500);
  }

  return jsonResponse({
    twin_id: body.twin_id,
    synthesized: true,
    model: MODEL,
    tokens_in: result.tokens_in,
    tokens_out: result.tokens_out,
    chunks_used: used,
    new_status: "draft",
  });
});
