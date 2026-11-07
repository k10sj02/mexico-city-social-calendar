from __future__ import annotations

from datetime import datetime, timezone

from icalendar import Calendar, Event as IcsEvent

from .model import Event


def render(events: list[Event]) -> bytes:
    calendar = Calendar()
    calendar.add("prodid", "-//CDMX Social and Culture Calendar//EN")
    calendar.add("version", "2.0")
    calendar.add("calscale", "GREGORIAN")
    calendar.add("method", "PUBLISH")
    calendar.add("x-wr-calname", "Mexico City Social & Culture")
    calendar.add("x-wr-timezone", "America/Mexico_City")
    calendar.add("refresh-interval", "PT6H")
    calendar.add("x-published-ttl", "PT6H")
    now = datetime.now(timezone.utc)
    for item in sorted(events, key=lambda event: (event.start, event.title.casefold())):
        event = IcsEvent()
        event.add("uid", item.uid)
        event.add("dtstamp", now)
        event.add("dtstart", item.start)
        event.add("dtend", item.end)
        prefix = "🆓 " if item.price == "FREE" else ""
        event.add("summary", prefix + item.title)
        event.add("location", ", ".join(value for value in (item.venue, item.address) if value))
        details = [item.category]
        if item.price:
            details.append(f"Admission: {item.price}")
        if item.description:
            details.append(item.description)
        details.extend((f"Source: {item.source}", item.url))
        event.add("description", "\n\n".join(details))
        event.add("url", item.url)
        event.add("categories", [item.category])
        event.add("status", item.status)
        event.add("transp", "TRANSPARENT")
        calendar.add_component(event)
    return calendar.to_ical()

