# Chatbot de WhatsApp para Barbearia

Backend Node.js/Express com SQLite para atendimento via WhatsApp Cloud API da Meta. O MVP cadastra novos clientes, mantem estado persistente da conversa, agenda horarios, remarca agendamentos e salva historico de mensagens.

## Requisitos

- Node.js 18 ou superior
- Conta/app Meta com WhatsApp Cloud API
- Um numero de WhatsApp configurado na Meta

## Instalar

```bash
npm install
```

Crie o arquivo `.env` a partir do exemplo:

```bash
cp .env.example .env
```

No Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

## Configurar `.env`

Preencha:

- `PORT`: porta HTTP do servidor.
- `DB_PATH`: caminho do arquivo SQLite.
- `WHATSAPP_TOKEN`: token de acesso da Meta.
- `WHATSAPP_PHONE_NUMBER_ID`: ID do numero de telefone na Cloud API.
- `WHATSAPP_BUSINESS_ID`: ID da conta WhatsApp Business.
- `WHATSAPP_VERIFY_TOKEN`: token usado para validar o webhook.
- `NUMERO_DESTINATARIO`: numero usado no teste manual.
- `JANELA_HORARIOS`: texto padrao de disponibilidade.
- `ADMIN_TOKEN`: token para endpoints administrativos.

## Popular Banco

```bash
npm run seed
```

O seed cria clientes de exemplo, um agendamento futuro confirmado e estados `idle` na tabela `conversas_estado`.

## Rodar

```bash
npm run dev
```

Servidor padrao: `http://localhost:8000`

## Webhook Meta

No painel Meta Developers, configure o webhook para:

- Callback URL: `https://SEU_DOMINIO/webhook`
- Verify token: mesmo valor de `WHATSAPP_VERIFY_TOKEN`
- Campo assinado: `messages`

O endpoint `GET /webhook` valida o desafio da Meta. O endpoint `POST /webhook` recebe mensagens, ignora eventos sem texto util e responde pelo WhatsApp.

## Endpoints

- `GET /health`
- `GET /webhook`
- `POST /webhook`
- `POST /send-test`
- `GET /clientes/:telefone/historico?limit=20`

`/send-test` e `/clientes/:telefone/historico` exigem o header:

```http
x-admin-token: SEU_ADMIN_TOKEN
```

Exemplo de teste:

```bash
curl -X POST http://localhost:8000/send-test -H "x-admin-token: SEU_ADMIN_TOKEN"
```

Consultar historico:

```bash
curl "http://localhost:8000/clientes/5511999991111/historico?limit=20" -H "x-admin-token: SEU_ADMIN_TOKEN"
```

## Fluxos Suportados

- Cliente novo: pede nome, cadastra telefone e libera o menu principal.
- Agendamento: coleta data, horario, confirma e grava em `agendamentos`.
- Remarcacao: encontra o proximo agendamento confirmado, coleta nova data/hora, confirma e atualiza o registro.
- Promocao: responde oferta simples baseada na preferencia do cliente.
- Mensagens genericas: recomenda corte e mostra opcoes principais.

Datas aceitas no MVP: `hoje`, `amanha`, dias da semana como `sexta`, e datas como `25/04`. Horarios aceitos: `14h`, `14:30` e formatos proximos.

## Verificacao Local

```bash
npm run check
```

O projeto usa `fetch` nativo, por isso requer Node.js 18+.
