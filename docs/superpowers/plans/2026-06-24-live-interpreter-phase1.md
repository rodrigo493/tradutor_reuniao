# Live Interpreter — Fase 1 (Intérprete bidirecional) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transformar o app num intérprete de voz bidirecional no PC Windows: ouvir a outra pessoa traduzida em português no fone e responder em português com a tradução injetada no app de call via VB-Cable.

**Architecture:** Reuso da captura existente (loopback = outra pessoa, mic = você). Adiciona (1) saída de áudio para dispositivo específico — fone para inbound PT, VB-Cable para outbound; (2) auto-detecção de idioma no inbound com descarte de eco em PT; (3) anti-eco half-duplex pausando o loopback durante o TTS inbound; (4) seleção de dispositivos + idioma na UI.

**Tech Stack:** Python 3.14, FastAPI, faster-whisper, deep-translator, edge-tts, pyaudiowpatch, PyAV (`av`, já vem com faster-whisper), NumPy. Frontend: HTML/CSS/JS vanilla (SPA existente).

## Global Constraints

- Plataforma: **Windows apenas** (WASAPI loopback + VB-Cable).
- Rodar com **Python 3.14** (`py -3.14`); o ambiente já tem as dependências instaladas.
- **Nenhuma dependência de áudio nova** — reuso `pyaudiowpatch` + `av`.
- A migração Supabase é **Fase 2** — esta fase mantém o SQLite atual intacto.
- Áudio interno do pipeline: **16000 Hz, mono, int16 PCM** (constante `RATE` em `backend/audio.py`).
- edge-tts gera **mp3 24kHz mono**; sempre reamostrar para o rate/canais nativos do dispositivo de saída antes de tocar.
- Idiomas foco do inbound robusto: **inglês e espanhol** → sempre **português**.
- Rodar testes: `py -3.14 -m pytest <arquivo>::<teste> -v`. Servidor: `py -3.14 -m uvicorn backend.main:app --port 8001`.
- Commits frequentes, um por task no mínimo. Sem atribuição (config global).

---

### Task 1: Enumeração de dispositivos + detecção do VB-Cable

**Files:**
- Create: `backend/devices.py`
- Test: `tests/test_devices.py`

**Interfaces:**
- Produces:
  - `list_devices() -> dict` → `{"inputs": list[dict], "outputs": list[dict]}`, cada item `{"index": int, "name": str, "rate": int, "in_ch": int, "out_ch": int}`.
  - `find_vbcable(outputs: list[dict]) -> dict | None` → o primeiro output cujo nome contém "cable" (case-insensitive), ou `None`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_devices.py
from backend.devices import find_vbcable


def test_find_vbcable_matches_cable_input():
    outputs = [
        {"index": 3, "name": "Headphones (Realtek)", "rate": 48000, "in_ch": 0, "out_ch": 2},
        {"index": 7, "name": "CABLE Input (VB-Audio Virtual Cable)", "rate": 48000, "in_ch": 0, "out_ch": 2},
    ]
    found = find_vbcable(outputs)
    assert found is not None
    assert found["index"] == 7


def test_find_vbcable_returns_none_when_absent():
    outputs = [{"index": 3, "name": "Headphones (Realtek)", "rate": 48000, "in_ch": 0, "out_ch": 2}]
    assert find_vbcable(outputs) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.14 -m pytest tests/test_devices.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backend.devices'`

- [ ] **Step 3: Write minimal implementation**

```python
# backend/devices.py
from typing import Optional
import pyaudiowpatch as pyaudio


def list_devices() -> dict:
    """Lista dispositivos de entrada e saída disponíveis."""
    pa = pyaudio.PyAudio()
    inputs, outputs = [], []
    try:
        for i in range(pa.get_device_count()):
            d = pa.get_device_info_by_index(i)
            entry = {
                "index": int(d["index"]),
                "name": str(d["name"]),
                "rate": int(d["defaultSampleRate"]),
                "in_ch": int(d["maxInputChannels"]),
                "out_ch": int(d["maxOutputChannels"]),
            }
            if entry["in_ch"] > 0:
                inputs.append(entry)
            if entry["out_ch"] > 0:
                outputs.append(entry)
    finally:
        pa.terminate()
    return {"inputs": inputs, "outputs": outputs}


def find_vbcable(outputs: list[dict]) -> Optional[dict]:
    """Retorna o dispositivo de saída do VB-Cable, ou None se não instalado."""
    for d in outputs:
        if "cable" in d["name"].lower():
            return d
    return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -3.14 -m pytest tests/test_devices.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Manual smoke test of list_devices**

Run: `py -3.14 -c "from backend.devices import list_devices, find_vbcable; d=list_devices(); print('OUTPUTS:'); [print(o) for o in d['outputs']]; print('VBCABLE:', find_vbcable(d['outputs']))"`
Expected: imprime os dispositivos de saída reais. `VBCABLE: None` é esperado até instalarmos o VB-Cable na Task 6.

- [ ] **Step 6: Commit**

```bash
git add backend/devices.py tests/test_devices.py
git commit -m "feat: device enumeration and VB-Cable detection"
```

---

### Task 2: Saída de áudio para dispositivo específico (mp3 → PCM → device)

**Files:**
- Create: `backend/audio_output.py`
- Test: `tests/test_audio_output.py`

**Interfaces:**
- Consumes: nenhum.
- Produces:
  - `mp3_to_pcm(mp3: bytes, rate: int, channels: int) -> bytes` → PCM int16 reamostrado.
  - `play_pcm_to_device(pcm: bytes, device_index: int, rate: int, channels: int) -> None` → toca PCM bloqueante no dispositivo.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_audio_output.py
import asyncio
import edge_tts
from backend.audio_output import mp3_to_pcm


def _make_mp3() -> bytes:
    async def synth():
        comm = edge_tts.Communicate("Hello world, this is a test.", "en-US-JennyNeural")
        buf = bytearray()
        async for chunk in comm.stream():
            if chunk["type"] == "audio":
                buf.extend(chunk["data"])
        return bytes(buf)
    return asyncio.run(synth())


def test_mp3_to_pcm_produces_pcm_at_requested_rate():
    mp3 = _make_mp3()
    pcm = mp3_to_pcm(mp3, rate=48000, channels=2)
    assert isinstance(pcm, bytes)
    # ~1.5s de fala a 48kHz estéreo int16 => muito mais que 10k bytes
    assert len(pcm) > 10000
    # estéreo int16 => múltiplo de 4 bytes por frame
    assert len(pcm) % 4 == 0


def test_mp3_to_pcm_mono_frame_alignment():
    mp3 = _make_mp3()
    pcm = mp3_to_pcm(mp3, rate=16000, channels=1)
    assert len(pcm) % 2 == 0
    assert len(pcm) > 5000
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.14 -m pytest tests/test_audio_output.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backend.audio_output'`

- [ ] **Step 3: Write minimal implementation**

```python
# backend/audio_output.py
import io
import av  # vem junto com faster-whisper
import pyaudiowpatch as pyaudio


def mp3_to_pcm(mp3: bytes, rate: int, channels: int) -> bytes:
    """Decodifica mp3 para PCM int16 packed, reamostrado para rate/channels."""
    layout = "stereo" if channels >= 2 else "mono"
    container = av.open(io.BytesIO(mp3))
    resampler = av.AudioResampler(format="s16", layout=layout, rate=rate)
    out = bytearray()
    for frame in container.decode(audio=0):
        for resampled in resampler.resample(frame):
            out.extend(bytes(resampled.planes[0]))
    # flush do resampler
    for resampled in resampler.resample(None):
        out.extend(bytes(resampled.planes[0]))
    container.close()
    return bytes(out)


def play_pcm_to_device(pcm: bytes, device_index: int, rate: int, channels: int) -> None:
    """Toca PCM int16 bloqueante no dispositivo de saída indicado."""
    pa = pyaudio.PyAudio()
    try:
        stream = pa.open(
            format=pyaudio.paInt16,
            channels=channels,
            rate=rate,
            output=True,
            output_device_index=device_index,
        )
        stream.write(pcm)
        stream.stop_stream()
        stream.close()
    finally:
        pa.terminate()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -3.14 -m pytest tests/test_audio_output.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/audio_output.py tests/test_audio_output.py
git commit -m "feat: audio output to specific device (mp3 decode + resample + playback)"
```

---

### Task 3: TTS para dispositivo específico

**Files:**
- Modify: `backend/tts.py`
- Test: `tests/test_tts.py`

**Interfaces:**
- Consumes: `backend.audio_output.mp3_to_pcm`, `play_pcm_to_device`; `backend.devices.list_devices`.
- Produces:
  - `synthesize_to_mp3_bytes(text: str, lang: str) -> bytes` (async) → mp3 em memória.
  - `speak_to_device(text: str, lang: str, device_index: int) -> None` → síncrono e bloqueante; descobre rate/channels do dispositivo e toca.
  - Mantém `get_voice`, `VOICE_MAP` inalterados.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_tts.py
import asyncio
from backend.tts import synthesize_to_mp3_bytes, get_voice


def test_get_voice_known_and_fallback():
    assert get_voice("en") == "en-US-JennyNeural"
    assert get_voice("pt") == "pt-BR-FranciscaNeural"
    assert get_voice("xx") == "pt-BR-FranciscaNeural"  # fallback


def test_synthesize_to_mp3_bytes_nonempty():
    mp3 = asyncio.run(synthesize_to_mp3_bytes("Olá, teste de voz.", "pt"))
    assert isinstance(mp3, bytes)
    assert len(mp3) > 1000
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.14 -m pytest tests/test_tts.py -v`
Expected: FAIL with `ImportError: cannot import name 'synthesize_to_mp3_bytes'`

- [ ] **Step 3: Write minimal implementation**

Adicionar ao topo de `backend/tts.py` (após os imports existentes):

```python
import pyaudiowpatch as pyaudio
from backend.audio_output import mp3_to_pcm, play_pcm_to_device
```

Adicionar estas funções ao `backend/tts.py`:

```python
async def synthesize_to_mp3_bytes(text: str, lang: str) -> bytes:
    """Sintetiza texto e retorna o mp3 em memória (sem tocar)."""
    voice = get_voice(lang)
    communicate = edge_tts.Communicate(text, voice)
    buf = bytearray()
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            buf.extend(chunk["data"])
    return bytes(buf)


def _device_format(device_index: int) -> tuple[int, int]:
    """Retorna (rate, channels) nativos do dispositivo de saída."""
    pa = pyaudio.PyAudio()
    try:
        d = pa.get_device_info_by_index(device_index)
        rate = int(d["defaultSampleRate"])
        channels = 2 if int(d["maxOutputChannels"]) >= 2 else 1
        return rate, channels
    finally:
        pa.terminate()


def speak_to_device(text: str, lang: str, device_index: int) -> None:
    """Sintetiza e toca o texto (bloqueante) no dispositivo indicado."""
    if not text.strip():
        return
    loop = asyncio.new_event_loop()
    try:
        mp3 = loop.run_until_complete(synthesize_to_mp3_bytes(text, lang))
    finally:
        loop.close()
    rate, channels = _device_format(device_index)
    pcm = mp3_to_pcm(mp3, rate=rate, channels=channels)
    play_pcm_to_device(pcm, device_index, rate, channels)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -3.14 -m pytest tests/test_tts.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/tts.py tests/test_tts.py
git commit -m "feat: TTS synthesis to bytes and playback to specific device"
```

---

### Task 4: Inbound auto-detecção + descarte de eco em português

**Files:**
- Modify: `backend/transcriber.py`
- Test: `tests/test_transcriber.py`

**Interfaces:**
- Consumes: `backend.audio.save_audio_chunk`, `CHUNK_BYTES`.
- Produces:
  - `transcribe_and_translate(audio_bytes, source_lang, target_lang, speaker, on_result, detect=False, drop_langs=())` — quando `detect=True`, passa `language=None` ao Whisper e usa o idioma detectado como `source`; se o idioma detectado estiver em `drop_langs`, **descarta** o trecho (não chama `on_result`). `on_result` ganha 4º argumento `detected_lang: str`.
  - `AudioWorker.__init__(..., detect=False, drop_langs=())` repassando os flags.
  - Assinatura nova de `on_result`: `Callable[[str, str, str, str], None]` = `(speaker, original, translation, detected_lang)`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_transcriber.py
import asyncio
import io
import edge_tts
import av
from backend.transcriber import transcribe_and_translate


def _speech_pcm(text: str, voice: str) -> bytes:
    async def synth():
        comm = edge_tts.Communicate(text, voice)
        buf = bytearray()
        async for c in comm.stream():
            if c["type"] == "audio":
                buf.extend(c["data"])
        return bytes(buf)
    mp3 = asyncio.run(synth())
    container = av.open(io.BytesIO(mp3))
    resampler = av.AudioResampler(format="s16", layout="mono", rate=16000)
    out = bytearray()
    for frame in container.decode(audio=0):
        for r in resampler.resample(frame):
            out.extend(bytes(r.planes[0]))
    return bytes(out)


def test_inbound_detects_english_and_translates_to_pt():
    pcm = _speech_pcm("Good morning, how are you today?", "en-US-JennyNeural")
    results = []
    transcribe_and_translate(
        pcm, source_lang="en", target_lang="pt", speaker="Outro",
        on_result=lambda sp, o, t, dl: results.append((sp, o, t, dl)),
        detect=True, drop_langs=("pt",),
    )
    assert len(results) == 1
    assert results[0][3] == "en"          # detected_lang
    assert results[0][2].strip() != ""    # tradução PT não vazia


def test_inbound_drops_portuguese_echo():
    pcm = _speech_pcm("Olá, tudo bem com você hoje?", "pt-BR-FranciscaNeural")
    results = []
    transcribe_and_translate(
        pcm, source_lang="en", target_lang="pt", speaker="Outro",
        on_result=lambda sp, o, t, dl: results.append((sp, o, t, dl)),
        detect=True, drop_langs=("pt",),
    )
    assert results == []  # eco em PT descartado
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.14 -m pytest tests/test_transcriber.py -v`
Expected: FAIL (`on_result` recebe 3 args / `detect` não existe → TypeError)

- [ ] **Step 3: Write minimal implementation**

Substituir `transcribe_and_translate` em `backend/transcriber.py` por:

```python
def transcribe_and_translate(
    audio_bytes: bytes,
    source_lang: str,
    target_lang: str,
    speaker: str,
    on_result: Callable[[str, str, str, str], None],
    detect: bool = False,
    drop_langs: tuple = (),
) -> None:
    print(f"[Transcriber] {len(audio_bytes)} bytes speaker={speaker} detect={detect}")
    path = save_audio_chunk(audio_bytes)
    try:
        model = get_model()
        lang_arg = None if detect else source_lang
        segments, info = model.transcribe(path, language=lang_arg)
        detected = getattr(info, "language", source_lang) or source_lang
        if detected in drop_langs:
            print(f"[Transcriber] descartado (idioma {detected} em drop_langs)")
            return
        original = " ".join(s.text for s in segments).strip()
        print(f"[Transcriber] [{detected}] '{original}'")
        if not original:
            return
        effective_source = detected if detect else source_lang
        translation = translate_text(original, effective_source, target_lang)
        on_result(speaker, original, translation, detected)
    except Exception as e:
        print(f"[Transcriber] ERRO: {e}")
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass
```

Atualizar `AudioWorker` para repassar os flags:

```python
class AudioWorker:
    def __init__(self, queue, source_lang: str, target_lang: str,
                 speaker: str, on_result: Callable,
                 detect: bool = False, drop_langs: tuple = ()):
        self.queue = queue
        self.source_lang = source_lang
        self.target_lang = target_lang
        self.speaker = speaker
        self.on_result = on_result
        self.detect = detect
        self.drop_langs = drop_langs
        self._thread: Optional[threading.Thread] = None

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        buffer = b""
        while True:
            chunk = self.queue.get()
            if chunk is None:
                break
            buffer += chunk
            if len(buffer) >= CHUNK_BYTES:
                data = buffer
                buffer = b""
                threading.Thread(
                    target=transcribe_and_translate,
                    args=(data, self.source_lang, self.target_lang,
                          self.speaker, self.on_result),
                    kwargs={"detect": self.detect, "drop_langs": self.drop_langs},
                    daemon=True,
                ).start()
```

Garantir que o modelo padrão seja `base` (mais robusto para auto-detect). Em `get_model`, trocar o default:

```python
            model_size = os.getenv("WHISPER_MODEL", "base")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -3.14 -m pytest tests/test_transcriber.py -v`
Expected: PASS (2 passed). Nota: primeira execução baixa o modelo `base` (~140MB), pode demorar.

- [ ] **Step 5: Commit**

```bash
git add backend/transcriber.py tests/test_transcriber.py
git commit -m "feat: inbound language auto-detect with portuguese echo drop, base model"
```

---

### Task 5: Seleção de dispositivos na captura + gate half-duplex

**Files:**
- Modify: `backend/audio.py`
- Test: `tests/test_audio_capture.py`

**Interfaces:**
- Consumes: nenhum novo.
- Produces:
  - `AudioCapture(mic_index: int | None = None, loopback_index: int | None = None)` — usa os índices quando fornecidos; `None` mantém o comportamento atual (default mic / `get_default_wasapi_loopback`).
  - `AudioCapture.pause_loopback()` / `AudioCapture.resume_loopback()` — quando pausado, os chunks de loopback lidos são **descartados** (não vão para `spk_queue`), evitando capturar o próprio TTS inbound.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_audio_capture.py
from backend.audio import AudioCapture


def test_pause_resume_flags_default_running():
    cap = AudioCapture()
    assert cap.loopback_paused is False
    cap.pause_loopback()
    assert cap.loopback_paused is True
    cap.resume_loopback()
    assert cap.loopback_paused is False


def test_accepts_device_indices():
    cap = AudioCapture(mic_index=1, loopback_index=9)
    assert cap.mic_index == 1
    assert cap.loopback_index == 9
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.14 -m pytest tests/test_audio_capture.py -v`
Expected: FAIL (`AudioCapture()` não aceita kwargs / sem `loopback_paused`)

- [ ] **Step 3: Write minimal implementation**

Substituir `__init__` e adicionar controles/seleção em `backend/audio.py`:

```python
    def __init__(self, mic_index: int | None = None, loopback_index: int | None = None):
        self.mic_queue: queue.Queue = queue.Queue()
        self.spk_queue: queue.Queue = queue.Queue()
        self._running = False
        self._threads: list[threading.Thread] = []
        self.mic_index = mic_index
        self.loopback_index = loopback_index
        self.loopback_paused = False

    def pause_loopback(self):
        self.loopback_paused = True

    def resume_loopback(self):
        self.loopback_paused = False
```

No `_capture_mic`, usar o índice quando fornecido:

```python
            stream = pa.open(format=pyaudio.paInt16, channels=1, rate=RATE,
                             input=True, frames_per_buffer=CHUNK,
                             input_device_index=self.mic_index)
```

No `_capture_loopback`, escolher o dispositivo e respeitar o pause:

```python
            if self.loopback_index is not None:
                device = pa.get_device_info_by_index(self.loopback_index)
            else:
                device = pa.get_default_wasapi_loopback()
```

E, dentro do `while self._running:`, após obter `arr` reamostrado, antes do `put`:

```python
                if self.loopback_paused:
                    continue
                self.spk_queue.put(arr.tobytes())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -3.14 -m pytest tests/test_audio_capture.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/audio.py tests/test_audio_capture.py
git commit -m "feat: device selection and half-duplex pause for loopback capture"
```

---

### Task 6: Instalar e validar o VB-Cable

**Files:** nenhum de código (instalação de sistema + verificação).

**Interfaces:** depende de `backend.devices.find_vbcable` (Task 1).

- [ ] **Step 1: Baixar o VB-Cable**

Baixar o pacote oficial (VB-Audio Virtual Cable, freeware) de https://vb-audio.com/Cable/ para a pasta de downloads. É um ZIP com `VBCABLE_Setup_x64.exe`.

- [ ] **Step 2: Instalar**

Extrair e executar `VBCABLE_Setup_x64.exe` **como administrador**, clicar em "Install Driver", e **reiniciar o Windows** (exigido pelo driver).

- [ ] **Step 3: Verificar que o app enxerga o dispositivo**

Run: `py -3.14 -c "from backend.devices import list_devices, find_vbcable; o=list_devices()['outputs']; print(find_vbcable(o))"`
Expected: imprime um dict com `name` contendo "CABLE Input" e um `index` válido (não `None`).

- [ ] **Step 4: Commit (registro do marco)**

```bash
git commit --allow-empty -m "chore: VB-Cable installed and detected by device enumeration"
```

---

### Task 7: Reescrever a sessão para pipelines direcionais com roteamento de saída

**Files:**
- Modify: `backend/session.py`
- Test: `tests/test_session.py`

**Interfaces:**
- Consumes: `AudioCapture` (Task 5), `AudioWorker`/`transcribe_and_translate` (Task 4), `speak_to_device` (Task 3).
- Produces:
  - `RecordingSession(user_id, other_lang, websocket, loop, headphone_index, vbcable_index, mic_index=None, loopback_index=None)`. `my_lang` é fixo `"pt"`.
  - Inbound (loopback, speaker `"Outro"`): `detect=True`, `drop_langs=("pt",)`, traduz → PT, fala no **headphone_index**, com pause/resume do loopback ao redor do TTS (anti-eco).
  - Outbound (mic, speaker `"Você"`): source `pt`, traduz → `other_lang`, fala no **vbcable_index**.
  - `_handle_result(speaker, original, translation, detected_lang)` decide rota de saída e envia o JSON ao websocket.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_session.py
from unittest.mock import patch
from backend.session import RecordingSession


class _FakeWS:
    pass


def _make_session():
    # loop e websocket não são exercitados neste teste de roteamento
    return RecordingSession(
        user_id=1, other_lang="en", websocket=_FakeWS(), loop=None,
        headphone_index=3, vbcable_index=7,
    )


def test_inbound_routes_to_headphones_and_pauses_loopback():
    s = _make_session()
    calls = {"spoken": [], "paused": 0, "resumed": 0}
    s.audio.pause_loopback = lambda: calls.__setitem__("paused", calls["paused"] + 1)
    s.audio.resume_loopback = lambda: calls.__setitem__("resumed", calls["resumed"] + 1)
    s._send = lambda entry: None  # não tocar no websocket real
    with patch("backend.session.speak_to_device",
               lambda text, lang, idx: calls["spoken"].append((text, lang, idx))):
        s._handle_result("Outro", "Hello", "Olá", "en")
    assert calls["spoken"] == [("Olá", "pt", 3)]   # PT no fone
    assert calls["paused"] == 1 and calls["resumed"] == 1  # half-duplex


def test_outbound_routes_to_vbcable():
    s = _make_session()
    spoken = []
    s._send = lambda entry: None
    with patch("backend.session.speak_to_device",
               lambda text, lang, idx: spoken.append((text, lang, idx))):
        s._handle_result("Você", "Olá", "Hello", "pt")
    assert spoken == [("Hello", "en", 7)]  # tradução EN no VB-Cable
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.14 -m pytest tests/test_session.py -v`
Expected: FAIL (`RecordingSession` não aceita os novos kwargs / sem `_handle_result`)

- [ ] **Step 3: Write minimal implementation**

Substituir `backend/session.py` por:

```python
import asyncio
import datetime
from typing import Optional
from fastapi import WebSocket
from backend.audio import AudioCapture
from backend.transcriber import AudioWorker
from backend.tts import speak_to_device

MY_LANG = "pt"


class RecordingSession:
    """Sessão de intérprete bidirecional para um usuário."""

    def __init__(self, user_id: int, other_lang: str, websocket: WebSocket,
                 loop: Optional[asyncio.AbstractEventLoop],
                 headphone_index: int, vbcable_index: int,
                 mic_index: Optional[int] = None,
                 loopback_index: Optional[int] = None):
        self.user_id = user_id
        self.other_lang = other_lang
        self.websocket = websocket
        self.loop = loop
        self.headphone_index = headphone_index
        self.vbcable_index = vbcable_index
        self.audio = AudioCapture(mic_index=mic_index, loopback_index=loopback_index)
        self.transcriptions: list[dict] = []
        self.started_at = datetime.datetime.now()
        self._workers: list[AudioWorker] = []

    def _send(self, entry: dict):
        if self.loop is not None:
            asyncio.run_coroutine_threadsafe(
                self.websocket.send_json(entry), self.loop
            )

    def _handle_result(self, speaker: str, original: str,
                       translation: str, detected_lang: str):
        entry = {
            "type": "transcription",
            "speaker": speaker,
            "original": original,
            "translation": translation,
            "detected_lang": detected_lang,
            "timestamp": datetime.datetime.now().strftime("%H:%M:%S"),
        }
        self.transcriptions.append(entry)
        self._send(entry)
        if speaker == "Outro":
            # PT no fone, pausando o loopback para não capturar o próprio TTS
            self.audio.pause_loopback()
            try:
                speak_to_device(translation, MY_LANG, self.headphone_index)
            finally:
                self.audio.resume_loopback()
        else:
            # tradução no idioma da outra pessoa, injetada no VB-Cable
            speak_to_device(translation, self.other_lang, self.vbcable_index)

    def start(self):
        self.audio.start()
        worker_in = AudioWorker(
            self.audio.spk_queue, source_lang="en", target_lang=MY_LANG,
            speaker="Outro", on_result=self._handle_result,
            detect=True, drop_langs=("pt",),
        )
        worker_out = AudioWorker(
            self.audio.mic_queue, source_lang=MY_LANG, target_lang=self.other_lang,
            speaker="Você", on_result=self._handle_result,
        )
        worker_in.start()
        worker_out.start()
        self._workers = [worker_in, worker_out]

    def stop(self) -> list[dict]:
        self.audio.stop()
        return self.transcriptions
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -3.14 -m pytest tests/test_session.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/session.py tests/test_session.py
git commit -m "feat: directional session pipelines with output routing and anti-echo"
```

---

### Task 8: Endpoint de dispositivos + plumbing no WebSocket

**Files:**
- Modify: `backend/main.py`
- Test: `tests/test_devices_endpoint.py`

**Interfaces:**
- Consumes: `backend.devices.list_devices`, `find_vbcable`; `RecordingSession` novo (Task 7).
- Produces:
  - `GET /devices` → `{"inputs": [...], "outputs": [...], "vbcable": {...}|null}`.
  - WS `start` agora aceita: `other_language`, `headphone_index`, `vbcable_index`, opcional `mic_index`, `loopback_index`, e instancia `RecordingSession` com eles.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_devices_endpoint.py
from fastapi.testclient import TestClient
from unittest.mock import patch
import backend.main as main


def test_devices_endpoint_shape():
    fake = {
        "inputs": [{"index": 1, "name": "Mic", "rate": 48000, "in_ch": 1, "out_ch": 0}],
        "outputs": [{"index": 7, "name": "CABLE Input", "rate": 48000, "in_ch": 0, "out_ch": 2}],
    }
    with patch.object(main, "list_devices", lambda: fake):
        client = TestClient(main.app)
        r = client.get("/devices")
    assert r.status_code == 200
    body = r.json()
    assert body["inputs"][0]["name"] == "Mic"
    assert body["vbcable"]["index"] == 7
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.14 -m pytest tests/test_devices_endpoint.py -v`
Expected: FAIL (rota `/devices` inexistente → 404)

- [ ] **Step 3: Write minimal implementation**

Adicionar import em `backend/main.py`:

```python
from backend.devices import list_devices, find_vbcable
```

Adicionar a rota (após `index`):

```python
@app.get("/devices")
async def devices():
    data = list_devices()
    return {
        "inputs": data["inputs"],
        "outputs": data["outputs"],
        "vbcable": find_vbcable(data["outputs"]),
    }
```

Atualizar o bloco `start` do WebSocket para usar a nova assinatura de `RecordingSession`:

```python
            if data.get("action") == "start":
                async with aiosqlite.connect(DATABASE_URL) as db:
                    db.row_factory = aiosqlite.Row
                    cursor = await db.execute("SELECT * FROM users WHERE id = ?", (user_id,))
                    row = await cursor.fetchone()
                other_lang = data.get("other_language", row["other_language"] if row else "en")
                headphone_index = int(data["headphone_index"])
                vbcable_index = int(data["vbcable_index"])
                mic_index = data.get("mic_index")
                loopback_index = data.get("loopback_index")
                session = RecordingSession(
                    user_id=user_id, other_lang=other_lang, websocket=websocket, loop=loop,
                    headphone_index=headphone_index, vbcable_index=vbcable_index,
                    mic_index=int(mic_index) if mic_index is not None else None,
                    loopback_index=int(loopback_index) if loopback_index is not None else None,
                )
                session.start()
                active_sessions[user_id] = session
                await websocket.send_json({"type": "status", "status": "recording"})
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -3.14 -m pytest tests/test_devices_endpoint.py -v`
Expected: PASS (1 passed)

- [ ] **Step 5: Run full suite to check for regressions**

Run: `py -3.14 -m pytest -v`
Expected: todos passam.

- [ ] **Step 6: Commit**

```bash
git add backend/main.py tests/test_devices_endpoint.py
git commit -m "feat: /devices endpoint and websocket device/lang plumbing"
```

---

### Task 9: UI — painel de dispositivos, idioma, status do VB-Cable, console bidirecional

**Files:**
- Modify: `static/index.html`
- Modify: `static/app.js`
- Modify: `static/style.css`

**Interfaces:**
- Consumes: `GET /devices`; WS `start` com `{action, other_language, headphone_index, vbcable_index, mic_index?, loopback_index?}`; mensagens `{type:"transcription", speaker, original, translation, detected_lang, timestamp}`.

- [ ] **Step 1: Adicionar painel de configuração no HTML**

Em `static/index.html`, na tela de gravação, adicionar antes do botão start:

```html
<section id="device-config" class="device-config">
  <label>Seu fone (saída em PT):
    <select id="sel-headphone"></select>
  </label>
  <label>Microfone (sua voz):
    <select id="sel-mic"></select>
  </label>
  <label>Loopback (voz da outra pessoa):
    <select id="sel-loopback"></select>
  </label>
  <label>Idioma da outra pessoa:
    <select id="sel-other-lang">
      <option value="en">Inglês</option>
      <option value="es">Espanhol</option>
      <option value="fr">Francês</option>
      <option value="de">Alemão</option>
      <option value="it">Italiano</option>
    </select>
  </label>
  <p id="vbcable-status" class="vbcable-status"></p>
</section>
```

- [ ] **Step 2: Carregar dispositivos e checar VB-Cable no app.js**

Adicionar em `static/app.js` uma função chamada ao entrar na tela de gravação:

```javascript
let vbcableIndex = null;

async function loadDevices() {
  const res = await fetch('/devices');
  const data = await res.json();
  const inputs = data.inputs, outputs = data.outputs;

  const fill = (el, list, key) => {
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
```

- [ ] **Step 3: Enviar a config no start do WebSocket**

Localizar onde o app.js envia `{action: 'start', ...}` e substituir o payload por:

```javascript
  ws.send(JSON.stringify({
    action: 'start',
    other_language: document.getElementById('sel-other-lang').value,
    headphone_index: parseInt(document.getElementById('sel-headphone').value, 10),
    vbcable_index: vbcableIndex,
    mic_index: parseInt(document.getElementById('sel-mic').value, 10),
    loopback_index: parseInt(document.getElementById('sel-loopback').value, 10),
  }));
```

Antes de enviar, bloquear se não houver VB-Cable:

```javascript
  if (vbcableIndex === null) {
    alert('Instale o VB-Cable antes de iniciar (necessário para enviar sua voz traduzida).');
    return;
  }
```

- [ ] **Step 4: Renderizar transcrição com o idioma detectado**

Localizar o handler de mensagens `transcription` no app.js e garantir que use os campos novos. Renderizar na coluna certa por `speaker` e mostrar `detected_lang` no inbound:

```javascript
  if (msg.type === 'transcription') {
    const isOther = msg.speaker === 'Outro';
    const col = isOther ? document.getElementById('col-other') : document.getElementById('col-you');
    const div = document.createElement('div');
    div.className = 'line';
    const langTag = isOther && msg.detected_lang ? ` [${msg.detected_lang}]` : '';
    div.innerHTML = `<span class="t">${msg.timestamp}${langTag}</span>
                     <span class="orig">${msg.original}</span>
                     <span class="trad">${msg.translation}</span>`;
    col.appendChild(div);
    col.scrollTop = col.scrollHeight;
  }
```

Garantir que existam os contêineres de duas colunas no HTML (`col-other`, `col-you`); se não existirem, adicioná-los na tela de gravação:

```html
<div class="console">
  <div class="column"><h3>Outra pessoa</h3><div id="col-other" class="lines"></div></div>
  <div class="column"><h3>Você</h3><div id="col-you" class="lines"></div></div>
</div>
```

- [ ] **Step 5: Estilo das duas colunas e status**

Adicionar em `static/style.css`:

```css
.device-config { display: grid; gap: 8px; margin-bottom: 16px; }
.device-config label { display: flex; flex-direction: column; font-size: 14px; gap: 4px; }
.vbcable-status.ok { color: #4 caf50; }
.vbcable-status.warn { color: #ff9800; }
.console { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.column { background: #1b1b1f; border-radius: 12px; padding: 12px; }
.lines { max-height: 50vh; overflow-y: auto; display: flex; flex-direction: column; gap: 8px; }
.line { display: flex; flex-direction: column; gap: 2px; padding: 8px; background: #232329; border-radius: 8px; }
.line .t { font-size: 11px; opacity: .6; }
.line .orig { font-size: 13px; opacity: .8; }
.line .trad { font-size: 15px; font-weight: 600; }
```

(Corrigir `#4 caf50` → `#4caf50` ao colar; sem espaço.)

- [ ] **Step 6: Verificação manual da UI**

Run: `py -3.14 -m uvicorn backend.main:app --port 8001`
Abrir http://localhost:8001, logar, ir à tela de gravação. Verificar: dropdowns preenchidos com dispositivos reais; status do VB-Cable correto (✅ após Task 6); duas colunas visíveis.

- [ ] **Step 7: Commit**

```bash
git add static/index.html static/app.js static/style.css
git commit -m "feat: device config panel, language selector, VB-Cable status and two-column console"
```

---

### Task 10: Verificação end-to-end numa call real

**Files:** nenhum (verificação manual).

- [ ] **Step 1: Configurar o app de call**

Abrir o app de call (ex.: Google Meet). Em configurações de áudio, definir o **microfone** como `CABLE Output (VB-Audio Virtual Cable)` e a **saída/alto-falante** como seu fone.

- [ ] **Step 2: Configurar o intérprete**

No app: fone = seu fone; mic = seu microfone físico; loopback = o dispositivo de loopback do seu fone; idioma da outra pessoa = Inglês. Iniciar.

- [ ] **Step 3: Testar inbound**

A outra pessoa (ou um vídeo em inglês na call) fala. Esperado: em ~2–4s você ouve a tradução em português no fone e a linha aparece na coluna "Outra pessoa" com `[en]`. Sem loop de eco (o app não deve transcrever a própria voz PT).

- [ ] **Step 4: Testar outbound**

Você fala em português no mic. Esperado: a outra pessoa ouve a tradução em inglês (vinda do CABLE Output) e a linha aparece na coluna "Você".

- [ ] **Step 5: Registrar resultado**

Anotar latência percebida e qualquer eco/erro. Se houver eco no inbound, aumentar a janela de pausa do loopback. Commit de marco:

```bash
git commit --allow-empty -m "test: end-to-end bidirectional interpreter verified on live call"
```

---

## Self-Review

**Spec coverage:**
- Plataforma Windows + VB-Cable → Tasks 5, 6, 7, 10. ✅
- Inbound auto-detect EN/ES → PT, modelo base → Task 4. ✅
- Outbound PT → idioma escolhido, injeção VB-Cable → Tasks 3, 7, 8, 9. ✅
- Entrada de texto no inbound → **não coberto na Fase 1** (YAGNI para o MVP de voz; adicionar como follow-up se desejado). ⚠️ Anotado.
- Roteamento de saída (fone vs VB-Cable) → Tasks 2, 3, 7. ✅
- Anti-eco (half-duplex + descarte PT) → Tasks 4, 5, 7. ✅
- UI duas colunas + dispositivos + status VB-Cable → Task 9. ✅
- Persistência Supabase → **Fase 2** (fora deste plano). ✅
- Sem dependência de áudio nova → Tasks 2, 3 usam `av` + `pyaudiowpatch`. ✅

**Placeholder scan:** sem TBD/TODO; todo passo de código tem código real. O único item adiado (texto inbound) está explicitamente marcado como fora de escopo, não como placeholder.

**Type consistency:** `on_result(speaker, original, translation, detected_lang)` consistente entre Tasks 4 e 7. `RecordingSession(...headphone_index, vbcable_index...)` consistente entre Tasks 7 e 8. `list_devices()`/`find_vbcable()` consistentes entre Tasks 1, 8. `speak_to_device(text, lang, index)` consistente entre Tasks 3, 7. ✅

**Nota de teste:** partes de I/O de áudio em hardware (tocar em dispositivo, captura real) têm verificação manual (Tasks 6, 9, 10); a lógica pura e decodificável tem testes automatizados (Tasks 1–5, 7, 8).
