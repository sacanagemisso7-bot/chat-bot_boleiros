import importlib
from datetime import datetime, timedelta


class _FakeTypes:
    class GenerateContentConfig:
        def __init__(self, **kwargs):
            self.kwargs = kwargs


class _FakeResponse:
    def __init__(self, text: str):
        self.text = text


class _FakeClient:
    def __init__(self, text: str = "", fail: bool = False):
        self._text = text
        self._fail = fail
        self.models = self

    def generate_content(self, **kwargs):
        if self._fail:
            raise TimeoutError("gemini timeout")
        return _FakeResponse(self._text)


def test_gemini_desligada_nao_chama_cliente(monkeypatch):
    monkeypatch.setenv("GEMINI_ENABLED", "false")
    monkeypatch.setenv("GEMINI_API_KEY", "")

    import services.ai as ai_module

    importlib.reload(ai_module)

    svc = ai_module.AIService()

    def _should_not_call():
        raise AssertionError("Cliente Gemini não deveria ser instanciado")

    monkeypatch.setattr(svc, "_build_client", _should_not_call)
    assert svc.generate_reply("teste", {"scheduling_context": {}, "promotions": {"active": []}}) is None


def test_gemini_falha_com_fallback(monkeypatch):
    monkeypatch.setenv("GEMINI_ENABLED", "true")
    monkeypatch.setenv("GEMINI_API_KEY", "key")

    import services.ai as ai_module

    importlib.reload(ai_module)
    svc = ai_module.AIService()
    monkeypatch.setattr(svc, "_build_client", lambda: (_FakeClient(fail=True), _FakeTypes))

    assert svc.generate_reply("teste", {"scheduling_context": {}, "promotions": {"active": []}}) is None


def test_contexto_real_continua_sendo_montado(app_ctx):
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
    assert context["scheduling_context"]["proximo_agendamento"] is not None
    assert len(context["conversation_history"]) >= 1


def test_gemini_nao_inventa_fluxo_sensivel(monkeypatch):
    monkeypatch.setenv("GEMINI_ENABLED", "true")
    monkeypatch.setenv("GEMINI_API_KEY", "key")

    import services.ai as ai_module

    importlib.reload(ai_module)
    svc = ai_module.AIService()
    monkeypatch.setattr(
        svc,
        "_build_client",
        lambda: (_FakeClient(text="Temos horário às 15h com 20% de desconto hoje."), _FakeTypes),
    )

    context = {"scheduling_context": {"proximos_slots_disponiveis": []}, "promotions": {"active": []}}
    assert svc.generate_reply("horários?", context) is None


def test_duvida_generica_com_gemini(app_ctx, monkeypatch):
    db = app_ctx["db"]
    with db.get_conn() as conn:
        stamp = db.utc_now_iso()
        conn.execute(
            "INSERT INTO clientes (nome, telefone, onboarding_status, criado_em, atualizado_em) VALUES ('Lia', '5511944400001', 'ativo', ?, ?)",
            (stamp, stamp),
        )
        conn.commit()

    monkeypatch.setenv("GEMINI_ENABLED", "true")
    monkeypatch.setenv("GEMINI_API_KEY", "key")

    import services.ai as ai_module
    import services.chatbot as chatbot_module

    importlib.reload(ai_module)
    importlib.reload(chatbot_module)

    bot = chatbot_module.ChatbotService()
    monkeypatch.setattr(
        bot.ai,
        "_build_client",
        lambda: (_FakeClient(text="Posso te orientar com base nos horários reais disponíveis no sistema."), _FakeTypes),
    )

    resp = bot.handle_message("5511944400001", "como funciona o atendimento de vocês?")
    assert "horários reais" in resp.lower() or "orientar" in resp.lower()


def test_sem_chave_gemini_sistema_continua_funcionando(app_ctx, monkeypatch):
    db = app_ctx["db"]
    with db.get_conn() as conn:
        stamp = db.utc_now_iso()
        conn.execute(
            "INSERT INTO clientes (nome, telefone, onboarding_status, criado_em, atualizado_em) VALUES ('Caio', '5511933300001', 'ativo', ?, ?)",
            (stamp, stamp),
        )
        conn.commit()

    monkeypatch.setenv("GEMINI_ENABLED", "true")
    monkeypatch.setenv("GEMINI_API_KEY", "")

    import services.chatbot as chatbot_module

    importlib.reload(chatbot_module)
    bot = chatbot_module.ChatbotService()
    resposta = bot.handle_message("5511933300001", "me explica os serviços")
    assert "posso te ajudar" in resposta.lower()
