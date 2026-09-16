"""Configuration management with XDG-compliant defaults."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

_XDG_CONFIG = Path.home() / ".config" / "yt-transcribe"
_XDG_CACHE = Path.home() / ".cache" / "yt-transcribe"
# Generic defaults — override [vault] inbox_path / [media] dir in config.toml.
_OBSIDIAN = Path.home() / "Obsidian"
_VAULT_INBOX = _OBSIDIAN / "Inbox"
_MEDIA_DIR = _OBSIDIAN / "yt-transcribe"


@dataclass
class Config:
    model: str = "medium"
    language: str = "auto"
    format: str = "vault"
    timestamps: bool = True
    inbox_path: Path = field(default_factory=lambda: _VAULT_INBOX)
    cache_dir: Path = field(default_factory=lambda: _XDG_CACHE)
    media_dir: Path = field(default_factory=lambda: _MEDIA_DIR)
    keep_audio: bool = False
    # YouTube 403s cookie-less clients; pass browser cookies by default.
    cookies_from_browser: str = "chrome"

    def ensure_dirs(self) -> None:
        """Create cache and media directories if they don't exist."""
        (self.cache_dir / "audio").mkdir(parents=True, exist_ok=True)


def load_config(overrides: dict | None = None) -> Config:
    """Load config from TOML file, then apply CLI overrides."""
    cfg = Config()

    config_file = _XDG_CONFIG / "config.toml"
    if config_file.exists():
        with open(config_file, "rb") as f:
            data = tomllib.load(f)

        defaults = data.get("defaults", {})
        if "model" in defaults:
            cfg.model = defaults["model"]
        if "language" in defaults:
            cfg.language = defaults["language"]
        if "format" in defaults:
            cfg.format = defaults["format"]
        if "timestamps" in defaults:
            cfg.timestamps = defaults["timestamps"]

        vault = data.get("vault", {})
        if "inbox_path" in vault:
            cfg.inbox_path = Path(vault["inbox_path"]).expanduser()

        media = data.get("media", {})
        if "dir" in media:
            cfg.media_dir = Path(media["dir"]).expanduser()

        cache = data.get("cache", {})
        if "dir" in cache:
            cfg.cache_dir = Path(cache["dir"]).expanduser()
        if "keep_audio" in cache:
            cfg.keep_audio = cache["keep_audio"]

        download = data.get("download", {})
        if "cookies_from_browser" in download:
            cfg.cookies_from_browser = download["cookies_from_browser"] or ""

    # Hand the cookie choice to the downloader (it reads the env at call time).
    import os as _os
    _os.environ.setdefault("YT_TRANSCRIBE_COOKIES_FROM_BROWSER", cfg.cookies_from_browser)

    if overrides:
        for key, value in overrides.items():
            if value is not None and hasattr(cfg, key):
                setattr(cfg, key, value)

    return cfg
