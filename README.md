# Chatbot de WhatsApp para Barbearia (Meta WhatsApp Cloud API)

Projeto base de chatbot para WhatsApp com respostas personalizadas usando dados já existentes de clientes, integrado diretamente com a **API oficial da Meta**.

## O que esse bot faz
- Recebe eventos no webhook `POST /webhook`.
- Faz a verificação de webhook no `GET /webhook`.
- Busca cliente por telefone no SQLite.
- Responde de forma personalizada com nome, preferência de corte e barbeiro favorito.
- Sugere manutenção com base na data do último corte.
- Informa próximo agendamento, sugere horários e ofertas.
- Envia a resposta para o cliente usando `/{PHONE_NUMBER_ID}/messages` da Graph API.

## Stack
- Python + FastAPI
- SQLite
- Meta WhatsApp Cloud API

## Como rodar
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python seed_clientes.py
uvicorn app:app --reload --port 8000
```

## Configuração na Meta
1. Crie um app no Meta for Developers e habilite WhatsApp.
2. Configure no `.env`:
   - `META_VERIFY_TOKEN`
   - `META_WHATSAPP_TOKEN`
   - `META_PHONE_NUMBER_ID`
3. Opcional (produção):
   - `META_VALIDATE_SIGNATURE=true`
   - `META_APP_SECRET` para validar `X-Hub-Signature-256`
4. Configure webhook na Meta para:
   - `GET/POST https://SEU_DOMINIO/webhook`

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
