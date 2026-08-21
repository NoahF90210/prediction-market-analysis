from __future__ import annotations

import hashlib
import json
import re
import subprocess
import tempfile
from pathlib import Path

from src.rebuild.claims import claim_consistency_errors
from src.rebuild.pipeline import build_fixture_analysis
from src.rebuild.protocol import ROOT

_SECRET_PATTERNS = (
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"eyJ[a-zA-Z0-9_-]{20,}\.eyJ[a-zA-Z0-9_-]{20,}\.[a-zA-Z0-9_-]{20,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"gh[pousr]_[A-Za-z0-9]{30,}"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
)
_SECRET_ASSIGNMENT = re.compile(
    r"(?i)\b((?:[A-Z_][A-Z0-9_]*(?:_PASSWORD|_SECRET|_PRIVATE_KEY|_ACCESS_KEY|_API_KEY_ID|_API_KEY|_AUTH_TOKEN|_BEARER_TOKEN|_GITHUB_TOKEN))|PASSWORD|SECRET|PRIVATE_KEY|ACCESS_KEY|API_KEY_ID|API_KEY|AUTH_TOKEN|BEARER_TOKEN|GITHUB_TOKEN)\b[ \t]*[:=][ \t]*['\"]?([^'\"\s,}\]]+)"
)
_PLACEHOLDER_MARKERS = ("example", "placeholder", "fixture", "must-never", "changeme", "your_", "<", "${")


def _tracked_files() -> list[Path]:
    # Include tracked files plus untracked, non-ignored files that would be eligible
    # for a future commit. Ignored local raw/derived data and .env stay outside scope.
    output = subprocess.check_output(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=ROOT,
    )
    return [ROOT / item.decode() for item in output.split(b"\0") if item]


def scan_text_for_secrets(text: str, label: str) -> list[str]:
    errors: list[str] = []
    for pattern in _SECRET_PATTERNS:
        if pattern.search(text):
            errors.append(f"possible_tracked_secret:{label}:{pattern.pattern}")
    for match in _SECRET_ASSIGNMENT.finditer(text):
        value = match.group(2).strip()
        value_lower = value.lower()
        if len(value) < 12 or any(marker in value_lower for marker in _PLACEHOLDER_MARKERS):
            continue
        if value_lower.startswith(("os.environ", "os.getenv", "environ.get")):
            continue
        errors.append(f"possible_secret_assignment:{label}:{match.group(1)}")
    return errors


def secret_boundary_errors() -> list[str]:
    errors: list[str] = []
    tracked = _tracked_files()
    relative = {path.relative_to(ROOT).as_posix() for path in tracked}
    if ".env" in relative:
        errors.append("tracked_secret_file:.env")
    for path in tracked:
        if not path.is_file():
            continue
        try:
            text = path.read_text(errors="ignore")
        except OSError as exc:
            errors.append(f"unreadable_tracked_file:{path.relative_to(ROOT)}:{exc}")
            continue
        errors.extend(scan_text_for_secrets(text, path.relative_to(ROOT).as_posix()))
    return errors


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def deterministic_fixture_errors() -> list[str]:
    errors: list[str] = []
    with tempfile.TemporaryDirectory(prefix="forecast-audit-validate-") as temp:
        temp_root = Path(temp)
        _, first = build_fixture_analysis(output_dir=temp_root / "first")
        _, second = build_fixture_analysis(output_dir=temp_root / "second")
        if set(first) != set(second):
            return ["fixture_artifact_set_mismatch"]
        for key in sorted(first):
            if _sha256(first[key]) != _sha256(second[key]):
                errors.append(f"fixture_not_deterministic:{key}")
    return errors


def validate_repository() -> dict[str, object]:
    secret_errors = secret_boundary_errors()
    claim_errors = claim_consistency_errors()
    fixture_errors = deterministic_fixture_errors()
    errors = [*secret_errors, *claim_errors, *fixture_errors]
    return {
        "status": "passed" if not errors else "failed",
        "checks": {
            "tracked_secret_boundary": "passed" if not secret_errors else "failed",
            "public_claim_consistency": "passed" if not claim_errors else "failed",
            "deterministic_fixture_build": "passed" if not fixture_errors else "failed",
        },
        "errors": errors,
    }


def main() -> int:
    result = validate_repository()
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
