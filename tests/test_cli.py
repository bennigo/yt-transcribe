"""Tests for yt_transcribe.cli — arg parsing, dedup, and the main flows (mocked)."""

from __future__ import annotations

from pathlib import Path

import pytest

import yt_transcribe.cli as cli
import yt_transcribe.config as config
import yt_transcribe.downloader as downloader
import yt_transcribe.transcriber as transcriber
from yt_transcribe.downloader import AudioResult, VideoMeta
from yt_transcribe.transcriber import Segment, Transcript

URL = "https://www.youtube.com/watch?v=gNbHpt_KODU"
VID = "gNbHpt_KODU"


# --- video id extraction ---------------------------------------------------


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://www.youtube.com/watch?v=gNbHpt_KODU", VID),
        ("https://www.youtube.com/watch?v=gNbHpt_KODU&t=42s", VID),
        ("https://youtu.be/gNbHpt_KODU", VID),
        ("https://youtu.be/gNbHpt_KODU?si=abc", VID),
        ("https://www.youtube.com/live/gNbHpt_KODU", VID),
        ("https://www.youtube.com/embed/gNbHpt_KODU", VID),
        ("https://www.youtube.com/v/gNbHpt_KODU", VID),
    ],
)
def test_extract_video_id_accepts_every_url_shape(url, expected):
    assert cli._extract_video_id(url) == expected


@pytest.mark.parametrize(
    "url", ["https://vimeo.com/12345", "https://example.com/watch?v=tooshort", "not a url", ""]
)
def test_extract_video_id_returns_none_for_non_youtube(url):
    assert cli._extract_video_id(url) is None


# --- dedup -----------------------------------------------------------------


def test_check_vault_duplicate_finds_an_existing_note(tmp_path):
    note = tmp_path / "Journal" / "note.md"
    note.parent.mkdir(parents=True)
    note.write_text(f'---\nresource: "https://youtu.be/{VID}"\n---\n', encoding="utf-8")
    assert cli._check_vault_duplicate(VID, tmp_path) == note


def test_check_vault_duplicate_returns_none_when_absent(tmp_path):
    (tmp_path / "other.md").write_text("nothing here", encoding="utf-8")
    assert cli._check_vault_duplicate(VID, tmp_path) is None


def test_check_vault_duplicate_returns_none_for_a_missing_root(tmp_path):
    assert cli._check_vault_duplicate(VID, tmp_path / "nope") is None


@pytest.mark.parametrize("skip_dir", [".obsidian", "Assets", "node_modules"])
def test_check_vault_duplicate_skips_hidden_and_asset_dirs(tmp_path, skip_dir):
    d = tmp_path / skip_dir
    d.mkdir()
    (d / "note.md").write_text(VID, encoding="utf-8")
    assert cli._check_vault_duplicate(VID, tmp_path) is None


def test_check_vault_duplicate_ignores_ids_below_the_first_20_lines(tmp_path):
    body = "\n".join(f"line {i}" for i in range(25)) + f"\n{VID}\n"
    (tmp_path / "long.md").write_text(body, encoding="utf-8")
    assert cli._check_vault_duplicate(VID, tmp_path) is None


# --- output writing --------------------------------------------------------


def test_write_output_creates_directories(tmp_path):
    dest = tmp_path / "a" / "b"
    cli._write_output("content", "note.md", dest)
    assert (dest / "note.md").read_text() == "content"


# --- parser ----------------------------------------------------------------


def test_parser_defaults():
    args = cli.build_parser().parse_args([URL])
    assert args.url == URL
    assert args.model is None and args.language is None and args.output_format is None
    assert not (args.subs_only or args.force or args.link_audio or args.keep_audio)


def test_parser_rejects_an_unknown_model():
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args(["-m", "gigantic", URL])


def test_main_requires_a_url_or_file():
    with pytest.raises(SystemExit):
        cli.main([])


def test_subs_only_with_a_local_file_is_rejected():
    with pytest.raises(SystemExit):
        cli.main(["--file", "x.mp3", "--subs-only"])


# --- fixtures --------------------------------------------------------------


@pytest.fixture
def tmp_cfg(tmp_path, monkeypatch):
    """Give main() a Config whose paths all live under tmp_path."""
    paths = {
        "inbox": tmp_path / "vault" / "0.Inbox",
        "media": tmp_path / "media",
        "cache": tmp_path / "cache",
    }

    def fake_load(overrides=None):
        cfg = config.Config()
        cfg.inbox_path = paths["inbox"]
        cfg.media_dir = paths["media"]
        cfg.cache_dir = paths["cache"]
        for k, v in (overrides or {}).items():
            if hasattr(cfg, k):
                setattr(cfg, k, v)
        return cfg

    monkeypatch.setattr(config, "load_config", fake_load)
    return paths


def _fake_meta() -> VideoMeta:
    return VideoMeta("Title", "Channel", "2026-09-16", 2967, "", URL)


def _fake_transcript() -> Transcript:
    return Transcript(
        segments=[Segment(0.0, 3.0, " hello")], language="en", language_probability=0.9
    )


@pytest.fixture
def pipeline(monkeypatch, tmp_path):
    """Replace the download + transcribe stages; records what was called."""
    calls: dict[str, list] = {"download": [], "transcribe": []}

    def fake_download(url, out_dir):
        calls["download"].append(url)
        audio = tmp_path / "cache" / "audio" / f"{VID}.wav"
        audio.parent.mkdir(parents=True, exist_ok=True)
        audio.write_bytes(b"RIFF")
        return AudioResult(path=audio, meta=_fake_meta())

    def fake_transcribe(audio_path, model=None, language=None, device="auto"):
        calls["transcribe"].append({"model": model, "language": language})
        return _fake_transcript()

    monkeypatch.setattr(downloader, "download_audio", fake_download)
    monkeypatch.setattr(downloader, "fetch_metadata", lambda url: _fake_meta())
    monkeypatch.setattr(transcriber, "transcribe", fake_transcribe)
    return calls


def _seed_duplicate(paths) -> None:
    paths["inbox"].mkdir(parents=True, exist_ok=True)
    (paths["inbox"].parent / "existing.md").write_text(
        f"resource: https://youtu.be/{VID}", encoding="utf-8"
    )


# --- main: YouTube flow ----------------------------------------------------


def test_main_writes_a_vault_note(pipeline, tmp_cfg):
    cli.main([URL])
    notes = list(tmp_cfg["inbox"].glob("*.md"))
    assert len(notes) == 1
    assert pipeline["download"] == [URL]
    assert "## Transcript" in notes[0].read_text()


def test_main_honours_an_explicit_output_dir(pipeline, tmp_path, tmp_cfg):
    out = tmp_path / "elsewhere"
    cli.main([URL, "-o", str(out)])
    assert list(out.glob("*.md"))


def test_main_skips_a_video_already_in_the_vault(pipeline, tmp_cfg):
    _seed_duplicate(tmp_cfg)
    with pytest.raises(SystemExit) as exc:
        cli.main([URL])
    assert exc.value.code == 0
    assert pipeline["download"] == [], "must not download a duplicate"


def test_main_force_bypasses_the_dedup_check(pipeline, tmp_cfg):
    _seed_duplicate(tmp_cfg)
    cli.main([URL, "--force"])
    assert pipeline["download"] == [URL]


def test_main_markdown_format_names_the_file_after_the_title(pipeline, tmp_cfg, tmp_path):
    out = tmp_path / "md"
    cli.main([URL, "-f", "markdown", "-o", str(out)])
    assert [f.name for f in out.glob("*.md")] == ["title.md"]


def test_main_deletes_the_audio_by_default(pipeline, tmp_path, tmp_cfg):
    cli.main([URL])
    assert not (tmp_path / "cache" / "audio" / f"{VID}.wav").exists()


def test_main_link_audio_stores_media_and_links_it(pipeline, tmp_cfg):
    cli.main([URL, "--link-audio"])
    assert (tmp_cfg["media"] / f"{VID}.srt").exists()
    assert (tmp_cfg["media"] / f"{VID}.wav").exists()
    note = next(tmp_cfg["inbox"].glob("*.md")).read_text()
    assert "**Audio**" in note
    assert "**Subtitles**" in note


def test_main_keep_audio_leaves_the_file_in_the_cache(pipeline, tmp_path, tmp_cfg):
    cli.main([URL, "--keep-audio"])
    assert (tmp_path / "cache" / "audio" / f"{VID}.wav").exists()


# --- main: subs-only -------------------------------------------------------


def test_subs_only_exits_1_when_no_subtitles(monkeypatch, tmp_cfg):
    monkeypatch.setattr(downloader, "fetch_subtitles", lambda url, lang: None)
    with pytest.raises(SystemExit) as exc:
        cli.main([URL, "--subs-only"])
    assert exc.value.code == 1


def test_subs_only_writes_a_note_from_captions(monkeypatch, tmp_cfg):
    monkeypatch.setattr(downloader, "fetch_subtitles", lambda url, lang: "[00:00] hi")
    monkeypatch.setattr(downloader, "fetch_metadata", lambda url: _fake_meta())
    cli.main([URL, "--subs-only"])
    note = next(tmp_cfg["inbox"].glob("*.md")).read_text()
    assert "existing YouTube subtitles" in note


def test_subs_only_uses_the_configured_language(monkeypatch, tmp_cfg):
    seen = {}

    def fake_subs(url, lang):
        seen["lang"] = lang
        return None

    monkeypatch.setattr(downloader, "fetch_subtitles", fake_subs)
    with pytest.raises(SystemExit):
        cli.main([URL, "--subs-only"])
    assert seen["lang"] == "en"  # 'auto' falls back to en for captions


# --- main: local file ------------------------------------------------------


def test_local_file_writes_note_and_srt(pipeline, tmp_path, tmp_cfg):
    src = tmp_path / "my-talk.mp3"
    src.write_bytes(b"audio")
    out = tmp_path / "out"
    cli.main(["--file", str(src), "-o", str(out)])

    notes = list(out.glob("*.md"))
    assert len(notes) == 1
    assert (out / "my-talk.srt").exists()
    body = notes[0].read_text()
    assert "**Source file**" in body
    assert "**Subtitles**" in body
    assert notes[0].name.endswith("-my-talk.md")


def test_local_file_missing_exits_1(pipeline, tmp_cfg):
    with pytest.raises(SystemExit) as exc:
        cli.main(["--file", "/nope/missing.mp3"])
    assert exc.value.code == 1
