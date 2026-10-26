#!/usr/bin/env python3
"""Check baseline self-contained / GitHub Markdown requirements for CS149 textbook.

This static check does not replace math validation, GPU benchmarking or audio review.
Run: python3 tools/check_textbook.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import unquote

CS149_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = CS149_ROOT.parent
CHAPTER_DIR = CS149_ROOT / "textbook"
LINK = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
CODE_FENCE = re.compile(r"^\s*((?:\x60{3,})|(?:~{3,}))")


def lint_chapter(path: Path) -> list[str]:
    body = path.read_text(encoding="utf-8")
    rows = body.splitlines()
    problems: list[str] = []
    in_code: tuple[str, int] | None = None
    in_math = False
    math_marker = "$" * 2

    for num, row in enumerate(rows, 1):
        stripped = row.strip()
        fence = CODE_FENCE.match(row)
        if fence:
            symbols = fence.group(1)
            if in_code is None:
                in_code = (symbols[0], len(symbols))
            elif in_code[0] == symbols[0] and len(symbols) >= in_code[1]:
                in_code = None
            continue
        if in_code:
            continue

        if stripped == "$":
            problems.append(f"line {num}: standalone single $ breaks display math")
        if stripped in (r"\[", r"\]"):
            problems.append(f"line {num}: use $$ delimiters for GitHub display math")
        if stripped == math_marker:
            in_math = not in_math
        elif in_math and re.match(r"^[+-]\s", stripped):
            problems.append(
                f"line {num}: leading + or - may turn a math line into a Markdown list"
            )
        if "input[...]" in stripped or "output[...]" in stripped:
            problems.append(f"line {num}: unfinished array-index placeholder")

    if in_code:
        problems.append("unclosed code fence")
    if in_math:
        problems.append("unclosed display-math block")

    if "**先修知识：**" not in body:
        problems.append("missing explicit prerequisites")
    if "练习" not in body or not any(word in body for word in ("答：", "答案", "参考答案")):
        problems.append("missing exercises or answers")
    if "来源" not in body:
        problems.append("missing source-verification section")

    for match in LINK.finditer(body):
        raw_link = match.group(1).split()[0]
        if raw_link.startswith(("https://", "http://", "mailto:", "#", "data:")):
            continue
        local = unquote(raw_link.split("#")[0].split("?")[0])
        if not local:
            continue
        target = (path.parent / local).resolve()
        if REPO_ROOT.resolve() not in target.parents and target != REPO_ROOT.resolve():
            problems.append(f"local link escapes repository: {raw_link}")
        elif not target.exists():
            problems.append(f"broken local link: {raw_link}")

    return problems


def main() -> int:
    chapter_paths = sorted(CHAPTER_DIR.glob("[0-9][0-9]-*.md"))
    if not chapter_paths:
        print("No textbook chapters found.", file=sys.stderr)
        return 1
    errors = 0
    for chapter in chapter_paths:
        issues = lint_chapter(chapter)
        rel = chapter.relative_to(REPO_ROOT)
        if issues:
            print(f"FAIL {rel}")
            for issue in issues:
                print(f"  - {issue}")
            errors += len(issues)
        else:
            print(f"PASS {rel}")
    if errors:
        print(f"\nFound {errors} issue(s) across {len(chapter_paths)} chapters.")
        return 1
    print(f"\nAll {len(chapter_paths)} chapters passed baseline checks.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
