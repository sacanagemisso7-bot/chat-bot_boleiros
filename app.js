const express = require('express');
const sqlite3 = require('sqlite3').verbose();
require('dotenv').config();

const app = express();
app.use(express.urlencoded({ extended: false }));
app.use(express.json());

const DB_PATH = process.env.DB_PATH || 'barbearia.db';
const PORT = Number(process.env.PORT || 8000);

const WHATSAPP_TOKEN = process.env.WHATSAPP_TOKEN || '';
const WHATSAPP_PHONE_NUMBER_ID = process.env.WHATSAPP_PHONE_NUMBER_ID || '1047204661812681';
const WHATSAPP_BUSINESS_ID = process.env.WHATSAPP_BUSINESS_ID || '1972894139980996';
const WHATSAPP_VERIFY_TOKEN = process.env.WHATSAPP_VERIFY_TOKEN || 'verify_token_boleiros';
const NUMERO_TESTE = process.env.NUMERO_TESTE || '+15556327882';
const NUMERO_DESTINATARIO = process.env.NUMERO_DESTINATARIO || '+5542999845078';
const JANELA_HORARIOS = process.env.JANELA_HORARIOS || 'amanhã entre 10h e 19h';

function limparNumero(numero = '') {
  return numero.replace(/[\s()-]/g, '');
}

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
          provider_message_id TEXT,
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

function salvarMensagem({ clienteId = null, telefone, direcao, conteudo, providerMessageId = null }) {
  return new Promise((resolve, reject) => {
    withDb(async (db) => {
      try {
        await run(
          db,
          `INSERT INTO mensagens (cliente_id, telefone, direcao, conteudo, provider_message_id) VALUES (?, ?, ?, ?, ?)`,
          [clienteId, telefone, direcao, conteudo, providerMessageId],
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
            SELECT id, telefone, direcao, conteudo, provider_message_id, created_at
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

  if (!ultimo) return `Posso te recomendar um ${pref} com acabamento na navalha.`;

  const dataUltimo = new Date(ultimo);
  if (Number.isNaN(dataUltimo.getTime())) return `Quer repetir seu último estilo (${pref}) ou testar um degradê moderno?`;

  const dias = Math.floor((Date.now() - dataUltimo.getTime()) / (1000 * 60 * 60 * 24));
  if (dias >= 30) return 'Já passou do tempo ideal de manutenção. Quer agendar para esta semana?';
  if (dias >= 15) return 'Seu corte está na janela perfeita para manutenção leve.';
  return 'Seu visual ainda está em dia. Posso já deixar um horário reservado para a próxima quinzena.';
}

async function mensagemPersonalizada(phone, body) {
  const texto = (body || '').trim().toLowerCase();
  const cliente = await getClienteByPhone(phone);

  if (!cliente) {
    return {
      texto: 'Olá! 👋 Sou o assistente da barbearia. Ainda não encontrei seu cadastro. Me diga seu *nome* para eu iniciar seu atendimento personalizado.',
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
      texto: `${nome}, com base no seu perfil, temos combo de ${cliente.preferencia || 'corte + barba'} com 15% de desconto até sexta. Quer garantir?`,
      clienteId: cliente.id,
    };
  }

  return {
    texto: `Fala, ${nome}! ✂️ ${recomendacao} Seu barbeiro favorito é ${cliente.barbeiro_favorito || 'qualquer profissional da casa'}. Posso te ajudar com *agendar*, *remarcar* ou *promoção* hoje.`,
    clienteId: cliente.id,
  };
}

async function enviarMensagemWhatsApp(destino, texto) {
  if (!WHATSAPP_TOKEN) {
    throw new Error('WHATSAPP_TOKEN não configurado');
  }

  const endpoint = `https://graph.facebook.com/v22.0/${WHATSAPP_PHONE_NUMBER_ID}/messages`;
  const payload = {
    messaging_product: 'whatsapp',
    to: limparNumero(destino),
    type: 'text',
    text: { body: texto },
  };

  const response = await fetch(endpoint, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${WHATSAPP_TOKEN}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload),
  });

  const data = await response.json();

  if (!response.ok) {
    throw new Error(`Erro Meta API: ${response.status} - ${JSON.stringify(data)}`);
  }

  return data;
}

function extrairMensagemWhatsApp(payload) {
  try {
    const entry = payload.entry?.[0];
    const change = entry?.changes?.[0];
    const value = change?.value;
    const message = value?.messages?.[0];
    if (!message) return null;

    return {
      from: limparNumero(message.from),
      body: message.text?.body || '',
      messageId: message.id || null,
    };
  } catch (_e) {
    return null;
  }
}

app.get('/health', (_req, res) => {
  res.json({
    status: 'ok',
    provider: 'meta_whatsapp_cloud_api',
    businessId: WHATSAPP_BUSINESS_ID,
    phoneNumberId: WHATSAPP_PHONE_NUMBER_ID,
  });
});

app.get('/webhook', (req, res) => {
  const mode = req.query['hub.mode'];
  const token = req.query['hub.verify_token'];
  const challenge = req.query['hub.challenge'];

  if (mode === 'subscribe' && token === WHATSAPP_VERIFY_TOKEN) {
    return res.status(200).send(challenge);
  }

  return res.sendStatus(403);
});

app.post('/webhook', async (req, res) => {
  try {
    const inbound = extrairMensagemWhatsApp(req.body);
    if (!inbound) return res.sendStatus(200);

    const fromWhatsApp = `whatsapp:${inbound.from}`;
    const resposta = await mensagemPersonalizada(fromWhatsApp, inbound.body);

    await salvarMensagem({
      clienteId: resposta.clienteId,
      telefone: fromWhatsApp,
      direcao: 'entrada',
      conteudo: inbound.body,
      providerMessageId: inbound.messageId,
    });

    const envio = await enviarMensagemWhatsApp(inbound.from, resposta.texto);
    const saidaId = envio?.messages?.[0]?.id || null;

    await salvarMensagem({
      clienteId: resposta.clienteId,
      telefone: fromWhatsApp,
      direcao: 'saida',
      conteudo: resposta.texto,
      providerMessageId: saidaId,
    });

    return res.sendStatus(200);
  } catch (error) {
    console.error(error);
    return res.status(500).json({ detail: 'Erro interno', error: String(error.message || error) });
  }
});

app.post('/send-test', async (_req, res) => {
  try {
    const texto = `Teste automático ✅\nOrigem: ${limparNumero(NUMERO_TESTE)}\nDestino: ${limparNumero(NUMERO_DESTINATARIO)}\nData UTC: ${new Date().toISOString()}`;
    const envio = await enviarMensagemWhatsApp(NUMERO_DESTINATARIO, texto);

    await salvarMensagem({
      clienteId: null,
      telefone: `whatsapp:${limparNumero(NUMERO_DESTINATARIO)}`,
      direcao: 'saida',
      conteudo: texto,
      providerMessageId: envio?.messages?.[0]?.id || null,
    });

    return res.json({ ok: true, envio });
  } catch (error) {
    console.error(error);
    return res.status(500).json({ ok: false, detail: String(error.message || error) });
  }
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

initDb();

app.listen(PORT, '0.0.0.0', () => {
  console.log(`Servidor rodando na porta ${PORT}`);
});
