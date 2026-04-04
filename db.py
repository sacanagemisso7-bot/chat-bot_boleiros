import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Iterator, Optional

DB_PATH = os.getenv("DB_PATH", "barbearia.db")


def utc_now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat()


@contextmanager
def get_conn() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
    finally:
        conn.close()


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, ddl: str) -> None:
    cols = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")


def init_db() -> None:
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS clientes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT,
                telefone TEXT UNIQUE NOT NULL,
                ultimo_corte TEXT,
                preferencia TEXT,
                barbeiro_favorito TEXT,
                observacoes TEXT,
                onboarding_status TEXT NOT NULL DEFAULT 'aguardando_nome',
                criado_em TEXT NOT NULL,
                atualizado_em TEXT NOT NULL
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS agendamentos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cliente_id INTEGER NOT NULL,
                data_hora TEXT NOT NULL,
                servico TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'confirmado',
                criado_em TEXT NOT NULL,
                atualizado_em TEXT NOT NULL,
                FOREIGN KEY (cliente_id) REFERENCES clientes(id)
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS mensagens (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cliente_id INTEGER,
                telefone TEXT NOT NULL,
                direcao TEXT NOT NULL CHECK (direcao IN ('in', 'out')),
                mensagem TEXT NOT NULL,
                tipo TEXT NOT NULL DEFAULT 'text',
                meta_message_id TEXT,
                criada_em TEXT NOT NULL,
                FOREIGN KEY (cliente_id) REFERENCES clientes(id)
            )
            """
        )
        cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_mensagens_meta_id ON mensagens(meta_message_id) WHERE meta_message_id IS NOT NULL")
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS eventos_webhook (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                meta_event_id TEXT UNIQUE,
                payload_json TEXT NOT NULL,
                criado_em TEXT NOT NULL
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS disponibilidade (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                barbeiro TEXT NOT NULL,
                data_hora TEXT NOT NULL,
                disponivel INTEGER NOT NULL DEFAULT 1,
                servico TEXT NOT NULL,
                observacoes TEXT
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS conversa_estado (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cliente_id INTEGER UNIQUE NOT NULL,
                estado TEXT NOT NULL DEFAULT 'idle',
                dados_json TEXT,
                atendimento_humano INTEGER NOT NULL DEFAULT 0,
                atualizado_em TEXT NOT NULL,
                FOREIGN KEY (cliente_id) REFERENCES clientes(id)
            )
            """
        )

        # Migração da base antiga
        _ensure_column(conn, "clientes", "onboarding_status", "TEXT NOT NULL DEFAULT 'ativo'")
        _ensure_column(conn, "clientes", "criado_em", "TEXT")
        _ensure_column(conn, "clientes", "atualizado_em", "TEXT")
        _ensure_column(conn, "agendamentos", "criado_em", "TEXT")
        _ensure_column(conn, "agendamentos", "atualizado_em", "TEXT")
        now = utc_now_iso()
        conn.execute("UPDATE clientes SET criado_em = COALESCE(criado_em, ?), atualizado_em = COALESCE(atualizado_em, ?)", (now, now))
        conn.execute("UPDATE agendamentos SET criado_em = COALESCE(criado_em, ?), atualizado_em = COALESCE(atualizado_em, ?)", (now, now))
        conn.commit()


def normalizar_numero(numero: str) -> str:
    return "".join(ch for ch in numero if ch.isdigit())


def get_cliente_by_phone(phone: str) -> Optional[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute("SELECT * FROM clientes WHERE telefone = ?", (phone,)).fetchone()


def create_cliente_placeholder(phone: str) -> sqlite3.Row:
    now = utc_now_iso()
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO clientes (nome, telefone, onboarding_status, criado_em, atualizado_em)
            VALUES (NULL, ?, 'aguardando_nome', ?, ?)
            """,
            (phone, now, now),
        )
        conn.commit()
        return conn.execute("SELECT * FROM clientes WHERE telefone = ?", (phone,)).fetchone()


def update_cliente_nome(cliente_id: int, nome: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE clientes SET nome = ?, onboarding_status = 'ativo', atualizado_em = ? WHERE id = ?",
            (nome.strip(), utc_now_iso(), cliente_id),
        )
        conn.commit()


def set_cliente_handoff(cliente_id: int, ativo: bool) -> None:
    with get_conn() as conn:
        now = utc_now_iso()
        conn.execute(
            """
            INSERT INTO conversa_estado (cliente_id, estado, atendimento_humano, atualizado_em)
            VALUES (?, 'idle', ?, ?)
            ON CONFLICT(cliente_id) DO UPDATE SET atendimento_humano = excluded.atendimento_humano, atualizado_em = excluded.atualizado_em
            """,
            (cliente_id, 1 if ativo else 0, now),
        )
        conn.commit()


def get_conversa_estado(cliente_id: int) -> dict[str, Any]:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM conversa_estado WHERE cliente_id = ?", (cliente_id,)).fetchone()
        if not row:
            return {"estado": "idle", "dados": {}, "atendimento_humano": False}
        dados = json.loads(row["dados_json"] or "{}")
        return {"estado": row["estado"], "dados": dados, "atendimento_humano": bool(row["atendimento_humano"])}


def save_conversa_estado(cliente_id: int, estado: str, dados: Optional[dict[str, Any]] = None) -> None:
    with get_conn() as conn:
        now = utc_now_iso()
        conn.execute(
            """
            INSERT INTO conversa_estado (cliente_id, estado, dados_json, atualizado_em)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(cliente_id) DO UPDATE SET estado = excluded.estado, dados_json = excluded.dados_json, atualizado_em = excluded.atualizado_em
            """,
            (cliente_id, estado, json.dumps(dados or {}, ensure_ascii=False), now),
        )
        conn.commit()


def save_message(cliente_id: Optional[int], telefone: str, direcao: str, mensagem: str, tipo: str = "text", meta_message_id: Optional[str] = None) -> bool:
    with get_conn() as conn:
        try:
            conn.execute(
                """
                INSERT INTO mensagens (cliente_id, telefone, direcao, mensagem, tipo, meta_message_id, criada_em)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (cliente_id, telefone, direcao, mensagem, tipo, meta_message_id, utc_now_iso()),
            )
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False


def list_recent_messages(telefone: str, limit: int = 8) -> list[sqlite3.Row]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM mensagens WHERE telefone = ? ORDER BY id DESC LIMIT ?",
            (telefone, limit),
        ).fetchall()
        return list(reversed(rows))


def save_webhook_event(meta_event_id: Optional[str], payload: dict[str, Any]) -> bool:
    with get_conn() as conn:
        try:
            conn.execute(
                "INSERT INTO eventos_webhook (meta_event_id, payload_json, criado_em) VALUES (?, ?, ?)",
                (meta_event_id, json.dumps(payload, ensure_ascii=False), utc_now_iso()),
            )
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False
