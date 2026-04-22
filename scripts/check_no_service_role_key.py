#!/usr/bin/env python3
"""Pre-commit hook: fail if any staged file assigns a non-empty value to SUPABASE_SERVICE_ROLE_KEY.

Scans the files passed on argv for patterns like:
    SUPABASE_SERVICE_ROLE_KEY=eyJhbGciOi...
    SUPABASE_SERVICE_ROLE_KEY = "eyJhbGciOi..."
and rejects the commit if a match is found. Empty assignments (as in .env.example)
are allowed so the template file stays checked in.

Exits 0 on success, 1 on findings.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# Match SUPABASE_SERVICE_ROLE_KEY followed by = (with optional spaces, optional quotes)
# and at least one non-space, non-quote character — i.e., a real value.
_PATTERN = re.compile(
    r"""SUPABASE_SERVICE_ROLE_KEY\s*=\s*["']?([^"'\s#][^"'\s#]*)""",
    re.IGNORECASE,
)

# Known safe placeholder substrings. If the captured value contains any of these
# (case-insensitive), we treat it as a placeholder and skip.
_SAFE_PLACEHOLDERS = (
    "your",
    "placeholder",
    "example",
    "fake",
    "dummy",
    "test",
    "xxx",
    "...",
)


def _looks_binary(sample: bytes) -> bool:
    # Heuristic: NUL byte -> binary.
    return b"\x00" in sample


def _is_placeholder(value: str) -> bool:
    lower = value.lower()
    return any(marker in lower for marker in _SAFE_PLACEHOLDERS)


def main(argv: list[str]) -> int:
    findings: list[tuple[str, int, str]] = []
    for path_str in argv:
        path = Path(path_str)
        if not path.is_file():
            continue
        try:
            head = path.read_bytes()[:4096]
            if _looks_binary(head):
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            match = _PATTERN.search(line)
            if match and not _is_placeholder(match.group(1)):
                findings.append((str(path), lineno, line.strip()))

    if findings:
        sys.stderr.write(
            "ERROR: a SUPABASE_SERVICE_ROLE_KEY value looks committed. "
            "Remove it, rotate the key via the Supabase dashboard, "
            "and use .env (git-ignored) instead.\n\n"
        )
        for path_str, lineno, line in findings:
            sys.stderr.write(f"  {path_str}:{lineno}: {line}\n")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
