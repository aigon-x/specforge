import json  # noqa: F401

from specforge.contract_tests import (
    build_test_plan,
    generate_contract_tests,
    write_contract_tests,
)
from specforge.generator import generate_spec


def test_plan_has_happy_and_error_cases(shop_brief):
    plan = build_test_plan(generate_spec(shop_brief))
    names = {test["name"] for test in plan}
    assert len(plan) == 45
    assert {
        "test_listProducts_happy",
        "test_createProduct_happy",
        "test_createProduct_401",
        "test_getProduct_404",
        "test_createOrder_422",
    }.issubset(names)
    create = next(test for test in plan if test["name"] == "test_createProduct_happy")
    assert create["expect"] == 201
    assert create["body"]["name"] == "sample"
    invalid = next(test for test in plan if test["name"] == "test_createOrder_422")
    assert invalid["body"] == {}
    unauthorised = next(test for test in plan if test["name"] == "test_getOrder_401")
    assert unauthorised["auth"] is False


def test_generated_source_compiles_and_is_skipped_without_base_url(shop_brief):
    source = generate_contract_tests(generate_spec(shop_brief), "out/openapi.yaml")
    compile(source, "<generated>", "exec")
    namespace = {}
    exec(source, namespace)
    assert namespace["BASE_URL"] == ""
    assert namespace["AUTH_HEADER"] == "Authorization"
    assert "test_createProduct_401" in source
    assert "pytest.mark.skipif(not BASE_URL" in source
    assert "00000000-0000-4000-8000-000000000000" in source


def test_write_contract_tests_creates_runnable_file(shop_brief, tmp_path):
    spec = generate_spec(shop_brief)
    path, count = write_contract_tests(spec, tmp_path / "contract_tests", "shop")
    assert path.exists()
    assert count == 45
    assert path.name == "test_contract_shop.py"
    compile(path.read_text(encoding="utf-8"), str(path), "exec")


def test_malformed_path_item_is_ignored(shop_brief):
    spec = generate_spec(shop_brief)
    spec["paths"]["/broken"] = {"summary": "not an operation"}
    plan = build_test_plan(spec)
    assert len(plan) == 45
