# Changelog

## 0.1.4 — 2026-11-03

Add source thumbnails with visible-row loading, compact toggle, retry, author/license attribution and original links. Add a native OpenStreetMap tile view with current-cartography labeling, attribution, source points, catalog footprints, geodesic radius, zoom/pan/recenter and explicit polar/offline fallback. Add bounded asynchronous Qt Network retrieval, supported-host redirects, response size/image format checks, integrity-checked local cache and request cancellation for invisible queued work. Extract official NASA browse previews without changing full-asset download permissions. Fix first-show map centering. Publish export manifest only after all referenced files are in place. Extend regression coverage to 88 tests and native audit to seven tabs.

## 0.1.3 — 2026-11-03

Audit release. Fix archive reopening without original form parameters; geocoding/search handoff and overlapping coordinate lookups; cancellation before thread startup; early worker replacement; mutable result cells; stale details after empty searches. Fit startup window to the work area and make parameters scrollable. Keep forms and archive opening disabled during active searches. Display gallery timestamps in the selected timezone and sort timeline events by absolute time; tolerate malformed timestamps. Improve map dateline wrapping, MultiPolygon and NASA box footprints, click versus drag behavior and persistent offline legend.

Validate equal time ranges, media types and IANA zones even for offset timestamps. Reject malformed API payloads and resumed searches with different parameters; honor HTTP-date Retry-After. Missing/invalid capture times remain UNKNOWN. Close SQLite connections deterministically and refuse unsupported newer schemas. Share the default archive between CLI and desktop.

Generate readable linked PDF/HTML summaries, protect CSV formula-like text and include a SHA-256 export manifest; generate all artifacts before replacing previous reports. Validate local download identifiers. Add 63 regression tests and reproducible native Windows/UI and HTML/PDF rendering audit scripts. Prevent the build script from overwriting a running application.

## 0.1.2 — 2026-11-02

Synchronize location labels and coordinates on field completion. Reverse geocoding preserves exact entered coordinates. Detect IANA timezone offline with tzfpy, with manual override for ambiguous boundaries. Reject stale lookup responses. Normalize local dates and preserve duration when changing the start; reject reversed intervals. Replace editable provider/media lists with checkboxes and validate compatible selection. Added regression tests for coordinate authority, timezone override, stale responses, date normalization and invalid-input recovery (19 tests total).

## 0.1.1 — 2026-11-02

Fix changed location labels silently using previous coordinates. Resolve new location text before starting the worker. Center the coordinate map on the actual search area, use cosmetic pens and scale markers to the radius. Display provider statuses as a readable table; convert timeline timestamps to the investigation timezone. Add official public search links using location, date and event keywords, keeping these separate from API results. Classify Commons JSON busy responses as RATE_LIMITED. Use a project contact URL in API User-Agent. Log and display unhandled exceptions. Add Windows launcher, reproducible build script and GitHub Actions Windows tests/build. Expand to 14 automated tests including an actual Qt Start Search workflow with isolated fixtures.

## 0.1.0 — 2026-11-02

Created GeoTrace in the supplied empty workspace. Added public STAC/CMR/Commons connectors, parallel coordinator, SQLite archive, temporal/geographic classifications, Qt interface, offline map, timeline, provider coverage and four report formats. Added CLI and portable Windows build configuration, tests and continuity documentation.

Live integration exposed required collection filters in Copernicus and CMR; constrained initial adapters to Sentinel-2 L2A and HLSL30 and documented those coverage limits. Classified environment HTTP 403 separately from empty results. No synthetic evidence or automatically downloaded AI models.
