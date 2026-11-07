from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime, timedelta
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

import httpx
from bs4 import BeautifulSoup

from .model import Event

TZ = ZoneInfo("America/Mexico_City")
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; CDMXSocialCalendar/1.0; +https://github.com/k10sj02/mexico-city-social-calendar)"}


def _dt(value: str) -> datetime:
    value = value.strip().replace("a. m.", "AM").replace("p. m.", "PM")
    for fmt in ("%d/%m/%Y %I:%M:%S %p", "%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=TZ)
        except ValueError:
            pass
    raise ValueError(f"Unsupported date: {value}")


async def _get(client: httpx.AsyncClient, url: str) -> str:
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            response = await client.get(url, follow_redirects=True, timeout=35)
            response.raise_for_status()
            return response.text
        except (httpx.HTTPError, OSError) as exc:
            last_error = exc
            if attempt < 2:
                await asyncio.sleep(1.5 * (attempt + 1))
    assert last_error is not None
    raise last_error


async def fetch_unam(client: httpx.AsyncClient) -> list[Event]:
    categories = (
        "Arte-sonoro", "Artes-Visuales", "Conferencias-y-presentaciones",
        "Cursos-y-talleres", "Danza", "Especiales", "Libros", "Música", "Teatro",
    )
    urls = [f"https://www.cultura.unam.mx/actividades/{category}" for category in categories]
    pages = await asyncio.gather(*(_get(client, url) for url in urls), return_exceptions=True)
    events: list[Event] = []
    for url, page in zip(urls, pages):
        if isinstance(page, Exception):
            print(f"WARN Cultura UNAM failed: {url}: {page}")
            continue
        soup = BeautifulSoup(page, "html.parser")
        for card in soup.select('[itemtype="http://schema.org/Event"]'):
            link = card.select_one('[itemprop="url"]')
            name = card.select_one('[itemprop="name"]')
            start_el = card.select_one('[itemprop="startDate"]')
            if not (link and name and start_el and start_el.get("content")):
                continue
            try:
                start = _dt(start_el["content"])
                end_el = card.select_one('[itemprop="endDate"]')
                end = _dt(end_el["content"]) if end_el and end_el.get("content") else start + timedelta(hours=2)
            except ValueError:
                continue
            event_url = urljoin(url, link.get("href", ""))
            venue_el = card.select_one('[itemprop="location"] [itemprop="name"]')
            category_el = card.select_one(".event-cat")
            # UNAM uses start/end as the run of an exhibition or series. Treat the
            # opening/start as one calendar item instead of blocking every day.
            if end - start > timedelta(hours=8):
                end = start + timedelta(hours=2)
            events.append(Event(
                source="cultura-unam",
                source_id=event_url.rstrip("/").rsplit("/", 1)[-1],
                title=name.get("title") or name.get_text(" ", strip=True),
                start=start,
                end=max(end, start + timedelta(minutes=30)),
                venue=venue_el.get_text(" ", strip=True) if venue_el else "UNAM",
                address="Ciudad de México, CDMX, México",
                url=event_url,
                category=category_el.get_text(" ", strip=True) if category_el else "Cultura UNAM",
                description="Event details and admission information are available at the official Cultura UNAM listing.",
            ))
    return events


def _event_jsonld(html: str) -> dict | None:
    soup = BeautifulSoup(html, "html.parser")
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            data = json.loads(script.string or "")
        except (json.JSONDecodeError, TypeError):
            continue
        values = data if isinstance(data, list) else [data]
        for value in values:
            if isinstance(value, dict) and value.get("@type") == "Event":
                return value
    return None


async def fetch_tianguis(client: httpx.AsyncClient) -> list[Event]:
    base = "https://www.tianguis.net"
    html = await _get(client, f"{base}/calendario")
    soup = BeautifulSoup(html, "html.parser")
    links = sorted({urljoin(base, a["href"]) for a in soup.select('a[href^="/cartelera/"]')})
    semaphore = asyncio.Semaphore(10)

    async def fetch_one(url: str) -> Event | None:
        async with semaphore:
            try:
                data = _event_jsonld(await _get(client, url))
            except Exception as exc:
                print(f"WARN Tianguis detail failed: {url}: {exc}")
                return None
        if not data:
            return None
        location = data.get("location") or {}
        address = location.get("address") or {}
        if isinstance(address, dict):
            address = address.get("streetAddress", "")
        offers = data.get("offers") or {}
        price = "FREE" if str(offers.get("price", "")).strip() in {"0", "0.0"} else ""
        try:
            start = _dt(data["startDate"])
            end = _dt(data.get("endDate", data["startDate"]))
        except (KeyError, ValueError):
            return None
        # Some listings use 23:59 as an unknown closing time; cap calendar blocking.
        if end - start > timedelta(hours=6):
            end = start + timedelta(hours=2)
        source_id = url.rstrip("/").rsplit("/", 1)[-1]
        return Event(
            source="tianguis-cdmx",
            source_id=source_id,
            title=str(data.get("name", "")).strip(),
            start=start,
            end=max(end, start + timedelta(minutes=30)),
            venue=str(location.get("name", "CDMX venue")),
            address=(str(address).strip() + ", Ciudad de México, CDMX, México").strip(", "),
            url=url,
            category=_tianguis_category(html, source_id),
            description=str(data.get("description", "")).strip(),
            price=price,
        )

    results = await asyncio.gather(*(fetch_one(url) for url in links))
    return [event for event in results if event and event.title]


def _tianguis_category(index_html: str, source_id: str) -> str:
    soup = BeautifulSoup(index_html, "html.parser")
    link = soup.select_one(f'a[href="/cartelera/{source_id}"]')
    if not link:
        return "Community event"
    blocks = link.select("div")
    return blocks[2].get_text(" ", strip=True) if len(blocks) > 2 else "Community event"


async def fetch_cdmx365(client: httpx.AsyncClient) -> list[Event]:
    base = "https://www.cdmx365.com"
    pages: list[str] = []
    for number in range(1, 8):
        url = f"{base}/es/eventos" + (f"?page={number}" if number > 1 else "")
        try:
            html = await _get(client, url)
        except Exception as exc:
            print(f"WARN CDMX365 page failed: {url}: {exc}")
            break
        pages.append(html)
        if f"?page={number + 1}" not in html:
            break

    allowed = {
        "Antros y DJs", "Conciertos y Festivales", "Música en Vivo", "Teatro", "Danza",
        "Comida y Bebidas", "Experiencias", "Conferencias", "Exposiciones de Arte",
        "Clases y Talleres", "Meetups", "Mercados y Bazares", "LGBTQ+", "Literario",
        "Comedia", "Networking", "Fiestas",
    }
    events: list[Event] = []
    seen: set[str] = set()
    for html in pages:
        soup = BeautifulSoup(html, "html.parser")
        for group in soup.select(".date-group[data-date]"):
            date = group.get("data-date", "")
            for card in group.select(".listing-row"):
                link = card.select_one("a.listing-title-link")
                title_el = card.select_one(".listing-title")
                category_el = card.select_one(".list-tag")
                if not (link and title_el and category_el):
                    continue
                category = category_el.get_text(" ", strip=True)
                if category not in allowed:
                    continue
                url = urljoin(base, link.get("href", ""))
                if url in seen:
                    continue
                seen.add(url)
                time_el = card.select_one(".listing-event-meta .em-item")
                time_text = time_el.get_text(" ", strip=True) if time_el else ""
                match = re.search(r"(\d{1,2}:\d{2}\s*[AP]M)", time_text, re.I)
                if not match:
                    continue
                try:
                    start = datetime.strptime(f"{date} {match.group(1).upper()}", "%Y-%m-%d %I:%M %p").replace(tzinfo=TZ)
                except ValueError:
                    continue
                venue_el = card.select_one(".venue-link")
                neighborhood = card.select_one(".listing-neighborhood")
                description = card.select_one(".listing-desc")
                meta = card.select(".listing-event-meta .em-item")
                price = meta[1].get_text(" ", strip=True) if len(meta) > 1 else ""
                events.append(Event(
                    source="cdmx365",
                    source_id=url.rstrip("/").rsplit("/", 1)[-1],
                    title=title_el.get_text(" ", strip=True),
                    start=start,
                    end=start + timedelta(hours=2),
                    venue=venue_el.get_text(" ", strip=True) if venue_el else "CDMX venue",
                    address=((neighborhood.get_text(" ", strip=True) + ", ") if neighborhood else "") + "Ciudad de México, CDMX, México",
                    url=url,
                    category=category,
                    description=description.get_text(" ", strip=True) if description else "",
                    price=price,
                ))
    return events


async def fetch_all() -> tuple[list[Event], dict[str, int]]:
    async with httpx.AsyncClient(headers=HEADERS) as client:
        results = await asyncio.gather(
            fetch_tianguis(client), fetch_unam(client), fetch_cdmx365(client),
            return_exceptions=True,
        )
    names = ("Tianguis / Cartelera CDMX", "Cultura UNAM", "CDMX365")
    events: list[Event] = []
    counts: dict[str, int] = {}
    for name, result in zip(names, results):
        if isinstance(result, Exception):
            print(f"ERROR source failed: {name}: {result}")
            counts[name] = 0
        else:
            counts[name] = len(result)
            events.extend(result)
    return events, counts
