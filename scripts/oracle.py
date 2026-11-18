"""Independent, narrowly scoped oracle for the trusted synthetic case families.

This module is evaluation-only. It does not import the reviewer, and must never
be used to execute user bundles. The evaluation harness checks frozen hashes first.
"""

import operator
import re
from fractions import Fraction


def expected_route(bundle, ticket):
    rules = sorted(bundle["requirements"], key=lambda r: r["order"])
    if ticket.get("category") is None:
        return "manual"
    technical_only = 'category = "technical"' in rules[1]["text"]
    if ticket.get("urgent") is True and (not technical_only or ticket.get("category") == "technical"):
        return "priority"
    threshold_text = rules[2]["text"]
    applicable = [a for a in bundle["approvals"] if a["status"] == "approved"
                  and a["from_revision"] <= bundle["revision"] <= a["to_revision"]]
    if applicable:
        threshold_text = max(applicable, key=lambda a: a["sequence"])["text"]
    number = re.search(r"waiting\s*(?:>=|<)\s*(\d+(?:\.\d+)?)\s+minutes", threshold_text)
    if not number:
        raise ValueError("Oracle supports only the frozen ticket-routing scenario families")
    threshold = Fraction(number[1])
    wait = ticket.get("waiting")
    return "escalation" if wait is not None and wait >= threshold else "normal"


def graph_route(bundle, ticket):
    factors = {"seconds": Fraction(1, 60), "minutes": 1, "hours": 60, "count": 1}

    def condition(e):
        if type(e) is bool:
            return e
        op = e["op"]
        if op == "and":
            return all(condition(child) for child in e["args"])
        if op == "or":
            return any(condition(child) for child in e["args"])
        if op == "not":
            return not condition(e["arg"])
        actual = ticket.get(e["field"])
        if op == "missing":
            return actual is None
        if actual is None:
            return op == "ne"
        expected = e["value"]
        if "unit" in e:
            expected = Fraction(str(expected)) * factors[e["unit"]]
        comparisons = {"eq": operator.eq, "ne": operator.ne, "lt": operator.lt,
                       "lte": operator.le, "gt": operator.gt, "gte": operator.ge}
        return comparisons[op](actual, expected)

    nodes = {n["id"]: n for n in bundle["workflow"]["nodes"]}
    name, visited = bundle["workflow"]["entry"], set()
    while name in nodes and name not in visited:
        visited.add(name)
        n = nodes[name]
        if n["kind"] == "route":
            return n["route"]
        name = n["true"] if condition(n["when"]) else n["false"]
    return "ERROR:cycle" if name in visited else "ERROR:missing_branch"


def actual_route(bundle, artifact, ticket):
    if artifact == "workflow":
        return graph_route(bundle, ticket)
    if artifact == "specification":
        # Reuse this oracle's graph predicate evaluator, not reviewer logic.
        rules = sorted(bundle["specification"]["rules"], key=lambda r: r["order"])
        nodes = []
        for i, r in enumerate(rules):
            nodes += [{"id": f"test{i}", "kind": "decision", "when": r["when"], "true": f"out{i}", "false": f"test{i+1}"},
                      {"id": f"out{i}", "kind": "route", "route": r["route"]}]
        nodes.append({"id": f"test{len(rules)}", "kind": "route", "route": None})
        return graph_route({"workflow": {"entry": "test0", "nodes": nodes}}, ticket)
    if artifact == "code":
        namespace = {}
        # Only hash-verified, generated fixture code is executed here, never user code.
        exec(compile(bundle["snippets"][0]["code"], "<trusted frozen synthetic fixture>", "exec"), {"__builtins__": {}}, namespace)
        try:
            return namespace["route"](ticket)
        except (KeyError, TypeError) as exc:
            return f"ERROR:{type(exc).__name__}"
    raise ValueError(artifact)
