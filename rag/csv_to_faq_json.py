"""
rag/csv_to_faq_json.py
FAQ登録用CSVをingest_json対応のネスト形式JSONに変換する
"""

import csv
import json
import sys
from pathlib import Path


def convert(csv_path: str | Path, json_path: str | Path) -> None:
    csv_path = Path(csv_path)
    json_path = Path(json_path)

    rows = []
    with open(csv_path, encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        next(reader)  # ヘッダー行をスキップ
        for row in reader:
            if len(row) < 3:
                continue
            rows.append(row)

    # 空カテゴリ行（継続行）を直前の行の回答に結合する
    merged: list[tuple[str, str, str]] = []
    for row in rows:
        category = row[0].strip()
        question = row[1].strip() if len(row) > 1 else ""
        answer = row[2].strip() if len(row) > 2 else ""

        if not category and not question and merged:
            prev_cat, prev_q, prev_a = merged[-1]
            merged[-1] = (prev_cat, prev_q, prev_a + "\n" + answer)
        else:
            if category or question:
                merged.append((category, question, answer))

    # カテゴリ別にグループ化（出現順を保持）
    category_order: list[str] = []
    category_items: dict[str, list[dict]] = {}
    for category, question, answer in merged:
        if category not in category_items:
            category_order.append(category)
            category_items[category] = []
        category_items[category].append({"question": question, "answer": answer})

    result = [
        {"category": cat, "items": category_items[cat]}
        for cat in category_order
    ]

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    total = sum(len(c["items"]) for c in result)
    print(f"変換完了: {len(result)} カテゴリ, {total} 件 → {json_path}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("使い方: python rag/csv_to_faq_json.py <入力CSV> <出力JSON>")
        sys.exit(1)
    convert(sys.argv[1], sys.argv[2])
