"""Review orchestration. No evaluation labels, fixture IDs, or caches are consulted."""

import copy
import hashlib
import itertools
import json
import time

from .contracts import Unsupported, unique, validate_bundle
from .language import Code, evaluate, normalize, parse_source, representatives
from .model import Config, FakeClient, review_model


def evidence(artifact, version, location, quote):
    return {"artifact": artifact, "version": version, "location": location, "quote": quote}


def describe_locations(report, bundle):
    """Add display labels without changing evidence or model requests."""
    if not report["findings"]:
        return report
    labels = {}
    for i, node in enumerate(bundle.get("workflow", {}).get("nodes", [])):
        detail = "condition" if node["kind"] == "decision" else "destination"
        labels[("workflow", f"/nodes/{i}")] = f"Workflow step '{node['id']}': {detail}"
    for i, rule in enumerate(bundle.get("specification", {}).get("rules", [])):
        labels[("specification", f"/rules/{i}")] = f"Specification rule '{rule['id']}'"
    labels[("specification", "/rules")] = "Specification rules: no matching rule"
    for snippet in bundle.get("snippets", []):
        name = snippet["id"]
        labels[("code", name)] = f"Python snippet '{name}'"
        for line in range(1, len(snippet["code"].splitlines()) + 1):
            labels[("code", f"{name}:{line}")] = f"Python snippet '{name}', line {line}"
    for finding in report["findings"]:
        finding["location_description"] = labels.get(
            (finding["artifact"], finding["location"]), "Specific location could not be identified")
    return report


def inventory(bundle):
    items = [evidence("source", r["version"], r["location"], r["text"]) for r in bundle["requirements"]]
    for i, r in enumerate(bundle["specification"]["rules"]):
        items.append(evidence("specification", bundle["specification"]["version"], f"/rules/{i}", json.dumps(r, sort_keys=True)))
    for i, n in enumerate(bundle["workflow"]["nodes"]):
        items.append(evidence("workflow", bundle["workflow"]["version"], f"/nodes/{i}", json.dumps(n, sort_keys=True)))
    for s in bundle["snippets"]:
        items.append(evidence("code", s["version"], s["id"], s["code"]))
        for i, line in enumerate(s["code"].splitlines(), 1):
            if line.strip():
                items.append(evidence("code", s["version"], f"{s['id']}:{i}", line))
    for i, a in enumerate(bundle["approvals"]):
        items.append(evidence("approvals", a["version"], f"/approvals/{i}", json.dumps(a, sort_keys=True)))
    return items


def effective_rules(bundle, items):
    rules = copy.deepcopy(bundle["requirements"])
    unique(rules)
    unique(rules, "order")
    unique(rules, "location")
    by_id = {r["id"]: r for r in rules}
    for rule in rules:
        rule["evidence"] = [evidence("source", rule["version"], rule["location"], rule["text"])]
    unique(bundle["approvals"])
    applicable = []
    decisions = {}
    for i, approval in enumerate(bundle["approvals"]):
        if approval["rule_ref"] not in by_id:
            raise Unsupported(f"Approval {approval['id']} references unknown source rule")
        if approval["from_revision"] > approval["to_revision"]:
            raise Unsupported(f"Approval {approval['id']} has an inverted revision scope")
        if approval["from_revision"] <= bundle["revision"] <= approval["to_revision"]:
            if approval["status"] in ("approved", "rejected"):
                key = (approval["rule_ref"], approval["version"])
                prior = decisions.setdefault(key, approval)
                if prior["status"] != approval["status"]:
                    raise Unsupported(f"Conflicting approval decisions for {key}: {prior['id']} and {approval['id']}")
            if approval["status"] == "approved":
                applicable.append((i, approval))
    seen_sequences, seen_versions = set(), set()
    for i, a in sorted(applicable, key=lambda pair: pair[1]["sequence"]):
        key = (a["rule_ref"], a["sequence"])
        vkey = (a["rule_ref"], a["version"])
        if key in seen_sequences or vkey in seen_versions:
            raise Unsupported(f"Conflicting approvals for {a['rule_ref']}: repeated sequence or target version")
        seen_sequences.add(key)
        seen_versions.add(vkey)
        rule = by_id[a["rule_ref"]]
        if a["base_version"] != rule["version"] or a["version"] <= a["base_version"]:
            raise Unsupported(f"Approval {a['id']} does not extend the current rule version")
        rule["text"], rule["version"] = a["text"], a["version"]
        rule["evidence"].append(next(e for e in items if e["artifact"] == "approvals" and e["location"] == f"/approvals/{i}"))
    return sorted(rules, key=lambda r: r["order"])


def route_rules(rules, ticket):
    trace = []
    for rule in rules:
        trace.append(rule)
        if evaluate(rule["when"], ticket):
            return rule["route"], rule, trace
    return None, None, trace


def route_graph(nodes, entry, ticket):
    trace, seen = [], set()
    current = entry
    while current in nodes and current not in seen:
        seen.add(current)
        node = nodes[current]
        trace.append(node)
        if node["kind"] == "route":
            return node["route"], trace
        current = node["true"] if evaluate(node["when"], ticket) else node["false"]
    return "ERROR:cycle" if current in seen else "ERROR:missing_branch", trace


def review(bundle, client=None, config=None, *, semantic_checks=True, max_tickets=100000, provided_tickets=None):
    start = time.perf_counter()
    result = {"status": "INCOMPLETE", "summary": "", "findings": [],
              "coverage": {"rules": [], "unreviewed": [], "method": "exhaustive integer predicate partition", "representative_tickets": 0},
              "check_results": [], "model": {},
              "provenance": {"reviewer_version": "0.6.0", "cache": "disabled"}}
    findings, checks, coverage = result["findings"], result["check_results"], result["coverage"]

    def unchecked(scope, reason, rule_ref=None):
        coverage["unreviewed"].append({"scope": scope, "reason": reason, "rule_ref": rule_ref})
        checks.append({"check": scope, "status": "INCOMPLETE", "detail": reason})

    def finish():
        blockers = sum(f["severity"] == "blocker" for f in findings)
        result["status"] = "CHANGES_REQUIRED" if blockers else "INCOMPLETE" if coverage["unreviewed"] else "PASS"
        result["summary"] = f"{blockers} evidenced blocker(s); {len(coverage['unreviewed'])} unreviewed scope item(s)."
        if coverage["unreviewed"]:
            for record in coverage["rules"]:
                if record["status"] == "reviewed":
                    record["status"] = "partially_reviewed"
        result["resources"] = {"seconds": time.perf_counter() - start,
                               "model_calls": result["model"].get("calls", 0), "model_retries": result["model"].get("retries", 0)}
        return describe_locations(result, bundle)

    try:
        validate_bundle(bundle)
        result["provenance"]["bundle_sha256"] = hashlib.sha256(json.dumps(bundle, sort_keys=True).encode()).hexdigest()
        items = inventory(bundle)
        rules = effective_rules(bundle, items)
    except (ValueError, TypeError, KeyError, RecursionError) as exc:
        unchecked("contracts_and_approvals", f"{type(exc).__name__}: {exc}")
        return finish()
    checks.append({"check": "contracts_and_approvals", "status": "PASS"})
    if provided_tickets is None:
        provided_tickets = bundle.get("example_tickets", ())
    try:
        if not isinstance(provided_tickets, (list, tuple)) or len(provided_tickets) > 128:
            raise Unsupported("Provide an array of at most 128 tickets")
        for ticket in provided_tickets:
            if type(ticket) is not dict or set(ticket) - bundle["fields"].keys():
                raise Unsupported("Ticket must be an object using declared fields")
            for name, value in ticket.items():
                field = bundle["fields"][name]
                if value is None:
                    continue
                valid = ((field["type"] == "number" and type(value) is int)
                         or (field["type"] == "boolean" and type(value) is bool)
                         or (field["type"] == "enum" and type(value) is str and value in field["values"]))
                if not valid:
                    raise Unsupported(f"Ticket {name} is outside the declared integer/boolean/enum domain")
    except ValueError as exc:
        unchecked("provided_tickets", str(exc))
        provided_tickets = ()
    result["ticket_results"] = []
    source_rules = []
    for rule in rules:
        record = {"rule_ref": rule["id"], "version": rule["version"], "source": rule["evidence"], "status": "reviewed"}
        coverage["rules"].append(record)
        try:
            expr, route = parse_source(rule["text"], bundle["fields"])
            source_rules.append({**rule, "when": expr, "route": route})
        except (ValueError, RecursionError) as exc:
            record["status"] = "unreviewed"
            unchecked("source_language", str(exc), rule["id"])
    if not source_rules or source_rules[-1]["when"] is not True or any(r["when"] is True for r in source_rules[:-1]):
        unchecked("source_order", "Exactly one final OTHERWISE rule is required")

    expressions = [r["when"] for r in source_rules]
    spec, nodes, programs = [], {}, {}
    spec_ok, graph_ok, code_ok = True, True, True
    try:
        unique(bundle["specification"]["rules"])
        unique(bundle["specification"]["rules"], "order")
        for i, rule in enumerate(bundle["specification"]["rules"]):
            if rule.get("rule_ref", rules[0]["id"]) not in {r["id"] for r in rules}:
                raise Unsupported("Specification has an invented rule reference")
            spec.append({**rule, "when": normalize(rule["when"], bundle["fields"]), "location": f"/rules/{i}"})
        spec.sort(key=lambda r: r["order"])
        expressions.extend(r["when"] for r in spec)
    except (ValueError, RecursionError) as exc:
        spec_ok = False
        unchecked("specification", str(exc))
    try:
        unique(bundle["workflow"]["nodes"])
        for i, node in enumerate(bundle["workflow"]["nodes"]):
            item = {**node, "location": f"/nodes/{i}"}
            if node["kind"] == "decision":
                item["when"] = normalize(node["when"], bundle["fields"])
                expressions.append(item["when"])
            if node.get("rule_ref", rules[0]["id"]) not in {r["id"] for r in rules}:
                raise Unsupported("Workflow has an invented rule reference")
            nodes[node["id"]] = item
        if bundle["workflow"]["entry"] not in nodes:
            raise Unsupported("Workflow entry node is absent")
    except (ValueError, RecursionError) as exc:
        graph_ok = False
        unchecked("workflow", str(exc))
    try:
        unique(bundle["snippets"])
        linked = {n["snippet_id"] for n in nodes.values() if "snippet_id" in n}
        if linked != {s["id"] for s in bundle["snippets"]}:
            raise Unsupported("Missing or unlinked snippets")
        if not graph_ok or "snippet_id" not in nodes[bundle["workflow"]["entry"]]:
            raise Unsupported("An entry-linked snippet is required for full code coverage")
        for snippet in bundle["snippets"]:
            try:
                program = Code(snippet["code"], bundle["fields"])
                programs[snippet["id"]] = (program, snippet)
                expressions.extend(program.expressions)
                checks.append({"check": f"code_syntax:{snippet['id']}", "status": "PASS", "execution": "not executed; restricted AST interpreter"})
            except SyntaxError as exc:
                findings.append({"severity": "blocker", "kind": "syntax_error", "rule_ref": None,
                                 "artifact": "code", "version": snippet["version"], "location": f"{snippet['id']}:{exc.lineno}",
                                 "evidence": [next(e for e in items if e["artifact"] == "code" and e["location"] == snippet["id"])],
                                 "correction": "Fix Python syntax before reviewing behavior.", "message": str(exc)})
                code_ok = False
                unchecked("code_semantics", f"Syntax failure in {snippet['id']}")
    except (ValueError, RecursionError) as exc:
        code_ok = False
        unchecked("code_inspection", str(exc))

    ready = not any(u["scope"] in ("source_language", "source_order") for u in coverage["unreviewed"])
    seen_findings = set()

    def mismatch(artifact, version, location, expected, actual, rule, ticket, refs, trace):
        key = (artifact, location, rule["id"])
        if key in seen_findings:
            return
        seen_findings.add(key)
        findings.append({"severity": "blocker", "kind": "behavior_mismatch", "rule_ref": rule["id"],
                         "artifact": artifact, "version": version, "location": location,
                         "message": f"Expected {expected}; observed {actual} in supported semantics.",
                         "evidence": rule["evidence"] + refs,
                         "counterexample": {"ticket": ticket, "expected_route": expected, "actual_route": actual},
                         "trace": trace,
                         "correction": f"Implement '{rule['text']}' in {artifact}; preserve earlier exceptions and route this ticket to {expected}."})

    if ready and semantic_checks:
        try:
            tickets, count = representatives(expressions, bundle["fields"], max_tickets)
            coverage["representative_tickets"] = count
            reached_nodes = set()
            skipped_nested = set()
            for ticket in itertools.chain(tickets, provided_tickets):
                expected, rule, source_trace = route_rules(source_rules, ticket)
                ticket_result = {"ticket": ticket, "expected_route": expected, "artifacts": {}}
                if spec_ok:
                    actual, actual_rule, trace = route_rules(spec, ticket)
                    ticket_result["artifacts"]["specification"] = actual
                    if actual != expected:
                        locations = [r["location"] for r in trace]
                        refs = [e for e in items if e["artifact"] == "specification" and e["location"] in locations]
                        location = next((r["location"] for r in reversed(trace) if r["route"] == expected),
                                        actual_rule["location"] if actual_rule else "/rules")
                        mismatch("specification", bundle["specification"]["version"], location, expected, actual, rule, ticket, refs, locations)
                if graph_ok:
                    actual, trace = route_graph(nodes, bundle["workflow"]["entry"], ticket)
                    ticket_result["artifacts"]["workflow"] = actual
                    reached_nodes.update(n["id"] for n in trace)
                    if actual != expected:
                        locations = [n["location"] for n in trace]
                        refs = [e for e in items if e["artifact"] == "workflow" and e["location"] in locations]
                        # shortcut: locate a candidate decision region; unique root causes need global repair proofs.
                        decisions = [n for n in trace if n["kind"] == "decision"]
                        responsible = decisions[-1] if decisions else trace[-1]
                        for decision in reversed(decisions):
                            alternate = decision["false"] if evaluate(decision["when"], ticket) else decision["true"]
                            if route_graph(nodes, alternate, ticket)[0] == expected:
                                responsible = decision
                                break
                        mismatch("workflow", bundle["workflow"]["version"], responsible["location"], expected, actual, rule, ticket, refs, locations)
                    if code_ok:
                        for node in trace:
                            if "snippet_id" not in node:
                                continue
                            # A broken workflow cannot establish the context for a downstream snippet.
                            if node["id"] != bundle["workflow"]["entry"] and actual != expected:
                                if node["id"] not in skipped_nested:
                                    skipped_nested.add(node["id"])
                                    unchecked("nested_code_context", f"Linked snippet {node['snippet_id']} at node {node['id']} was not compared on policy-inconsistent workflow paths; fix the workflow and rerun")
                                continue
                            program, snippet = programs[node["snippet_id"]]
                            observed, lines = program.route(ticket)
                            if node["id"] == bundle["workflow"]["entry"]:
                                ticket_result["artifacts"]["code"] = observed
                            if observed != expected:
                                locations = [f"{snippet['id']}:{line}" for line in lines]
                                refs = [e for e in items if e["artifact"] == "code" and e["location"] in locations]
                                line = next((line for line in reversed(lines) if line in program.decision_lines), lines[-1] if lines else None)
                                location = f"{snippet['id']}:{line}" if line is not None else snippet["id"]
                                mismatch("code", snippet["version"], location, expected, observed, rule, ticket, refs, locations)
                if ticket in provided_tickets:
                    if ticket_result not in result["ticket_results"]:
                        result["ticket_results"].append(ticket_result)
            coverage["reachable_nodes"] = sorted(reached_nodes)
            coverage["unreachable_nodes"] = sorted(set(nodes) - reached_nodes)
            for node in nodes.values():
                if "snippet_id" in node and node["id"] not in reached_nodes:
                    unchecked("code_reachability", f"Linked snippet at unreachable node {node['id']} was inspected but not behaviorally compared")
            for artifact, ok in (("specification", spec_ok), ("workflow", graph_ok), ("code", code_ok)):
                if ok:
                    checks.append({"check": f"{artifact}_semantics", "status": "CHANGES_REQUIRED" if any(f["artifact"] == artifact for f in findings) else "INCOMPLETE" if artifact == "code" and skipped_nested else "PASS",
                                   "method": "exhaustive predicate partition", "representatives": count})
        except (ValueError, RecursionError) as exc:
            unchecked("exhaustive_semantics", str(exc))
    else:
        unchecked("exhaustive_semantics", "Disabled for controlled ablation" if not semantic_checks else "Effective source policy is unresolved")

    interpretations = {r["id"]: {"condition": json.loads(json.dumps(r["when"], default=str)), "route": r["route"], "order": r["order"]}
                       for r in source_rules}
    model_rules = [{"id": r["id"], "text": r["text"], "version": r["version"], "evidence": [r["evidence"][-1]],
                    "interpretation": interpretations.get(r["id"])} for r in rules]
    unresolved_rules = [r for r in model_rules if r["interpretation"] is None]
    requested_rules = unresolved_rules or model_rules
    model_items = [e for r in requested_rules for e in r["evidence"]]
    bindings = {r["id"]: {(e["artifact"], e["version"], e["location"]) for e in r["evidence"]}
                for r in requested_rules}
    result["model"], errors, ambiguities = review_model(client or FakeClient(), config or Config(), requested_rules, model_items, findings, bundle["fields"], bindings)
    result["model"]["requested_rules"] = [r["id"] for r in requested_rules]
    result["model"]["scope"] = "unresolved_source_language" if unresolved_rules else "residual_ambiguity_of_formal_policy"
    for error in errors:
        unchecked("model_review", error)
    for claim in ambiguities:
        unchecked("model_ambiguity", claim["explanation"], claim["rule_ref"])
    checks.append({"check": "model_review", "status": "INCOMPLETE" if errors or ambiguities else "PASS"})
    return finish()
