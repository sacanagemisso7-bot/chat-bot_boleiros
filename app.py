import os
import sqlite3
from datetime import datetime
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, Form, Header, HTTPException, Request
from fastapi.responses import PlainTextResponse
from twilio.request_validator import RequestValidator
from twilio.twiml.messaging_response import MessagingResponse

load_dotenv()

app = FastAPI(title="Barbershop WhatsApp Bot (Twilio)")

DB_PATH = os.getenv("DB_PATH", "barbearia.db")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_VALIDATE_REQUESTS = os.getenv("TWILIO_VALIDATE_REQUESTS", "false").lower() == "true"


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


def validar_assinatura_twilio(request_url: str, form_data: dict[str, str], signature: str) -> bool:
    if not TWILIO_VALIDATE_REQUESTS:
        return True
    if not TWILIO_AUTH_TOKEN:
        return False
    validator = RequestValidator(TWILIO_AUTH_TOKEN)
    return validator.validate(request_url, form_data, signature)


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.get("/health", response_class=PlainTextResponse)
def health() -> str:
    return "ok"


@app.post("/whatsapp", response_class=PlainTextResponse)
async def whatsapp_webhook(
    request: Request,
    From: str = Form(...),
    Body: str = Form(""),
    x_twilio_signature: Optional[str] = Header(default=None, alias="X-Twilio-Signature"),
):
    if TWILIO_VALIDATE_REQUESTS:
        if not x_twilio_signature:
            raise HTTPException(status_code=403, detail="Assinatura Twilio ausente")

        form_data = {"From": From, "Body": Body}
        ok = validar_assinatura_twilio(str(request.url), form_data, x_twilio_signature)
        if not ok:
            raise HTTPException(status_code=403, detail="Assinatura Twilio inválida")

    resposta = mensagem_personalizada(From, Body)
    twiml = MessagingResponse()
    twiml.message(resposta)
    return str(twiml)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
