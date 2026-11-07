from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from .ics import render
from .model import Event
from .sources import fetch_all

ROOT = Path(__file__).resolve().parents[2]
STATE = ROOT / "data" / "state.json"
OUTPUT = ROOT / "public" / "mexico-city-social-culture.ics"
STATUS = ROOT / "public" / "status.json"
TZ = ZoneInfo("America/Mexico_City")


def deduplicate(events: list[Event]) -> list[Event]:
    chosen: dict[str, Event] = {}
    # Prefer records with more complete descriptions and addresses.
    for event in events:
        existing = chosen.get(event.dedupe_key)
        score = len(event.description) + len(event.address) + (20 if event.price else 0)
        old_score = len(existing.description) + len(existing.address) + (20 if existing.price else 0) if existing else -1
        if score > old_score:
            chosen[event.dedupe_key] = event
    return list(chosen.values())


def load_previous() -> list[Event]:
    if not STATE.exists():
        return []
    try:
        return [Event.from_dict(value) for value in json.loads(STATE.read_text())["events"]]
    except (KeyError, ValueError, TypeError, json.JSONDecodeError):
        return []


def apply_cancellations(current: list[Event], previous: list[Event], now: datetime) -> list[Event]:
    current_uids = {event.uid for event in current}
    cancelled: list[Event] = []
    for event in previous:
        if (
            event.category.casefold() != "cine"
            and event.uid not in current_uids
            and now <= event.start <= now + timedelta(days=45)
        ):
            event.status = "CANCELLED"
            cancelled.append(event)
    return current + cancelled


async def run() -> None:
    now = datetime.now(TZ)
    raw, source_counts = await fetch_all()
    if not raw:
        raise RuntimeError("All event sources returned zero events; refusing to replace the feed")
    current = deduplicate([
        event for event in raw
        if event.end >= now - timedelta(hours=3)
        and event.category.casefold() != "cine"
    ])
    previous = load_previous()
    published = apply_cancellations(current, previous, now)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_bytes(render(published))
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps({"updated_at": now.isoformat(), "events": [event.to_dict() for event in current]}, ensure_ascii=False, indent=2) + "\n")
    STATUS.write_text(json.dumps({
        "updated_at": now.isoformat(),
        "event_count": len(current),
        "cancelled_count": len(published) - len(current),
        "source_counts": source_counts,
    }, ensure_ascii=False, indent=2) + "\n")
    print(f"Published {len(current)} current events ({source_counts})")


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()

