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


def test_learn_other_lang_updates_outbound_target():
    # other_lang começa como palpite e é atualizado por auto-detecção do loopback
    s = _make_session()  # other_lang inicial = "en"
    s._learn_other_lang("es", 0.9)
    assert s.other_lang == "es"
    spoken = []
    s._send = lambda entry: None
    with patch("backend.session.speak_to_device",
               lambda text, lang, idx: spoken.append((text, lang, idx))):
        s._handle_result("Você", "Olá", "Hola", "pt")
    assert spoken == [("Hola", "es", 7)]  # agora sai em ES (idioma aprendido)


def test_learn_other_lang_ignores_my_own_language():
    # Detecções no meu idioma (eco) não viram "idioma do outro"
    s = _make_session()  # my_lang default = "pt", other_lang = "en"
    s._learn_other_lang("pt", 0.99)
    assert s.other_lang == "en"  # inalterado
