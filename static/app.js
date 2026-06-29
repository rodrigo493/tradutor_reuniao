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
  hideError("login-error");
  hideError("register-error");
  document.getElementById("login-box").style.display = "none";
  document.getElementById("register-box").style.display = "block";
}

function showLogin() {
  hideError("login-error");
  hideError("register-error");
  document.getElementById("register-box").style.display = "none";
  document.getElementById("login-box").style.display = "block";
}

async function doRegister() {
  hideError("register-error");
  const name = document.getElementById("reg-name").value.trim();
  const email = document.getElementById("reg-email").value.trim();
  const password = document.getElementById("reg-password").value;
  if (!name || !email || !password) {
    showError("register-error", "Preencha nome, email e senha.");
    return;
  }
  const res = await fetch("/auth/register", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, email, password }),
  });
  if (!res.ok) {
    let detail = "Erro ao criar conta.";
    try { detail = (await res.json()).detail || detail; } catch (e) {}
    showError("register-error", detail);
    return;
  }
  // Sucesso: preenche o login e entra automaticamente
  document.getElementById("login-email").value = email;
  document.getElementById("login-password").value = password;
  showLogin();
  await doLogin();
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

let wsReconnectTimer = null;

function connectWS(onMessage) {
  // Cancela qualquer reconexão pendente e desarma o socket antigo para evitar
  // loops de reconexão sobrepostos.
  if (wsReconnectTimer) { clearTimeout(wsReconnectTimer); wsReconnectTimer = null; }
  if (state.ws) {
    state.ws.onclose = null;
    state.ws.onerror = null;
    try { state.ws.close(); } catch (e) {}
  }
  const wsHost = window.location.host;
  const ws = new WebSocket(`ws://${wsHost}/ws?token=${state.token}`);
  state.ws = ws;
  setWsStatus("🔌 Conectando ao servidor...", "#aaa");
  ws.onopen = () => {
    setWsStatus("✅ Conectado — aguardando início do áudio...", "#00ff88");
  };
  ws.onmessage = e => onMessage(JSON.parse(e.data));
  ws.onclose = () => {
    if (state.ws !== ws) return;  // socket obsoleto: ignora
    setWsStatus("🔴 Desconectado", "#e94560");
    if (!state.stopping) wsReconnectTimer = setTimeout(() => connectWS(onMessage), 3000);
  };
  ws.onerror = () => {
    if (state.ws !== ws) return;
    setWsStatus("❌ Erro na conexão", "#e94560");
    // onclose dispara em seguida e cuida da reconexão única
  };
}

// ── Dispositivos ──────────────────────────────────────────────────────────────

async function loadDevices() {
  const res = await fetch('/devices');
  const data = await res.json();
  const inputs = data.inputs, outputs = data.outputs;

  const fill = (el, list) => {
    const prev = el.value;  // preserva a seleção atual no refresh (por NOME)
    el.innerHTML = '';
    const seen = new Set();
    list.forEach(d => {
      if (seen.has(d.name)) return;  // evita nomes duplicados (mesmo device em várias APIs)
      seen.add(d.name);
      const opt = document.createElement('option');
      opt.value = d.name;            // nome é estável; índice muda quando devices conectam
      opt.textContent = `${d.name}`;
      el.appendChild(opt);
    });
    if (prev && seen.has(prev)) el.value = prev;
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

  // Espelha o idioma escolhido na tela de espera (#my-lang) no seletor da
  // tela de gravação (#sel-my-lang), default pt.
  const myLangSel = document.getElementById("sel-my-lang");
  const waitingMyLang = document.getElementById("my-lang");
  if (myLangSel && waitingMyLang && waitingMyLang.value) myLangSel.value = waitingMyLang.value;
  const myLang = myLangSel ? myLangSel.value : "pt";
  document.getElementById("langs-display").textContent = `🌐 auto → ${myLang}`;
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
    const ttsOn = document.getElementById('chk-tts').checked;
    if (ttsOn && vbcableIndex === null) {
      alert('Para falar a tradução em voz, instale o VB-Cable. Ou deixe desligado para usar só texto.');
      return;
    }
    const myLangSel = document.getElementById('sel-my-lang');
    state.ws.send(JSON.stringify({
      action: 'start',
      my_language: myLangSel ? myLangSel.value : 'pt',
      headphone_name: document.getElementById('sel-headphone').value,
      mic_name: document.getElementById('sel-mic').value,
      loopback_name: document.getElementById('sel-loopback').value,
      tts_enabled: ttsOn,
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
