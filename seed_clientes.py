import sqlite3
from datetime import datetime, timedelta

DB_PATH = "barbearia.db"

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

cur.execute('''
CREATE TABLE IF NOT EXISTS clientes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL,
    telefone TEXT UNIQUE NOT NULL,
    ultimo_corte TEXT,
    preferencia TEXT,
    barbeiro_favorito TEXT,
    observacoes TEXT
)
''')
cur.execute('''
CREATE TABLE IF NOT EXISTS agendamentos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cliente_id INTEGER NOT NULL,
    data_hora TEXT NOT NULL,
    servico TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'confirmado',
    FOREIGN KEY (cliente_id) REFERENCES clientes(id)
)
''')

cur.execute(
    """
    INSERT OR REPLACE INTO clientes (id, nome, telefone, ultimo_corte, preferencia, barbeiro_favorito, observacoes)
    VALUES
      (1, 'Carlos Souza', 'whatsapp:+5511999991111', ?, 'degradê com risca', 'João', 'Cliente VIP'),
      (2, 'André Lima', 'whatsapp:+5511988882222', ?, 'corte social', 'Marcos', 'Prefere sábado')
    """,
    (
        (datetime.utcnow() - timedelta(days=21)).isoformat(),
        (datetime.utcnow() - timedelta(days=35)).isoformat(),
    ),
)

cur.execute(
    """
    INSERT OR REPLACE INTO agendamentos (id, cliente_id, data_hora, servico, status)
    VALUES
      (1, 1, ?, 'corte + barba', 'confirmado')
    """,
    ((datetime.utcnow() + timedelta(days=2)).replace(microsecond=0).isoformat(),),
)

conn.commit()
conn.close()
print("Dados de exemplo inseridos.")
