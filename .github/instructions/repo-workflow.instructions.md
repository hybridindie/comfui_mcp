---
description: "Use when doing git workflow tasks in this repo: commit, push, PR updates, review comment resolution, merge, and documentation follow-through."
name: "Repo Workflow Preferences"
---
# Repo Workflow Preferences

- Execute repository workflow requests directly when asked: create logical commits, push updates, address PR comments, and merge when checks are green.
- Every issue must be resolved by its own dedicated PR. Never include changes for two or more separate issues in the same PR unless those issues are explicitly part of the same Epic.
- Keep commit history clean and task-oriented: separate code fixes, scripts/tooling, and documentation into distinct commits when practical.
- When behavior/config changes affect operators or contributors, update relevant docs in the same workstream (`README.md`, `CONTRIBUTING.md`, `config.example.yaml`, `CLAUDE.md`) before finalizing.
- After addressing PR feedback, verify tests/lint for changed files, push, and post a concise PR update comment summarizing what changed.
- Before merging a PR, confirm CI checks are successful and review threads are resolved.
- Remove stale plan/design docs once features are implemented, unless the user asks to keep them as historical artifacts.
