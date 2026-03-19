#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = REPO_ROOT / "contract" / "manifest.yaml"
ARTIFACTS_DIR = REPO_ROOT / "artifacts"
SUMMARY_PATH = ARTIFACTS_DIR / "check_contract_summary.json"
IGNORED_BASENAMES = {".DS_Store"}

def should_ignore(path: Path) -> bool:
    return path.name in IGNORED_BASENAMES


class CheckContractError(Exception):
    pass


@dataclass
class FixtureRunResult:
    fixture_id: str
    passed: bool
    expected_exit_code: int
    actual_exit_code: int
    missing_paths: list[str]
    unexpected_paths: list[str]
    changed_files: list[str]
    stdout: str
    stderr: str


def load_manifest(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise CheckContractError(f"Missing manifest: {path}")

    try:
        with path.open("r", encoding="utf-8") as handle:
            manifest = yaml.safe_load(handle)
    except yaml.YAMLError as exc:
        raise CheckContractError(f"Invalid YAML in manifest: {exc}") from exc

    if not isinstance(manifest, dict):
        raise CheckContractError("Manifest must be a JSON/YAML object.")

    return manifest


def validate_manifest(manifest: dict[str, Any]) -> None:
    contract = manifest.get("contract")
    if not isinstance(contract, dict):
        raise CheckContractError("Manifest must contain a contract object.")

    contract_file = contract.get("contract_file")
    if not isinstance(contract_file, str) or not contract_file.strip():
        raise CheckContractError("Manifest contract.contract_file is required.")

    if not (REPO_ROOT / contract_file).exists():
        raise CheckContractError(f"Referenced contract file does not exist: {contract_file}")

    clauses = manifest.get("clauses")
    fixtures = manifest.get("fixtures")

    if not isinstance(clauses, list) or not clauses:
        raise CheckContractError("Manifest must contain a non-empty clauses list.")
    if not isinstance(fixtures, list) or not fixtures:
        raise CheckContractError("Manifest must contain a non-empty fixtures list.")

    clause_ids: set[str] = set()
    fixture_ids: set[str] = set()

    for fixture in fixtures:
        if not isinstance(fixture, dict):
            raise CheckContractError("Each fixture entry must be an object.")
        fixture_id = fixture.get("fixture_id")
        if not isinstance(fixture_id, str) or not fixture_id.strip():
            raise CheckContractError("Each fixture must define fixture_id.")
        if fixture_id in fixture_ids:
            raise CheckContractError(f"Duplicate fixture_id: {fixture_id}")
        fixture_ids.add(fixture_id)

        fixture_dir = REPO_ROOT / "fixtures" / fixture_id
        if not fixture_dir.exists():
            raise CheckContractError(f"Referenced fixture directory does not exist: {fixture_dir}")

    for clause in clauses:
        if not isinstance(clause, dict):
            raise CheckContractError("Each clause entry must be an object.")
        clause_id = clause.get("clause_id")
        if not isinstance(clause_id, str) or not clause_id.strip():
            raise CheckContractError("Each clause must define clause_id.")
        if clause_id in clause_ids:
            raise CheckContractError(f"Duplicate clause_id: {clause_id}")
        clause_ids.add(clause_id)

    for clause in clauses:
        check = clause.get("check")
        if not isinstance(check, dict):
            raise CheckContractError(f"Clause {clause['clause_id']} must contain a check object.")

        check_type = check.get("type")
        if check_type == "fixture":
            fixture_id = check.get("fixture_id")
            if not isinstance(fixture_id, str) or fixture_id not in fixture_ids:
                raise CheckContractError(
                    f"Clause {clause['clause_id']} references unknown fixture_id: {fixture_id}"
                )
        elif check_type == "aggregate":
            requires = check.get("requires")
            if not isinstance(requires, list) or not requires:
                raise CheckContractError(
                    f"Aggregate clause {clause['clause_id']} must define non-empty requires."
                )
            for dependency in requires:
                if dependency not in clause_ids:
                    raise CheckContractError(
                        f"Aggregate clause {clause['clause_id']} references unknown clause {dependency}"
                    )
        else:
            raise CheckContractError(
                f"Clause {clause['clause_id']} has unsupported check type: {check_type}"
            )


def load_expected_result(fixture_dir: Path) -> dict[str, Any]:
    path = fixture_dir / "expected_result.json"
    if not path.exists():
        raise CheckContractError(f"Missing expected_result.json in {fixture_dir}")

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CheckContractError(f"Invalid JSON in {path}: {exc}") from exc

    if not isinstance(payload, dict):
        raise CheckContractError(f"{path} must contain a JSON object.")

    return payload


def copy_tree_contents(src: Path, dst: Path) -> None:
    dst.mkdir(parents=True, exist_ok=True)
    if not src.exists():
        return

    for child in src.iterdir():
        target = dst / child.name
        if child.is_dir():
            shutil.copytree(child, target)
        else:
            shutil.copy2(child, target)


def compare_output_tree(actual_root: Path, expected_root: Path) -> tuple[list[str], list[str], list[str]]:
    actual_files: dict[str, bytes] = {}
    expected_files: dict[str, bytes] = {}

    if actual_root.exists():
        for path in actual_root.rglob("*"):
            if path.is_file() and not should_ignore(path):
                actual_files[path.relative_to(actual_root).as_posix()] = path.read_bytes()

    if expected_root.exists():
        for path in expected_root.rglob("*"):
            if path.is_file() and not should_ignore(path):
                expected_files[path.relative_to(expected_root).as_posix()] = path.read_bytes()

    actual_paths = set(actual_files)
    expected_paths = set(expected_files)

    missing_paths = sorted(expected_paths - actual_paths)
    unexpected_paths = sorted(actual_paths - expected_paths)
    changed_files = sorted(
        rel for rel in (actual_paths & expected_paths)
        if actual_files[rel] != expected_files[rel]
    )

    return missing_paths, unexpected_paths, changed_files


def run_fixture(fixture_id: str) -> FixtureRunResult:
    fixture_dir = REPO_ROOT / "fixtures" / fixture_id
    desired_state_path = fixture_dir / "desired_state.json"
    initial_out_dir = fixture_dir / "initial_out"
    expected_out_dir = fixture_dir / "expected_out"
    expected_result = load_expected_result(fixture_dir)

    expected_exit_code = expected_result.get("expected_exit_code")
    if not isinstance(expected_exit_code, int):
        raise CheckContractError(
            f"Fixture {fixture_id} must define integer expected_exit_code."
        )

    run_args = expected_result.get("run_args", [])
    if not isinstance(run_args, list) or not all(isinstance(arg, str) for arg in run_args):
        raise CheckContractError(f"Fixture {fixture_id} run_args must be a list of strings.")

    env_overrides = expected_result.get("env", {})
    if not isinstance(env_overrides, dict) or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in env_overrides.items()
    ):
        raise CheckContractError(f"Fixture {fixture_id} env must be an object of string pairs.")

    with tempfile.TemporaryDirectory(prefix=f"{fixture_id}-") as temp_dir_str:
        temp_dir = Path(temp_dir_str)
        input_dir = temp_dir / "input"
        out_dir = temp_dir / "out"
        input_dir.mkdir(parents=True, exist_ok=True)
        out_dir.mkdir(parents=True, exist_ok=True)

        if not desired_state_path.exists():
            raise CheckContractError(f"Fixture {fixture_id} missing desired_state.json")

        shutil.copy2(desired_state_path, input_dir / "desired_state.json")
        copy_tree_contents(initial_out_dir, out_dir)

        env = os.environ.copy()
        env.update(env_overrides)

        command = [sys.executable, str(REPO_ROOT / "src" / "reconcile.py"), *run_args]
        completed = subprocess.run(
            command,
            cwd=temp_dir,
            env=env,
            capture_output=True,
            text=True,
        )

        missing_paths, unexpected_paths, changed_files = compare_output_tree(
            out_dir, expected_out_dir
        )

        passed = (
            completed.returncode == expected_exit_code
            and not missing_paths
            and not unexpected_paths
            and not changed_files
        )

        return FixtureRunResult(
            fixture_id=fixture_id,
            passed=passed,
            expected_exit_code=expected_exit_code,
            actual_exit_code=completed.returncode,
            missing_paths=missing_paths,
            unexpected_paths=unexpected_paths,
            changed_files=changed_files,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )


def evaluate_direct_clauses(
    manifest: dict[str, Any],
    fixture_results: dict[str, FixtureRunResult],
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []

    for clause in manifest["clauses"]:
        check = clause["check"]
        if check["type"] != "fixture":
            continue

        fixture_id = check["fixture_id"]
        fixture_result = fixture_results[fixture_id]

        clause_result: dict[str, Any] = {
            "clause_id": clause["clause_id"],
            "result": "PASS" if fixture_result.passed else "FAIL",
            "source": "fixture",
            "fixture": fixture_id,
        }

        if not fixture_result.passed:
            clause_result["diagnostics"] = {
                "expected_exit_code": fixture_result.expected_exit_code,
                "actual_exit_code": fixture_result.actual_exit_code,
                "missing_paths": fixture_result.missing_paths,
                "unexpected_paths": fixture_result.unexpected_paths,
                "changed_files": fixture_result.changed_files,
                "stderr": fixture_result.stderr,
            }

        results.append(clause_result)

    return results


def evaluate_aggregate_clauses(
    manifest: dict[str, Any],
    direct_results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    direct_map = {entry["clause_id"]: entry for entry in direct_results}
    aggregates: list[dict[str, Any]] = []

    for clause in manifest["clauses"]:
        check = clause["check"]
        if check["type"] != "aggregate":
            continue

        requires = check["requires"]
        passed = all(direct_map[dependency]["result"] == "PASS" for dependency in requires)

        aggregates.append(
            {
                "clause_id": clause["clause_id"],
                "result": "PASS" if passed else "FAIL",
                "source": "aggregate",
                "depends_on": requires,
            }
        )

    return aggregates


def print_summary(clause_results: list[dict[str, Any]]) -> None:
    print("Mini Contract Check Results")
    print()

    failed_count = 0
    for result in clause_results:
        source_detail = result.get("fixture", "aggregate")
        print(f"{result['result']:<5} {result['clause_id']:<10} {source_detail}")
        if result["result"] == "FAIL":
            failed_count += 1

    print()
    print("Summary:")
    print(f"{len(clause_results)} clauses evaluated")
    print(f"{failed_count} failed")


def write_summary(manifest: dict[str, Any], clause_results: list[dict[str, Any]]) -> None:
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

    overall_result = "PASS" if all(result["result"] == "PASS" for result in clause_results) else "FAIL"

    summary = {
        "contract_id": manifest["contract"]["contract_id"],
        "contract_version": manifest["contract"]["contract_version"],
        "manifest_version": manifest["manifest_version"],
        "overall_result": overall_result,
        "fail_on_block": manifest.get("policy", {}).get("fail_on_block", True),
        "clauses": clause_results,
    }

    SUMMARY_PATH.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    try:
        manifest = load_manifest(MANIFEST_PATH)
        validate_manifest(manifest)

        fixture_ids: list[str] = []
        seen: set[str] = set()

        for clause in manifest["clauses"]:
            check = clause["check"]
            if check["type"] != "fixture":
                continue
            fixture_id = check["fixture_id"]
            if fixture_id not in seen:
                seen.add(fixture_id)
                fixture_ids.append(fixture_id)

        fixture_results = {
            fixture_id: run_fixture(fixture_id)
            for fixture_id in fixture_ids
        }

        direct_results = evaluate_direct_clauses(manifest, fixture_results)
        aggregate_results = evaluate_aggregate_clauses(manifest, direct_results)
        all_results = direct_results + aggregate_results

        write_summary(manifest, all_results)
        print_summary(all_results)

        return 1 if any(result["result"] == "FAIL" for result in all_results) else 0

    except CheckContractError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
