from conftest import minimal_brief
from specforge import parse_brief, validate_spec
from specforge.generator import generate_spec, spec_stats


def _operations(spec):
    return [
        (method, op)
        for item in spec["paths"].values()
        for method, op in item.items()
    ]


def test_generated_spec_is_valid_and_complete(shop_brief):
    spec = generate_spec(shop_brief)
    report = validate_spec(spec, shop_brief)
    assert report.errors == []
    assert report.coverage["ratio"] == 1.0
    assert report.coverage["covered"] == 11
    assert spec["openapi"] == "3.1.0"
    assert spec_stats(spec) == {"paths": 6, "operations": 15, "schemas": 13}


def test_operation_ids_are_unique_and_secured(shop_brief):
    spec = generate_spec(shop_brief)
    operations = _operations(spec)
    ids = [op["operationId"] for _, op in operations]
    assert len(ids) == 15
    assert len(set(ids)) == 15
    assert spec["security"] == [{"bearerAuth": []}]
    assert spec["components"]["securitySchemes"]["bearerAuth"]["scheme"] == "bearer"
    assert all("401" in op["responses"] for _, op in operations)


def test_every_response_has_a_description(shop_brief):
    spec = generate_spec(shop_brief)
    for _, op in _operations(spec):
        for code, response in op["responses"].items():
            assert response["description"].strip(), f"{op['operationId']} {code}"


def test_requirements_are_attached_to_operations(shop_brief):
    spec = generate_spec(shop_brief)
    assert spec["paths"]["/products"]["post"]["x-specforge-requirements"] == ["R2"]
    assert spec["paths"]["/orders"]["post"]["x-specforge-requirements"] == ["R7", "R9"]


def test_api_key_auth_uses_configured_header():
    payload = minimal_brief()
    payload["auth"] = {"type": "api_key", "header": "X-Service-Key"}
    spec = generate_spec(parse_brief(payload))
    scheme = spec["components"]["securitySchemes"]["apiKeyAuth"]
    assert scheme["type"] == "apiKey"
    assert scheme["name"] == "X-Service-Key"
    assert spec["security"] == [{"apiKeyAuth": []}]


def test_open_brief_has_no_security_and_no_401():
    spec = generate_spec(parse_brief(minimal_brief()))
    assert "security" not in spec
    assert "securitySchemes" not in spec["components"]
    assert all("401" not in op["responses"] for _, op in _operations(spec))
