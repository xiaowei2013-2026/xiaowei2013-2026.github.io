"""Export anonymous daily review totals from a local Anki collection."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import tempfile
from collections import defaultdict
from datetime import datetime
from pathlib import Path


def arguments() -> argparse.Namespace:
    default = Path(os.environ.get("APPDATA", "")) / "Anki2" / "账户 1" / "collection.anki2"
    parser = argparse.ArgumentParser()
    parser.add_argument("--collection", type=Path, default=default)
    parser.add_argument("--deck-prefix", default="英语")
    parser.add_argument("--output", type=Path, default=Path(__file__).parents[1] / "data" / "anki_stats.json")
    return parser.parse_args()


def snapshot(source: Path) -> Path:
    folder = Path(tempfile.mkdtemp(prefix="anki-stats-"))
    target = folder / "collection.anki2"
    shutil.copy2(source, target)
    for suffix in ("-wal", "-shm"):
        companion = Path(f"{source}{suffix}")
        if companion.exists():
            shutil.copy2(companion, Path(f"{target}{suffix}"))
    return target


def main() -> None:
    args = arguments()
    if not args.collection.exists():
        raise SystemExit(f"找不到 Anki 数据库：{args.collection}")
    copy = snapshot(args.collection)
    db = sqlite3.connect(copy)
    db.create_collation("unicase", lambda a, b: (a.casefold() > b.casefold()) - (a.casefold() < b.casefold()))
    deck_ids = [row[0] for row in db.execute("select id from decks where name = ? or name like ?", (args.deck_prefix, f"{args.deck_prefix}\x1f%"))]
    if not deck_ids:
        raise SystemExit(f"没有找到牌组：{args.deck_prefix}")
    marks = ",".join("?" for _ in deck_ids)
    rows = db.execute(
        f"""select r.id, r.cid, r.time,
        case when r.id=(select min(r2.id) from revlog r2 where r2.cid=r.cid) then 1 else 0 end
        from revlog r join cards c on c.id=r.cid where c.did in ({marks}) order by r.id""",
        deck_ids,
    )
    daily: dict[str, dict] = defaultdict(lambda: {"reviews": 0, "new_cards": 0, "minutes": 0, "_cards": set()})
    for review_id, card_id, milliseconds, first in rows:
        day = datetime.fromtimestamp(review_id / 1000).astimezone().strftime("%Y-%m-%d")
        item = daily[day]
        item["reviews"] += 1
        item["new_cards"] += first
        item["minutes"] += min(milliseconds, 60_000) / 60_000
        item["_cards"].add(card_id)
    result = {}
    for day, item in sorted(daily.items()):
        result[day] = {
            "reviews": item["reviews"],
            "unique_cards": len(item["_cards"]),
            "new_cards": item["new_cards"],
            "minutes": round(item["minutes"]),
        }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"已导出 {len(result)} 天的匿名统计：{args.output}")


if __name__ == "__main__":
    main()
