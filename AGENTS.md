# GeoTrace developer handoff

Python 3.11+ / PySide6 desktop, CPU only. No existing repository was supplied. Do not fabricate search results or conflate upload and recording times.

Architecture: `core.py` validated query/record dataclasses, spatial/time helpers, schema-v1 SQLite persistence; `providers.py` capabilities, public adapters and asynchronous coordinator; `app.py` Qt main thread with worker-owned asyncio loop; `reports.py` export; `media.py` optional local hashes and guarded downloads; `cli.py` headless retrieval.

Commands: `python -m pytest -q`; `python -m geotrace.app`; `python -m geotrace.cli --export private/reports`; `python -m PyInstaller --noconfirm --windowed --name GeoTrace --collect-data tzdata launch.py`.

Keep unit fixtures in tests, real investigations in ignored private/. Desktop archives are outside source under LOCALAPPDATA. Do not commit investigations or credentials. Preserve original provider metadata; estimates must be separate. HTTP 403 is unavailable/access denied, not necessarily authentication-required. A failed query must never be NO_RESULTS. New connectors subclass Provider and declare Capabilities. Maintain README/TODO/CHANGELOG when behavior changes. See TODO for incomplete user requirements. No delegation is required.
