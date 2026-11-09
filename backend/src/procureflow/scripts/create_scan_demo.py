"""Generate a synthetic image-only Chinese quote for the local demo."""

import argparse
from decimal import Decimal
from pathlib import Path

import fitz

from procureflow.services.extractors.pdf_extractor import PDFExtractor

LABELS = ("品名", "数量", "单价", "金额")
VALUES = ("钢制支架", "10", "28.50", "285.00")


def create_sample(path: Path) -> None:
    with fitz.open() as source:
        page = source.new_page(width=420, height=160)
        for y, row in enumerate((LABELS, VALUES)):
            for x, value in enumerate(row):
                page.insert_text(
                    (20 + x * 100, 37 + y * 35), value, fontname="china-s", fontsize=12
                )
        image = page.get_pixmap(matrix=fitz.Matrix(2, 2)).tobytes("png")

    with fitz.open() as output:
        page = output.new_page(width=420, height=160)
        page.insert_image(page.rect, stream=image)
        output.save(path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, help="Path for the synthetic PDF")
    parser.add_argument("--check-ocr", action="store_true", help="Run the configured OCR pipeline")
    args = parser.parse_args()
    create_sample(args.output)
    print(f"Created {args.output}")
    if args.check_ocr:
        result = PDFExtractor().extract(args.output, reference_currency="CNY")
        rows = [
            (item.description_raw, item.quantity, item.unit_price, item.total_price)
            for item in result.line_items
        ]
        print(rows)
        if rows != [("钢制支架", Decimal("10"), Decimal("28.50"), Decimal("285.00"))]:
            raise SystemExit("Synthetic OCR check did not match the expected row.")


if __name__ == "__main__":
    main()
