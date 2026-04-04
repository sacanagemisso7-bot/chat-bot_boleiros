import hashlib
import hmac
import json
import logging
import os
from dataclasses import dataclass
from typing import Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from db import normalizar_numero

logger = logging.getLogger(__name__)

META_WHATSAPP_TOKEN = os.getenv("META_WHATSAPP_TOKEN", "")
META_PHONE_NUMBER_ID = os.getenv("META_PHONE_NUMBER_ID", "")
META_APP_SECRET = os.getenv("META_APP_SECRET", "")
META_VALIDATE_SIGNATURE = os.getenv("META_VALIDATE_SIGNATURE", "false").lower() == "true"
META_GRAPH_VERSION = os.getenv("META_GRAPH_VERSION", "v22.0")
GRAPH_BASE_URL = f"https://graph.facebook.com/{META_GRAPH_VERSION}"


@dataclass
class InboundMessage:
    phone: str
    text: str
    message_id: Optional[str]
    message_type: str


def validate_signature(body: bytes, signature_header: Optional[str]) -> bool:
    if not META_VALIDATE_SIGNATURE:
        return True
    if not signature_header or not META_APP_SECRET or not signature_header.startswith("sha256="):
        return False
    received_sig = signature_header.split("=", 1)[1]
    expected_sig = hmac.new(META_APP_SECRET.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(received_sig, expected_sig)


def extract_inbound_messages(payload: dict) -> list[InboundMessage]:
    output: list[InboundMessage] = []
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            for msg in value.get("messages", []) or []:
                from_number = msg.get("from")
                if not from_number:
                    continue
                text_body = (msg.get("text") or {}).get("body") or ""
                if not text_body.strip():
                    continue
                output.append(
                    InboundMessage(
                        phone=normalizar_numero(from_number),
                        text=text_body.strip(),
                        message_id=msg.get("id"),
                        message_type=msg.get("type", "text"),
                    )
                )
    return output


def build_event_id(payload: dict) -> Optional[str]:
    try:
        entry_id = payload.get("entry", [{}])[0].get("id")
        first_change = payload.get("entry", [{}])[0].get("changes", [{}])[0]
        value = first_change.get("value", {})
        if value.get("messages"):
            return value["messages"][0].get("id")
        if value.get("statuses"):
            return value["statuses"][0].get("id")
        return entry_id
    except Exception:
        return None


def send_whatsapp_message(to_number: str, text: str) -> Optional[str]:
    if not META_WHATSAPP_TOKEN or not META_PHONE_NUMBER_ID:
        raise RuntimeError("META_WHATSAPP_TOKEN ou META_PHONE_NUMBER_ID não configurados")

    url = f"{GRAPH_BASE_URL}/{META_PHONE_NUMBER_ID}/messages"
    payload = json.dumps(
        {
            "messaging_product": "whatsapp",
            "to": to_number,
            "type": "text",
            "text": {"body": text},
        }
    ).encode("utf-8")

    req = Request(
        url,
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {META_WHATSAPP_TOKEN}",
            "Content-Type": "application/json",
        },
    )

    try:
        with urlopen(req, timeout=20) as response:
            body = json.loads(response.read().decode("utf-8"))
            messages = body.get("messages", [])
            return messages[0].get("id") if messages else None
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        logger.error("Falha Meta API (%s): %s", exc.code, detail)
        raise
    except URLError:
        logger.exception("Erro de conexão ao enviar mensagem para Meta")
        raise
