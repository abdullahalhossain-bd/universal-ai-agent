# Standalone E2E scripts

These are **not** pytest modules — pytest.ini explicitly excludes this
directory (`norecursedirs = tests/e2e`) because each script calls
`sys.exit()` when it can't reach a running server, which crashes
pytest's collection instead of failing gracefully as a test.

Run them directly against a live instance instead:

```bash
python tests/e2e/api_smoke_test.py       # quick health/auth smoke check
python tests/e2e/api_e2e_test.py         # authenticated flow
python tests/e2e/api_full_e2e_test.py    # fuller end-to-end flow
```

They default to `http://127.0.0.1:8000` — start the app first
(`docker compose up` or `uvicorn app.main:app --reload`).

The real, CI-run test suite lives one level up in `tests/*.py` and
runs with `pytest`.
