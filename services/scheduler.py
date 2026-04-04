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

    def get_slots_by_ids(self, slot_ids: list[int]) -> list[sqlite3.Row]:
        """Retorna slots na mesma ordem exibida ao cliente."""
        if not slot_ids:
            return []
        with get_conn() as conn:
            placeholders = ",".join("?" for _ in slot_ids)
            rows = conn.execute(
                f"SELECT * FROM disponibilidade WHERE id IN ({placeholders})",
                tuple(slot_ids),
            ).fetchall()
        by_id = {row["id"]: row for row in rows}
        return [by_id[sid] for sid in slot_ids if sid in by_id]

    def format_slots(self, slots: list[sqlite3.Row]) -> str:
        if not slots:
            return "No momento não temos horários livres próximos. Posso te encaminhar para um atendente humano."
        linhas = ["Estes são os próximos horários disponíveis:"]
        for idx, slot in enumerate(slots, start=1):
            dt = datetime.fromisoformat(slot["data_hora"]).strftime("%d/%m às %H:%M")
            linhas.append(f"{idx}) {dt} - {slot['barbeiro']} ({slot['servico']})")
        linhas.append("Me responda com o número da opção para confirmar.")
        return "\n".join(linhas)

    def parse_choice_to_slot_id(self, text: str, slot_ids: list[int]) -> Optional[int]:
        match = re.search(r"\d+", text)
        if not match:
            return None
        idx = int(match.group())
        if idx < 1 or idx > len(slot_ids):
            return None
        return slot_ids[idx - 1]

    def book_slot(self, cliente_id: int, slot_id: int) -> Optional[sqlite3.Row]:
        with get_conn() as conn:
            slot = conn.execute("SELECT * FROM disponibilidade WHERE id = ?", (slot_id,)).fetchone()
            if not slot or not slot["disponivel"]:
                return None

            now = utc_now_iso()
            conn.execute("UPDATE disponibilidade SET disponivel = 0 WHERE id = ? AND disponivel = 1", (slot_id,))
            if conn.total_changes == 0:
                return None

            conn.execute(
                """
                INSERT INTO agendamentos (cliente_id, data_hora, servico, status, criado_em, atualizado_em)
                VALUES (?, ?, ?, 'confirmado', ?, ?)
                """,
                (cliente_id, slot["data_hora"], slot["servico"], now, now),
            )
            ag = conn.execute("SELECT * FROM agendamentos WHERE id = last_insert_rowid()").fetchone()
            conn.commit()
            return ag


    def cancel_other_future_appointments(self, cliente_id: int, keep_agendamento_id: int) -> None:
        with get_conn() as conn:
            now = utc_now_iso()
            rows = conn.execute(
                """
                SELECT * FROM agendamentos
                WHERE cliente_id = ? AND status = 'confirmado' AND id != ? AND datetime(data_hora) >= datetime('now')
                """,
                (cliente_id, keep_agendamento_id),
            ).fetchall()
            for ag in rows:
                conn.execute("UPDATE agendamentos SET status = 'cancelado', atualizado_em = ? WHERE id = ?", (now, ag["id"]))
                conn.execute(
                    "UPDATE disponibilidade SET disponivel = 1 WHERE data_hora = ? AND servico = ?",
                    (ag["data_hora"], ag["servico"]),
                )
            conn.commit()

    def cancel_next_appointment(self, cliente_id: int) -> bool:
        with get_conn() as conn:
            ag = conn.execute(
                """
                SELECT * FROM agendamentos
                WHERE cliente_id = ? AND status = 'confirmado' AND datetime(data_hora) >= datetime('now')
                ORDER BY datetime(data_hora) ASC
                LIMIT 1
                """,
                (cliente_id,),
            ).fetchone()
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
