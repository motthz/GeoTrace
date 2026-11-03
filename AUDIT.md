# GeoTrace 0.1.3 audit — 2–3 November 2026

This audit covers implemented behavior. It does not certify completion of the original universal-discovery specification or guarantee future external-provider availability.

## Method and environment

Windows 11 (development host), Python 3.12, PySide6 6.12. Sixty-three isolated automated regression tests passed. Windows UI Automation drives a real application window using mouse clicks, keyboard input and native dialogs. Real network searches use public providers and isolated audit profiles; no fixture records enter live investigations. Screenshots are captured from application windows, not constructed mockups. Exported HTML is rendered with Chromium/Qt WebEngine and every PDF page is loaded, rendered and checked for text with Qt PDF. Screenshots are inspected visually.

Audit evidence stays under ignored `private/audit/`: native screenshot galleries, per-step checks.json, isolated SQLite archives, original responses, exported files, report rendering checks and JUnit XML. Generated HTML/PDF reports are compared with the saved JSON records and their SHA-256 manifest is verified. See the local `private/audit/index.html` for the final evidence index.

Final evidence index: **63 automated tests, 48 native/rendering checks and 52 screenshots**, all final checks passed. The packaged run returned 38 satellite records with Commons RATE_LIMITED; the successful source run returned 88 total candidates. Both HTML reports matched their JSON record counts; all 21 + 10 PDF pages rendered with extractable text. A separate CLI live query with whitespace-separated source names returned 31 real satellite records and exported successfully. The build preflight correctly refused to overwrite the then-running application.

## User journeys covered

| Area | Verification |
| --- | --- |
| Startup | Real Windows window, initial action availability, smaller 1000×740 window and scrollable parameters |
| Location | Real Nominatim lookup and choice dialog, reverse lookup, exact-coordinate preservation, rapid changes, automatic New York/Rome timezone, unknown place recovery |
| Dates | ISO/Italian normalization, duration preservation, reversed/equal intervals, DST ambiguity error and manual UTC override |
| Search | Real retrieval, source status, compatible source/media selection, read-only form while running, provider error/timeout handling |
| Gallery | Real records, selection, filter/clear, immutable cells, source URL dispatch, selected-timezone timestamps |
| Map | Radius/center, provider coordinates, catalog polygons/MultiPolygons and NASA boxes, dateline wrapping, single-click details, bounded zoom and pan |
| Timeline | Discrete timestamps, UTC ordering and selected-zone display; unknown/invalid timestamps stay unconfirmed |
| Coverage | Real successes, restricted sources, unavailable/busy sources and failure distinct from empty results |
| Metadata | Original JSON record, selection synchronization, clearing when no record is selected |
| Public links | Correct URL construction from saved parameters; these are external searches, not retrieved evidence |
| Archive | Native selection dialog, restored query fields/source selections/timezone, restart and persistence, SQLite connections/schema guard |
| Reports | Native directory chooser accept/cancel; HTML/PDF/CSV/JSON; full companion JSON; manifest hashes; HTML record count and all PDF pages |
| Cancellation | Before startup and during real search; retained archived records; clean close and restart |

During live desktop runs the June 2024/10 km test returned 38 satellite catalog records and, when Commons was available, 50 additional geotagged candidates (88 total). Commons also returned a transient busy response in another run; this appeared as RATE_LIMITED, never as zero results. Commons candidates have unconfirmed capture dates and are not established as recordings within the requested interval. These counts describe bounded returned pages, not exhaustive coverage.

## Defects repaired

- Archive results reopened with unrelated current form parameters; restore the original location, exact coordinates, interval, timezone, radius, mode, keywords and source/media choices.
- Geocoding could finish its result handler while its thread was still running, leaving a pending search stuck; begin after thread completion and defer while a location choice is open.
- A second coordinate edit could be dropped during an earlier lookup; queue the final pair, discard stale successes/errors and preserve exact coordinates.
- Cancellation could be lost before the event loop existed; retain cancellation state and checkpoint pre-start cancellation.
- Starting a replacement worker could race thread completion; re-enable Start on QThread.finished.
- Invalid/equal ranges, unknown media and invalid zones with explicit offsets could bypass core validation; validate centrally and compare actual UTC datetimes.
- Malformed API JSON could become NO_RESULTS; require the expected response envelope. Invalid/missing capture timestamps no longer receive METADATA_SUPPORTED.
- SQLite context managers committed without explicitly closing connections, and newer schemas could be downgraded; close deterministically and reject unsupported versions.
- Result cells could be edited independently of saved records, details could stay stale, gallery times could ignore the selected zone, and timeline ordering used display strings; correct each behavior without rewriting original metadata.
- The startup window could exceed the available screen at scaling; bound its size and scroll parameters. Preserve map clicks versus drags and wrap dateline features.
- CSV cells could execute spreadsheet formulas; escape dangerous strings, keeping originals in JSON. Make reports readable, embed a report font, add integrity hashes, and finish generation before replacing existing outputs.
- CLI/desktop default archives differed; use the same application archive. Validate source selection and resumed parameters before retrieving records; mutually exclusive CLI inputs and invalid files return actionable errors without tracebacks.
- Build output could be overwritten while the executable was running; fail early and leave it intact.

## Limits and unverified areas

- The map remains an offline longitude/latitude diagram, explicitly labeled, with no street basemap. The gallery remains a metadata table, without image/video thumbnails or an embedded player.
- Authorized social/video retrieval, AI analysis/model manager, download queue/resume UI, news/RSS retrieval, true multi-round discovery and exhaustive pagination are not implemented. Provider statuses disclose these limits; external search links do not implement those connectors.
- Positive media-download behavior is an internal utility rather than a user-facing workflow. No third-party copyrighted asset was downloaded in this audit. The preflight DNS guard does not eliminate DNS rebinding; do not expose the utility as a service without a hardened transport.
- API availability, quotas, exact historical content, historical timezone boundary changes, all languages/fonts, all display scales, clean Windows 10/11 machines, offline installation, code signing and SmartScreen reputation are not certified.
- Default browser URL dispatch is regression-tested; the content and behavior of third-party sites opened by that browser are outside application control.
- Fault tests cover failures, cancellation and export-generation errors; they do not certify recovery from arbitrary disk loss, power failure or physical database corruption.

## Reproduce

```powershell
python -m pip install -e '.[test,build,audit]'
python -m pytest -q --junitxml=private/audit/tests-final.xml
python tools/audit_desktop.py --output private/audit/source
python tools/audit_geocoding.py --output private/audit/geocoding
python tools/audit_reports.py private/audit/source
# Repeat against the exact Windows executable, with separate output/profile folders:
python tools/audit_desktop.py --exe dist/GeoTrace/GeoTrace.exe --output private/audit/packaged
python tools/audit_geocoding.py --exe dist/GeoTrace/GeoTrace.exe --output private/audit/geocoding-packaged
python tools/audit_reports.py private/audit/packaged
```

Run native scripts one at a time in an interactive Windows session. Earlier interrupted harness runs are retained separately; use the final successful runs listed in the evidence index. A failed audit condition is a failure to investigate, not permission to insert synthetic results.

Generate the final evidence gallery with `python tools/build_audit_index.py` after all four final runs and report checks complete. Earlier failed harness attempts are not final product results; their logs remain available in separate private folders.
