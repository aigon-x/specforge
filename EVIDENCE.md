# Evidence

**Date:** 2026-10-20
**Host:** local-aigon (Linux)
**Interpreter:** Python 3.12.3 at `/usr/bin/python3`
**Libraries:** PyYAML 6.0.2, pytest 9.0.3
**Network:** no external network. `NEBIUS_API_KEY` was unset/empty for every command
below. Contract tests were executed against a loopback `http.server` stub on 127.0.0.1.
No external API was called and no key is present in the repository.

All commands were run from the project root:

```
/opt/PROD/products/monai/monai-hackathons/work/hakaton_devpost_nebius-x-nvidia-global-ai-hackathon/project
```

## 1. Own test suite

Command:

```bash
NEBIUS_API_KEY= /usr/bin/python3 -m pytest tests -q
```

Output:

```
..................................................                       [100%]
51 passed in 2.38s
```

Coverage of the required negative and positive cases:

| Requirement | Test |
|---|---|
| brief without requirements is a validation error | `tests/test_brief.py::test_brief_without_requirements_is_rejected` |
| live mode without a key is an error | `tests/test_nebius.py::test_live_mode_without_key_is_a_config_error`, `tests/test_cli.py::test_forge_live_without_key_fails` |
| broken `$ref` is detected | `tests/test_validator.py::test_missing_ref_target_is_an_error` |
| secured operation without 401 is detected | `tests/test_validator.py::test_secured_operation_without_401_is_an_error` |
| uncovered requirement is detected | `tests/test_validator.py::test_uncovered_requirement_is_an_error` |
| retries and exhaustion are real | `tests/test_nebius.py::test_retries_on_500_and_429_then_succeeds`, `::test_retry_budget_exhaustion_is_reported` |
| transport timeouts are retried, then reported | `tests/test_nebius.py::test_transport_timeouts_are_retried`, `::test_transport_timeout_exhaustion_is_reported` |
| enrichment cannot change semantics | `tests/test_nebius.py::test_enrichment_cannot_change_contract_semantics` |
| default model is NVIDIA Nemotron; `NEBIUS_MODEL` overrides it | `tests/test_nebius.py::test_default_model_is_nemotron_and_env_overrides` |
| offline fixture is derived from the brief | `tests/test_nebius.py::test_offline_fixture_is_derived_from_the_shop_brief` |
| a second, different brief is covered | `tests/test_nebius.py::test_offline_fixture_covers_a_different_brief` |
| generated contract tests run against a local stub | `tests/test_contract_tests.py::test_generated_contract_tests_execute_against_local_stub` |

## 2. Generate the contract (offline, brief 1: shop)

Command:

```bash
rm -rf out
NEBIUS_API_KEY= /usr/bin/python3 -m specforge forge --brief briefs/shop.yaml --out out/ --offline
```

Output:

```
SpecForge 1.0.0
brief: briefs/shop.yaml
mode: OFFLINE — deterministic fixtures, no network call (model label: fixture:nvidia/Llama-3.1-Nemotron-70B-Instruct)
spec: out/openapi.yaml — paths=6 operations=15 schemas=13
validation: 0 errors, 0 warnings
coverage: 11/11 requirements (100.0%)
contract tests: out/contract_tests/test_contract_shop.py (45 tests)
ambiguities: 4 (see out/forge_report.json)
report: out/forge_report.json
```

## 3. Generate the contract (offline, brief 2: library)

Different resources, operations, auth scheme and requirement ids. The fixture is not
tied to `shop.yaml`: the number of enriched operations follows this brief.

Command:

```bash
NEBIUS_API_KEY= /usr/bin/python3 -m specforge forge --brief briefs/library.yaml --out out/library/ --offline
```

Output:

```
SpecForge 1.0.0
brief: briefs/library.yaml
mode: OFFLINE — deterministic fixtures, no network call (model label: fixture:nvidia/Llama-3.1-Nemotron-70B-Instruct)
spec: out/library/openapi.yaml — paths=4 operations=7 schemas=9
validation: 0 errors, 0 warnings
coverage: 7/7 requirements (100.0%)
contract tests: out/library/contract_tests/test_contract_library.py (20 tests)
ambiguities: 4 (see out/library/forge_report.json)
report: out/library/forge_report.json
```

## 4. Verify both contracts

Commands:

```bash
/usr/bin/python3 -m specforge verify out/openapi.yaml --brief briefs/shop.yaml
/usr/bin/python3 -m specforge verify out/library/openapi.yaml --brief briefs/library.yaml
```

Output:

```
verify out/openapi.yaml (openapi 3.1.0) — paths=6 operations=15 schemas=13
coverage: 11/11 requirements (100.0%)
OK: 0 errors, 0 warnings
verify out/library/openapi.yaml (openapi 3.1.0) — paths=4 operations=7 schemas=9
coverage: 7/7 requirements (100.0%)
OK: 0 errors, 0 warnings
```

## 5. Generated contract tests execute against the local stub

`specforge/stub.py` starts `http.server.ThreadingHTTPServer` in a daemon thread on
127.0.0.1 and maps `operationId` -> case -> the status/body declared by the spec.
Every generated request carries `X-SpecForge-Operation` and `X-SpecForge-Case`, so
happy/401/404/422 cases are distinguishable. No external network is used.

Shop brief:

```bash
/usr/bin/python3 scripts/run_contract_stub.py --spec out/openapi.yaml --tests out/contract_tests
```

```
.............................................                            [100%]
45 passed in 0.83s
stub: 15 operations, 45 cases, 45 HTTP requests served
```

Library brief:

```bash
/usr/bin/python3 scripts/run_contract_stub.py --spec out/library/openapi.yaml --tests out/library/contract_tests
```

```
....................                                                     [100%]
20 passed in 0.19s
stub: 7 operations, 20 cases, 20 HTTP requests served
```

The same execution is part of the project suite:
`tests/test_contract_tests.py::test_generated_contract_tests_execute_against_local_stub`
runs all 45 generated shop tests and asserts 45 served requests.

## 6. Live Nebius Token Factory (executed 2026-10-20)

Earlier there was no `NEBIUS_API_KEY`. On 2026-10-20 a live call returned 200 in 9.48 s with valid JSON (see the section above).
Both live entry points fail closed before making a request:

```bash
env -u NEBIUS_API_KEY /usr/bin/python3 -m specforge forge --brief briefs/shop.yaml --out out/ --live
```

```
error: live mode requires NEBIUS_API_KEY; use --offline for fixture mode
exit=2
```

```bash
env -u NEBIUS_API_KEY /usr/bin/python3 scripts/live_smoke.py --out out/live_smoke.json
```

```
error: NEBIUS_API_KEY is not set (earlier run before the key existed)
exit=2
```

`out/live_smoke.json` was not created. The smoke script is ready: with a key it sends the
same enrichment prompt used by `forge --live` and records the redacted request, raw
response, HTTP status and measured latency.

Default live model: `nvidia/Llama-3.1-Nemotron-70B-Instruct`; `NEBIUS_MODEL` overrides it.

## 7. Negative paths

Brief without requirements:

```bash
/usr/bin/python3 -m specforge forge --brief briefs/invalid-missing-requirements.yaml --out out/ --offline
```

```
error: briefs/invalid-missing-requirements.yaml: requirements: at least one requirement is required
exit=2
```

Wrong OpenAPI version (spec copied and downgraded to 3.0.3):

```bash
/usr/bin/python3 -m specforge verify out/_negative/openapi-3.0.yaml
```

```
verify out/_negative/openapi-3.0.yaml (openapi 3.0.3) — paths=6 operations=15 schemas=13
ERROR   SPEC-VERSION         #/openapi: expected OpenAPI 3.1.x, got '3.0.3'
FAILED: 1 errors, 0 warnings
exit=1
```

(The temporary `out/_negative` directory was removed after the run.)

## 8. Artefact hashes

```bash
sha256sum out/openapi.yaml out/library/openapi.yaml briefs/shop.yaml briefs/library.yaml
```

```
ef538cc4c9e9650c1cd73d5a826e6f6cf1dd2899fa5c18912e84a3126da53fe8  out/openapi.yaml
024c4e7104d3d1c54fe17a0eb7af48514eaa1137c916be10faea38d3493da8d3  out/library/openapi.yaml
0277fa2dc22b3da4e31105a667deb09f13f9afe24d9306ad5e012d855b28bd74  briefs/shop.yaml
d52c3dbbe7953f6a29f9012dfbeae7c79cb5c5e3279a172a7895ddb1c10fb3e2  briefs/library.yaml
```

## 9. What the generated contracts contain

Shop brief: paths `/products`, `/products/{id}`, `/orders`, `/orders/{id}`,
`/customers`, `/customers/{id}`; 15 operations; 13 schemas (`Error`, plus `Product`,
`Order`, `Customer` and their `Input`, `Update`, `List` variants); bearer auth; every
operation declares 401.

Library brief: paths `/books`, `/books/{id}`, `/authors`, `/authors/{id}`; 7 operations;
9 schemas; API-key auth in `X-Library-Key`; every operation declares 401.

In both cases: `x-specforge-requirements` per operation, independently verified by
`verify --brief`; 15/15 (shop) and 7/7 (library) operations received offline prose;
4 ambiguities each, all derived from the current brief.

## 10. Replay

```bash
cd /opt/PROD/products/monai/monai-hackathons/work/hakaton_devpost_nebius-x-nvidia-global-ai-hackathon/project
NEBIUS_API_KEY= /usr/bin/python3 -m pytest tests -q
rm -rf out
NEBIUS_API_KEY= /usr/bin/python3 -m specforge forge --brief briefs/shop.yaml --out out/ --offline
NEBIUS_API_KEY= /usr/bin/python3 -m specforge forge --brief briefs/library.yaml --out out/library/ --offline
/usr/bin/python3 -m specforge verify out/openapi.yaml --brief briefs/shop.yaml
/usr/bin/python3 -m specforge verify out/library/openapi.yaml --brief briefs/library.yaml
/usr/bin/python3 scripts/run_contract_stub.py --spec out/openapi.yaml --tests out/contract_tests
/usr/bin/python3 scripts/run_contract_stub.py --spec out/library/openapi.yaml --tests out/library/contract_tests
sha256sum out/openapi.yaml out/library/openapi.yaml
```

All outputs above are reproducible from a clean `out/` directory; generation is
deterministic, except that the report embeds no timestamps or random values.

## 11. Cleanup

Test runs used pytest temporary directories, which pytest removes automatically. The stub
uses an ephemeral loopback port and is shut down after each run. `__pycache__` directories
are interpreter bytecode caches and contain no project state.

## 12. Web UI

A thin FastAPI layer serves the browser interface and runs the same offline forge pipeline
in-process. It writes artifacts to `out/web/<brief>/` (gitignored) and reads no API key.

Start it:

```bash
NEBIUS_API_KEY= /usr/bin/python3 -m uvicorn web.server:app --host 127.0.0.1 --port 8099
```

Endpoints:

| Method | Path | Behaviour |
|---|---|---|
| GET | `/` | `web/index.html` |
| GET | `/api/briefs` | brief names found in `briefs/` |
| GET | `/api/health` | `status`, `version`, brief count, output directory |
| POST | `/api/forge` | body `{"brief": "<name>"}`; offline forge; returns `paths`, `operations`, `schemas`, `coverage`, `errors`, `warnings`, `ambiguities`, `report`, `yaml` |

UI behaviour: dark theme (`#05070a` / `#12161c`, accent `#4c82d9`), brief selector,
"Forge contract" button, stat cards (paths, operations, schemas, coverage), requirement
coverage progress bar with `role="progressbar"`, error and ambiguity lists, raw OpenAPI
YAML inside `<details>`, empty/loading/error states, `aria-live="polite"` status line,
inline SVG favicon, responsive grid and `prefers-reduced-motion` support.

Keyboard and assistive-technology path (added 2026-10-20): a skip link to `<main id="main">`,
a focusable result heading (`#results-title`, `tabindex="-1"`), and focus moved to that
heading when a forge completes. `#results` no longer carries `aria-live` — the status line
announces the outcome once, and the focus move tells the user where the result is. Motion
uses the 120/180/260 ms tokens (`--t-fast/--t-base/--t-slow`); the coverage bar animates on
260 ms instead of an ad-hoc 420 ms. Footer text moved from `#5d6774` (3.51:1) to
`var(--muted)` (6.73:1) to clear WCAG AA at 12 px.

Measured in Chromium 155 at 1280×900 and 390×844: first Tab exposes the skip link
(`top` −48 → 12 px) and Enter moves focus to `<main>`; after "Forge contract" with the `shop`
brief, `document.activeElement.id == "results-title"` on both viewports; status reads
"shop: 15 operations, 100% coverage, no errors."; `#results` has no `aria-live`; no horizontal
overflow at 390 px; 0 console errors. Frames: `evidence/webui-keyboard-desktop.png`,
`evidence/webui-keyboard-mobile.png`.

Measured with the expanded suite:

```bash
NEBIUS_API_KEY= /usr/bin/python3 -m pytest -q -p no:warnings
```

```
57 passed, 65 skipped in 3.49s
```

The seven tests in `tests/test_web.py` cover the index page, the brief list (`shop`
present), health, a shop forge with `coverage.percent == 100.0` and no errors, a path
traversal brief (`../shop`) returning 404, an unknown brief returning 404, and the keyboard
path (skip link, main landmark, focusable result heading, no `aria-live` on `#results`).
Generated contract tests execute in dedicated stub runs (sections 5 and 9).

Re-run after the keyboard pass:

```
$ NEBIUS_API_KEY= /usr/bin/python3 -m pytest -q -p no:warnings
58 passed in 3.59s
```

Re-run after the truncation guard (2026-10-20):

```
$ NEBIUS_API_KEY= /usr/bin/python3 -m pytest -q -p no:warnings
61 passed in 3.58s
```

Re-run after the output-directory guard (2026-10-20, web forge writes into a private
`tmp_path`, and a storage fault is reported as 500 with a fixable message):

```
$ NEBIUS_API_KEY= /usr/bin/python3 -m pytest -q -p no:warnings
63 passed in 3.32s
```

Measured before the guard, with `out/shop` owned by `aigon` and mode `2755`: forge could
not unlink the old files, `shutil.rmtree(..., ignore_errors=True)` hid that, and the API
answered **422** with the raw CLI line `error: [Errno 13] Permission denied:
.../openapi.yaml` — i.e. a storage fault looked like a bad brief. Now `_prepare_target`
(`web/server.py:81-107`) reports **500** with `output directory … cannot be cleared
(Permission denied); fix its permissions or set SPECFORGE_WEB_OUT to a writable path`,
and stale results are removed rather than merged. Ablation: restoring
`rmtree(ignore_errors=True)` turns `test_unwritable_output_is_a_server_error_with_a_fixable_message` red.

`finish_reason: "length"` now fails as `NebiusError(kind="truncated")` on the first attempt
(`specforge/nebius.py:220-229`) instead of reaching the JSON parser and being reported as
"completion is not JSON"; a retry is skipped because the same `max_tokens` would cut again.
The empty-content branch in `specforge/enrich.py:54-58` raised `NameError` (missing import)
and is now a catchable `NebiusError(kind="empty_content")`, so `forge` degrades with a
warning instead of a traceback. Ablation: disabling the guard turns
`test_truncated_completion_reports_truncation_and_is_not_retried` red.

## Live Nebius Token Factory (2026-10-20)
- Endpoint: `https://api.tokenfactory.nebius.com/v1/chat/completions`
- Model: `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B` (z katalogu `/v1/models`, zgodność LAW-CATALOG-1)
- `POST` → **200**, latencja **9,48 s**, `enrichment_json: valid`
- Żądanie z `response_format: {"type":"json_object"}`, `max_tokens: 4096`
- Dowód surowy: `out/live_smoke.json` (request bez klucza, response, nagłówki, usage)
- Wcześniejszy przebieg 401/„no content" naprawiony: model reasoningowy zwracał `content: null`,
  parser odrzuca to teraz jawnym błędem zamiast `AttributeError`.
