import re
import sqlite3
from datetime import datetime
from typing import Optional

from db import get_conn, utc_now_iso


class SchedulerService:
    def list_available_slots(self, limit: int = 5) -> list[sqlite3.Row]:
        with get_conn() as conn:
            return conn.execute(
                """
                SELECT * FROM disponibilidade
                WHERE disponivel = 1 AND datetime(data_hora) >= datetime('now')
                ORDER BY datetime(data_hora) ASC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

    def format_slots(self, slots: list[sqlite3.Row]) -> str:
        if not slots:
            return "No momento não temos horários livres próximos. Posso te encaminhar para um atendente humano."
        linhas = ["Estes são os próximos horários disponíveis:"]
        for idx, slot in enumerate(slots, start=1):
            dt = datetime.fromisoformat(slot["data_hora"]).strftime("%d/%m às %H:%M")
            linhas.append(f"{idx}) {dt} - {slot['barbeiro']} ({slot['servico']})")
        linhas.append("Me responda com o número da opção para confirmar.")
        return "\n".join(linhas)

    def parse_slot_choice(self, text: str, slots: list[sqlite3.Row]) -> Optional[sqlite3.Row]:
        match = re.search(r"\d+", text)
        if not match:
            return None
        idx = int(match.group())
        if idx < 1 or idx > len(slots):
            return None
        return slots[idx - 1]

    def book_slot(self, cliente_id: int, slot_id: int) -> Optional[sqlite3.Row]:
        with get_conn() as conn:
            slot = conn.execute("SELECT * FROM disponibilidade WHERE id = ?", (slot_id,)).fetchone()
            if not slot or not slot["disponivel"]:
                return None

            now = utc_now_iso()
            conn.execute("UPDATE disponibilidade SET disponivel = 0 WHERE id = ? AND disponivel = 1", (slot_id,))
            if conn.total_changes == 0:
                return None

            existing = conn.execute(
                "SELECT * FROM agendamentos WHERE cliente_id = ? AND status = 'confirmado' ORDER BY datetime(data_hora) DESC LIMIT 1",
                (cliente_id,),
            ).fetchone()

            if existing and existing["data_hora"] == slot["data_hora"]:
                conn.commit()
                return existing

            conn.execute(
                """
                INSERT INTO agendamentos (cliente_id, data_hora, servico, status, criado_em, atualizado_em)
                VALUES (?, ?, ?, 'confirmado', ?, ?)
                """,
                (cliente_id, slot["data_hora"], slot["servico"], now, now),
            )
            ag = conn.execute(
                "SELECT * FROM agendamentos WHERE id = last_insert_rowid()"
            ).fetchone()
            conn.commit()
            return ag

    def get_next_appointment(self, cliente_id: int) -> Optional[sqlite3.Row]:
        with get_conn() as conn:
            return conn.execute(
                """
                SELECT * FROM agendamentos
                WHERE cliente_id = ? AND status = 'confirmado' AND datetime(data_hora) >= datetime('now')
                ORDER BY datetime(data_hora) ASC
                LIMIT 1
                """,
                (cliente_id,),
            ).fetchone()

    def cancel_next_appointment(self, cliente_id: int) -> bool:
        with get_conn() as conn:
            ag = self.get_next_appointment(cliente_id)
            if not ag:
                return False
            now = utc_now_iso()
            conn.execute("UPDATE agendamentos SET status = 'cancelado', atualizado_em = ? WHERE id = ?", (now, ag["id"]))
            conn.execute(
                "UPDATE disponibilidade SET disponivel = 1 WHERE data_hora = ? AND servico = ?",
                (ag["data_hora"], ag["servico"]),
            )
            conn.commit()
            return True
