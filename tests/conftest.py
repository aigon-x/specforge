import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from specforge import load_brief  # noqa: E402


@pytest.fixture(scope="session")
def shop_brief():
    return load_brief(ROOT / "briefs" / "shop.yaml")


def minimal_brief() -> dict:
    return {
        "name": "Tiny API",
        "version": "1.0.0",
        "resources": [
            {
                "name": "Item",
                "path": "/items",
                "operations": ["list", "create", "get"],
                "fields": {
                    "id": {"type": "string", "read_only": True},
                    "name": {"type": "string", "required": True},
                },
            }
        ],
        "requirements": [
            {"id": "R1", "text": "List items.", "method": "GET", "path": "/items", "status": 200}
        ],
    }
