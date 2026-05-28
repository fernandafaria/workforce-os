"""
executive_ai_fluency_interview_guide — Mom-Test discovery script (Blocos 0–4, ~30 min).

Used by interview_archetype (--guide mom-test) and batch scripts.
Canonical copy: company/SyntheticPerson/syntheticperson-ai/guides/exec-ai-fluency-mom-test-interview.md
"""

from __future__ import annotations

from pathlib import Path

GUIDE_DOC = Path(
    "company/SyntheticPerson/syntheticperson-ai/guides/exec-ai-fluency-mom-test-interview.md"
)

MOM_TEST_RESEARCH_GOAL = (
    "Entrevista de descoberta Mom-Test (~30 min): calibrar comportamento passado com IA "
    "no trabalho (não opinião), reação ao atrito, gasto realizado, mapa de comprador, "
    "dor de prever reações de grupos (ICP Research), e recrutamento composto. "
    "Não validar produto até o Bloco 4 opcional."
)

# Bloco 0 — primeira pergunta (não pular aquecimento)
MOM_TEST_OPENER = (
    "Me conta o que você faz no dia a dia — não o cargo, o que ocupa suas horas."
)

# Scripted mock path: one question per turn, past-behavior probes in order.
MOM_TEST_MOCK_QUESTIONS: tuple[str, ...] = (
    # Bloco 0 — Aquecimento (~3 min)
    MOM_TEST_OPENER,
    "Como foi sua semana? O que tomou mais tempo do que devia?",
    # Bloco 1 — Comportamento real com IA (~12–15 min)
    "Quando foi a última vez que você abriu uma ferramenta de IA pra fazer algo do trabalho? "
    "Me conta essa vez específica.",
    "O que você estava tentando resolver? Por que naquele momento?",
    "E aí, o que você fez exatamente? Me passo a passo.",
    "O que funcionou? Em que momento você pensou 'opa, isso aqui presta'?",
    "E onde travou? Conta a parte que deu errado ou frustrou.",
    "O que você fez depois que travou?",
    "Hoje, numa semana normal, quantas vezes você abre uma dessas? Pra quê?",
    "Tem algo que você sabe que daria pra fazer com IA mas você não faz? Por quê?",
    "Quando você ouve 'usar IA de um jeito profissional, avançado' — o que isso significa pra você? "
    "Como seria diferente do que você faz hoje?",
    "Você conhece alguém que usa de um jeito que te faz pensar 'queria saber fazer assim'? "
    "O que essa pessoa faz?",
    # Bloco 2 — Custo, álibi, quem decide (~8 min)
    "O que te impede de usar mais? Seja honesto — é tempo, é não saber como, é a empresa, "
    "é não ver valor?",
    "Você já gastou dinheiro do próprio bolso ou aprovou gasto com isso? Quanto, com o quê?",
    "Quem mais decide se a sua empresa usa ou não essas ferramentas?",
    # Bloco 3 — ICP / prever reações (~6–7 min)
    "Com que frequência você ou seu time precisam decidir algo que depende de adivinhar como um "
    "grupo de pessoas vai reagir — clientes, um segmento de mercado, até funcionários — "
    "antes de gastar dinheiro ou expor a marca?",
    "Me conta a última vez que isso aconteceu. O que estava em jogo?",
    "Como vocês decidem isso hoje? Pesquisa contratada, dado interno, intuição, alguém do time?",
    "A última vez que essa decisão deu errado por terem lido o público errado — o que aconteceu?",
    "Quando vocês fazem esse tipo de estudo, quem põe a mão na massa? Você, alguém do seu time, "
    "um fornecedor de fora?",
    "Se existisse uma forma de testar essas reações em dias em vez de semanas, quem na sua "
    "estrutura usaria isso no dia a dia?",
    "Quem é a pessoa no seu mundo que mais vive na dor de 'adivinhar como as pessoas vão reagir'?",
    # Bloco 4 — Fechamento (~2 min)
    "Tem alguma coisa que eu deveria ter te perguntado e não perguntei?",
    "Quem mais eu deveria conversar sobre isso?",
)

MOM_TEST_DEFAULT_TURNS = len(MOM_TEST_MOCK_QUESTIONS)

MOM_TEST_INTERVIEWER_GUIDE_INLINE = """
ROTEIRO OBRIGATÓRIO (Mom-Test, ~30 min) — siga na ordem; NÃO pule o Bloco 0.

Bloco 0 — Aquecimento (~3 min). Calibre comportamento, não opinião:
- "Me conta o que você faz no dia a dia — não o cargo, o que ocupa suas horas."
- "Como foi sua semana? O que tomou mais tempo do que devia?"
Escute onde está a dor de tempo real; volte a isso depois.

Bloco 1 — Comportamento real com IA (~12–15 min). Tudo passado concreto; se hipótese, puxe de volta.
Abertura após aquecimento:
- "Quando foi a última vez que você abriu uma ferramenta de IA pra fazer algo do trabalho? Me conta essa vez específica."
- "O que você estava tentando resolver? Por que naquele momento?"
História (siga o que ela contar):
- "E aí, o que você fez exatamente? Me passo a passo."
- "O que funcionou? Em que momento você pensou 'opa, isso aqui presta'?"
- "E onde travou? Conta a parte que deu errado ou frustrou."
- "O que você fez depois que travou?" ← PERGUNTA MAIS IMPORTANTE (reação ao atrito).
Frequência:
- "Hoje, numa semana normal, quantas vezes você abre uma dessas? Pra quê?"
- "Tem algo que você sabe que daria pra fazer com IA mas você não faz? Por quê?"
"Pro" (não defina — deixe ELA definir):
- "Quando você ouve 'usar IA de um jeito profissional, avançado' — o que isso significa pra você?"
- "Você conhece alguém que usa de um jeito que te faz pensar 'queria saber fazer assim'? O que essa pessoa faz?"

Bloco 2 — Custo, álibi, quem decide (~8 min):
- "O que te impede de usar mais? Seja honesto — tempo, não saber, empresa, valor?"
- Se citar bloqueio institucional: "E o que você fez sobre isso?"
- "Você já gastou dinheiro do próprio bolso ou aprovou gasto com isso? Quanto, com o quê?" (não "pagaria?")
- "Quem mais decide se a sua empresa usa ou não essas ferramentas?"

Bloco 3 — ICP / prever reações (~6–7 min). Sem pitch.
- Frequência de decidir sem saber reação de grupo; última vez e o que estava em jogo.
- Como decidem hoje; se pesquisa instituto: tempo e custo da última vez.
- Última vez que leram o público errado — o que aconteceu.
- Quem põe a mão na massa no estudo; quem usaria teste rápido no organograma.
- "Quem é a pessoa no seu mundo que mais vive na dor de 'adivinhar como as pessoas vão reagir'?"

Bloco 4 — Fechamento (~2 min):
- "Tem alguma coisa que eu deveria ter te perguntado e não perguntei?"
- "Quem mais eu deveria conversar sobre isso?"
- Só se fizer sentido: demo rápida do que está construindo.

Pós-entrevista (anotação interna, não pergunte em voz alta): 2–3 histórias concretas; reação ao atrito;
gasto realizado sim/não; surpresas. Após ~6 entrevistas: agrupar por atrito + gasto, não clusters prévios.
""".strip()


def load_mom_test_guide_markdown() -> str:
    """Full guide from repo doc if present, else inline script."""
    if GUIDE_DOC.is_file():
        return GUIDE_DOC.read_text(encoding="utf-8").strip()
    return MOM_TEST_INTERVIEWER_GUIDE_INLINE


POST_INTERVIEW_DEBRIEF_TEMPLATE = """
## Debrief (5 min) — {person_id} / {session_id}

### Histórias concretas (copiar frases dela, não resumo)
1.
2.
3.

### Reação ao atrito (Bloco 1)
[ ] desistiu / culpou ferramenta  [ ] contornou sozinha  [ ] delegou  [ ] pagou

### Gasto realizado
sim/não — quanto, com o quê:

### Surpresas (contradisse expectativa)
-

### ICP / Research (Bloco 3)
Operador vs comprador:
Próximo contato sugerido:
""".strip()
