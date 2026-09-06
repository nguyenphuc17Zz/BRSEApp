from abc import ABC, abstractmethod
from typing import Dict, List, Any

class OCREngine(ABC):
    """Abstract base class for OCR engines."""

    @abstractmethod
    async def extract_text_from_image(self, image_bytes: bytes) -> List[Dict[str, Any]]:
        """
        Extracts text with bounding boxes and confidence score from image bytes.
        Returns list of {"text": str, "confidence": float, "bbox": [x0, y0, x1, y1]}.
        """
        pass
