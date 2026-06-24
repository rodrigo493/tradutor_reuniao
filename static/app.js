// Índice do VB-Cable detectado (null = não instalado)
let vbcableIndex = null;

// Estado da aplicação
const state = {
  token: localStorage.getItem("token") || null,
  user: null,
  ws: null,
  transcriptions: [],
  stopping: false,
};

// ── Utilitários ──────────────────────────────────────────────────────────────

function showScreen(id) {
  document.querySelectorAll(".screen").forEach(s => s.classList.remove("active"));
  document.getElementById("screen-" + id).classList.add("active");
}

function showError(elementId, msg) {
  const el = document.getElementById(elementId);
  if (el) { el.textContent = msg; el.style.display = "block"; }
}

function hideError(elementId) {
  const el = document.getElementById(elementId);
  if (el) el.style.display = "none";
}

// ── Auth ─────────────────────────────────────────────────────────────────────

async function doLogin() {
  hideError("login-error");
  const email = document.getElementById("login-email").value.trim();
  const password = document.getElementById("login-password").value;
  if (!email || !password) { showError("login-error", "Preencha email e senha."); return; }

  const res = await fetch("/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  if (!res.ok) { showError("login-error", "Email ou senha incorretos."); return; }
  const data = await res.json();
  state.token = data.access_token;
  localStorage.setItem("token", state.token);
  await loadUser();
}

function showRegister() {
  const name = prompt("Seu nome:");
  if (!name) return;
  const email = prompt("Email:");
  if (!email) return;
  const password = prompt("Senha:");
  if (!password) return;
  const folder = prompt("Caminho da pasta Google Drive (ex: G:/Meu Drive/Reunioes):", "G:/Meu Drive/Reunioes");

  fetch("/auth/register", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, email, password, drive_folder: folder || "" }),
  }).then(r => r.json()).then(() => {
    document.getElementById("login-email").value = email;
    alert("Conta criada! Faça login.");
  }).catch(() => alert("Erro ao criar conta."));
}

async function loadUser() {
  const res = await fetch(`/auth/me?token=${state.token}`);
  if (!res.ok) { logout(); return; }
  state.user = await res.json();
  document.getElementById("user-name").textContent = state.user.name;
  const myLang = document.getElementById("my-lang");
  const otherLang = document.getElementById("other-lang");
  if (myLang) myLang.value = state.user.my_language || "pt";
  if (otherLang) otherLang.value = state.user.other_language || "en";
  showScreen("waiting");
}

function logout() {
  state.token = null;
  localStorage.removeItem("token");
  showScreen("login");
}

// ── WebSocket ─────────────────────────────────────────────────────────────────

function setWsStatus(msg, color) {
  const el = document.getElementById("ws-status");
  if (el) { el.textContent = msg; el.style.color = color || "#aaa"; }
}

function connectWS(onMessage) {
  if (state.ws) state.ws.close();
  const wsHost = window.location.host;
  state.ws = new WebSocket(`ws://${wsHost}/ws?token=${state.token}`);
  setWsStatus("🔌 Conectando ao servidor...", "#aaa");
  state.ws.onopen = () => {
    setWsStatus("✅ Conectado — aguardando início do áudio...", "#00ff88");
  };
  state.ws.onmessage = e => onMessage(JSON.parse(e.data));
  state.ws.onclose = () => {
    setWsStatus("🔴 Desconectado", "#e94560");
    if (!state.stopping) setTimeout(() => connectWS(onMessage), 3000);
  };
  state.ws.onerror = () => { setWsStatus("❌ Erro na conexão", "#e94560"); state.ws.close(); };
}

// ── Dispositivos ──────────────────────────────────────────────────────────────

async function loadDevices() {
  const res = await fetch('/devices');
  const data = await res.json();
  const inputs = data.inputs, outputs = data.outputs;

  const fill = (el, list) => {
    el.innerHTML = '';
    list.forEach(d => {
      const opt = document.createElement('option');
      opt.value = d.index;
      opt.textContent = `${d.name}`;
      el.appendChild(opt);
    });
  };
  fill(document.getElementById('sel-headphone'), outputs);
  fill(document.getElementById('sel-mic'), inputs);
  fill(document.getElementById('sel-loopback'), inputs);

  const status = document.getElementById('vbcable-status');
  if (data.vbcable) {
    vbcableIndex = data.vbcable.index;
    status.textContent = `✅ VB-Cable detectado: ${data.vbcable.name}`;
    status.className = 'vbcable-status ok';
  } else {
    vbcableIndex = null;
    status.textContent = '⚠️ VB-Cable não encontrado. O outbound (sua voz traduzida) não funcionará até instalá-lo.';
    status.className = 'vbcable-status warn';
  }
}

// ── Gravação ──────────────────────────────────────────────────────────────────

async function startRecording() {
  showScreen("recording");
  await loadDevices();

  const headphoneSel = document.getElementById("sel-headphone");
  const micSel = document.getElementById("sel-mic");
  const loopbackSel = document.getElementById("sel-loopback");
  if (!headphoneSel.value || !micSel.value || !loopbackSel.value) {
    alert("Nenhum dispositivo de áudio encontrado. Verifique as conexões e tente novamente.");
    showScreen("waiting");
    return;
  }

  const otherLang = document.getElementById("sel-other-lang").value;
  document.getElementById("langs-display").textContent = `pt ↔ ${otherLang}`;
  document.getElementById("live-caption").textContent = "Aguardando fala...";
  document.getElementById("live-translation").textContent = "";
  document.getElementById("col-other").innerHTML = "";
  document.getElementById("col-you").innerHTML = "";
  state.transcriptions = [];
  state.audioOn = false;
  const btn = document.getElementById("btn-audio");
  if (btn) btn.textContent = "🎤 Ligar Áudio";
  connectWS(onWsMessage);
}

function toggleAudio() {
  if (!state.ws || state.ws.readyState !== WebSocket.OPEN) {
    setWsStatus("❌ WebSocket não conectado", "#e94560");
    return;
  }
  if (!state.audioOn) {
    if (vbcableIndex === null) {
      alert('Instale o VB-Cable antes de iniciar (necessário para enviar sua voz traduzida).');
      return;
    }
    state.ws.send(JSON.stringify({
      action: 'start',
      other_language: document.getElementById('sel-other-lang').value,
      headphone_index: parseInt(document.getElementById('sel-headphone').value, 10),
      vbcable_index: vbcableIndex,
      mic_index: parseInt(document.getElementById('sel-mic').value, 10),
      loopback_index: parseInt(document.getElementById('sel-loopback').value, 10),
    }));
    state.audioOn = true;
    const btn = document.getElementById("btn-audio");
    if (btn) { btn.textContent = "🔴 Áudio ligado"; btn.style.background = "#e94560"; btn.style.color = "white"; }
    setWsStatus("🎤 Gravando — fale agora", "#00ff88");
  }
}

function onWsMessage(data) {
  if (data.type === "transcription") {
    document.getElementById("live-caption").textContent =
      `[${data.speaker}] ${data.translation}`;
    document.getElementById("live-translation").textContent =
      data.original !== data.translation ? `↳ ${data.original}` : "";

    const isOther = data.speaker === 'Outro';
    const col = isOther
      ? document.getElementById('col-other')
      : document.getElementById('col-you');

    const div = document.createElement('div');
    div.className = 'line';

    const tSpan = document.createElement('span');
    tSpan.className = 't';
    const langTag = isOther && data.detected_lang ? ` [${data.detected_lang}]` : '';
    tSpan.textContent = (data.timestamp || '') + langTag;

    const origSpan = document.createElement('span');
    origSpan.className = 'orig';
    origSpan.textContent = data.original || '';

    const tradSpan = document.createElement('span');
    tradSpan.className = 'trad';
    tradSpan.textContent = data.translation || '';

    div.appendChild(tSpan);
    div.appendChild(origSpan);
    div.appendChild(tradSpan);
    col.appendChild(div);
    col.scrollTop = col.scrollHeight;

    state.transcriptions.push(data);
  }
}

async function stopRecording() {
  state.stopping = true;
  const res = await fetch(`/meetings/end?token=${state.token}`, { method: "POST" });
  if (!res.ok) {
    state.stopping = false;
    alert("Erro ao salvar reunião.");
    return;
  }
  // Fecha WS após salvar (não reconecta)
  if (state.ws) { state.ws.close(); state.ws = null; }
  const data = await res.json();

  const filesEl = document.getElementById("saved-files");
  filesEl.innerHTML =
    `<div>📁 ${data.folder}</div>` +
    (data.txt ? `<div>📝 transcricao.txt</div>` : "") +
    (data.pdf ? `<div>📄 reuniao.pdf</div>` : "");

  document.getElementById("summary-text").textContent = data.summary || "Resumo indisponível.";
  state.stopping = false;
  showScreen("end");
}

function downloadPDF() {
  alert("PDF será gerado ao parar a gravação.");
}

function requestSummary() {
  alert("O resumo é gerado automaticamente ao parar a gravação.");
}

function newMeeting() {
  state.stopping = false;
  showScreen("waiting");
}

// ── Init ──────────────────────────────────────────────────────────────────────

window.addEventListener("load", () => {
  // Checar token na URL (vinda do OAuth Google)
  const params = new URLSearchParams(window.location.search);
  const urlToken = params.get("token");
  if (urlToken) {
    state.token = urlToken;
    localStorage.setItem("token", urlToken);
    window.history.replaceState({}, "", "/");
  }

  if (state.token) {
    loadUser();
  } else {
    showScreen("login");
  }
});
