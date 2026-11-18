"""Preserve the first working implementation before further debugging."""

import hashlib
import json
import platform
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


if __name__ == "__main__":
    target = ROOT / "checkpoints/initial.zip"
    if target.exists():
        raise SystemExit("Initial checkpoint already exists; refusing to replace it")
    paths = [p for directory in ("reviewer", "schemas", "tests") for p in (ROOT / directory).rglob("*")
             if p.is_file() and "__pycache__" not in p.parts]
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(paths):
            archive.write(path, path.relative_to(ROOT))
    manifest = {"created_utc": datetime.now(timezone.utc).isoformat(), "python": platform.python_version(),
                "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
                "files": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
                "working_evidence": "17 unit tests passed; development statuses 16/16 before checkpoint. Holdouts not run.",
                "dataset_manifest_sha256": hashlib.sha256((ROOT / "evaluation/frozen_manifest.json").read_bytes()).hexdigest()}
    (ROOT / "checkpoints/initial_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print("Initial working checkpoint preserved.")
