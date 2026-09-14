# AGENTS.md

Flask app (Python 3.14) adding LLM-assisted search to library catalogs (VuFind / Primo). No CI, no linter, no automated test suite — verify by running the app.

## Layout

- `app.py` — the only Flask entrypoint (web UI at `/`, JSON API at `POST /api/search`). Feature work goes here and in `systems/`.
- `systems/` — `base.py` holds shared LLM plumbing (prompt, tolerant JSON extraction, nh3 sanitization); `primo.py` / `vufind.py` are the integrations. Per-query flow: `translate_query` → `build_search_params` → `call_search` → `normalize_results` → `summarize_results`.
- `primo_ai_frontend_flask.py` and `vufind_ai_frontend_flask.py` at the repo root are dead single-file prototypes superseded by `app.py` + `systems/`. Do not edit them.

## Running

- Run `python app.py` from the project venv (venvs follow the `venv{python version}` naming convention) → http://127.0.0.1:5001
- App raises at import time without `OPENAI_API_KEY` and without at least one of `VUFIND_SEARCH_ENDPOINT` / `PRIMO_SEARCH_ENDPOINT`.
- `.env` is gitignored; `sample.env` is the template. Never commit `.env`.
- `DEBUG_LOG=/path/file` enables a file log of LLM responses (see `systems/base.py`).
- System selection per query (`detect_system` in `app.py`): "primo" in the query → Primo; else VuFind if configured; else fallback to Primo.
- `POST /api/search` is rate-limited to 10 req/min/IP (`API_RATE_LIMIT`) — repeated curl in development will 429.

## Production

systemd unit `maidisco.service` runs gunicorn against `app:app` in `/opt/maidisco` with its own `venv/` there (not the repo's). Subpath deployments set `APPLICATION_ROOT`; the SCRIPT_NAME middleware already lives in `app.py`.

## Gotchas

- LLM output is untrusted and the models are small/thinking models: the fallbacks in `systems/base.py` (extracting JSON from malformed output, reading `reasoning_content`) are deliberate workarounds. Don't "clean them up".
