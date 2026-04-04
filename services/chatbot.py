from datetime import datetime
import os

from db import get_cliente_by_phone, get_conversa_estado, save_conversa_estado, set_cliente_handoff
from services.ai import AIService
from services.ai_context import build_ai_context
from services.onboarding import OnboardingService
from services.scheduler import SchedulerService


class ChatbotService:
    def __init__(self) -> None:
        self.scheduler = SchedulerService()
        self.ai = AIService()

    @staticmethod
    def _detect_intent(text: str) -> str:
        t = text.lower().strip()
        if any(x in t for x in ["humano", "atendente", "falar com alguém", "pessoa"]):
            return "humano"
        if any(x in t for x in ["cancelar", "cancela"]):
            return "cancelar"
        if any(x in t for x in ["remarcar", "reagendar", "trocar horário"]):
            return "remarcar"
        if any(x in t for x in ["agendar", "marcar", "horário", "disponibilidade"]):
            return "agendar"
        if "promo" in t:
            return "promocao"
        if "barbeiro" in t:
            return "barbeiro"
        if any(x in t for x in ["oi", "ola", "olá", "bom dia", "boa tarde", "boa noite"]):
            return "cumprimento"
        return "duvida"

    @staticmethod
    def _extract_name(text: str) -> str:
        nome = text.strip()
        if len(nome) < 2 or len(nome.split()) > 4 or any(ch.isdigit() for ch in nome):
            return ""
        return nome.title()

    def _prepare_slots_state(self, cliente_id: int, intent: str) -> str:
        slots = self.scheduler.list_available_slots(limit=5)
        if not slots:
            save_conversa_estado(cliente_id, "idle", {})
            return "No momento não há horários livres próximos. Posso te encaminhar para um atendente humano."

        estado_nome = "aguardando_slot_remarcar" if intent == "remarcar" else "aguardando_slot_agendar"
        save_conversa_estado(
            cliente_id,
            estado_nome,
            {
                "slots_ids": [s["id"] for s in slots],
                "slots_view": self.scheduler.format_slots(slots),
            },
        )
        return self.scheduler.format_slots(slots)

    def handle_message(self, phone: str, inbound_text: str) -> str:
        cliente = get_cliente_by_phone(phone)

        if not cliente:
            OnboardingService.start(phone)
            return (
                "Olá! 👋 Bem-vindo à Barbearia Boleiros. Ainda não encontrei seu cadastro. "
                "Qual é o seu nome para começarmos?"
            )

        estado = get_conversa_estado(cliente["id"])
        if estado["atendimento_humano"]:
            if any(x in inbound_text.lower() for x in ["voltar", "bot", "automatizado"]):
                set_cliente_handoff(cliente["id"], False)
                return "Perfeito! Voltei com o atendimento automático. Posso te ajudar com agendamento, remarcação ou promoções."
            return "Seu atendimento está com nossa equipe humana. Assim que possível, alguém continua por aqui."

        if cliente["onboarding_status"] != "ativo":
            nome = self._extract_name(inbound_text)
            if nome:
                OnboardingService.finalize(cliente["id"], nome)
                return (
                    f"Prazer, {nome}! ✅ Seu cadastro foi concluído. "
                    "Posso te ajudar com: *agendar*, *promoções* ou *falar com atendente*."
                )
            return "Para continuar seu cadastro, me diga seu nome (ex: Gustavo Silva)."

        intent = self._detect_intent(inbound_text)
        if intent == "humano":
            set_cliente_handoff(cliente["id"], True)
            return "Certo, vou encaminhar seu atendimento para um atendente humano."

        conv_state = estado["estado"]
        dados = estado["dados"]

        if conv_state in {"aguardando_slot_agendar", "aguardando_slot_remarcar"}:
            slot_ids = [int(sid) for sid in dados.get("slots_ids", []) if str(sid).isdigit()]
            chosen_slot_id = self.scheduler.parse_choice_to_slot_id(inbound_text, slot_ids)
            if not chosen_slot_id:
                return "Não consegui identificar a opção. Responda com o número do horário desejado."

            ag = self.scheduler.book_slot(cliente["id"], chosen_slot_id)
            if not ag:
                aviso = "Esse horário acabou de ser ocupado. Vou te mostrar novas opções reais:\n"
                return aviso + self._prepare_slots_state(cliente["id"], "agendar")

            if conv_state == "aguardando_slot_remarcar":
                self.scheduler.cancel_other_future_appointments(cliente["id"], ag["id"])

            save_conversa_estado(cliente["id"], "idle", {})
            dt = datetime.fromisoformat(ag["data_hora"]).strftime("%d/%m às %H:%M")
            return f"Agendamento confirmado para {dt}. Te esperamos na barbearia! ✂️"

        if intent == "cancelar":
            ok = self.scheduler.cancel_next_appointment(cliente["id"])
            if ok:
                return "Seu próximo agendamento foi cancelado e o horário foi liberado. Quer que eu mostre novos horários?"
            return "Você não tem agendamento confirmado para cancelar no momento."

        if intent in {"agendar", "remarcar"}:
            return self._prepare_slots_state(cliente["id"], intent)

        if intent == "promocao":
            return "Promoção atual: combo corte + barba com 10% no pagamento via PIX até sexta-feira."

        if intent == "barbeiro":
            if cliente["barbeiro_favorito"]:
                return f"Seu barbeiro favorito é {cliente['barbeiro_favorito']}. Posso buscar horários com ele também."
            return "Ainda não tenho seu barbeiro favorito salvo. Se quiser, posso registrar isso para os próximos atendimentos."

        if intent == "cumprimento":
            nome_curto = (cliente["nome"] or "cliente").split()[0]
            return f"Olá, {nome_curto}! Posso te ajudar com agendamento, remarcação, cancelamento, promoções ou atendimento humano."

        # IA apenas como complemento em dúvidas gerais após fluxos determinísticos.
        max_ctx = int(os.getenv("OPENAI_MAX_CONTEXT_MESSAGES", "8"))
        ai_context = build_ai_context(cliente, phone, max_history=max_ctx)
        ai_reply = self.ai.generate_reply(inbound_text, ai_context)
        if ai_reply:
            return ai_reply

        return "Posso te ajudar com *agendar*, *remarcar*, *cancelar*, *promoções* ou *falar com atendente*."
