# yt-transcribe

Download a YouTube video's audio and transcribe it locally with
[faster-whisper](https://github.com/SYSTRAN/faster-whisper), writing a structured
Markdown note — optionally formatted for an [Obsidian](https://obsidian.md) vault.

No cloud APIs, no per-minute cost: everything runs on your machine. It is also
**idempotent against your vault** — if the video is already transcribed, it tells
you where and stops.

## How it works

```
YouTube URL ──yt-dlp──► audio (m4a→wav) ──faster-whisper──► segments
                                  │                              │
                                  │                              ▼
                                  └──deleted unless kept    formatter ──► Markdown / vault note (+ .srt)
```

1. **Download** — `yt-dlp` pulls the best audio-only stream and `ffmpeg` converts it to WAV.
2. **Dedup** — unless `--force`, the video ID is looked up across your vault; if a note already
   references it, the run exits without spending GPU time.
3. **Transcribe** — `faster-whisper` (CTranslate2). CUDA/`float16` when available, otherwise CPU/`int8`.
   Voice-activity detection is on; if VAD strips everything (music-heavy audio), it automatically retries with VAD off.
4. **Format** — a Markdown note, or an Obsidian-style note with YAML frontmatter.
5. **Clean up** — the downloaded audio is deleted unless you keep or link it.

## Features

- Local transcription — `tiny`, `base`, `small`, `medium`, `large-v3`.
- **Vault output** (`-f vault`, default): frontmatter (`id`, `aliases`, `tags`, `area`, `created`,
  `project`, `resource`), `# Title`, a channel/date/duration line, and `## Transcript` with
  `<!-- HH:MM -->` markers.
- **Markdown output** (`-f markdown`) for use outside Obsidian.
- **Vault deduplication** by video ID — no accidental re-transcription.
- **`--subs-only`**: reuse YouTube's existing captions, skipping Whisper entirely.
- **SRT output**: local-file mode always writes a `.srt` next to the note; YouTube mode writes one when `--link-audio` is used.
- Automatic **CUDA detection**, and a `LD_LIBRARY_PATH` shim so the pip-installed CUDA wheels are found.
- **Browser-cookie support** for YouTube's anti-bot `403` responses (see Troubleshooting).

## Requirements

- Python **3.12+**
- **ffmpeg** on `PATH` (`sudo apt install ffmpeg` / `brew install ffmpeg`)
- Optional: an NVIDIA GPU. The default install pulls the CUDA runtime wheels
  (`nvidia-cublas-cu12`, `nvidia-cudnn-cu12`, `nvidia-cuda-runtime-cu12`); on a CPU-only machine,
  drop those three from `pyproject.toml` before installing.

## Install

Not published on PyPI. The name `yt-transcribe` there belongs to an **unrelated project**
(`pascalweiss/yt-transcribe`, a whisper.cpp-based tool), so `pip install yt-transcribe` will
fetch the wrong thing. Install from source instead:

```bash
git clone https://github.com/bennigo/yt-transcribe
cd yt-transcribe
uv tool install --force .
```

or with pipx:

```bash
pipx install .
```

The Whisper weights are downloaded from Hugging Face **on first use** per model
(`medium` ≈ 1.5 GB, `large-v3` ≈ 3 GB) into the HF cache.

## Usage

```bash
# YouTube → vault note
yt-transcribe "https://www.youtube.com/watch?v=VIDEO_ID"

# A specific model + output directory
yt-transcribe -m large-v3 -o ~/notes ~/Obsidian/Inbox

# Reuse YouTube's own captions (no Whisper, very fast)
yt-transcribe --subs-only "https://youtu.be/VIDEO_ID"

# A local file (skips download; writes note + .srt)
yt-transcribe --file ~/audio/interview.mp3
```

### Options

| Flag | Description |
|------|-------------|
| `-m, --model` | Whisper model: `tiny`, `base`, `small`, `medium` *(default)*, `large-v3` |
| `-l, --language` | Language code (`en`, `is`, …) or `auto` *(default)* — auto-detection is used when omitted |
| `-f, --format` | `vault` *(default)* or `markdown` |
| `-o, --output` | Output directory. Defaults to the configured vault inbox (vault format) or the cwd |
| `--file` | Transcribe a local audio/video file instead of downloading |
| `--subs-only` | Fetch and use existing YouTube subtitles; never runs Whisper. Fails if none exist for the language |
| `--no-timestamps` | Omit the `<!-- HH:MM -->` markers |
| `--keep-audio` | Keep the downloaded audio in the cache directory (not linked in the note) |
| `--link-audio` | Move the audio into the media directory, write a `.srt` beside it, and link both from the note |
| `--force` | Skip the vault deduplication check and transcribe anyway |

`--subs-only` and `--file` are mutually exclusive (subtitles only exist for YouTube URLs).

## Configuration

Everything below is optional. Create `~/.config/yt-transcribe/config.toml`:

```toml
[defaults]
model = "large-v3"        # default: medium
language = "auto"         # or a code like "en", "is"
format = "vault"          # or "markdown"
timestamps = true

[vault]
inbox_path = "~/Obsidian/MyVault/0.Inbox"

[media]
dir = "~/Obsidian/MyVault/Assets/yt-transcribe"

[cache]
dir = "~/.cache/yt-transcribe"
keep_audio = false

[download]
# Browser to read cookies from (download troubleshooting below). "" disables.
cookies_from_browser = "chrome"
```

Defaults when no config file exists: inbox `~/Obsidian/Inbox`, media `~/Obsidian/yt-transcribe`,
cache `~/.cache/yt-transcribe`. CLI flags override the file.

## Output

A vault note looks like this:

```markdown
---
id: 1789562184-douglas-macgregor-ukraine-endgame-is-here
aliases:
  - "Douglas Macgregor: Ukraine Endgame Is Here"
tags:
  - type/reference
  - source/youtube
  - ctx/ai
area: ""
created: 2026-09-16 12:36
project: ""
resource: "https://www.youtube.com/watch?v=VIDEO_ID"
---

# Douglas Macgregor: Ukraine Endgame Is Here

**Channel**: Glenn Diesen | **Date**: 2026-09-16 | **Duration**: 49:27
**Source**: [Douglas Macgregor: Ukraine Endgame Is Here](https://www.youtube.com/watch?v=VIDEO_ID)

## Transcript

<!-- 00:00 -->
Welcome back, everyone. We are joined today by …
```

`area` is left empty on purpose — it is yours to fill (or set with a vault automation).
Downstream enrichment (extra reference sections, wikilinks, placeholders) is not this tool's job.

## Troubleshooting

**`ERROR: unable to download video data: HTTP Error 403: Forbidden`**

YouTube increasingly rejects cookie-less clients. `yt-transcribe` therefore passes browser cookies
to yt-dlp by default, read from the browser named in `cookies_from_browser` (default `chrome`).
Override per run:

```bash
YT_TRANSCRIBE_COOKIES_FROM_BROWSER=firefox yt-transcribe "<url>"
YT_TRANSCRIBE_COOKIES_FROM_BROWSER= yt-transcribe "<url>"   # disable
```

The 403 also behaves like burst rate-limiting — the same URL may succeed a minute later — but cookies
are the reliable fix. If cookies can't be read (browser running as a snap, keyring locked), the error
surfaces as a yt-dlp warning; disabling cookies restores the previous behaviour.

**"No subtitles found"** — `--subs-only` only works when the uploader provided captions in that
language (or YouTube auto-generated them). Drop the flag to use Whisper.

**Everything is very slow** — Whisper is running on CPU. Check the `Using device: … (compute: …)`
line printed at start-up. GPU use requires the three `nvidia-*` wheels and a working CUDA driver.

**Wrong output location** — with `-f vault` and no `-o`, notes go to the configured `inbox_path`.
Set `[vault] inbox_path` or pass `-o`.

## Development

```bash
uv sync
uv run --with pytest pytest
```

`tests/` is currently a placeholder — there is **no test suite yet**, so treat `--force` runs as authoritative
and re-check output by hand after changing the formatter or downloader.

## See also

- [`pascalweiss/yt-transcribe`](https://pypi.org/project/yt-transcribe/) — an unrelated tool that owns the PyPI name.
- [`SYSTRAN/faster-whisper`](https://github.com/SYSTRAN/faster-whisper) — the transcription backend.
- [`yt-dlp/yt-dlp`](https://github.com/yt-dlp/yt-dlp) — the downloader.

## License

MIT — see [LICENSE](LICENSE).
