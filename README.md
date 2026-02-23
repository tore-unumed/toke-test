# toke-test — Multi-Repo Issue Solver Agent

An automated GitHub Agentic Workflow (built with [`gh aw`](https://github.com/github/gh-aw))
that reads issues filed on **this** repository and implements the requested changes across one or
more side-repositories — then opens a descriptive PR in each one.

---

## How it works

```
Issue opened / labeled "agent"   OR   /solve comment
        │
        ▼
┌───────────────────────────────────┐
│  issue-solver (gh-aw workflow)    │  .github/workflows/issue-solver.md
│                                   │
│  1. Read agent.md (system map)    │
│  2. Read & understand the issue   │
│  3. Add "in-progress" label       │
│  4. For each target repo:         │
│     - Explore the codebase        │
│     - Clone, branch, implement    │
│     - Push branch                 │
│     - Open PR (target-repo)       │
│  5. Post summary comment          │
│  6. Transition to "in-review"     │
└───────────────────────────────────┘
```

1. **Write an issue** describing the feature or fix. Mention the target repository/repositories
   by name, e.g.:
   > Implement feature X in the `toke-util` repository.

2. **Add the `agent` label** (or post a comment starting with `/solve`).

3. The agentic workflow runs, posts status comments, creates branches in the relevant side-repos,
   commits AI-generated code, and opens PRs.

4. Labels transition automatically: `agent` → `in-progress` → `in-review`

---

## Setup

### 1 — Install `gh aw`

```bash
# Download the installer, inspect it, then run it
curl -sLO https://raw.githubusercontent.com/github/gh-aw/main/install-gh-aw.sh
# Review install-gh-aw.sh before executing
bash install-gh-aw.sh
```

### 2 — Secrets & Variables

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `AGENT_TOKEN` | Secret | **Yes** | PAT (or GitHub App token) with `repo` write access to every side-repo. |

Set it at **Settings → Secrets and variables → Actions → New repository secret**.

### 3 — Agent instructions (`agent.md`)

Edit [`agent.md`](agent.md) to describe:
- Your repository map (which repos exist and what they do).
- Coding standards and conventions.
- Architectural context the agent should know.

### 4 — Trigger

Label any issue with **`agent`**, or comment `/solve` to invoke the workflow.

---

## Workflow file

The workflow is defined in markdown + YAML frontmatter format:

```
.github/workflows/
  issue-solver.md        # Human-readable workflow definition (edit this)
  issue-solver.lock.yml  # Compiled GitHub Actions YAML (do not edit)
agent.md                 # System instructions for the agent
.gitattributes           # Marks lock files as generated
README.md                # This file
```

### Modifying the workflow

- **Agent instructions** (what the AI does) → edit the body of `issue-solver.md` — no
  recompilation needed.
- **Configuration** (triggers, tools, permissions) → edit the YAML frontmatter in
  `issue-solver.md`, then recompile:

  ```bash
  gh aw compile issue-solver
  ```

---

## Development

```bash
# Install gh aw
curl -sL https://raw.githubusercontent.com/github/gh-aw/main/install-gh-aw.sh | bash

# Validate and recompile
gh aw compile issue-solver

# List workflow status
gh aw list

# Debug a failed run (replace RUN_ID)
gh aw audit RUN_ID
```

