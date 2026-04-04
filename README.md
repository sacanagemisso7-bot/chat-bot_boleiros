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
├── .env.example
├── requirements.txt
└── README.md
```

## Banco de dados

Tabelas principais:
- `clientes`
- `agendamentos`
- `mensagens`
- `eventos_webhook`
- `disponibilidade`
- `conversa_estado`

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

Endpoints úteis locais:
- `GET /debug/clientes`
- `GET /debug/slots`
- `GET /debug/mensagens?telefone=5511999991111`

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

Se `OPENAI_ENABLED=false`, o bot funciona 100% via regras e estados.

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

## Teste local com túnel (ngrok)

```bash
ngrok http 8000
```

Use a URL HTTPS gerada no webhook da Meta.

## Fluxos implementados

### 1) Onboarding
- Telefone novo: cria cliente com `onboarding_status=aguardando_nome`.
- Bot pede nome.
- Ao receber nome válido: salva nome, ativa cadastro e oferece opções.

### 2) Agendamento real
- Intenção de agendar/remarcar: busca slots da tabela `disponibilidade`.
- Cliente responde com número da opção.
- Bot confirma, cria `agendamentos` e marca slot como indisponível.
- Cancelamento: muda status do agendamento e libera slot.

### 3) Handoff humano
- Detecta termos como `humano`, `atendente`, `pessoa`.
- Marca `atendimento_humano=true` em `conversa_estado`.
- Enquanto ativo, bot para automações e mantém somente resposta de encaminhamento.

### 4) Histórico e idempotência
- Mensagens inbound/outbound salvas em `mensagens`.
- `meta_message_id` armazenado quando disponível.
- Payload bruto salvo em `eventos_webhook`.
- Eventos/mensagens duplicadas são ignorados por chave única.

## Como testar rapidamente

### Onboarding
1. Envie mensagem de número não cadastrado (ex.: "oi").
2. Bot pede nome.
3. Envie "Gustavo".
4. Verifique `GET /debug/clientes` e `GET /debug/mensagens`.

### Agendamento
1. Envie "quero agendar".
2. Escolha opção numérica retornada.
3. Verifique `agendamentos` e `disponibilidade` via SQLite ou endpoints debug.

### Sem IA
- `OPENAI_ENABLED=false`
- Mensagens de fallback seguem regras internas.

### Com IA
- `OPENAI_ENABLED=true` + `OPENAI_API_KEY` válido.
- IA só atua em fallback e deve respeitar contexto real.

## Limitações atuais (MVP)
- Apenas mensagens de texto.
- Sem painel web para atendente humano.
- Sem autenticação dos endpoints `/debug/*` (uso local).
- Sem filas/retry assíncrono para envio Meta.

## Próximos passos (produção)
- Autenticar/ocultar endpoints internos.
- Adicionar fila (Celery/RQ) para resiliência de envio.
- Observabilidade (logs estruturados + tracing).
- Políticas de reprocessamento e dead-letter para webhook.
- Painel para operação humana e auditoria.
