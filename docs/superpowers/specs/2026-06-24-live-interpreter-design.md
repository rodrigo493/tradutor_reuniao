# Live Interpreter — Design Spec

**Data:** 2026-06-24
**Projeto:** tradutor_reuniao
**Status:** Aprovado (aguardando revisão do spec escrito)

## 1. Visão

Transformar o `tradutor_reuniao` (hoje um transcritor de reunião unidirecional) em um
**intérprete de voz bidirecional** que roda em **PC Windows** e funciona como camada de
tradução por cima de **qualquer app de call** (WhatsApp, Telegram, Teams, Google Meet,
ligação, etc.).

Fluxo alvo:

```
OUTRA PESSOA fala (ex.: inglês)
  → app de call toca no seu fone
  → [app captura via loopback WASAPI] → detecta idioma → traduz → TTS PT
  → você ouve em português 🎧

VOCÊ responde (português no mic)
  → [app captura] → traduz → TTS no idioma da outra pessoa
  → toca no "CABLE Input" (VB-Cable)
  → call app usa "CABLE Output" como microfone
  → OUTRA PESSOA ouve no idioma dela 🔊
```

## 2. Restrições e decisões de plataforma

- **Apenas PC Windows.** Celular está fora de escopo: iOS/Android proíbem um app capturar o
  áudio de outro app (a call) — limitação do SO, não do nosso código. Inbound e outbound
  automáticos só são possíveis no desktop.
- **Outbound exige VB-Cable** (cabo de áudio virtual, grátis, instalação única). É a única
  forma de "virar o microfone" do app de call. O app de call precisa ter o microfone
  configurado para `CABLE Output`.
- **Latência turno-a-turno** (~2–4s por fala). Não é simultâneo; serve para conversa com
  pausas, não para falar por cima.

## 3. Idiomas

- **Inbound** (outra pessoa → você): **detecção automática** do idioma, robusta para
  **inglês e espanhol**, sempre traduzindo para **português**. Modelo Whisper **`base`**
  (auto-detect confiável; `tiny` erra demais). Seletor opcional
  "Idioma da outra pessoa: Auto / Inglês / Espanhol" para forçar quando quiser mais precisão.
- **Outbound** (você → outra pessoa): você fala **português** → traduz para o idioma
  escolhido num **dropdown** (padrão Inglês) → injeta no VB-Cable.
- **Entrada de texto** no inbound: a outra pessoa pode ter mandado mensagem escrita; o app
  aceita texto colado → devolve áudio + texto em PT.

## 4. Arquitetura de áudio e dispositivos

Dois streams simultâneos (já existem em `backend/audio.py`):

- **Loopback** = saída do sistema (voz da outra pessoa vinda do app de call) → pipeline inbound.
- **Mic** = sua voz → pipeline outbound.

Roteamento de saída (parte nova crítica):

- TTS inbound (português) → **dispositivo do seu fone**, para você ouvir.
- TTS outbound (idioma da outra pessoa) → **VB-Cable Input** → o app de call usa
  `CABLE Output` como microfone → a outra pessoa ouve.

Painel de configuração de dispositivos na UI: escolher loopback, mic, saída do fone, e
confirmar o VB-Cable.

## 5. Anti-eco (problema real)

O loopback do Windows captura **tudo** que sai no dispositivo de fone — incluindo o
**nosso próprio TTS em português**. Sem tratamento, isso vira um loop de realimentação.
Solução pragmática dupla:

1. **Half-duplex no inbound:** pausar a captura do loopback enquanto o TTS português toca.
2. **Descarte por idioma:** o inbound espera EN/ES; se o Whisper detectar **português** num
   trecho inbound, é eco nosso → descartar.

## 6. Pipelines (reuso)

- `backend/transcriber.py` (Whisper + tradução): reuso, mudando para auto-detect e modelo
  `base`. Adiciona descarte de segmentos PT no canal inbound.
- `backend/tts.py` (edge-tts, mapa de 11 vozes): reuso. Decodificar o mp3 com `av` (PyAV, já
  vem com faster-whisper) e escrever o PCM no **dispositivo de saída escolhido** via
  `pyaudiowpatch` (já existe). **Sem dependência de áudio nova.**
- `backend/audio.py` (captura loopback + mic): reuso, adicionando seleção de dispositivo e o
  gate half-duplex.
- `backend/session.py` (`RecordingSession`, workers): estender para dois pipelines
  direcionais (inbound/outbound) com roteamento de saída distinto.

## 7. Persistência — migração SQLite → Supabase Postgres

Mantida (login + histórico na nuvem). Driver: **`asyncpg`** + connection pool.

- Pool `asyncpg` criado no `lifespan` (startup), em `app.state.pool`, fechado no shutdown.
- String de conexão via `.env` (`SUPABASE_DB_URL`), **nunca** no código. Usar o
  **Session Pooler** do Supabase (host `...pooler.supabase.com`, IPv4) — o host direto
  `db.<ref>.supabase.co` é IPv6-only em projetos novos e falha em máquina residencial.
- `backend/database.py` reescrito: DDL Postgres (`GENERATED ALWAYS AS IDENTITY`,
  `TIMESTAMPTZ`). `get_db` entrega conexão do pool.
- Queries (`main.py` + `routers/auth_router.py`): placeholders `?` → `$1,$2…`;
  `cursor.lastrowid` → `INSERT … RETURNING id` (`fetchval`); `db.execute/fetchone/fetchall`
  → `conn.fetch/fetchrow/execute`; remover `db.commit()` (autocommit). `row["col"]` continua
  funcionando (asyncpg `Record`).
- Tabela `meetings` evolui para `conversations`: transcrição dos **dois lados**, idiomas,
  timestamps, e resumo por IA.
- Começar do zero (sem migrar os 3 usuários de teste do `db.sqlite3`).

## 8. UI

Console ao vivo em duas colunas (**Outra pessoa** | **Você**), texto rolando em tempo real,
indicador de quem está falando, painel de dispositivos, seletor de idioma, botão start/stop,
e um **checador do VB-Cable** (avisa se não estiver instalado/configurado).

## 9. Dependências novas

- `asyncpg` — versão estável fixada (`==`), após checar **cooldown de 7 dias** e
  socket.dev/osv.dev. Apresentar bloco de aviso antes de instalar. Remover `aiosqlite`.
- Áudio: **nenhuma nova** (reuso `pyaudiowpatch` + PyAV).

## 10. Teste / verificação

- Pipeline de tradução inbound e outbound validado com áudio sintético (edge-tts → PCM 16k →
  transcribe → translate), como já feito para o pipeline atual.
- Health-check do pool asyncpg contra o Supabase real.
- Fluxo register → login → /auth/me contra o Postgres.
- Teste manual end-to-end numa call real com VB-Cable.

## 11. Fora de escopo (YAGNI / fase 2)

- Suporte a celular (limitação de SO).
- Tradução simultânea (sobreposição de fala).
- Idiomas além de EN/ES no inbound robusto (auto-detect cobre outros, mas o foco/teste é EN/ES).
```
