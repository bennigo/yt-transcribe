"""Tests for yt_transcribe.downloader (yt-dlp is faked)."""

from __future__ import annotations

import types
from pathlib import Path

import pytest

import yt_transcribe.downloader as downloader
from yt_transcribe.downloader import (
    _clean_vtt,
    _cookie_opts,
    download_audio,
    fetch_metadata,
    fetch_subtitles,
)

INFO = {
    "id": "gNbHpt_KODU",
    "title": "Douglas Macgregor: Ukraine Endgame Is Here",
    "channel": "Glenn Diesen",
    "upload_date": "20260916",
    "duration": 2967,
    "description": "desc",
    "webpage_url": "https://www.youtube.com/watch?v=gNbHpt_KODU",
}


class _FakeYDL:
    """Minimal stand-in for yt_dlp.YoutubeDL."""

    def __init__(self, opts, info=None, side_effect=None):
        self.opts = opts
        self.info = info or {}
        self.side_effect = side_effect

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def extract_info(self, url, download=False):
        self.last_call = ("extract_info", url, download)
        if self.side_effect:
            self.side_effect(self, "extract_info")
        return self.info

    def download(self, urls):
        self.last_call = ("download", urls)
        if self.side_effect:
            self.side_effect(self, "download")


@pytest.fixture
def fake_yt_dlp(monkeypatch):
    """Patch the module reference downloader.py uses, returning an installer."""

    def install(info=None, side_effect=None):
        holder = {}

        def factory(opts):
            ydl = _FakeYDL(opts, info if info is not None else INFO, side_effect)
            holder["ydl"] = ydl
            return ydl

        mod = types.ModuleType("yt_dlp")
        mod.YoutubeDL = factory
        monkeypatch.setattr(downloader, "yt_dlp", mod)
        return holder

    return install


# --- cookies ---------------------------------------------------------------


def test_cookie_opts_default_to_chrome(monkeypatch):
    monkeypatch.delenv("YT_TRANSCRIBE_COOKIES_FROM_BROWSER", raising=False)
    assert _cookie_opts() == {"cookiesfrombrowser": ("chrome",)}


def test_cookie_opts_follow_the_env_var(monkeypatch):
    monkeypatch.setenv("YT_TRANSCRIBE_COOKIES_FROM_BROWSER", "firefox")
    assert _cookie_opts() == {"cookiesfrombrowser": ("firefox",)}


def test_cookie_opts_empty_disables(monkeypatch):
    monkeypatch.setenv("YT_TRANSCRIBE_COOKIES_FROM_BROWSER", "")
    assert _cookie_opts() == {}


def test_cookies_are_passed_to_yt_dlp(fake_yt_dlp, monkeypatch, tmp_path):
    monkeypatch.setenv("YT_TRANSCRIBE_COOKIES_FROM_BROWSER", "chrome")
    holder = fake_yt_dlp()
    fetch_metadata("https://youtu.be/gNbHpt_KODU")
    assert holder["ydl"].opts["cookiesfrombrowser"] == ("chrome",)


# --- metadata / download ---------------------------------------------------


def test_fetch_metadata_maps_fields(fake_yt_dlp):
    fake_yt_dlp()
    m = fetch_metadata("https://www.youtube.com/watch?v=gNbHpt_KODU")
    assert m.title == INFO["title"]
    assert m.channel == "Glenn Diesen"
    assert m.upload_date == "2026-09-16"  # YYYYMMDD → ISO
    assert m.duration == 2967
    assert m.url == INFO["webpage_url"]


def test_fetch_metadata_passes_through_a_missing_date(fake_yt_dlp):
    fake_yt_dlp(info={**INFO, "upload_date": ""})
    assert fetch_metadata("u").upload_date == ""


def test_fetch_metadata_falls_back_for_an_absent_channel(fake_yt_dlp):
    fake_yt_dlp(info={**INFO, "channel": None, "uploader": "Some Uploader"})
    assert fetch_metadata("u").channel == "Some Uploader"


def _writes_wav(ydl, action):
    """Simulate the postprocessor producing <id>.wav next to outtmpl."""
    if action != "extract_info":
        return
    tmpl = ydl.opts["outtmpl"].replace("%(id)s", INFO["id"]).replace("%(ext)s", "wav")
    Path(tmpl).parent.mkdir(parents=True, exist_ok=True)
    Path(tmpl).write_bytes(b"RIFF....WAVE")


def test_download_audio_returns_the_produced_wav(fake_yt_dlp, tmp_path):
    fake_yt_dlp(side_effect=_writes_wav)
    result = download_audio("https://youtu.be/gNbHpt_KODU", tmp_path)
    assert result.path == tmp_path / "gNbHpt_KODU.wav"
    assert result.path.exists()
    assert result.meta.duration == 2967


def test_download_audio_raises_when_nothing_lands(fake_yt_dlp, tmp_path):
    fake_yt_dlp()  # no side effect → no file written
    with pytest.raises(FileNotFoundError):
        download_audio("https://youtu.be/gNbHpt_KODU", tmp_path)


# --- subtitles -------------------------------------------------------------


def test_fetch_subtitles_returns_none_when_absent(fake_yt_dlp):
    fake_yt_dlp(info={"subtitles": {}, "automatic_captions": {}})
    assert fetch_subtitles("u", "en") is None


def test_fetch_subtitles_reads_and_cleans_vtt(fake_yt_dlp, vtt_sample, tmp_path):
    def write_vtt(ydl, action):
        if action != "download":
            return
        outdir = Path(ydl.opts["outtmpl"]).parent
        (outdir / "subs.en.vtt").write_text(vtt_sample, encoding="utf-8")

    fake_yt_dlp(info={"subtitles": {"en": [{"ext": "vtt"}]}}, side_effect=write_vtt)
    out = fetch_subtitles("https://youtu.be/gNbHpt_KODU", "en")
    assert out is not None
    assert "Hello & welcome." in out
    assert "[00:00:00]" in out


# --- vtt cleaning ----------------------------------------------------------


def test_clean_vtt_decodes_html_entities(vtt_sample):
    out = _clean_vtt(vtt_sample)
    assert "&amp;" not in out
    assert "Hello & welcome." in out
    assert "&#39;" not in out
    assert "Kenobi's line." in out


def test_clean_vtt_strips_inline_tags():
    vtt = "WEBVTT\n\n00:00:00.000 --> 00:00:01.000\n<c.colorE5E5E5>hi there</c>\n"
    assert _clean_vtt(vtt) == "[00:00:00] hi there"


def test_clean_vtt_dedupes_consecutive_repeats():
    vtt = (
        "WEBVTT\n\n"
        "00:00:00.000 --> 00:00:02.000\nsame line\n\n"
        "00:00:02.000 --> 00:00:04.000\nsame line\n\n"
        "00:00:04.000 --> 00:00:06.000\ndifferent\n"
    )
    out = _clean_vtt(vtt)
    assert out.count("same line") == 1
    assert "different" in out


def test_clean_vtt_handles_empty_input():
    assert _clean_vtt("") == ""
    assert _clean_vtt("WEBVTT\n\n") == ""
