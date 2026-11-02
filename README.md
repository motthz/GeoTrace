# GeoTrace 0.1.1

**Windows:** double-click `Avvia GeoTrace.cmd` in the project folder after building. Source checkout: run `powershell -ExecutionPolicy Bypass -File .\Build-Windows.ps1` to install dependencies, test and create the portable application. Keep the entire `dist/GeoTrace` directory together. No Python installation is needed to run the completed portable build.

**Search behavior:** location text changes are geocoded before search; explicitly editing coordinates uses the entered coordinates. Catalogs may return no acquisitions for a short nighttime interval. Inspect **Source coverage** for actual results, failures and limits. **Public search links** opens YouTube, Commons, Google News and Flickr using the location label, keywords and date; these are external searches, not automatically retrieved evidence. Use an accurate nearby place label when entering coordinates because external keyword links use that label.

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

Desktop archives reside in `%LOCALAPPDATA%/GeoTrace/archive.sqlite`. CLI defaults to `private/archive.sqlite`. No credentials, paid APIs, models or private camera discovery are used.

## Implemented

- Four real, concurrent API adapters: Copernicus Sentinel-2 L2A STAC, Element84 Earth Search STAC, NASA CMR HLSL30, Wikimedia Commons geosearch.
- Coordinate/radius/date/time zone validation, UTC conversion, ambiguous/nonexistent local time rejection, dateline and polar bounding boxes, radius filtering for geotagged Commons records.
- Manual Nominatim place lookup with selection and cooldown; reverse lookup available as Python API.
- SQLite investigation archive, durable provider checkpoints, cancellation, bounded retry/backoff, timeout handling, CLI repeat-and-merge via `--resume ID`.
- Searchable results table, original record inspector, offline coordinate map centered on the search radius with STAC polygons, zoom/pan and double-click record selection, timezone-converted discrete timestamp timeline and readable coverage matrix.
- JSON, CSV, HTML and PDF exports preserving raw metadata, provenance, errors and uncertainties. Original source links open on double-click.
- Exact URL/hash grouping helpers, file SHA-256, optional local image perceptual hashing. Permission-gated download helper; current discovery adapters conservatively permit metadata only.

## Verified live behavior

Version 0.1.1: 14 local automated tests passed, including Qt Start Search, persistence/reopen, changed-location resolution and Commons busy-status handling. A real search through the Qt event loop retrieved 88 records: 38 satellite catalog records and 50 nearby Commons candidates. Commons recording dates remain unknown and are not confirmed within the requested historical interval. The updated portable executable passed a four-second startup smoke check on the development Windows 11 host. Download the incremental Windows prerelease at https://github.com/motthz/GeoTrace/releases/tag/v0.1.1 .

Earlier 0.1.0 test: Samolaco, 31 October 2026 01:00–02:00 Europe/Rome, 1 km: three satellite catalogs returned no results in their queried subsets. Commons returned HTTP 403 from this environment, recorded as UNAVAILABLE, not zero matches. In 0.1.1 the application User-Agent includes the project URL and Commons access succeeded in the real UI test after an earlier provider-side busy response. This establishes no conclusion about an incident or the existence of other footage.

Separate integration query, Samolaco, June 2024, 10 km: Copernicus returned 6 records, NASA 7, Earth Search 25 (first-page cap). These are catalog records, not downloaded or independently verified images. Actual raw responses and exported reports remain under ignored `private/`, strictly separate from mocked unit tests.

## Limits of this release

This is an incremental working release, not the full requested production system. QUICK/DEEP/EXTENDED currently change STAC first-page budgets only; there is no multi-round archive discovery. Keywords/location labels are preserved in investigation parameters but do not yet expand provider queries. Searches are capped, not exhaustive; satellite footprint queries use bounding boxes rather than exact circle intersections. Commons searches at most 10 km/50 candidates and retains unknown capture-time candidates regardless of requested dates. NASA currently queries HLSL30 only; Copernicus queries Sentinel-2 L2A only.

The map is an offline longitude/latitude plot, without a street basemap; the gallery is a record table, without thumbnail fetching. Timeline displays timezone-aware timestamps in the investigation's selected zone; original timestamps stay in raw records. Filter controls per timeline, polygon user input, nearby names and CRS conversion remain pending. Nominatim policies apply: https://operations.osmfoundation.org/policies/nominatim/ .

Authenticated video/social adapters, RSS discovery, webcam archives, query expansion, AI model manager/OCR/transcription/semantic analysis, near-duplicate video clustering, download queue/resume/UI, response cache, true pagination checkpoints and automatic migrations beyond schema version 1 are pending. No large models are downloaded. Permission-gated download is a Python helper, not an end-user download manager. A separate hardened transport is needed before exposing arbitrary untrusted download URLs in a service (DNS rebinding is not prevented by a preflight resolution check).

Tested on the current Windows 11/Python 3.12 host. Windows 10 and clean-machine deployment require additional validation. Qt/PySide6 licensing and third-party notices must be reviewed for redistribution.

## API references

- https://documentation.dataspace.copernicus.eu/APIs/STAC.html
- https://cmr.earthdata.nasa.gov/search/site/docs/search/api.html
- https://commons.wikimedia.org/wiki/Commons:API/MediaWiki
- https://earth-search.aws.element84.com/v1
