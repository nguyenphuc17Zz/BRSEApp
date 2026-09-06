from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, List, Tuple, Any, Optional
from app.documents.segmenter import ParsedSegment

class DocumentParser(ABC):
    """Abstract base class for all document format parsers."""

    @abstractmethod
    def parse(self, file_path: Path, options: Optional[Dict[str, Any]] = None) -> Tuple[List[ParsedSegment], Dict[str, Any]]:
        """
        Parses a document file.
        Returns:
            (list_of_segments, document_metadata)
            where document_metadata includes unit_count, unit_label, sheets/slides list, etc.
        """
        pass
