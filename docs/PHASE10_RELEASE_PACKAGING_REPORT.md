# Phase 10 — Release packaging & legacy quarantine

**Platform:** ROZVI **0.9.0**

## Implemented

1. `src/rozvi/legacy.py` — disclaimer, product metadata, helper predicates
2. `main.run_pipeline` — warns on use; tags GeoTIFF; embeds product metadata in provenance
3. `CHANGELOG.md` — phases 2–10
4. `docs/LEGACY_AND_DEPRECATION.md` — canonical vs legacy map
5. `docs/RELEASE_0.9.md` — release notes + short scientific statement

## Tests

`tests/rozvi/test_legacy_quarantine.py`

## Non-claims

No change to flood-depth validation status (still provisional).
No removal of the legacy path (still runnable, but labelled).
