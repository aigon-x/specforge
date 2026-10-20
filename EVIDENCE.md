# Evidence

**Date:** 2026-10-20
**Host:** local-aigon (Linux)
**Interpreter:** Python 3.12.3 at `/usr/bin/python3`
**Libraries:** PyYAML 6.0.2, pytest 9.0.3
**Network:** none. `NEBIUS_API_KEY` was unset/empty for every command below, and offline
mode was requested explicitly. No external API was called and no key is present in the
repository.

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
............................................                             [100%]
46 passed in 0.76s
```

Coverage of the required negative cases:

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

## 2. Generate the contract (offline)

Command:

```bash
rm -rf out
NEBIUS_API_KEY= /usr/bin/python3 -m specforge forge --brief briefs/shop.yaml --out out/ --offline
```

Output:

```
SpecForge 1.0.0
brief: briefs/shop.yaml
mode: OFFLINE — deterministic fixtures, no network call (model label: fixture:meta-llama/Meta-Llama-3.1-8B-Instruct)
spec: out/openapi.yaml — paths=6 operations=15 schemas=13
validation: 0 errors, 0 warnings
coverage: 11/11 requirements (100.0%)
contract tests: out/contract_tests/test_contract_shop.py (45 tests)
ambiguities: 3 (see out/forge_report.json)
report: out/forge_report.json
```

## 3. Verify the contract

Command:

```bash
/usr/bin/python3 -m specforge verify out/openapi.yaml --brief briefs/shop.yaml
```

Output:

```
verify out/openapi.yaml (openapi 3.1.0) — paths=6 operations=15 schemas=13
coverage: 11/11 requirements (100.0%)
OK: 0 errors, 0 warnings
```

## 4. Generated contract tests are runnable

Command:

```bash
NEBIUS_API_KEY= /usr/bin/python3 -m pytest -q out/contract_tests
```

Output:

```
45 skipped in 0.47s
```

The skip is explicit: `SPECFORGE_BASE_URL is not set`. No server was started, so no false
green is claimed.

## 5. Negative paths

Brief without requirements:

```bash
/usr/bin/python3 -m specforge forge --brief briefs/invalid-missing-requirements.yaml --out out/ --offline
```

```
error: briefs/invalid-missing-requirements.yaml: requirements: at least one requirement is required
exit=2
```

Live mode without a key:

```bash
env -u NEBIUS_API_KEY /usr/bin/python3 -m specforge forge --brief briefs/shop.yaml --out out/ --live
```

```
error: live mode requires NEBIUS_API_KEY; use --offline for fixture mode
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
```

(The temporary `out/_negative` directory was removed after the run.)

## 6. Artefact hashes

```bash
sha256sum out/openapi.yaml briefs/shop.yaml
```

```
4a4cea1dee6056fc58685b8b8f0e6c63af1ebb1137d339a3498ce975bb8976ec  out/openapi.yaml
0277fa2dc22b3da4e31105a667deb09f13f9afe24d9306ad5e012d855b28bd74  briefs/shop.yaml
```

## 7. What the generated contract contains

- Paths: `/products`, `/products/{id}`, `/orders`, `/orders/{id}`, `/customers`,
  `/customers/{id}`.
- Operations: 15 (5 per resource).
- Schemas: 13 — `Error`, plus `Product`, `Order`, `Customer` and their `Input`, `Update`,
  `List` variants.
- Security: bearer auth globally; every operation declares 401.
- Requirement annotations: `x-specforge-requirements` per operation; coverage verified
  independently by `verify --brief`.
- Enrichment: 15/15 operations received fixture prose; 3 ambiguities recorded in
  `out/forge_report.json`; contract semantics unchanged (asserted by test).

## 8. Replay

```bash
cd /opt/PROD/products/monai/monai-hackathons/work/hakaton_devpost_nebius-x-nvidia-global-ai-hackathon/project
NEBIUS_API_KEY= /usr/bin/python3 -m pytest tests -q
rm -rf out
NEBIUS_API_KEY= /usr/bin/python3 -m specforge forge --brief briefs/shop.yaml --out out/ --offline
/usr/bin/python3 -m specforge verify out/openapi.yaml --brief briefs/shop.yaml
NEBIUS_API_KEY= /usr/bin/python3 -m pytest -q out/contract_tests
sha256sum out/openapi.yaml
```

All outputs above are reproducible from a clean `out/` directory; generation is
deterministic, except that the report embeds no timestamps or random values.

## 9. Cleanup

Test runs used pytest temporary directories, which pytest removes automatically. The only
files written outside the project directory were those ephemeral pytest scratch files.
`__pycache__` directories are interpreter bytecode caches and contain no project state.
