#!/usr/bin/env python3
"""Run a generated contract-test file against the bundled local HTTP stub.

No external network is used: the stub listens on 127.0.0.1 and returns the
status/body declared by the OpenAPI document for each operationId + case.

Example:
    python3 scripts/run_contract_stub.py --spec out/openapi.yaml \
        --tests out/contract_tests
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from specforge.stub import build_stub_routes, stub_server  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", default=str(ROOT / "out" / "openapi.yaml"))
    parser.add_argument("--tests", default=str(ROOT / "out" / "contract_tests"))
    args = parser.parse_args(argv)

    spec = yaml.safe_load(Path(args.spec).read_text(encoding="utf-8"))
    routes = build_stub_routes(spec)
    cases = sum(len(case_map) for case_map in routes.values())
    with stub_server(routes) as stub:
        env = os.environ.copy()
        env.update({
            "SPECFORGE_BASE_URL": stub.base_url,
            "SPECFORGE_TOKEN": "stub-token",
            "SPECFORGE_TIMEOUT": "10",
        })
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", args.tests],
            cwd=str(ROOT),
            env=env,
            check=False,
        )
        print(f"stub: {len(routes)} operations, {cases} cases, "
              f"{len(stub.records)} HTTP requests served")
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
