from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN = re.compile(
    r"comfyui|azure|elevenlabs|google[_-]?tts|\bark\b|bailian|qwen|openai",
    re.IGNORECASE,
)
SCAN_ROOTS = (ROOT / "app", ROOT / "web" / "src")
SCAN_FILES = (ROOT / ".env.example",)


def main() -> int:
    files = [path for root in SCAN_ROOTS for path in root.rglob("*") if path.is_file() and path.suffix in {".py", ".ts", ".tsx", ".css"}]
    files.extend(path for path in SCAN_FILES if path.is_file())
    violations = []
    for path in files:
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if FORBIDDEN.search(line):
                violations.append(f"{path.relative_to(ROOT)}:{line_number}: prohibited provider reference")
    if violations:
        print("\n".join(violations), file=sys.stderr)
        return 1
    print(f"Provider boundary clean ({len(files)} files scanned)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
