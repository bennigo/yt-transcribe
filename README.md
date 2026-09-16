# yt-transcribe

Download a YouTube video's audio and transcribe it locally with **faster-whisper**, writing a structured Markdown note — optionally formatted for an [Obsidian](https://obsidian.md) vault, complete with YAML frontmatter, timestamps and a subtitles link.

No cloud APIs, no per-minute cost: everything runs on your machine.

## Features

- **Local transcription** via `faster-whisper` (tiny → large-v3). GPU if available, CPU otherwise.
- **Vault output format** — emits a note with frontmatter (`id`, `aliases`, `tags`, `area`, `resource`), a `# Title`, channel/date/duration line, `## Transcript` with `<!-- HH:MM -->` markers, plus `## References` and `## Vault links` when applicable.
- **Plain Markdown output** for use outside Obsidian (`-f markdown`).
- **Existing subtitles** — `--subs-only` uses YouTube's captions and skips Whisper entirely.
- **Metadata from YouTube** — title, channel, upload date and duration are pulled from yt-dlp and injected into the note.
- **Cookie support** for YouTube's anti-bot responses (see below).

## Requirements

- Python **3.12+**
- **ffmpeg** on `PATH` (audio extraction)
- Optional but recommended: an NVIDIA GPU. The default install pulls the CUDA runtime wheels; on CPU-only machines remove the three `nvidia-*` dependencies from `pyproject.toml`.

## Install

```bash
git clone https://github.com/bennigo/yt-transcribe
cd yt-transcribe
uv tool install --force .
```

or with pipx:

```bash
pipx install .
```

## Usage

```bash
yt-transcribe "https://www.youtube.com/watch?v=VIDEO_ID"
```

Transcribe a local file instead (skips download):

```bash
yt-transcribe --file talk.mp3
```

### Options

| Flag | Description |
|------|-------------|
| `-m, --model` | Whisper model: `tiny`, `base`, `small`, `medium` (default), `large-v3` |
| `-l, --language` | Language code (`en`, `is`, …) or `auto` (default) |
| `-f, --format` | `vault` (default) or `markdown` |
| `-o, --output` | Output directory (default: the configured vault inbox, else cwd) |
| `--file` | Transcribe a local audio/video file instead of downloading |
| `--subs-only` | Use existing YouTube subtitles; do not run Whisper |
| `--no-timestamps` | Omit the `<!-- HH:MM -->` markers |
| `--keep-audio` | Keep the downloaded audio after transcription |
| `--link-audio` | Link the source audio in the note |
| `--force` | Overwrite an existing note |

## Configuration

Optional TOML at `~/.config/yt-transcribe/config.toml`:

```toml
[defaults]
model = "large-v3"
language = "auto"
format = "vault"
timestamps = true

[vault]
inbox_path = "~/Obsidian/MyVault/0.Inbox"

[media]
dir = "~/Obsidian/MyVault/Assets/yt-transcribe"

[cache]
dir = "~/.cache/yt-transcribe"
keep_audio = false

[download]
# Browser to read cookies from (see below). Empty string disables.
cookies_from_browser = "chrome"
```

CLI flags override the file.

## YouTube "HTTP 403: Forbidden" on download

YouTube increasingly rejects cookie-less clients, and yt-dlp then fails with:

```
ERROR: unable to download video data: HTTP Error 403: Forbidden
```

`yt-transcribe` therefore passes **browser cookies** to yt-dlp by default, read from the browser named in `cookies_from_browser` (default `chrome`). Override per run with an environment variable:

```bash
YT_TRANSCRIBE_COOKIES_FROM_BROWSER=firefox yt-transcribe "<url>"
YT_TRANSCRIBE_COOKIES_FROM_BROWSER= yt-transcribe "<url>"   # disable
```

Note this is not always strictly required — the same URL may work a minute later, so the 403 also behaves like burst rate-limiting. Cookies are the reliable fix.

## License

MIT — see [LICENSE](LICENSE).
