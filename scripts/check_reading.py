"""Validate book references and daily reading logs before publishing."""

from __future__ import annotations

import json
import re
import sys
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1] / "content" / "reading"
FIELD = re.compile(r"^([a-z_]+):\s*(.*?)\s*$")


def fields(path: Path) -> dict[str, str]:
    lines = path.read_text(encoding="utf-8-sig").splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError("缺少 YAML 文章头")
    result: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            return result
        match = FIELD.match(line)
        if match:
            key, raw = match.groups()
            if raw.startswith('"'):
                result[key] = json.loads(raw)
            elif raw.startswith("'") and raw.endswith("'"):
                result[key] = raw[1:-1].replace("''", "'")
            else:
                result[key] = raw
    raise ValueError("文章头缺少结束的 ---")


def main() -> int:
    errors: list[str] = []
    books: dict[str, tuple[Path, bool]] = {}
    logs: list[tuple[Path, dict[str, str]]] = []

    for path in sorted(ROOT.rglob("*.md")):
        if path.name == "_index.md":
            continue
        try:
            data = fields(path)
        except (ValueError, json.JSONDecodeError) as exc:
            errors.append(f"{path}: {exc}")
            continue
        if path.is_relative_to(ROOT / "books"):
            book_id = data.get("book_id", "").strip()
            if not book_id:
                if data.get("draft", "").lower() == "true":
                    continue
                errors.append(f"{path}: 书籍缺少 book_id")
            elif book_id in books:
                errors.append(f"book_id 重复：{path} 与 {books[book_id][0]}")
            else:
                books[book_id] = (path, data.get("draft", "").lower() == "true")
        elif path.is_relative_to(ROOT / "logs"):
            logs.append((path, data))

    seen: dict[tuple[str, str], Path] = {}
    for path, data in logs:
        book_id = data.get("book_id", "").strip()
        if not book_id and data.get("draft", "").lower() == "true":
            continue
        day = data.get("date", "").strip()
        try:
            if not book_id:
                raise ValueError("阅读记录缺少 book_id")
            date.fromisoformat(day)
            minutes = int(data.get("reading_minutes", ""))
            pages = int(data.get("pages", "0"))
            if minutes < 0 or pages < 0:
                raise ValueError("阅读分钟数和页数不能为负数")
        except ValueError as exc:
            errors.append(f"{path}: {exc}")
            continue
        if book_id not in books:
            errors.append(f"{path}: 找不到 book_id={book_id} 对应的书籍页")
        elif data.get("draft", "").lower() != "true" and books[book_id][1]:
            errors.append(f"{path}: 正式阅读记录关联的书籍仍是草稿：{books[book_id][0]}")
        key = (day, book_id)
        if key in seen:
            errors.append(f"同一本书同一天有重复记录：{path} 与 {seen[key]}")
        else:
            seen[key] = path

    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print(f"阅读检查通过：{len(books)} 本书，{len(seen)} 条记录。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
