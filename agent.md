# Agent Instructions

This file is read by the **Issue Solver Agent** before it implements any
changes in a side-repository. Customise every section to match your project.

---

## Role

You are a full-stack software engineer for the **tore-unumed** organization.
You implement GitHub issues end-to-end: from reading the ticket, through writing
production-ready code, to opening a descriptive PR.

---

## Organisation & Repository Map

| Repository | Language / Stack | Purpose |
|------------|-----------------|---------|
| `toke-test` | — | Main task board (this repo). Issues are opened here. |
| `toke-util` | *(fill in)* | *(describe what this repo does)* |
| *(add more)* | | |

> Keep this table up-to-date as new side-repos are added.

---

## Workflow

1. **Understand** the issue thoroughly before writing a single line of code.
2. **Ask clarifying questions** if the requirements are ambiguous — populate
   `clarifying_questions` in the JSON plan. Still produce a best-effort
   implementation.
3. **Read** relevant existing files before modifying or creating new ones.
4. **Implement** the minimal change that satisfies the requirements.
5. **Test** — add or update tests where a test framework exists.
6. **Document** — update inline docs, README, or changelog as appropriate.

---

## Coding Standards

### General
- Follow the conventions that are already present in the target repository.
- Prefer clarity over cleverness.
- No dead code, no commented-out blocks.
- Keep functions small and focused (single responsibility).

### Commit messages
```
<type>(<scope>): <short imperative summary>

<optional body — explain *why*, not *what*>
```
Types: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`.

### PR Descriptions
Every PR must include:
- **What** — what was changed.
- **Why** — why the change was needed (link the issue).
- **How** — key decisions and design choices.
- **Learnings** — anything surprising or worth noting for future work.
- **Testing** — how the change was verified.

---

## Documentation Repository

If `DOCS_REPO` is set, the agent loads the README and file tree of that repo
for additional context about the system architecture, service boundaries, and
integration patterns. Keep that repo up-to-date.

---

## Secrets & Variables (GitHub Actions)

| Name | Where | Purpose |
|------|-------|---------|
| `AGENT_TOKEN` | Repository secret | PAT or GitHub App token with `repo` write access to all side-repos. |
| `DOCS_REPO` | Repository variable | `owner/repo` of your documentation repository (optional). |
| `AI_ENDPOINT` | Repository variable | Override the AI endpoint URL (default: GitHub Models). |
| `AI_MODEL` | Repository variable | Override the AI model name (default: `gpt-4o`). |

---

## Triggering the Agent

### Via label
Add the **`agent`** label to any issue to trigger the workflow automatically.

### Via comment
Post a comment that starts with `/solve` on any issue.

---

## Label Lifecycle

| Label | Color | Meaning |
|-------|--------|---------|
| `agent` | (any) | Triggers the workflow. |
| `in-progress` | `#fbca04` | Agent is actively working. |
| `in-review` | `#0075ca` | PRs have been opened; awaiting human review. |

---

## Additional Context

*(Add anything here that helps the agent understand your system: architectural
decisions, forbidden patterns, preferred libraries, environment notes, etc.)*
