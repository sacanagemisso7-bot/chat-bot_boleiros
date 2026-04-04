# Chatbot WhatsApp para Barbearia (MVP)

MVP funcional em **Python + FastAPI + SQLite** integrado com **Meta WhatsApp Cloud API**, com:
- onboarding real de novos clientes,
- histórico persistente de mensagens,
- fluxo de agendamento/remarcação/cancelamento com disponibilidade real,
- handoff para humano,
- deduplicação/idempotência de eventos do webhook,
- integração opcional com OpenAI (fallback para regras quando desabilitado).

## Estrutura de pastas

```text
.
├── app.py
├── db.py
├── seed_clientes.py
├── services/
│   ├── ai.py
│   ├── chatbot.py
│   ├── meta.py
│   ├── onboarding.py
│   └── scheduler.py
├── tests/
│   ├── conftest.py
│   └── test_chatbot_flows.py
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

### Meta (obrigatórias para envio real)
- `META_VERIFY_TOKEN`
- `META_WHATSAPP_TOKEN`
- `META_PHONE_NUMBER_ID`
- `META_GRAPH_VERSION` (ex.: `v22.0`)

### Segurança (produção)
- `META_VALIDATE_SIGNATURE=true|false`
- `META_APP_SECRET` (necessário se validação estiver ligada)

### Banco
- `DB_PATH` (default `barbearia.db`)

### IA opcional
- `OPENAI_ENABLED=true|false`
- `OPENAI_API_KEY`
- `OPENAI_MODEL` (default `gpt-5.4-mini`)

### Endpoints de debug
- `DEBUG_ENDPOINTS_ENABLED=true|false`
- Se `true`: habilita `/debug/clientes`, `/debug/slots`, `/debug/mensagens`
- Se `false`: endpoints retornam `404` (recomendado em produção)

## Configuração da Meta (passo a passo)

1. Crie app em Meta for Developers.
2. Adicione produto **WhatsApp**.
3. Gere token e copie `META_WHATSAPP_TOKEN`.
4. Copie `Phone Number ID` para `META_PHONE_NUMBER_ID`.
5. Configure webhook apontando para `https://SEU_DOMINIO/webhook`.
6. Use em webhook verify token o mesmo valor de `META_VERIFY_TOKEN`.
7. Assine o campo **`messages`**.
8. (Produção) habilite assinatura:
   - `META_VALIDATE_SIGNATURE=true`
   - `META_APP_SECRET=<app secret>`

## Fluxo de escolha de slots (corrigido)

O bot agora salva no estado conversacional os **IDs exatos e ordenados** dos slots exibidos (`slots_ids`).
Quando o cliente responde `1`, `2`, `3`..., o sistema mapeia para esse ID salvo (sem recalcular posição em lista nova).

Se o slot escolhido tiver ficado indisponível entre a listagem e a confirmação, o bot:
1. informa que o horário foi ocupado,
2. atualiza o estado com uma nova lista real,
3. reapresenta as novas opções.

## Testes automatizados

Rodar testes:

```bash
pytest -q
```

Cobertura mínima implementada:
- onboarding de cliente novo,
- agendamento com validação por `slots_ids` salvos,
- cancelamento,
- deduplicação de webhook por ID da Meta,
- proteção de endpoints debug quando desabilitados.

Os testes usam banco isolado temporário e mock das chamadas externas da Meta.

## Teste local com túnel (ngrok)

```bash
ngrok http 8000
```

Use a URL HTTPS gerada no webhook da Meta.

## Limitações atuais (MVP)
- Apenas mensagens de texto.
- Sem painel web para atendente humano.
- Sem filas/retry assíncrono para envio Meta.

## Próximos passos (produção)
- Autenticar/ocultar endpoints internos.
- Adicionar fila (Celery/RQ) para resiliência de envio.
- Observabilidade (logs estruturados + tracing).
- Painel para operação humana e auditoria.
