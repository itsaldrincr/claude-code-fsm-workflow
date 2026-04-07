# Changelog

All notable changes to `claude-code-fsm-workflow` are documented here.

Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html):

- **MAJOR** (`1.0.0` → `2.0.0`) — breaking changes to the hook contract, task file format, agent interface, or installer behavior. Requires user action to upgrade.
- **MINOR** (`0.1.0` → `0.2.0`) — new features that don't break existing installs (new agents, new hooks, new slash commands, new install modes).
- **PATCH** (`0.1.0` → `0.1.1`) — bug fixes, documentation improvements, internal refactors with no user-visible changes.

Sections within each release:
- **Added** — new features
- **Changed** — changes to existing behavior
- **Deprecated** — soon-to-be-removed features
- **Removed** — features deleted in this release
- **Fixed** — bug fixes
- **Security** — vulnerability fixes

---

## [Unreleased]

Changes on `main` that have not yet been cut as a tagged release.

### Added

- None yet.

### Changed

- None yet.

### Fixed

- None yet.

---

## [0.1.1] — 2026-04-08

Marketplace support, enforcement-first repositioning, and competitive comparison. No behavior changes to hooks, agents, or the installer logic — existing Mode 1 users who `git pull` + re-run `./install.sh` will not notice any functional difference.

Repo: https://github.com/itsaldrincr/claude-code-fsm-workflow
Release: https://github.com/itsaldrincr/claude-code-fsm-workflow/releases/tag/v0.1.1

### Added

- **Claude Code plugin marketplace support** via `.claude-plugin/marketplace.json` at the repo root and `.claude-plugin/plugin.json` inside the plugin directory. The package can now be installed with `/plugin marketplace add itsaldrincr/claude-code-fsm-workflow` + `/plugin install fsm-workflow`.
- **`/fsm-setup-hooks` slash command** — new command at `plugins/fsm-workflow/commands/fsm-setup-hooks.md` that walks users through installing the enforcement hooks after a marketplace install (Mode 2). The plugin marketplace format does not currently support user-level hook registration, so this command is declared mandatory for marketplace installs in the README.
- **Competitive comparison table** in the README comparing this package against `wshobson/agents`, `gsd-build/get-shit-done`, `Yeachan-Heo/oh-my-claudecode`, and `disler/claude-code-hooks-multi-agent-observability`. Covers enforcement properties (where this package wins) and breadth/ecosystem properties (where competitors win).
- **Three install modes** documented in the README: Mode 1 (full install via `install.sh`), Mode 2 (marketplace via `/plugin install` + `/fsm-setup-hooks`), Mode 3 (ask Claude via `INSTALL_FOR_CLAUDE.md`).
- **`CHANGELOG.md`** following Keep a Changelog format, with a backfilled `[0.1.0]` section and links to GitHub compare views.

### Changed

- **Repository restructured** to match the canonical Claude Code plugin layout. `agents/`, `commands/`, and `templates/` moved from the repo root to `plugins/fsm-workflow/`. The `hooks/` directory remains at the root because the plugin marketplace does not ship hooks. `install.sh` and `INSTALL_FOR_CLAUDE.md` updated for the new paths.
- **README positioning** rewritten around "discipline enforced by hooks, not personas." The opening bullets now lead with hook enforcement, context isolation, and nonce-proof reads — the properties that differentiate this package from persona-based multi-agent collections.

### Fixed

- None in this window.

---

## [0.1.0] — 2026-04-08

Initial public release.

Repo: https://github.com/itsaldrincr/claude-code-fsm-workflow
Release: https://github.com/itsaldrincr/claude-code-fsm-workflow/releases/tag/v0.1.0

### Added

- **22 subagents** covering the full FSM pipeline:
  - *Orchestration helpers*: `dispatcher`, `spec-writer`, `research-scout`
  - *Scouts* (read-only): `explore-scout`, `explore-superscout`, `file-lister`
  - *Synthesis*: `architect`
  - *Planning*: `task-planner`
  - *Workers*: `fsm-executor`, `fsm-integrator`
  - *Auditors*: `code-auditor`, `bug-scanner`, `dep-checker`
  - *Fixers*: `code-fixer`, `debugger`
  - *Test*: `test-runner`
  - *Bookkeeping*: `session-closer`, `session-handoff`, `doc-writer`
  - *Misc*: `mock-server`, `mockup-verifier`, `code-reviewer`
- **4 user-level hooks** enforcing the workflow's core discipline:
  - `block-map-writes.sh` — `PreToolUse` on `Write|Edit|MultiEdit`. Denies `MAP.md` writes from any agent other than `task-planner`, `session-closer`, or the orchestrator.
  - `block-worker-reads.sh` — `PreToolUse` on `Read`. Denies worker subagents from reading `MAP.md` or `CLAUDE.md` (enforces context isolation).
  - `block-model-override.sh` — `PreToolUse` on `Agent`. Denies callers that try to force a weaker model on a subagent via the Agent tool's `model` parameter.
  - `surface-map-on-start.sh` — `SessionStart`. Emits a compact status summary if `MAP.md` exists in the CWD, so the orchestrator notices recovery situations.
- **`/init-workflow` slash command** that bootstraps any project with `CLAUDE.md`, `.claude/settings.json`, and the discipline gate in one step.
- **Project templates** — `CLAUDE.md` (full coding discipline + task coordination SOP), `settings.json` with the discipline gate registered, and `discipline-gate.sh` PostToolUse hook that blocks `.py` / `.tsx?` writes with coding-discipline violations in a compact XML block reason.
- **Idempotent installer** (`install.sh`) — copies agents, hooks, commands, and templates into `~/.claude/`, merges hook registrations into `~/.claude/settings.json` via `jq`, backs up the existing settings before any change, and validates the final JSON. Safe to re-run.
- **`INSTALL_FOR_CLAUDE.md`** — paste-ready instruction set for installing the package by asking another Claude Code session to do it with safety checks at every step.
- **MIT license**.
- **README** with install instructions, usage notes, recovery instructions, uninstall steps, and troubleshooting.

### Known scope

- The `deploy-handler` agent was intentionally excluded from the public package because it contains infrastructure paths specific to the original author's fleet. If you want deploy automation, model it on the bookkeeper agents.
- No benchmarks, no observability/tracing layer, no DAG wave analyzer, no plugin marketplace support in `v0.1.0` itself (marketplace support lands in `[Unreleased]`).
- Claude Code only. No multi-runtime support (Codex, Gemini, etc.).

---

[Unreleased]: https://github.com/itsaldrincr/claude-code-fsm-workflow/compare/v0.1.1...HEAD
[0.1.1]: https://github.com/itsaldrincr/claude-code-fsm-workflow/releases/tag/v0.1.1
[0.1.0]: https://github.com/itsaldrincr/claude-code-fsm-workflow/releases/tag/v0.1.0
