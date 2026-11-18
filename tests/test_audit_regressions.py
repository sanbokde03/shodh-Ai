"""Reproductions of the PDF-compliance audit findings, using development data."""

import json
import unittest
from unittest.mock import MagicMock, patch

from reviewer.contracts import ROOT, load_json
from reviewer.markdown import load_markdown
from reviewer.engine import inventory, review
from reviewer.model import Config, FakeClient, OllamaClient


def bundle(name="valid_base"):
    return load_markdown(ROOT / "inputs" / f"{name}.md")


class CitingClient(FakeClient):
    def __init__(self, rule_index, artifact, location, review_bundle=None):
        super().__init__()
        self.rule_index, self.artifact, self.location = rule_index, artifact, location
        self.item = next(e for e in inventory(review_bundle or bundle())
                         if e["artifact"] == artifact and e["location"] == location)

    def complete(self, request, config):
        response = json.loads(super().complete(request, config))
        response["claims"][self.rule_index].update(self.item)
        return json.dumps(response)


class AuditRegressions(unittest.TestCase):
    def nested_bundle(self, wrong_graph=False, wrong_code=False):
        b = bundle()
        b["workflow"]["nodes"][2]["snippet_id"] = "wait_only"
        b["snippets"].append({"id": "wait_only", "version": 1, "code":
            'def route(ticket):\n    if ticket.get("waiting") is not None and ticket.get("waiting") >= 30:\n        return "escalation"\n    return "normal"\n'})
        if wrong_graph:
            b["workflow"]["nodes"][2]["true"] = "out_normal"
        if wrong_code:
            b["snippets"][-1]["code"] = 'def route(ticket):\n    return "normal"\n'
        return b

    def test_wrong_graph_does_not_blame_correct_nested_code(self):
        r = review(self.nested_bundle(wrong_graph=True))
        self.assertEqual(r["status"], "CHANGES_REQUIRED")
        self.assertFalse(any(f["artifact"] == "code" for f in r["findings"]))
        skipped = [u for u in r["coverage"]["unreviewed"] if u["scope"] == "nested_code_context"]
        self.assertEqual(len(skipped), 1)
        self.assertEqual(next(c["status"] for c in r["check_results"] if c["check"] == "code_semantics"), "INCOMPLETE")

    def test_correct_graph_exposes_wrong_nested_code(self):
        r = review(self.nested_bundle(wrong_code=True))
        findings = [f for f in r["findings"] if f["artifact"] == "code"]
        self.assertTrue(findings)
        for f in findings:
            self.assertEqual(f["counterexample"]["expected_route"], "escalation")
            self.assertIn("route this ticket to escalation", f["correction"])

    def test_wrong_graph_still_checks_entry_and_valid_nested_paths(self):
        b = self.nested_bundle(wrong_graph=True)
        b["snippets"][0]["code"] = 'def route(ticket):\n    return "normal"\n'
        b["snippets"][-1]["code"] = 'def route(ticket):\n    return "escalation"\n'
        r = review(b)
        locations = [f["location"] for f in r["findings"] if f["artifact"] == "code"]
        self.assertIn("main:2", locations)
        self.assertIn("wait_only:2", locations)
        self.assertEqual(next(c["status"] for c in r["check_results"] if c["check"] == "code_semantics"), "CHANGES_REQUIRED")

    def test_opposite_approval_decisions_are_unresolved(self):
        b = bundle("valid_approved")
        rejection = {**b["approvals"][0], "id": "A_rejected", "status": "rejected"}
        b["approvals"].append(rejection)
        r = review(b)
        self.assertEqual(r["status"], "INCOMPLETE")
        self.assertIn("Conflicting approval", r["coverage"]["unreviewed"][0]["reason"])

    def test_out_of_scope_rejection_is_not_a_conflict(self):
        b = bundle("valid_approved")
        b["approvals"].append({**b["approvals"][0], "id": "old_rejection", "status": "rejected",
                               "from_revision": 2, "to_revision": 3})
        self.assertEqual(review(b)["status"], "PASS")

    def test_proposal_and_approval_can_coexist(self):
        b = bundle("valid_approved")
        b["approvals"].append({**b["approvals"][0], "id": "proposal", "status": "proposed"})
        self.assertEqual(review(b)["status"], "PASS")

    def test_unrelated_structured_evidence_is_rejected(self):
        for artifact, location in (("specification", "/rules/1"), ("workflow", "/nodes/1")):
            with self.subTest(artifact=artifact):
                r = review(bundle(), CitingClient(0, artifact, location))
                self.assertEqual(r["status"], "INCOMPLETE")
                self.assertTrue(any(u["scope"] == "model_review" for u in r["coverage"]["unreviewed"]))

    def test_source_evidence_is_valid_but_implementation_cannot_define_policy(self):
        self.assertEqual(review(bundle(), CitingClient(1, "source", "policy/paragraph/2"))["status"], "PASS")
        for artifact, location in (("specification", "/rules/1"), ("workflow", "/nodes/1")):
            self.assertEqual(review(bundle(), CitingClient(1, artifact, location))["status"], "INCOMPLETE")

    def test_linked_code_is_checked_but_is_not_policy_evidence(self):
        b = bundle()
        b["workflow"]["nodes"][2]["snippet_id"] = "wait_only"
        b["snippets"].append({"id": "wait_only", "version": 1, "code":
            'def route(ticket):\n    if ticket.get("waiting") is not None and ticket.get("waiting") >= 30:\n        return "escalation"\n    return "normal"\n'})
        self.assertEqual(review(b)["status"], "PASS")
        self.assertEqual(review(b, CitingClient(0, "code", "wait_only:2", b))["status"], "INCOMPLETE")
        self.assertEqual(review(b, CitingClient(2, "code", "wait_only:2", b))["status"], "INCOMPLETE")

    def test_primary_locations_identify_the_responsible_decision(self):
        cases = [("defect_boundary", "workflow", "/nodes/2"),
                 ("defect_branch", "workflow", "/nodes/2"),
                 ("defect_precedence", "workflow", "/nodes/1"),
                 ("defect_stale_revision", "specification", "/rules/2"),
                 ("defect_omission", "specification", "/rules/2"),
                 ("defect_code", "code", "main:6")]
        for name, artifact, expected in cases:
            with self.subTest(case=name):
                findings = [f for f in review(bundle(name))["findings"] if f["artifact"] == artifact]
                self.assertTrue(findings)
                self.assertTrue(any(f["location"] == expected for f in findings),
                                [(f["location"], f["rule_ref"]) for f in findings])

    def test_context_budget_abstains_before_a_call(self):
        client = FakeClient()
        r = review(bundle(), client, Config(context_window=4096))
        self.assertEqual(r["status"], "INCOMPLETE")
        self.assertEqual(client.calls, 0)
        self.assertIn("context bound", r["coverage"]["unreviewed"][-1]["reason"])

    def test_model_receives_computed_meaning_and_binding_scope(self):
        class InspectingClient(FakeClient):
            def complete(self, request, config):
                rule = request["effective_rules"][0]
                if rule["interpretation"]["condition"] != {"op": "missing", "field": "category"}:
                    raise ValueError("Missing formal meaning")
                if not request["citation_scope"][rule["id"]]:
                    raise ValueError("Missing citation scope")
                return super().complete(request, config)
        self.assertEqual(review(bundle(), InspectingClient())["status"], "PASS")

    def test_live_transport_uses_the_declared_context_and_thinking_setting(self):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps({
            "done": True, "done_reason": "stop", "message": {"content": "{}"}}).encode()
        with patch("urllib.request.urlopen", return_value=response) as transport:
            OllamaClient().complete({"effective_rules": [{"id": "unseen_policy"}]}, Config(thinking=False))
        payload = json.loads(transport.call_args.args[0].data)
        self.assertEqual(payload["options"]["num_ctx"], 32768)
        self.assertIs(payload["think"], False)
        self.assertEqual(payload["format"]["properties"]["coverage"]["enum"], [["unseen_policy"]])

    def test_unresolved_language_has_explicit_model_scope_and_stays_unreviewed(self):
        class ScopedClient(FakeClient):
            def complete(self, request, config):
                if [r["id"] for r in request["effective_rules"]] != ["R3"]:
                    raise ValueError("Model scope must identify the unresolved language")
                if any(e["artifact"] not in ("source", "approvals") for e in request["evidence_inventory"]):
                    raise ValueError("Implementation cannot define an unspecified source requirement")
                if request["deterministic_findings"]:
                    raise ValueError("Implementation details must not leak through findings")
                return super().complete(request, config)
        r = review(bundle("incomplete_ambiguous"), ScopedClient())
        self.assertEqual(r["status"], "INCOMPLETE")
        self.assertEqual(r["model"]["requested_rules"], ["R3"])
        self.assertEqual(len(r["coverage"]["rules"]), 4)
        self.assertTrue(any(u["scope"] == "source_language" and u["rule_ref"] == "R3"
                            for u in r["coverage"]["unreviewed"]))

    def test_complete_coverage_can_report_no_additional_claims(self):
        class NoIssuesClient(FakeClient):
            def complete(self, request, config):
                response = json.loads(super().complete(request, config))
                response["claims"] = []
                return json.dumps(response)
        self.assertEqual(review(bundle(), NoIssuesClient())["status"], "PASS")

    def test_model_does_not_receive_superseded_or_implementation_thresholds(self):
        class CurrentPolicyClient(FakeClient):
            def complete(self, request, config):
                rule = next(r for r in request["effective_rules"] if r["id"] == "R3")
                if "25 minutes" not in rule["text"] or len(rule["evidence"]) != 1:
                    raise ValueError("Expected the effective approved source")
                if any(e["artifact"] not in ("source", "approvals") for e in request["evidence_inventory"]):
                    raise ValueError("Implementation must not supply source meaning")
                if any(e["artifact"] == "source" and e["location"] == "policy/paragraph/3"
                       for e in request["evidence_inventory"]):
                    raise ValueError("Superseded source is not the current policy")
                return super().complete(request, config)
        self.assertEqual(review(bundle("valid_approved"), CurrentPolicyClient())["status"], "PASS")


if __name__ == "__main__":
    unittest.main()
