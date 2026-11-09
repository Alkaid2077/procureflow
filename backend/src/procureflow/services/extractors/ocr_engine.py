import csv
import io
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import fitz  # PyMuPDF
import structlog

from procureflow.config import get_settings

logger = structlog.get_logger(__name__)
settings = get_settings()


def group_ocr_rows(words: list[tuple[float, float, float, float, str]]) -> list[dict]:
    """Group OCR words into visual rows across table columns."""
    rows: list[list[tuple[float, float, float, float, str]]] = []
    for word in sorted(words, key=lambda entry: (entry[1] + entry[3]) / 2):
        if rows:
            first = rows[-1][0]
            center_delta = abs((word[1] + word[3] - first[1] - first[3]) / 2)
            if center_delta <= min(word[3] - word[1], first[3] - first[1]) * 0.45:
                rows[-1].append(word)
                continue
        rows.append([word])
    return [
        {
            "text": " ".join(word[4] for word in sorted(row, key=lambda word: word[0])),
            "words": sorted(row, key=lambda word: word[0]),
            "bbox": [
                min(word[0] for word in row),
                min(word[1] for word in row),
                max(word[2] for word in row),
                max(word[3] for word in row),
            ],
        }
        for row in rows
    ]


class OCREngine:
    """Read raster PDFs with PyMuPDF OCR or a Tesseract CLI fallback."""

    def __init__(self) -> None:
        self.tesseract_bin = shutil.which("tesseract")

    def should_run_ocr(self, page: fitz.Page, min_chars: int | None = None) -> bool:
        if not settings.ocr_enabled:
            return False

        threshold = min_chars if min_chars is not None else settings.min_native_text_chars
        native_text = (page.get_text() or "").strip()
        return len(native_text) < threshold and (not native_text or bool(page.get_images()))

    def perform_ocr_page(self, page: fitz.Page, page_num: int) -> dict[str, Any]:
        language = settings.ocr_language
        try:
            textpage = page.get_textpage_ocr(flags=0, language=language, dpi=150, full=True)
            text = textpage.extractText()
            if text.strip():
                rows = group_ocr_rows([tuple(word[:5]) for word in textpage.extractWORDS()])
                return {
                    "text": text,
                    "rows": rows,
                    "ocr_confidence": 0.90,
                    "page_num": page_num,
                    "method": "pymupdf_ocr",
                }
        except Exception as error:
            logger.debug(
                "PyMuPDF OCR unavailable, trying Tesseract", error_type=type(error).__name__
            )

        if self.tesseract_bin:
            try:
                pixmap = page.get_pixmap(dpi=150)
                with tempfile.TemporaryDirectory() as directory:
                    image_path = Path(directory) / "page.png"
                    pixmap.save(image_path)
                    result = subprocess.run(
                        [self.tesseract_bin, str(image_path), "stdout", "-l", language, "tsv"],
                        capture_output=True,
                        encoding="utf-8",
                        errors="replace",
                        timeout=30,
                    )
                if result.returncode == 0:
                    words = []
                    scale_x, scale_y = (
                        page.rect.width / pixmap.width,
                        page.rect.height / pixmap.height,
                    )
                    for entry in csv.DictReader(io.StringIO(result.stdout), delimiter="\t"):
                        word = (entry.get("text") or "").strip()
                        if not word:
                            continue
                        left, top, width, height = (
                            int(entry[key]) for key in ("left", "top", "width", "height")
                        )
                        words.append(
                            (
                                left * scale_x,
                                top * scale_y,
                                (left + width) * scale_x,
                                (top + height) * scale_y,
                                word,
                            )
                        )
                    rows = group_ocr_rows(words)
                    if rows:
                        return {
                            "text": "\n".join(row["text"] for row in rows),
                            "rows": rows,
                            "ocr_confidence": 0.88,
                            "page_num": page_num,
                            "method": "tesseract_cli",
                        }
            except (OSError, ValueError, KeyError, subprocess.TimeoutExpired) as error:
                logger.warning("Tesseract OCR failed", error_type=type(error).__name__)

        text = page.get_text() or ""
        return {
            "text": text,
            "rows": [],
            "ocr_confidence": 0.50 if text.strip() else 0.0,
            "page_num": page_num,
            "method": "native_fallback",
        }


ocr_engine = OCREngine()
