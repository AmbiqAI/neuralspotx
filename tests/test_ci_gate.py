"""The aggregate required CI check must include every mandatory safety job."""

from __future__ import annotations

from pathlib import Path

import yaml


def test_required_gate_includes_c_locale_safety_job() -> None:
    workflow_path = Path(__file__).parents[1] / ".github" / "workflows" / "ci.yml"
    workflow = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
    gate = workflow["jobs"]["lint-and-test"]

    assert "unit-tests-c-locale" in gate["needs"]
    decision = gate["steps"][0]["run"]
    assert "needs.unit-tests-c-locale.result" in decision
