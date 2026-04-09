# tests/test_storage.py
import pytest
import os
import tempfile
from backend.storage import build_transcript_text, get_save_folder

def test_build_transcript_text():
    transcriptions = [
        {"timestamp": "14:00:01", "speaker": "Você", "original": "Bom dia", "translation": "Good morning"},
        {"timestamp": "14:00:05", "speaker": "Outro", "original": "Good morning", "translation": "Bom dia"},
    ]
    result = build_transcript_text(transcriptions)
    assert "[14:00:01] Você: Bom dia" in result
    assert "↳ Good morning" in result

def test_get_save_folder_creates_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        folder = get_save_folder(tmpdir, "joao", "20260101_1400")
        assert os.path.isdir(folder)
        assert "joao" in folder
        assert "20260101_1400" in folder
