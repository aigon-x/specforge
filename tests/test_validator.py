import copy

from specforge import validate_spec
from specforge.generator import generate_spec


def _codes(report):
    return {finding.code for finding in report.errors}


def _warnings(report):
    return {finding.code for finding in report.warnings}


def _broken(spec, mutate):
    clone = copy.deepcopy(spec)
    mutate(clone)
    return clone


def test_missing_ref_target_is_an_error(shop_brief):
    spec = generate_spec(shop_brief)
    broken = _broken(
        spec,
        lambda doc: doc["components"]["schemas"]["Product"]["properties"].update(
            {"name": {"$ref": "#/components/schemas/Missing"}}
        ),
    )
    report = validate_spec(broken)
    assert "REF-NOT-FOUND" in _codes(report)
    assert not report.ok()


def test_undefined_security_scheme_is_an_error(shop_brief):
    spec = generate_spec(shop_brief)
    broken = _broken(spec, lambda doc: doc.update({"security": [{"magic": []}]}))
    report = validate_spec(broken)
    assert "SEC-SCHEME-MISSING" in _codes(report)


def test_secured_operation_without_401_is_an_error(shop_brief):
    spec = generate_spec(shop_brief)
    broken = _broken(spec, lambda doc: doc["paths"]["/products"]["post"]["responses"].pop("401"))
    report = validate_spec(broken)
    assert "SEC-NO-401" in _codes(report)
    finding = next(item for item in report.errors if item.code == "SEC-NO-401")
    assert finding.location == "#/paths//products/post" or "createProduct" in finding.location


def test_undeclared_path_parameter_is_an_error(shop_brief):
    spec = generate_spec(shop_brief)
    broken = _broken(spec, lambda doc: doc["paths"]["/products/{id}"]["get"].pop("parameters"))
    report = validate_spec(broken)
    assert "PARAM-UNDECLARED" in _codes(report)


def test_uncovered_requirement_is_an_error(shop_brief):
    spec = generate_spec(shop_brief)
    broken = _broken(spec, lambda doc: doc["paths"].pop("/orders"))
    report = validate_spec(broken, shop_brief)
    assert "COV-UNMAPPED" in _codes(report)
    assert report.coverage["ratio"] < 1.0
    assert "R6" in report.coverage["uncovered"]
    assert report.coverage["covered"] == 8


def test_missing_status_for_requirement_is_an_error(shop_brief):
    spec = generate_spec(shop_brief)
    broken = _broken(spec, lambda doc: doc["paths"]["/orders"]["post"]["responses"].pop("422"))
    report = validate_spec(broken, shop_brief)
    assert "COV-STATUS" in _codes(report)
    assert "R9" in report.coverage["uncovered"]


def test_wrong_openapi_version_is_an_error(shop_brief):
    spec = generate_spec(shop_brief)
    broken = _broken(spec, lambda doc: doc.update({"openapi": "3.0.3"}))
    report = validate_spec(broken)
    assert "SPEC-VERSION" in _codes(report)


def test_nullable_keyword_is_rejected(shop_brief):
    spec = generate_spec(shop_brief)
    broken = _broken(
        spec,
        lambda doc: doc["components"]["schemas"]["Product"]["properties"]["name"].update(
            {"nullable": True}
        ),
    )
    report = validate_spec(broken)
    assert "SCHEMA-NULLABLE-3_0" in _codes(report)


def test_duplicate_operation_id_is_an_error(shop_brief):
    spec = generate_spec(shop_brief)
    broken = _broken(
        spec,
        lambda doc: doc["paths"]["/products"]["post"].update({"operationId": "listProducts"}),
    )
    report = validate_spec(broken)
    assert "OP-DUPLICATE-ID" in _codes(report)


def test_missing_response_description_is_an_error(shop_brief):
    spec = generate_spec(shop_brief)
    broken = _broken(
        spec, lambda doc: doc["paths"]["/products"]["get"]["responses"]["200"].update(
            {"description": ""}
        ),
    )
    report = validate_spec(broken)
    assert "RESP-NO-DESCRIPTION" in _codes(report)


def test_ambiguous_path_template_is_an_error(shop_brief):
    spec = generate_spec(shop_brief)
    broken = _broken(
        spec, lambda doc: doc["paths"].update({"/products/{product_id}": {"get": {}}})
    )
    report = validate_spec(broken)
    assert "SPEC-PATH-AMBIGUOUS" in _codes(report)


def test_public_operation_with_401_is_a_warning(shop_brief):
    spec = generate_spec(shop_brief)
    broken = _broken(spec, lambda doc: doc["paths"]["/products"]["get"].update({"security": []}))
    report = validate_spec(broken)
    assert "SEC-PUBLIC-401" in _warnings(report)
    assert report.ok() is True
