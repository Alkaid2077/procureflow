import json
from decimal import Decimal
from pathlib import Path

import fitz
import httpx
import pytest

from procureflow.config import Settings
from procureflow.scripts.create_scan_demo import create_sample
from procureflow.services.extractors import pdf_extractor, scan_review
from procureflow.services.extractors.chinese_quote import extract_chinese_rows
from procureflow.services.extractors.ocr_engine import group_ocr_rows, ocr_engine
from procureflow.services.extractors.pdf_extractor import PDFExtractor

LABELS = ("品名", "数量", "单价", "金额")
VALUES = ("钢制支架", "10", "128.50", "285.00")


def words_for(*lines):
    return [
        (20.0 + x * 100, 25.0 + y * 35, 60.0 + x * 100, 37.0 + y * 35, value)
        for y, line in enumerate(lines)
        for x, value in enumerate(line)
    ]


def scan_pdf(tmp_path: Path) -> Path:
    path = tmp_path / "quotation.pdf"
    create_sample(path)
    return path


def test_ocr_rows_and_cpu_extractor_ignore_totals():
    rows = group_ocr_rows(words_for(LABELS, VALUES, ("合计", "10", "", "285.00")))
    [item] = extract_chinese_rows(rows, 1, "CNY")
    assert item.quantity == Decimal("10")
    assert item.unit_price == Decimal("128.50")
    assert item.total_price == Decimal("285.00")
    assert item.evidence.page == 1
    assert item.evidence.bbox == [20, 60, 360, 72]
    assert extract_chinese_rows(rows[1:], 1, "CNY") == []


@pytest.mark.parametrize(
    ("mode", "expected"),
    [
        ("disabled", "manual"),
        ("timeout", "unavailable"),
        ("conflict", "conflict"),
        ("success", "suggestion"),
    ],
)
def test_scan_pdf_review_is_bounded_and_never_mutates_amounts(
    tmp_path, monkeypatch, mode, expected
):
    path = scan_pdf(tmp_path)
    with fitz.open(path) as scan:
        assert scan[0].get_text() == ""

    rows = group_ocr_rows(words_for(LABELS, VALUES))
    monkeypatch.setattr(
        ocr_engine,
        "perform_ocr_page",
        lambda *_: {"text": "\n".join(row["text"] for row in rows), "rows": rows},
    )
    settings = Settings(
        scan_vision_base_url="" if mode == "disabled" else "http://localhost:1234/v1",
        scan_vision_model="local-vision-test",
    )
    monkeypatch.setattr(pdf_extractor, "get_settings", lambda: settings)

    calls = []

    def read_crop(image: bytes, settings: Settings):
        calls.append((image, settings.scan_vision_model))
        pixmap = fitz.Pixmap(image)
        assert pixmap.width < 840
        assert pixmap.height < 100
        if mode == "timeout":
            raise httpx.ReadTimeout("unavailable")
        return scan_review.VisualReading(
            description="另一商品" if mode == "conflict" else "钢制支架",
            quantity=Decimal("10"),
            unit_price=Decimal("28.50"),
            total_price=Decimal("285.00"),
        )

    monkeypatch.setattr(scan_review, "read_visual_crop", read_crop)
    [item] = PDFExtractor().extract(path, reference_currency="CNY").line_items

    assert len(calls) == (0 if mode == "disabled" else 1)
    assert item.unit_price == Decimal("128.50")
    assert item.evidence.scan_review is not None
    assert item.evidence.scan_review.outcome == expected
    assert item.evidence.scan_review.reason == "amount_mismatch"
    if mode == "success":
        assert item.evidence.scan_review.field == "unit_price"
        assert item.evidence.scan_review.suggested == "28.50"


def test_visual_transport_sends_only_image_and_expected_parameters(monkeypatch):
    def post(url, *, headers, json: dict, timeout):
        assert url == "https://example.invalid/v1/chat/completions"
        assert not headers
        assert timeout == 15
        assert json["model"] == "vision"
        parts = json["messages"][0]["content"]
        assert parts[1]["image_url"]["url"] == "data:image/png;base64,cG5n"
        return httpx.Response(
            200,
            request=httpx.Request("POST", url),
            json={"choices": [{"message": {"content": response}}]},
        )

    response = json.dumps(
        {
            "description": "钢制支架",
            "quantity": 10,
            "unit_price": "28.50",
            "total_price": 285,
        }
    )
    monkeypatch.setattr(scan_review.httpx, "post", post)
    settings = Settings(
        scan_vision_base_url="https://example.invalid/v1", scan_vision_model="vision"
    )
    assert scan_review.read_visual_crop(b"png", settings).unit_price == Decimal("28.50")


def test_ocr_failure_does_not_fabricate_quote(tmp_path, monkeypatch):
    monkeypatch.setattr(ocr_engine, "tesseract_bin", None)

    def unavailable(*args, **kwargs):
        raise RuntimeError("no language data installed")

    monkeypatch.setattr(fitz.Page, "get_textpage_ocr", unavailable)
    result = PDFExtractor().extract(scan_pdf(tmp_path))
    assert not result.line_items
    assert any("No readable quotation text" in warning for warning in result.validation_warnings)
