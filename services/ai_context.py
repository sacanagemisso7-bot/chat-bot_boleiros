from typing import Any

from db import (
    get_conversa_estado,
    get_next_agendamento,
    list_available_slots,
    list_recent_agendamentos,
    list_recent_messages,
)


def _serialize_rows(rows) -> list[dict[str, Any]]:
    return [dict(r) for r in rows]


def build_ai_context(cliente, telefone: str, max_history: int = 8, max_slots: int = 5) -> dict[str, Any]:
    cliente_id = cliente["id"]
    conv_state = get_conversa_estado(cliente_id)
    next_agendamento = get_next_agendamento(cliente_id)
    recent_agendamentos = list_recent_agendamentos(cliente_id, limit=3)
    raw_history = list_recent_messages(telefone, limit=max_history)

    # Remove repetições imediatas para não inflar contexto.
    history = []
    last_key = None
    for msg in raw_history:
        key = (msg["direcao"], msg["mensagem"].strip().lower())
        if key == last_key:
            continue
        history.append(
            {
                "direcao": msg["direcao"],
                "mensagem": msg["mensagem"],
                "tipo": msg["tipo"],
                "criada_em": msg["criada_em"],
            }
        )
        last_key = key

    slots = _serialize_rows(list_available_slots(limit=max_slots))

    return {
        "business_rules": {
            "deterministic_flows_first": True,
            "language": "pt-BR",
            "do_not_invent_data": True,
            "human_handoff_hint": "Ofereça atendimento humano quando faltarem dados.",
        },
        "customer_profile": {
            "id": cliente_id,
            "nome": cliente["nome"],
            "telefone": cliente["telefone"],
            "onboarding_status": cliente["onboarding_status"],
            "barbeiro_favorito": cliente["barbeiro_favorito"],
            "preferencia": cliente["preferencia"],
            "observacoes": cliente["observacoes"],
        },
        "conversation_state": {
            "estado": conv_state["estado"],
            "atendimento_humano": conv_state["atendimento_humano"],
            "dados": conv_state["dados"],
        },
        "scheduling_context": {
            "proximo_agendamento": dict(next_agendamento) if next_agendamento else None,
            "ultimos_agendamentos": _serialize_rows(recent_agendamentos),
            "proximos_slots_disponiveis": slots,
        },
        "promotions": {
            "active": [],
            "note": "Sem promoções ativas cadastradas no banco no momento.",
        },
        "conversation_history": history,
        "allowed_actions": [
            "responder dúvidas gerais",
            "resumir disponibilidade real do contexto",
            "orientar usuário a usar fluxo de agendamento/cancelamento",
        ],
        "forbidden_actions": [
            "inventar horários",
            "inventar promoções",
            "inventar cadastro de cliente",
            "confirmar agendamento fora do fluxo determinístico",
        ],
    }
