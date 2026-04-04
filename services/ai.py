import json
import logging
import os
import re
from typing import Any, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from services.ai_prompt import SYSTEM_PROMPT, build_user_payload

logger = logging.getLogger(__name__)


class AIService:
    def __init__(self) -> None:
        self.enabled = os.getenv("OPENAI_ENABLED", "false").lower() == "true"
        self.api_key = os.getenv("OPENAI_API_KEY", "")
        self.model = os.getenv("OPENAI_MODEL", "gpt-5.4-mini")
        self.timeout_seconds = float(os.getenv("OPENAI_TIMEOUT_SECONDS", "20"))
        self.temperature = float(os.getenv("OPENAI_TEMPERATURE", "0.2"))

    def can_use(self) -> bool:
        return self.enabled and bool(self.api_key)

    @staticmethod
    def _is_grounded_reply(reply: str, context: dict[str, Any]) -> bool:
        scheduling = context.get("scheduling_context", {})
        promotions = context.get("promotions", {})

        # Sem slots no contexto => não aceitar resposta com horário específico inventado.
        if not scheduling.get("proximos_slots_disponiveis"):
            if re.search(r"\b\d{1,2}[:h]\d{0,2}\b", reply.lower()):
                return False

        # Sem promoções ativas => não aceitar afirmação promocional detalhada.
        if not promotions.get("active"):
            if any(token in reply.lower() for token in ["desconto", "%", "promoção", "promo"]):
                return False

        return True

    def generate_reply(self, user_message: str, context: dict[str, Any]) -> Optional[str]:
        if not self.can_use():
            return None

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_user_payload(context, user_message)},
        ]

        payload = json.dumps(
            {"model": self.model, "messages": messages, "temperature": self.temperature}
        ).encode("utf-8")
        req = Request(
            "https://api.openai.com/v1/chat/completions",
            data=payload,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urlopen(req, timeout=self.timeout_seconds) as response:
                data = json.loads(response.read().decode("utf-8"))
                reply = data["choices"][0]["message"]["content"].strip()
                if not reply:
                    return None
                if not self._is_grounded_reply(reply, context):
                    logger.warning("Resposta da IA rejeitada por potencial falta de lastro no contexto")
                    return None
                return reply
        except HTTPError as exc:
            logger.warning("OpenAI HTTPError %s", exc.code)
            return None
        except URLError as exc:
            logger.warning("OpenAI URLError: %s", exc)
            return None
        except (KeyError, IndexError, ValueError, json.JSONDecodeError) as exc:
            logger.warning("Resposta OpenAI inválida: %s", exc)
            return None
        except Exception as exc:
            logger.exception("Falha inesperada na integração OpenAI: %s", exc)
            return None
