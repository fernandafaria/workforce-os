// supabase/functions/twin-eval/index.ts
//
// Stage 5 of twin creation: evaluate fidelity against held-out corpus.
//
// Harness: "holdout_cosine"
//   For each holdout chunk, take first ~50% as a prefix, ask the twin
//   (Claude Opus + synthesized schema as system prompt) to continue,
//   then compare the twin's continuation vs the actual continuation
//   via Voyage cosine similarity. The mean similarity is the score;
//   passed = score >= THRESHOLD (default 0.55).
//
// Auth: requires service_role JWT.
// Body: { twin_id: uuid, num_probes?: number, threshold?: number }
// Returns: { twin_id, eval_id, harness, score, passed, num_probes, per_probe }

import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const SUPABASE_URL = Deno.env.get("SUPABASE_URL") || "";
const SUPABASE_SERVICE_ROLE_KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") || "";
const ANTHROPIC_API_KEY = Deno.env.get("ANTHROPIC_API_KEY") || "";
const VOYAGE_API_KEY = Deno.env.get("VOYAGE_API_KEY") || "";

const MODEL = "claude-opus-4-7";
const ANTHROPIC_VERSION = "2023-06-01";
const EMBEDDING_MODEL = "voyage-4";
const EMBEDDING_DIMENSIONS = 1024;
const DEFAULT_NUM_PROBES = 8;
const DEFAULT_THRESHOLD = 0.55;
const MAX_ANSWER_TOKENS = 800;
const PREFIX_RATIO = 0.5;

interface EvalRequest { twin_id: string; num_probes?: number; threshold?: number; }
interface ProbeResult { source_url: string | null; similarity: number; prefix_len: number; target_len: number; answer_len: number; }

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
  const identity = synth.identity ?? "";
  const voice = synth.voice ?? {};
  const decisions = synth.decision_patterns ?? [];
  const biases = synth.biases ?? [];
  const phrases = synth.signature_phrases ?? [];
  const dos = synth.do ?? [];
  const donts = synth.dont ?? [];
  return [
    `Você está respondendo *como* ${namePublic}. Não invente fatos que não estão na sua identidade. Responda na voz dessa pessoa.`,
    `\nIDENTITY:\n${identity}`,
    `\nVOICE: ${JSON.stringify(voice)}`,
    `\nDECISION PATTERNS:\n${JSON.stringify(decisions)}`,
    `\nBIASES:\n${JSON.stringify(biases)}`,
    `\nSIGNATURE PHRASES (use naturalmente, sem forçar):\n${JSON.stringify(phrases)}`,
    `\nDO: ${JSON.stringify(dos)}`,
    `\nDONT: ${JSON.stringify(donts)}`,
  ].join("\n");
}

async function callClaudeContinuation(system: string, prefix: string): Promise<string | null> {
  const resp = await fetch("https://api.anthropic.com/v1/messages", {
    method: "POST",
    headers: { "Content-Type": "application/json", "x-api-key": ANTHROPIC_API_KEY, "anthropic-version": ANTHROPIC_VERSION },
    body: JSON.stringify({
      model: MODEL, max_tokens: MAX_ANSWER_TOKENS, system,
      messages: [{ role: "user", content: `Continue this passage as you (${"the person you are"}) would have said it next. Match the register, length (roughly 2-4 sentences), and topical direction. Don't repeat the prefix.\n\nPREFIX:\n${prefix.slice(0, 3000)}\n\nContinuation:` }],
    }),
  });
  if (!resp.ok) { console.error(`Anthropic ${resp.status}: ${await resp.text()}`); return null; }
  const data = await resp.json();
  const block = (data.content ?? []).find((b: { type: string }) => b.type === "text");
  return (block?.text ?? "").trim() || null;
}

async function embedText(text: string): Promise<number[] | null> {
  if (!VOYAGE_API_KEY) return null;
  const resp = await fetch("https://api.voyageai.com/v1/embeddings", {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${VOYAGE_API_KEY}` },
    body: JSON.stringify({ model: EMBEDDING_MODEL, input: text.slice(0, 16000), input_type: "document", output_dimension: EMBEDDING_DIMENSIONS }),
  });
  if (!resp.ok) return null;
  const data = await resp.json();
  return data.data?.[0]?.embedding ?? null;
}

function cosineSim(a: number[], b: number[]): number {
  let dot = 0, na = 0, nb = 0;
  for (let i = 0; i < a.length; i++) { dot += a[i] * b[i]; na += a[i] * a[i]; nb += b[i] * b[i]; }
  if (na === 0 || nb === 0) return 0;
  return dot / (Math.sqrt(na) * Math.sqrt(nb));
}

Deno.serve(async (req) => {
  if (req.method !== "POST") return new Response("Method not allowed", { status: 405 });
  const denied = requireServiceRole(req); if (denied) return denied;
  if (!ANTHROPIC_API_KEY) return json({ error: "ANTHROPIC_API_KEY not set" }, 503);
  if (!VOYAGE_API_KEY) return json({ error: "VOYAGE_API_KEY not set" }, 503);

  const body: EvalRequest = await req.json().catch(() => ({ twin_id: "" }));
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

  const numProbes = body.num_probes ?? DEFAULT_NUM_PROBES;
  const threshold = body.threshold ?? DEFAULT_THRESHOLD;

  const { data: chunks } = await supabase
    .from("twin_corpus_chunk").select("text, source_url, source_type, source_date, first_person")
    .eq("person_id", personId).eq("holdout", true)
    .order("first_person", { ascending: false })
    .limit(numProbes);

  if (!chunks || chunks.length === 0) {
    return json({ error: "no holdout chunks; corpus must have holdout=true chunks. Re-run ingest or wait for more sources." }, 400);
  }

  const system = buildTwinSystemPrompt(synth, namePublic);
  const perProbe: ProbeResult[] = [];

  for (const c of chunks) {
    const fullText = (c.text as string).trim();
    if (fullText.length < 400) continue;
    const cut = Math.floor(fullText.length * PREFIX_RATIO);
    const prefix = fullText.slice(0, cut);
    const target = fullText.slice(cut);

    const answer = await callClaudeContinuation(system, prefix);
    if (!answer) continue;

    const [eAns, eTarget] = await Promise.all([embedText(answer), embedText(target)]);
    if (!eAns || !eTarget) continue;

    perProbe.push({
      source_url: c.source_url ?? null,
      similarity: cosineSim(eAns, eTarget),
      prefix_len: prefix.length,
      target_len: target.length,
      answer_len: answer.length,
    });
  }

  if (perProbe.length === 0) return json({ error: "no probes produced; check holdout chunk quality" }, 500);

  const mean = perProbe.reduce((s, p) => s + p.similarity, 0) / perProbe.length;
  const passed = mean >= threshold;

  const scoresJson = {
    mean_similarity: mean,
    threshold,
    num_probes: perProbe.length,
    per_probe: perProbe,
  };

  const { data: evalRow, error: insErr } = await supabase
    .from("twin_eval_run")
    .insert({
      twin_id: body.twin_id,
      harness: "holdout_cosine",
      scores_json: scoresJson,
      passed,
      notes: `${perProbe.length} probes vs threshold ${threshold}; voyage-4 cosine`,
    })
    .select("id")
    .single();

  if (insErr) return json({ error: `eval_run insert failed: ${insErr.message}` }, 500);

  // Also surface aggregate into twin.eval_scores for quick filter/list
  const evalScores = { harness: "holdout_cosine", mean_similarity: mean, threshold, passed, ran_at: new Date().toISOString() };
  await supabase.from("twin").update({ eval_scores: evalScores, updated_at: new Date().toISOString() }).eq("id", body.twin_id);

  return json({
    twin_id: body.twin_id,
    eval_id: evalRow?.id,
    harness: "holdout_cosine",
    score: mean,
    threshold,
    passed,
    num_probes: perProbe.length,
    per_probe: perProbe,
  });
});
