"""Freeze four new procedural holdouts after the audit fixes, before evaluating them.

Labels use direct routing reasoning, never reviewer predictions. The scenario families
are known to the author; concrete seeded variants are excluded from tuning.
"""

import copy
import hashlib
import json
import random
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEED = 20261117


def main():
    manifest_path = ROOT / "evaluation/fresh_manifest.json"
    checkpoint = ROOT / "checkpoints/v02-reviewer.zip"
    if manifest_path.exists() or checkpoint.exists():
        raise SystemExit("Fresh freeze already exists; do not overwrite inspected holdouts")
    rng = random.Random(SEED)
    manifest = {"seed": SEED, "created_utc": datetime.now(timezone.utc).isoformat(),
                "label_method": "Direct manual policy reasoning encoded independently of reviewer outputs; AI-authored and not human-audited.",
                "holdout_policy": "Four fresh concrete variants frozen after the audit fixes. Families are known; inputs/results excluded from tuning. Original four holdouts are now historical.",
                "files": {}, "cases": []}
    for letter in "abcd":
        b = json.loads((ROOT / "evaluation/inputs/valid_base.json").read_text())
        b["id"] = f"v3_{letter}"
        b["revision"] = rng.randint(20, 80)
        threshold = rng.randint(41, 79)
        refs = {r["id"]: f"policy_{rng.randrange(10000, 99999)}_{i}" for i, r in enumerate(b["requirements"])}
        for r in b["requirements"]:
            r["id"] = refs[r["id"]]
        b["requirements"][2]["text"] = f"WHEN waiting >= {threshold} minutes THEN escalation"
        b["fields"]["category"]["values"].append("research")
        for r in b["specification"]["rules"]:
            r["rule_ref"] = refs[r["rule_ref"]]
        b["specification"]["rules"][2]["when"]["value"] = threshold
        for n in b["workflow"]["nodes"]:
            if "rule_ref" in n:
                n["rule_ref"] = refs[n["rule_ref"]]
        b["workflow"]["nodes"][2]["when"]["value"] = threshold
        b["snippets"][0]["code"] = b["snippets"][0]["code"].replace(">= 30", f">= {threshold}")
        for artifact in (b["specification"], b["workflow"], b["snippets"][0]):
            artifact["version"] = rng.randint(3, 12)
        status, kind, target = "PASS", "valid", None
        reason = "New IDs, revisions, threshold and enum value preserve the ordered policy."
        if letter == "b":
            b["workflow"]["nodes"][2]["when"]["value"] = threshold + 1
            status, kind = "CHANGES_REQUIRED", "defective"
            target = {"artifact": "workflow", "rule_ref": refs["R3"], "location": "/nodes/2"}
            reason = "At the source threshold, a categorized nonurgent ticket must escalate; workflow waits one extra minute."
        elif letter == "c":
            a = {"id": "decision_a", "rule_ref": refs["R3"], "status": "approved",
                 "from_revision": b["revision"], "to_revision": b["revision"], "sequence": 1,
                 "base_version": 1, "version": 2, "text": b["requirements"][2]["text"]}
            b["approvals"] = [a, {**a, "id": "decision_b", "status": "rejected"}]
            status, kind = "INCOMPLETE", "incomplete"
            reason = "Approved and rejected records claim the same rule version in the same revision scope without a resolution."
        elif letter == "d":
            b["snippets"][0]["code"] = b["snippets"][0]["code"].replace('ticket.get("urgent")', 'ticket["urgent"]')
            status, kind = "CHANGES_REQUIRED", "defective"
            target = {"artifact": "code", "rule_ref": refs["R4"], "location": "main:4"}
            reason = "Categorized ticket without urgent/waiting keys should use normal fallback; code raises KeyError on urgent."
        rng.shuffle(b["requirements"])
        label = {"status": status, "kind": kind, "split": "holdout", "reason": reason, "model_mode": "ok",
                 "source_evidence": [r["location"] for r in b["requirements"]], "target": target}
        for folder, value in (("inputs", b), ("labels", label)):
            path = ROOT / "evaluation" / folder / f"{b['id']}.json"
            path.write_text(json.dumps(value, indent=2) + "\n")
            manifest["files"][str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
        manifest["cases"].append({"id": b["id"], "split": "holdout", "model_mode": "ok"})
    core = [p for folder in ("reviewer", "schemas") for p in (ROOT / folder).rglob("*")
            if p.is_file() and "__pycache__" not in p.parts]
    with zipfile.ZipFile(checkpoint, "w", zipfile.ZIP_DEFLATED) as archive:
        for p in sorted(core):
            archive.write(p, p.relative_to(ROOT))
            manifest["files"][str(p.relative_to(ROOT))] = hashlib.sha256(p.read_bytes()).hexdigest()
    for path in (checkpoint, Path(__file__)):
        manifest["files"][str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    print("Frozen four fresh holdouts and the fixed reviewer checkpoint. No evaluation run yet.")


if __name__ == "__main__":
    main()
