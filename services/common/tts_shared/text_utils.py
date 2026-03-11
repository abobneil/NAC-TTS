from __future__ import annotations

import re


SENTENCE_BOUNDARY_RE = re.compile(r"(?<=[.!?])\s+")


def normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[^\S\n]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    return text.strip()


def _sentence_split(text: str) -> list[str]:
    return [part.strip() for part in SENTENCE_BOUNDARY_RE.split(text.strip()) if part.strip()]


def chunk_text(text: str, target_min: int = 700, target_max: int = 1200) -> list[str]:
    paragraphs = [part.strip() for part in text.split("\n\n") if part.strip()]
    chunks: list[str] = []
    current = ""

    def flush() -> None:
        nonlocal current
        if current.strip():
            chunks.append(current.strip())
        current = ""

    for paragraph in paragraphs:
        candidate = f"{current}\n\n{paragraph}".strip() if current else paragraph
        if len(candidate) <= target_max:
            current = candidate
            continue

        if current and len(current) >= target_min:
            flush()

        if len(paragraph) <= target_max:
            current = paragraph
            continue

        sentence_chunk = ""
        for sentence in _sentence_split(paragraph):
            next_candidate = f"{sentence_chunk} {sentence}".strip() if sentence_chunk else sentence
            if len(next_candidate) <= target_max:
                sentence_chunk = next_candidate
                continue
            if sentence_chunk:
                chunks.append(sentence_chunk)
            if len(sentence) <= target_max:
                sentence_chunk = sentence
                continue
            for offset in range(0, len(sentence), target_max):
                chunks.append(sentence[offset:offset + target_max].strip())
            sentence_chunk = ""
        if sentence_chunk:
            current = sentence_chunk

    flush()
    return chunks or [text.strip()]
