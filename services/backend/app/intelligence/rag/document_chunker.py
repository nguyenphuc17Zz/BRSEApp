import re
from dataclasses import dataclass
from typing import List, Optional

@dataclass
class DocumentChunk:
    chunk_index: int
    content: str
    char_count: int
    token_estimate: int
    char_start: int
    char_end: int

class DocumentChunker:
    """Intelligent, multi-lingual text chunker for Vietnamese, Japanese, and English.
    Breaks large documents (txt, md, docx/pdf extracted text) on natural semantic boundaries
    (paragraphs, bullet points, Japanese full-stops, sentence terminals).
    """

    @classmethod
    def estimate_tokens(cls, text: str) -> int:
        """Accurate token estimator handling mixed CJK (Japanese/Chinese) and Latin/Vietnamese."""
        if not text:
            return 0
        # CJK characters typically represent 1 to 2 tokens each
        cjk_count = len(re.findall(r"[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF]", text))
        # Non-CJK words
        non_cjk_words = len(re.findall(r"[a-zA-Z0-9\u00C0-\u024F\u1EA0-\u1EF9]+", text))
        # Symbols and whitespace
        return int(cjk_count * 1.2 + non_cjk_words * 1.3) + 1

    @classmethod
    def chunk_text(
        cls,
        text: str,
        target_tokens: int = 500,
        overlap_tokens: int = 50,
        min_chunk_chars: int = 80
    ) -> List[DocumentChunk]:
        """Splits a document into overlapping semantic chunks safe for LLM context windows."""
        if not text or not text.strip():
            return []

        clean_text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
        if cls.estimate_tokens(clean_text) <= target_tokens:
            return [
                DocumentChunk(
                    chunk_index=0,
                    content=clean_text,
                    char_count=len(clean_text),
                    token_estimate=cls.estimate_tokens(clean_text),
                    char_start=0,
                    char_end=len(clean_text)
                )
            ]

        # Split into atomic semantic units: double-newline, single newline, Japanese full stops, latin sentence ends
        raw_units = re.split(r"(?<=\n\n)|(?<=\n)|(?<=[。！？])|(?<=[.!?]\s)", clean_text)
        units = [u for u in raw_units if u]

        chunks: List[DocumentChunk] = []
        current_units: List[str] = []
        current_tokens = 0
        chunk_idx = 0
        current_start_char = 0

        for unit in units:
            unit_tokens = cls.estimate_tokens(unit)

            # If a single unit is gigantic, subdivide it
            if unit_tokens > target_tokens:
                sub_chars = target_tokens * 3
                for i in range(0, len(unit), sub_chars):
                    sub_str = unit[i:i + sub_chars]
                    sub_tok = cls.estimate_tokens(sub_str)
                    if current_tokens + sub_tok > target_tokens and current_units:
                        chunk_content = "".join(current_units).strip()
                        if len(chunk_content) >= min_chunk_chars:
                            chunks.append(DocumentChunk(
                                chunk_index=chunk_idx,
                                content=chunk_content,
                                char_count=len(chunk_content),
                                token_estimate=cls.estimate_tokens(chunk_content),
                                char_start=current_start_char,
                                char_end=current_start_char + len(chunk_content)
                            ))
                            chunk_idx += 1
                        current_units = []
                        current_tokens = 0
                    current_units.append(sub_str)
                    current_tokens += sub_tok
                continue

            if current_tokens + unit_tokens > target_tokens and current_units:
                chunk_content = "".join(current_units).strip()
                if len(chunk_content) >= min_chunk_chars:
                    chunks.append(DocumentChunk(
                        chunk_index=chunk_idx,
                        content=chunk_content,
                        char_count=len(chunk_content),
                        token_estimate=cls.estimate_tokens(chunk_content),
                        char_start=current_start_char,
                        char_end=current_start_char + len(chunk_content)
                    ))
                    chunk_idx += 1

                # Overlap handling: retain the last unit or units matching overlap_tokens
                overlap_units = []
                overlap_cnt = 0
                for rev_u in reversed(current_units):
                    u_tok = cls.estimate_tokens(rev_u)
                    if overlap_cnt + u_tok <= overlap_tokens:
                        overlap_units.insert(0, rev_u)
                        overlap_cnt += u_tok
                    else:
                        break

                current_units = overlap_units
                current_tokens = overlap_cnt

            current_units.append(unit)
            current_tokens += unit_tokens

        # Flush final chunk
        if current_units:
            chunk_content = "".join(current_units).strip()
            if len(chunk_content) >= min_chunk_chars or not chunks:
                chunks.append(DocumentChunk(
                    chunk_index=chunk_idx,
                    content=chunk_content,
                    char_count=len(chunk_content),
                    token_estimate=cls.estimate_tokens(chunk_content),
                    char_start=current_start_char,
                    char_end=current_start_char + len(chunk_content)
                ))

        return chunks
