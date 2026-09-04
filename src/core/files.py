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

import gzip
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


# ---------------------------------------------------------------------------
# Compressed artifacts.
#
# A run directory older than CRITERIA [Retention] hot_sessions is gzipped in
# place: packet.json becomes packet.json.gz and nothing else changes. That is
# a 12.5 percent packet and a 25 percent report, measured 2026-09-04, and it
# is the whole of the retention saving that does not delete anything.
#
# READERS MUST NOT CARE. Every reader that opens a run artifact goes through
# read_text_maybe_gz, which prefers the plain file and falls back to the
# gzipped sibling, so a warm session reads exactly like a hot one and a
# gunzip by hand puts a session back to hot with nothing else to do.
#
# The plain file WINS when both exist. Both existing means a compression that
# was interrupted between writing the .gz and removing the original, and the
# original is the one nothing can have truncated.


def resolve_maybe_gz(path: Path) -> Path | None:
    """The readable form of `path`: itself, else its .gz sibling, else None."""
    path = Path(path)
    if path.is_file():
        return path
    packed = path.with_name(path.name + ".gz")
    return packed if packed.is_file() else None


def read_text_maybe_gz(path: Path, encoding: str = "utf-8") -> str:
    """Read `path`, transparently accepting a gzipped sibling.

    Raises FileNotFoundError naming the PLAIN path when neither exists, so a
    caller's error message reads the same whether or not retention has run.
    """
    found = resolve_maybe_gz(path)
    if found is None:
        raise FileNotFoundError(str(path))
    if found.suffix == ".gz":
        with gzip.open(found, "rt", encoding=encoding) as handle:
            return handle.read()
    return found.read_text(encoding=encoding)


def read_json_maybe_gz(path: Path) -> Any:
    """json.loads of read_text_maybe_gz."""
    return json.loads(read_text_maybe_gz(path))


def gzip_in_place(path: Path, attempts: int = 1, retry_s: float = 0.0) -> int:
    """Replace `path` with `path.gz`, atomically, and return the bytes saved.

    Zero when there is nothing to do: no such file, or already compressed.

    The .gz is written to a .partial sibling and os.replace'd into position
    BEFORE the original is unlinked, so a crash at any point leaves either the
    original alone or both files, and read_text_maybe_gz prefers the original.
    There is no window in which neither is readable.
    """
    path = Path(path)
    if not path.is_file():
        return 0
    packed = path.with_name(path.name + ".gz")
    raw = path.read_bytes()
    temporary = packed.with_name(packed.name + ".partial")
    last: OSError | None = None
    for attempt in range(max(1, attempts)):
        try:
            temporary.write_bytes(gzip.compress(raw, 9))
            os.replace(temporary, packed)
            break
        except OSError as exc:
            last = exc
            if attempt + 1 < attempts and retry_s > 0:
                time.sleep(retry_s)
        finally:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
    else:
        assert last is not None
        raise last
    saved = len(raw) - packed.stat().st_size
    path.unlink()
    return saved
