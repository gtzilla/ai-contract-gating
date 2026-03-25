#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
SUMMARY_PATH = REPO_ROOT / "artifacts" / "check_contract_summary.json"
MANIFEST_PATH = REPO_ROOT / "contract" / "manifest.yaml"
MANIFEST_REPO_PATH = "contract/manifest.yaml"
API_BASE = "https://api.github.com"
API_VERSION = "2022-11-28"
COMMENT_MARKER = "<!-- contract-gate-file-comment -->"


class ReviewCommentError(Exception):
    pass


def load_json_object(path: Path, missing_label: str) -> dict[str, Any]:
    if not path.exists():
        raise ReviewCommentError(f"Missing {missing_label}: {path}")

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ReviewCommentError(f"Invalid JSON in {path}: {exc}") from exc

    if not isinstance(payload, dict):
        raise ReviewCommentError(f"{missing_label} must contain a JSON object.")

    return payload


def github_request(
    method: str,
    url: str,
    token: str,
    payload: dict[str, Any] | None = None,
) -> Any:
    data: bytes | None = None
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": API_VERSION,
        "User-Agent": "ai-contract-gating-review-comments",
    }

    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    request = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers=headers,
    )

    try:
        with urllib.request.urlopen(request) as response:
            body = response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise ReviewCommentError(
            f"GitHub API {method} {url} failed: {exc.code} {detail}"
        ) from exc

    if not body:
        return None

    try:
        return json.loads(body.decode("utf-8"))
    except json.JSONDecodeError:
        return body.decode("utf-8")


def paginate(url: str, token: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    page = 1

    while True:
        separator = "&" if "?" in url else "?"
        page_url = f"{url}{separator}per_page=100&page={page}"
        payload = github_request("GET", page_url, token)
        if not isinstance(payload, list):
            raise ReviewCommentError(f"Expected list response from {page_url}")
        if not payload:
            break
        items.extend(entry for entry in payload if isinstance(entry, dict))
        if len(payload) < 100:
            break
        page += 1

    return items


def get_pull_request_context(event: dict[str, Any]) -> tuple[int, str]:
    pull_request = event.get("pull_request")
    if not isinstance(pull_request, dict):
        raise ReviewCommentError("This script only supports pull_request events.")

    number = pull_request.get("number") or event.get("number")
    if not isinstance(number, int):
        raise ReviewCommentError("Could not determine pull request number.")

    head = pull_request.get("head")
    if not isinstance(head, dict):
        raise ReviewCommentError("Pull request payload missing head block.")

    sha = head.get("sha")
    if not isinstance(sha, str) or not sha.strip():
        raise ReviewCommentError("Pull request head SHA missing.")

    return number, sha


def get_repository(event: dict[str, Any]) -> str:
    env_repo = os.environ.get("GITHUB_REPOSITORY")
    if env_repo:
        return env_repo

    repository = event.get("repository")
    if isinstance(repository, dict):
        full_name = repository.get("full_name")
        if isinstance(full_name, str) and full_name.strip():
            return full_name

    raise ReviewCommentError("Could not determine repository full name.")


def get_changed_files(repo: str, pull_number: int, token: str) -> list[dict[str, Any]]:
    return paginate(f"{API_BASE}/repos/{repo}/pulls/{pull_number}/files", token)


def choose_commentable_paths(files: list[dict[str, Any]]) -> list[str]:
    def collect(prefixes: tuple[str, ...]) -> list[str]:
        collected: list[str] = []
        for entry in files:
            path = entry.get("filename")
            status = entry.get("status")
            if (
                isinstance(path, str)
                and isinstance(status, str)
                and status != "removed"
                and (prefixes == ("",) or path.startswith(prefixes))
            ):
                collected.append(path)
        return collected

    for prefixes in (("src/",), ("contract/", ".github/workflows/"), ("",)):
        kept = collect(prefixes)
        if kept:
            seen: set[str] = set()
            ordered: list[str] = []
            for path in kept:
                if path not in seen:
                    seen.add(path)
                    ordered.append(path)
            return ordered

    return []


def get_existing_gate_comments(
    repo: str,
    pull_number: int,
    token: str,
) -> list[dict[str, Any]]:
    comments = paginate(f"{API_BASE}/repos/{repo}/pulls/{pull_number}/comments", token)
    return [
        comment
        for comment in comments
        if isinstance(comment.get("body"), str) and COMMENT_MARKER in comment["body"]
    ]


def delete_comment(repo: str, comment_id: int, token: str) -> None:
    github_request("DELETE", f"{API_BASE}/repos/{repo}/pulls/comments/{comment_id}", token)


def summarize_sequence(values: list[str], empty_label: str, *, code_style: bool = True) -> str:
    if not values:
        return empty_label
    if code_style:
        return ", ".join(f"`{value}`" for value in values)
    return ", ".join(values)


def normalize_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def find_clause_line_ranges(manifest_text: str, clause_ids: list[str]) -> dict[str, tuple[int, int]]:
    lines = manifest_text.splitlines()
    found_starts: list[tuple[str, int]] = []
    wanted = {clause_id for clause_id in clause_ids if clause_id}
    clause_id_pattern = re.compile(r"^-?\s*clause_id:\s*['\"]([^'\"]+)['\"]\s*$")

    for index, raw_line in enumerate(lines, start=1):
        stripped = raw_line.strip()
        match = clause_id_pattern.match(stripped)
        if not match:
            continue
        clause_id = match.group(1)
        if clause_id in wanted:
            found_starts.append((clause_id, index))

    found_starts.sort(key=lambda item: item[1])
    clause_ranges: dict[str, tuple[int, int]] = {}
    for position, (clause_id, start_line) in enumerate(found_starts):
        if position + 1 < len(found_starts):
            end_line = found_starts[position + 1][1] - 1
        else:
            end_line = len(lines)
            for index in range(start_line, len(lines) + 1):
                if lines[index - 1].strip().startswith("fixtures:"):
                    end_line = index - 1
                    break
        clause_ranges[clause_id] = (start_line, max(start_line, end_line))

    return clause_ranges


def load_manifest_metadata() -> tuple[str, dict[str, str], dict[str, tuple[int, int]]]:
    if not MANIFEST_PATH.exists():
        raise ReviewCommentError(f"Missing manifest: {MANIFEST_PATH}")

    manifest_text = MANIFEST_PATH.read_text(encoding="utf-8")

    try:
        payload = yaml.safe_load(manifest_text)
    except yaml.YAMLError as exc:
        raise ReviewCommentError(f"Invalid YAML in {MANIFEST_PATH}: {exc}") from exc

    if not isinstance(payload, dict):
        raise ReviewCommentError("Manifest must contain a top-level object.")

    contract = payload.get("contract")
    if not isinstance(contract, dict):
        raise ReviewCommentError("Manifest missing contract block.")

    contract_file = contract.get("contract_file")
    if not isinstance(contract_file, str) or not contract_file.strip():
        raise ReviewCommentError("Manifest missing contract.contract_file.")

    clauses = payload.get("clauses")
    if not isinstance(clauses, list):
        raise ReviewCommentError("Manifest clauses must be a list.")

    clause_titles: dict[str, str] = {}
    clause_ids: list[str] = []
    for clause in clauses:
        if not isinstance(clause, dict):
            continue
        clause_id = clause.get("clause_id")
        title = clause.get("title")
        if isinstance(clause_id, str) and clause_id.strip():
            clause_ids.append(clause_id)
            if isinstance(title, str) and title.strip():
                clause_titles[clause_id] = title

    clause_line_ranges = find_clause_line_ranges(manifest_text, clause_ids)
    return contract_file, clause_titles, clause_line_ranges


def build_repo_blob_url(repo: str, head_sha: str, repo_path: str) -> str:
    return f"https://github.com/{repo}/blob/{head_sha}/{repo_path}"


def build_contract_url(repo: str, head_sha: str, contract_file: str) -> str:
    return build_repo_blob_url(repo, head_sha, contract_file)


def build_manifest_url(repo: str, head_sha: str) -> str:
    return build_repo_blob_url(repo, head_sha, MANIFEST_REPO_PATH)


def build_clause_manifest_url(
    repo: str,
    head_sha: str,
    clause_id: str,
    clause_line_ranges: dict[str, tuple[int, int]],
) -> str | None:
    line_range = clause_line_ranges.get(clause_id)
    if not line_range:
        return None
    start_line, end_line = line_range
    base_url = build_manifest_url(repo, head_sha)
    if start_line == end_line:
        return f"{base_url}#L{start_line}"
    return f"{base_url}#L{start_line}-L{end_line}"


def format_clause_label(
    clause_id: str,
    clause_titles: dict[str, str],
    repo: str,
    head_sha: str,
    clause_line_ranges: dict[str, tuple[int, int]],
) -> str:
    clause_title = clause_titles.get(clause_id)
    label_text = f"{clause_id} — {clause_title}" if clause_title else clause_id
    clause_url = build_clause_manifest_url(repo, head_sha, clause_id, clause_line_ranges)
    if clause_url:
        return f"[{label_text}]({clause_url})"
    return label_text


def build_comment_body(
    summary: dict[str, Any],
    repo: str,
    head_sha: str,
    contract_file: str,
    clause_titles: dict[str, str],
    clause_line_ranges: dict[str, tuple[int, int]],
) -> str:
    clauses = summary.get("clauses", [])
    if not isinstance(clauses, list):
        raise ReviewCommentError("Summary clauses must be a list.")

    direct_failures = [
        entry
        for entry in clauses
        if isinstance(entry, dict)
        and entry.get("result") == "FAIL"
        and entry.get("source") == "fixture"
    ]
    aggregate_failures = [
        entry
        for entry in clauses
        if isinstance(entry, dict)
        and entry.get("result") == "FAIL"
        and entry.get("source") == "aggregate"
    ]

    contract_url = build_contract_url(repo, head_sha, contract_file)
    manifest_url = build_manifest_url(repo, head_sha)

    lines = [
        COMMENT_MARKER,
        "Contract gate failed for this pull request.",
        "",
        "This is a file-scoped review comment generated from `check_contract_summary.json`.",
        "It points at the changed implementation surface, not an exact source line.",
        "",
        f"Contract under test: [`{contract_file}`]({contract_url})",
        f"Manifest under test: [`{MANIFEST_REPO_PATH}`]({manifest_url})",
        "In plain English: this PR changed a managed mutation surface, and the contract fixtures detected behavior drift that now needs review against the preserved rules in the contract and manifest.",
        "",
        f"- overall_result: **{summary.get('overall_result', 'UNKNOWN')}**",
    ]

    if direct_failures:
        lines.extend(["", "**Failed direct clauses**", ""])
        for entry in direct_failures:
            diagnostics = entry.get("diagnostics", {})
            if not isinstance(diagnostics, dict):
                diagnostics = {}

            missing_paths = normalize_string_list(diagnostics.get("missing_paths"))
            unexpected_paths = normalize_string_list(diagnostics.get("unexpected_paths"))
            changed_files = normalize_string_list(diagnostics.get("changed_files"))
            stderr = diagnostics.get("stderr", "")

            clause_id = entry.get("clause_id", "UNKNOWN")
            label = format_clause_label(
                clause_id,
                clause_titles,
                repo,
                head_sha,
                clause_line_ranges,
            )

            lines.extend(
                [
                    f"- **{label}** (`{entry.get('fixture', 'unknown-fixture')}`)",
                    f"  - missing_paths: {summarize_sequence(missing_paths, 'none')}",
                    f"  - unexpected_paths: {summarize_sequence(unexpected_paths, 'none')}",
                    f"  - changed_files: {summarize_sequence(changed_files, 'none')}",
                ]
            )
            if isinstance(stderr, str) and stderr.strip():
                compact_stderr = " ".join(stderr.strip().splitlines())
                lines.append(f"  - stderr: `{compact_stderr[:220]}`")

    if aggregate_failures:
        lines.extend(["", "**Failed aggregate clauses**", ""])
        for entry in aggregate_failures:
            depends_on = normalize_string_list(entry.get("depends_on"))
            clause_id = entry.get("clause_id", "UNKNOWN")
            label = format_clause_label(
                clause_id,
                clause_titles,
                repo,
                head_sha,
                clause_line_ranges,
            )
            linked_dependencies = [
                format_clause_label(
                    dependency,
                    clause_titles,
                    repo,
                    head_sha,
                    clause_line_ranges,
                )
                for dependency in depends_on
            ]
            lines.append(
                f"- **{label}** depends on {summarize_sequence(linked_dependencies, 'none', code_style=False)}"
            )

    lines.extend(
        [
            "",
            "This comment is attached to a changed file in the implementation surface so reviewers can jump directly into the affected code area.",
        ]
    )

    return "\n".join(lines)


def create_file_comment(
    repo: str,
    pull_number: int,
    head_sha: str,
    path: str,
    body: str,
    token: str,
) -> None:
    github_request(
        "POST",
        f"{API_BASE}/repos/{repo}/pulls/{pull_number}/comments",
        token,
        {
            "body": body,
            "commit_id": head_sha,
            "path": path,
            "subject_type": "file",
        },
    )


def main() -> int:
    try:
        token = os.environ.get("GITHUB_TOKEN")
        if not token:
            raise ReviewCommentError("GITHUB_TOKEN is required.")

        summary = load_json_object(SUMMARY_PATH, "contract summary")
        contract_file, clause_titles, clause_line_ranges = load_manifest_metadata()
        event_path = os.environ.get("GITHUB_EVENT_PATH")
        if not event_path:
            raise ReviewCommentError("GITHUB_EVENT_PATH is required.")
        event = load_json_object(Path(event_path), "GitHub event payload")

        pull_number, head_sha = get_pull_request_context(event)
        repo = get_repository(event)

        existing_comments = get_existing_gate_comments(repo, pull_number, token)
        for comment in existing_comments:
            comment_id = comment.get("id")
            if isinstance(comment_id, int):
                delete_comment(repo, comment_id, token)

        if summary.get("overall_result") != "FAIL":
            print("Contract gate passed; no file-scoped rejection comments created.")
            return 0

        changed_files = get_changed_files(repo, pull_number, token)
        commentable_paths = choose_commentable_paths(changed_files)
        if not commentable_paths:
            print("No changed files available for file-scoped review comments.")
            return 0

        body = build_comment_body(
            summary,
            repo,
            head_sha,
            contract_file,
            clause_titles,
            clause_line_ranges,
        )
        for path in commentable_paths:
            create_file_comment(repo, pull_number, head_sha, path, body, token)
            print(f"Created contract gate file comment on {path}")

        return 0
    except ReviewCommentError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
