# Mexico City Social & Culture Calendar

An automatically refreshed, subscribable calendar of social and cultural events in Mexico City.

It combines selected listings from:

- [Tianguis / Cartelera CDMX](https://www.tianguis.net/calendario): community events, public cultural programming, workshops, literature, concerts, festivals and free activities
- [Cultura UNAM](https://www.cultura.unam.mx/): music, theatre, dance, talks, books, visual and sound art, and special events
- [CDMX365](https://www.cdmx365.com/es/eventos): nightlife, DJs, concerts, live music, performing arts, queer events, markets, meetups and other social listings

Movie screenings are deliberately excluded because they belong in the separate Mexico City cinema calendar.

## Subscribe

Landing page: <https://k10sj02.github.io/mexico-city-social-calendar/>

Calendar feed:

```text
https://k10sj02.github.io/mexico-city-social-calendar/mexico-city-social-culture.ics
```

## How it works

GitHub Actions rebuilds the feed every six hours. Events use stable source-derived UIDs, `America/Mexico_City` timezone data, exact source links, venue details, category metadata, cross-source deduplication, free-event labels, and cancellation records when a previously published future event disappears.

The build refuses to replace the feed when every source returns zero events.

## Run locally

```bash
python -m venv .venv
.venv/bin/pip install -e '.[test]'
.venv/bin/pytest -q
.venv/bin/python -m cdmx_social_calendar.build
```

