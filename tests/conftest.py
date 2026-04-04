import importlib
import json
from datetime import datetime, timedelta

import pytest

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class DummyRequest:
    def __init__(self, payload: dict):
        self.payload = payload
        self.raw = json.dumps(payload).encode("utf-8")

    async def body(self) -> bytes:
        return self.raw

    async def json(self) -> dict:
        return self.payload


@pytest.fixture
def app_ctx(tmp_path, monkeypatch):
    db_path = tmp_path / "test_chatbot.db"
    monkeypatch.setenv("DB_PATH", str(db_path))
    monkeypatch.setenv("META_VALIDATE_SIGNATURE", "false")
    monkeypatch.setenv("META_VERIFY_TOKEN", "verify")
    monkeypatch.setenv("META_WHATSAPP_TOKEN", "token")
    monkeypatch.setenv("META_PHONE_NUMBER_ID", "phone-id")
    monkeypatch.setenv("DEBUG_ENDPOINTS_ENABLED", "true")
    monkeypatch.setenv("OPENAI_ENABLED", "false")

    import db
    import services.ai
    import services.chatbot
    import services.meta
    import services.scheduler
    import app as app_module

    importlib.reload(db)
    importlib.reload(services.ai)
    importlib.reload(services.scheduler)
    importlib.reload(services.chatbot)
    importlib.reload(services.meta)
    importlib.reload(app_module)

    db.init_db()

    sent_messages: list[tuple[str, str]] = []

    def fake_send(to_number: str, text: str):
        sent_messages.append((to_number, text))
        return f"out-{len(sent_messages)}"

    monkeypatch.setattr(app_module, "send_whatsapp_message", fake_send)

    return {"db": db, "app": app_module, "sent": sent_messages, "DummyRequest": DummyRequest}


@pytest.fixture
def seeded_cliente_e_slots(app_ctx):
    db = app_ctx["db"]
    now = datetime.utcnow().replace(minute=0, second=0, microsecond=0)
    with db.get_conn() as conn:
        now_iso = db.utc_now_iso()
        conn.execute(
            """
            INSERT INTO clientes (nome, telefone, onboarding_status, criado_em, atualizado_em)
            VALUES ('Carlos', '5511990000001', 'ativo', ?, ?)
            """,
            (now_iso, now_iso),
        )
        slots = [
            ("João", (now + timedelta(days=1, hours=10)).isoformat(), 1, "corte", "A"),
            ("Marcos", (now + timedelta(days=1, hours=11)).isoformat(), 1, "corte", "B"),
        ]
        conn.executemany(
            "INSERT INTO disponibilidade (barbeiro, data_hora, disponivel, servico, observacoes) VALUES (?, ?, ?, ?, ?)",
            slots,
        )
        conn.commit()
