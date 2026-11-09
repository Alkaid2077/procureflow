"""Extract the common four-column Chinese quotation layout from OCR geometry."""

import re
import unicodedata
from bisect import bisect_right
from decimal import Decimal
from typing import Any

from procureflow.services.extractors.base import RawLineItem, SourceEvidence

HEADERS = (
    {"品名", "商品名称", "产品名称", "物料名称", "品名规格"},
    {"数量", "采购数量", "报价数量"},
    {"单价", "含税单价", "未税单价"},
    {"金额", "合计金额", "小计", "含税金额", "未税金额"},
)
TOTALS = ("合计", "小计", "总计", "备注", "税额", "运费")


def clean(text: str) -> str:
    return "".join(unicodedata.normalize("NFKC", text).split())


def read_amount(text: str) -> Decimal | None:
    value = clean(text).removeprefix("¥").removeprefix("￥").removesuffix("元")
    if not re.fullmatch(r"(?:\d{1,12}|\d{1,3}(?:,\d{3}){1,3})(?:\.\d{1,4})?", value):
        return None
    return Decimal(value.replace(",", ""))


def extract_chinese_rows(rows: list[dict[str, Any]], page: int, currency: str) -> list[RawLineItem]:
    """Parse only recognized headers. Leave unknown layouts to the existing extractor."""
    items: list[RawLineItem] = []
    boundaries: list[float] = []
    for index, row in enumerate(rows):
        words = row.get("words", [])
        if not words:
            continue
        centers = [
            [(x0 + x1) / 2 for x0, _, x1, _, text in words if clean(text) in aliases]
            for aliases in HEADERS
        ]
        if all(len(values) == 1 for values in centers):
            anchors = [values[0] for values in centers]
            if anchors == sorted(set(anchors)):
                boundaries = [
                    (left + right) / 2 for left, right in zip(anchors, anchors[1:], strict=False)
                ]
                continue
        if not boundaries:
            continue
        if clean(row["text"]).startswith(TOTALS):
            break

        cells: list[list[str]] = [[], [], [], []]
        for x0, _, x1, _, word in words:
            cells[bisect_right(boundaries, (x0 + x1) / 2)].append(word)
        description = " ".join(cells[0]).strip()
        amounts = [read_amount("".join(cell)) for cell in cells[1:]]
        if not description or sum(value is not None for value in amounts) < 2:
            continue

        # The existing row schema requires decimals. A zero placeholder is flagged for review.
        quantity, unit_price, total_price = [
            value if value is not None else Decimal("0") for value in amounts
        ]
        items.append(
            RawLineItem(
                description_raw=description,
                quantity=quantity,
                unit_price=unit_price,
                total_price=total_price,
                currency=currency,
                confidence=Decimal("0.60"),
                evidence=SourceEvidence(
                    evidence_id=f"p{page}_ocr_row{index}",
                    type="ocr_pdf",
                    page=page,
                    bbox=row["bbox"],
                    text_snippet=row["text"][:300],
                ),
            )
        )
    return items
