from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from hashlib import sha256
import re
import unicodedata


def normalized(value: str) -> str:
    value = unicodedata.normalize("NFKD", value.casefold())
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", " ", value).strip()


@dataclass(slots=True)
class Event:
    source: str
    source_id: str
    title: str
    start: datetime
    end: datetime
    venue: str
    address: str
    url: str
    category: str = "Culture"
    description: str = ""
    price: str = ""
    status: str = "CONFIRMED"

    @property
    def uid(self) -> str:
        key = f"{self.source}|{self.source_id}"
        return sha256(key.encode()).hexdigest()[:24] + "@cdmx-social-calendar"

    @property
    def dedupe_key(self) -> str:
        return "|".join((normalized(self.title), self.start.isoformat(), normalized(self.venue)))

    def to_dict(self) -> dict:
        data = asdict(self)
        data["start"] = self.start.isoformat()
        data["end"] = self.end.isoformat()
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "Event":
        data = dict(data)
        data["start"] = datetime.fromisoformat(data["start"])
        data["end"] = datetime.fromisoformat(data["end"])
        return cls(**data)

