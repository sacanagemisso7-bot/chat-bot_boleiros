import logging
import os
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse, PlainTextResponse

from db import (
    get_cliente_by_phone,
    get_conn,
    init_db,
    list_recent_messages,
    normalizar_numero,
    save_message,
    save_webhook_event,
)
from services.chatbot import ChatbotService
from services.meta import build_event_id, extract_inbound_messages, send_whatsapp_message, validate_signature
from services.scheduler import SchedulerService

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("barbearia-bot")

app = FastAPI(title="Barbershop WhatsApp Bot (Meta Cloud API)")
META_VERIFY_TOKEN = os.getenv("META_VERIFY_TOKEN", "")

chatbot = ChatbotService()
scheduler = SchedulerService()


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.get("/health", response_class=PlainTextResponse)
def health() -> str:
    return "ok"


@app.get("/webhook", response_class=PlainTextResponse)
def verify_webhook(
    hub_mode: str = Query(alias="hub.mode"),
    hub_verify_token: str = Query(alias="hub.verify_token"),
    hub_challenge: str = Query(alias="hub.challenge"),
):
    if hub_mode == "subscribe" and hub_verify_token == META_VERIFY_TOKEN:
        return hub_challenge
    raise HTTPException(status_code=403, detail="Verificação inválida")


@app.post("/webhook")
async def receive_webhook(
    request: Request,
    x_hub_signature_256: Optional[str] = Header(default=None, alias="X-Hub-Signature-256"),
):
    raw_body = await request.body()
    if not validate_signature(raw_body, x_hub_signature_256):
        raise HTTPException(status_code=403, detail="Assinatura Meta inválida")

    payload = await request.json()
    event_id = build_event_id(payload)
    if not save_webhook_event(event_id, payload):
        logger.info("Evento duplicado ignorado: %s", event_id)
        return JSONResponse({"status": "duplicate_event"}, status_code=200)

    inbound_messages = extract_inbound_messages(payload)
    if not inbound_messages:
        logger.info("Evento sem mensagem útil recebido; ignorado")
        return JSONResponse({"status": "ignored"}, status_code=200)

    for msg in inbound_messages:
        phone = normalizar_numero(msg.phone)
        cliente = get_cliente_by_phone(phone)
        cliente_id = cliente["id"] if cliente else None

        was_saved = save_message(cliente_id, phone, "in", msg.text, msg.message_type, msg.message_id)
        if not was_saved:
            logger.info("Mensagem inbound duplicada ignorada: %s", msg.message_id)
            continue

        resposta = chatbot.handle_message(phone, msg.text)
        try:
            outbound_meta_id = send_whatsapp_message(phone, resposta)
            updated_cliente = get_cliente_by_phone(phone)
            updated_cliente_id = updated_cliente["id"] if updated_cliente else None
            save_message(updated_cliente_id, phone, "out", resposta, "text", outbound_meta_id)
        except Exception as exc:
            logger.exception("Erro ao enviar mensagem para %s: %s", phone, exc)
            raise HTTPException(status_code=500, detail=f"Falha ao enviar mensagem: {exc}") from exc

    return JSONResponse({"status": "sent"}, status_code=200)


@app.get("/debug/clientes")
def debug_clientes(limit: int = 30):
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM clientes ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(row) for row in rows]


@app.get("/debug/slots")
def debug_slots(limit: int = 20):
    return [dict(r) for r in scheduler.list_available_slots(limit=limit)]


@app.get("/debug/mensagens")
def debug_mensagens(telefone: str, limit: int = 15):
    return [dict(r) for r in list_recent_messages(normalizar_numero(telefone), limit=limit)]


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
