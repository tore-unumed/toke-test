# toke-test — Multi-Repo Issue Solver Agent

An automated GitHub Actions workflow that reads issues filed on **this**
repository and, using AI, implements the requested changes across one or more
side-repositories — then opens a PR in each one.

---

## How it works

```
Issue opened / labeled "agent"
        │
        ▼
┌───────────────────────┐
│  issue-solver workflow│  (.github/workflows/issue-solver.yml)
└───────────┬───────────┘
            │
            ▼
┌───────────────────────┐
│  issue_agent.py       │  reads issue, extracts target repos,
│                       │  calls GitHub Models AI, clones repos,
│                       │  applies changes, opens PRs
└───────────┬───────────┘
            │
            ▼
   PR in toke-util  ·  PR in toke-frontend  ·  …
```

1. **Write an issue** describing the feature or fix.  Mention the target
   repository/repositories by name, e.g.:
   > Implement feature X in the `toke-util` repository.

2. **Add the `agent` label** (or post a comment starting with `/solve`).

3. The workflow runs, the agent posts status comments, creates branches in
   the relevant side-repos, commits the AI-generated code, and opens PRs.

4. Labels transition automatically:
   `agent` → `in-progress` → `in-review`

---

## Setup

### 1 — Secrets & Variables

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `AGENT_TOKEN` | Secret | **Yes** | PAT (or GitHub App token) with `repo` write access to every side-repo. |
| `DOCS_REPO` | Variable | No | `owner/repo` of a documentation repo the agent reads for context. |
| `AI_ENDPOINT` | Variable | No | Override the AI endpoint (default: `https://models.inference.ai.azure.com`). |
| `AI_MODEL` | Variable | No | Override the model name (default: `gpt-4o`). |

Set secrets at **Settings → Secrets and variables → Actions → New repository secret**.

### 2 — Agent instructions (`agent.md`)

Edit [`agent.md`](agent.md) to describe:
- Your repository map (which repos exist and what they do).
- Coding standards and conventions.
- Any architectural context the agent should know.

### 3 — Trigger

Label any issue with **`agent`**, or comment `/solve` to invoke the workflow.

---

## File layout

```
.github/
  workflows/
    issue-solver.yml   # Workflow definition
  scripts/
    issue_agent.py     # Agent logic (Python 3.12)
agent.md               # System instructions for the AI agent
README.md              # This file
```

---

## Customisation

- **Add more repos** — just mention them in an issue; the agent will verify
  they exist in the organisation before attempting any changes.
- **Change AI model** — set the `AI_MODEL` repository variable.
- **Extend instructions** — update `agent.md`; changes take effect on the
  next workflow run.
- **Documentation repo** — set `DOCS_REPO` to a repo that describes your
  system architecture, and the agent will include it as context.
