#!/usr/bin/env python3
"""Cleanup filler words (um/uh/erm/er) in diarised markdown transcripts.

Design goals:
- Deterministic + local (no LLM pass)
- Safe-by-default: operate on markdown transcript only (not SRT)
- Conservative removals: only standalone filler tokens
- Light formatting fixes after removal
- Capitalise the first word of a sentence when it becomes sentence-initial after removals

Usage:
  cleanup_filler_words.py <input_md> [--in-place] [--backup]

By default, rewrites the file in-place (because this skill uses it as a post-process).
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

FILLERS = [
    "um",
    "uh",
    "erm",
    "er",
]

# Allow stretched variants like "umm", "uhhh" by matching repeated last char(s)
# - um+ matches um, umm, ummm
# - uh+ matches uh, uhh...
# - erm+ matches erm, ermm...
FILLER_RE = r"(?:um+|uh+|erm+|er)"

RE_PARENS_ONLY = re.compile(rf"\(\s*(?P<f>{FILLER_RE})\s*\)", re.IGNORECASE)
RE_FILLER_COMMA = re.compile(rf"\b(?P<f>{FILLER_RE})\b\s*,\s*", re.IGNORECASE)
RE_FILLER_SPACED = re.compile(rf"\s+\b(?P<f>{FILLER_RE})\b\s+", re.IGNORECASE)
RE_FILLER_START = re.compile(rf"^\s*\b(?P<f>{FILLER_RE})\b\s+", re.IGNORECASE)
RE_FILLER_END = re.compile(rf"\s+\b(?P<f>{FILLER_RE})\b\s*$", re.IGNORECASE)
RE_FILLER_STANDALONE = re.compile(rf"\b(?P<f>{FILLER_RE})\b", re.IGNORECASE)

# Speaker label: **Name:**
RE_SPEAKER = re.compile(r"^(\*\*[^\n]*?:\*\*)\s*(.*)$")


def _fix_spacing(text: str) -> str:
    # Collapse multiple spaces
    text = re.sub(r"[ \t]{2,}", " ", text)

    # Remove space before punctuation
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)

    # Normalise spaces after punctuation (very light touch)
    text = re.sub(r"([,.;:!?])(\S)", r"\1 \2", text)

    # Normalise em/en dashes (but don't touch hyphens inside words)
    text = re.sub(r"\s*[—–]\s*", " — ", text)
    # If a hyphen is used as a dash with spaces around it, normalise that too
    text = re.sub(r"\s+-\s+", " — ", text)
    text = re.sub(r"\s{2,}", " ", text)

    return text.strip()


def _capitalise_sentence_starts(text: str) -> str:
    """Capitalise first alphabetic character after sentence boundaries.

    This intentionally focuses on obvious boundaries:
    - start of string
    - after . ! ?

    It also handles optional quotes/brackets immediately after the boundary.
    """

    def cap_after_boundary(match: re.Match) -> str:
        boundary = match.group("boundary")
        prefix = match.group("prefix")
        ch = match.group("ch")
        return f"{boundary}{prefix}{ch.upper()}"

    # Start of string
    text = re.sub(r"^(?P<prefix>[\s\"'“”‘’\(\[\{]*)(?P<ch>[a-z])", lambda m: m.group("prefix") + m.group("ch").upper(), text)

    # After sentence punctuation
    text = re.sub(
        r"(?P<boundary>[.!?])(?P<prefix>[\s\"'“”‘’\)\]\}]*[\s\"'“”‘’\(\[\{]*)?(?P<ch>[a-z])",
        cap_after_boundary,
        text,
    )

    # Special-case lone "i" as a word
    text = re.sub(r"\bi\b", "I", text)

    return text


def cleanup_utterance(text: str) -> str:
    original = text

    # Remove (um) / (uh) / (erm)
    text = RE_PARENS_ONLY.sub("", text)

    # Remove "um, " patterns
    text = RE_FILLER_COMMA.sub("", text)

    # Remove fillers surrounded by spaces
    text = RE_FILLER_SPACED.sub(" ", text)

    # Remove at start/end
    text = RE_FILLER_START.sub("", text)
    text = RE_FILLER_END.sub("", text)

    # Remove remaining standalone fillers when they are the only token left between punctuation.
    # (Conservative: just remove the token, let spacing fixer handle the rest.)
    text = RE_FILLER_STANDALONE.sub("", text)

    text = _fix_spacing(text)
    text = _capitalise_sentence_starts(text)

    # Preserve empty utterances as empty string
    return text


def cleanup_markdown(md: str) -> str:
    out_lines: list[str] = []

    for line in md.splitlines():
        m = RE_SPEAKER.match(line)
        if not m:
            out_lines.append(line)
            continue

        speaker = m.group(1)
        utterance = m.group(2)
        cleaned = cleanup_utterance(utterance)

        if cleaned:
            out_lines.append(f"{speaker} {cleaned}")
        else:
            out_lines.append(f"{speaker}")

    # Ensure trailing newline
    return "\n".join(out_lines).rstrip() + "\n"


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("input_md", type=Path)
    p.add_argument("--in-place", action="store_true", default=True)
    p.add_argument("--no-in-place", dest="in_place", action="store_false")
    p.add_argument("--backup", action="store_true", help="Write a .raw.md backup alongside if it doesn't exist")
    args = p.parse_args()

    path: Path = args.input_md
    if not path.exists():
        raise SystemExit(f"File not found: {path}")

    original = path.read_text(encoding="utf-8")

    if args.backup:
        backup_path = path.with_suffix(path.suffix.replace(".md", "") + ".raw.md")
        # If suffix not .md, just append
        if backup_path == path:
            backup_path = Path(str(path) + ".raw")
        if not backup_path.exists():
            backup_path.write_text(original, encoding="utf-8")

    cleaned = cleanup_markdown(original)

    if args.in_place:
        path.write_text(cleaned, encoding="utf-8")
    else:
        print(cleaned)


if __name__ == "__main__":
    main()
