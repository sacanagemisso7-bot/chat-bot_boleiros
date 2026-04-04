import argparse
from datetime import datetime, timedelta

from db import get_conn, init_db, utc_now_iso


def reset_database(conn):
    conn.execute("DELETE FROM mensagens")
    conn.execute("DELETE FROM eventos_webhook")
    conn.execute("DELETE FROM conversa_estado")
    conn.execute("DELETE FROM agendamentos")
    conn.execute("DELETE FROM disponibilidade")
    conn.execute("DELETE FROM clientes")
    conn.commit()


def seed_clientes(conn):
    now = utc_now_iso()
    clientes = [
        ("Carlos Souza", "5511999991111", (datetime.utcnow() - timedelta(days=21)).isoformat(), "degradê com risca", "João", "Cliente VIP", "ativo", now, now),
        ("André Lima", "5511988882222", (datetime.utcnow() - timedelta(days=35)).isoformat(), "corte social", "Marcos", "Prefere sábado", "ativo", now, now),
        (None, "5511977773333", None, None, None, "Lead novo", "aguardando_nome", now, now),
    ]
    conn.executemany(
        """
        INSERT INTO clientes (nome, telefone, ultimo_corte, preferencia, barbeiro_favorito, observacoes, onboarding_status, criado_em, atualizado_em)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        clientes,
    )
    conn.commit()


def seed_disponibilidade(conn):
    inicio = datetime.utcnow().replace(minute=0, second=0, microsecond=0) + timedelta(days=1)
    barbeiros = ["João", "Marcos"]
    slots = []
    for dia in range(0, 4):
        for hora in [10, 11, 14, 15, 16, 18]:
            for barbeiro in barbeiros:
                dt = (inicio + timedelta(days=dia)).replace(hour=hora)
                slots.append((barbeiro, dt.isoformat(), 1, "corte", "slot seed"))
    conn.executemany(
        "INSERT INTO disponibilidade (barbeiro, data_hora, disponivel, servico, observacoes) VALUES (?, ?, ?, ?, ?)",
        slots,
    )
    conn.commit()


def seed_agendamentos(conn):
    cliente = conn.execute("SELECT id FROM clientes WHERE telefone = '5511999991111'").fetchone()
    slot = conn.execute("SELECT * FROM disponibilidade WHERE disponivel = 1 ORDER BY datetime(data_hora) LIMIT 1").fetchone()
    if not cliente or not slot:
        return
    now = utc_now_iso()
    conn.execute(
        "INSERT INTO agendamentos (cliente_id, data_hora, servico, status, criado_em, atualizado_em) VALUES (?, ?, ?, 'confirmado', ?, ?)",
        (cliente["id"], slot["data_hora"], slot["servico"], now, now),
    )
    conn.execute("UPDATE disponibilidade SET disponivel = 0 WHERE id = ?", (slot["id"],))
    conn.commit()


def main():
    parser = argparse.ArgumentParser(description="Seed local da barbearia")
    parser.add_argument("--reset", action="store_true", help="Limpa dados antes de popular")
    args = parser.parse_args()

    init_db()
    with get_conn() as conn:
        if args.reset:
            reset_database(conn)
        seed_clientes(conn)
        seed_disponibilidade(conn)
        seed_agendamentos(conn)

    print("Seed concluído com sucesso.")


if __name__ == "__main__":
    main()
