"""Small, explicitly development-only live check; never part of offline verification."""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from evaluate import verify_freeze
from reviewer.contracts import load_json
from reviewer.engine import review
from reviewer.model import Config, OllamaClient

CASES = {"valid_base": set(), "valid_approved": set(), "valid_unusual_units": set(),
         "defect_code": set(), "incomplete_ambiguous": {"R3"}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True, help="Already installed local Ollama model")
    parser.add_argument("--output", default="reports/live_current_after_usability.json")
    parser.add_argument("--no-thinking", action="store_true")
    parser.add_argument("--timeout-seconds", type=int, default=30)
    args = parser.parse_args()
    verify_freeze()
    config = Config(model=args.model, timeout_seconds=args.timeout_seconds, max_attempts=2,
                    thinking=False if args.no_thinking else None)
    rows, counts = [], Counter()
    report = {"scope": "Five inspected development cases; not held-out model accuracy or a production benchmark.",
              "configuration": config.__dict__, "metrics": {}, "cases": rows}
    for name in CASES:
        bundle = load_json(ROOT / "evaluation/inputs" / f"{name}.json")
        label = load_json(ROOT / "evaluation/labels" / f"{name}.json")
        assert label["split"] == "development"
        result = review(bundle, OllamaClient(), config)
        attempts = result["model"]["attempts"]
        validated = bool(attempts) and attempts[-1]["result"] == "validated"
        claims = json.loads(attempts[-1]["response"])["claims"] if validated else []
        ambiguous = {c["rule_ref"] for c in claims if c["judgment"] == "ambiguous"}
        language_correct = validated and ambiguous == CASES[name]
        counts["total"] += 1
        counts["correct"] += result["status"] == label["status"]
        counts[f"{label['kind']}_total"] += 1
        counts[f"{label['kind']}_incomplete"] += result["status"] == "INCOMPLETE"
        counts["false_passes"] += label["kind"] == "defective" and result["status"] == "PASS"
        counts["false_blocks"] += label["kind"] == "valid" and result["status"] == "CHANGES_REQUIRED"
        counts["model_calls"] += result["resources"]["model_calls"]
        counts["model_retries"] += result["resources"]["model_retries"]
        counts["validated_model_reports"] += validated
        counts["ambiguity_judgments_correct"] += language_correct
        counts["runtime_seconds"] += result["resources"]["seconds"]
        rows.append({"id": name, "expected": label["status"], "actual": result["status"],
                     "expected_ambiguous_rules": sorted(CASES[name]), "actual_ambiguous_rules": sorted(ambiguous),
                     "ambiguity_judgment_correct": language_correct, "report": result})
        report["metrics"] = dict(counts)
        Path(args.output).write_text(json.dumps(report, indent=2) + "\n")
        print(f"{name}: expected {label['status']}, actual {result['status']}; model language judgment correct: {language_correct}", flush=True)
    print(json.dumps(report["metrics"], indent=2), flush=True)
    return 0 if counts["correct"] == counts["total"] and counts["ambiguity_judgments_correct"] == counts["total"] else 1


if __name__ == "__main__":
    sys.exit(main())
