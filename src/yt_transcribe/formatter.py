"""Output formatting for transcripts — vault notes and plain markdown."""

from __future__ import annotations

import re
import time
from pathlib import Path

from yt_transcribe.downloader import VideoMeta
from yt_transcribe.transcriber import Segment


def format_duration(seconds: int) -> str:
    """Format duration as H:MM:SS or MM:SS."""
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def format_timestamp(seconds: float) -> str:
    """Format a segment timestamp as HH:MM:SS."""
    total = int(seconds)
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def format_short_timestamp(seconds: float) -> str:
    """Format timestamp as MM:SS or H:MM:SS for HTML comments."""
    total = int(seconds)
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def _srt_timestamp(seconds: float) -> str:
    """Format seconds as SRT timestamp: HH:MM:SS,mmm."""
    total = int(seconds)
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    millis = int((seconds - total) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def format_srt(segments: list[Segment]) -> str:
    """Format segments as an SRT subtitle file."""
    entries: list[str] = []
    idx = 0
    for seg in segments:
        text = seg.text.strip()
        if not text:
            continue
        idx += 1
        start = _srt_timestamp(seg.start)
        end = _srt_timestamp(seg.end)
        entries.append(f"{idx}\n{start} --> {end}\n{text}\n")
    return "\n".join(entries)


def slugify(title: str, max_len: int = 50) -> str:
    """Convert a title to a URL/filename-friendly slug."""
    slug = title.lower()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")
    if len(slug) > max_len:
        slug = slug[:max_len].rsplit("-", 1)[0]
    return slug


def inject_audio_link(content: str, audio_path: str) -> str:
    """Insert an audio file link into the note, just before ## Transcript."""
    file_uri = f"file://{audio_path}"
    audio_line = f"**Audio**: [{Path(audio_path).name}]({file_uri})\n"
    return content.replace("## Transcript", f"{audio_line}\n## Transcript", 1)


def inject_srt_link(content: str, srt_path: str) -> str:
    """Insert an SRT subtitle file link into the note, just before ## Transcript."""
    file_uri = f"file://{srt_path}"
    srt_line = f"**Subtitles**: [{Path(srt_path).name}]({file_uri})\n"
    return content.replace("## Transcript", f"{srt_line}\n## Transcript", 1)


def _format_segments(segments: list[Segment], timestamps: bool) -> str:
    """Format transcript segments with optional HTML comment timestamps.

    When timestamps=True, inserts invisible ``<!-- MM:SS -->`` markers
    every ~30 seconds.  These create paragraph breaks in the transcript
    and are invisible in Obsidian reading mode but visible in source mode
    for navigating back to the video.
    """
    lines: list[str] = []
    last_ts_mark = -30.0
    for seg in segments:
        text = seg.text.strip()
        if not text:
            continue
        if timestamps and seg.start - last_ts_mark >= 30.0:
            if lines:
                lines.append("")  # paragraph break
            lines.append(f"<!-- {format_short_timestamp(seg.start)} -->")
            last_ts_mark = seg.start
        lines.append(text)
    return "\n".join(lines)


def format_markdown(
    meta: VideoMeta,
    segments: list[Segment],
    timestamps: bool = True,
) -> str:
    """Format as plain markdown."""
    transcript = _format_segments(segments, timestamps)
    duration = format_duration(meta.duration)

    return f"""# {meta.title}

**Channel**: {meta.channel} | **Date**: {meta.upload_date} | **Duration**: {duration}
**URL**: {meta.url}

## Transcript

{transcript}
"""


def format_vault_note(
    meta: VideoMeta,
    segments: list[Segment],
    timestamps: bool = True,
) -> tuple[str, str]:
    """Format as an Obsidian vault note with frontmatter.

    Returns:
        (content, filename) tuple
    """
    ts = int(time.time())
    slug = slugify(meta.title)
    note_id = f"{ts}-{slug}"
    filename = f"{note_id}.md"

    now = time.strftime("%Y-%m-%d %H:%M")
    transcript = _format_segments(segments, timestamps)
    duration = format_duration(meta.duration)

    content = f"""---
id: {note_id}
aliases:
  - "{meta.title}"
tags:
  - type/reference
  - source/youtube
  - ctx/ai
area: ""
created: {now}
project: ""
resource: "{meta.url}"
---

# {meta.title}

**Channel**: {meta.channel} | **Date**: {meta.upload_date} | **Duration**: {duration}
**Source**: [{meta.title}]({meta.url})

## Transcript

{transcript}
"""
    return content, filename


def format_local_markdown(
    title: str,
    source_file: str,
    segments: list[Segment],
    language: str,
    timestamps: bool = True,
) -> str:
    """Format a local file transcription as plain markdown."""
    transcript = _format_segments(segments, timestamps)
    duration = ""
    if segments:
        duration = format_duration(int(segments[-1].end))

    return f"""# {title}

**Source file**: `{source_file}` | **Language**: {language}{f' | **Duration**: {duration}' if duration else ''}

## Transcript

{transcript}
"""


def format_local_vault_note(
    title: str,
    source_file: str,
    segments: list[Segment],
    language: str,
    timestamps: bool = True,
) -> tuple[str, str]:
    """Format a local file transcription as an Obsidian vault note."""
    ts = int(time.time())
    slug = slugify(title)
    note_id = f"{ts}-{slug}"
    filename = f"{note_id}.md"

    now = time.strftime("%Y-%m-%d %H:%M")
    transcript = _format_segments(segments, timestamps)
    duration = ""
    if segments:
        duration = format_duration(int(segments[-1].end))

    content = f"""---
id: {note_id}
aliases:
  - "{title}"
tags:
  - type/reference
  - ctx/ai
area: ""
created: {now}
project: ""
resource: ""
---

# {title}

**Source file**: `{source_file}` | **Language**: {language}{f' | **Duration**: {duration}' if duration else ''}

## Transcript

{transcript}
"""
    return content, filename


def format_vault_note_from_subs(
    meta: VideoMeta,
    subtitle_text: str,
) -> tuple[str, str]:
    """Format a vault note from pre-existing subtitles (no whisper segments)."""
    ts = int(time.time())
    slug = slugify(meta.title)
    note_id = f"{ts}-{slug}"
    filename = f"{note_id}.md"

    now = time.strftime("%Y-%m-%d %H:%M")
    duration = format_duration(meta.duration)

    content = f"""---
id: {note_id}
aliases:
  - "{meta.title}"
tags:
  - type/reference
  - source/youtube
  - ctx/ai
area: ""
created: {now}
project: ""
resource: "{meta.url}"
---

# {meta.title}

**Channel**: {meta.channel} | **Date**: {meta.upload_date} | **Duration**: {duration}
**Source**: [{meta.title}]({meta.url})

> Note: Transcript from existing YouTube subtitles (not Whisper-transcribed)

## Transcript

{subtitle_text}
"""
    return content, filename
