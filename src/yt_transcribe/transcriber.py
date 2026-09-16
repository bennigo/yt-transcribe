"""Audio transcription via faster-whisper (CTranslate2 backend)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class Segment:
    start: float
    end: float
    text: str


@dataclass
class Transcript:
    segments: list[Segment]
    language: str
    language_probability: float

    @property
    def text(self) -> str:
        return " ".join(seg.text.strip() for seg in self.segments)


def transcribe(
    audio_path: Path,
    model: str = "medium",
    language: str | None = None,
    device: str = "auto",
) -> Transcript:
    """Transcribe an audio file using faster-whisper.

    Args:
        audio_path: Path to audio file (WAV, MP3, etc.)
        model: Whisper model size (tiny/base/small/medium/large-v3)
        language: Language code or None for auto-detection
        device: "cuda", "cpu", or "auto"
    """
    from faster_whisper import WhisperModel

    if device == "auto":
        device = _detect_device()

    compute_type = "float16" if device == "cuda" else "int8"
    print(f"Using device: {device} (compute: {compute_type})")

    whisper = WhisperModel(model, device=device, compute_type=compute_type)

    lang_arg = language if language and language != "auto" else None

    segments_iter, info = whisper.transcribe(
        str(audio_path),
        language=lang_arg,
        beam_size=5,
        vad_filter=True,
    )

    segments = [
        Segment(start=seg.start, end=seg.end, text=seg.text)
        for seg in segments_iter
    ]

    # VAD can aggressively filter singing/music — retry without it
    if not segments:
        print("VAD filter returned 0 segments, retrying without VAD...")
        segments_iter, info = whisper.transcribe(
            str(audio_path),
            language=lang_arg,
            beam_size=5,
            vad_filter=False,
        )
        segments = [
            Segment(start=seg.start, end=seg.end, text=seg.text)
            for seg in segments_iter
        ]

    return Transcript(
        segments=segments,
        language=info.language,
        language_probability=info.language_probability,
    )


def _detect_device() -> str:
    """Check if CUDA is available for GPU acceleration."""
    try:
        import ctranslate2

        if ctranslate2.get_supported_compute_types("cuda"):
            return "cuda"
    except Exception:
        pass
    return "cpu"
