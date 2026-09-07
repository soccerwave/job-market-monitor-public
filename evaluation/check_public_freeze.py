from __future__ import annotations

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
MANIFEST = HERE / "PUBLIC_FREEZE.json"


def canonical_sha256(path: Path) -> str:
    # Public freeze hashes text semantically across Windows/Linux checkouts.
    # Normalizing line endings avoids CRLF/LF false failures.
    text = path.read_text(encoding="utf-8-sig")
    canonical = text.replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def main() -> int:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    failures: list[str] = []
    for rel, expected in manifest["canonical_sha256"].items():
        path = ROOT / rel
        if not path.exists():
            failures.append(f"missing: {rel}")
            continue
        actual = canonical_sha256(path)
        if actual != expected:
            failures.append(f"hash mismatch: {rel}\n  expected={expected}\n  actual={actual}")

    if failures:
        print("Public freeze check FAILED")
        print("\n".join(failures))
        return 1

    print(f"Public freeze check PASS: {manifest['status']}")
    print(f"Frozen public-safe files: {len(manifest['canonical_sha256'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
