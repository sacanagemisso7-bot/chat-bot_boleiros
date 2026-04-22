# Chatbot de WhatsApp para Barbearia (Meta Cloud API)

Projeto de chatbot para WhatsApp com respostas personalizadas usando base de clientes em SQLite e integração com **WhatsApp Cloud API (Meta Graph API)**.

## O que esse bot faz
- Recebe mensagens no webhook `POST /webhook` (padrão Meta).
- Faz validação do webhook em `GET /webhook` com `hub.verify_token`.
- Busca cliente por telefone no SQLite.
- Responde de forma personalizada com nome, preferência de corte e barbeiro favorito.
- Sugere manutenção com base na data do último corte.
- Permite solicitar **remarcação** e marca o agendamento como `remarcacao_solicitada`.
- Salva histórico de mensagens (entrada/saída) por cliente.
- Envia mensagem de teste para o número de destino configurado.

## Stack
- JavaScript (Node.js + Express)
- SQLite
- WhatsApp Cloud API (Meta)

## Como rodar
```bash
npm install
cp .env.example .env
npm run seed
npm run dev
```

Servidor padrão: `http://localhost:8000`

## Variáveis de ambiente
- `WHATSAPP_TOKEN`: token de acesso do app Meta.
- `WHATSAPP_PHONE_NUMBER_ID`: ID do número de telefone do WhatsApp Cloud API.
- `WHATSAPP_BUSINESS_ID`: ID da business account.
- `WHATSAPP_VERIFY_TOKEN`: token de verificação do webhook.
- `NUMERO_TESTE`: número de referência interna para teste.
- `NUMERO_DESTINATARIO`: número para disparo de teste.
- `JANELA_HORARIOS`: texto padrão com janela sugerida de horários.

## Endpoints
- `GET /health`
- `GET /webhook` (verificação Meta)
- `POST /webhook` (mensagens recebidas)
- `POST /send-test` (envia uma mensagem de teste)
- `GET /clientes/:telefone/historico?limit=20` (histórico de conversa)

## Configuração Meta (Webhook)
1. No painel Meta Developers, configure o webhook para apontar para:
   - `GET/POST https://SEU_DOMINIO/webhook`
2. Use o mesmo valor de `WHATSAPP_VERIFY_TOKEN` na configuração do webhook.
3. Garanta que o app tenha permissão para enviar mensagens no número `WHATSAPP_PHONE_NUMBER_ID`.

## Exemplo rápido de fluxo
- Cliente envia: `quero agendar`
- Bot responde com horário existente ou janela disponível.
- Cliente envia: `remarcar`
- Bot muda status do agendamento para `remarcacao_solicitada` e sugere nova janela.
