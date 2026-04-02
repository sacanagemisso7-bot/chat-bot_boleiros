# Chatbot de WhatsApp para Barbearia (Twilio)

Projeto base de chatbot para WhatsApp com respostas personalizadas usando dados já existentes de clientes, integrado via **Twilio WhatsApp API**.

## O que esse bot faz
- Recebe mensagens no webhook `POST /whatsapp`.
- Busca cliente por telefone no SQLite.
- Responde de forma personalizada com nome, preferência de corte e barbeiro favorito.
- Sugere manutenção com base na data do último corte.
- Informa próximo agendamento, sugere horários e ofertas.
- Retorna resposta em TwiML para o Twilio entregar no WhatsApp.

## Stack
- Python + FastAPI
- SQLite
- Twilio WhatsApp API (Webhook + TwiML)

## Como rodar
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python seed_clientes.py
uvicorn app:app --reload --port 8000
```

## Configuração Twilio
1. Ative WhatsApp Sandbox no Twilio.
2. Configure o webhook de entrada para:
   - `POST https://SEU_DOMINIO/whatsapp`
3. Se quiser validação da assinatura do Twilio:
   - defina `TWILIO_VALIDATE_REQUESTS=true`
   - preencha `TWILIO_AUTH_TOKEN` no `.env`

## Exemplo de uso
Mensagem do cliente: `quero agendar`

Resposta:
- Se já houver horário confirmado: informa data/hora e oferece remarcação.
- Se não houver: sugere janela de horários.

## Próximos passos para produção
- Integrar com seu CRM/ERP em vez de SQLite.
- Guardar histórico de conversa.
- Implementar confirmação automática de agenda por IA.
- Disparar campanhas segmentadas (aniversariantes, clientes inativos, etc.).
