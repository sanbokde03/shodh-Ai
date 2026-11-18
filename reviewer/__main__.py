"""Review scenario files and save one JSON result for each input."""

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

from .contracts import ROOT
from .markdown import load_markdown
from .engine import review
from .model import Config, FakeClient, OllamaClient


def simplify_report(report, mode):
    findings = []
    for finding in report["findings"]:
        item = {"problem": finding.get("message", finding["correction"]),
                "severity": finding["severity"], "rule_ref": finding["rule_ref"],
                "artifact": finding["artifact"], "version": finding["version"],
                "location": finding.get("location_description", "Specific location could not be identified"),
                "reference": finding["location"],
                "evidence": [e for e in finding["evidence"] if e["artifact"] in ("source", "approvals")
                             or (e["artifact"] == "code" and e["location"] == finding["location"])] or finding["evidence"][:1],
                "correction": finding["correction"]}
        if "counterexample" in finding:
            item["counterexample"] = finding["counterexample"]
            example = finding["counterexample"]
            artifact = {"code": "Python code", "workflow": "workflow", "specification": "specification"}.get(finding["artifact"], finding["artifact"])
            item["problem"] = f"This ticket should go to {example['expected_route']}, but the {artifact} returns {example['actual_route']}."
        findings.append(item)
    unfinished = report["coverage"]["unreviewed"]
    count = len(findings)
    summary = ("The specification, workflow and Python follow the company rules." if report["status"] == "PASS"
               else f"{count} problem{'s' if count != 1 else ''} found." if report["status"] == "CHANGES_REQUIRED"
               else "The review could not be completed. See coverage.unreviewed.")
    if report["status"] == "CHANGES_REQUIRED" and unfinished:
        summary += " Some checks could not be completed. See coverage.unreviewed."
    checks = []
    for check in report["check_results"]:
        name, separator, identifier = check["check"].partition(":")
        checks.append({"check": name.replace("_", " ") + separator + identifier, "status": check["status"]})
    simple = {"status": report["status"], "summary": summary, "mode": mode, "findings": findings,
              "coverage": {"rules": {r["rule_ref"]: r["status"] for r in report["coverage"].get("rules", [])},
                           "unreviewed": unfinished},
              "check_results": checks}
    if report.get("ticket_results"):
        simple["ticket_results"] = report["ticket_results"]
    simple["resources"] = report.get("resources", {"seconds": None, "model_calls": 0, "model_retries": 0})
    simple["audit"] = {"model": report.get("model", {}), "provenance": report.get("provenance", {})}
    return simple


def save_report(path, report):
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(report, stream, indent=2, allow_nan=False, ensure_ascii=False)
            stream.write("\n")
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description="Review all inputs and save JSON results in outputs/.")
    parser.add_argument("input", nargs="?", type=Path, default=ROOT / "inputs", help="A Markdown file or folder; default: inputs/")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "outputs", help="Result folder; default: outputs/")
    parser.add_argument("--offline", action="store_true", help="Use synthetic responses for offline checks instead of real AI")
    args = parser.parse_args()
    paths = sorted(args.input.glob("*.md")) if args.input.is_dir() else [args.input]
    if not paths:
        parser.error("The input folder contains no Markdown files")
    targets = [args.output_dir / path.with_suffix('.json').name for path in paths]
    if args.output_dir.resolve() in {p.parent.resolve() for p in paths}:
        parser.error("Output files must be separate from input files")
    try:
        args.output_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        parser.error(f"Cannot create the output folder: {exc}")
    config = Config() if args.offline else Config(model="qwen3.5:9b", timeout_seconds=90, thinking=False)
    exit_code = 0
    for path, target in zip(paths, targets):
        try:
            bundle = load_markdown(path)
            report = review(bundle, FakeClient() if args.offline else OllamaClient(), config)
        except (ValueError, OSError, RecursionError) as exc:
            report = {"status": "INCOMPLETE", "summary": f"Input could not be read: {exc}", "findings": [],
                      "coverage": {"unreviewed": [{"scope": "entire_input", "reason": str(exc)}]},
                      "check_results": [{"check": "input_read", "status": "INCOMPLETE"}]}
        try:
            save_report(target, simplify_report(report, "offline" if args.offline else "ai"))
        except OSError as exc:
            print(f"Cannot save {target}: {exc}", file=sys.stderr)
            exit_code = 2
            continue
        print(f"{path.name} -> {target} ({report['status']})", file=sys.stderr, flush=True)
        exit_code = max(exit_code, {"PASS": 0, "CHANGES_REQUIRED": 1, "INCOMPLETE": 2}[report["status"]])
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
