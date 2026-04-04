import hashlib
import hmac
import os
import sqlite3
from datetime import datetime
from typing import Optional

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse, PlainTextResponse

load_dotenv()

app = FastAPI(title="Barbershop WhatsApp Bot (Meta Cloud API)")

DB_PATH = os.getenv("DB_PATH", "barbearia.db")
META_VERIFY_TOKEN = os.getenv("META_VERIFY_TOKEN", "")
META_WHATSAPP_TOKEN = os.getenv("META_WHATSAPP_TOKEN", "")
META_PHONE_NUMBER_ID = os.getenv("META_PHONE_NUMBER_ID", "")
META_APP_SECRET = os.getenv("META_APP_SECRET", "")
META_VALIDATE_SIGNATURE = os.getenv("META_VALIDATE_SIGNATURE", "false").lower() == "true"
META_GRAPH_VERSION = os.getenv("META_GRAPH_VERSION", "v22.0")
GRAPH_BASE_URL = f"https://graph.facebook.com/{META_GRAPH_VERSION}"


def init_db() -> None:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS clientes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            telefone TEXT UNIQUE NOT NULL,
            ultimo_corte TEXT,
            preferencia TEXT,
            barbeiro_favorito TEXT,
            observacoes TEXT
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS agendamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cliente_id INTEGER NOT NULL,
            data_hora TEXT NOT NULL,
            servico TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'confirmado',
            FOREIGN KEY (cliente_id) REFERENCES clientes(id)
        )
        """
    )
    conn.commit()
    conn.close()


def normalizar_numero(numero: str) -> str:
    return ''.join(c for c in numero if c.isdigit())


def get_cliente_by_phone(phone: str) -> Optional[sqlite3.Row]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM clientes WHERE telefone = ?", (phone,))
    cliente = cur.fetchone()
    conn.close()
    return cliente


def get_proximo_agendamento(cliente_id: int) -> Optional[sqlite3.Row]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(
        """
        SELECT * FROM agendamentos
        WHERE cliente_id = ? AND status = 'confirmado' AND datetime(data_hora) >= datetime('now')
        ORDER BY datetime(data_hora) ASC
        LIMIT 1
        """,
        (cliente_id,),
    )
    agendamento = cur.fetchone()
    conn.close()
    return agendamento


def get_recomendacao(cliente: sqlite3.Row) -> str:
    ultimo = cliente["ultimo_corte"]
    pref = cliente["preferencia"] or "corte social"

    if not ultimo:
        return f"Posso te recomendar um {pref} com acabamento na navalha."

    try:
        data_ultimo = datetime.fromisoformat(ultimo)
    except ValueError:
        return f"Quer repetir seu último estilo ({pref}) ou testar um degradê moderno?"

    dias = (datetime.utcnow() - data_ultimo).days
    if dias >= 30:
        return "Já passou do tempo ideal de manutenção. Quer agendar para esta semana?"
    if dias >= 15:
        return "Seu corte está na janela perfeita para manutenção leve."
    return "Seu visual ainda está em dia. Posso já deixar um horário reservado para a próxima quinzena."


def mensagem_personalizada(phone: str, body: str) -> str:
    texto = body.strip().lower()
    cliente = get_cliente_by_phone(phone)

    if not cliente:
        return (
            "Olá! 👋 Sou o assistente da barbearia. Ainda não encontrei seu cadastro. "
            "Me diga seu *nome* para eu iniciar seu atendimento personalizado."
        )

    nome = cliente["nome"].split()[0]
    recomendacao = get_recomendacao(cliente)
    proximo = get_proximo_agendamento(cliente["id"])

    if "horário" in texto or "agendar" in texto:
        if proximo:
            data_fmt = datetime.fromisoformat(proximo["data_hora"]).strftime("%d/%m às %H:%M")
            return f"{nome}, seu próximo horário já está marcado para {data_fmt}. Se quiser alterar, me responda com *remarcar*."
        return f"{nome}, tenho horários amanhã entre 10h e 19h. Prefere manhã, tarde ou noite?"

    if "promo" in texto or "promoção" in texto:
        return (
            f"{nome}, com base no seu perfil, temos combo de {cliente['preferencia'] or 'corte + barba'} "
            "com 15% de desconto até sexta. Quer garantir?"
        )

    return (
        f"Fala, {nome}! ✂️ {recomendacao} "
        f"Seu barbeiro favorito é {cliente['barbeiro_favorito'] or 'qualquer profissional da casa'}. "
        "Posso te ajudar com *agendar*, *remarcar* ou *promoção* hoje."
    )


def validar_assinatura_meta(body: bytes, signature_header: str) -> bool:
    if not META_VALIDATE_SIGNATURE:
        return True
    if not META_APP_SECRET or not signature_header.startswith("sha256="):
        return False

    received_sig = signature_header.split("=", 1)[1]
    expected_sig = hmac.new(META_APP_SECRET.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(received_sig, expected_sig)


def send_whatsapp_message(to_number: str, text: str) -> None:
    if not META_WHATSAPP_TOKEN or not META_PHONE_NUMBER_ID:
        raise RuntimeError("META_WHATSAPP_TOKEN ou META_PHONE_NUMBER_ID não configurados")

    url = f"{GRAPH_BASE_URL}/{META_PHONE_NUMBER_ID}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "to": to_number,
        "type": "text",
        "text": {"body": text},
    }
    headers = {
        "Authorization": f"Bearer {META_WHATSAPP_TOKEN}",
        "Content-Type": "application/json",
    }

    with httpx.Client(timeout=20) as client:
        response = client.post(url, json=payload, headers=headers)
        response.raise_for_status()


def extract_message(payload: dict) -> Optional[tuple[str, str]]:
    try:
        entry = payload.get("entry", [])[0]
        change = entry.get("changes", [])[0]
        value = change.get("value", {})
        messages = value.get("messages", [])
        if not messages:
            return None
        msg = messages[0]
        from_number = normalizar_numero(msg["from"])
        text_body = msg.get("text", {}).get("body", "")
        if not text_body:
            return None
        return from_number, text_body
    except (IndexError, KeyError, AttributeError, TypeError):
        return None


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
    if META_VALIDATE_SIGNATURE:
        if not x_hub_signature_256:
            raise HTTPException(status_code=403, detail="Assinatura Meta ausente")
        if not validar_assinatura_meta(raw_body, x_hub_signature_256):
            raise HTTPException(status_code=403, detail="Assinatura Meta inválida")

    payload = await request.json()
    parsed = extract_message(payload)
    if not parsed:
        return JSONResponse({"status": "ignored"}, status_code=200)

    from_number, inbound_text = parsed
    resposta = mensagem_personalizada(from_number, inbound_text)

    try:
        send_whatsapp_message(from_number, resposta)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Falha ao enviar mensagem: {exc}") from exc

    return JSONResponse({"status": "sent"}, status_code=200)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
