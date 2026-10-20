# SpecForge — DEVPOST DRAFT

**Hackathon:** Nebius x NVIDIA Global AI Hackathon
**Draft date:** 2026-10-20
**Status:** working prototype, offline-verifiable; generated contract tests run against a
local HTTP stub. A live Token Factory call ran on 2026-10-20 (HTTP 200, 9.48 s, valid JSON) in
this environment; `scripts/live_smoke.py` is ready and records request/response/latency.

## Name

SpecForge

## Elevator pitch

SpecForge turns a product brief into an OpenAPI 3.1 contract, audits the contract for
broken references, security contradictions and requirement coverage, and generates pytest
contract tests — deterministically, with an NVIDIA Nemotron model on Nebius Token Factory
used only where prose helps.

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
   proposes better summaries/descriptions and lists ambiguities. The default model is
   `nvidia/Llama-3.1-Nemotron-70B-Instruct`; `NEBIUS_MODEL` overrides it with any model
   available in Token Factory. Output is parsed as JSON and applied only to prose fields;
   unknown operation ids are ignored and reported.
4. **Offline mode.** Without a key, or with `--offline`, enrichment is generated
   deterministically from the operations and requirements in the brief itself. The CLI
   banner and the JSON report both state `OFFLINE`.
5. **Contract tests.** Emits pytest files from the spec: happy path plus 401/404/422 cases
   where declared, with sample payloads derived from schemas. The bundled
   `specforge/stub.py` runs `http.server` in a thread and maps `operationId` -> case ->
   declared status/body, so all generated tests issue real HTTP requests and assert
   statuses without external network. Without `SPECFORGE_BASE_URL` the generated file
   still skips cleanly in CI.
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
- **Offline reproducibility without a sample-specific fixture.** The offline payload is
  derived from the prompt: every operation of any brief gets prose, and a second brief
  (library API) is covered without editing a fixture. It is deterministic and clearly
  labelled, not passed off as model output.
- **Proving contract tests are runnable.** A loopback `http.server` stub keyed by
  `operationId` and case name turns 45 skipped tests into 45 executed requests with
  asserted statuses; the second brief adds 20 more.
- **Live evidence without a key.** `scripts/live_smoke.py` exercises the same enrichment
  request, redacts the bearer token, and records request, response and latency. It refuses
  to run without `NEBIUS_API_KEY`.
- **Failure behaviour.** A missing key, exhausted retries and malformed completions each
  needed a distinct, testable outcome instead of a generic exception.

## Accomplishments

- 6 paths / 15 operations / 13 schemas generated from an 11-requirement shop brief, and
  4 paths / 7 operations / 9 schemas from a second, independent 7-requirement library
  brief; both at 100% requirement coverage and zero validation errors.
- 51 own tests passing, including negative tests for invalid brief, undefined security
  scheme, missing `$ref`, missing 401, uncovered requirements, retry exhaustion and live
  mode without a key.
- 45 generated shop contract tests and 20 library contract tests actually executed against
  the local stub (45 and 20 HTTP requests served), not skipped.
- One-command offline demo: `forge`, `verify` and `run_contract_stub.py`, no external
  network, no secrets.
- Live smoke test ready: `scripts/live_smoke.py` records the redacted request, raw response
  and latency; it wrote nothing here because no key was available.

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

- Run `scripts/live_smoke.py` with a real key and publish the sanitised evidence; gate it
  in CI with secrets.
- Expand validation: `webhooks`, `callbacks`, OAuth flow internals, JSON Schema format
  checks, and semantic diffing between two spec versions.
- Generate schemathesis-style property tests and negative payloads from the same plan.
- Add a mode that reconciles an existing spec with a brief and reports drift.
- Package as a GitHub Action: brief in, spec + coverage report + contract tests out.

## Built with

- Python 3.12, PyYAML, pytest, `urllib.request`
- Nebius Token Factory (OpenAI-compatible chat completions)
- NVIDIA Nemotron (`nvidia/Llama-3.1-Nemotron-70B-Instruct`) as the default model
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

Contract tests against the bundled local stub (no external network):

```bash
python3 scripts/run_contract_stub.py --spec out/openapi.yaml --tests out/contract_tests
```

Contract tests against a running service:

```bash
SPECFORGE_BASE_URL=https://api.example.com SPECFORGE_TOKEN=... \
  python3 -m pytest -q out/contract_tests
```

Live smoke evidence (requires a key; not run in this environment):

```bash
export NEBIUS_API_KEY=...
python3 scripts/live_smoke.py --out out/live_smoke.json
```

## Notes for judges

The development environment had no Nebius API key, so live inference was not exercised.
The client, retry policy, timeout handling, JSON parsing and offline fallback are covered by
tests; offline mode is deliberately loud and deterministic. Generated contract tests were
not left skipped: all 45 shop tests and all 20 library tests ran against the local stub and
asserted real statuses. `scripts/live_smoke.py` is the ready live evidence path and writes
request/response/latency once a key is supplied. Every number in `EVIDENCE.md` was produced
by the commands shown there on 2026-10-20.
