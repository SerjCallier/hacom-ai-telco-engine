"""Markdown runbook corpus loader.

Chunks are section-level (one ``## heading`` block each) because that is the unit
a network engineer actually cites: "the detection section of the congestion
runbook", not "somewhere in a 40-page PDF".

Chunk ids are stable (``doc_id#section-slug``) so an answer can point at the exact
text it used, and so retrieval quality can be asserted in tests.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

DEFAULT_CORPUS_DIR = Path(__file__).resolve().parents[2] / "data" / "runbooks"

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return _SLUG_RE.sub("-", normalized.lower()).strip("-")


@dataclass(frozen=True, slots=True)
class Chunk:
    chunk_id: str
    doc_id: str
    doc_title: str
    section: str
    text: str
    source: str

    @property
    def snippet(self) -> str:
        return " ".join(self.text.split())


def _parse_document(path: Path) -> list[Chunk]:
    raw = path.read_text(encoding="utf-8")
    doc_id = slugify(path.stem)

    title = path.stem.replace("-", " ").title()
    source = "Internal engineering note"
    body_lines: list[str] = []

    for line in raw.splitlines():
        if line.startswith("# ") and title == path.stem.replace("-", " ").title():
            title = line[2:].strip()
        elif line.startswith("> Source:"):
            source = line[len("> Source:") :].strip()
        else:
            body_lines.append(line)

    body = "\n".join(body_lines)
    sections = re.split(r"^## ", body, flags=re.MULTILINE)

    chunks: list[Chunk] = []
    for block in sections:
        block = block.strip()
        if not block:
            continue
        heading, _, content = block.partition("\n")
        section = heading.strip()
        chunks.append(
            Chunk(
                chunk_id=f"{doc_id}#{slugify(section)}",
                doc_id=doc_id,
                doc_title=title,
                section=section,
                text=content.strip(),
                source=source,
            )
        )
    return chunks


def load_corpus(corpus_dir: Path | None = None) -> list[Chunk]:
    directory = corpus_dir or DEFAULT_CORPUS_DIR
    chunks: list[Chunk] = []
    for path in sorted(directory.glob("*.md")):
        chunks.extend(_parse_document(path))
    return chunks
