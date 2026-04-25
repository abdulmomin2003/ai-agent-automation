"""
Smart text chunker with token-aware splitting.

Uses recursive splitting strategy that respects document structure
(headings, paragraphs, sentences) to create semantically coherent chunks.
"""

import re
import logging
from dataclasses import dataclass, field
from typing import Optional

import tiktoken

from config import settings

logger = logging.getLogger(__name__)


@dataclass
class Chunk:
    """Represents a text chunk with metadata."""
    text: str
    chunk_index: int
    metadata: dict = field(default_factory=dict)
    token_count: int = 0


class TextChunker:
    """
    Recursive token-aware text chunker.

    Splits text by structural boundaries (headings → paragraphs → sentences
    → words) while respecting token limits and maintaining overlap for
    context continuity.
    """

    # Separators in order of priority (try largest units first)
    SEPARATORS = [
        "\n\n\n",       # Major section breaks
        "\n\n",          # Paragraph breaks
        "\n",            # Line breaks
        ". ",            # Sentence boundaries
        "? ",            # Question boundaries
        "! ",            # Exclamation boundaries
        "; ",            # Clause boundaries
        ", ",            # Phrase boundaries
        " ",             # Word boundaries
    ]

    def __init__(
        self,
        chunk_size: int = settings.CHUNK_SIZE,
        chunk_overlap: int = settings.CHUNK_OVERLAP,
        model: str = settings.EMBEDDING_MODEL,
    ):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        try:
            self.tokenizer = tiktoken.encoding_for_model(model)
        except KeyError:
            self.tokenizer = tiktoken.get_encoding("cl100k_base")

    def count_tokens(self, text: str) -> int:
        """Count tokens in a text string."""
        return len(self.tokenizer.encode(text))

    def chunk_text(
        self,
        text: str,
        metadata: Optional[dict] = None,
    ) -> list[Chunk]:
        """
        Split text into semantically coherent, overlapping chunks.

        Args:
            text: The text to chunk.
            metadata: Base metadata to attach to each chunk.

        Returns:
            List of Chunk objects.
        """
        if not text or not text.strip():
            return []

        base_metadata = metadata or {}
        raw_chunks = self._recursive_split(text, 0)

        # Merge very small chunks with neighbors
        merged = self._merge_small_chunks(raw_chunks)

        # Add overlap between chunks for context continuity
        overlapped = self._add_overlap(merged)

        # Build final Chunk objects
        chunks = []
        for i, chunk_text in enumerate(overlapped):
            token_count = self.count_tokens(chunk_text)
            chunk_metadata = {
                **base_metadata,
                "chunk_index": i,
                "chunk_total": len(overlapped),
                "token_count": token_count,
            }
            chunks.append(Chunk(
                text=chunk_text,
                chunk_index=i,
                metadata=chunk_metadata,
                token_count=token_count,
            ))

        logger.info(
            f"Created {len(chunks)} chunks "
            f"(avg {sum(c.token_count for c in chunks) // max(len(chunks), 1)} tokens/chunk)"
        )
        return chunks

    def _recursive_split(self, text: str, sep_index: int) -> list[str]:
        """Recursively split text using progressively finer separators."""
        if self.count_tokens(text) <= self.chunk_size:
            return [text.strip()] if text.strip() else []

        if sep_index >= len(self.SEPARATORS):
            # Last resort: hard cut by tokens
            return self._hard_split(text)

        separator = self.SEPARATORS[sep_index]
        parts = text.split(separator)

        if len(parts) == 1:
            # This separator didn't help, try the next one
            return self._recursive_split(text, sep_index + 1)

        # Group parts into chunks that fit within the token limit
        chunks = []
        current = ""

        for part in parts:
            candidate = (
                current + separator + part if current else part
            )
            if self.count_tokens(candidate) <= self.chunk_size:
                current = candidate
            else:
                if current.strip():
                    chunks.append(current.strip())
                # If this single part is too big, recursively split it
                if self.count_tokens(part) > self.chunk_size:
                    sub_chunks = self._recursive_split(
                        part, sep_index + 1
                    )
                    chunks.extend(sub_chunks)
                    current = ""
                else:
                    current = part

        if current.strip():
            chunks.append(current.strip())

        return chunks

    def _hard_split(self, text: str) -> list[str]:
        """Hard split by token count when no separator works."""
        tokens = self.tokenizer.encode(text)
        chunks = []
        for i in range(0, len(tokens), self.chunk_size):
            chunk_tokens = tokens[i : i + self.chunk_size]
            chunk_text = self.tokenizer.decode(chunk_tokens)
            if chunk_text.strip():
                chunks.append(chunk_text.strip())
        return chunks

    def _merge_small_chunks(
        self, chunks: list[str], min_tokens: int = 50
    ) -> list[str]:
        """Merge chunks that are too small with their neighbors."""
        if len(chunks) <= 1:
            return chunks

        merged = []
        buffer = ""

        for chunk in chunks:
            if buffer:
                candidate = buffer + "\n\n" + chunk
                if self.count_tokens(candidate) <= self.chunk_size:
                    buffer = candidate
                else:
                    merged.append(buffer)
                    buffer = chunk
            elif self.count_tokens(chunk) < min_tokens:
                buffer = chunk
            else:
                buffer = chunk

        if buffer:
            # If last buffer is tiny, merge with previous
            if (
                merged
                and self.count_tokens(buffer) < min_tokens
                and self.count_tokens(merged[-1] + "\n\n" + buffer)
                <= self.chunk_size
            ):
                merged[-1] = merged[-1] + "\n\n" + buffer
            else:
                merged.append(buffer)

        return merged

    def _add_overlap(self, chunks: list[str]) -> list[str]:
        """Add overlap between consecutive chunks for context continuity."""
        if len(chunks) <= 1 or self.chunk_overlap <= 0:
            return chunks

        overlapped = []
        for i, chunk in enumerate(chunks):
            if i == 0:
                overlapped.append(chunk)
                continue

            # Get the tail of the previous chunk as overlap
            prev_tokens = self.tokenizer.encode(chunks[i - 1])
            overlap_tokens = prev_tokens[-self.chunk_overlap :]
            overlap_text = self.tokenizer.decode(overlap_tokens).strip()

            # Prepend overlap context
            new_chunk = f"...{overlap_text}\n\n{chunk}"

            # If it exceeds the limit, trim the overlap
            if self.count_tokens(new_chunk) > self.chunk_size + self.chunk_overlap:
                overlapped.append(chunk)
            else:
                overlapped.append(new_chunk)

        return overlapped
