import json

import pytest

from specforge import NebiusConfigError, NebiusError, parse_brief, validate_spec
from specforge.enrich import (
    apply_enrichment,
    build_messages,
    enrich_spec,
    parse_payload,
)
from specforge.errors import FixtureError
from specforge.generator import generate_spec
from specforge.nebius import NebiusClient, _TransportError

from conftest import minimal_brief


def _body(content='{"operations": {}, "ambiguities": []}', model="nebius/test-model"):
    return json.dumps({"model": model, "choices": [{"message": {"content": content}}]})


class FakeTransport:
    def __init__(self, statuses, body=None):
        self.statuses = list(statuses)
        self.calls = []
        self.body = body

    def __call__(self, payload):
        self.calls.append(payload)
        status = self.statuses.pop(0) if len(self.statuses) > 1 else self.statuses[0]
        if self.body is not None:
            return status, {"Content-Type": "application/json"}, self.body
        return status, {"Content-Type": "application/json"}, _body()


def _client(statuses, **kwargs):
    transport = FakeTransport(statuses)
    client = NebiusClient(api_key="test-key", transport=transport, backoff=0.0, **kwargs)
    return client, transport


def test_offline_mode_is_deterministic_and_never_calls_transport():
    def forbidden(payload):
        raise AssertionError("transport must not be used in offline mode")

    brief = parse_brief(minimal_brief())
    messages = build_messages(brief, generate_spec(brief))
    client = NebiusClient(offline=True, transport=forbidden)
    first = client.complete(messages, task="enrich")
    second = client.complete(messages, task="enrich")
    assert first.content == second.content
    assert first.mode == "offline"
    assert first.attempts == 0
    assert first.model.startswith("fixture:")
    assert json.loads(first.content)["ambiguities"]


def test_offline_fixture_rejects_unknown_task():
    client = NebiusClient(offline=True)
    with pytest.raises(FixtureError):
        client.complete([], task="no-such-task")


def test_live_mode_without_key_is_a_config_error(monkeypatch):
    monkeypatch.delenv("NEBIUS_API_KEY", raising=False)
    with pytest.raises(NebiusConfigError):
        NebiusClient.from_env(mode="live")


def test_default_model_is_nemotron_and_env_overrides(monkeypatch):
    monkeypatch.delenv("NEBIUS_MODEL", raising=False)
    assert NebiusClient.from_env(mode="offline").model == (
        "nvidia/Llama-3.1-Nemotron-70B-Instruct"
    )
    monkeypatch.setenv("NEBIUS_MODEL", "nvidia/Some-Other-Nemotron")
    assert NebiusClient.from_env(mode="offline").model == "nvidia/Some-Other-Nemotron"


def test_auto_mode_falls_back_to_offline_without_key(monkeypatch):
    monkeypatch.delenv("NEBIUS_API_KEY", raising=False)
    client = NebiusClient.from_env(mode="auto")
    assert client.offline is True
    assert client.describe()["mode"] == "offline"


def test_retries_on_500_and_429_then_succeeds():
    client, transport = _client([500, 429, 200], max_retries=2)
    completion = client.complete([{"role": "user", "content": "hi"}])
    assert completion.attempts == 3
    assert completion.mode == "live"
    assert len(transport.calls) == 3
    assert transport.calls[0]["model"] == client.model


def test_retry_budget_exhaustion_is_reported():
    client, transport = _client([503], max_retries=1)
    with pytest.raises(NebiusError) as excinfo:
        client.complete([])
    assert excinfo.value.kind == "retry_exhausted"
    assert excinfo.value.attempts == 2
    assert len(transport.calls) == 2


def test_client_error_is_not_retried():
    client, transport = _client([401], max_retries=3)
    with pytest.raises(NebiusError) as excinfo:
        client.complete([])
    assert excinfo.value.kind == "http"
    assert excinfo.value.attempts == 1
    assert len(transport.calls) == 1


def test_invalid_completion_payload_is_rejected():
    transport = FakeTransport([200], body="not-json")
    client = NebiusClient(api_key="test-key", transport=transport, backoff=0.0)
    with pytest.raises(NebiusError) as excinfo:
        client.complete([])
    assert excinfo.value.kind == "invalid_response"


class TimeoutTransport:
    def __init__(self, failures):
        self.failures = failures
        self.calls = 0

    def __call__(self, payload):
        self.calls += 1
        if self.failures:
            self.failures -= 1
            raise _TransportError("timed out")
        return 200, {"Content-Type": "application/json"}, _body()


def test_transport_timeouts_are_retried():
    transport = TimeoutTransport(2)
    client = NebiusClient(api_key="k", transport=transport, backoff=0.0, max_retries=2)
    completion = client.complete([])
    assert completion.attempts == 3
    assert transport.calls == 3


def test_transport_timeout_exhaustion_is_reported():
    transport = TimeoutTransport(5)
    client = NebiusClient(api_key="k", transport=transport, backoff=0.0, max_retries=1)
    with pytest.raises(NebiusError) as excinfo:
        client.complete([])
    assert excinfo.value.kind == "retry_exhausted"
    assert excinfo.value.attempts == 2
    assert transport.calls == 2


def test_enrichment_parses_fenced_json():
    payload = parse_payload('```json\n{"operations": {"a": {"summary": "s"}}}\n```')
    assert payload["operations"]["a"]["summary"] == "s"


def test_enrichment_rejects_non_json():
    with pytest.raises(NebiusError) as excinfo:
        parse_payload("I cannot help with that.")
    assert excinfo.value.kind == "invalid_json"


def test_enrichment_cannot_change_contract_semantics():
    spec = generate_spec(parse_brief(minimal_brief()))
    paths_before = _semantics(spec)
    payload = {
        "operations": {
            "listItems": {"summary": "List items", "description": "Better prose."},
            "ghostOperation": {"summary": "Ignore me", "description": "Nope."},
        },
        "ambiguities": ["Money units are unspecified."],
    }
    meta = apply_enrichment(spec, payload, model="test-model", mode="offline")
    assert meta["applied_operations"] == ["listItems"]
    assert meta["ignored_operations"] == ["ghostOperation"]
    assert _semantics(spec) == paths_before
    assert spec["paths"]["/items"]["get"]["description"] == "Better prose. Covers: R1."
    assert validate_spec(spec).errors == []


def _spec_operation_ids(spec):
    ids = set()
    for item in spec.get("paths", {}).values():
        for operation in item.values():
            if isinstance(operation, dict) and "operationId" in operation:
                ids.add(operation["operationId"])
    return ids


def test_offline_fixture_is_derived_from_the_shop_brief(shop_brief):
    spec = generate_spec(shop_brief)
    client = NebiusClient(offline=True)
    completion = client.complete(build_messages(shop_brief, spec), task="enrich")
    payload = json.loads(completion.content)
    assert set(payload["operations"]) == _spec_operation_ids(spec)
    assert len(payload["operations"]) == 15
    ambiguities = json.dumps(payload["ambiguities"])
    assert "price_cents" not in ambiguities
    assert "Order" not in ambiguities


def test_offline_fixture_covers_a_different_brief(library_brief, shop_brief):
    spec = generate_spec(library_brief)
    client = NebiusClient(offline=True)
    messages = build_messages(library_brief, spec)
    payload = json.loads(client.complete(messages, task="enrich").content)
    expected = _spec_operation_ids(spec)
    declared = sum(len(resource.operations) for resource in library_brief.resources)
    assert set(payload["operations"]) == expected
    assert len(payload["operations"]) == len(expected) == declared == 7
    assert set(payload["operations"]) != _spec_operation_ids(generate_spec(shop_brief))
    meta = enrich_spec(spec, library_brief, client)
    assert sorted(meta["applied_operations"]) == sorted(expected)
    assert meta["ignored_operations"] == []
    assert validate_spec(spec, library_brief).coverage["ratio"] == 1.0


def _semantics(spec):
    clone = json.loads(json.dumps(spec))
    for item in clone["paths"].values():
        for operation in item.values():
            if isinstance(operation, dict):
                for key in ("summary", "description", "x-specforge-enriched"):
                    operation.pop(key, None)
    return json.dumps(clone["paths"], sort_keys=True)
