#!/usr/bin/env python3
"""
Multi-Repo Issue Solving Agent
===============================
Triggered by the issue-solver workflow, this script:

1. Reads an issue from the main (toke-test) repository.
2. Identifies target side-repositories mentioned in the issue body/title.
3. Optionally loads context from a documentation repository.
4. Uses the GitHub Models AI API (OpenAI-compatible) to plan & generate
   concrete code changes for each target repository.
5. Clones each side-repo, applies the generated changes, and opens a
   Pull Request with a rich description (what / why / plan / learnings).
6. Posts a summary comment on the original issue and transitions labels
   from "in-progress" → "in-review".
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional

import requests
from github import Github, GithubException

# ── Configuration ─────────────────────────────────────────────────────────────
GITHUB_TOKEN: str = os.environ["GITHUB_TOKEN"]
ORG_NAME: str = os.environ.get("ORG_NAME", "")
REPO_NAME: str = os.environ.get("REPO_NAME", "")
ISSUE_NUMBER: int = int(os.environ.get("ISSUE_NUMBER", "0"))
DOCS_REPO: str = os.environ.get("DOCS_REPO", "")
AI_ENDPOINT: str = os.environ.get(
    "AI_ENDPOINT", "https://models.inference.ai.azure.com"
)
AI_MODEL: str = os.environ.get("AI_MODEL", "gpt-4o")

g = Github(GITHUB_TOKEN)


# ── AI helper ─────────────────────────────────────────────────────────────────

def call_ai(messages: list[dict], max_tokens: int = 4096) -> str:
    """Call the GitHub Models (OpenAI-compatible) chat completion endpoint."""
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": AI_MODEL,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": 0.1,
    }
    resp = requests.post(
        f"{AI_ENDPOINT}/chat/completions",
        headers=headers,
        json=payload,
        timeout=180,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


# ── Repository discovery ───────────────────────────────────────────────────────

_REPO_PATTERNS = [
    # 'toke-util' repo / repository
    r"""['\"`]([a-z0-9][a-z0-9_-]*)['\"`]\s+repo(?:sitory)?""",
    # repo/repository 'toke-util'
    r"""repo(?:sitory)?\s+['\"`]([a-z0-9][a-z0-9_-]*)['\"`]""",
    # in `toke-util`
    r"""`([a-z0-9][a-z0-9_-]*)`""",
    # org/repo  or  @org/repo
    r"""@?[a-z0-9_-]+/([a-z0-9][a-z0-9_-]*)""",
]


def _regex_extract_repos(text: str) -> set[str]:
    found: set[str] = set()
    for pattern in _REPO_PATTERNS:
        for match in re.findall(pattern, text, re.IGNORECASE):
            found.add(match.lower())
    return found


def _ai_extract_repos(text: str, org: str) -> list[str]:
    """Ask the AI to extract repository names from the issue text."""
    messages = [
        {
            "role": "system",
            "content": (
                f"You are a GitHub issue analyzer for the '{org}' organization. "
                "Extract the names of side-repositories that need code changes to "
                "resolve the issue. Return only repository short-names (not "
                "owner/repo format), one per line. If none are mentioned explicitly, "
                "return an empty response."
            ),
        },
        {
            "role": "user",
            "content": f"Issue text:\n\n{text[:4000]}",
        },
    ]
    try:
        response = call_ai(messages, max_tokens=300)
        return [ln.strip().lower() for ln in response.splitlines() if ln.strip()]
    except Exception as exc:  # noqa: BLE001
        print(f"[warn] AI repo extraction failed: {exc}")
        return []


def extract_target_repos(issue_title: str, issue_body: str, org: str) -> list[str]:
    """Return verified repository names that should receive changes."""
    text = f"{issue_title}\n{issue_body}"

    candidates = _regex_extract_repos(text)
    candidates.update(_ai_extract_repos(text, org))

    # Strip words that are obviously not repo names
    noise = {
        "the", "a", "an", "this", "that", "main", "github", "git",
        "issue", "pr", "fix", "feature", "repo", "repository",
    }
    candidates -= noise

    valid: list[str] = []
    for name in sorted(candidates):
        try:
            g.get_repo(f"{org}/{name}")
            valid.append(name)
        except GithubException:
            pass  # repo doesn't exist or no access → skip

    return valid


# ── Repository context builder ────────────────────────────────────────────────

def _read_file_safe(repo, path: str, max_bytes: int = 3000) -> str:
    try:
        content = repo.get_contents(path)
        raw = content.decoded_content.decode("utf-8", errors="replace")
        return raw[:max_bytes]
    except Exception:  # noqa: BLE001
        return ""


def get_repo_context(repo_full_name: str) -> str:
    """Build a concise context string describing the repository."""
    repo = g.get_repo(repo_full_name)
    parts: list[str] = [f"# Repository: {repo_full_name}"]

    if repo.description:
        parts.append(f"Description: {repo.description}")

    readme = _read_file_safe(repo, "README.md")
    if readme:
        parts.append(f"\n## README (excerpt)\n{readme[:2000]}")

    # File tree (up to 80 entries)
    try:
        tree = repo.get_git_tree(repo.default_branch, recursive=True)
        files = [i.path for i in tree.tree if i.type == "blob"]
        parts.append(
            f"\n## File tree ({len(files)} files)\n" + "\n".join(files[:80])
        )
    except Exception:  # noqa: BLE001
        pass

    return "\n".join(parts)


# ── AI implementation planner ─────────────────────────────────────────────────

_PLAN_SYSTEM = """\
You are a senior software engineer implementing GitHub issues across multiple \
repositories.

Given an issue description and the target repository's context, produce a \
complete implementation plan as a **single JSON object** (no markdown fences, \
no extra text):

{{
  "branch_name": "feature/<kebab-case-description>",
  "pr_title": "Short, imperative PR title",
  "pr_description": "Detailed markdown description: ## What, ## Why, ## How, ## Learnings",
  "files": [
    {{
      "path": "relative/path/to/file.ext",
      "action": "create | modify | delete",
      "content": "<full file content for create/modify; empty string for delete>",
      "description": "What changed and why"
    }}
  ],
  "clarifying_questions": [],
  "implementation_notes": "Any gotchas or future improvement ideas"
}}

Rules:
- Provide *complete* file contents (not diffs or snippets).
- Follow the coding conventions evident in the repository.
- If the issue is ambiguous, populate clarifying_questions and still provide a \
  best-effort implementation.
- Agent instructions (if any) take precedence over your defaults.
"""


def plan_implementation(
    issue_title: str,
    issue_body: str,
    repo_context: str,
    agent_instructions: str,
) -> dict:
    """Ask the AI for a full implementation plan for one repository."""
    system_prompt = _PLAN_SYSTEM
    if agent_instructions.strip():
        system_prompt += f"\n\n## Agent Instructions\n{agent_instructions}"

    messages = [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": (
                f"## Issue title\n{issue_title}\n\n"
                f"## Issue body\n{issue_body}\n\n"
                f"## Repository context\n{repo_context}\n\n"
                "Implement the changes required by this issue."
            ),
        },
    ]

    raw = call_ai(messages, max_tokens=8192)

    # Attempt to extract the JSON object from the response
    json_match = re.search(r"\{.*\}", raw, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group())
        except json.JSONDecodeError:
            pass

    # Fallback — treat the whole response as a prose description
    return {
        "branch_name": f"agent/issue-{ISSUE_NUMBER}",
        "pr_title": f"Implement: {issue_title}",
        "pr_description": raw,
        "files": [],
        "clarifying_questions": [],
        "implementation_notes": "AI response was not valid JSON; no files changed.",
    }


# ── Git / PR helpers ──────────────────────────────────────────────────────────

def _git(repo_dir: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo_dir), *args],
        check=True,
        capture_output=True,
    )


def implement_in_repo(
    org: str,
    repo_name: str,
    issue_title: str,
    issue_body: str,
    agent_instructions: str,
    main_repo_ref: str,
) -> Optional[str]:
    """Clone a side-repo, apply AI-generated changes, push, and open a PR.

    Returns the URL of the created PR, or None if nothing was done.
    """
    repo_full_name = f"{org}/{repo_name}"
    print(f"\n{'='*60}\nProcessing: {repo_full_name}\n{'='*60}")

    repo_context = get_repo_context(repo_full_name)

    print("  → Planning implementation via AI …")
    plan = plan_implementation(issue_title, issue_body, repo_context, agent_instructions)

    if plan.get("clarifying_questions"):
        print(f"  ⚠ Agent questions: {plan['clarifying_questions']}")

    if not plan.get("files"):
        print("  → No file changes planned; skipping this repo.")
        return None

    with tempfile.TemporaryDirectory() as tmpdir:
        repo_dir = Path(tmpdir) / repo_name
        clone_url = (
            f"https://x-access-token:{GITHUB_TOKEN}"
            f"@github.com/{repo_full_name}.git"
        )

        print(f"  → Cloning {repo_full_name} …")
        subprocess.run(
            ["git", "clone", "--depth=1", clone_url, str(repo_dir)],
            check=True,
            capture_output=True,
        )

        _git(repo_dir, "config", "user.name", "Issue Solver Agent")
        _git(repo_dir, "config", "user.email", "agent@github-actions.com")

        # Sanitise and create branch
        raw_branch = plan.get("branch_name", f"agent/issue-{ISSUE_NUMBER}")
        branch = re.sub(r"[^a-z0-9/_-]", "-", raw_branch.lower()).strip("-")
        if str(ISSUE_NUMBER) not in branch:
            branch = f"{branch}-{ISSUE_NUMBER}"
        _git(repo_dir, "checkout", "-b", branch)

        # Apply file changes
        for fc in plan.get("files", []):
            fpath = repo_dir / fc["path"]
            action = fc.get("action", "modify")
            if action == "delete":
                if fpath.exists():
                    fpath.unlink()
                    print(f"  🗑  Deleted:   {fc['path']}")
            else:
                fpath.parent.mkdir(parents=True, exist_ok=True)
                fpath.write_text(fc.get("content", ""), encoding="utf-8")
                verb = "Created" if action == "create" else "Modified"
                print(f"  ✏  {verb}: {fc['path']}")

        # Commit
        _git(repo_dir, "add", ".")
        commit_msg = (
            f"{plan.get('pr_title', f'Implement: {issue_title}')}\n\n"
            f"Closes {main_repo_ref}#{ISSUE_NUMBER}"
        )
        _git(repo_dir, "commit", "-m", commit_msg)

        # Push
        print(f"  → Pushing branch '{branch}' …")
        _git(repo_dir, "push", "origin", branch)

        # Open PR
        print("  → Creating PR …")
        gh_repo = g.get_repo(repo_full_name)
        pr_body = plan.get("pr_description", "")
        pr_body += (
            "\n\n---\n"
            "_Automatically created by the [Issue Solver Agent]"
            f"(https://github.com/{main_repo_ref}/blob/main/.github/scripts/issue_agent.py)._\n"
            f"_Resolves {main_repo_ref}#{ISSUE_NUMBER}: {issue_title}_"
        )
        if plan.get("implementation_notes"):
            pr_body += (
                f"\n\n**Implementation notes:** {plan['implementation_notes']}"
            )

        pr = gh_repo.create_pull(
            title=plan.get("pr_title", f"Implement: {issue_title}"),
            body=pr_body,
            head=branch,
            base=gh_repo.default_branch,
        )
        print(f"  ✅ PR created: {pr.html_url}")
        return pr.html_url


# ── Label helpers ─────────────────────────────────────────────────────────────

def _ensure_label(repo, name: str, color: str, description: str = ""):
    try:
        return repo.get_label(name)
    except GithubException:
        return repo.create_label(name, color, description)


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    if not ISSUE_NUMBER:
        print("ISSUE_NUMBER is not set. Exiting.")
        sys.exit(1)

    org = ORG_NAME or REPO_NAME.split("/")[0]
    print(f"Issue Solver Agent — issue #{ISSUE_NUMBER} in {REPO_NAME}")

    main_repo = g.get_repo(REPO_NAME)
    issue = main_repo.get_issue(ISSUE_NUMBER)

    issue_title = issue.title
    issue_body = issue.body or ""

    print(f"Title: {issue_title}")

    # ── Labels: mark as in-progress ──────────────────────────────────────────
    in_progress = _ensure_label(
        main_repo, "in-progress", "fbca04", "Being worked on by the agent"
    )
    issue.add_to_labels(in_progress)

    # ── Initial comment ───────────────────────────────────────────────────────
    issue.create_comment(
        "🤖 **Issue Solver Agent** — I'm on it!\n\n"
        "Analysing the issue and identifying target repositories…"
    )

    # ── Load agent instructions ───────────────────────────────────────────────
    agent_md = Path("agent.md")
    agent_instructions = agent_md.read_text("utf-8") if agent_md.exists() else ""

    # Optionally augment with a docs repo
    if DOCS_REPO:
        try:
            docs_context = get_repo_context(DOCS_REPO)
            agent_instructions = (
                f"{agent_instructions}\n\n"
                f"## Documentation Repository Context\n{docs_context}"
            )
        except Exception as exc:  # noqa: BLE001
            print(f"[warn] Could not load docs repo '{DOCS_REPO}': {exc}")

    # ── Discover target repositories ──────────────────────────────────────────
    target_repos = extract_target_repos(issue_title, issue_body, org)

    if not target_repos:
        issue.create_comment(
            "🤖 **Issue Solver Agent** — I couldn't identify any target "
            "repositories in this issue.\n\n"
            "Please mention the repository name(s) in the issue body, e.g.:\n"
            "> Implement feature X in the `toke-util` repository."
        )
        issue.remove_from_labels(in_progress)
        return

    print(f"Target repos: {target_repos}")
    issue.create_comment(
        f"🤖 **Issue Solver Agent** — Found {len(target_repos)} target "
        f"repo(s): {', '.join(f'`{r}`' for r in target_repos)}.\n\n"
        "Starting implementation…"
    )

    # ── Implement in each repo ────────────────────────────────────────────────
    pr_urls: list[tuple[str, str]] = []
    errors: list[tuple[str, str]] = []

    for repo_name in target_repos:
        try:
            url = implement_in_repo(
                org=org,
                repo_name=repo_name,
                issue_title=issue_title,
                issue_body=issue_body,
                agent_instructions=agent_instructions,
                main_repo_ref=REPO_NAME,
            )
            if url:
                pr_urls.append((repo_name, url))
        except Exception as exc:  # noqa: BLE001
            print(f"[error] {repo_name}: {exc}")
            errors.append((repo_name, str(exc)))

    # ── Summary comment ───────────────────────────────────────────────────────
    lines = ["🤖 **Issue Solver Agent** — Done!\n"]

    if pr_urls:
        lines.append("## Pull Requests\n")
        for rname, url in pr_urls:
            lines.append(f"- **{rname}**: {url}")

    if errors:
        lines.append("\n## Errors\n")
        for rname, err in errors:
            lines.append(f"- **{rname}**: `{err}`")

    issue.create_comment("\n".join(lines))

    # ── Labels: transition to in-review ──────────────────────────────────────
    try:
        issue.remove_from_labels(in_progress)
    except GithubException:
        pass

    if pr_urls:
        in_review = _ensure_label(
            main_repo, "in-review", "0075ca", "PR under review"
        )
        issue.add_to_labels(in_review)


if __name__ == "__main__":
    main()
