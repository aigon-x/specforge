import copy

import pytest

from conftest import minimal_brief
from specforge import BriefError, parse_brief


def test_shop_brief_parses(shop_brief):
    assert shop_brief.name == "Shop API"
    assert len(shop_brief.resources) == 3
    assert len(shop_brief.requirements) == 11
    assert shop_brief.secured is True
    assert [resource.name for resource in shop_brief.resources] == ["Product", "Order", "Customer"]


def test_brief_without_requirements_is_rejected():
    payload = minimal_brief()
    payload["requirements"] = []
    with pytest.raises(BriefError) as excinfo:
        parse_brief(payload)
    assert any("requirements" in problem for problem in excinfo.value.problems)


def test_duplicate_requirement_id_is_rejected():
    payload = minimal_brief()
    payload["requirements"].append(dict(payload["requirements"][0]))
    with pytest.raises(BriefError) as excinfo:
        parse_brief(payload)
    assert any("duplicate" in problem for problem in excinfo.value.problems)


def test_unknown_field_type_is_rejected():
    payload = copy.deepcopy(minimal_brief())
    payload["resources"][0]["fields"]["name"]["type"] = "currency"
    with pytest.raises(BriefError) as excinfo:
        parse_brief(payload)
    assert any("unsupported type" in problem for problem in excinfo.value.problems)


def test_plain_string_field_shorthand_is_accepted():
    payload = copy.deepcopy(minimal_brief())
    payload["resources"][0]["fields"]["sku"] = "string"
    brief = parse_brief(payload)
    assert brief.resources[0].fields["sku"].type == "string"
