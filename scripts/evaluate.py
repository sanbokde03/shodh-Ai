"""Frozen offline evaluation. Labels stay here, outside reviewer code and requests."""

import argparse
import hashlib
import json
import os
import sys
import zipfile
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, os.environ.get("SHODH_IMPLEMENTATION_ROOT", str(ROOT)))

from reviewer.contracts import load_json
from reviewer.engine import inventory, review
from reviewer.model import FakeClient
from oracle import actual_route, expected_route


def verify_freeze():
    manifest = load_json(ROOT / "evaluation/frozen_manifest.json")
    fresh_path = ROOT / "evaluation/fresh_manifest.json"
    if fresh_path.exists():
        fresh = load_json(fresh_path)
        # Source hashes describe the frozen checkpoint, not later working-tree repairs.
        with zipfile.ZipFile(ROOT / "checkpoints/v02-reviewer.zip") as checkpoint:
            for name, expected in fresh["files"].items():
                if name.startswith(("reviewer/", "schemas/")):
                    if hashlib.sha256(checkpoint.read(name)).hexdigest() != expected:
                        raise RuntimeError(f"Frozen checkpoint content changed: {name}")
                else:
                    manifest["files"][name] = expected
        for case in manifest["cases"]:
            if case["split"] == "holdout":
                case["split"] = "historical_holdout"
        manifest["cases"].extend({**case, "split": "historical_holdout"} for case in fresh["cases"])
        manifest["holdout_policy"] = fresh["holdout_policy"] + " All eight reserved cases have since been exposed; current reruns are historical regression checks."
    for name, expected in manifest["files"].items():
        if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != expected:
            raise RuntimeError(f"Frozen evaluation content changed: {name}")
    return manifest


def primary_target_found(findings, target):
    return any(f["artifact"] == target["artifact"] and f["rule_ref"] == target["rule_ref"]
               and f["location"] == target["location"] for f in findings)


def evaluate(split="development", semantic_checks=True, markdown=False):
    manifest = verify_freeze()
    rows, counts = [], Counter()
    finding_counts = Counter()
    elapsed = 0.0
    for case in manifest["cases"]:
        if split != "all" and case["split"] != ("historical_holdout" if split == "holdout" else split):
            continue
        name = case["id"]
        frozen_bundle = load_json(ROOT / "evaluation/inputs" / f"{name}.json")
        if markdown:
            from reviewer.markdown import load_markdown
            bundle = load_markdown(ROOT / "inputs" / f"{name}.md")
        else:
            bundle = frozen_bundle
        label = load_json(ROOT / "evaluation/labels" / f"{name}.json")
        report = review(bundle, FakeClient(case["model_mode"]), semantic_checks=semantic_checks)
        counts[f"{label['kind']}_total"] += 1
        counts["total"] += 1
        counts["correct"] += report["status"] == label["status"]
        counts["false_passes"] += label["kind"] == "defective" and report["status"] == "PASS"
        counts["false_blocks"] += label["kind"] == "valid" and report["status"] == "CHANGES_REQUIRED"
        counts[f"{label['kind']}_incomplete"] += report["status"] == "INCOMPLETE"
        counts["calls"] += report["resources"]["model_calls"]
        counts["retries"] += report["resources"]["model_retries"]
        elapsed += report["resources"]["seconds"]
        allowed = inventory(bundle)
        unsupported = 0
        for finding in report["findings"]:
            finding_counts["total"] += 1
            supported = bool(finding["evidence"]) and all(e in allowed for e in finding["evidence"])
            if finding["kind"] == "behavior_mismatch":
                c = finding["counterexample"]
                supported &= c["expected_route"] != c["actual_route"]
                expected = expected_route(frozen_bundle, c["ticket"])
                actual = actual_route(frozen_bundle, finding["artifact"], c["ticket"])
                agrees = expected == c["expected_route"] and actual == c["actual_route"]
                finding_counts["counterexamples_independently_replayed"] += 1
                finding_counts["counterexamples_correct"] += agrees
                supported &= agrees
            unsupported += not supported
        finding_counts["unsupported_evidence_or_identical_routes"] += unsupported
        target = label["target"]
        target_found = None
        if target:
            finding_counts["target_total"] += 1
            target_found = primary_target_found(report["findings"], target)
            finding_counts["target_found"] += target_found
        rows.append({"id": name, "split": case["split"], "expected": label["status"],
                     "actual": report["status"], "correct": report["status"] == label["status"],
                     "target_found": target_found, "report": report})
    return {"split": split, "input_format": "Markdown development translation" if markdown else "original frozen JSON",
            "model_results": "synthetic fake client only; real-model semantic performance not measured",
            "semantic_checks_enabled": semantic_checks,
            "metrics": {**dict(counts), "finding_quality": dict(finding_counts), "runtime_seconds": elapsed},
            "label_limitations": manifest["label_method"], "cases": rows}


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--split", choices=["development", "holdout", "historical_holdout", "all"], default="development")
    p.add_argument("--output", required=True)
    p.add_argument("--ablate-semantics", action="store_true")
    p.add_argument("--markdown", action="store_true", help="Check the public Markdown translations against the frozen oracle/labels")
    args = p.parse_args()
    result = evaluate(args.split, not args.ablate_semantics, args.markdown)
    Path(args.output).write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result["metrics"], indent=2))
