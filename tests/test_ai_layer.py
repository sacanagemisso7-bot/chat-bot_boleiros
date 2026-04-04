import importlib
import json
from datetime import datetime, timedelta
from urllib.error import URLError


def _mock_response(payload: dict):
    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps(payload).encode("utf-8")

    return _Resp()


def test_ai_desligada_nao_chama_openai(monkeypatch):
    monkeypatch.setenv("OPENAI_ENABLED", "false")
    monkeypatch.setenv("OPENAI_API_KEY", "")

    import services.ai as ai_module

    importlib.reload(ai_module)

    def _should_not_call(*args, **kwargs):
        raise AssertionError("urlopen não deveria ser chamado com IA desligada")

    monkeypatch.setattr(ai_module, "urlopen", _should_not_call)
    svc = ai_module.AIService()
    assert svc.generate_reply("teste", {"scheduling_context": {}, "promotions": {"active": []}}) is None


def test_ai_falha_openai_com_fallback(monkeypatch):
    monkeypatch.setenv("OPENAI_ENABLED", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "key")

    import services.ai as ai_module

    importlib.reload(ai_module)

    def _raise_url_error(*args, **kwargs):
        raise URLError("timeout")

    monkeypatch.setattr(ai_module, "urlopen", _raise_url_error)
    svc = ai_module.AIService()
    assert svc.generate_reply("teste", {"scheduling_context": {}, "promotions": {"active": []}}) is None


def test_build_ai_context_com_dados_reais(app_ctx):
    db = app_ctx["db"]
    with db.get_conn() as conn:
        stamp = db.utc_now_iso()
        conn.execute(
            """
            INSERT INTO clientes (nome, telefone, onboarding_status, barbeiro_favorito, preferencia, observacoes, criado_em, atualizado_em)
            VALUES ('Bruno', '5511955500001', 'ativo', 'João', 'degradê', 'cliente antigo', ?, ?)
            """,
            (stamp, stamp),
        )
        cid = conn.execute("SELECT id FROM clientes WHERE telefone='5511955500001'").fetchone()["id"]
        dt = (datetime.utcnow() + timedelta(days=1)).isoformat()
        conn.execute(
            "INSERT INTO agendamentos (cliente_id, data_hora, servico, status, criado_em, atualizado_em) VALUES (?, ?, 'corte', 'confirmado', ?, ?)",
            (cid, dt, stamp, stamp),
        )
        conn.execute(
            "INSERT INTO disponibilidade (barbeiro, data_hora, disponivel, servico, observacoes) VALUES ('João', ?, 1, 'corte', 'slot')",
            ((datetime.utcnow() + timedelta(days=2)).isoformat(),),
        )
        conn.execute(
            "INSERT INTO mensagens (cliente_id, telefone, direcao, mensagem, tipo, criada_em) VALUES (?, '5511955500001', 'in', 'oi', 'text', ?)",
            (cid, stamp),
        )
        conn.commit()

    import services.ai_context as ctx_module

    importlib.reload(ctx_module)
    cliente = db.get_cliente_by_phone("5511955500001")
    context = ctx_module.build_ai_context(cliente, "5511955500001")

    assert context["customer_profile"]["nome"] == "Bruno"
    assert context["customer_profile"]["barbeiro_favorito"] == "João"
    assert context["scheduling_context"]["proximo_agendamento"] is not None
    assert len(context["conversation_history"]) >= 1
    assert len(context["scheduling_context"]["proximos_slots_disponiveis"]) >= 1


def test_ai_bloqueia_resposta_inventada_sem_slots(monkeypatch):
    monkeypatch.setenv("OPENAI_ENABLED", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "key")

    import services.ai as ai_module

    importlib.reload(ai_module)
    payload = {"choices": [{"message": {"content": "Temos horário às 15h com 20% de desconto hoje."}}]}
    monkeypatch.setattr(ai_module, "urlopen", lambda *a, **k: _mock_response(payload))

    svc = ai_module.AIService()
    context = {"scheduling_context": {"proximos_slots_disponiveis": []}, "promotions": {"active": []}}
    assert svc.generate_reply("horários?", context) is None


def test_chatbot_usa_ia_em_duvida_generica(app_ctx, monkeypatch):
    db = app_ctx["db"]
    with db.get_conn() as conn:
        stamp = db.utc_now_iso()
        conn.execute(
            "INSERT INTO clientes (nome, telefone, onboarding_status, criado_em, atualizado_em) VALUES ('Lia', '5511944400001', 'ativo', ?, ?)",
            (stamp, stamp),
        )
        conn.commit()

    monkeypatch.setenv("OPENAI_ENABLED", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "key")

    import services.ai as ai_module
    import services.chatbot as chatbot_module

    importlib.reload(ai_module)
    importlib.reload(chatbot_module)

    payload = {"choices": [{"message": {"content": "Para essa semana, consigo te orientar pelos próximos horários disponíveis do sistema. Quer que eu te mostre?"}}]}
    monkeypatch.setattr(ai_module, "urlopen", lambda *a, **k: _mock_response(payload))

    bot = chatbot_module.ChatbotService()
    resp = bot.handle_message("5511944400001", "como funciona o atendimento de vocês?")
    assert "próximos horários" in resp.lower() or "quer que eu te mostre" in resp.lower()
