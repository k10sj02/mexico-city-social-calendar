from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from icalendar import Calendar

from cdmx_social_calendar.build import deduplicate
from cdmx_social_calendar.ics import render
from cdmx_social_calendar.model import Event


TZ = ZoneInfo("America/Mexico_City")


def sample(source="source-a", source_id="1"):
    start = datetime(2026, 11, 20, 19, 0, tzinfo=TZ)
    return Event(source, source_id, "Poetry Night", start, start + timedelta(hours=2), "Venue", "CDMX", "https://example.com", "Literary")


def test_stable_uid():
    assert sample().uid == sample().uid
    assert sample(source_id="2").uid != sample().uid


def test_deduplicates_cross_source_listing():
    assert len(deduplicate([sample(), sample("source-b", "99")])) == 1


def test_event_uid_survives_metadata_changes():
    changed = sample()
    changed.title = "Poetry Night — updated"
    assert changed.uid == sample().uid


def test_valid_calendar_and_timezone():
    calendar = Calendar.from_ical(render([sample()]))
    assert calendar["X-WR-CALNAME"] == "Mexico City Social & Culture"
    event = calendar.walk("VEVENT")[0]
    assert event.decoded("DTSTART").tzinfo is not None

