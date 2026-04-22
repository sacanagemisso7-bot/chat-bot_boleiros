const sqlite3 = require('sqlite3').verbose();

const DB_PATH = process.env.DB_PATH || 'barbearia.db';

const db = new sqlite3.Database(DB_PATH);

const now = new Date();
const daysAgo = (days) => new Date(now.getTime() - days * 24 * 60 * 60 * 1000).toISOString();
const daysAhead = (days) => {
  const d = new Date(now.getTime() + days * 24 * 60 * 60 * 1000);
  d.setMilliseconds(0);
  return d.toISOString();
};

db.serialize(() => {
  db.run(`
    CREATE TABLE IF NOT EXISTS clientes (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      nome TEXT NOT NULL,
      telefone TEXT UNIQUE NOT NULL,
      ultimo_corte TEXT,
      preferencia TEXT,
      barbeiro_favorito TEXT,
      observacoes TEXT
    )
  `);

  db.run(`
    CREATE TABLE IF NOT EXISTS agendamentos (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      cliente_id INTEGER NOT NULL,
      data_hora TEXT NOT NULL,
      servico TEXT NOT NULL,
      status TEXT NOT NULL DEFAULT 'confirmado',
      FOREIGN KEY (cliente_id) REFERENCES clientes(id)
    )
  `);

  db.run(`
    CREATE TABLE IF NOT EXISTS mensagens (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      cliente_id INTEGER,
      telefone TEXT NOT NULL,
      direcao TEXT NOT NULL CHECK (direcao IN ('entrada', 'saida')),
      conteudo TEXT NOT NULL,
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      FOREIGN KEY (cliente_id) REFERENCES clientes(id)
    )
  `);

  db.run(
    `
      INSERT OR REPLACE INTO clientes (id, nome, telefone, ultimo_corte, preferencia, barbeiro_favorito, observacoes)
      VALUES
        (1, 'Carlos Souza', 'whatsapp:+5511999991111', ?, 'degradê com risca', 'João', 'Cliente VIP'),
        (2, 'André Lima', 'whatsapp:+5511988882222', ?, 'corte social', 'Marcos', 'Prefere sábado')
    `,
    [daysAgo(21), daysAgo(35)],
  );

  db.run(
    `
      INSERT OR REPLACE INTO agendamentos (id, cliente_id, data_hora, servico, status)
      VALUES
        (1, 1, ?, 'corte + barba', 'confirmado')
    `,
    [daysAhead(2)],
  );
});

db.close(() => {
  console.log('Dados de exemplo inseridos.');
});
