import os
import shutil
from pathlib import Path
from typing import Optional
from app.core.config import DATA_DIR
from app.core.logging import logger

DOCUMENTS_DIR = DATA_DIR / "documents"
ORIGINAL_DIR = DOCUMENTS_DIR / "original"
WORKING_DIR = DOCUMENTS_DIR / "working"
OUTPUT_DIR = DOCUMENTS_DIR / "output"
TEMP_DIR = DOCUMENTS_DIR / "temp"

for d in [ORIGINAL_DIR, WORKING_DIR, OUTPUT_DIR, TEMP_DIR]:
    d.mkdir(parents=True, exist_ok=True)

class DocumentStorage:
    """Manages document storage lifecycles across original, working, output, and temp files."""

    @classmethod
    def save_original(cls, filename: str, content: bytes) -> Path:
        target = ORIGINAL_DIR / filename
        # Ensure unique name if exists
        base = target.stem
        ext = target.suffix
        counter = 1
        while target.exists():
            target = ORIGINAL_DIR / f"{base}_{counter}{ext}"
            counter += 1

        with open(target, "wb") as f:
            f.write(content)
        return target

    @classmethod
    def create_working_copy(cls, original_path: Path, job_id: str) -> Path:
        ext = original_path.suffix
        working_path = WORKING_DIR / f"job_{job_id}_working{ext}"
        shutil.copy2(original_path, working_path)
        return working_path

    @classmethod
    def get_output_path(
        cls,
        original_filename: str,
        target_lang: str,
        custom_dir: Optional[str] = None,
        custom_filename: Optional[str] = None
    ) -> Path:
        target_directory = OUTPUT_DIR
        if custom_dir and custom_dir.strip():
            try:
                p = Path(custom_dir.strip())
                p.mkdir(parents=True, exist_ok=True)
                target_directory = p
            except Exception as e:
                logger.warning(f"Could not create or access custom output directory '{custom_dir}': {e}. Falling back to default OUTPUT_DIR.")

        path = Path(original_filename)
        ext = path.suffix

        if custom_filename and custom_filename.strip():
            cleaned = custom_filename.strip()
            if ext and not cleaned.lower().endswith(ext.lower()):
                cleaned = f"{cleaned}{ext}"
            c_stem = Path(cleaned).stem
            c_ext = Path(cleaned).suffix
            out_path = target_directory / cleaned
            counter = 1
            while out_path.exists():
                out_path = target_directory / f"{c_stem}_{counter}{c_ext}"
                counter += 1
            return out_path

        base = path.stem
        out_name = f"{base}_{target_lang}{ext}"
        out_path = target_directory / out_name
        counter = 1
        while out_path.exists():
            out_path = target_directory / f"{base}_{target_lang}_{counter}{ext}"
            counter += 1
        return out_path

    @classmethod
    def get_temp_path(cls, filename: str) -> Path:
        return TEMP_DIR / filename

    @classmethod
    def cleanup_working(cls, working_path: Optional[Path]):
        if working_path and working_path.exists():
            try:
                os.remove(working_path)
            except Exception as e:
                logger.warning(f"Failed to cleanup working file {working_path}: {e}")

document_storage = DocumentStorage()
