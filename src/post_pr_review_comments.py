#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
SUMMARY_PATH = REPO_ROOT / "artifacts" / "check_contract_summary.json"
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


def get_existing_gate_comments(repo: str, pull_number: int, token: str) -> list[dict[str, Any]]:
    comments = paginate(f"{API_BASE}/repos/{repo}/pulls/{pull_number}/comments", token)
    return [
        comment
        for comment in comments
        if isinstance(comment.get("body"), str) and COMMENT_MARKER in comment["body"]
    ]


def delete_comment(repo: str, comment_id: int, token: str) -> None:
    github_request("DELETE", f"{API_BASE}/repos/{repo}/pulls/comments/{comment_id}", token)


def summarize_sequence(values: list[str], empty_label: str) -> str:
    if not values:
        return empty_label
    return ", ".join(f"`{value}`" for value in values)


def build_comment_body(summary: dict[str, Any]) -> str:
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

    lines = [
        COMMENT_MARKER,
        "Contract gate failed for this pull request.",
        "",
        "This is a file-scoped review comment generated from `check_contract_summary.json`.",
        "It points at the changed implementation surface, not an exact source line.",
        "",
        f"- overall_result: **{summary.get('overall_result', 'UNKNOWN')}**",
    ]

    if direct_failures:
        lines.extend(["", "**Failed direct clauses**", ""])
        for entry in direct_failures:
            diagnostics = entry.get("diagnostics", {})
            if not isinstance(diagnostics, dict):
                diagnostics = {}
            lines.extend(
                [
                    f"- **{entry.get('clause_id', 'UNKNOWN')}** (`{entry.get('fixture', 'unknown-fixture')}`)",
                    f"  - missing_paths: {summarize_sequence(diagnostics.get('missing_paths', []) if isinstance(diagnostics.get('missing_paths', []), list) else [], 'none')}",
                    f"  - unexpected_paths: {summarize_sequence(diagnostics.get('unexpected_paths', []) if isinstance(diagnostics.get('unexpected_paths', []), list) else [], 'none')}",
                    f"  - changed_files: {summarize_sequence(diagnostics.get('changed_files', []) if isinstance(diagnostics.get('changed_files', []), list) else [], 'none')}",
                ]
            )

    return "\n".join(lines)


def create_file_comment(repo: str, pull_number: int, head_sha: str, path: str, body: str, token: str) -> None:
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
        event_path = os.environ.get("GITHUB_EVENT_PATH")
        if not event_path:
            raise ReviewCommentError("GITHUB_EVENT_PATH is required.")
        event = load_json_object(Path(event_path), "GitHub event payload")

        pull_number, head_sha = get_pull_request_context(event)
        repo = get_repository(event)

        for comment in get_existing_gate_comments(repo, pull_number, token):
            comment_id = comment.get("id")
            if isinstance(comment_id, int):
                delete_comment(repo, comment_id, token)
