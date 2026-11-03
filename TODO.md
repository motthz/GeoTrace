# Pending requirements

- Implement authorized YouTube/Flickr/etc adapters with secure user credential storage, official scopes and quotas.
- Implement query expansion, nearby/local-language names, RSS and permitted archive discovery.
- Add proper paginated bounded rounds with durable continuation tokens/cache; rate scheduling per domain and HTTP-date Retry-After.
- Add polygon queries, exact footprint-circle geometry checks and CRS transformations.
- Add richer gallery layouts and granular timeline filters. Source previews, OSM basemap/attribution, offline fallback and selected-timezone display are implemented.
- Add evidence review workflow and original time-zone/interval normalization with precision tracking.
- Add permission/license review UI and download queue, resume, attribution sidecars and safe transport.
- Add local model manager and opt-in OCR/transcription/embeddings, video keyframes, near-duplicate grouping.
- Add formal sequential migrations and FTS, links between independently discovered provenance records.
- Expand beyond the audited regression/UI flows: schema migrations, exact footprint filtering, more language/font combinations, corrupt database recovery and power-loss scenarios. See AUDIT.md for the 63 current tests and native Windows evidence.
- Verify portable executable on clean Windows 10/11, accessibility, dependency notices and redistribution licensing.
