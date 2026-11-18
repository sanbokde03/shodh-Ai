"""One CPU-only, offline command: tests, identical-set comparison, ablation, regressions."""

import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def compare_translation(original, translated):
    from reviewer.contracts import Unsupported
    from reviewer.language import parse_source

    def meaning(text, fields):
        try:
            return parse_source(text, fields)
        except Unsupported:
            return None

    comparable = json.loads(json.dumps(translated))
    unresolved = 0
    for key in ("requirements", "approvals"):
        if len(original[key]) != len(comparable[key]):
            raise ValueError(f"Markdown changed the number of {key}")
        for before, after in zip(original[key], comparable[key]):
            first = meaning(before["text"], original["fields"])
            second = meaning(after["text"], translated["fields"])
            if first != second:
                raise ValueError("Markdown changed a supported rule's meaning")
            unresolved += first is None
            after["text"] = before["text"]
    if comparable != original:
        raise ValueError("Markdown changed scenario structure, code or metadata")
    return unresolved


def run(*args, env=None, output=None):
    proc = subprocess.run([sys.executable, *args], cwd=ROOT, env=env, capture_output=True, text=True)
    if output:
        (ROOT / output).write_text(proc.stdout + proc.stderr)
    if proc.returncode:
        print(proc.stdout + proc.stderr)
        raise SystemExit(proc.returncode)
    if proc.stdout:
        print(proc.stdout.strip())


def main():
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT / "scripts"))
    from evaluate import verify_freeze
    manifest = verify_freeze()
    report_dir = ROOT / "reports"
    report_dir.mkdir(exist_ok=True)
    run("-m", "unittest", "discover", "-s", "tests", "-v", output="reports/unit_tests.txt")
    initial = json.loads((ROOT / "checkpoints/initial_manifest.json").read_text())
    archive = ROOT / "checkpoints/initial.zip"
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == initial["sha256"], "Checkpoint changed"
    implementation_files = [p for folder in ("reviewer", "schemas", "scripts", "tests") for p in (ROOT / folder).rglob("*")
                            if p.is_file() and "__pycache__" not in p.parts]
    implementation = {"created_before_run_utc": datetime.now(timezone.utc).isoformat(),
                      "python": platform.python_version(), "platform": platform.platform(),
                      "dataset_manifest_sha256": hashlib.sha256((ROOT / "evaluation/frozen_manifest.json").read_bytes()).hexdigest(),
                      "files": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in implementation_files}}
    (report_dir / "final_implementation_manifest.json").write_text(json.dumps(implementation, indent=2) + "\n")
    with tempfile.TemporaryDirectory(prefix="shodh-checkpoint-") as directory:
        with zipfile.ZipFile(archive) as z:
            z.extractall(directory)
        for name, expected in initial["files"].items():
            assert hashlib.sha256((Path(directory) / name).read_bytes()).hexdigest() == expected
        baseline_env = {**os.environ, "SHODH_IMPLEMENTATION_ROOT": directory}
        run("scripts/evaluate.py", "--split", "all", "--output", "reports/baseline.json", env=baseline_env)
        run("scripts/debug_examples.py", "reports/debug_baseline.json", env=baseline_env)
    run("scripts/evaluate.py", "--split", "all", "--output", "reports/final.json")
    from reviewer.contracts import load_json
    from reviewer.markdown import load_markdown
    unresolved_translations = sum(compare_translation(
        load_json(ROOT / "evaluation/inputs" / f"{case['id']}.json"),
        load_markdown(ROOT / "inputs" / f"{case['id']}.md")) for case in manifest["cases"])
    run("scripts/evaluate.py", "--split", "all", "--markdown", "--output", "reports/markdown.json")
    run("scripts/evaluate.py", "--split", "all", "--ablate-semantics", "--output", "reports/ablation.json")
    run("scripts/debug_examples.py", "reports/debug_final.json")
    baseline = json.loads((report_dir / "baseline.json").read_text())
    final = json.loads((report_dir / "final.json").read_text())
    ablation = json.loads((report_dir / "ablation.json").read_text())
    markdown = json.loads((report_dir / "markdown.json").read_text())
    debug_before = json.loads((report_dir / "debug_baseline.json").read_text())
    debug_after = json.loads((report_dir / "debug_final.json").read_text())
    from reviewer.contracts import load_json, validate
    from reviewer.engine import describe_locations, review
    from reviewer.__main__ import simplify_report
    from reviewer.model import Config
    schema = load_json(ROOT / "schemas/report.schema.json")
    for row in final["cases"]:
        validate(row["report"], schema)
    assert final["metrics"]["correct"] == final["metrics"]["total"], "Final decisions do not match frozen labels"
    quality = final["metrics"]["finding_quality"]
    assert quality.get("unsupported_evidence_or_identical_routes", 0) == 0
    assert quality["counterexamples_correct"] == quality["counterexamples_independently_replayed"]
    assert quality["target_found"] == quality["target_total"]
    assert markdown["metrics"]["correct"] == markdown["metrics"]["total"] == 24
    mq = markdown["metrics"]["finding_quality"]
    assert mq["unsupported_evidence_or_identical_routes"] == 0
    assert mq["counterexamples_correct"] == mq["counterexamples_independently_replayed"]
    assert mq["target_found"] == mq["target_total"]
    assert len([c for c in final["cases"] if c["split"] == "historical_holdout"]) == 8
    assert all(x["actual"] == x["expected"] for x in debug_after["examples"])
    assert any(x["actual"] != x["expected"] for x in debug_before["examples"])
    holdouts = [c for c in final["cases"] if c["split"] == "historical_holdout"]
    summary = {"model": "Frozen evaluation: fake only. Separate development-only live smoke reports are not a real-model benchmark.", "baseline": baseline["metrics"],
               "final": final["metrics"], "ablation": ablation["metrics"],
               "holdout": {"correct": sum(c["correct"] for c in holdouts), "total": len(holdouts), "scope": "Historical regression only; no new unseen cases in v0.2.1, v0.3.0 or v0.4.0"},
               "regressions": [{"name": before["name"], "baseline": before["actual"], "final": after["actual"], "expected": after["expected"]}
                               for before, after in zip(debug_before["examples"], debug_after["examples"])],
               "interpretation": "The original 20 status labels tie; four newly frozen variants test the audit fixes. The two original debugging probes remain separate development evidence. Primary-location scoring is now strict.",
               "holdout_limitations": manifest["holdout_policy"]}
    summary["markdown_development"] = {"metrics": markdown["metrics"],
        "unresolved_source_texts": unresolved_translations,
        "scope": "Inspected translations of the same 24 cases, not fresh holdouts. Supported rules have equal parsed meaning and all other data is identical. Unresolved prose remains unresolved; its equivalence is not claimed."}
    class RecordedClient:
        provenance = "replay of a recorded live response; no network or new inference"

        def __init__(self, response):
            self.response = response

        def complete(self, request, config):
            return self.response

    historical_checkpoint = load_json(ROOT / "checkpoints/pre-usability-fixes.json")
    historical_archive = ROOT / "checkpoints/pre-usability-fixes.zip"
    assert hashlib.sha256(historical_archive.read_bytes()).hexdigest() == historical_checkpoint["sha256"]
    with tempfile.TemporaryDirectory(prefix="shodh-historical-live-") as directory:
        with zipfile.ZipFile(historical_archive) as archive:
            archive.extractall(directory)
        for name, expected in historical_checkpoint["files"].items():
            assert hashlib.sha256((Path(directory) / name).read_bytes()).hexdigest() == expected
        run("scripts/replay_historical_live.py", env={**os.environ, "SHODH_IMPLEMENTATION_ROOT": directory})
    historical = load_json(report_dir / "historical_live_replay.json")
    summary["live_development"] = {**historical["original_live_development"],
        "verification": "Replayed with the archived pre-fix prompt/schema/implementation, not the current policy. No new inference."}
    summary["historical_live_replay"] = historical
    from collections import Counter
    statuses, replayed, calls, retries, saved_seconds = Counter(), 0, 0, 0, 0.0
    assert {p.stem for p in (ROOT / "outputs").glob("*.json")} == {case["id"] for case in manifest["cases"]}
    for case in manifest["cases"]:
        saved = load_json(ROOT / "outputs" / f"{case['id']}.json")
        bundle = load_markdown(ROOT / "inputs" / f"{case['id']}.md")
        validate(saved, schema)
        assert saved["mode"] == "ai"
        assert saved["audit"]["provenance"]["bundle_sha256"] == hashlib.sha256(json.dumps(bundle, sort_keys=True).encode()).hexdigest()
        model = saved["audit"]["model"]
        resources = saved["resources"]
        calls += resources["model_calls"]
        retries += resources["model_retries"]
        saved_seconds += resources["seconds"]
        statuses[saved["status"]] += 1
        if not resources["model_calls"]:
            assert review(bundle)["status"] == saved["status"]
            continue
        assert model["client"] == "live-local-ollama"
        attempt = model["attempts"][-1]
        assert attempt["result"] == "validated"
        replay = review(bundle, RecordedClient(attempt["response"]), Config(**model["configuration"]))
        assert replay["model"]["request_sha256"] == model["request_sha256"]
        assert replay["model"]["response_schema_sha256"] == model["response_schema_sha256"]
        assert replay["model"]["attempts"][-1]["result"] == "validated"
        assert replay["status"] == saved["status"]
        view = simplify_report(replay, "ai")
        for key in ("summary", "findings", "coverage", "check_results", "ticket_results"):
            assert view.get(key) == saved.get(key), (case["id"], key)
        replayed += 1
    summary["public_live_development"] = {"scope": "Saved inspected development reviews of the Markdown scenarios; offline replay is not new model inference. Three historical fault-injection filenames do not force failures during live reviews.",
        "outputs": sum(statuses.values()), "statuses": dict(statuses), "validated_responses_replayed": replayed,
        "saved_model_calls": calls, "saved_retries": retries, "sum_saved_review_seconds": saved_seconds,
        "ambiguity_fix": {"before": "INCOMPLETE (preserved in pre_usability_outputs.json)", "after": load_json(ROOT / "outputs/valid_unusual_units.json")["status"], "scope": "Inspected development correction, not held-out accuracy"}}
    demo_bundle = load_markdown(ROOT / "examples/ticket_demo.md")
    demo = load_json(ROOT / "examples/results/ticket_demo.json")
    validate(demo, schema)
    assert demo["audit"]["provenance"]["bundle_sha256"] == hashlib.sha256(json.dumps(demo_bundle, sort_keys=True).encode()).hexdigest()
    demo_model = demo["audit"]["model"]
    attempt = demo_model["attempts"][-1]
    demo_replay = review(demo_bundle, RecordedClient(attempt["response"]), Config(**demo_model["configuration"]))
    assert demo_replay["model"]["request_sha256"] == demo_model["request_sha256"]
    assert demo_replay["status"] == demo["status"] == "PASS"
    assert demo_replay["ticket_results"] == demo["ticket_results"]
    assert [t["expected_route"] for t in demo["ticket_results"]] == ["escalation", "manual"]
    summary["markdown_ticket_demo"] = {"status": demo["status"], "ticket_results": demo["ticket_results"],
        "resources": demo["resources"], "verification": "Saved real demonstration replayed offline against matching input/request hashes"}
    # The first-run protocol verifies its archived code, not later display changes.
    with tempfile.TemporaryDirectory(prefix="shodh-reserved-protocol-") as directory:
        archived = Path(directory)
        with zipfile.ZipFile(ROOT / "checkpoints/reserved_20261118.zip") as checkpoint:
            checkpoint.extractall(archived)
        shutil.copytree(ROOT / "evaluation/reserved_20261118", archived / "evaluation/reserved_20261118")
        (archived / "scripts").mkdir()
        for name in ("freeze_additional_cases.py", "evaluate_additional_cases.py"):
            shutil.copyfile(ROOT / "scripts" / name, archived / "scripts" / name)
        (archived / "checkpoints").mkdir()
        shutil.copyfile(ROOT / "checkpoints/reserved_20261118.zip", archived / "checkpoints/reserved_20261118.zip")
        (archived / "reports").symlink_to(report_dir, target_is_directory=True)
        run(str(archived / "scripts/evaluate_additional_cases.py"))
        run(str(archived / "scripts/evaluate_additional_cases.py"), "--replay-live")
    additional_offline = load_json(report_dir / "additional_offline_first.json")
    additional_live = load_json(report_dir / "additional_live_first.json")
    additional_replay = load_json(report_dir / "additional_live_replay.json")
    assert additional_offline["metrics"]["correct"] == additional_live["metrics"]["correct"] == 8
    assert additional_replay["metrics"]["correct"] == 8
    # Replay every actual response, including the rejected report and corrective retry.
    from reviewer.model import PROMPT
    for row in additional_live["cases"]:
        saved = row["report"]
        bundle = load_markdown(ROOT / "evaluation/reserved_20261118/inputs" / f"{row['id']}.md")
        decorated = describe_locations(json.loads(json.dumps(saved)), bundle)
        assert load_json(ROOT / "outputs/additional_cases" / f"{row['id']}.json") == simplify_report(decorated, "ai")
        class AttemptReplay:
            provenance = "recorded complete attempt sequence; no new inference"
            def __init__(self):
                self.index = 0
            def complete(self, request, config):
                attempt = saved["model"]["attempts"][self.index]
                self.index += 1
                encoded = json.dumps({"system": PROMPT, "request": request}, sort_keys=True).encode()
                assert hashlib.sha256(encoded).hexdigest() == attempt["request_sha256"]
                return attempt["response"]
        replay = review(bundle, AttemptReplay(), Config(**additional_live["configuration"]))
        assert replay["status"] == saved["status"]
        assert replay["resources"]["model_calls"] == saved["resources"]["model_calls"]
        assert replay["resources"]["model_retries"] == saved["resources"]["model_retries"]
    summary["additional_reserved_cases"] = {"scope": additional_live["scope"],
        "seed": additional_live["seed"], "manifest_sha256": additional_live["manifest_sha256"],
        "first_offline": additional_offline["metrics"], "first_live": additional_live["metrics"],
        "verification": "Frozen implementation and inputs/labels/protocol hashes checked; first results preserved. Current reruns/replays are exposed historical checks, not new holdouts."}
    (report_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(f"Verified {final['metrics']['correct']}/{final['metrics']['total']} frozen decisions, 8 historical holdout regressions, 2 debugging regressions.")


if __name__ == "__main__":
    main()
