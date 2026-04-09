import pytest
from unittest.mock import MagicMock, patch

def test_translate_same_language_returns_original():
    from backend.transcriber import translate_text
    result = translate_text("hello world", source="en", target="en")
    assert result == "hello world"

def test_translate_returns_string():
    from backend.transcriber import translate_text
    with patch("backend.transcriber.GoogleTranslator") as mock_cls:
        mock_cls.return_value.translate.return_value = "olá mundo"
        result = translate_text("hello world", source="en", target="pt")
    assert isinstance(result, str)
    assert len(result) > 0
