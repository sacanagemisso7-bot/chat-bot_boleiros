import asyncio
import json
from datetime import datetime, timedelta

from fastapi import HTTPException


def make_message_payload(phone: str, text: str, message_id: str) -> dict:
    return {
        "entry": [
            {
                "id": "WABA-ID",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messaging_product": "whatsapp",
                            "messages": [
                                {
                                    "id": message_id,
                                    "from": phone,
                                    "type": "text",
                                    "text": {"body": text},
                                }
                            ],
                        },
                    }
                ],
            }
        ]
    }


def parse_response(response):
    return json.loads(response.body.decode("utf-8"))


def test_onboarding_cliente_novo(app_ctx):
    app = app_ctx["app"]
    db = app_ctx["db"]
    DummyRequest = app_ctx["DummyRequest"]

    response = asyncio.run(app.receive_webhook(DummyRequest(make_message_payload("5511960000001", "oi", "m-onb-1")), None))
    assert parse_response(response)["status"] == "sent"

    with db.get_conn() as conn:
        cliente = conn.execute("SELECT * FROM clientes WHERE telefone = '5511960000001'").fetchone()
        assert cliente is not None
        assert cliente["onboarding_status"] == "aguardando_nome"

    response2 = asyncio.run(app.receive_webhook(DummyRequest(make_message_payload("5511960000001", "Gustavo", "m-onb-2")), None))
    assert parse_response(response2)["status"] == "sent"

    with db.get_conn() as conn:
        cliente2 = conn.execute("SELECT * FROM clientes WHERE telefone = '5511960000001'").fetchone()
        msgs = conn.execute("SELECT * FROM mensagens WHERE telefone = '5511960000001' ORDER BY id").fetchall()
        assert cliente2["nome"] == "Gustavo"
        assert cliente2["onboarding_status"] == "ativo"
        assert len(msgs) == 4  # 2 inbound + 2 outbound


def test_agendamento_respeita_slots_ids_salvos(app_ctx, seeded_cliente_e_slots):
    app = app_ctx["app"]
    db = app_ctx["db"]
    DummyRequest = app_ctx["DummyRequest"]

    asyncio.run(app.receive_webhook(DummyRequest(make_message_payload("5511990000001", "quero agendar", "m-ag-1")), None))

    with db.get_conn() as conn:
        cliente = conn.execute("SELECT * FROM clientes WHERE telefone = '5511990000001'").fetchone()
        estado = conn.execute("SELECT * FROM conversa_estado WHERE cliente_id = ?", (cliente["id"],)).fetchone()
        dados = json.loads(estado["dados_json"])
        slots_ids = dados["slots_ids"]
        assert len(slots_ids) >= 2
        expected_slot_id = slots_ids[1]
        expected_slot = conn.execute("SELECT * FROM disponibilidade WHERE id = ?", (expected_slot_id,)).fetchone()

        # adiciona slot mais cedo para bagunçar eventual recálculo por posição
        earlier_dt = (datetime.fromisoformat(expected_slot["data_hora"]) - timedelta(hours=2)).isoformat()
        conn.execute(
            "INSERT INTO disponibilidade (barbeiro, data_hora, disponivel, servico, observacoes) VALUES ('Novo', ?, 1, 'corte', 'inserido depois')",
            (earlier_dt,),
        )
        conn.commit()

    asyncio.run(app.receive_webhook(DummyRequest(make_message_payload("5511990000001", "2", "m-ag-2")), None))

    with db.get_conn() as conn:
        ag = conn.execute(
            "SELECT * FROM agendamentos a JOIN clientes c ON c.id = a.cliente_id WHERE c.telefone = '5511990000001' ORDER BY a.id DESC LIMIT 1"
        ).fetchone()
        slot = conn.execute("SELECT * FROM disponibilidade WHERE id = ?", (expected_slot_id,)).fetchone()
        assert ag["data_hora"] == expected_slot["data_hora"]
        assert slot["disponivel"] == 0


def test_cancelamento_libera_slot(app_ctx):
    app = app_ctx["app"]
    db = app_ctx["db"]
    DummyRequest = app_ctx["DummyRequest"]

    now = datetime.utcnow().replace(minute=0, second=0, microsecond=0)
    slot_dt = (now + timedelta(days=1)).isoformat()
    with db.get_conn() as conn:
        stamp = db.utc_now_iso()
        conn.execute(
            "INSERT INTO clientes (nome, telefone, onboarding_status, criado_em, atualizado_em) VALUES ('Ana', '5511970000002', 'ativo', ?, ?)",
            (stamp, stamp),
        )
        cliente_id = conn.execute("SELECT id FROM clientes WHERE telefone='5511970000002'").fetchone()["id"]
        conn.execute(
            "INSERT INTO disponibilidade (barbeiro, data_hora, disponivel, servico, observacoes) VALUES ('João', ?, 0, 'corte', 'slot agendado')",
            (slot_dt,),
        )
        conn.execute(
            "INSERT INTO agendamentos (cliente_id, data_hora, servico, status, criado_em, atualizado_em) VALUES (?, ?, 'corte', 'confirmado', ?, ?)",
            (cliente_id, slot_dt, stamp, stamp),
        )
        conn.commit()

    asyncio.run(app.receive_webhook(DummyRequest(make_message_payload("5511970000002", "cancelar", "m-can-1")), None))

    with db.get_conn() as conn:
        ag = conn.execute("SELECT * FROM agendamentos WHERE cliente_id = ? ORDER BY id DESC LIMIT 1", (cliente_id,)).fetchone()
        slot = conn.execute("SELECT * FROM disponibilidade WHERE data_hora = ? AND servico = 'corte'", (slot_dt,)).fetchone()
        assert ag["status"] == "cancelado"
        assert slot["disponivel"] == 1


def test_deduplicacao_webhook_mesmo_message_id(app_ctx):
    app = app_ctx["app"]
    db = app_ctx["db"]
    DummyRequest = app_ctx["DummyRequest"]
    sent = app_ctx["sent"]

    payload = make_message_payload("5511960000099", "oi", "meta-dup-1")
    resp1 = asyncio.run(app.receive_webhook(DummyRequest(payload), None))
    resp2 = asyncio.run(app.receive_webhook(DummyRequest(payload), None))

    assert parse_response(resp1)["status"] == "sent"
    assert parse_response(resp2)["status"] == "duplicate_event"
    assert len(sent) == 1

    with db.get_conn() as conn:
        msgs = conn.execute("SELECT * FROM mensagens WHERE meta_message_id = 'meta-dup-1'").fetchall()
        assert len(msgs) == 1


def test_debug_endpoints_bloqueados_quando_desabilitados(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "db_debug.db"))
    monkeypatch.setenv("DEBUG_ENDPOINTS_ENABLED", "false")

    import importlib
    import app as app_module
    import db

    importlib.reload(db)
    importlib.reload(app_module)
    db.init_db()

    try:
        app_module.debug_clientes()
        assert False, "Deveria bloquear endpoint debug"
    except HTTPException as exc:
        assert exc.status_code == 404
