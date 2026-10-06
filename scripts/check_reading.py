"""Validate manually maintained reading dates and book/article names."""

from __future__ import annotations

import json
import re
import sys
from datetime import date
from pathlib import Path


RECORDS = Path(__file__).resolve().parents[1] / "content" / "reading" / "reading-records.json"


def unique_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"重复日期或字段：{key}")
        result[key] = value
    return result


def validate_records(records: object) -> list[str]:
    if not isinstance(records, dict):
        return ["最外层必须是 JSON 对象：日期对应书名／文章名列表"]
    errors: list[str] = []
    for day, names in records.items():
        try:
            if not isinstance(day, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day):
                raise ValueError("日期必须是 YYYY-MM-DD")
            date.fromisoformat(day)
        except ValueError as exc:
            errors.append(f"{day}: {exc}")
        if not isinstance(names, list):
            errors.append(f"{day}: 内容必须是书名／文章名列表")
            continue
        seen: set[str] = set()
        for name in names:
            if not isinstance(name, str) or not name.strip():
                errors.append(f"{day}: 每个书名／文章名都必须是非空字符串")
            elif name != name.strip():
                errors.append(f"{day}: 名称前后不能有空格：{name!r}")
            elif name in seen:
                errors.append(f"{day}: 名称重复：{name}")
            else:
                seen.add(name)
    return errors


def main() -> int:
    try:
        records = json.loads(RECORDS.read_text(encoding="utf-8-sig"), object_pairs_hook=unique_keys)
    except (OSError, ValueError) as exc:
        print(f"阅读数据无法读取：{exc}", file=sys.stderr)
        return 1
    errors = validate_records(records)
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print(f"阅读检查通过：{len(records)} 个日期，{sum(len(names) for names in records.values())} 条阅读记录。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
