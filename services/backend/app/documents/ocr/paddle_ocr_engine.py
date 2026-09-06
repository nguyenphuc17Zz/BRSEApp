import io
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional
import numpy as np
from PIL import Image
import httpx
from app.core.logging import logger

MODELS_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data" / "models" / "paddleocr"
JA_MODEL_PATH = MODELS_DIR / "japan_PP-OCRv3_rec_infer.onnx"
JA_DICT_PATH = MODELS_DIR / "japan_dict.txt"

JA_MODEL_URL = "https://huggingface.co/breezedeus/cnocr-ppocr-japan_PP-OCRv3/resolve/main/japan_PP-OCRv3_rec_infer.onnx"
JA_DICT_URL = "https://raw.githubusercontent.com/PaddlePaddle/PaddleOCR/main/ppocr/utils/dict/japan_dict.txt"

class PaddleOCREngine:
    """
    Dedicated Offline OCR Engine powered by PaddleOCR PP-OCR (via RapidOCR ONNX Runtime).
    Supports dedicated Japanese PP-OCRv3 (Hiragana, Katakana, Kanji) for Japanese documents,
    with automatic fallback to default multilingual PP-OCRv4.
    """

    def __init__(self):
        self._default_engine = None
        self._ja_engine = None

    def _ensure_ja_models(self) -> bool:
        """Ensures the dedicated Japanese PP-OCRv3 model and dictionary exist locally."""
        if JA_MODEL_PATH.exists() and JA_DICT_PATH.exists() and JA_MODEL_PATH.stat().st_size > 100000:
            return True
        try:
            MODELS_DIR.mkdir(parents=True, exist_ok=True)
            logger.info("PaddleOCREngine: Downloading dedicated Japanese PP-OCRv3 model (~10MB)...")
            with httpx.Client(follow_redirects=True, timeout=60.0) as client:
                if not JA_DICT_PATH.exists():
                    r = client.get(JA_DICT_URL)
                    if r.status_code == 200:
                        JA_DICT_PATH.write_bytes(r.content)
                if not JA_MODEL_PATH.exists() or JA_MODEL_PATH.stat().st_size < 100000:
                    r = client.get(JA_MODEL_URL)
                    if r.status_code == 200:
                        JA_MODEL_PATH.write_bytes(r.content)
            return JA_MODEL_PATH.exists() and JA_DICT_PATH.exists()
        except Exception as dl_err:
            logger.warning(f"PaddleOCREngine: Failed downloading Japanese model: {dl_err}")
            return False

    def _get_engine(self, lang: str = "ja"):
        is_ja = (lang or "").lower() in ("ja", "japanese", "jp")
        if is_ja:
            if self._ja_engine is None:
                try:
                    if self._ensure_ja_models():
                        from rapidocr_onnxruntime import RapidOCR
                        self._ja_engine = RapidOCR(
                            rec_model_path=str(JA_MODEL_PATH),
                            rec_char_dict_path=str(JA_DICT_PATH),
                            rec_img_shape=[3, 48, 320]
                        )
                        logger.info("PaddleOCREngine: Successfully initialized dedicated Japanese PP-OCRv3 engine.")
                except Exception as ja_err:
                    logger.warning(f"PaddleOCREngine: Could not initialize Japanese engine: {ja_err}. Falling back to default.")
            if self._ja_engine is not None:
                return self._ja_engine

        if self._default_engine is None:
            try:
                from rapidocr_onnxruntime import RapidOCR
                self._default_engine = RapidOCR()
                logger.info("PaddleOCREngine: Successfully initialized default RapidOCR PP-OCRv4 engine.")
            except Exception as e:
                logger.error(f"PaddleOCREngine: Failed to load RapidOCR: {e}")
                raise e
        return self._default_engine

    def detect_and_recognize(self, image_bytes: bytes, lang: str = "ja") -> List[Dict[str, Any]]:
        """
        Extracts text bounding boxes, text content, and confidence scores from image bytes.
        Uses dedicated Japanese PP-OCRv3 when lang is 'ja' to recognize Hiragana, Katakana, and Kanji.
        Returns a list of dicts with normalized 2D boxes [ymin, xmin, ymax, xmax] (0 to 1000 scale).
        """
        try:
            engine = self._get_engine(lang=lang)
            pil_img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
            orig_w, orig_h = pil_img.size
            min_dim = min(orig_w, orig_h)
            max_dim = max(orig_w, orig_h)

            # Adaptive super-resolution scaling:
            # Low-res diagram crops (<600px min or <1200px max) have tiny 10-12px font that causes
            # character stroke collisions in Kanji/Katakana. Upscaling 2x-3x with LANCZOS + contrast boost
            # dramatically improves text detection and recognition accuracy.
            scale = 1.0
            if min_dim < 600 or max_dim < 1200:
                scale = max(2.0, min(3.0, 1200.0 / max(max_dim, 1)))
                new_w, new_h = int(orig_w * scale), int(orig_h * scale)
                scaled_img = pil_img.resize((new_w, new_h), Image.Resampling.LANCZOS)
                try:
                    from PIL import ImageEnhance
                    scaled_img = ImageEnhance.Contrast(scaled_img).enhance(1.15)
                except Exception:
                    pass
                img_np = np.array(scaled_img)
            else:
                img_np = np.array(pil_img)

            # RapidOCR accepts numpy ndarray (H, W, 3).
            # Override text_score and box_thresh so RapidOCR does not silently discard low-confidence/small Kanji.
            result, elapse = engine(
                img_np,
                text_score=0.20,
                box_thresh=0.25,
                unclip_ratio=1.6
            )
            if not result:
                return []

            labels = []
            for item in result:
                # item format: [box_points, text, confidence]
                # box_points: [[x1, y1], [x2, y2], [x3, y3], [x4, y4]]
                box_pts, text, conf = item
                text = str(text or "").strip()
                if not text or conf < 0.25:
                    continue

                if scale != 1.0:
                    box_pts = [[pt[0] / scale, pt[1] / scale] for pt in box_pts]

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

            logger.info(f"PaddleOCREngine ({'Japanese' if (lang or '').lower() in ('ja', 'japanese', 'jp') else 'Default'}): Detected {len(labels)} text boxes (scale: {scale}x) in {elapse}s.")
            return labels

        except Exception as e:
            logger.warning(f"PaddleOCREngine detection failed: {e}")
            return []

paddle_ocr_engine = PaddleOCREngine()

