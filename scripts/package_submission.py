"""Verify offline, then atomically rebuild the submission ZIP without local path prefixes."""

import os
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    subprocess.run([sys.executable, "scripts/verify.py"], cwd=ROOT, check=True)
    target = ROOT.parent / "shodh-reviewer-submission.zip"
    with tempfile.NamedTemporaryFile(dir=target.parent, suffix=".zip", delete=False) as stream:
        temporary = Path(stream.name)
    try:
        with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(ROOT.rglob("*")):
                if (not path.is_file() or path.is_symlink() or "__pycache__" in path.parts
                        or ".git" in path.parts or path.suffix == ".pyc" or path.name in (".DS_Store", ".env")):
                    continue
                data = path.read_bytes()
                if path.suffix == ".txt":
                    data = data.replace(str(ROOT).encode(), b"<PROJECT>")
                archive.writestr(str(Path("shodh-reviewer") / path.relative_to(ROOT)), data)
        with zipfile.ZipFile(temporary) as archive:
            assert archive.testzip() is None
            assert archive.read("shodh-reviewer/reviewer/engine.py") == (ROOT / "reviewer/engine.py").read_bytes()
            for name in ("docs/engineering-note.pdf", "evaluation/fresh_manifest.json", "reports/live_current.json"):
                assert archive.getinfo(f"shodh-reviewer/{name}").file_size > 0
        os.replace(temporary, target)
        print(f"Built {target.name} ({target.stat().st_size:,} bytes). Local prefixes in text logs were redacted.")
    finally:
        temporary.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
