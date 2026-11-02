# Pending requirements

- Implement authorized YouTube/Flickr/etc adapters with secure user credential storage, official scopes and quotas.
- Implement query expansion, nearby/local-language names, RSS and permitted archive discovery.
- Add proper paginated bounded rounds with durable continuation tokens/cache; rate scheduling per domain and HTTP-date Retry-After.
- Add polygon queries, exact footprint-circle geometry checks and CRS transformations.
- Add thumbnail gallery, map basemap/attribution and granular timeline filters. Selected-timezone timeline display is implemented.
- Add evidence review workflow and original time-zone/interval normalization with precision tracking.
- Add permission/license review UI and download queue, resume, attribution sidecars and safe transport.
- Add local model manager and opt-in OCR/transcription/embeddings, video keyframes, near-duplicate grouping.
- Add formal sequential migrations and FTS, links between independently discovered provenance records.
- Expand tests: timeout/retry/cancel orchestration, resume, schema migrations, footprint filters and UI search interactions.
- Verify portable executable on clean Windows 10/11, accessibility, dependency notices and redistribution licensing.
