# Twins Pipeline

Pipeline de construção de digital twins (gêmeos digitais) para board members e advisors sintéticos.

## Estrutura

```
twins/
├── persons/          # YAML specs dos twins (fonte da verdade)
│   ├── renato-meirelles.yaml
│   ├── luiza-helena-trajano.yaml
│   ├── jorge-paulo-lemann.yaml
│   └── vicente-falconi.yaml
├── corpus/           # Corpus de texto (transcrições, artigos, livros)
│   ├── renato-meirelles/
│   ├── trajano/
│   ├── lemann/
│   └── falconi/
└── README.md

rag/twins/            # Pipeline Python (migrado do syntheticalpha)
├── ingest_person.py  # CLI principal — fetch → chunk → embed → store
├── storage.py        # SQLite storage (twins.db)
├── transcribe.py     # Whisper transcription
├── build_twin.py     # Monta twin a partir do corpus
├── chat_with_twin.py # Chat com twin construído
├── eval_twin.py      # Avaliação de qualidade
├── interview_archetype.py  # Entrevista de validação
├── joint_discovery.py      # Descoberta colaborativa entre twins
└── sync_to_supabase.py     # Sincroniza com Supabase (FeBrain)
```

## Como usar

### 1. Criar spec YAML

```yaml
# twins/persons/meu-twin.yaml
id: meu-twin
name_public: "Nome Público"
archetype_label: "Descrição curta"
authorization: public_figure
sources:
  - path: twins/corpus/meu-twin/entrevista.txt
    type: podcast
    first_person: true
  - url: https://exemplo.com/artigo
    type: interview
    first_person: true
```

### 2. Ingerir corpus

```bash
cd workforce-os
python -m rag.twins.ingest_person twins/persons/meu-twin.yaml
```

### 3. Construir twin

```bash
python -m rag.twins.build_twin meu-twin
```

### 4. Testar

```bash
python -m rag.twins.chat_with_twin meu-twin
```

## Variáveis de ambiente

- `VOYAGE_API_KEY` — embeddings (Voyage AI)
- `FIRECRAWL_API_KEY` — scraping de URLs (opcional, usar `path:` como alternativa)
- `SUPABASE_URL` / `SUPABASE_SERVICE_ROLE_KEY` — sync com FeBrain
- `ANTHROPIC_API_KEY` ou `DEEPSEEK_API_KEY` — LLM para build/chat

## Tipos de source válidos

`interview`, `podcast`, `linkedin`, `talk`, `release`, `book`, `article`, `crawl`, `video`
