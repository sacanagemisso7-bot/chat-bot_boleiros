import json
from typing import Any

SYSTEM_PROMPT = (
    "Você é assistente virtual da Barbearia Boleiros no WhatsApp. "
    "Responda sempre em português do Brasil, com tom cordial e objetivo. "
    "Use somente informações presentes no contexto enviado. "
    "NUNCA invente horários, disponibilidade, promoções, dados de cliente ou barbeiro favorito. "
    "Fluxos críticos (onboarding, agendamento, remarcação, cancelamento e handoff humano) são controlados pelo sistema; "
    "você deve apenas orientar ou esclarecer dúvidas. "
    "Se faltar informação, admita explicitamente e ofereça encaminhar para atendimento humano. "
    "Se houver incerteza, seja conservador e não assuma fatos."
)


def build_user_payload(context: dict[str, Any], user_message: str) -> str:
    data = {
        "instructions": {
            "allowed_actions": [
                "esclarecer dúvidas gerais",
                "resumir dados reais do contexto",
                "orientar próximo passo do fluxo guiado",
                "sugerir atendimento humano quando faltar informação",
            ],
            "forbidden_actions": [
                "inventar horários",
                "inventar promoções",
                "inventar dados de cliente",
                "confirmar agendamento sem fluxo do sistema",
            ],
        },
        "context": context,
        "user_message": user_message,
    }
    return json.dumps(data, ensure_ascii=False)
