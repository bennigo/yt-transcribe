"""Tests for yt_transcribe.formatter — pure functions, no mocks needed."""

from __future__ import annotations

import re

import pytest

from yt_transcribe.formatter import (
    _format_segments,
    _srt_timestamp,
    format_duration,
    format_local_markdown,
    format_local_vault_note,
    format_markdown,
    format_short_timestamp,
    format_srt,
    format_timestamp,
    format_vault_note,
    format_vault_note_from_subs,
    inject_audio_link,
    inject_srt_link,
    slugify,
)
from yt_transcribe.downloader import VideoMeta
from yt_transcribe.transcriber import Segment


@pytest.mark.parametrize(
    "seconds,expected",
    [(0, "0:00"), (59, "0:59"), (60, "1:00"), (3599, "59:59"), (3600, "1:00:00"), (3661, "1:01:01")],
)
def test_format_duration(seconds, expected):
    assert format_duration(seconds) == expected


@pytest.mark.parametrize(
    "seconds,expected",
    [(0, "00:00:00"), (61, "00:01:01"), (3661.9, "01:01:01"), (86399, "23:59:59")],
)
def test_format_timestamp(seconds, expected):
    assert format_timestamp(seconds) == expected


@pytest.mark.parametrize(
    "seconds,expected", [(0, "00:00"), (59, "00:59"), (60, "01:00"), (3600, "1:00:00"), (3661, "1:01:01")]
)
def test_format_short_timestamp(seconds, expected):
    assert format_short_timestamp(seconds) == expected


@pytest.mark.parametrize(
    "seconds,expected",
    [(0, "00:00:00,000"), (1.5, "00:00:01,500"), (3661.123, "01:01:01,123")],
)
def test_srt_timestamp(seconds, expected):
    assert _srt_timestamp(seconds) == expected


def test_format_srt_numbers_and_skips_blank_segments():
    segs = [
        Segment(start=0.0, end=1.0, text="first"),
        Segment(start=1.0, end=2.0, text="   "),  # blank → skipped, not numbered
        Segment(start=2.0, end=3.0, text=" second "),
    ]
    out = format_srt(segs)
    assert out.startswith("1\n00:00:00,000 --> 00:00:01,000\nfirst\n")
    assert "\n2\n00:00:02,000 --> 00:00:03,000\nsecond\n" in out
    assert "\n3\n" not in out


@pytest.mark.parametrize(
    "title,expected",
    [
        ("Hello, World!", "hello-world"),
        ("  Spaced   Out  ", "spaced-out"),
        ("Dots.And/Slashes", "dotsandslashes"),
        ("UPPER case", "upper-case"),
        ("a--b", "a-b"),
        ("',.!?", ""),
    ],
)
def test_slugify(title, expected):
    assert slugify(title) == expected


def test_slugify_truncates_on_a_word_boundary():
    title = "word " * 30  # slugs to "word-word-..."
    out = slugify(title, max_len=20)
    assert len(out) <= 20
    assert not out.endswith("-")


def test_slugify_without_a_dash_returns_hard_slice():
    out = slugify("x" * 100, max_len=10)
    assert out == "x" * 10


def test_inject_audio_link_goes_before_transcript():
    body = "# T\n\n## Transcript\n\nhello\n"
    out = inject_audio_link(body, "/tmp/media/clip.wav")
    assert out.index("**Audio**") < out.index("## Transcript")
    assert "[clip.wav](file:///tmp/media/clip.wav)" in out


def test_inject_srt_link_goes_before_transcript():
    body = "# T\n\n## Transcript\n\nhello\n"
    out = inject_srt_link(body, "/tmp/media/clip.srt")
    assert out.index("**Subtitles**") < out.index("## Transcript")
    assert "[clip.srt](file:///tmp/media/clip.srt)" in out


def test_inject_links_are_noops_without_a_transcript_heading():
    body = "# T\n\nno transcript here\n"
    assert inject_audio_link(body, "/a.wav") == body
    assert inject_srt_link(body, "/a.srt") == body


def test_format_segments_skips_blank_and_strips_whitespace(segments):
    out = _format_segments(segments, timestamps=False)
    assert out == "Welcome back, everyone.\nWe are joined today by Colonel Macgregor.\nLet us begin."


def test_format_segments_inserts_timestamps_every_30s(segments):
    out = _format_segments(segments, timestamps=True)
    assert out.startswith("<!-- 00:00 -->")
    # 44s is >=30s after the 0s marker → a second marker (and paragraph break)
    assert "<!-- 00:44 -->" in out
    assert "\n\n<!-- 00:44 -->" in out


def test_format_segments_with_no_timestamps_has_no_markers(segments):
    assert "<!--" not in _format_segments(segments, timestamps=False)


def test_format_markdown_structure(meta, segments):
    out = format_markdown(meta, segments)
    assert out.startswith(f"# {meta.title}\n")
    assert f"**Channel**: {meta.channel} | **Date**: {meta.upload_date} | **Duration**: 49:27" in out
    assert f"**URL**: {meta.url}" in out
    assert "## Transcript" in out


def test_format_vault_note_frontmatter_and_filename(meta, segments):
    content, filename = format_vault_note(meta, segments)
    assert filename.endswith(".md")
    assert filename.startswith(str(int(filename.split("-")[0])))  # <unix-ts>-slug.md
    fm = re.match(r"^---\n(.*?)\n---\n", content, re.S)
    assert fm, "frontmatter must open and close with ---"
    block = fm.group(1)
    assert f'id: {filename[:-3]}' in block
    assert f'aliases:\n  - "{meta.title}"' in block
    for tag in ("type/reference", "source/youtube", "ctx/ai"):
        assert f"  - {tag}" in block
    assert "area: \"\"" in block
    assert f'resource: "{meta.url}"' in block
    assert re.search(r"^created: \d{4}-\d{2}-\d{2} \d{2}:\d{2}$", block, re.M)


def test_format_vault_note_is_parseable_yaml(meta, segments):
    yaml = pytest.importorskip("yaml")
    content, _ = format_vault_note(meta, segments)
    block = re.match(r"^---\n(.*?)\n---\n", content, re.S).group(1)
    assert yaml.safe_load(block)["resource"] == meta.url


def test_format_local_markdown_uses_last_segment_for_duration(segments):
    out = format_local_markdown("Talk", "/tmp/talk.mp3", segments, "en")
    # last segment ends at 61.25s
    assert "**Source file**: `/tmp/talk.mp3` | **Language**: en | **Duration**: 1:01" in out


def test_format_local_markdown_without_segments_omits_duration():
    out = format_local_markdown("Talk", "/tmp/talk.mp3", [], "en")
    assert "**Duration**" not in out


def test_format_local_vault_note_has_no_source_youtube_tag(segments):
    content, filename = format_local_vault_note("Talk", "/tmp/talk.mp3", segments, "en")
    assert filename.endswith("-talk.md")
    assert "source/youtube" not in content
    assert 'resource: ""' in content


def test_format_vault_note_from_subs_marks_the_transcript_source(meta):
    content, filename = format_vault_note_from_subs(meta, "[00:00] hello")
    assert filename.endswith(".md")
    assert "existing YouTube subtitles" in content
    assert "[00:00] hello" in content
    assert f'resource: "{meta.url}"' in content


def test_titles_with_quotes_do_not_break_frontmatter():
    """Titles containing double quotes must not produce invalid YAML."""
    yaml = pytest.importorskip("yaml")
    quoted = VideoMeta(
        title='Prof. X: "We Cannot Stop" Iran',
        channel="c",
        upload_date="2026-01-01",
        duration=60,
        description="",
        url="https://youtu.be/abcdefghijk",
    )
    content, _ = format_vault_note(quoted, [Segment(0.0, 1.0, "hi")])
    block = re.match(r"^---\n(.*?)\n---\n", content, re.S).group(1)
    yaml.safe_load(block)  # raises if the quote wasn't handled
