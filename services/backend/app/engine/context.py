import json
from typing import Dict, List, Optional, Any
import numpy as np
from sqlalchemy import select, or_, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import logger
from app.db.models import (
    Project, ProjectInstruction, GlossaryTerm, TranslationMemory,
    TranslationCorrection, StyleProfile
)
from app.providers.registry import provider_registry

def cosine_similarity(v1: List[float], v2: List[float]) -> float:
    """Computes cosine similarity between two float vectors."""
    try:
        a = np.array(v1)
        b = np.array(v2)
        dot = np.dot(a, b)
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return float(dot / (norm_a * norm_b))
    except Exception:
        return 0.0

class ContextEngine:
    """Builds intelligent context packages prioritizing Project Rules, Glossaries, TM, and Corrections."""

    async def build_context(
        self,
        db: AsyncSession,
        source_text: str,
        project_id: Optional[str] = None,
        style: str = "auto",
        source_lang: str = "ja",
        target_lang: str = "vi"
    ) -> Dict[str, Any]:
        context_package: Dict[str, Any] = {
            "project": None,
            "project_instructions": [],
            "glossary_terms": [],
            "translation_memory": [],
            "corrections": [],
            "style_profile": None,
        }

        # 1. Load Project & Instructions
        if project_id:
            proj_res = await db.execute(select(Project).where(Project.id == project_id))
            project = proj_res.scalar_one_or_none()
            if project:
                context_package["project"] = {
                    "id": project.id,
                    "name": project.name,
                    "code": project.code,
                    "client": project.client_name,
                    "description": project.description
                }
                # Load project instructions
                inst_res = await db.execute(
                    select(ProjectInstruction)
                    .where(and_(ProjectInstruction.project_id == project_id, ProjectInstruction.is_active == True))
                    .order_by(ProjectInstruction.priority.desc())
                )
                context_package["project_instructions"] = [
                    inst.rule_text for inst in inst_res.scalars().all()
                ]

        # 2. Retrieve Relevant Glossary Terms (Hierarchical: Project > Client > Global)
        glossary_terms = await self._retrieve_glossary(db, source_text, project_id, source_lang, target_lang)
        context_package["glossary_terms"] = glossary_terms

        # 3. Retrieve Relevant Translation Memory (Hybrid: Lexical Substring + Vector Similarity)
        tm_items = await self._retrieve_translation_memory(db, source_text, project_id, source_lang, target_lang)
        context_package["translation_memory"] = tm_items

        # 4. Retrieve Relevant User Corrections
        corrections = await self._retrieve_corrections(db, source_text, project_id)
        context_package["corrections"] = corrections

        # 5. Load Style Profile
        if style and style != "auto":
            context_package["style_profile"] = {"register": style}
        elif project_id and context_package.get("project"):
            style_res = await db.execute(
                select(StyleProfile).where(StyleProfile.project_id == project_id)
            )
            sp = style_res.scalar_one_or_none()
            if sp:
                context_package["style_profile"] = {
                    "name": sp.name,
                    "register": sp.register,
                    "technical_handling": sp.technical_handling,
                    "sentence_length": sp.sentence_length
                }

        return context_package

    async def _retrieve_glossary(
        self,
        db: AsyncSession,
        source_text: str,
        project_id: Optional[str],
        source_lang: str,
        target_lang: str
    ) -> List[Dict[str, Any]]:
        """Finds glossary terms matching the source text directly or within substring."""
        query = select(GlossaryTerm).where(
            and_(
                GlossaryTerm.is_active == True,
                or_(
                    GlossaryTerm.project_id == project_id,
                    GlossaryTerm.project_id == None,
                    GlossaryTerm.scope.in_(["global", "company"])
                )
            )
        )
        res = await db.execute(query)
        all_terms = res.scalars().all()

        matched = []
        for term in all_terms:
            # Substring match in source text (case-insensitive for Latin terms)
            if term.source_term in source_text or term.source_term.lower() in source_text.lower():
                matched.append({
                    "source_term": term.source_term,
                    "target_term": term.target_term,
                    "category": term.category,
                    "definition": term.definition,
                    "priority": term.priority,
                    "scope": term.scope
                })

        # Sort by specificity (project terms over global terms, higher priority first, longer terms first)
        matched.sort(key=lambda x: (x["scope"] == "project", x["priority"], len(x["source_term"])), reverse=True)
        return matched[:15] # Keep top 15 most relevant

    async def _retrieve_translation_memory(
        self,
        db: AsyncSession,
        source_text: str,
        project_id: Optional[str],
        source_lang: str,
        target_lang: str
    ) -> List[Dict[str, Any]]:
        """Retrieves similar past translations using substring overlap and vector similarity."""
        query = select(TranslationMemory).where(
            or_(
                TranslationMemory.project_id == project_id,
                TranslationMemory.project_id == None
            )
        ).order_by(TranslationMemory.created_at.desc()).limit(100)

        res = await db.execute(query)
        candidates = res.scalars().all()
        if not candidates:
            return []

        # Get embedding of source_text from Ollama if available
        ollama_prov = provider_registry.get_provider("ollama")
        source_emb = None
        if ollama_prov:
            source_emb = await ollama_prov.get_embedding(source_text)

        scored = []
        for item in candidates:
            sim = 0.0
            # Exact or substring match heuristic
            if item.source_text == source_text:
                sim = 1.0
            elif item.source_text in source_text or source_text in item.source_text:
                sim = 0.85
            elif source_emb and item.embedding_vector:
                try:
                    item_emb = json.loads(item.embedding_vector)
                    sim = cosine_similarity(source_emb, item_emb)
                except Exception:
                    sim = 0.0

            if sim >= 0.65:
                scored.append({
                    "source_text": item.source_text,
                    "target_text": item.target_text,
                    "similarity": round(sim, 2),
                    "style": item.style
                })

        scored.sort(key=lambda x: x["similarity"], reverse=True)
        return scored[:3]

    async def _retrieve_corrections(
        self,
        db: AsyncSession,
        source_text: str,
        project_id: Optional[str]
    ) -> List[Dict[str, Any]]:
        """Finds previous user corrections for similar or identical source sentences."""
        query = select(TranslationCorrection).where(
            or_(
                TranslationCorrection.project_id == project_id,
                TranslationCorrection.apply_scope == "global"
            )
        ).order_by(TranslationCorrection.created_at.desc()).limit(20)

        res = await db.execute(query)
        corrections = res.scalars().all()
        matched = []
        for c in corrections:
            if c.source_text in source_text or source_text in c.source_text:
                matched.append({
                    "source_text": c.source_text,
                    "original_translation": c.original_translation,
                    "corrected_translation": c.corrected_translation,
                    "note": c.context_note
                })
        return matched[:3]

context_engine = ContextEngine()
