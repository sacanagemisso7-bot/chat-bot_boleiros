const sqlite3 = require('sqlite3').verbose();
require('dotenv').config();

const DB_PATH = process.env.DB_PATH || 'barbearia.db';
const db = new sqlite3.Database(DB_PATH);

function limparNumero(numero = '') {
  return String(numero).replace(/\D/g, '');
}

function telefoneWhatsApp(numero) {
  return `whatsapp:${limparNumero(numero)}`;
}

function run(sql, params = []) {
  return new Promise((resolve, reject) => {
    db.run(sql, params, function onRun(err) {
      if (err) return reject(err);
      resolve({ lastID: this.lastID, changes: this.changes });
    });
  });
}

function closeDb() {
  return new Promise((resolve, reject) => {
    db.close((err) => {
      if (err) return reject(err);
      resolve();
    });
  });
}

const now = new Date();
const daysAgo = (days) => new Date(now.getTime() - days * 24 * 60 * 60 * 1000).toISOString();
const daysAheadAt = (days, hour, minute = 0) => {
  const d = new Date(now.getFullYear(), now.getMonth(), now.getDate() + days, hour, minute, 0, 0);
  return d.toISOString();
};

async function initSchema() {
  await run('PRAGMA foreign_keys = ON');

  await run(`
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

  await run(`
    CREATE TABLE IF NOT EXISTS agendamentos (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      cliente_id INTEGER NOT NULL,
      data_hora TEXT NOT NULL,
      servico TEXT NOT NULL,
      status TEXT NOT NULL DEFAULT 'confirmado',
      FOREIGN KEY (cliente_id) REFERENCES clientes(id)
    )
  `);

  await run(`
    CREATE TABLE IF NOT EXISTS mensagens (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      cliente_id INTEGER,
      telefone TEXT NOT NULL,
      direcao TEXT NOT NULL CHECK (direcao IN ('entrada', 'saida')),
      conteudo TEXT NOT NULL,
      provider_message_id TEXT,
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      FOREIGN KEY (cliente_id) REFERENCES clientes(id)
    )
  `);

  await run(`
    CREATE TABLE IF NOT EXISTS conversas_estado (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      telefone TEXT UNIQUE NOT NULL,
      estado TEXT NOT NULL DEFAULT 'idle',
      contexto_json TEXT,
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
  `);

  await run('CREATE INDEX IF NOT EXISTS idx_mensagens_telefone_created_at ON mensagens (telefone, created_at)');
  await run('CREATE INDEX IF NOT EXISTS idx_agendamentos_cliente_status_data ON agendamentos (cliente_id, status, data_hora)');
  await run('CREATE INDEX IF NOT EXISTS idx_conversas_estado_telefone ON conversas_estado (telefone)');
}

async function upsertCliente(cliente) {
  await run(
    `
      INSERT INTO clientes (id, nome, telefone, ultimo_corte, preferencia, barbeiro_favorito, observacoes)
      VALUES (?, ?, ?, ?, ?, ?, ?)
      ON CONFLICT(id) DO UPDATE SET
        nome = excluded.nome,
        telefone = excluded.telefone,
        ultimo_corte = excluded.ultimo_corte,
        preferencia = excluded.preferencia,
        barbeiro_favorito = excluded.barbeiro_favorito,
        observacoes = excluded.observacoes
    `,
    [
      cliente.id,
      cliente.nome,
      cliente.telefone,
      cliente.ultimo_corte,
      cliente.preferencia,
      cliente.barbeiro_favorito,
      cliente.observacoes,
    ],
  );

  await run(
    `
      INSERT INTO conversas_estado (telefone, estado, contexto_json)
      VALUES (?, 'idle', '{}')
      ON CONFLICT(telefone) DO UPDATE SET
        estado = 'idle',
        contexto_json = '{}',
        updated_at = CURRENT_TIMESTAMP
    `,
    [cliente.telefone],
  );
}

async function main() {
  await initSchema();

  await upsertCliente({
    id: 1,
    nome: 'Carlos Souza',
    telefone: telefoneWhatsApp('+5511999991111'),
    ultimo_corte: daysAgo(21),
    preferencia: 'degrade com risca',
    barbeiro_favorito: 'Joao',
    observacoes: 'Cliente VIP',
  });

  await upsertCliente({
    id: 2,
    nome: 'Andre Lima',
    telefone: telefoneWhatsApp('+5511988882222'),
    ultimo_corte: daysAgo(35),
    preferencia: 'corte social',
    barbeiro_favorito: 'Marcos',
    observacoes: 'Prefere sabado',
  });

  await run(
    `
      INSERT INTO agendamentos (id, cliente_id, data_hora, servico, status)
      VALUES (1, 1, ?, 'corte + barba', 'confirmado')
      ON CONFLICT(id) DO UPDATE SET
        cliente_id = excluded.cliente_id,
        data_hora = excluded.data_hora,
        servico = excluded.servico,
        status = excluded.status
    `,
    [daysAheadAt(2, 14, 0)],
  );

  await closeDb();
  console.log('Dados de exemplo inseridos.');
}

main().catch(async (error) => {
  console.error('Erro ao popular banco:', error);
  await closeDb().catch(() => {});
  process.exit(1);
});
