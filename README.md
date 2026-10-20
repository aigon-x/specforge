# SpecForge

SpecForge turns a short product brief (YAML) into an OpenAPI 3.1 contract, audits the
contract with its own validator, and emits runnable pytest contract tests. An optional
LLM step (Nebius Token Factory, OpenAI-compatible) improves summaries, descriptions and
flags ambiguities; it can never add endpoints, fields or status codes. Without an API key
the whole pipeline runs on a deterministic fixture derived from the brief and says so in
the output.

## What it does

- `forge` — brief -> `openapi.yaml`, `forge_report.json`, `contract_tests/`.
- `verify` — structural audit of an OpenAPI 3.1 document: version, schemas, local `$ref`,
  path parameters, operation ids, response descriptions, security contradictions and
  (with `--brief`) requirement coverage by method/path/status.
- `tests/` — 51 own tests, including negative cases (invalid brief, no key in live mode,
  broken references, missing 401, uncovered requirements); within them all 45 generated
  shop contract tests and all 20 library contract tests execute against a local
  `http.server` stub.

No production server is bundled. A loopback stub (`specforge/stub.py`) serves the
generated contract tests; the same tests run against any implementation that matches
the spec.

## Quickstart

```bash
cd /path/to/project
python3 -m specforge forge --brief briefs/shop.yaml --out out/ --offline
python3 -m specforge forge --brief briefs/library.yaml --out out/library/ --offline
python3 -m specforge verify out/openapi.yaml --brief briefs/shop.yaml
python3 -m pytest tests -q
```

Generated contract tests execute against the bundled local stub (no external network):

```bash
python3 scripts/run_contract_stub.py --spec out/openapi.yaml --tests out/contract_tests
```

Against a real service:

```bash
SPECFORGE_BASE_URL=https://api.example.com SPECFORGE_TOKEN=... \
  python3 -m pytest -q out/contract_tests
```

Live enrichment through Nebius Token Factory:

```bash
export NEBIUS_API_KEY=...            # never commit it
python3 -m specforge forge --brief briefs/shop.yaml --out out/ --live
```

`--auto` (default when neither flag is given) uses live mode when `NEBIUS_API_KEY` is set
and a fixture derived from the brief otherwise. Every run prints `mode: OFFLINE ...` or
`mode: LIVE ...`.

Live smoke test (one real Token Factory call, records request/response/latency):

```bash
export NEBIUS_API_KEY=...
python3 scripts/live_smoke.py --out out/live_smoke.json
```

Without `NEBIUS_API_KEY` the script exits `2` before any request and writes nothing.

## CLI

```
python3 -m specforge forge --brief <brief.yaml> --out <dir> [--offline|--live]
                           [--no-enrich] [--no-contract-tests] [--timeout SECONDS]
                           [--retries N] [--json]
python3 -m specforge verify <spec.yaml|json> [--brief <brief.yaml>] [--json] [--strict]
```

Exit codes: `0` success, `1` validation errors (or warnings with `--strict`), `2` invalid
brief, unreadable input or live mode without a key.

Environment: `NEBIUS_API_KEY`, `NEBIUS_API_BASE` (default
`https://api.studio.nebius.ai/v1`), `NEBIUS_MODEL` (default
`nvidia/Llama-3.1-Nemotron-70B-Instruct`), `NEBIUS_TIMEOUT`, `SPECFORGE_BASE_URL`,
`SPECFORGE_TOKEN`, `SPECFORGE_TIMEOUT`. `NEBIUS_MODEL` overrides the default and may
name any model available in Nebius Token Factory.

## Brief format

```yaml
name: Shop API
version: 1.0.0
base_url: https://api.shop.example/v1
auth: {type: bearer}              # none | bearer | api_key
resources:
  - name: Product
    path: /products
    id_field: id                  # must be string/integer and read_only
    operations: [list, create, get, update, delete]
    search: [name]                # optional list filters
    extra_errors: [409]
    fields:
      id: {type: string, format: uuid, read_only: true}
      name: {type: string, required: true, min_length: 1, max_length: 120}
      price_cents: {type: integer, required: true, minimum: 0}
requirements:
  - {id: R1, text: "List products.", method: GET, path: /products, status: 200}
```

A brief must declare at least one resource and at least one requirement; requirement ids
are unique. Each requirement names the method, path and (optionally) status code that must
exist in the contract. `forge` attaches matching ids to operations as
`x-specforge-requirements`, and `verify --brief` recomputes coverage independently.

The generated contract contains, per resource: collection `GET` (pagination plus declared
filters) and `POST`, item `GET`, `PATCH` and `DELETE` (when requested), schemas `Name`,
`NameInput`, `NameUpdate`, `NameList`, RFC 9457 `Error`, and 400/401/404/409/422/500
responses where they apply.

## Validation rules

| Group | Examples |
|---|---|
| SPEC | `openapi` must be `3.1.x`, `info.title`/`info.version`, non-empty `paths`, ambiguous path templates |
| SCHEMA | type set, `nullable` rejected (3.0 leftover), required subset of properties, arrays need items, bounds |
| REF | local `$ref` resolves; external refs rejected |
| PARAM | path template vs declared parameters, `required: true`, duplicates, schema presence |
| OP/RESP | duplicate `operationId`, empty responses, missing response description, invalid status keys |
| SEC | undefined schemes, secured operation without 401, public operation declaring 401, unused scheme |
| COV | requirement without matching operation, required status missing, unknown requirement ids |

Findings carry `severity`, `code`, `location` (`#/paths/...`) and a message. Errors fail
the run; warnings fail only with `--strict`.

## Generated contract tests

For the sample shop brief SpecForge emits 45 tests: a happy path per operation, plus 401,
404 and 422 cases where the spec declares them. Each test asserts the expected status and
the top-level required fields/types of the JSON response. Requests carry
`X-SpecForge-Operation` and `X-SpecForge-Case` correlation headers.

`specforge/stub.py` runs `http.server.ThreadingHTTPServer` in a background thread and maps
`operationId` -> case -> declared status/body. `scripts/run_contract_stub.py` starts it and
runs the generated pytest file, so all 45 shop tests and all 20 library tests really issue
HTTP requests and assert statuses without external network. Without `SPECFORGE_BASE_URL`
the generated file still skips with an explicit reason, so it remains safe in CI.

## Limitations

- The validator is a structural checker, not a complete JSON Schema 2020-12 or OpenAPI
  3.1 validation suite. It does not validate `format` values, deep `$ref` circular
  semantics, `webhooks`, `callbacks`, links or OAuth flow internals.
- `$ref` support is local-only by design; external references are reported as errors.
- LLM enrichment is prose-only. Model output cannot alter paths, schemas, parameters or
  status codes; unknown operation ids are ignored and reported.
- Live Nebius inference requires `NEBIUS_API_KEY` and was not exercised in this
  environment (no key). `scripts/live_smoke.py` is ready and records the redacted request,
  raw response and latency; it exits `2` before any request when the key is missing.
- Offline enrichment is generated from the operations and requirements in the brief, so it
  covers every operation of any brief; it is deterministic and is not model output.
- The local stub validates status codes and shallow response shape, not business semantics.
- Contract tests assert status and shallow JSON shape, not business semantics.
- Brief input is YAML via PyYAML; a missing PyYAML is a hard error rather than a silent
  fallback.

## License

MIT — see `LICENSE`.
