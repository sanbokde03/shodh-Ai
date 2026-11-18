"""Replay the two real pre-fix false passes against either implementation."""

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, os.environ.get("SHODH_IMPLEMENTATION_ROOT", str(ROOT)))

from reviewer.engine import review
from reviewer.model import FakeClient


def examples():
    b = json.loads((ROOT / "evaluation/inputs/valid_base.json").read_text())
    b["snippets"][0]["code"] = b["snippets"][0]["code"].replace('ticket.get("urgent")', 'ticket["urgent"]')
    missing_report = review(b)

    class MisattributingClient(FakeClient):
        def complete(self, request, config):
            response = json.loads(super().complete(request, config))
            response["claims"][0].update(request["effective_rules"][1]["evidence"][0])
            return json.dumps(response)

    b = json.loads((ROOT / "evaluation/inputs/valid_base.json").read_text())
    citation_report = review(b, MisattributingClient())
    return {"history": "Actual failures observed after preserving the first working checkpoint; not deliberately injected reviewer faults. Inputs are targeted synthetic regression probes.",
            "examples": [
                {"name": "absent_field_vs_null", "expected": "CHANGES_REQUIRED", "actual": missing_report["status"], "report": missing_report,
                 "diagnosis": "The partition enumerated null but not an absent key. Subscript access raises KeyError only for the absent key.",
                 "fix": "Enumerate absent and explicit null separately for every declared field.",
                 "regression_test": "test_absent_field_is_distinct_from_explicit_null_in_python"},
                {"name": "source_citation_misattribution", "expected": "INCOMPLETE", "actual": citation_report["status"], "report": citation_report,
                 "diagnosis": "A real quote was checked against the inventory, but not against the rule it claimed to support.",
                 "fix": "Bind source and approval anchors to each effective rule before validating claims.",
                 "regression_test": "test_model_cannot_relabel_an_unrelated_source_quote"}]}


if __name__ == "__main__":
    Path(sys.argv[1]).write_text(json.dumps(examples(), indent=2) + "\n")
