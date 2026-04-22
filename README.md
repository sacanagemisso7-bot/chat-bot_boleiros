# Chatbot de WhatsApp para Barbearia (Twilio)

Projeto base de chatbot para WhatsApp com respostas personalizadas usando dados já existentes de clientes, integrado via **Twilio WhatsApp API**.

## O que esse bot faz
- Recebe mensagens no webhook `POST /whatsapp`.
- Busca cliente por telefone no SQLite.
- Responde de forma personalizada com nome, preferência de corte e barbeiro favorito.
- Sugere manutenção com base na data do último corte.
- Informa próximo agendamento, permite solicitar **remarcação** e sugere horários.
- Salva histórico de mensagens (entrada/saída) por cliente.
- Retorna resposta em TwiML para o Twilio entregar no WhatsApp.

## Stack
- JavaScript (Node.js + Express)
- SQLite
- Twilio WhatsApp API (Webhook + TwiML)

## Como rodar
```bash
npm install
cp .env.example .env
npm run seed
npm run dev
```

Servidor padrão: `http://localhost:8000`

## Configuração Twilio
1. Ative WhatsApp Sandbox no Twilio.
2. Configure o webhook de entrada para:
   - `POST https://SEU_DOMINIO/whatsapp`
3. Se quiser validação da assinatura do Twilio:
   - defina `TWILIO_VALIDATE_REQUESTS=true`
   - preencha `TWILIO_AUTH_TOKEN` no `.env`

## Variáveis de ambiente
- `PORT`: porta HTTP da aplicação.
- `DB_PATH`: caminho do banco SQLite.
- `TWILIO_AUTH_TOKEN`: token para validar assinatura da Twilio.
- `TWILIO_VALIDATE_REQUESTS`: habilita/desabilita validação da assinatura.
- `JANELA_HORARIOS`: texto padrão com janela sugerida de horários.

## Endpoints úteis
- `GET /health`
- `POST /whatsapp`
- `GET /clientes/:telefone/historico?limit=20` (retorna histórico de conversa salvo)

## Exemplo de uso
Mensagem do cliente: `quero agendar`

Resposta:
- Se já houver horário confirmado: informa data/hora e oferece remarcação.
- Se não houver: sugere janela de horários.

Mensagem do cliente: `remarcar`

Resposta:
- Marca agendamento atual como `remarcacao_solicitada` e inicia fluxo de nova sugestão.

## Próximos passos para produção
- [ ] Integrar com seu CRM/ERP em vez de SQLite.
- [x] Guardar histórico de conversa.
- [ ] Implementar confirmação automática de agenda por IA.
- [ ] Disparar campanhas segmentadas (aniversariantes, clientes inativos, etc.).
