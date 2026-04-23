const express = require('express');
const sqlite3 = require('sqlite3').verbose();
require('dotenv').config();

const app = express();
app.use(express.urlencoded({ extended: false }));
app.use(express.json());

const DB_PATH = process.env.DB_PATH || 'barbearia.db';
const PORT = Number(process.env.PORT || 8000);

const WHATSAPP_TOKEN = process.env.WHATSAPP_TOKEN || '';
const WHATSAPP_PHONE_NUMBER_ID = process.env.WHATSAPP_PHONE_NUMBER_ID || '';
const WHATSAPP_BUSINESS_ID = process.env.WHATSAPP_BUSINESS_ID || '';
const WHATSAPP_VERIFY_TOKEN = process.env.WHATSAPP_VERIFY_TOKEN || '';
const NUMERO_DESTINATARIO = process.env.NUMERO_DESTINATARIO || '';
const JANELA_HORARIOS = process.env.JANELA_HORARIOS || 'entre 10h e 19h';
const ADMIN_TOKEN = process.env.ADMIN_TOKEN || '';

const ESTADOS = {
  IDLE: 'idle',
  AGUARDANDO_NOME: 'aguardando_nome',
  AGUARDANDO_DATA_AGENDAMENTO: 'aguardando_data_agendamento',
  AGUARDANDO_HORARIO_AGENDAMENTO: 'aguardando_horario_agendamento',
  AGUARDANDO_CONFIRMACAO_AGENDAMENTO: 'aguardando_confirmacao_agendamento',
  AGUARDANDO_NOVA_DATA_REMARCACAO: 'aguardando_nova_data_remarcacao',
  AGUARDANDO_NOVO_HORARIO_REMARCACAO: 'aguardando_novo_horario_remarcacao',
  AGUARDANDO_CONFIRMACAO_REMARCACAO: 'aguardando_confirmacao_remarcacao',
};

function limparNumero(numero = '') {
  return String(numero).replace(/\D/g, '');
}

function normalizarTelefoneWhatsApp(telefone = '') {
  const digits = limparNumero(String(telefone).replace(/^whatsapp:/i, ''));
  return digits ? `whatsapp:${digits}` : '';
}

function telefonesCompatibilidade(telefone = '') {
  const digits = limparNumero(telefone);
  return [`whatsapp:${digits}`, `whatsapp:+${digits}`];
}

function openDb() {
  return new sqlite3.Database(DB_PATH);
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

function closeDb(db) {
  return new Promise((resolve, reject) => {
    db.close((err) => {
      if (err) return reject(err);
      resolve();
    });
  });
}

async function withDb(callback) {
  const db = openDb();
  try {
    await run(db, 'PRAGMA foreign_keys = ON');
    return await callback(db);
  } finally {
    await closeDb(db);
  }
}

async function initDb() {
  await withDb(async (db) => {
    await run(
      db,
      `
        CREATE TABLE IF NOT EXISTS clientes (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          nome TEXT NOT NULL,
          telefone TEXT UNIQUE NOT NULL,
          ultimo_corte TEXT,
          preferencia TEXT,
          barbeiro_favorito TEXT,
          observacoes TEXT
        )
      `,
    );

    await run(
      db,
      `
        CREATE TABLE IF NOT EXISTS agendamentos (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          cliente_id INTEGER NOT NULL,
          data_hora TEXT NOT NULL,
          servico TEXT NOT NULL,
          status TEXT NOT NULL DEFAULT 'confirmado',
          FOREIGN KEY (cliente_id) REFERENCES clientes(id)
        )
      `,
    );

    await run(
      db,
      `
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
      `,
    );

    await run(
      db,
      `
        CREATE TABLE IF NOT EXISTS conversas_estado (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          telefone TEXT UNIQUE NOT NULL,
          estado TEXT NOT NULL DEFAULT 'idle',
          contexto_json TEXT,
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
      `,
    );

    await run(db, 'CREATE INDEX IF NOT EXISTS idx_mensagens_telefone_created_at ON mensagens (telefone, created_at)');
    await run(db, 'CREATE INDEX IF NOT EXISTS idx_agendamentos_cliente_status_data ON agendamentos (cliente_id, status, data_hora)');
    await run(db, 'CREATE INDEX IF NOT EXISTS idx_conversas_estado_telefone ON conversas_estado (telefone)');
  });
}

function parseContexto(contextoJson) {
  if (!contextoJson) return {};
  try {
    const parsed = JSON.parse(contextoJson);
    return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed : {};
  } catch (_err) {
    return {};
  }
}

async function getEstadoConversa(telefone) {
  const phone = normalizarTelefoneWhatsApp(telefone);
  return withDb(async (db) => {
    const row = await get(db, 'SELECT * FROM conversas_estado WHERE telefone = ?', [phone]);
    if (!row) return { telefone: phone, estado: ESTADOS.IDLE, contexto: {} };
    return { telefone: phone, estado: row.estado || ESTADOS.IDLE, contexto: parseContexto(row.contexto_json) };
  });
}

async function setEstadoConversa(telefone, estado, contexto = {}) {
  const phone = normalizarTelefoneWhatsApp(telefone);
  await withDb(async (db) => {
    await run(
      db,
      `
        INSERT INTO conversas_estado (telefone, estado, contexto_json, updated_at)
        VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(telefone) DO UPDATE SET
          estado = excluded.estado,
          contexto_json = excluded.contexto_json,
          updated_at = CURRENT_TIMESTAMP
      `,
      [phone, estado, JSON.stringify(contexto || {})],
    );
  });
}

async function resetEstadoConversa(telefone) {
  await setEstadoConversa(telefone, ESTADOS.IDLE, {});
}

async function getClienteByPhone(telefone) {
  const [phone, phoneLegacy] = telefonesCompatibilidade(telefone);
  return withDb(async (db) => {
    const cliente = await get(db, 'SELECT * FROM clientes WHERE telefone = ? LIMIT 1', [phone]);
    if (cliente) return cliente;

    const legado = await get(db, 'SELECT * FROM clientes WHERE telefone = ? LIMIT 1', [phoneLegacy]);
    if (legado) {
      await run(db, 'UPDATE clientes SET telefone = ? WHERE id = ?', [phone, legado.id]);
      legado.telefone = phone;
    }

    return legado;
  });
}

async function criarCliente({ nome, telefone }) {
  const phone = normalizarTelefoneWhatsApp(telefone);
  const existente = await getClienteByPhone(phone);
  if (existente) return existente;

  return withDb(async (db) => {
    await run(
      db,
      `
        INSERT OR IGNORE INTO clientes
          (nome, telefone, ultimo_corte, preferencia, barbeiro_favorito, observacoes)
        VALUES (?, ?, NULL, NULL, NULL, NULL)
      `,
      [nome, phone],
    );

    return get(db, 'SELECT * FROM clientes WHERE telefone = ?', [phone]);
  });
}

async function getProximoAgendamento(clienteId) {
  return withDb(async (db) => {
    return get(
      db,
      `
        SELECT * FROM agendamentos
        WHERE cliente_id = ? AND status = 'confirmado' AND data_hora >= ?
        ORDER BY data_hora ASC
        LIMIT 1
      `,
      [clienteId, new Date().toISOString()],
    );
  });
}

async function getAgendamentoById(agendamentoId, clienteId) {
  return withDb(async (db) => {
    return get(
      db,
      `
        SELECT * FROM agendamentos
        WHERE id = ? AND cliente_id = ? AND status = 'confirmado'
        LIMIT 1
      `,
      [agendamentoId, clienteId],
    );
  });
}

async function horarioOcupado(dataHoraIso, ignorarAgendamentoId = null) {
  return withDb(async (db) => {
    const params = [dataHoraIso];
    let filtroIgnorar = '';
    if (ignorarAgendamentoId) {
      filtroIgnorar = 'AND id <> ?';
      params.push(ignorarAgendamentoId);
    }

    const row = await get(
      db,
      `
        SELECT id FROM agendamentos
        WHERE status = 'confirmado' AND data_hora = ?
        ${filtroIgnorar}
        LIMIT 1
      `,
      params,
    );
    return Boolean(row);
  });
}

async function criarAgendamento(clienteId, dataHoraIso, servico = 'corte') {
  return withDb(async (db) => {
    return run(
      db,
      `
        INSERT INTO agendamentos (cliente_id, data_hora, servico, status)
        VALUES (?, ?, ?, 'confirmado')
      `,
      [clienteId, dataHoraIso, servico],
    );
  });
}

async function remarcarAgendamento(agendamentoId, clienteId, novaDataHoraIso) {
  // MVP: atualizamos o mesmo registro para manter um unico agendamento ativo.
  return withDb(async (db) => {
    return run(
      db,
      `
        UPDATE agendamentos
        SET data_hora = ?, status = 'confirmado'
        WHERE id = ? AND cliente_id = ? AND status = 'confirmado'
      `,
      [novaDataHoraIso, agendamentoId, clienteId],
    );
  });
}

async function salvarMensagem({ clienteId = null, telefone, direcao, conteudo, providerMessageId = null }) {
  const phone = normalizarTelefoneWhatsApp(telefone);
  return withDb(async (db) => {
    await run(
      db,
      `
        INSERT INTO mensagens (cliente_id, telefone, direcao, conteudo, provider_message_id)
        VALUES (?, ?, ?, ?, ?)
      `,
      [clienteId, phone, direcao, conteudo, providerMessageId],
    );
  });
}

async function listarHistoricoPorTelefone(telefone, limit = 20) {
  const [phone, phoneLegacy] = telefonesCompatibilidade(telefone);
  return withDb(async (db) => {
    return all(
      db,
      `
        SELECT id, cliente_id, telefone, direcao, conteudo, provider_message_id, created_at
        FROM mensagens
        WHERE telefone IN (?, ?)
        ORDER BY datetime(created_at) DESC
        LIMIT ?
      `,
      [phone, phoneLegacy, limit],
    );
  });
}

function normalizarTexto(texto = '') {
  return String(texto)
    .trim()
    .toLowerCase()
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '');
}

function primeiroNome(cliente) {
  return String(cliente.nome || '').trim().split(/\s+/)[0] || 'cliente';
}

function capitalizarNome(nome) {
  return nome
    .trim()
    .replace(/\s+/g, ' ')
    .split(' ')
    .map((parte) => parte.charAt(0).toUpperCase() + parte.slice(1).toLowerCase())
    .join(' ');
}

function extrairNome(texto) {
  let nome = String(texto || '').trim().replace(/\s+/g, ' ');
  nome = nome.replace(/^(meu nome (e|eh)|sou|me chamo|chamo)\s+/i, '').trim();

  const letras = nome.match(/\p{L}/gu) || [];
  if (letras.length < 2 || nome.length > 80 || /\d/.test(nome)) return null;
  return capitalizarNome(nome);
}

function menuPrincipal(nome = '') {
  const saudacao = nome ? `Fala, ${nome}!` : 'Ola!';
  return `${saudacao} Posso te ajudar com:\n1. Agendar horario\n2. Remarcar horario\n3. Ver promocao\n\nResponda com *agendar*, *remarcar* ou *promocao*.`;
}

function getRecomendacao(cliente) {
  const ultimo = cliente.ultimo_corte;
  const pref = cliente.preferencia || 'corte social';

  if (!ultimo) return `Posso te recomendar um ${pref} com acabamento na navalha.`;

  const dataUltimo = new Date(ultimo);
  if (Number.isNaN(dataUltimo.getTime())) return `Quer repetir seu ultimo estilo (${pref}) ou testar um degrade moderno?`;

  const dias = Math.floor((Date.now() - dataUltimo.getTime()) / (1000 * 60 * 60 * 24));
  if (dias >= 30) return 'Ja passou do tempo ideal de manutencao. Quer agendar para esta semana?';
  if (dias >= 15) return 'Seu corte esta na janela perfeita para manutencao leve.';
  return 'Seu visual ainda esta em dia. Posso deixar um horario reservado para a proxima quinzena.';
}

function isPedidoAgendamento(texto) {
  const t = normalizarTexto(texto);
  return /\b(agendar|agenda|marcar|reservar|horario|cortar|corte)\b/.test(t);
}

function isPedidoRemarcacao(texto) {
  const t = normalizarTexto(texto);
  return /\b(remarcar|remarcacao|alterar|mudar|trocar)\b/.test(t);
}

function isPedidoPromocao(texto) {
  const t = normalizarTexto(texto);
  return /\b(promo|promocao|desconto|combo|oferta)\b/.test(t);
}

function isPedidoMenu(texto) {
  const t = normalizarTexto(texto);
  return /\b(oi|ola|menu|opcoes|ajuda|bom dia|boa tarde|boa noite)\b/.test(t);
}

function isCancelamento(texto) {
  const t = normalizarTexto(texto).replace(/[.!?]/g, '').trim();
  return ['cancelar', 'cancela', 'sair', 'menu', 'voltar'].includes(t);
}

function isConfirmacao(texto) {
  const t = normalizarTexto(texto).replace(/[.!?]/g, '').trim();
  return ['sim', 's', 'ok', 'okay', 'confirmar', 'confirmo', 'pode ser', 'fechado', 'isso'].includes(t);
}

function isNegacao(texto) {
  const t = normalizarTexto(texto).replace(/[.!?]/g, '').trim();
  return ['nao', 'n', 'cancelar', 'cancela', 'deixa', 'nao quero'].includes(t);
}

function addDias(data, dias) {
  return new Date(data.getFullYear(), data.getMonth(), data.getDate() + dias);
}

function inicioDoDia(data) {
  return new Date(data.getFullYear(), data.getMonth(), data.getDate());
}

function isoDateLocal(data) {
  return `${data.getFullYear()}-${String(data.getMonth() + 1).padStart(2, '0')}-${String(data.getDate()).padStart(2, '0')}`;
}

function dataLocalFromIsoDate(isoDate) {
  const [ano, mes, dia] = String(isoDate).split('-').map(Number);
  if (!ano || !mes || !dia) return null;
  return new Date(ano, mes - 1, dia);
}

function formatarDataDate(data) {
  return `${String(data.getDate()).padStart(2, '0')}/${String(data.getMonth() + 1).padStart(2, '0')}`;
}

function parseData(texto) {
  const t = normalizarTexto(texto);
  const hoje = new Date();
  const hojeInicio = inicioDoDia(hoje);

  let data = null;

  if (/\b(depois de amanha|depois da amanha)\b/.test(t)) {
    data = addDias(hoje, 2);
  } else if (/\bamanha\b/.test(t)) {
    data = addDias(hoje, 1);
  } else if (/\bhoje\b/.test(t)) {
    data = hojeInicio;
  }

  if (!data) {
    const matchData = t.match(/\b(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?\b/);
    if (matchData) {
      const dia = Number(matchData[1]);
      const mes = Number(matchData[2]);
      const anoInformado = matchData[3];
      let ano = anoInformado ? Number(anoInformado) : hoje.getFullYear();
      if (anoInformado && ano < 100) ano += 2000;

      data = new Date(ano, mes - 1, dia);
      const dataValida = data.getFullYear() === ano && data.getMonth() === mes - 1 && data.getDate() === dia;
      if (!dataValida) return null;

      if (!anoInformado && inicioDoDia(data) < hojeInicio) {
        data = new Date(ano + 1, mes - 1, dia);
      }
      if (anoInformado && inicioDoDia(data) < hojeInicio) return null;
    }
  }

  if (!data) {
    const diasSemana = [
      ['domingo', 0],
      ['segunda', 1],
      ['terca', 2],
      ['quarta', 3],
      ['quinta', 4],
      ['sexta', 5],
      ['sabado', 6],
    ];
    const encontrado = diasSemana.find(([nome]) => t.includes(nome));
    if (encontrado) {
      const alvo = encontrado[1];
      let diferenca = (alvo - hoje.getDay() + 7) % 7;
      if (diferenca === 0) diferenca = 7;
      data = addDias(hoje, diferenca);
    }
  }

  if (!data || inicioDoDia(data) < hojeInicio) return null;

  return {
    isoDate: isoDateLocal(data),
    display: formatarDataDate(data),
  };
}

function parseHorario(texto) {
  const t = normalizarTexto(texto);
  const match = t.match(/\b([01]?\d|2[0-3])\s*(?:[:h]\s*([0-5]\d))?\b/);
  if (!match) return null;

  const hora = Number(match[1]);
  const minuto = match[2] ? Number(match[2]) : 0;
  if (hora < 0 || hora > 23 || minuto < 0 || minuto > 59) return null;

  return `${String(hora).padStart(2, '0')}:${String(minuto).padStart(2, '0')}`;
}

function combinarDataHora(dataIso, horario) {
  const data = dataLocalFromIsoDate(dataIso);
  if (!data) return null;

  const [hora, minuto] = String(horario).split(':').map(Number);
  if (Number.isNaN(hora) || Number.isNaN(minuto)) return null;

  return new Date(data.getFullYear(), data.getMonth(), data.getDate(), hora, minuto, 0, 0);
}

function formatarDataHora(dataHoraIso) {
  const data = new Date(dataHoraIso);
  if (Number.isNaN(data.getTime())) return dataHoraIso;
  return `${String(data.getDate()).padStart(2, '0')}/${String(data.getMonth() + 1).padStart(2, '0')} as ${String(data.getHours()).padStart(2, '0')}:${String(data.getMinutes()).padStart(2, '0')}`;
}

async function iniciarFluxoAgendamento(cliente, telefone) {
  const proximo = await getProximoAgendamento(cliente.id);
  const nome = primeiroNome(cliente);

  if (proximo) {
    return {
      clienteId: cliente.id,
      texto: `${nome}, voce ja tem um horario confirmado para ${formatarDataHora(proximo.data_hora)}. Para alterar, responda com *remarcar*.`,
    };
  }

  await setEstadoConversa(telefone, ESTADOS.AGUARDANDO_DATA_AGENDAMENTO, { operacao: 'agendamento' });
  return {
    clienteId: cliente.id,
    texto: `${nome}, vamos agendar. Qual data voce prefere? Pode responder como *amanha*, *sexta* ou *25/04*.`,
  };
}

async function iniciarFluxoRemarcacao(cliente, telefone) {
  const proximo = await getProximoAgendamento(cliente.id);
  const nome = primeiroNome(cliente);

  if (!proximo) {
    await resetEstadoConversa(telefone);
    return {
      clienteId: cliente.id,
      texto: `${nome}, nao encontrei agendamento futuro confirmado para remarcar. Se quiser um novo horario, responda com *agendar*.`,
    };
  }

  await setEstadoConversa(telefone, ESTADOS.AGUARDANDO_NOVA_DATA_REMARCACAO, {
    operacao: 'remarcacao',
    agendamento_id: proximo.id,
    data_hora_antiga: proximo.data_hora,
  });

  return {
    clienteId: cliente.id,
    texto: `${nome}, seu horario atual e ${formatarDataHora(proximo.data_hora)}. Qual nova data voce prefere?`,
  };
}

async function receberDataAgendamento(cliente, telefone, texto, contexto) {
  const data = parseData(texto);
  if (!data) {
    return {
      clienteId: cliente.id,
      texto: 'Nao consegui entender a data. Pode enviar como *amanha*, *sexta* ou *25/04*?',
    };
  }

  await setEstadoConversa(telefone, ESTADOS.AGUARDANDO_HORARIO_AGENDAMENTO, {
    ...contexto,
    data: data.isoDate,
    data_display: data.display,
  });

  return {
    clienteId: cliente.id,
    texto: `Perfeito. Para ${data.display}, qual horario voce prefere? Exemplos: *14h* ou *14:30*.`,
  };
}

async function receberHorarioAgendamento(cliente, telefone, texto, contexto) {
  const horario = parseHorario(texto);
  if (!horario) {
    return {
      clienteId: cliente.id,
      texto: 'Nao consegui entender o horario. Pode enviar como *14h* ou *14:30*?',
    };
  }

  const dataHora = combinarDataHora(contexto.data, horario);
  if (!dataHora || dataHora <= new Date()) {
    await setEstadoConversa(telefone, ESTADOS.AGUARDANDO_DATA_AGENDAMENTO, { operacao: 'agendamento' });
    return {
      clienteId: cliente.id,
      texto: 'Esse horario ja passou. Me envie uma nova data para o agendamento.',
    };
  }

  const dataHoraIso = dataHora.toISOString();
  if (await horarioOcupado(dataHoraIso)) {
    return {
      clienteId: cliente.id,
      texto: `Esse horario (${formatarDataHora(dataHoraIso)}) ja esta ocupado. Me envie outro horario para a mesma data ou digite *cancelar*.`,
    };
  }

  await setEstadoConversa(telefone, ESTADOS.AGUARDANDO_CONFIRMACAO_AGENDAMENTO, {
    ...contexto,
    horario,
    data_hora: dataHoraIso,
  });

  return {
    clienteId: cliente.id,
    texto: `Confirmando: agendamento para ${formatarDataHora(dataHoraIso)}. Deseja confirmar?`,
  };
}

async function confirmarAgendamento(cliente, telefone, texto, contexto) {
  if (isNegacao(texto)) {
    await resetEstadoConversa(telefone);
    return {
      clienteId: cliente.id,
      texto: 'Agendamento cancelado. Quando quiser tentar outro horario, responda com *agendar*.',
    };
  }

  if (!isConfirmacao(texto)) {
    return {
      clienteId: cliente.id,
      texto: 'Responda com *sim* para confirmar ou *cancelar* para desistir desse agendamento.',
    };
  }

  const proximo = await getProximoAgendamento(cliente.id);
  if (proximo) {
    await resetEstadoConversa(telefone);
    return {
      clienteId: cliente.id,
      texto: `Voce ja tem um horario confirmado para ${formatarDataHora(proximo.data_hora)}. Para alterar, responda com *remarcar*.`,
    };
  }

  if (!contexto.data_hora || (await horarioOcupado(contexto.data_hora))) {
    await setEstadoConversa(telefone, ESTADOS.AGUARDANDO_HORARIO_AGENDAMENTO, contexto);
    return {
      clienteId: cliente.id,
      texto: 'Esse horario acabou de ficar indisponivel. Me envie outro horario.',
    };
  }

  await criarAgendamento(cliente.id, contexto.data_hora, 'corte');
  await resetEstadoConversa(telefone);

  return {
    clienteId: cliente.id,
    texto: `Fechado, ${primeiroNome(cliente)}! Seu agendamento ficou confirmado para ${formatarDataHora(contexto.data_hora)}.`,
  };
}

async function receberDataRemarcacao(cliente, telefone, texto, contexto) {
  const data = parseData(texto);
  if (!data) {
    return {
      clienteId: cliente.id,
      texto: 'Nao consegui entender a nova data. Pode enviar como *amanha*, *sexta* ou *25/04*?',
    };
  }

  await setEstadoConversa(telefone, ESTADOS.AGUARDANDO_NOVO_HORARIO_REMARCACAO, {
    ...contexto,
    nova_data: data.isoDate,
    nova_data_display: data.display,
  });

  return {
    clienteId: cliente.id,
    texto: `Certo. Para ${data.display}, qual novo horario voce prefere? Exemplos: *14h* ou *14:30*.`,
  };
}

async function receberHorarioRemarcacao(cliente, telefone, texto, contexto) {
  const horario = parseHorario(texto);
  if (!horario) {
    return {
      clienteId: cliente.id,
      texto: 'Nao consegui entender o horario. Pode enviar como *14h* ou *14:30*?',
    };
  }

  const dataHora = combinarDataHora(contexto.nova_data, horario);
  if (!dataHora || dataHora <= new Date()) {
    await setEstadoConversa(telefone, ESTADOS.AGUARDANDO_NOVA_DATA_REMARCACAO, contexto);
    return {
      clienteId: cliente.id,
      texto: 'Esse novo horario ja passou. Me envie outra data para a remarcacao.',
    };
  }

  const dataHoraIso = dataHora.toISOString();
  if (await horarioOcupado(dataHoraIso, contexto.agendamento_id)) {
    return {
      clienteId: cliente.id,
      texto: `Esse horario (${formatarDataHora(dataHoraIso)}) ja esta ocupado. Me envie outro horario ou digite *cancelar*.`,
    };
  }

  await setEstadoConversa(telefone, ESTADOS.AGUARDANDO_CONFIRMACAO_REMARCACAO, {
    ...contexto,
    novo_horario: horario,
    nova_data_hora: dataHoraIso,
  });

  return {
    clienteId: cliente.id,
    texto: `Confirmando remarcacao: de ${formatarDataHora(contexto.data_hora_antiga)} para ${formatarDataHora(dataHoraIso)}. Deseja confirmar?`,
  };
}

async function confirmarRemarcacao(cliente, telefone, texto, contexto) {
  if (isNegacao(texto)) {
    await resetEstadoConversa(telefone);
    return {
      clienteId: cliente.id,
      texto: 'Remarcacao cancelada. Seu horario original continua confirmado.',
    };
  }

  if (!isConfirmacao(texto)) {
    return {
      clienteId: cliente.id,
      texto: 'Responda com *sim* para confirmar a remarcacao ou *cancelar* para manter o horario atual.',
    };
  }

  const agendamento = await getAgendamentoById(contexto.agendamento_id, cliente.id);
  if (!agendamento) {
    await resetEstadoConversa(telefone);
    return {
      clienteId: cliente.id,
      texto: 'Nao encontrei mais esse agendamento ativo. Responda com *agendar* para escolher um novo horario.',
    };
  }

  if (!contexto.nova_data_hora || (await horarioOcupado(contexto.nova_data_hora, agendamento.id))) {
    await setEstadoConversa(telefone, ESTADOS.AGUARDANDO_NOVO_HORARIO_REMARCACAO, contexto);
    return {
      clienteId: cliente.id,
      texto: 'Esse horario acabou de ficar indisponivel. Me envie outro horario para a remarcacao.',
    };
  }

  await remarcarAgendamento(agendamento.id, cliente.id, contexto.nova_data_hora);
  await resetEstadoConversa(telefone);

  return {
    clienteId: cliente.id,
    texto: `Remarcado com sucesso! Seu novo horario e ${formatarDataHora(contexto.nova_data_hora)}.`,
  };
}

async function responderEstadoAtivo(cliente, telefone, texto, estadoConversa) {
  const { estado, contexto } = estadoConversa;

  if (estado === ESTADOS.IDLE) return null;

  if (isCancelamento(texto)) {
    await resetEstadoConversa(telefone);
    return {
      clienteId: cliente.id,
      texto: `${primeiroNome(cliente)}, atendimento atual cancelado. ${menuPrincipal(primeiroNome(cliente))}`,
    };
  }

  switch (estado) {
    case ESTADOS.AGUARDANDO_DATA_AGENDAMENTO:
      return receberDataAgendamento(cliente, telefone, texto, contexto);
    case ESTADOS.AGUARDANDO_HORARIO_AGENDAMENTO:
      return receberHorarioAgendamento(cliente, telefone, texto, contexto);
    case ESTADOS.AGUARDANDO_CONFIRMACAO_AGENDAMENTO:
      return confirmarAgendamento(cliente, telefone, texto, contexto);
    case ESTADOS.AGUARDANDO_NOVA_DATA_REMARCACAO:
      return receberDataRemarcacao(cliente, telefone, texto, contexto);
    case ESTADOS.AGUARDANDO_NOVO_HORARIO_REMARCACAO:
      return receberHorarioRemarcacao(cliente, telefone, texto, contexto);
    case ESTADOS.AGUARDANDO_CONFIRMACAO_REMARCACAO:
      return confirmarRemarcacao(cliente, telefone, texto, contexto);
    default:
      await resetEstadoConversa(telefone);
      return null;
  }
}

async function responderCadastroNovo(telefone, texto, estadoConversa) {
  if (estadoConversa.estado === ESTADOS.AGUARDANDO_NOME) {
    if (isCancelamento(texto)) {
      await resetEstadoConversa(telefone);
      return {
        clienteId: null,
        texto: 'Sem problema. Quando quiser iniciar seu atendimento, me envie seu nome.',
      };
    }

    const nome = extrairNome(texto);
    if (!nome) {
      return {
        clienteId: null,
        texto: 'Nao consegui identificar seu nome. Pode enviar apenas seu nome, por exemplo: *Rafael*?',
      };
    }

    const cliente = await criarCliente({ nome, telefone });
    await resetEstadoConversa(telefone);

    return {
      clienteId: cliente.id,
      texto: `Prazer, ${primeiroNome(cliente)}! Seu cadastro foi criado. ${menuPrincipal(primeiroNome(cliente))}`,
    };
  }

  await setEstadoConversa(telefone, ESTADOS.AGUARDANDO_NOME, {});
  return {
    clienteId: null,
    texto: 'Ola! Sou o assistente da barbearia. Ainda nao encontrei seu cadastro. Me diga seu *nome* para eu iniciar seu atendimento.',
  };
}

async function processarMensagem(telefone, body) {
  const phone = normalizarTelefoneWhatsApp(telefone);
  const texto = String(body || '').trim();
  const estadoConversa = await getEstadoConversa(phone);
  const cliente = await getClienteByPhone(phone);

  if (!cliente) {
    return responderCadastroNovo(phone, texto, estadoConversa);
  }

  const respostaEstado = await responderEstadoAtivo(cliente, phone, texto, estadoConversa);
  if (respostaEstado) return respostaEstado;

  const nome = primeiroNome(cliente);

  if (isPedidoRemarcacao(texto)) return iniciarFluxoRemarcacao(cliente, phone);

  if (isPedidoPromocao(texto)) {
    return {
      clienteId: cliente.id,
      texto: `${nome}, temos combo de ${cliente.preferencia || 'corte + barba'} com 15% de desconto ate sexta. Quer aproveitar? Responda com *agendar*.`,
    };
  }

  if (isPedidoAgendamento(texto)) return iniciarFluxoAgendamento(cliente, phone);

  if (isPedidoMenu(texto)) {
    return {
      clienteId: cliente.id,
      texto: menuPrincipal(nome),
    };
  }

  return {
    clienteId: cliente.id,
    texto: `${nome}, ${getRecomendacao(cliente)} Seu barbeiro favorito e ${cliente.barbeiro_favorito || 'qualquer profissional da casa'}. Posso te ajudar com *agendar*, *remarcar* ou *promocao*.`,
  };
}

async function enviarMensagemWhatsApp(destino, texto) {
  if (!WHATSAPP_TOKEN) {
    throw new Error('WHATSAPP_TOKEN nao configurado');
  }
  if (!WHATSAPP_PHONE_NUMBER_ID) {
    throw new Error('WHATSAPP_PHONE_NUMBER_ID nao configurado');
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

  const data = await response.json().catch(() => ({}));

  if (!response.ok) {
    throw new Error(`Erro Meta API: ${response.status} - ${JSON.stringify(data)}`);
  }

  return data;
}

function extrairTextoMensagemMeta(message) {
  if (message?.type === 'text' && typeof message.text?.body === 'string') {
    const body = message.text.body.trim();
    return body ? body : null;
  }

  // Futuro: normalizar interactive.button_reply e interactive.list_reply aqui.
  return null;
}

function extrairMensagemWhatsApp(payload) {
  if (!payload || !Array.isArray(payload.entry)) return null;

  for (const entry of payload.entry) {
    const changes = Array.isArray(entry?.changes) ? entry.changes : [];

    for (const change of changes) {
      const value = change?.value || {};
      const messages = Array.isArray(value.messages) ? value.messages : [];
      if (!messages.length) continue;

      for (const message of messages) {
        const body = extrairTextoMensagemMeta(message);
        const from = limparNumero(message?.from || '');

        if (!body || !from) continue;

        return {
          from,
          body,
          messageId: message.id || null,
          type: message.type || 'text',
        };
      }
    }
  }

  return null;
}

function adminAuth(req, res, next) {
  if (!ADMIN_TOKEN) {
    return res.status(503).json({ detail: 'ADMIN_TOKEN nao configurado no servidor' });
  }

  const token = req.get('x-admin-token') || '';
  if (token !== ADMIN_TOKEN) {
    return res.status(401).json({ detail: 'Token admin invalido' });
  }

  return next();
}

app.get('/health', (_req, res) => {
  res.json({
    status: 'ok',
    provider: 'meta_whatsapp_cloud_api',
    businessId: WHATSAPP_BUSINESS_ID || null,
    phoneNumberId: WHATSAPP_PHONE_NUMBER_ID || null,
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

    const telefone = normalizarTelefoneWhatsApp(inbound.from);
    const resposta = await processarMensagem(telefone, inbound.body);

    await salvarMensagem({
      clienteId: resposta.clienteId,
      telefone,
      direcao: 'entrada',
      conteudo: inbound.body,
      providerMessageId: inbound.messageId,
    });

    const envio = await enviarMensagemWhatsApp(inbound.from, resposta.texto);
    const saidaId = envio?.messages?.[0]?.id || null;

    await salvarMensagem({
      clienteId: resposta.clienteId,
      telefone,
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

app.post('/send-test', adminAuth, async (_req, res) => {
  try {
    if (!NUMERO_DESTINATARIO) {
      return res.status(400).json({ ok: false, detail: 'NUMERO_DESTINATARIO nao configurado' });
    }

    const texto = `Teste automatico\nDestino: ${limparNumero(NUMERO_DESTINATARIO)}\nData UTC: ${new Date().toISOString()}`;
    const envio = await enviarMensagemWhatsApp(NUMERO_DESTINATARIO, texto);

    await salvarMensagem({
      clienteId: null,
      telefone: normalizarTelefoneWhatsApp(NUMERO_DESTINATARIO),
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

app.get('/clientes/:telefone/historico', adminAuth, async (req, res) => {
  try {
    const telefone = decodeURIComponent(req.params.telefone);
    const limit = Number(req.query.limit || 20);
    const limitSeguro = limit > 0 ? Math.min(limit, 100) : 20;
    const historico = await listarHistoricoPorTelefone(telefone, limitSeguro);

    res.json({
      telefone: normalizarTelefoneWhatsApp(telefone),
      total: historico.length,
      mensagens: historico,
    });
  } catch (error) {
    console.error(error);
    res.status(500).json({ detail: 'Erro interno' });
  }
});

async function iniciarServidor() {
  try {
    await initDb();
    app.listen(PORT, '0.0.0.0', () => {
      console.log(`Servidor rodando na porta ${PORT}`);
    });
  } catch (error) {
    console.error('Falha ao iniciar servidor:', error);
    process.exit(1);
  }
}

iniciarServidor();
