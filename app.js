const express = require('express');
const sqlite3 = require('sqlite3').verbose();
const { MessagingResponse } = require('twilio').twiml;
const twilio = require('twilio');
require('dotenv').config();

const app = express();
app.use(express.urlencoded({ extended: false }));
app.use(express.json());

const DB_PATH = process.env.DB_PATH || 'barbearia.db';
const TWILIO_AUTH_TOKEN = process.env.TWILIO_AUTH_TOKEN || '';
const TWILIO_VALIDATE_REQUESTS = (process.env.TWILIO_VALIDATE_REQUESTS || 'false').toLowerCase() === 'true';
const JANELA_HORARIOS = process.env.JANELA_HORARIOS || 'amanhã entre 10h e 19h';

function withDb(callback) {
  const db = new sqlite3.Database(DB_PATH);
  callback(db);
}

function run(db, sql, params = []) {
  return new Promise((resolve, reject) => {
    db.run(sql, params, function onRun(err) {
      if (err) return reject(err);
      resolve({ lastID: this.lastID, changes: this.changes });
    });
  });
}

function get(db, sql, params = []) {
  return new Promise((resolve, reject) => {
    db.get(sql, params, (err, row) => {
      if (err) return reject(err);
      resolve(row || null);
    });
  });
}

function all(db, sql, params = []) {
  return new Promise((resolve, reject) => {
    db.all(sql, params, (err, rows) => {
      if (err) return reject(err);
      resolve(rows || []);
    });
  });
}

function initDb() {
  withDb((db) => {
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
    });
    db.close();
  });
}

function getClienteByPhone(phone) {
  return new Promise((resolve, reject) => {
    withDb(async (db) => {
      try {
        const row = await get(db, 'SELECT * FROM clientes WHERE telefone = ?', [phone]);
        db.close();
        resolve(row);
      } catch (err) {
        db.close();
        reject(err);
      }
    });
  });
}

function getProximoAgendamento(clienteId) {
  return new Promise((resolve, reject) => {
    withDb(async (db) => {
      try {
        const row = await get(
          db,
          `
            SELECT * FROM agendamentos
            WHERE cliente_id = ? AND status = 'confirmado' AND datetime(data_hora) >= datetime('now')
            ORDER BY datetime(data_hora) ASC
            LIMIT 1
          `,
          [clienteId],
        );
        db.close();
        resolve(row);
      } catch (err) {
        db.close();
        reject(err);
      }
    });
  });
}

function marcarAgendamentoComoRemarcacao(clienteId) {
  return new Promise((resolve, reject) => {
    withDb(async (db) => {
      try {
        const result = await run(
          db,
          `
            UPDATE agendamentos
            SET status = 'remarcacao_solicitada'
            WHERE id = (
              SELECT id FROM agendamentos
              WHERE cliente_id = ? AND status = 'confirmado' AND datetime(data_hora) >= datetime('now')
              ORDER BY datetime(data_hora) ASC
              LIMIT 1
            )
          `,
          [clienteId],
        );
        db.close();
        resolve(result.changes > 0);
      } catch (err) {
        db.close();
        reject(err);
      }
    });
  });
}

function salvarMensagem({ clienteId = null, telefone, direcao, conteudo }) {
  return new Promise((resolve, reject) => {
    withDb(async (db) => {
      try {
        await run(
          db,
          `INSERT INTO mensagens (cliente_id, telefone, direcao, conteudo) VALUES (?, ?, ?, ?)`,
          [clienteId, telefone, direcao, conteudo],
        );
        db.close();
        resolve();
      } catch (err) {
        db.close();
        reject(err);
      }
    });
  });
}

function listarHistoricoPorTelefone(telefone, limit = 20) {
  return new Promise((resolve, reject) => {
    withDb(async (db) => {
      try {
        const rows = await all(
          db,
          `
            SELECT id, telefone, direcao, conteudo, created_at
            FROM mensagens
            WHERE telefone = ?
            ORDER BY datetime(created_at) DESC
            LIMIT ?
          `,
          [telefone, limit],
        );
        db.close();
        resolve(rows);
      } catch (err) {
        db.close();
        reject(err);
      }
    });
  });
}

function getRecomendacao(cliente) {
  const ultimo = cliente.ultimo_corte;
  const pref = cliente.preferencia || 'corte social';

  if (!ultimo) {
    return `Posso te recomendar um ${pref} com acabamento na navalha.`;
  }

  const dataUltimo = new Date(ultimo);
  if (Number.isNaN(dataUltimo.getTime())) {
    return `Quer repetir seu último estilo (${pref}) ou testar um degradê moderno?`;
  }

  const diffMs = Date.now() - dataUltimo.getTime();
  const dias = Math.floor(diffMs / (1000 * 60 * 60 * 24));

  if (dias >= 30) {
    return 'Já passou do tempo ideal de manutenção. Quer agendar para esta semana?';
  }
  if (dias >= 15) {
    return 'Seu corte está na janela perfeita para manutenção leve.';
  }
  return 'Seu visual ainda está em dia. Posso já deixar um horário reservado para a próxima quinzena.';
}

async function mensagemPersonalizada(phone, body) {
  const texto = (body || '').trim().toLowerCase();
  const cliente = await getClienteByPhone(phone);

  if (!cliente) {
    return {
      texto:
        'Olá! 👋 Sou o assistente da barbearia. Ainda não encontrei seu cadastro. Me diga seu *nome* para eu iniciar seu atendimento personalizado.',
      clienteId: null,
    };
  }

  const nome = cliente.nome.split(' ')[0];
  const recomendacao = getRecomendacao(cliente);
  const proximo = await getProximoAgendamento(cliente.id);

  if (texto.includes('remarcar')) {
    if (!proximo) {
      return {
        texto: `${nome}, não encontrei agendamento ativo para remarcar. Posso te oferecer um novo horário (${JANELA_HORARIOS}).`,
        clienteId: cliente.id,
      };
    }

    await marcarAgendamentoComoRemarcacao(cliente.id);
    return {
      texto: `${nome}, pedido de remarcação recebido ✅. Tenho opções ${JANELA_HORARIOS}. Prefere manhã, tarde ou noite?`,
      clienteId: cliente.id,
    };
  }

  if (texto.includes('horário') || texto.includes('agendar')) {
    if (proximo) {
      const data = new Date(proximo.data_hora);
      const dataFmt = `${String(data.getDate()).padStart(2, '0')}/${String(data.getMonth() + 1).padStart(2, '0')} às ${String(data.getHours()).padStart(2, '0')}:${String(data.getMinutes()).padStart(2, '0')}`;
      return {
        texto: `${nome}, seu próximo horário já está marcado para ${dataFmt}. Se quiser alterar, me responda com *remarcar*.`,
        clienteId: cliente.id,
      };
    }
    return {
      texto: `${nome}, tenho horários ${JANELA_HORARIOS}. Prefere manhã, tarde ou noite?`,
      clienteId: cliente.id,
    };
  }

  if (texto.includes('promo') || texto.includes('promoção')) {
    return {
      texto:
        `${nome}, com base no seu perfil, temos combo de ${cliente.preferencia || 'corte + barba'} ` +
        'com 15% de desconto até sexta. Quer garantir?',
      clienteId: cliente.id,
    };
  }

  return {
    texto:
      `Fala, ${nome}! ✂️ ${recomendacao} ` +
      `Seu barbeiro favorito é ${cliente.barbeiro_favorito || 'qualquer profissional da casa'}. ` +
      'Posso te ajudar com *agendar*, *remarcar* ou *promoção* hoje.',
    clienteId: cliente.id,
  };
}

function validarAssinaturaTwilio(requestUrl, formData, signature) {
  if (!TWILIO_VALIDATE_REQUESTS) return true;
  if (!TWILIO_AUTH_TOKEN) return false;
  return twilio.validateRequest(TWILIO_AUTH_TOKEN, signature, requestUrl, formData);
}

app.get('/health', (_req, res) => {
  res.type('text/plain').send('ok');
});

app.get('/clientes/:telefone/historico', async (req, res) => {
  try {
    const telefone = decodeURIComponent(req.params.telefone);
    const limit = Number(req.query.limit || 20);
    const historico = await listarHistoricoPorTelefone(telefone, limit > 0 ? Math.min(limit, 100) : 20);
    res.json({ telefone, total: historico.length, mensagens: historico });
  } catch (error) {
    console.error(error);
    res.status(500).json({ detail: 'Erro interno' });
  }
});

app.post('/whatsapp', async (req, res) => {
  try {
    const from = req.body.From;
    const body = req.body.Body || '';

    if (!from) {
      return res.status(400).json({ detail: 'Campo From é obrigatório' });
    }

    if (TWILIO_VALIDATE_REQUESTS) {
      const signature = req.header('X-Twilio-Signature');
      if (!signature) {
        return res.status(403).json({ detail: 'Assinatura Twilio ausente' });
      }

      const host = req.get('host');
      const requestUrl = `${req.protocol}://${host}${req.originalUrl}`;
      const ok = validarAssinaturaTwilio(requestUrl, { From: from, Body: body }, signature);
      if (!ok) {
        return res.status(403).json({ detail: 'Assinatura Twilio inválida' });
      }
    }

    const resposta = await mensagemPersonalizada(from, body);

    await salvarMensagem({
      clienteId: resposta.clienteId,
      telefone: from,
      direcao: 'entrada',
      conteudo: body,
    });

    await salvarMensagem({
      clienteId: resposta.clienteId,
      telefone: from,
      direcao: 'saida',
      conteudo: resposta.texto,
    });

    const twiml = new MessagingResponse();
    twiml.message(resposta.texto);

    res.type('text/xml').send(twiml.toString());
  } catch (error) {
    console.error(error);
    res.status(500).json({ detail: 'Erro interno' });
  }
});

initDb();

const PORT = Number(process.env.PORT || 8000);
app.listen(PORT, '0.0.0.0', () => {
  console.log(`Servidor rodando na porta ${PORT}`);
});
