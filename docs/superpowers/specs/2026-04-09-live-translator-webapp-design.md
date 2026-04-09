# Live Translator Web App — Design Spec
**Data:** 2026-04-09  
**Status:** Aprovado

---

## Visão Geral

Substituir o app Tkinter atual por um **webapp moderno** (FastAPI + frontend HTML/JS) com autenticação de equipe, detecção automática de reuniões (Zoom, Teams, Meet e similares), transcrição em tempo real, tradução bidirecional com áudio via TTS, e salvamento automático no Google Drive.

---

## Arquitetura

```
[Meeting Watcher (watcher.py)]
  - Monitora processos: Zoom, Teams, Meet, Webex e similares
  - Detecta abertura de reunião (iniciada pelo usuário OU recebida)
  - Abre browser automaticamente apontando para o frontend
  - Hotkey global Ctrl+Shift+T como fallback manual
  - Usa psutil para monitoramento de processos

[FastAPI Backend (main.py)]
  - Servidor HTTP na porta 8000
  - WebSocket em /ws/{user_id} para comunicação em tempo real com o frontend
  - Rotas REST: /auth/*, /meetings/*, /users/*

[Frontend (static/)]
  - SPA em HTML/CSS/JS vanilla (sem framework)
  - 4 telas: Login → Em espera → Gravando → Fim da reunião
  - Tema dark: #1a1a2e, #e94560, #00ff88
  - Conecta ao backend via WebSocket

[SQLite (db.sqlite3)]
  - Tabela users
  - Tabela meetings
```

---

## Componentes do Backend

### `main.py`
- Inicializa FastAPI, monta rotas e WebSocket
- Serve os arquivos estáticos do frontend

### `audio.py`
- Captura microfone via pyaudiowpatch (16kHz, mono)
- Captura loopback do sistema (áudio do outro na call)
- Enfileira chunks de 3s para processamento

### `transcriber.py`
- Recebe chunks de áudio
- Transcreve com faster-whisper (modelo configurável: tiny/base/small)
- Traduz com deep-translator (GoogleTranslator)
- Envia resultado via WebSocket para o frontend

### `tts.py`
- Recebe texto traduzido para português (do áudio do outro)
- Converte para áudio via **edge-tts** (Microsoft, gratuito, alta qualidade)
- Toca no dispositivo de saída padrão do usuário (fone)

### `auth.py`
- Login com email + senha (bcrypt + JWT via python-jose)
- Login com Google OAuth2 (Authlib)
- Middleware de autenticação para rotas protegidas

### `storage.py`
- Ao fim da reunião, salva na pasta Google Drive do usuário:
  ```
  <pasta_drive>/<usuario>/<YYYYMMDD_HHMM>/
    ├── audio.wav
    ├── transcricao.txt
    └── reuniao.pdf
  ```
- PDF gerado com reportlab (transcrição completa + resumo IA)
- Resumo gerado via OpenAI GPT-4o-mini

### `watcher.py`
- Script independente que roda em background
- Polling de processos a cada 3s via psutil
- Processos monitorados: `zoom.exe`, `ms-teams.exe` / `teams.exe`, `webex.exe`, `slack.exe`
- Google Meet: detectado via título de janela do Chrome/Edge contendo "Meet" (window title check via pygetwindow)
- Ao detectar: abre `http://localhost:8000` no browser padrão
- Registra hotkey global Ctrl+Shift+T via keyboard lib
- Para de monitorar quando reunião encerra (processo some)

---

## Banco de Dados (SQLite)

```sql
CREATE TABLE users (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  name        TEXT NOT NULL,
  email       TEXT UNIQUE NOT NULL,
  password_hash TEXT,           -- NULL se login Google
  google_id   TEXT,             -- NULL se login email/senha
  my_language TEXT DEFAULT 'pt',
  other_language TEXT DEFAULT 'en',
  drive_folder TEXT NOT NULL,   -- caminho da pasta no Google Drive
  created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE meetings (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id     INTEGER REFERENCES users(id),
  started_at  DATETIME NOT NULL,
  ended_at    DATETIME,
  audio_path  TEXT,
  transcript_path TEXT,
  pdf_path    TEXT,
  summary     TEXT
);
```

---

## Frontend — Telas

### Tela 1: Login
- Campos: email + senha → botão "Entrar"
- Botão "Entrar com Google" (OAuth redirect)
- Link "Criar conta"

### Tela 2: Em espera
- Indicador verde "● ativo — monitorando"
- Lista dos apps monitorados: Zoom · Teams · Meet
- Dropdown: "Meu idioma" ⇄ "Idioma da reunião" (pré-preenchido do perfil, editável)
- Nome do usuário + pasta Google Drive configurada
- Dica: Ctrl+Shift+T para iniciar manual

### Tela 3: Gravando (Dashboard)
- Header: nome do app + badge "🔴 AO VIVO" + idiomas configurados
- Caixa de legenda ao vivo (última fala, em destaque)
- Tradução da última fala (texto menor abaixo)
- Histórico de transcrição com scroll (rolagem automática)
- Botões: ⏹ Parar | 📄 PDF | 🤖 Resumo

### Tela 4: Fim da reunião
- Confirmação: "✅ Reunião salva!"
- Lista dos arquivos salvos com caminhos
- Resumo IA exibido inline
- Botão "Nova reunião" → volta para Tela 2

---

## Fluxo de Tradução (Fase 1)

| Direção | Captura | Transcrição | Tradução | Saída |
|---|---|---|---|---|
| Outro fala (inglês) | Loopback | Whisper (en) | → português | **edge-tts toca no fone** |
| Você fala (português) | Microfone | Whisper (pt) | → inglês | **legenda na tela** |

**Fase 2 (futuro):** sua voz traduzida é injetada na call via áudio virtual (VB-Cable), para o outro ouvir em inglês diretamente.

---

## Configuração de Idiomas
- Cada usuário define no perfil: meu idioma (default: pt) e idioma da reunião (default: en)
- Configurável por reunião também, via dropdown na Tela 2

---

## Stack Tecnológica

| Componente | Tecnologia |
|---|---|
| Backend | Python 3.11+ + FastAPI + Uvicorn |
| WebSocket | FastAPI WebSocket nativo |
| Transcrição | faster-whisper |
| Tradução | deep-translator (GoogleTranslator) |
| TTS | edge-tts |
| Auth JWT | python-jose + passlib[bcrypt] |
| Auth Google | Authlib |
| Banco | SQLite via aiosqlite |
| PDF | reportlab |
| Resumo IA | OpenAI GPT-4o-mini |
| Watcher | psutil + keyboard |
| Frontend | HTML5 + CSS3 + JS vanilla |

---

## Salvamento no Google Drive

- O Google Drive é mapeado como pasta local no Windows (cliente Google Drive instalado)
- `drive_folder` no perfil do usuário = caminho absoluto da pasta (ex: `G:/Meu Drive/Reunioes`)
- Não requer Google Drive API — salva direto no filesystem

---

## Tratamento de Erros

- Modelo Whisper não baixado: retry com backoff exponencial (já implementado no `tradutor.py` atual)
- Falha no TTS: log silencioso, continua sem áudio (legenda ainda funciona)
- Falha no GPT: PDF é gerado sem resumo, com mensagem "Resumo indisponível"
- Conexão WebSocket cai: frontend tenta reconectar a cada 3s
- Google Drive offline: salva em pasta local temporária, avisa o usuário

---

## Fora do Escopo (Fase 1)

- Injeção de áudio na call (Fase 2)
- App mobile
- Histórico de reuniões anteriores na UI (os arquivos ficam no Drive)
- Notificações push
