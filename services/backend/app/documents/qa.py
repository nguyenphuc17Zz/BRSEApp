import re
from typing import Dict, List, Any
from app.documents.models import DocumentIssue

class DocumentQAChecker:
    """Performs document-level QA checks with severity classification (INFO, WARNING, ERROR, CRITICAL)."""

    NUMBER_PATTERN = re.compile(r"\b\d+(?:[\.,]\d+)?\b")
    URL_PATTERN = re.compile(r"https?://[^\s/$.?#].[^\s]*")

    @classmethod
    def check_segment(
        cls,
        job_id: str,
        segment_id: str,
        source_text: str,
        translated_text: str,
        location_text: str,
        protected_tokens_map: Dict[str, str]
    ) -> List[DocumentIssue]:
        issues: List[DocumentIssue] = []

        if not translated_text or not translated_text.strip():
            issues.append(DocumentIssue(
                job_id=job_id,
                segment_id=segment_id,
                severity="CRITICAL",
                category="missing_segment",
                location_text=location_text,
                message="Translated segment is empty."
            ))
            return issues

        # 1. Protected tokens check
        for token_key, orig_val in protected_tokens_map.items():
            if token_key in translated_text:
                issues.append(DocumentIssue(
                    job_id=job_id,
                    segment_id=segment_id,
                    severity="ERROR",
                    category="token_unrestored",
                    location_text=location_text,
                    message=f"Protected token placeholder '{token_key}' was not restored (value: '{orig_val}')."
                ))

        # 2. Number check
        src_nums = set(cls.NUMBER_PATTERN.findall(source_text))
        tgt_nums = set(cls.NUMBER_PATTERN.findall(translated_text))
        missing_nums = src_nums - tgt_nums
        if missing_nums:
            issues.append(DocumentIssue(
                job_id=job_id,
                segment_id=segment_id,
                severity="WARNING",
                category="number_mismatch",
                location_text=location_text,
                message=f"Numbers {list(missing_nums)} from source text not found in translation."
            ))

        # 3. URL check
        src_urls = set(cls.URL_PATTERN.findall(source_text))
        tgt_urls = set(cls.URL_PATTERN.findall(translated_text))
        missing_urls = src_urls - tgt_urls
        if missing_urls:
            issues.append(DocumentIssue(
                job_id=job_id,
                segment_id=segment_id,
                severity="ERROR",
                category="url_missing",
                location_text=location_text,
                message=f"URLs {list(missing_urls)} missing from translation."
            ))

        return issues
