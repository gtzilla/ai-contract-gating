#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Dict

DELETE_ENV_VAR = "MINI_RECONCILER_ALLOW_DELETIONS"
SCHEMA_VERSION = "0.2"
MANAGED_FILES = {"doc.txt", "meta.json"}


class ReconcileError(Exception):
    """Raised when the reconciler cannot safely complete."""


def normalize_doc_content(content: str) -> str:
    return content if content.endswith("\n") else content + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Mini Reconciler proof-of-concept")
    parser.add_argument(
        "--mode",
        choices=("normal", "reset"),
        default="normal",
        help="Execution mode. Reset still preserves manual files.",
    )
    return parser.parse_args()


def repo_paths() -> tuple[Path, Path]:
    input_path = Path("input") / "desired_state.json"
    out_root = Path("out")
    return input_path, out_root


def load_desired_state(input_path: Path) -> Dict[str, str]:
    if not input_path.exists():
        raise ReconcileError(f"Missing desired state file: {input_path}")

    try:
        payload = json.loads(input_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ReconcileError(f"Invalid JSON in {input_path}: {exc}") from exc

    if not isinstance(payload, dict):
        raise ReconcileError("Desired state must be a JSON object.")

    items = payload.get("items")
    if not isinstance(items, list):
        raise ReconcileError("Desired state must contain an 'items' array.")

    desired: Dict[str, str] = {}
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise ReconcileError(f"Desired item at index {index} must be an object.")

        unit_id = item.get("unit_id")
        content = item.get("content")

        if not isinstance(unit_id, str) or not unit_id.strip():
            raise ReconcileError(f"Desired item at index {index} has invalid unit_id.")
        if not isinstance(content, str):
            raise ReconcileError(f"Desired item '{unit_id}' has invalid content.")

        if unit_id in desired:
            raise ReconcileError(f"Duplicate unit_id: {unit_id}")

        desired[unit_id] = content

    return desired


def is_deletions_enabled() -> bool:
    return os.environ.get(DELETE_ENV_VAR) == "true"


def existing_unit_dirs(out_root: Path) -> Dict[str, Path]:
    if not out_root.exists():
        return {}
    return {path.name: path for path in out_root.iterdir() if path.is_dir()}


def build_meta_json(unit_id: str) -> str:
    return json.dumps(
        {
            "schema_version": SCHEMA_VERSION,
            "unit_id": unit_id,
        },
        indent=2,
        ensure_ascii=False,
    ) + "\n"


def write_text_atomically(target: Path, content: str) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)

    fd, temp_name = tempfile.mkstemp(prefix=".tmp-", dir=str(target.parent))
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(content)
        os.replace(temp_path, target)
    except Exception:
        try:
            temp_path.unlink(missing_ok=True)
        except Exception:
            pass
        raise


def write_managed_files(unit_dir: Path, unit_id: str, content: str) -> None:
    write_text_atomically(unit_dir / "doc.txt", normalize_doc_content(content))
    write_text_atomically(unit_dir / "meta.json", build_meta_json(unit_id))


def remove_stale_managed_files_only(unit_dir: Path) -> None:
    for filename in MANAGED_FILES:
        path = unit_dir / filename
        if path.exists():
            path.unlink()

    # Remove the unit directory only if it is now empty.
    try:
        next(unit_dir.iterdir())
    except StopIteration:
        unit_dir.rmdir()


def apply_desired_units(desired: Dict[str, str], out_root: Path) -> None:
    for unit_id, content in desired.items():
        unit_dir = out_root / unit_id
        unit_dir.mkdir(parents=True, exist_ok=True)
        write_managed_files(unit_dir, unit_id, content)


def handle_stale_units(existing: Dict[str, Path], desired: Dict[str, str]) -> None:
    stale_ids = sorted(set(existing) - set(desired))
    if not stale_ids:
        return

    if not is_deletions_enabled():
        stale_list = ", ".join(stale_ids)
        raise ReconcileError(
            f"Stale units exist while deletions are disabled: {stale_list}"
        )

    for unit_id in stale_ids:
        remove_stale_managed_files_only(existing[unit_id])


def run_normal_mode(desired: Dict[str, str], out_root: Path) -> None:
    existing = existing_unit_dirs(out_root)

    # Fail before changing anything if stale units exist and deletions are disabled.
    stale_ids = sorted(set(existing) - set(desired))
    if stale_ids and not is_deletions_enabled():
        stale_list = ", ".join(stale_ids)
        raise ReconcileError(
            f"Stale units exist while deletions are disabled: {stale_list}"
        )

    apply_desired_units(desired, out_root)
    handle_stale_units(existing_unit_dirs(out_root), desired)


def run_reset_mode(desired: Dict[str, str], out_root: Path) -> None:
    # INTENTIONAL FAILURE DEMO:
    # Reset mode now destructively replaces desired unit directories.
    # This will remove manual.txt and should fail MC-RST-1 / MC-GLOB-1.
    existing = existing_unit_dirs(out_root)

    stale_ids = sorted(set(existing) - set(desired))
    if stale_ids and not is_deletions_enabled():
        stale_list = ", ".join(stale_ids)
        raise ReconcileError(
            f"Stale units exist while deletions are disabled: {stale_list}"
        )

    for unit_id in desired:
        unit_dir = out_root / unit_id
        if unit_dir.exists():
            shutil.rmtree(unit_dir)

    apply_desired_units(desired, out_root)
    handle_stale_units(existing_unit_dirs(out_root), desired)


def main() -> int:
    args = parse_args()
    input_path, out_root = repo_paths()

    try:
        desired = load_desired_state(input_path)
        out_root.mkdir(parents=True, exist_ok=True)

        if args.mode == "normal":
            run_normal_mode(desired, out_root)
        elif args.mode == "reset":
            run_reset_mode(desired, out_root)
        else:
            raise ReconcileError(f"Unsupported mode: {args.mode}")

        return 0

    except ReconcileError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
