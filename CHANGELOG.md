# Changelog

## 0.1.1 — 2026-11-02

Fix changed location labels silently using previous coordinates. Resolve new location text before starting the worker. Center the coordinate map on the actual search area, use cosmetic pens and scale markers to the radius. Display provider statuses as a readable table; convert timeline timestamps to the investigation timezone. Add official public search links using location, date and event keywords, keeping these separate from API results. Classify Commons JSON busy responses as RATE_LIMITED. Use a project contact URL in API User-Agent. Log and display unhandled exceptions. Add Windows launcher, reproducible build script and GitHub Actions Windows tests/build. Expand to 14 automated tests including an actual Qt Start Search workflow with isolated fixtures.

## 0.1.0 — 2026-11-02

Created GeoTrace in the supplied empty workspace. Added public STAC/CMR/Commons connectors, parallel coordinator, SQLite archive, temporal/geographic classifications, Qt interface, offline map, timeline, provider coverage and four report formats. Added CLI and portable Windows build configuration, tests and continuity documentation.

Live integration exposed required collection filters in Copernicus and CMR; constrained initial adapters to Sentinel-2 L2A and HLSL30 and documented those coverage limits. Classified environment HTTP 403 separately from empty results. No synthetic evidence or automatically downloaded AI models.
