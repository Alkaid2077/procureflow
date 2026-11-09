import fitz
import pytest

from procureflow.config import Settings
from procureflow.services.extractors import pdf_extractor, scan_review
from procureflow.services.extractors.ocr_engine import group_ocr_rows, ocr_engine
from tests.unit.test_chinese_scan_review import LABELS, VALUES, scan_pdf, words_for


@pytest.mark.asyncio
async def test_scan_suggestion_reaches_review_and_comparison(async_client, tmp_path, monkeypatch):
    rows = group_ocr_rows(words_for(LABELS, VALUES))
    monkeypatch.setattr(
        ocr_engine,
        "perform_ocr_page",
        lambda *_: {"text": "\n".join(row["text"] for row in rows), "rows": rows},
    )
    monkeypatch.setattr(
        scan_review,
        "read_visual_crop",
        lambda *_: scan_review.VisualReading(
            description="钢制支架",
            quantity="10",
            unit_price="28.50",
            total_price="285.00",
        ),
    )
    settings = Settings(
        scan_vision_base_url="http://localhost:1234/v1", scan_vision_model="test-only"
    )
    monkeypatch.setattr(pdf_extractor, "get_settings", lambda: settings)

    headers = {"X-API-Key": "procureflow_dev_api_key_12345"}
    rfq = await async_client.post(
        "/api/v1/rfqs",
        json={
            "title": "合成报价复核",
            "category": "五金",
            "reference_currency": "CNY",
            "line_items": [
                {"position": 1, "description": "钢制支架", "quantity": 10, "unit": "units"}
            ],
            "criteria": [
                {"name": "Price", "weight": 1.0, "criterion_type": "price", "is_mandatory": True}
            ],
        },
        headers=headers,
    )
    assert rfq.status_code == 201
    rfq_id = rfq.json()["id"]
    path = scan_pdf(tmp_path)
    with fitz.open(path) as document:
        assert not document[0].get_text()
    quotation = await async_client.post(
        "/api/v1/quotations/upload",
        data={"rfq_id": rfq_id, "supplier_name": "合成供应商"},
        files={"file": ("quote.pdf", path.read_bytes(), "application/pdf")},
        headers=headers,
    )
    assert quotation.status_code == 201
    route = f"/api/v1/quotations/{quotation.json()['id']}"
    extracted = await async_client.post(f"{route}/extract", headers=headers)
    assert extracted.status_code == 200
    response = await async_client.get(f"{route}/extractions/latest", headers=headers)
    assert response.status_code == 200
    [item] = response.json()["line_items"]
    assert float(item["unit_price"]) == 128.5
    assert item["has_discrepancy"]
    evidence = item["source_evidence"]
    assert evidence["page"] == 1
    assert evidence["scan_review"]["suggested"] == "28.50"
    assert evidence["scan_review"]["field"] == "unit_price"

    approval = await async_client.patch(
        f"{route}/status", json={"status": "approved"}, headers=headers
    )
    assert approval.status_code == 422
    corrected = await async_client.patch(
        f"{route}/line-items/{item['id']}",
        json={"unit_price": float(evidence["scan_review"]["suggested"])},
        headers=headers,
    )
    assert corrected.status_code == 200
    assert corrected.json()["human_corrected"]
    assert not corrected.json()["has_discrepancy"]
    approved = await async_client.patch(
        f"{route}/status", json={"status": "approved"}, headers=headers
    )
    assert approved.status_code == 200
    matrix = await async_client.get(f"/api/v1/rfqs/{rfq_id}/matrix", headers=headers)
    assert matrix.status_code == 200
    [row] = matrix.json()["required_line_items"]
    assert float(row["supplier_cells"][quotation.json()["id"]]["normalized_unit_price"]) == 28.5
