# GeoTrace 0.1.4

Visual discovery: thumbnails from public provider metadata, visible author/license attribution, and a native OpenStreetMap street map with acquisition footprints and source-coordinate markers. The original offline coordinate map remains available. Thumbnails are not evidence of capture date or verified location; the basemap is current cartography, not historical footage.

Validation: 88 automated regression cases plus real Windows mouse/keyboard automation over seven tabs, live retrieval, archive reopening, native export dialogs, cancellation and restart. The earlier audit is recorded in [AUDIT.md](AUDIT.md); new visual behavior and limits are documented in [VISUALS.md](VISUALS.md). Real screenshots and source records stay in ignored `private/visual-audit/` and `private/audit/`.

Automatic field synchronization: leaving the location field resolves its coordinates; multiple matching places require selection. Editing coordinates preserves the exact point, resolves its label and detects its IANA timezone offline with tzfpy. A single unambiguous timezone is filled automatically; at boundaries or when unresolved, disable automatic timezone and enter a valid IANA zone. Dates are local times without embedded offsets and accept ISO or `DD/MM/YYYY HH:MM`. Editing the start moves the end by the previous duration; an invalid or reversed end is blocked. Sources and media use checkboxes and incompatible selections are rejected. Geographic responses for earlier field values cannot overwrite newer input. Reverse lookup failure retains the coordinate label and exact point. Timezone boundary data is approximate and may differ for historical jurisdiction changes; manual timezone remains available.

**Windows:** double-click `Avvia GeoTrace.cmd` in the project folder after building. Source checkout: run `powershell -ExecutionPolicy Bypass -File .\Build-Windows.ps1` to install dependencies, test and create the portable application. Keep the entire `dist/GeoTrace` directory together. No Python installation is needed to run the completed portable build.

**Search behavior:** location text changes are geocoded before search; explicitly editing coordinates uses the entered coordinates and reverse geocodes the place label. Catalogs may return no acquisitions for a short nighttime interval. Inspect **Source coverage** for actual results, failures and limits. **Public search links** opens YouTube, Commons, Google News and Flickr using the location label, keywords and date; these are external searches, not automatically retrieved evidence.

**Troubleshooting:** unexpected application exceptions are displayed and logged at `%LOCALAPPDATA%/GeoTrace/error.log`. Send the error text when reporting a failure. Wikimedia may respond with a provider-side busy error, shown as RATE_LIMITED; try later. No media availability is implied by an empty or failed search.

Windows desktop application for discovering public geo-temporal media metadata. The supplied workspace was empty; there was no Aerial & Satellite Archive Finder repository to preserve, migrate, or branch.

## Run

Open `dist/GeoTrace/GeoTrace.exe`, keeping the entire GeoTrace directory together. Alternatively:

```powershell
python -m pip install -e '.[test,build]'
python -m geotrace.app
python -m geotrace.cli --export private/reports
python -m pytest -q
python -m PyInstaller --noconfirm --windowed --name GeoTrace --collect-data tzdata launch.py
```

Desktop and CLI archives default to `%LOCALAPPDATA%/GeoTrace/archive.sqlite`. Use CLI `--archive private/archive.sqlite` for a separate archive. No credentials, paid APIs, models or private camera discovery are used.

## Implemented

- Four real, concurrent API adapters: Copernicus Sentinel-2 L2A STAC, Element84 Earth Search STAC, NASA CMR HLSL30, Wikimedia Commons geosearch.
- Coordinate/radius/date/time zone validation, UTC conversion, ambiguous/nonexistent local time rejection, dateline and polar bounding boxes, radius filtering for geotagged Commons records.
- Automatic Nominatim forward/reverse lookup on field completion, with place selection, cooldown and exact-coordinate preservation.
- SQLite investigation archive, durable provider checkpoints, cancellation, bounded retry/backoff, timeout handling, CLI repeat-and-merge via `--resume ID`.
- Searchable results table, original record inspector, offline coordinate map centered on the search radius with STAC polygons, zoom/pan and double-click record selection, timezone-converted discrete timestamp timeline and readable coverage matrix.
- Lazy source thumbnails in the gallery, compact mode via **Mostra anteprime**, explicit missing/error states, author/license credit and **Apri originale**. NASA uses published CMR browse links when available.
- **Street map (OSM)**: native Qt Web Mercator view, visible-area tiles only, local cache, attribution, geodesic search radius, source points and catalog footprints. Zoom/pan/recenter/retry controls; polar searches use the offline coordinate view.
- JSON, CSV, HTML and PDF exports with a SHA-256 manifest, provenance, errors and uncertainties. Lossless raw metadata remains in companion JSON and expandable HTML; PDF is a readable linked summary referencing the JSON hash. Formula-like CSV strings are escaped while originals stay in JSON. Original source links open on double-click.
- Exact URL/hash grouping helpers, file SHA-256, optional local image perceptual hashing. Permission-gated download helper; current discovery adapters conservatively permit metadata only.

## Verified live behavior

The bounded June 2024/Samolaco live query returned 88 records when all four public sources responded: 38 satellite catalog records and 50 nearby Commons candidates. Commons recording dates remain unconfirmed. Current Windows prereleases are available at https://github.com/motthz/GeoTrace/releases .

Earlier 0.1.0 test: Samolaco, 31 October 2026 01:00–02:00 Europe/Rome, 1 km: three satellite catalogs returned no results in their queried subsets. Commons returned HTTP 403 from this environment, recorded as UNAVAILABLE, not zero matches. In 0.1.1 the application User-Agent includes the project URL and Commons access succeeded in the real UI test after an earlier provider-side busy response. This establishes no conclusion about an incident or the existence of other footage.

Separate integration query, Samolaco, June 2024, 10 km: Copernicus returned 6 records, NASA 7, Earth Search 25 (first-page cap). These are catalog records, not downloaded or independently verified images. Actual raw responses and exported reports remain under ignored `private/`, strictly separate from mocked unit tests.

## Limits of this release

This is an incremental working release, not the full requested production system. QUICK/DEEP/EXTENDED currently change STAC first-page budgets only; there is no multi-round archive discovery. Keywords/location labels are preserved in investigation parameters but do not yet expand provider queries. Searches are capped, not exhaustive; satellite footprint queries use bounding boxes rather than exact circle intersections. Commons searches at most 10 km/50 candidates and retains unknown capture-time candidates regardless of requested dates. NASA currently queries HLSL30 only; Copernicus queries Sentinel-2 L2A only.

Street tiles and previews depend on public service availability. Only supported HTTPS image hosts are loaded; non-web assets, inaccessible URLs and oversized images remain explicitly unavailable. The basemap cannot represent polar search areas outside Web Mercator; use the offline coordinate view there. Previews load only for visible gallery rows, and can be disabled. Their cache does not constitute a downloaded evidence archive. Timeline filtering, polygon user input, nearby names and additional CRS conversion remain pending. Nominatim and OSM tile policies apply: https://operations.osmfoundation.org/policies/nominatim/ and https://operations.osmfoundation.org/policies/tiles/ .

Authenticated video/social adapters, RSS discovery, webcam archives, query expansion, AI model manager/OCR/transcription/semantic analysis, near-duplicate video clustering, download queue/resume/UI, response cache, true pagination checkpoints and automatic migrations beyond schema version 1 are pending. No large models are downloaded. Permission-gated download is a Python helper, not an end-user download manager. A separate hardened transport is needed before exposing arbitrary untrusted download URLs in a service (DNS rebinding is not prevented by a preflight resolution check).

Tested on the current Windows 11/Python 3.12 host. Windows 10 and clean-machine deployment require additional validation. Qt/PySide6 licensing and third-party notices must be reviewed for redistribution.

## API references

- https://documentation.dataspace.copernicus.eu/APIs/STAC.html
- https://cmr.earthdata.nasa.gov/search/site/docs/search/api.html
- https://commons.wikimedia.org/wiki/Commons:API/MediaWiki
- https://earth-search.aws.element84.com/v1
