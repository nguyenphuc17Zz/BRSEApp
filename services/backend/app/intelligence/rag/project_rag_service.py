import json
import os
import re
from pathlib import Path
from typing import Dict, List, Any, Optional
from sqlalchemy import select, delete, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import logger
from app.db.models import Project
from app.documents.models import DocumentFile
from app.intelligence.models import ProjectDocumentChunk
from app.intelligence.rag.document_chunker import DocumentChunker

class ProjectRAGService:
    """Enterprise RAG Service for Project Knowledge Documents.
    Enables indexing, BM25 full-text retrieval, and token-budgeted context assembly
    across 20 to 100+ files without ever exceeding LLM context windows.
    """

    @classmethod
    async def index_document_text(
        cls,
        db: AsyncSession,
        project_id: str,
        filename: str,
        text_content: str,
        file_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> int:
        """Splits document text into semantic chunks and updates SQLite FTS5 index."""
        if not text_content or not text_content.strip():
            return 0

        # 1. Clean existing chunks for this specific document
        stmt_del_orm = delete(ProjectDocumentChunk).where(
            ProjectDocumentChunk.project_id == project_id,
            ProjectDocumentChunk.filename == filename
        )
        await db.execute(stmt_del_orm)

        try:
            await db.execute(
                text("DELETE FROM fts_project_documents WHERE project_id = :pid AND filename = :fn"),
                {"pid": project_id, "fn": filename}
            )
        except Exception as e:
            logger.debug(f"FTS5 clean notice for {filename}: {e}")

        # 2. Generate semantic chunks
        chunks = DocumentChunker.chunk_text(text_content, target_tokens=500, overlap_tokens=50)
        meta_str = json.dumps(metadata or {}, ensure_ascii=False)

        created_count = 0
        for ch in chunks:
            chunk_orm = ProjectDocumentChunk(
                project_id=project_id,
                file_id=file_id,
                filename=filename,
                chunk_index=ch.chunk_index,
                content=ch.content,
                char_count=ch.char_count,
                token_estimate=ch.token_estimate,
                metadata_json=meta_str
            )
            db.add(chunk_orm)
            await db.flush()

            # Insert into SQLite FTS5
            try:
                await db.execute(
                    text("""
                        INSERT INTO fts_project_documents(chunk_id, project_id, file_id, filename, chunk_index, content)
                        VALUES (:chunk_id, :pid, :fid, :fn, :c_idx, :cnt)
                    """),
                    {
                        "chunk_id": chunk_orm.id,
                        "pid": project_id,
                        "fid": file_id or "",
                        "fn": filename,
                        "c_idx": str(ch.chunk_index),
                        "cnt": ch.content
                    }
                )
            except Exception as e:
                logger.warning(f"FTS5 insert warning for {filename} chunk {ch.chunk_index}: {e}")

            created_count += 1

        await db.commit()
        logger.info(f"[RAG] Indexed '{filename}' into {created_count} chunks for project {project_id}")
        return created_count

    @classmethod
    def _extract_text_from_file_path(cls, path_str: str) -> str:
        """Extracts text from txt, md, docx, or pdf files on disk."""
        p = Path(path_str)
        if not p.exists():
            return ""

        ext = p.suffix.lower()
        if ext in [".txt", ".md", ".json", ".csv", ".log"]:
            try:
                with open(p, "r", encoding="utf-8", errors="ignore") as f:
                    return f.read()
            except Exception:
                return ""

        elif ext == ".docx":
            try:
                import docx
                doc = docx.Document(str(p))
                paragraphs = [p_el.text for p_el in doc.paragraphs if p_el.text.strip()]
                for table in doc.tables:
                    for row in table.rows:
                        row_txt = " | ".join([c.text.strip() for c in row.cells if c.text.strip()])
                        if row_txt:
                            paragraphs.append(row_txt)
                return "\n\n".join(paragraphs)
            except Exception as e:
                logger.warning(f"Docx text extract error on {p.name}: {e}")
                return ""

        elif ext == ".pdf":
            try:
                # Try pymupdf first
                try:
                    import pymupdf
                    doc = pymupdf.open(str(p))
                    pages_text = [page.get_text() for page in doc if page.get_text().strip()]
                    return "\n\n".join(pages_text)
                except ImportError:
                    import pypdf
                    reader = pypdf.PdfReader(str(p))
                    pages_text = []
                    for page in reader.pages:
                        txt = page.extract_text()
                        if txt and txt.strip():
                            pages_text.append(txt.strip())
                    return "\n\n".join(pages_text)
            except Exception as e:
                logger.warning(f"PDF text extract error on {p.name}: {e}")
                return ""

        return ""

    @classmethod
    async def index_document_file(cls, db: AsyncSession, doc_file: DocumentFile) -> int:
        """Reads a DocumentFile record and indexes its text into Project Document RAG."""
        if not doc_file.project_id:
            return 0
        raw_text = cls._extract_text_from_file_path(doc_file.original_path)
        if not raw_text:
            return 0

        return await cls.index_document_text(
            db=db,
            project_id=doc_file.project_id,
            filename=doc_file.filename,
            text_content=raw_text,
            file_id=doc_file.id,
            metadata={"file_type": doc_file.file_type, "unit_count": doc_file.unit_count}
        )

    @classmethod
    async def index_all_project_documents(cls, db: AsyncSession, project_id: str) -> Dict[str, Any]:
        """Indexes all documents belonging to a project."""
        stmt = select(DocumentFile).where(DocumentFile.project_id == project_id)
        docs = (await db.execute(stmt)).scalars().all()

        indexed_files = 0
        total_chunks = 0
        for d in docs:
            c = await cls.index_document_file(db, d)
            if c > 0:
                indexed_files += 1
                total_chunks += c

        return {
            "project_id": project_id,
            "total_documents": len(docs),
            "indexed_files": indexed_files,
            "total_chunks": total_chunks
        }

    @classmethod
    async def retrieve_relevant_chunks(
        cls,
        db: AsyncSession,
        project_id: Optional[str],
        query: str,
        top_k: int = 6
    ) -> List[Dict[str, Any]]:
        """Performs BM25 semantic full-text retrieval across project document chunks."""
        effective_pid = project_id if (project_id and project_id not in ("all", "default-project", "")) else None

        # Multi-lingual Token Extraction (English/Code + Katakana + Kanji + Latin/Vietnamese)
        alpha_words = [w for w in re.findall(r"[A-Za-z0-9_]{2,}", query)]
        katakana_words = [w for w in re.findall(r"[\u30A0-\u30FF]{2,}", query)]
        kanji_words = [w for w in re.findall(r"[\u4E00-\u9FAF]{2,}", query)]
        latin_words = [w for w in re.findall(r"[A-Za-z\u00C0-\u024F\u1EA0-\u1EF9]{2,}", query) if w not in alpha_words]

        words = list(dict.fromkeys(alpha_words + katakana_words + kanji_words + latin_words))
        if not words:
            # Fallback to general recent chunks
            stmt_f = select(ProjectDocumentChunk)
            if effective_pid:
                stmt_f = stmt_f.where(ProjectDocumentChunk.project_id == effective_pid)
            items = (await db.execute(stmt_f.order_by(ProjectDocumentChunk.created_at.desc()).limit(top_k))).scalars().all()
            return [{
                "chunk_id": it.id,
                "filename": it.filename,
                "chunk_index": it.chunk_index,
                "content": it.content,
                "token_estimate": it.token_estimate,
                "score": 1.0
            } for it in items]

        # 1. Try SQLite FTS5 BM25 search
        clean_fts_words = [f'"{w}"*' for w in words[:10] if len(w) >= 2]
        fts_match_query = " OR ".join(clean_fts_words) if clean_fts_words else ""

        results = []
        if fts_match_query:
            try:
                sql_fts = """
                    SELECT chunk_id, filename, chunk_index, content, bm25(fts_project_documents) as rank
                    FROM fts_project_documents
                    WHERE fts_project_documents MATCH :q
                """
                params: Dict[str, Any] = {"q": fts_match_query}
                if effective_pid:
                    sql_fts += " AND project_id = :pid"
                    params["pid"] = effective_pid
                sql_fts += f" ORDER BY rank ASC LIMIT {top_k * 2}"

                rows = (await db.execute(text(sql_fts), params)).fetchall()
                for r in rows:
                    results.append({
                        "chunk_id": r[0],
                        "filename": r[1],
                        "chunk_index": int(r[2]),
                        "content": r[3],
                        "token_estimate": DocumentChunker.estimate_tokens(r[3]),
                        "score": abs(float(r[4])) if r[4] is not None else 1.0
                    })
            except Exception as e:
                logger.debug(f"FTS5 MATCH failed or fallback used: {e}")

        # 2. Heuristic fallback over ORM if FTS5 returned fewer than top_k
        if len(results) < top_k:
            stmt_all = select(ProjectDocumentChunk)
            if effective_pid:
                stmt_all = stmt_all.where(ProjectDocumentChunk.project_id == effective_pid)
            candidates = (await db.execute(stmt_all.limit(100))).scalars().all()

            seen_ids = {r["chunk_id"] for r in results}
            scored_candidates = []
            for cand in candidates:
                if cand.id in seen_ids:
                    continue
                sc = 0.0
                c_low = cand.content.lower()
                fn_low = cand.filename.lower()
                for w in words:
                    wl = w.lower()
                    if wl in fn_low:
                        sc += 5.0
                    if wl in c_low:
                        sc += 2.0
                if sc > 0:
                    scored_candidates.append({
                        "chunk_id": cand.id,
                        "filename": cand.filename,
                        "chunk_index": cand.chunk_index,
                        "content": cand.content,
                        "token_estimate": cand.token_estimate,
                        "score": sc
                    })

            scored_candidates.sort(key=lambda x: x["score"], reverse=True)
            results.extend(scored_candidates[:top_k - len(results)])

        return results[:top_k]

    @classmethod
    async def build_rag_context(
        cls,
        db: AsyncSession,
        project_id: Optional[str],
        query: str,
        max_tokens: int = 2800
    ) -> Dict[str, Any]:
        """Assembles a 2-Tier RAG Context Block guaranteed to fit within token budget.
        Tier 1: Global Document Catalog of the project (~150 tokens).
        Tier 2: Deep BM25 semantic chunks (~2000-2500 tokens).
        """
        effective_pid = project_id if (project_id and project_id not in ("all", "default-project", "")) else None

        # Tier 1: Project Document Inventory Catalog
        catalog_lines = ["### [TẦNG 1: DANH MỤC TÀI LIỆU DỰ ÁN (PROJECT DOCUMENT CATALOG)]"]
        stmt_docs = select(DocumentFile.filename, DocumentFile.file_type, DocumentFile.unit_count)
        if effective_pid:
            stmt_docs = stmt_docs.where(DocumentFile.project_id == effective_pid)
        doc_rows = (await db.execute(stmt_docs.limit(30))).fetchall()

        if doc_rows:
            for fn, ftype, ucnt in doc_rows:
                catalog_lines.append(f"- 📄 {fn} ({ftype.upper()}, {ucnt or 1} phần)")
        else:
            catalog_lines.append("- (Chưa có danh mục file độc lập, dữ liệu được trích xuất từ văn bản đặc tả)")

        tier1_text = "\n".join(catalog_lines)
        tier1_tokens = DocumentChunker.estimate_tokens(tier1_text)

        # Tier 2: Deep Semantic Relevant Chunks
        remaining_tokens = max_tokens - tier1_tokens - 100
        retrieved_chunks = await cls.retrieve_relevant_chunks(db, project_id, query, top_k=6)

        tier2_blocks = ["\n### [TẦNG 2: ĐOẠN TRÍCH TÀI LIỆU LIÊN QUAN NHẤT (TOP RELEVANT CHUNKS)]"]
        citations = []
        accumulated_tokens = tier1_tokens

        for ch in retrieved_chunks:
            cite_label = f"[{ch['filename']} #Đoạn {ch['chunk_index'] + 1}]"
            block_text = f"--- {cite_label} ---\n{ch['content']}\n"
            block_tokens = DocumentChunker.estimate_tokens(block_text)

            if accumulated_tokens + block_tokens > max_tokens:
                break

            tier2_blocks.append(block_text)
            citations.append({
                "source": ch["filename"],
                "chunk_index": ch["chunk_index"],
                "citation": cite_label
            })
            accumulated_tokens += block_tokens

        full_context = tier1_text + "\n" + "\n".join(tier2_blocks)
        return {
            "context_markdown": full_context,
            "citations": citations,
            "total_tokens_used": accumulated_tokens,
            "retrieved_chunks_count": len(citations),
            "is_safe_for_llm": accumulated_tokens <= max_tokens
        }

project_rag_service = ProjectRAGService()
