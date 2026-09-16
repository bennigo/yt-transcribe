"""Tests for yt_transcribe.transcriber (faster-whisper / ctranslate2 are faked)."""

from __future__ import annotations

import sys
import types

import pytest

import yt_transcribe.transcriber as transcriber


def _install_ctranslate2(monkeypatch, supported):
    mod = types.ModuleType("ctranslate2")
    mod.get_supported_compute_types = lambda device: supported
    monkeypatch.setitem(sys.modules, "ctranslate2", mod)


def test_detect_device_returns_cuda_when_supported(monkeypatch):
    _install_ctranslate2(monkeypatch, {"float16", "int8"})
    assert transcriber._detect_device() == "cuda"


def test_detect_device_returns_cpu_when_unsupported(monkeypatch):
    _install_ctranslate2(monkeypatch, set())
    assert transcriber._detect_device() == "cpu"


def test_detect_device_returns_cpu_when_ctranslate2_is_missing(monkeypatch):
    monkeypatch.setitem(sys.modules, "ctranslate2", None)
    assert transcriber._detect_device() == "cpu"


@pytest.fixture
def fake_whisper(monkeypatch):
    """Install a fake faster_whisper whose first VAD pass can return nothing."""

    def install(vad_returns_nothing: bool = False):
        calls: list[dict] = []

        class Model:
            def __init__(self, model, device=None, compute_type=None):
                self.model = model
                self.device = device
                self.compute_type = compute_type

            def transcribe(self, audio, language=None, beam_size=5, vad_filter=True):
                calls.append({"audio": audio, "language": language, "vad_filter": vad_filter})
                info = types.SimpleNamespace(language="en", language_probability=0.98)
                if vad_returns_nothing and vad_filter:
                    return iter([]), info
                segs = [
                    types.SimpleNamespace(start=0.0, end=3.0, text=" Hello there."),
                    types.SimpleNamespace(start=3.0, end=6.0, text=" General Kenobi."),
                ]
                return iter(segs), info

        mod = types.ModuleType("faster_whisper")
        mod.WhisperModel = Model
        monkeypatch.setitem(sys.modules, "faster_whisper", mod)
        return calls

    return install


def test_transcribe_maps_segments_and_language(fake_whisper, tmp_path, monkeypatch):
    fake_whisper()
    monkeypatch.setattr(transcriber, "_detect_device", lambda: "cpu")
    audio = tmp_path / "a.wav"
    audio.write_bytes(b"")

    t = transcriber.transcribe(audio, model="small")
    assert [s.text for s in t.segments] == [" Hello there.", " General Kenobi."]
    assert t.language == "en"
    assert t.language_probability == pytest.approx(0.98)
    assert t.text == "Hello there. General Kenobi."


def test_transcribe_uses_int8_on_cpu_and_float16_on_cuda(fake_whisper, tmp_path, monkeypatch):
    fake_whisper()
    audio = tmp_path / "a.wav"
    audio.write_bytes(b"")
    seen = {}

    monkeypatch.setattr(transcriber, "_detect_device", lambda: "cuda")
    # Capture the compute_type the model was constructed with.
    original = sys.modules["faster_whisper"].WhisperModel

    class Spy(original):
        def __init__(self, model, device=None, compute_type=None):
            seen["device"] = device
            seen["compute_type"] = compute_type
            super().__init__(model, device, compute_type)

    sys.modules["faster_whisper"].WhisperModel = Spy
    transcriber.transcribe(audio, model="tiny")
    assert seen == {"device": "cuda", "compute_type": "float16"}


def test_transcribe_retries_without_vad_when_vad_filters_everything(
    fake_whisper, tmp_path, monkeypatch
):
    calls = fake_whisper(vad_returns_nothing=True)
    monkeypatch.setattr(transcriber, "_detect_device", lambda: "cpu")
    audio = tmp_path / "a.wav"
    audio.write_bytes(b"")

    t = transcriber.transcribe(audio, model="tiny")
    assert len(calls) == 2
    assert calls[0]["vad_filter"] is True
    assert calls[1]["vad_filter"] is False
    assert len(t.segments) == 2  # the retry produced output


def test_transcribe_passes_language_through_but_maps_auto_to_none(
    fake_whisper, tmp_path, monkeypatch
):
    calls = fake_whisper()
    monkeypatch.setattr(transcriber, "_detect_device", lambda: "cpu")
    audio = tmp_path / "a.wav"
    audio.write_bytes(b"")

    transcriber.transcribe(audio, language="is")
    assert calls[-1]["language"] == "is"

    transcriber.transcribe(audio, language="auto")
    assert calls[-1]["language"] is None
    transcriber.transcribe(audio, language=None)
    assert calls[-1]["language"] is None
