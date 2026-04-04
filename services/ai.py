import json
import os
from typing import Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class AIService:
    def __init__(self) -> None:
        self.enabled = os.getenv("OPENAI_ENABLED", "false").lower() == "true"
        self.api_key = os.getenv("OPENAI_API_KEY", "")
        self.model = os.getenv("OPENAI_MODEL", "gpt-5.4-mini")

    def can_use(self) -> bool:
        return self.enabled and bool(self.api_key)

    def generate_reply(self, user_message: str, business_context: str, history: list[dict[str, str]]) -> Optional[str]:
        if not self.can_use():
            return None

        system_prompt = (
            "Você é assistente de WhatsApp de uma barbearia no Brasil. "
            "Responda em português do Brasil, com objetividade e simpatia. "
            "Nunca invente horários, promoções ou dados: use apenas contexto recebido. "
            "Se faltar informação, sugira atendimento humano."
        )
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(history[-6:])
        messages.append({"role": "user", "content": f"Contexto: {business_context}\nMensagem: {user_message}"})

        payload = json.dumps(
            {"model": self.model, "messages": messages, "temperature": 0.3}
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
            with urlopen(req, timeout=20) as response:
                data = json.loads(response.read().decode("utf-8"))
                return data["choices"][0]["message"]["content"].strip()
        except (HTTPError, URLError, KeyError, IndexError, ValueError):
            return None
