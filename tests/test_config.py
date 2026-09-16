"""Tests for yt_transcribe.config."""

from __future__ import annotations

import os
from pathlib import Path

from yt_transcribe.config import load_config


def test_defaults_when_no_config_file(monkeypatch, isolated_home):
    monkeypatch.setattr("yt_transcribe.config._XDG_CACHE", Path("/tmp/ytc-cache"))
    cfg = load_config()
    assert cfg.model == "medium"
    assert cfg.language == "auto"
    assert cfg.format == "vault"
    assert cfg.timestamps is True
    assert cfg.keep_audio is False
    assert cfg.cookies_from_browser == "chrome"
    # Generic, non-personal defaults.
    assert cfg.inbox_path == Path.home() / "Obsidian" / "Inbox"
    assert cfg.media_dir == Path.home() / "Obsidian" / "yt-transcribe"
    assert cfg.cache_dir == Path("/tmp/ytc-cache")


def test_toml_overrides_defaults(isolated_home):
    cfgdir = isolated_home
    cfgdir.mkdir(parents=True, exist_ok=True)
    (cfgdir / "config.toml").write_text(
        """
[defaults]
model = "large-v3"
language = "is"
format = "markdown"
timestamps = false

[vault]
inbox_path = "~/vault/0.Inbox"

[media]
dir = "~/vault/media"

[cache]
dir = "~/somewhere/cache"
keep_audio = true

[download]
cookies_from_browser = "firefox"
"""
    )
    cfg = load_config()
    assert cfg.model == "large-v3"
    assert cfg.language == "is"
    assert cfg.format == "markdown"
    assert cfg.timestamps is False
    assert cfg.keep_audio is True
    assert cfg.cookies_from_browser == "firefox"
    assert cfg.inbox_path == Path.home() / "vault" / "0.Inbox"
    assert cfg.media_dir == Path.home() / "vault" / "media"
    assert cfg.cache_dir == Path.home() / "somewhere" / "cache"


def test_empty_cookies_setting_disables_cookies(isolated_home):
    isolated_home.mkdir(parents=True, exist_ok=True)
    (isolated_home / "config.toml").write_text('[download]\ncookies_from_browser = ""\n')
    cfg = load_config()
    assert cfg.cookies_from_browser == ""


def test_cli_overrides_win_over_the_file(isolated_home):
    isolated_home.mkdir(parents=True, exist_ok=True)
    (isolated_home / "config.toml").write_text('[defaults]\nmodel = "tiny"\n')
    cfg = load_config({"model": "large-v3", "timestamps": False})
    assert cfg.model == "large-v3"
    assert cfg.timestamps is False


def test_overrides_ignore_unknown_keys():
    cfg = load_config({"nope": "x"})
    assert cfg.model == "medium"


def test_cookie_choice_is_exported_to_the_environment(isolated_home, monkeypatch):
    monkeypatch.delenv("YT_TRANSCRIBE_COOKIES_FROM_BROWSER", raising=False)
    isolated_home.mkdir(parents=True, exist_ok=True)
    (isolated_home / "config.toml").write_text('[download]\ncookies_from_browser = "firefox"\n')
    load_config()
    assert os.environ["YT_TRANSCRIBE_COOKIES_FROM_BROWSER"] == "firefox"


def test_ensure_dirs_creates_the_audio_cache(tmp_path, monkeypatch):
    cfg = load_config()
    cfg.cache_dir = tmp_path / "c"
    cfg.ensure_dirs()
    assert (tmp_path / "c" / "audio").is_dir()
