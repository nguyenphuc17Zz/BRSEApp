from typing import List, Dict, Any, Tuple, Optional
import io
import numpy as np
from PIL import Image
from app.core.logging import logger

class PaddleOCREngine:
    """
    Dedicated Offline OCR Engine powered by PaddleOCR PP-OCRv4 (via RapidOCR ONNX Runtime).
    Fast, highly accurate text detection and recognition for Japanese (Kanji/Kana)
    and Latin/Vietnamese scripts without external network or API dependencies.
    """

    def __init__(self):
        self._engine = None

    def _get_engine(self):
        if self._engine is None:
            try:
                from rapidocr_onnxruntime import RapidOCR
                self._engine = RapidOCR()
                logger.info("PaddleOCREngine: Successfully initialized RapidOCR PP-OCRv4.")
            except Exception as e:
                logger.error(f"PaddleOCREngine: Failed to load RapidOCR: {e}")
                raise e
        return self._engine

    def detect_and_recognize(self, image_bytes: bytes) -> List[Dict[str, Any]]:
        """
        Extracts text bounding boxes, text content, and confidence scores from image bytes.
        Returns a list of dicts with normalized 2D boxes [ymin, xmin, ymax, xmax] (0 to 1000 scale)
        compatible with the Inpainting and Overlay pipeline.
        """
        try:
            engine = self._get_engine()
            pil_img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
            orig_w, orig_h = pil_img.size
            img_np = np.array(pil_img)

            # RapidOCR accepts numpy ndarray (H, W, 3)
            result, elapse = engine(img_np)
            if not result:
                return []

            labels = []
            for item in result:
                # item format: [box_points, text, confidence]
                # box_points: [[x1, y1], [x2, y2], [x3, y3], [x4, y4]]
                box_pts, text, conf = item
                text = str(text or "").strip()
                if not text or conf < 0.35:
                    continue

                xs = [pt[0] for pt in box_pts]
                ys = [pt[1] for pt in box_pts]
                x_min = max(0, min(xs))
                x_max = min(orig_w, max(xs))
                y_min = max(0, min(ys))
                y_max = min(orig_h, max(ys))

                # Normalize to 0 - 1000 scale
                ymin_norm = int(y_min * 1000 / orig_h)
                xmin_norm = int(x_min * 1000 / orig_w)
                ymax_norm = int(y_max * 1000 / orig_h)
                xmax_norm = int(x_max * 1000 / orig_w)

                labels.append({
                    "box_2d": [ymin_norm, xmin_norm, ymax_norm, xmax_norm],
                    "original_text": text,
                    "confidence": round(float(conf), 3)
                })

            logger.info(f"PaddleOCREngine: Detected {len(labels)} text boxes in {elapse}s.")
            return labels

        except Exception as e:
            logger.warning(f"PaddleOCREngine detection failed: {e}")
            return []

paddle_ocr_engine = PaddleOCREngine()
