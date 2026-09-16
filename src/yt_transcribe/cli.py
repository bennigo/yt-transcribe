"""CLI entry point for yt-transcribe."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="yt-transcribe",
        description="Transcribe YouTube videos or local audio/video files. Outputs Obsidian vault notes or plain markdown.",
    )
    parser.add_argument("url", nargs="?", default=None, help="YouTube video URL")
    parser.add_argument(
        "--file",
        type=Path,
        help="Local audio/video file to transcribe (skips download)",
    )
    parser.add_argument(
        "-m", "--model",
        default=None,
        choices=["tiny", "base", "small", "medium", "large-v3"],
        help="Whisper model size (default: medium)",
    )
    parser.add_argument(
        "-l", "--language",
        default=None,
        help="Language code (en, is, etc.) or 'auto' for detection (default: auto)",
    )
    parser.add_argument(
        "-f", "--format",
        default=None,
        choices=["vault", "markdown"],
        dest="output_format",
        help="Output format (default: vault)",
    )
    parser.add_argument(
        "-o", "--output",
        default=None,
        type=Path,
        help="Output directory (default: vault inbox or cwd)",
    )
    parser.add_argument(
        "--subs-only",
        action="store_true",
        help="Only fetch existing YouTube subtitles, skip Whisper transcription",
    )
    parser.add_argument(
        "--no-timestamps",
        action="store_true",
        help="Omit timestamps from transcript for cleaner reading",
    )
    parser.add_argument(
        "--keep-audio",
        action="store_true",
        default=None,
        help="Don't delete downloaded audio after transcription",
    )
    parser.add_argument(
        "--link-audio",
        action="store_true",
        help="Keep audio on disk and add a file:// link in the note (audio stays in cache, not synced)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Skip duplicate check and transcribe even if video already exists in vault",
    )
    return parser


def _extract_video_id(url: str) -> str | None:
    """Extract YouTube video ID from various URL formats."""
    import re

    patterns = [
        r"(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/live/)([a-zA-Z0-9_-]{11})",
        r"youtube\.com/embed/([a-zA-Z0-9_-]{11})",
        r"youtube\.com/v/([a-zA-Z0-9_-]{11})",
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


def _check_vault_duplicate(video_id: str, vault_root: Path) -> Path | None:
    """Search vault for an existing note containing this video ID.

    Scans all .md files for the video ID in resource: frontmatter fields
    or YouTube URLs in the first 20 lines. Returns the path of the first
    match, or None if no duplicate found.
    """
    if not vault_root.is_dir():
        return None

    for md_file in vault_root.rglob("*.md"):
        # Skip hidden dirs, .obsidian, Assets, .git
        if any(
            part.startswith(".") or part in ("Assets", "node_modules")
            for part in md_file.parts
        ):
            continue
        try:
            # Only read the first 20 lines (frontmatter + header)
            with open(md_file, encoding="utf-8", errors="replace") as f:
                head = "".join(f.readline() for _ in range(20))
            if video_id in head:
                return md_file
        except OSError:
            continue
    return None


def _setup_nvidia_libs() -> None:
    """Add pip-installed NVIDIA library paths to LD_LIBRARY_PATH for CUDA support."""
    import os
    import site as site_mod

    site_dirs = site_mod.getsitepackages()
    nvidia_paths = []
    for site_dir in site_dirs:
        nvidia_base = Path(site_dir) / "nvidia"
        if nvidia_base.is_dir():
            for sub in nvidia_base.iterdir():
                lib_dir = sub / "lib"
                if lib_dir.is_dir():
                    nvidia_paths.append(str(lib_dir))

    if nvidia_paths:
        existing = os.environ.get("LD_LIBRARY_PATH", "")
        os.environ["LD_LIBRARY_PATH"] = ":".join(nvidia_paths) + (":" + existing if existing else "")


def main(argv: list[str] | None = None) -> None:
    _setup_nvidia_libs()

    parser = build_parser()
    args = parser.parse_args(argv)

    from yt_transcribe.config import load_config

    overrides = {}
    if args.model is not None:
        overrides["model"] = args.model
    if args.language is not None:
        overrides["language"] = args.language
    if args.output_format is not None:
        overrides["format"] = args.output_format
    if args.no_timestamps:
        overrides["timestamps"] = False
    if args.keep_audio is not None:
        overrides["keep_audio"] = args.keep_audio

    cfg = load_config(overrides)
    cfg.ensure_dirs()

    if not args.url and not args.file:
        parser.error("either a URL or --file is required")
    if args.file and args.subs_only:
        parser.error("--subs-only is only available for YouTube URLs")

    output_dir = args.output or (cfg.inbox_path if cfg.format == "vault" else Path.cwd())

    # --- Local file mode ---
    if args.file:
        _transcribe_local(args.file, cfg, output_dir, link_audio=args.link_audio)
        return

    # --- Dedup check for YouTube URLs ---
    if args.url and not args.force:
        video_id = _extract_video_id(args.url)
        if video_id:
            vault_root = cfg.inbox_path.parent  # e.g. ~/Obsidian
            existing = _check_vault_duplicate(video_id, vault_root)
            if existing:
                print(f"\n⚠️  This video has already been transcribed:")
                print(f"   → {existing}")
                print(f"\nUse --force to transcribe again.\n")
                sys.exit(0)

    from yt_transcribe.downloader import download_audio, fetch_metadata, fetch_subtitles
    from yt_transcribe.formatter import (
        format_markdown,
        format_srt,
        format_vault_note,
        format_vault_note_from_subs,
    )

    # --- Subs-only mode ---
    if args.subs_only:
        lang = cfg.language if cfg.language != "auto" else "en"
        print(f"Fetching existing subtitles ({lang})...")
        subs = fetch_subtitles(args.url, lang)
        if subs is None:
            print(f"No subtitles found for language '{lang}'. Try without --subs-only to use Whisper.", file=sys.stderr)
            sys.exit(1)

        meta = fetch_metadata(args.url)
        if cfg.format == "vault":
            content, filename = format_vault_note_from_subs(meta, subs)
        else:
            content = f"# {meta.title}\n\n**Channel**: {meta.channel} | **Date**: {meta.upload_date}\n**URL**: {meta.url}\n\n## Transcript\n\n{subs}\n"
            filename = f"{meta.title}.md"

        _write_output(content, filename, output_dir)
        return

    # --- YouTube transcription mode ---
    print(f"Downloading audio from: {args.url}")
    result = download_audio(args.url, cfg.cache_dir / "audio")
    print(f"Audio saved: {result.path} ({result.meta.duration}s)")

    print(f"Transcribing with model '{cfg.model}' (language: {cfg.language})...")
    from yt_transcribe.transcriber import transcribe

    transcript = transcribe(
        audio_path=result.path,
        model=cfg.model,
        language=cfg.language if cfg.language != "auto" else None,
    )
    print(f"Detected language: {transcript.language} ({transcript.language_probability:.0%})")
    print(f"Segments: {len(transcript.segments)}")

    # Format output
    timestamps = cfg.timestamps
    if cfg.format == "vault":
        content, filename = format_vault_note(result.meta, transcript.segments, timestamps)
    else:
        content = format_markdown(result.meta, transcript.segments, timestamps)
        slug = result.meta.title.replace(" ", "-").lower()[:50]
        filename = f"{slug}.md"

    # Persist audio + SRT to media directory when requested
    if args.link_audio:
        import shutil

        from yt_transcribe.formatter import inject_audio_link, inject_srt_link

        cfg.media_dir.mkdir(parents=True, exist_ok=True)

        srt_content = format_srt(transcript.segments)
        srt_path = cfg.media_dir / f"{result.path.stem}.srt"
        srt_path.write_text(srt_content, encoding="utf-8")
        print(f"SRT saved: {srt_path}")

        media_path = cfg.media_dir / result.path.name
        shutil.move(str(result.path), str(media_path))
        print(f"Audio stored: {media_path}")

        content = inject_audio_link(content, str(media_path.resolve()))
        if cfg.format == "vault":
            content = inject_srt_link(content, str(srt_path.resolve()))

    _write_output(content, filename, output_dir)

    # Cleanup audio (skip if --link-audio or --keep-audio)
    if not cfg.keep_audio and not args.link_audio:
        result.path.unlink(missing_ok=True)
        print(f"Cleaned up audio: {result.path}")


def _transcribe_local(
    file_path: Path, cfg: object, output_dir: Path, link_audio: bool = False,
) -> None:
    """Transcribe a local audio/video file."""
    if not file_path.exists():
        print(f"File not found: {file_path}", file=sys.stderr)
        sys.exit(1)

    print(f"Transcribing local file: {file_path}")
    print(f"Transcribing with model '{cfg.model}' (language: {cfg.language})...")

    from yt_transcribe.transcriber import transcribe

    transcript = transcribe(
        audio_path=file_path,
        model=cfg.model,
        language=cfg.language if cfg.language != "auto" else None,
    )
    print(f"Detected language: {transcript.language} ({transcript.language_probability:.0%})")
    print(f"Segments: {len(transcript.segments)}")

    from yt_transcribe.formatter import (
        format_local_markdown,
        format_local_vault_note,
        format_srt,
    )

    # Save SRT alongside output
    srt_content = format_srt(transcript.segments)
    srt_path = output_dir / f"{file_path.stem}.srt"
    output_dir.mkdir(parents=True, exist_ok=True)
    srt_path.write_text(srt_content, encoding="utf-8")
    print(f"SRT saved: {srt_path}")

    timestamps = cfg.timestamps
    title = file_path.stem.replace("-", " ").replace("_", " ").title()

    if cfg.format == "vault":
        content, filename = format_local_vault_note(
            title=title,
            source_file=str(file_path),
            segments=transcript.segments,
            language=transcript.language,
            timestamps=timestamps,
        )
    else:
        content = format_local_markdown(
            title=title,
            source_file=str(file_path),
            segments=transcript.segments,
            language=transcript.language,
            timestamps=timestamps,
        )
        from yt_transcribe.formatter import slugify

        filename = f"{slugify(title)}.md"

    if link_audio:
        from yt_transcribe.formatter import inject_audio_link

        content = inject_audio_link(content, str(file_path.resolve()))

    # Inject SRT link in vault notes
    if cfg.format == "vault":
        from yt_transcribe.formatter import inject_srt_link

        content = inject_srt_link(content, str(srt_path.resolve()))

    _write_output(content, filename, output_dir)


def _write_output(content: str, filename: str, output_dir: Path) -> None:
    """Write the output file and print the path."""
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / filename
    out_path.write_text(content, encoding="utf-8")
    print(f"Written: {out_path}")


if __name__ == "__main__":
    main()
