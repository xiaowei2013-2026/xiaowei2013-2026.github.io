"""Check daily quotes for repeated text or dates without extra dependencies."""

from __future__ import annotations

import json
import re
import sys
import unicodedata
from pathlib import Path


QUOTE_ROOT = Path(__file__).resolve().parents[1] / "content" / "quotes"
FIELD_PATTERN = re.compile(r"^(quote|date|draft):\s*(.*?)\s*$")


def front_matter(path: Path) -> dict[str, str]:
    lines = path.read_text(encoding="utf-8-sig").splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError("缺少 YAML 文章头")
    values: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            return values
        match = FIELD_PATTERN.match(line)
        if match:
            key, raw = match.groups()
            if raw.startswith('"'):
                values[key] = json.loads(raw)
            elif raw.startswith("'") and raw.endswith("'"):
                values[key] = raw[1:-1].replace("''", "'")
            else:
                values[key] = raw
    raise ValueError("文章头缺少结束的 ---")


def normalized(text: str) -> str:
    return "".join(
        char for char in unicodedata.normalize("NFKC", text).casefold() if char.isalnum()
    )


def main() -> int:
    seen_quotes: dict[str, Path] = {}
    seen_dates: dict[str, Path] = {}
    errors: list[str] = []
    checked = 0
    for path in sorted(QUOTE_ROOT.rglob("*.md")):
        if path.name == "_index.md":
            continue
        try:
            values = front_matter(path)
            quote = values.get("quote", "").strip()
            day = values.get("date", "").strip()
            if not quote and values.get("draft", "").lower() == "true":
                continue
            if not quote or not day:
                raise ValueError("quote 和 date 都必须填写")
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day):
                raise ValueError("date 必须是 YYYY-MM-DD")
            key = normalized(quote)
            if not key:
                raise ValueError("quote 不能只有标点或空格")
        except (ValueError, json.JSONDecodeError) as exc:
            errors.append(f"{path}: {exc}")
            continue
        checked += 1
        if key in seen_quotes:
            errors.append(f"金句重复：{path} 与 {seen_quotes[key]}")
        else:
            seen_quotes[key] = path
        if day in seen_dates:
            errors.append(f"日期重复：{path} 与 {seen_dates[day]}")
        else:
            seen_dates[day] = path

    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print(f"金句检查通过：{checked} 条，未发现重复原文或日期。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
