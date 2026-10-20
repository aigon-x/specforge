# SpecForge — DEVPOST DRAFT

**Hackathon:** Nebius x NVIDIA Global AI Hackathon
**Draft date:** 2026-10-20
**Status:** working prototype, offline-verifiable; live Token Factory call requires a key.

## Name

SpecForge

## Elevator pitch

SpecForge turns a product brief into an OpenAPI 3.1 contract, audits the contract for
broken references, security contradictions and requirement coverage, and generates pytest
contract tests — deterministically, with a Nebius Token Factory model used only where
prose helps.

## Inspiration

API contracts usually start as a paragraph and end as YAML written by hand. The expensive
failures are boring: a `$ref` that points nowhere, an operation marked as secured with no
401, a requirement nobody implemented, tests that check only that the server is up. We
wanted a tool that treats the brief as the source of truth and refuses to declare success
until the contract is internally consistent and every requirement is covered by a concrete
method, path and status code.

The hackathon constraint made the design sharper: an agent that calls an inference API has
to behave sensibly when the key is missing, the API is rate-limited or the model returns
malformed JSON. SpecForge therefore has a deterministic core and treats the model as an
optional, replaceable edge.

## What it does

1. **Brief -> contract.** Reads a YAML brief (resources, fields, operations, auth,
   requirement ids) and emits OpenAPI 3.1: paths, request/response schemas, RFC 9457 error
   responses, pagination and filters, bearer or API-key security.
2. **Own validator.** Checks the document envelope, schema keywords, local `$ref`
   resolution, path-template/parameter agreement, unique operation ids, response
   descriptions, and security contradictions such as a secured operation without a 401 or a
   public operation that still declares 401. With `--brief` it recomputes requirement
   coverage by method, path and status.
3. **Nebius Token Factory enrichment.** An OpenAI-compatible client (env
   `NEBIUS_API_KEY`, configurable base URL/model, timeout, retries with `Retry-After`)
   proposes better summaries/descriptions and lists ambiguities. Output is parsed as JSON
   and applied only to prose fields; unknown operation ids are ignored and reported.
4. **Offline mode.** Without a key, or with `--offline`, deterministic fixtures drive the
   same pipeline. The CLI banner and the JSON report both state `OFFLINE`.
5. **Contract tests.** Emits pytest files from the spec: happy path plus 401/404/422 cases
   where declared, with sample payloads derived from schemas. Tests skip cleanly until
   `SPECFORGE_BASE_URL` is set.
6. **Report.** `forge_report.json` records mode, model label, enrichment results,
   ambiguities, validation findings, coverage and artefact hashes.

## How we built it

- **Python 3.12 + PyYAML only.** No web framework, no OpenAPI library, no HTTP client
  dependency. The validator, generator and test emitter are plain modules.
- **Deterministic generator.** Rules map brief resources to paths and schemas. Operation
  ids, response matrices and requirement cross-references are stable across runs.
- **Separate validator.** `structure.py` and `validator.py` produce findings with stable
  codes (`REF-NOT-FOUND`, `SEC-NO-401`, `COV-UNMAPPED`, ...), severities and JSON-pointer
  locations. Errors fail the run; warnings fail only with `--strict`.
- **Dependency-injected HTTP.** `nebius.py` wraps `urllib.request`; retries cover
  429/5xx/timeouts with exponential backoff and `Retry-After`, and the transport is
  injectable, which is how retry behaviour is tested without network.
- **Strict JSON handling.** Fenced or plain JSON is accepted; anything else raises
  `invalid_json`, the CLI degrades to the deterministic contract and records the warning.
- **Thin, honest artefacts.** The generated pytest file contains only the tests implied by
  the spec and a small stdlib request helper.

## Challenges

- **Making an LLM safe for contract work.** The model must improve prose without changing
  semantics. We solved it with a whitelist of writable keys and an equality test proving
  paths and schemas are untouched by enrichment.
- **Useful validation without a full JSON Schema engine.** Implementing the subset that
  catches real failures took more care than wrapping a library, especially around path
  templates, `$ref` integrity and security/401 consistency.
- **Offline reproducibility.** Fixtures had to be deterministic and clearly labelled, not
  passed off as model output. Operation-id naming had to be stable so fixtures can target
  operations by id.
- **Failure behaviour.** A missing key, exhausted retries and malformed completions each
  needed a distinct, testable outcome instead of a generic exception.

## Accomplishments

- 6 paths / 15 operations / 13 schemas generated from an 11-requirement brief, with 100%
  requirement coverage and zero validation errors.
- 46 own tests passing, including negative tests for invalid brief, undefined security
  scheme, missing `$ref`, missing 401, uncovered requirements, retry exhaustion and live
  mode without a key.
- 45 generated contract tests that import, compile and skip deterministically in CI.
- One-command offline demo: `forge` and `verify`, no network, no secrets.

## What we learned

- Most contract defects are structural and cheap to detect; an LLM is not needed for them
  and is a poor place to put the decision.
- Coverage must be computed against declared requirement ids and status codes, not inferred
  from prose, otherwise it becomes a confidence score with no evidence.
- Retry logic is easy to claim and easy to get wrong; injecting the transport is the
  cheapest way to prove it.
- An explicit offline mode with a loud banner is a feature, not a workaround: reviewers can
  reproduce every result without credentials.

## What's next

- Replace the fixture with recorded Token Factory responses (sanitised) and add a live smoke
  test gated by CI secrets.
- Expand validation: `webhooks`, `callbacks`, OAuth flow internals, JSON Schema format
  checks, and semantic diffing between two spec versions.
- Generate schemathesis-style property tests and negative payloads from the same plan.
- Add a mode that reconciles an existing spec with a brief and reports drift.
- Package as a GitHub Action: brief in, spec + coverage report + contract tests out.

## Built with

- Python 3.12, PyYAML, pytest, `urllib.request`
- Nebius Token Factory (OpenAI-compatible chat completions)
- OpenAPI 3.1, JSON Schema 2020-12, RFC 9457 problem details

No framework, database or container is required. The code runs on CPU; Token Factory
inference is remote and optional.

## Links

- Repository: `https://github.com/aigon-x/specforge`
- Demo video: `<VIDEO_URL_PLACEHOLDER>`
- Architecture: `ARCHITECTURE.md`
- Evidence: `EVIDENCE.md`

## How to run

```bash
cd project
python3 -m specforge forge --brief briefs/shop.yaml --out out/ --offline
python3 -m specforge verify out/openapi.yaml --brief briefs/shop.yaml
python3 -m pytest tests -q
```

Live enrichment (requires a Nebius Token Factory key):

```bash
export NEBIUS_API_KEY=...
python3 -m specforge forge --brief briefs/shop.yaml --out out/ --live
```

Contract tests against a running service:

```bash
SPECFORGE_BASE_URL=https://api.example.com SPECFORGE_TOKEN=... \
  python3 -m pytest -q out/contract_tests
```

## Notes for judges

The development environment had no Nebius API key, so live inference was not exercised.
The client, retry policy, timeout handling, JSON parsing and offline fallback are covered by
tests; offline mode is deliberately loud and deterministic. Every number in `EVIDENCE.md`
was produced by the commands shown there on 2026-10-20.
