"""Structure-aware chunking (PRD C2): split on sections, pack paragraphs to ~400 tokens, keep tables whole."""

import hashlib
import re
from dataclasses import dataclass

import tiktoken

from policy_agent.ingest.documents import Block, Document

_ENC = tiktoken.get_encoding("cl100k_base")
MAX_TOKENS = 400


def n_tokens(text: str) -> int:
    return len(_ENC.encode(text))


@dataclass
class Chunk:
    chunk_id: str
    text: str
    section: str
    char_start: int
    tokens: int


def chunk_id(source_id: str, page: int, char_start: int) -> str:
    return hashlib.sha1(f"{source_id}|{page}|{char_start}".encode()).hexdigest()[:16]


def _split_long(block: Block) -> list[str]:
    sentences = re.split(r"(?<=[.!?])\s+", block.text)
    parts, cur = [], ""
    for s in sentences:
        if cur and n_tokens(cur + " " + s) > MAX_TOKENS:
            parts.append(cur)
            cur = s
        else:
            cur = f"{cur} {s}".strip()
    return parts + ([cur] if cur else [])


def chunk_document(doc: Document, page: int = 1, max_tokens: int = MAX_TOKENS) -> list[Chunk]:
    """Chunks never cross a section boundary. char_start is the offset into doc.text."""
    chunks: list[Chunk] = []
    offset = 0
    cur: list[tuple[str, int]] = []  # (text, offset)
    cur_section = ""

    def flush() -> None:
        nonlocal cur
        if cur:
            text = "\n\n".join(t for t, _ in cur)
            chunks.append(
                Chunk(
                    chunk_id(doc.source_id, page, cur[0][1]),
                    text,
                    cur_section,
                    cur[0][1],
                    n_tokens(text),
                )
            )
            cur = []

    for block in doc.blocks:
        start = offset
        offset += len(block.text) + 2  # the "\n\n" joiner used by Document.text
        if block.kind == "heading":
            flush()
            cur_section = block.text
            continue
        if block.section != cur_section:
            flush()
            cur_section = block.section
        pieces = [(block.text, start)]
        if block.kind != "table" and n_tokens(block.text) > max_tokens:
            pieces, pos = [], start
            for part in _split_long(block):
                pieces.append((part, pos))
                pos += len(part) + 1
        if block.kind == "table":
            flush()  # a table never shares a chunk with surrounding prose
        for text, pos in pieces:
            if cur and n_tokens("\n\n".join(t for t, _ in cur) + "\n\n" + text) > max_tokens:
                flush()
            cur.append((text, pos))
            if block.kind == "table":
                flush()  # tables are kept whole and stand alone
    flush()
    return chunks
