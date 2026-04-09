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
    setWsStatus("✅ Conectado — iniciando áudio...", "#00ff88");
    if (state.myLang && !state.audioOn) {
      state.ws.send(JSON.stringify({ action: "start", my_language: state.myLang, other_language: state.otherLang }));
      state.audioOn = true;
      const btn = document.getElementById("btn-audio");
      if (btn) { btn.textContent = "🔴 Áudio ligado"; btn.style.background = "#e94560"; btn.style.color = "white"; }
      setWsStatus("🎤 Gravando — fale agora!", "#00ff88");
    }
  };
  state.ws.onmessage = e => onMessage(JSON.parse(e.data));
  state.ws.onclose = () => {
    setWsStatus("🔴 Desconectado", "#e94560");
    if (!state.stopping) setTimeout(() => connectWS(onMessage), 3000);
  };
  state.ws.onerror = () => { setWsStatus("❌ Erro na conexão", "#e94560"); state.ws.close(); };
}

// ── Gravação ──────────────────────────────────────────────────────────────────

function startRecording() {
  const myLang = document.getElementById("my-lang").value;
  const otherLang = document.getElementById("other-lang").value;
  state.myLang = myLang;
  state.otherLang = otherLang;
  document.getElementById("langs-display").textContent = `${myLang} ↔ ${otherLang}`;
  document.getElementById("live-caption").textContent = "Aguardando fala...";
  document.getElementById("live-translation").textContent = "";
  document.getElementById("transcript-box").innerHTML = "";
  state.transcriptions = [];
  state.audioOn = false;
  const btn = document.getElementById("btn-audio");
  if (btn) btn.textContent = "🎤 Ligar Áudio";
  showScreen("recording");
  connectWS(onWsMessage);
}

function toggleAudio() {
  if (!state.ws || state.ws.readyState !== WebSocket.OPEN) {
    setWsStatus("❌ WebSocket não conectado", "#e94560");
    return;
  }
  if (!state.audioOn) {
    state.ws.send(JSON.stringify({ action: "start", my_language: state.myLang, other_language: state.otherLang }));
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

    const box = document.getElementById("transcript-box");
    const cls = data.speaker === "Você" ? "entry-you" : "entry-other";
    box.innerHTML += `<div class="${cls}"><b>[${data.timestamp}] ${data.speaker}:</b> ${data.original}</div>`;
    if (data.original !== data.translation) {
      box.innerHTML += `<div class="entry-translation">↳ ${data.translation}</div>`;
    }
    box.scrollTop = box.scrollHeight;
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
