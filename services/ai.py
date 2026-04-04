import json
import logging
import os
import re
from typing import Any, Optional

from services.ai_prompt import SYSTEM_PROMPT, build_user_payload

logger = logging.getLogger(__name__)


class AIService:
    def __init__(self) -> None:
        # Gemini é o caminho principal; OPENAI_* mantido apenas para retrocompatibilidade temporária.
        self.enabled = os.getenv("GEMINI_ENABLED", os.getenv("OPENAI_ENABLED", "false")).lower() == "true"
        self.api_key = os.getenv("GEMINI_API_KEY", os.getenv("OPENAI_API_KEY", ""))
        self.model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
        self.timeout_seconds = float(os.getenv("GEMINI_TIMEOUT_SECONDS", "20"))
        self.temperature = float(os.getenv("GEMINI_TEMPERATURE", "0.2"))

    def can_use(self) -> bool:
        return self.enabled and bool(self.api_key)

    def _build_client(self):
        from google import genai
        from google.genai import types

        http_options = types.HttpOptions(timeout=self.timeout_seconds)
        return genai.Client(api_key=self.api_key, http_options=http_options), types

    @staticmethod
    def _extract_text_from_response(response: Any) -> str:
        text = getattr(response, "text", None)
        if text:
            return text.strip()

        try:
            candidates = getattr(response, "candidates", []) or []
            parts = candidates[0].content.parts
            return "".join(getattr(p, "text", "") for p in parts).strip()
        except Exception:
            return ""

    @staticmethod
    def _is_grounded_reply(reply: str, context: dict[str, Any]) -> bool:
        scheduling = context.get("scheduling_context", {})
        promotions = context.get("promotions", {})

        if not scheduling.get("proximos_slots_disponiveis") and re.search(r"\b\d{1,2}[:h]\d{0,2}\b", reply.lower()):
            return False

        if not promotions.get("active") and any(token in reply.lower() for token in ["desconto", "%", "promoção", "promo"]):
            return False

        return True

    def generate_reply(self, user_message: str, context: dict[str, Any]) -> Optional[str]:
        if not self.can_use():
            return None

        prompt_json = build_user_payload(context, user_message)
        try:
            client, types = self._build_client()
            response = client.models.generate_content(
                model=self.model,
                contents=prompt_json,
                config=types.GenerateContentConfig(
                    temperature=self.temperature,
                    system_instruction=SYSTEM_PROMPT,
                ),
            )
            reply = self._extract_text_from_response(response)
            if not reply:
                return None
            if not self._is_grounded_reply(reply, context):
                logger.warning("Resposta Gemini rejeitada por potencial falta de lastro no contexto")
                return None
            return reply
        except Exception as exc:
            logger.warning("Falha na Gemini; fallback por regras ativado: %s", exc)
            return None
