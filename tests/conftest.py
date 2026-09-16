"""Shared fixtures — everything hermetic (no network, no GPU, no real vault)."""

from __future__ import annotations

import pytest

from yt_transcribe.downloader import VideoMeta
from yt_transcribe.transcriber import Segment


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    """Point the XDG config/cache lookups at a temp dir for every test."""
    import yt_transcribe.config as config

    monkeypatch.setattr(config, "_XDG_CONFIG", tmp_path / "config")
    monkeypatch.setattr(config, "_XDG_CACHE", tmp_path / "cache")
    # load_config exports this via os.environ.setdefault; keep it from leaking.
    monkeypatch.delenv("YT_TRANSCRIBE_COOKIES_FROM_BROWSER", raising=False)
    return tmp_path / "config"


@pytest.fixture
def meta() -> VideoMeta:
    return VideoMeta(
        title="Douglas Macgregor: Ukraine Endgame Is Here",
        channel="Glenn Diesen",
        upload_date="2026-09-16",
        duration=2967,
        description="desc",
        url="https://www.youtube.com/watch?v=gNbHpt_KODU",
    )


@pytest.fixture
def segments() -> list[Segment]:
    return [
        Segment(start=0.0, end=4.0, text="Welcome back, everyone."),
        Segment(start=4.0, end=12.5, text=" We are joined today by Colonel Macgregor."),
        Segment(start=12.5, end=44.0, text="   "),  # blank → skipped
        Segment(start=44.0, end=61.25, text="Let us begin."),
    ]


@pytest.fixture
def vtt_sample() -> str:
    return (
        "WEBVTT\n"
        "Kind: captions\n"
        "Language: en\n\n"
        "00:00:00.000 --> 00:00:03.000\n"
        "Hello &amp; welcome.\n\n"
        "00:00:03.000 --> 00:00:06.000\n"
        "<c>Hello &amp; welcome.</c>\n\n"
        "00:00:06.000 --> 00:00:09.000\n"
        "General Kenobi&#39;s line.\n"
    )
