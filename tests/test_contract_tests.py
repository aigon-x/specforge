import json  # noqa: F401

from specforge.contract_tests import (
    build_test_plan,
    generate_contract_tests,
    write_contract_tests,
)
from specforge.generator import generate_spec
from specforge.stub import build_stub_routes, stub_server


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
    assert "X-SpecForge-Operation" in source
    assert "case='test_createProduct_happy'" in source


def test_write_contract_tests_creates_runnable_file(shop_brief, tmp_path):
    spec = generate_spec(shop_brief)
    path, count = write_contract_tests(spec, tmp_path / "contract_tests", "shop")
    assert path.exists()
    assert count == 45
    assert path.name == "test_contract_shop.py"
    compile(path.read_text(encoding="utf-8"), str(path), "exec")


def test_generated_contract_tests_execute_against_local_stub(shop_brief, monkeypatch):
    spec = generate_spec(shop_brief)
    routes = build_stub_routes(spec)
    assert set(routes) == {
        test["operation"] for test in build_test_plan(spec)
    }
    with stub_server(routes) as stub:
        monkeypatch.setenv("SPECFORGE_BASE_URL", stub.base_url)
        monkeypatch.setenv("SPECFORGE_TOKEN", "stub-token")
        monkeypatch.setenv("SPECFORGE_TIMEOUT", "5")
        source = generate_contract_tests(spec, "out/openapi.yaml")
        namespace = {"__name__": "generated_contract_tests"}
        exec(compile(source, "<generated>", "exec"), namespace)
        tests = [name for name in namespace if name.startswith("test_")]
        assert len(tests) == 45
        for name in tests:
            namespace[name]()
        assert len(stub.records) == 45
        assert all(record.status < 500 for record in stub.records)
        assert len({record.case for record in stub.records}) == 45
        assert {record.operation for record in stub.records} == set(routes)


def test_stub_reports_unknown_case_as_404(shop_brief):
    spec = generate_spec(shop_brief)
    with stub_server(build_stub_routes(spec)) as stub:
        import urllib.error
        import urllib.request

        request = urllib.request.Request(
            stub.base_url + "/products",
            headers={"X-SpecForge-Operation": "noSuchOperation",
                     "X-SpecForge-Case": "noSuchCase"},
        )
        try:
            urllib.request.urlopen(request, timeout=5)
        except urllib.error.HTTPError as exc:
            assert exc.code == 404
        else:  # pragma: no cover - the stub must not answer 2xx
            raise AssertionError("stub must reject unknown routes with 404")


def test_malformed_path_item_is_ignored(shop_brief):
    spec = generate_spec(shop_brief)
    spec["paths"]["/broken"] = {"summary": "not an operation"}
    plan = build_test_plan(spec)
    assert len(plan) == 45
