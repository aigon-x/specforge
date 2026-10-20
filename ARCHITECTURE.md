# Architecture

## Data flow

```
 brief.yaml
     |
     v
 [brief.py]  parse + validate (resources, fields, operations, requirements)
     |
     v
 [generator.py] + [schemas.py]  deterministic OpenAPI 3.1 document
     |                         paths, components, error model, security
     |<---- [nebius.py] + [enrich.py]  optional prose enrichment
     |        offline fixtures or Token Factory (OpenAI-compatible)
     v
 [validator.py] + [structure.py] + [refs.py]
     |        structure / schemas / $ref / parameters / operations
     |        security contradictions / requirement coverage
     v
 out/openapi.yaml   out/forge_report.json   out/contract_tests/test_contract_<slug>.py
                                                ^
                                     [contract_tests.py]
```

`verify` reuses the validator directly on any 3.1 document and optionally on a brief.

## Modules

| Module | Responsibility |
|---|---|
| `specforge/brief.py` | Dataclasses and strict YAML brief parser; collects every problem instead of failing on the first one. |
| `specforge/schemas.py` | Field -> JSON Schema mapping, per-resource Input/Update/List schemas, RFC 9457 `Error`, security schemes. |
| `specforge/generator.py` | Path/operation assembly, response matrix, requirement cross-references, deterministic `operationId`s. |
| `specforge/refs.py` | Local JSON Pointer resolution (`~0`, `~1`, percent decoding) and reference sweep. |
| `specforge/structure.py` | Document envelope and recursive schema checks. |
| `specforge/validator.py` | Parameters, operations, responses, security, coverage; `ValidationReport` with stable finding codes. |
| `specforge/nebius.py` | HTTP client: env config, timeout, retry with `Retry-After`, injectable transport, offline fixture provider. |
| `specforge/enrich.py` | Prompt construction, strict JSON parsing, prose-only application, ambiguity list. |
| `specforge/contract_tests.py` | Test plan from spec (happy/401/404/422), sample payloads from schemas, pytest source emission. |
| `specforge/cli.py` | `forge` / `verify`, report assembly, exit codes, mode banner. |

## Decisions

**Deterministic core, LLM at the edge.** The contract is produced by rules from the brief.
A model is allowed to rewrite human-readable summaries/descriptions and to list open
questions; it is never allowed to add or remove endpoints, parameters, fields or status
codes. This keeps generation reproducible, testable and cheap, and matches what a contract
reviewer can verify line by line. Alternative rejected: asking an LLM for the whole spec —
non-deterministic, unverifiable, and it hides missing requirements.

**Own validator instead of a library.** The brief required a dependency-free structural
validator, so `structure.py`/`validator.py` implement the subset SpecForge emits and the
common failure modes it must catch (`$ref` integrity, template/parameter agreement,
security/401 contradictions, coverage). Alternative rejected: wrapping
`openapi-spec-validator` — quick, but it would not express coverage or the security
contradiction rules, and would add a dependency to the verification path.

**Findings, not exceptions.** Validation returns a report with codes, locations and
severities. Errors fail the command; warnings are visible but non-blocking unless
`--strict`. This makes `verify` usable in CI and honest about soft issues.

**HTTP via stdlib.** `nebius.py` uses `urllib.request` with an injectable transport.
Retries apply to 408/409/425/429 and 5xx, honour `Retry-After` (capped at 30 s), and use
exponential backoff. 4xx client errors are not retried. The transport seam keeps retry
tests fast and offline. Alternative rejected: `requests` — convenient but unnecessary for
one POST endpoint, and harder to inject deterministically.

**Fixtures are explicit.** Without `NEBIUS_API_KEY`, or with `--offline`, completions come
from `specforge/fixtures/nebius_fixture.json`. Output and the JSON report both mark
`mode: offline`; the banner says no network call was made. The fixture is synthetic and
labelled as such — it is not presented as model output.

**Generated tests import nothing exotic.** They use `urllib.request`, read
`SPECFORGE_BASE_URL`/`SPECFORGE_TOKEN`, and skip with a reason when no base URL is set.
Assertions stay shallow (status, required keys, JSON types) because deeper business
assertions cannot be derived from a contract alone.

**Failure modes are explicit.** Invalid briefs exit `2` with every problem listed; invalid
contracts exit `1` after writing artefacts so they can be inspected; live mode without a
key exits `2` before any request. Enrichment failures degrade to the deterministic contract
with a warning in the report, never to a silent success.

## Security and safety

- API key comes only from the environment; it is never written to artefacts or logs.
- Enrichment output is parsed as JSON and applied to a whitelist of prose keys only.
- External `$ref` targets are rejected, so validation never fetches remote documents.
- Generated test payloads contain no secrets; the optional token is read from env at run
  time.

## Runtime and versions

Python 3.12, PyYAML 6.0.2, pytest 9.0.3. No other runtime dependencies. Files are plain
YAML/JSON/Python; no database, server or container is required.
