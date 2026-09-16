"""YouTube audio download and metadata extraction via yt-dlp."""

from __future__ import annotations

import html
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

import yt_dlp


def _cookie_opts() -> dict:
    """YouTube serves HTTP 403 to cookie-less clients (seen 2026-09-16).

    Passing browser cookies fixes it. Controlled by
      YT_TRANSCRIBE_COOKIES_FROM_BROWSER=<browser>   (default: chrome)
      YT_TRANSCRIBE_COOKIES_FROM_BROWSER=            (disable)
    """
    browser = os.environ.get("YT_TRANSCRIBE_COOKIES_FROM_BROWSER", "chrome").strip()
    return {"cookiesfrombrowser": (browser,)} if browser else {}


@dataclass
class VideoMeta:
    title: str
    channel: str
    upload_date: str  # YYYY-MM-DD
    duration: int  # seconds
    description: str
    url: str


@dataclass
class AudioResult:
    path: Path
    meta: VideoMeta


def fetch_metadata(url: str) -> VideoMeta:
    """Fetch video metadata without downloading."""
    opts = {"quiet": True, "no_warnings": True, **_cookie_opts()}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)

    date_raw = info.get("upload_date", "")
    upload_date = (
        f"{date_raw[:4]}-{date_raw[4:6]}-{date_raw[6:8]}"
        if len(date_raw) == 8
        else date_raw
    )

    return VideoMeta(
        title=info.get("title", "Untitled"),
        channel=info.get("channel") or info.get("uploader") or "Unknown",
        upload_date=upload_date,
        duration=int(info.get("duration", 0)),
        description=info.get("description", ""),
        url=info.get("webpage_url", url),
    )


def download_audio(url: str, output_dir: Path) -> AudioResult:
    """Download audio from YouTube video, convert to WAV."""
    output_dir.mkdir(parents=True, exist_ok=True)

    output_template = str(output_dir / "%(id)s.%(ext)s")
    opts = {
        "format": "bestaudio/best",
        "outtmpl": output_template,
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "wav",
                "preferredquality": "0",
            }
        ],
        "quiet": True,
        "no_warnings": True,
        **_cookie_opts(),
    }

    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)

    video_id = info["id"]
    date_raw = info.get("upload_date", "")
    upload_date = (
        f"{date_raw[:4]}-{date_raw[4:6]}-{date_raw[6:8]}"
        if len(date_raw) == 8
        else date_raw
    )

    meta = VideoMeta(
        title=info.get("title", "Untitled"),
        channel=info.get("channel") or info.get("uploader") or "Unknown",
        upload_date=upload_date,
        duration=int(info.get("duration", 0)),
        description=info.get("description", ""),
        url=info.get("webpage_url", url),
    )

    wav_path = output_dir / f"{video_id}.wav"
    if not wav_path.exists():
        candidates = list(output_dir.glob(f"{video_id}.*"))
        if candidates:
            wav_path = candidates[0]
        else:
            raise FileNotFoundError(
                f"Downloaded audio not found for {video_id} in {output_dir}"
            )

    return AudioResult(path=wav_path, meta=meta)


def fetch_subtitles(url: str, lang: str = "en") -> str | None:
    """Fetch existing subtitles (manual or auto-generated) if available."""
    # First check what subs are available
    opts = {"quiet": True, "no_warnings": True, **_cookie_opts()}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)

    subs = info.get("subtitles", {})
    auto_subs = info.get("automatic_captions", {})

    if lang not in subs and lang not in auto_subs:
        return None

    # Download the subtitle file
    with tempfile.TemporaryDirectory() as tmpdir:
        dl_opts = {
            "writesubtitles": True,
            "writeautomaticsub": True,
            "subtitleslangs": [lang],
            "subtitlesformat": "vtt",
            "skip_download": True,
            "outtmpl": f"{tmpdir}/subs.%(ext)s",
            "quiet": True,
            "no_warnings": True,
            **_cookie_opts(),
        }

        with yt_dlp.YoutubeDL(dl_opts) as ydl:
            ydl.download([url])

        sub_files = list(Path(tmpdir).glob("*.vtt"))
        if not sub_files:
            return None

        raw = sub_files[0].read_text(encoding="utf-8")
        return _clean_vtt(raw)


def _clean_vtt(vtt_text: str) -> str:
    """Convert VTT subtitle text to plain timestamped text.

    YouTube's rolling captions repeat a cue's text across consecutive
    timestamps; those repeats are dropped. HTML entities (``&amp;``, ``&#39;``)
    are decoded and inline styling tags (``<c…>``) stripped.
    """
    lines: list[str] = []
    current_time = ""
    current_text = ""
    last_emitted = ""

    def flush() -> None:
        nonlocal current_text, last_emitted
        if current_text and current_text != last_emitted:
            lines.append(f"[{current_time}] {current_text}")
            last_emitted = current_text
        current_text = ""

    for line in vtt_text.splitlines():
        line = line.strip()

        if (
            not line
            or line.startswith("WEBVTT")
            or line.startswith("Kind:")
            or line.startswith("Language:")
        ):
            continue

        # Timestamp line: "00:00:01.234 --> 00:00:05.678"
        if "-->" in line:
            flush()
            raw_time = line.split("-->")[0].strip()
            time_parts = raw_time.split(":")
            if len(time_parts) == 3:
                current_time = raw_time.split(".")[0]
            else:
                current_time = f"00:{raw_time.split('.')[0]}"
        elif line.isdigit():
            continue  # cue index, as used by some VTT flavours
        else:
            clean = html.unescape(re.sub(r"<[^>]+>", "", line)).strip()
            if clean:
                current_text = clean

    flush()
    return "\n".join(lines)
