# Chatbot WhatsApp para Barbearia (MVP)

MVP funcional em **Python + FastAPI + SQLite** integrado com **Meta WhatsApp Cloud API**, com:
- onboarding real de novos clientes,
- histórico persistente de mensagens,
- fluxo de agendamento/remarcação/cancelamento com disponibilidade real,
- handoff para humano,
- deduplicação/idempotência de eventos do webhook,
- integração opcional com OpenAI com fallback robusto para regras.

## Estrutura de pastas

```text
.
├── app.py
├── db.py
├── seed_clientes.py
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

## Instalação e execução local

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python seed_clientes.py --reset
uvicorn app:app --reload --port 8000
```

Healthcheck:
- `GET /health`

## Variáveis de ambiente

### IA opcional (OpenAI)
- `OPENAI_ENABLED=true|false`
- `OPENAI_API_KEY`
- `OPENAI_MODEL` (default `gpt-5.4-mini`)
- `OPENAI_TIMEOUT_SECONDS` (default `20`)
- `OPENAI_MAX_CONTEXT_MESSAGES` (default `8`)
- `OPENAI_TEMPERATURE` (default `0.2`)

Se IA estiver desligada (ou falhar), o bot segue funcionando por regras/fluxos determinísticos.

### Endpoints de debug
- `DEBUG_ENDPOINTS_ENABLED=true|false`
- Se `false`: endpoints `/debug/*` retornam `404`.

## Como a IA usa contexto real

A camada de IA foi separada em:
- `services/ai_context.py`: monta contexto estruturado com dados reais do banco.
- `services/ai_prompt.py`: prompt fixo + payload estruturado com regras e limites.
- `services/ai.py`: integração OpenAI, timeout, logs e fallback seguro.

Contexto enviado inclui:
- perfil real do cliente (`nome`, `telefone`, `onboarding_status`, `barbeiro_favorito`, `preferencia`, `observacoes`),
- estado atual da conversa (`conversa_estado`, handoff humano),
- próximo agendamento e últimos agendamentos,
- últimas mensagens relevantes,
- próximos slots reais disponíveis,
- promoções ativas reais (atualmente lista vazia se não houver cadastro).

## Regras de segurança da IA

- IA é usada **apenas após** os fluxos determinísticos (onboarding/agendamento/cancelamento/handoff).
- IA não marca horário sozinha.
- Respostas da IA passam por validação de lastro:
  - sem slots no contexto, respostas com horário inventado são rejeitadas;
  - sem promoção ativa, respostas promocionais inventadas são rejeitadas.
- Quando IA falha (timeout/erro HTTP/parsing), fallback para resposta por regras.

## Testes automatizados

Rodar toda suíte:

```bash
pytest -q
```

Rodar apenas testes da IA:

```bash
pytest -q tests/test_ai_layer.py
```

Cobertura de IA:
- IA desligada,
- falha/timeout OpenAI,
- montagem de contexto real,
- bloqueio de resposta potencialmente inventada,
- resposta útil em dúvida genérica.

## Limitações atuais da IA
- Não há tabela de promoções no banco (contexto envia lista vazia quando não existir promoção cadastrada).
- Validação anti-alucinação é heurística (conservadora), não prova formal.
- IA é complementar, não substitui fluxos críticos do sistema.
