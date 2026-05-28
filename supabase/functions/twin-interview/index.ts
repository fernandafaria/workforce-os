// supabase/functions/twin-interview/index.ts
//
// Stage 4 of twin creation: generate an interview session of N turns.
//
// 1. Read twin.schema_json.synthesized to get topics_mastery and identity.
// 2. Generate N probe questions covering core/adjacent topics.
// 3. For each question, twin answers (Claude Opus + synthesized schema
//    as system prompt). No RAG over corpus in this pass — schema alone
//    is the contract being tested. Corpus-augmented answering belongs
//    in the Council runtime, not in eval.
// 4. Persist as twin_interview_turn (user + assistant alternating).
//
// Auth: requires service_role JWT.
// Body: { twin_id: uuid, num_questions?: number, session_label?: string }

import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const SUPABASE_URL = Deno.env.get("SUPABASE_URL") || "";
const SUPABASE_SERVICE_ROLE_KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") || "";
const ANTHROPIC_API_KEY = Deno.env.get("ANTHROPIC_API_KEY") || "";

const MODEL = "claude-opus-4-7";
const ANTHROPIC_VERSION = "2023-06-01";
const DEFAULT_NUM_QUESTIONS = 8;
const MAX_ANSWER_TOKENS = 700;

interface InterviewRequest { twin_id: string; num_questions?: number; session_label?: string; }

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

function buildTwinSystemPrompt(synth: Record<string, unknown>, namePublic: string): string {
  return [
    `Você responde *como* ${namePublic}. Voz, padrões de decisão e vieses devem refletir essa pessoa, não uma média. Não invente fatos sobre quem você não é.`,
    `\nIDENTITY:\n${synth.identity ?? ""}`,
    `\nVOICE: ${JSON.stringify(synth.voice ?? {})}`,
    `\nDECISION PATTERNS:\n${JSON.stringify(synth.decision_patterns ?? [])}`,
    `\nBIASES:\n${JSON.stringify(synth.biases ?? [])}`,
    `\nSIGNATURE PHRASES (use naturalmente, sem forçar):\n${JSON.stringify(synth.signature_phrases ?? [])}`,
    `\nDO: ${JSON.stringify(synth.do ?? [])}`,
    `\nDONT: ${JSON.stringify(synth.dont ?? [])}`,
    `\nResponda em 2-4 parágrafos, com substância. Sem lista numerada burocrática.`,
  ].join("\n");
}

async function generateQuestions(synth: Record<string, unknown>, namePublic: string, n: number): Promise<string[]> {
  const topics = synth.topics_mastery ?? [];
  const archetype = synth.archetype_match_confidence != null ? `(archetype confidence ${synth.archetype_match_confidence})` : "";

  const prompt = `Você é um entrevistador executivo. Vou montar uma entrevista de ${n} perguntas para um conselho com ${namePublic} ${archetype}.

Temas de domínio do entrevistado:
${JSON.stringify(topics, null, 2)}

Identity context:
${synth.identity ?? ""}

Gere ${n} perguntas que um executivo (CEO/diretor) faria a essa pessoa. Cubra:
- 50% perguntas de decisão concreta no domínio core dela
- 30% perguntas adjacentes (estratégia, time, escala)
- 20% perguntas de meta (como ela mesma tomaria uma decisão dura agora)

Retorne JSON array de strings. SEM markdown, SEM numeração, SEM comentários. Cada pergunta concisa (≤ 25 palavras).`;

  const resp = await fetch("https://api.anthropic.com/v1/messages", {
    method: "POST",
    headers: { "Content-Type": "application/json", "x-api-key": ANTHROPIC_API_KEY, "anthropic-version": ANTHROPIC_VERSION },
    body: JSON.stringify({ model: MODEL, max_tokens: 1500, messages: [{ role: "user", content: prompt }] }),
  });
  if (!resp.ok) { console.error(`question gen failed ${resp.status}: ${await resp.text()}`); return []; }
  const data = await resp.json();
  const text = ((data.content ?? []).find((b: { type: string }) => b.type === "text")?.text ?? "").trim();
  const start = text.indexOf("[");
  const end = text.lastIndexOf("]");
  if (start < 0 || end < 0) return [];
  try {
    const arr = JSON.parse(text.slice(start, end + 1));
    return Array.isArray(arr) ? arr.filter((q): q is string => typeof q === "string") : [];
  } catch { return []; }
}

async function answerAsTwin(system: string, question: string): Promise<{ text: string; tokens_in?: number; tokens_out?: number } | null> {
  const resp = await fetch("https://api.anthropic.com/v1/messages", {
    method: "POST",
    headers: { "Content-Type": "application/json", "x-api-key": ANTHROPIC_API_KEY, "anthropic-version": ANTHROPIC_VERSION },
    body: JSON.stringify({ model: MODEL, max_tokens: MAX_ANSWER_TOKENS, system, messages: [{ role: "user", content: question }] }),
  });
  if (!resp.ok) { console.error(`twin answer failed ${resp.status}: ${await resp.text()}`); return null; }
  const data = await resp.json();
  const block = (data.content ?? []).find((b: { type: string }) => b.type === "text");
  const text = (block?.text ?? "").trim();
  if (!text) return null;
  return { text, tokens_in: data.usage?.input_tokens, tokens_out: data.usage?.output_tokens };
}

Deno.serve(async (req) => {
  if (req.method !== "POST") return new Response("Method not allowed", { status: 405 });
  const denied = requireServiceRole(req); if (denied) return denied;
  if (!ANTHROPIC_API_KEY) return json({ error: "ANTHROPIC_API_KEY not set" }, 503);

  const body: InterviewRequest = await req.json().catch(() => ({ twin_id: "" }));
  if (!body.twin_id) return json({ error: "twin_id required" }, 400);

  const supabase = createClient(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY);

  const { data: twin, error: twinErr } = await supabase.from("twin").select("id, person_id, schema_json").eq("id", body.twin_id).single();
  if (twinErr || !twin) return json({ error: `twin not found: ${twinErr?.message}` }, 404);
  const personId = twin.person_id as string | null;
  if (!personId) return json({ error: "twin has no person_id" }, 400);

  const synth = (twin.schema_json?.synthesized ?? null) as Record<string, unknown> | null;
  if (!synth) return json({ error: "twin not synthesized; run twin-synthesize first" }, 400);

  const { data: personRow } = await supabase.from("twin_person").select("name_public").eq("id", personId).single();
  const namePublic = personRow?.name_public ?? "Unknown";

  const num = body.num_questions ?? DEFAULT_NUM_QUESTIONS;
  const questions = await generateQuestions(synth, namePublic, num);
  if (questions.length === 0) return json({ error: "failed to generate questions" }, 500);

  const sessionId = crypto.randomUUID();
  const sessionLabel = body.session_label ?? `auto-${new Date().toISOString().slice(0, 10)}`;
  const system = buildTwinSystemPrompt(synth, namePublic);

  let turnIndex = 0;
  let totalIn = 0, totalOut = 0;
  const rows: Array<Record<string, unknown>> = [];

  for (const q of questions) {
    const userRow = {
      session_id: sessionId, twin_id: body.twin_id, turn_index: turnIndex++,
      speaker: "interviewer", content: q, tool_calls: { session_label: sessionLabel },
      tokens_in: null, tokens_out: null,
    };
    rows.push(userRow);

    const answer = await answerAsTwin(system, q);
    if (!answer) {
      rows.push({
        session_id: sessionId, twin_id: body.twin_id, turn_index: turnIndex++,
        speaker: "twin", content: "[answer failed]", tool_calls: null, tokens_in: null, tokens_out: null,
      });
      continue;
    }
    totalIn += answer.tokens_in ?? 0;
    totalOut += answer.tokens_out ?? 0;
    rows.push({
      session_id: sessionId, twin_id: body.twin_id, turn_index: turnIndex++,
      speaker: "twin", content: answer.text,
      tool_calls: null, tokens_in: answer.tokens_in ?? null, tokens_out: answer.tokens_out ?? null,
    });
  }

  const { error: insErr } = await supabase.from("twin_interview_turn").insert(rows);
  if (insErr) return json({ error: `insert failed: ${insErr.message}` }, 500);

  return json({
    twin_id: body.twin_id, session_id: sessionId, session_label: sessionLabel,
    num_questions: questions.length, num_turns: rows.length,
    tokens_in: totalIn, tokens_out: totalOut, model: MODEL,
  });
});
