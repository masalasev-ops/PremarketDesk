"""Atomic file writes, once.

Six copies of "write to a temp sibling, then os.replace" lived across the tree
until 2026-09-02: config.ca_bundle, deliver's delivery record, scan's packet,
market_today's holiday cache, monitor_jobs' rerun state and
universe.write_atomically, two of them with a retry loop for the antivirus
that intermittently denies a first write on this machine. config's docstring
explained that it could not reuse universe's version because core cannot
import selection. This module is in core, so every one of them can.

os.replace is atomic on Windows and on POSIX, and the temporary file is a
sibling because rename is only atomic within a filesystem. A reader either
sees the whole previous file or the whole new one, never a half written one;
a plain write_text truncates the destination before it writes, which is how a
run interrupted mid write left a packet that parsed as nothing.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any


def write_text_atomically(path: Path, text: str, attempts: int = 1,
                          retry_s: float = 0.0, encoding: str = "utf-8") -> None:
    """Write text so that the file on disk is always whole.

    `attempts` above one retries a denied write, sleeping `retry_s` between
    tries, because every documented instance of this machine's antivirus
    denying a first write has cleared on a retry. The last error is raised
    when the tries are spent; callers that must never raise catch it.
    """
    path = Path(path)
    temporary = path.with_name(path.name + ".partial")
    last: OSError | None = None
    for attempt in range(max(1, attempts)):
        try:
            temporary.write_text(text, encoding=encoding)
            os.replace(temporary, path)
            return
        except OSError as exc:
            last = exc
            if attempt + 1 < attempts and retry_s > 0:
                time.sleep(retry_s)
        finally:
            # A crash between the write and the replace leaves the sibling
            # behind. Nothing reads it, but it should not accumulate.
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
    assert last is not None
    raise last


def write_json_atomically(path: Path, payload: Any, indent: int = 2,
                          sort_keys: bool = False, attempts: int = 1,
                          retry_s: float = 0.0) -> None:
    """json.dumps, then write_text_atomically."""
    write_text_atomically(path, json.dumps(payload, indent=indent, sort_keys=sort_keys),
                          attempts=attempts, retry_s=retry_s)
