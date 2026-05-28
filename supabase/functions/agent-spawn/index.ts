// supabase/functions/agent-spawn/index.ts
//
// Spawn a short-lived dynamic agent for an expertise gap detected during a
// Council session. Claude Opus 4.7 generates a focused SOUL, Voyage-4
// embeds the gap text for later semantic lookup, the row lands in
// public.dynamic_agents with TTL + max_uses, and a lineage row is appended
// to public.agent_spawn_log.
//
// Auth: requires Supabase service_role JWT.
// Body:
//   {
//     question: string,             // the original executive question
//     expertise_gap: string,        // what the panel couldn't cover
//     context?: string,
//     user_id?: uuid,               // owner of the spawned agent
//     parent_team_slug?: string,    // default: "estrategia"
//     parent_persona_slugs?: string[],  // panel members; first becomes parent_persona_id
//     ttl_hours?: number,           // default 24
//     max_uses?: number,            // default 5
//   }

import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const SUPABASE_URL = Deno.env.get("SUPABASE_URL") || "";
const SUPABASE_SERVICE_ROLE_KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") || "";
const ANTHROPIC_API_KEY = Deno.env.get("ANTHROPIC_API_KEY") || "";
const VOYAGE_API_KEY = Deno.env.get("VOYAGE_API_KEY") || "";

const MODEL = "claude-opus-4-7";
const ANTHROPIC_VERSION = "2023-06-01";
const EMBEDDING_MODEL = "voyage-4";
const EMBEDDING_DIMENSIONS = 1024;
const DEFAULT_PARENT_TEAM_SLUG = "estrategia";
const DEFAULT_TTL_HOURS = 24;
const DEFAULT_MAX_USES = 5;

interface SpawnRequest {
  question: string;
  expertise_gap: string;
  context?: string;
  user_id?: string;
  parent_team_slug?: string;
  parent_persona_slugs?: string[];
  ttl_hours?: number;
  max_uses?: number;
}

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

function requireServiceRole(req: Request): Response | null {
  const auth = req.headers.get("Authorization") || "";
  const token = auth.replace(/^Bearer\s+/, "");
  try {
    const payload = JSON.parse(atob(token.split(".")[1] ?? ""));
    if (payload?.role !== "service_role") return json({ error: "service_role required" }, 401);
  } catch { return json({ error: "invalid token" }, 401); }
  return null;
}

async function generateSoul(
  question: string,
  expertiseGap: string,
  context: string,
  parentNames: string[],
): Promise<
  | { name: string; description: string; icon: string; system_prompt: string; topics_mastery: string[]; tokens_in?: number; tokens_out?: number }
  | { error: string }
> {
  const parentBlock = parentNames.length
    ? `Painel atual (sua resposta deve ADICIONAR, não duplicar): ${parentNames.join(", ")}`
    : "Painel atual: nenhum especialista alinhado a essa expertise.";

  const userPrompt = `PERGUNTA EXECUTIVA:\n"""${question}"""\n\nLACUNA DE EXPERTISE IDENTIFICADA:\n${expertiseGap}\n\nCONTEXTO ADICIONAL:\n${context || "(nenhum)"}\n\n${parentBlock}\n\nGere um especialista focado e temporário para fechar esta lacuna específica. Retorne JSON puro:\n\n{\n  "name": "<título profissional curto>",\n  "icon": "<um emoji>",\n  "description": "<por que esse especialista existe — 1-2 frases>",\n  "system_prompt": "<prompt de sistema completo em PT-BR, 800-1500 chars, define IDENTITY / VOICE / DECISION PATTERNS / DO / DONT como uma persona Workforce OS>",\n  "topics_mastery": ["tópico 1", "tópico 2", "tópico 3"]\n}\n\nRegras: sem markdown, sem prefácio, só JSON.`;

  const resp = await fetch("https://api.anthropic.com/v1/messages", {
    method: "POST",
    headers: { "Content-Type": "application/json", "x-api-key": ANTHROPIC_API_KEY, "anthropic-version": ANTHROPIC_VERSION },
    body: JSON.stringify({ model: MODEL, max_tokens: 2500, messages: [{ role: "user", content: userPrompt }] }),
  });
  if (!resp.ok) return { error: `Anthropic ${resp.status}: ${await resp.text()}` };
  const data = await resp.json();
  const text = ((data.content ?? []).find((b: { type: string }) => b.type === "text")?.text ?? "").trim();
  const start = text.indexOf("{");
  const end = text.lastIndexOf("}");
  if (start < 0 || end < 0) return { error: "no JSON in spawn response" };
  let parsed: { name?: string; description?: string; icon?: string; system_prompt?: string; topics_mastery?: unknown };
  try { parsed = JSON.parse(text.slice(start, end + 1)); }
  catch (e) { return { error: `JSON parse: ${(e as Error).message}` }; }
  if (!parsed.name || !parsed.system_prompt) return { error: "spawn response missing name/system_prompt" };
  return {
    name: parsed.name,
    description: parsed.description ?? `Spawned to address expertise gap: ${expertiseGap.slice(0, 120)}`,
    icon: parsed.icon ?? "🔮",
    system_prompt: parsed.system_prompt,
    topics_mastery: Array.isArray(parsed.topics_mastery) ? parsed.topics_mastery.filter((t): t is string => typeof t === "string") : [],
    tokens_in: data.usage?.input_tokens,
    tokens_out: data.usage?.output_tokens,
  };
}

async function embedGap(text: string): Promise<number[] | null> {
  const resp = await fetch("https://api.voyageai.com/v1/embeddings", {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${VOYAGE_API_KEY}` },
    body: JSON.stringify({ model: EMBEDDING_MODEL, input: text.slice(0, 16000), input_type: "query", output_dimension: EMBEDDING_DIMENSIONS }),
  });
  if (!resp.ok) { console.error(`Voyage error ${resp.status}: ${await resp.text()}`); return null; }
  const data = await resp.json();
  return data.data?.[0]?.embedding ?? null;
}

Deno.serve(async (req) => {
  const t0 = Date.now();
  if (req.method !== "POST") return new Response("Method not allowed", { status: 405 });
  const denied = requireServiceRole(req); if (denied) return denied;
  if (!ANTHROPIC_API_KEY) return json({ error: "ANTHROPIC_API_KEY not set" }, 503);
  if (!VOYAGE_API_KEY) return json({ error: "VOYAGE_API_KEY not set" }, 503);

  const body: SpawnRequest = await req.json().catch(() => ({} as SpawnRequest));
  if (!body.question || !body.expertise_gap) {
    return json({ error: "question and expertise_gap are required" }, 400);
  }

  const supabase = createClient(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY);

  // Resolve parent_agent_id (FK to agent_teams) — required NOT NULL
  const parentTeamSlug = body.parent_team_slug ?? DEFAULT_PARENT_TEAM_SLUG;
  const { data: teamRow, error: teamErr } = await supabase
    .from("agent_teams").select("id, name").eq("slug", parentTeamSlug).single();
  if (teamErr || !teamRow) {
    return json({ error: `parent agent_team slug '${parentTeamSlug}' not found: ${teamErr?.message}` }, 400);
  }

  // Resolve parent_persona_id (optional) from first slug in panel
  let parentPersonaId: string | null = null;
  let parentPersonaNames: string[] = [];
  if (body.parent_persona_slugs && body.parent_persona_slugs.length > 0) {
    const { data: personas } = await supabase
      .from("personas").select("id, slug, name")
      .in("slug", body.parent_persona_slugs).limit(8);
    parentPersonaNames = (personas ?? []).map((p) => p.name as string);
    parentPersonaId = (personas?.[0]?.id ?? null) as string | null;
  }

  // Generate SOUL
  const soul = await generateSoul(body.question, body.expertise_gap, body.context ?? "", parentPersonaNames);
  if ("error" in soul) return json({ error: soul.error }, 502);

  // Embed expertise_gap
  const embedding = await embedGap(body.expertise_gap);

  // Insert dynamic_agent
  const ttlHours = body.ttl_hours ?? DEFAULT_TTL_HOURS;
  const maxUses = body.max_uses ?? DEFAULT_MAX_USES;
  const expiresAt = new Date(Date.now() + ttlHours * 3600 * 1000).toISOString();

  const insertPayload: Record<string, unknown> = {
    user_id: body.user_id ?? null,
    name: soul.name,
    description: soul.description,
    system_prompt: soul.system_prompt,
    icon: soul.icon,
    parent_agent_id: teamRow.id,
    parent_persona_id: parentPersonaId,
    spawn_reason: body.expertise_gap.slice(0, 1000),
    model: MODEL,
    temperature: 0.7,
    max_tokens: 1500,
    status: "active",
    max_uses: maxUses,
    expires_at: expiresAt,
    spawn_context_size_tokens: soul.tokens_in ?? 0,
  };
  if (embedding) insertPayload.expertise_gap_embedding = embedding;

  const { data: agentRow, error: insErr } = await supabase
    .from("dynamic_agents").insert(insertPayload).select("*").single();
  if (insErr || !agentRow) {
    return json({ error: `dynamic_agents insert failed: ${insErr?.message}` }, 500);
  }

  // Append lineage row
  const latencyMs = Date.now() - t0;
  const { error: logErr } = await supabase.from("agent_spawn_log").insert({
    dynamic_agent_id: agentRow.id,
    parent_agent_id: teamRow.id,
    trigger_query: body.question.slice(0, 2000),
    expertise_gap: body.expertise_gap.slice(0, 2000),
    spawn_latency_ms: latencyMs,
  });
  if (logErr) {
    // Non-fatal — the spawn row exists. Surface in response.
    console.error(`agent_spawn_log insert failed: ${logErr.message}`);
  }

  return json({
    dynamic_agent_id: agentRow.id,
    name: agentRow.name,
    description: agentRow.description,
    icon: agentRow.icon,
    system_prompt: agentRow.system_prompt,
    model: agentRow.model,
    parent_team_slug: parentTeamSlug,
    parent_persona_id: parentPersonaId,
    status: agentRow.status,
    max_uses: agentRow.max_uses,
    expires_at: agentRow.expires_at,
    spawn_latency_ms: latencyMs,
    tokens_in: soul.tokens_in,
    tokens_out: soul.tokens_out,
    log_error: logErr?.message ?? null,
    topics_mastery: soul.topics_mastery,
  });
});
