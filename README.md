# Chatbot WhatsApp para Barbearia (MVP)

MVP em **Python + FastAPI + SQLite** com **Meta WhatsApp Cloud API** e camada de IA opcional via **Gemini**.

## Estrutura

```text
.
├── app.py
├── db.py
├── services/
│   ├── ai.py
│   ├── ai_context.py
│   ├── ai_prompt.py
│   ├── chatbot.py
│   ├── meta.py
│   ├── onboarding.py
│   └── scheduler.py
├── tests/
│   ├── conftest.py
│   ├── test_chatbot_flows.py
│   └── test_ai_layer.py
├── .env.example
├── requirements.txt
└── README.md
```

## Rodando localmente

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python seed_clientes.py --reset
uvicorn app:app --reload --port 8000
```

## Configuração da Gemini

1. Gere chave em **Google AI Studio** (Gemini API key).
2. Configure no `.env`:
   - `GEMINI_ENABLED=true`
   - `GEMINI_API_KEY=<sua_chave>`
   - `GEMINI_MODEL=gemini-2.5-flash` (ou outro)
   - `GEMINI_TIMEOUT_SECONDS=20`
   - `GEMINI_MAX_CONTEXT_MESSAGES=8`
   - `GEMINI_TEMPERATURE=0.2`

Se `GEMINI_ENABLED=false` (ou sem chave), o bot segue em fallback determinístico por regras.

## Como a IA funciona sem quebrar fluxos críticos

- Onboarding, agendamento, escolha de slot, confirmação, cancelamento e handoff humano continuam determinísticos.
- A Gemini é usada apenas em dúvidas abertas/complementares.
- Se a Gemini falhar (timeout/erro), o bot cai no fallback sem quebrar webhook.

## Contexto real enviado para Gemini

A função `build_ai_context(...)` envia contexto estruturado com dados reais:
- perfil do cliente,
- estado da conversa,
- histórico recente,
- próximo/últimos agendamentos,
- slots reais disponíveis,
- promoções reais (ou vazio quando não houver).

## Guardrails anti-invenção

- Prompt reforça que a IA não pode inventar dados.
- Respostas são rejeitadas quando não há lastro no contexto (ex.: sugerir horário sem slots ou promoção sem promo ativa).
- Em rejeição, o sistema usa fallback por regras.

## Testes

Rodar tudo:

```bash
pytest -q
```

Rodar apenas IA:

```bash
pytest -q tests/test_ai_layer.py
```

Casos cobertos na IA:
- Gemini desligada,
- falha/timeout,
- contexto real,
- bloqueio de resposta inventada,
- dúvida genérica,
- sem chave Gemini.

## Limitações atuais

- Promoções ainda não têm tabela dedicada no banco (contexto pode vir vazio).
- Validação anti-alucinação é heurística conservadora.
