# SpecForge

SpecForge turns a short product brief (YAML) into an OpenAPI 3.1 contract, audits the
contract with its own validator, and emits runnable pytest contract tests. An optional
LLM step (Nebius Token Factory, OpenAI-compatible) improves summaries, descriptions and
flags ambiguities; it can never add endpoints, fields or status codes. Without an API key
the whole pipeline runs on deterministic fixtures and says so in the output.

## What it does

- `forge` — brief -> `openapi.yaml`, `forge_report.json`, `contract_tests/`.
- `verify` — structural audit of an OpenAPI 3.1 document: version, schemas, local `$ref`,
  path parameters, operation ids, response descriptions, security contradictions and
  (with `--brief`) requirement coverage by method/path/status.
- `tests/` — 46 own tests, including negative cases (invalid brief, no key in live mode,
  broken references, missing 401, uncovered requirements).

No server is bundled. Generated contract tests run against any implementation that
matches the spec.

## Quickstart

```bash
cd specforge
python3 -m specforge forge --brief briefs/shop.yaml --out out/ --offline
python3 -m specforge verify out/openapi.yaml --brief briefs/shop.yaml
python3 -m pytest tests -q
```

Generated contract tests (skipped until a base URL is provided):

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
and fixtures otherwise. Every run prints `mode: OFFLINE ...` or `mode: LIVE ...`.

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
`meta-llama/Meta-Llama-3.1-8B-Instruct`), `NEBIUS_TIMEOUT`, `SPECFORGE_BASE_URL`,
`SPECFORGE_TOKEN`, `SPECFORGE_TIMEOUT`.

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
the top-level required fields/types of the JSON response. Without `SPECFORGE_BASE_URL`
every test is skipped with an explicit reason, so the suite is safe in CI.

## Limitations

- The validator is a structural checker, not a complete JSON Schema 2020-12 or OpenAPI
  3.1 validation suite. It does not validate `format` values, deep `$ref` circular
  semantics, `webhooks`, `callbacks`, links or OAuth flow internals.
- `$ref` support is local-only by design; external references are reported as errors.
- LLM enrichment is prose-only. Model output cannot alter paths, schemas, parameters or
  status codes; unknown operation ids are ignored and reported. Live mode was not exercised
  here (no API key); the shipped deterministic fixture is not a model output.
- Contract tests assert status and shallow JSON shape, not business semantics.
- Brief input is YAML via PyYAML; a missing PyYAML is a hard error rather than a silent
  fallback.

## License

MIT — see `LICENSE`.
