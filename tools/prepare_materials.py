#!/usr/bin/env python3
"""Make a private, page/time-indexed source packet from an official PDF and VTT.

This script does NOT download videos or generate a derivative transcript.
Keep source packets and raw subtitles local; do not commit them to GitHub.
"""
from __future__ import annotations

import argparse
import html
import re
from pathlib import Path

TIMECODE = re.compile(
    r"(?P<start>(?:\d{2}:)?\d{2}:\d{2}[.,]\d{3})\s*-->\s*"
    r"(?P<end>(?:\d{2}:)?\d{2}:\d{2}[.,]\d{3})"
)
TAG = re.compile(r"<[^>]+>")


def parse_vtt(path: Path) -> list[tuple[str, str]]:
    data = path.read_text(encoding="utf-8-sig", errors="replace")
    data = data.replace("\r\n", "\n").replace("\r", "\n")
    chunks = re.split(r"\n\s*\n", data)
    result: list[tuple[str, str]] = []
    prev = ""
    for chunk in chunks:
        lines = [line.strip() for line in chunk.splitlines() if line.strip()]
        idx = next((i for i, line in enumerate(lines) if TIMECODE.search(line)), None)
        if idx is None:
            continue
        m = TIMECODE.search(lines[idx])
        assert m is not None
        raw = " ".join(lines[idx + 1:])
        raw = re.sub(r"\{\\an\d+\}", "", raw)
        raw = TAG.sub("", raw)
        raw = html.unescape(raw)
        raw = re.sub(r"\s+", " ", raw).strip()
        # Many auto-caption providers repeat exactly the previous caption.
        if not raw or raw == prev:
            continue
        prev = raw
        result.append((m.group("start").replace(",", "."), raw))
    return result


def extract_pdf(path: Path) -> list[str]:
    try:
        import fitz
    except ImportError as exc:
        raise RuntimeError("PDF extraction requires: pip install pymupdf") from exc
    doc = fitz.open(path)
    try:
        return [page.get_text("text").strip() for page in doc]
    finally:
        doc.close()


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--pdf", type=Path, help="Downloaded official slides PDF")
    p.add_argument("--vtt", type=Path, help="Locally acquired VTT subtitles")
    p.add_argument("--output", required=True, type=Path)
    a = p.parse_args()
    if not a.pdf and not a.vtt:
        p.error("at least one of --pdf or --vtt is required")
    for src in (a.pdf, a.vtt):
        if src and not src.is_file():
            p.error(f"not found: {src}")

    lines = [
        "# PRIVATE SOURCE PACKET — do not commit",
        "",
        "> Auto-extracted content is for source checking, NOT a publishable textbook.",
        "> Transcripts may have errors; verify technical terms in the video.",
        "",
    ]
    if a.pdf:
        lines.extend(["## Slides (PDF page numbers are 1-based)", ""])
        for num, txt in enumerate(extract_pdf(a.pdf), 1):
            lines.extend([f"### Slide PDF page {num}", "", txt or "[No extractable text; inspect page image]", ""])
    else:
        lines.extend(["## Slides: missing (not verified)", ""])

    if a.vtt:
        lines.extend(["## Transcript (from locally supplied VTT)", ""])
        for stamp, txt in parse_vtt(a.vtt):
            lines.extend([f"**[{stamp}]** {txt}", ""])
    else:
        lines.extend(["## Transcript: missing (not verified)", ""])

    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text("\n".join(lines), encoding="utf-8")
    print(f"Prepared {a.output} ({len(lines)} lines of source text).")


if __name__ == "__main__":
    main()
