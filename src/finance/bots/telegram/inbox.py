"""Persist inbound PDFs to `~/.finance/inbox/<sha256>.pdf` before ingestion.

Content-addressed names give us free de-duplication of identical re-uploads
(scenario in `telegram-bot/spec.md`). The directory is created at mode 0700
on first use to match the rest of `~/.finance/`.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from finance.core import paths

INBOX_DIRNAME = "inbox"


def inbox_dir() -> Path:
    """Return `~/.finance/inbox/`, creating it (mode 0700) if missing."""
    runtime = paths.runtime_dir()
    target = runtime / INBOX_DIRNAME
    if not target.exists():
        target.mkdir(parents=True, mode=0o700)
    return target


@dataclass(frozen=True, slots=True)
class SavedArtifact:
    path: Path
    sha256: str
    size_bytes: int
    is_new: bool


def save_pdf_bytes(data: bytes) -> SavedArtifact:
    """Write `data` to `inbox/<sha256>.pdf` and return its path metadata.

    Idempotent on identical inputs: re-saving the same bytes does not
    duplicate the file on disk.
    """
    sha = hashlib.sha256(data).hexdigest()
    target = inbox_dir() / f"{sha}.pdf"
    is_new = not target.exists()
    if is_new:
        target.write_bytes(data)
    return SavedArtifact(
        path=target,
        sha256=sha,
        size_bytes=len(data),
        is_new=is_new,
    )
