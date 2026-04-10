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

## [1.1.0] — 2026-04-11

Pipeline automation engine, per-wave advisor gate, enforcement hooks, and 315 tests.

Repo: https://github.com/itsaldrincr/claude-code-fsm-workflow
Release: https://github.com/itsaldrincr/claude-code-fsm-workflow/releases/tag/v1.1.0

### Added

- **`src/fsm_core/` — 10 Python modules** powering the automated dispatch pipeline:
  - `action_decider.py` — pure-function 6-level priority cascade (BLOCKED → REVIEW → PENDING → ALL_DONE → WAITING → ERROR)
  - `advisor_parser.py` — APPROVE/REVISE verdict parsing, revision round counting
  - `subprocess_dispatch.py` — worker, advisor, and REVISE dispatch via `claude` CLI with model-tier routing
  - `map_io.py` — atomic MAP.md status flips under lockfile with status validation
  - `map_reader.py` — combines MAP.md statuses with task file frontmatter
  - `map_lock.py` — atomic lockfile context manager with stale-lock reclaim
  - `dag_waves.py` — DAG wave computation and cycle detection
  - `session_state.py` — session state JSON projection
  - `trace.py` — JSONL event trace appender
  - `frontmatter.py` — shared task file frontmatter parser
- **`scripts/orchestrate.py`** — step-function CLI for automated dispatch. Reads MAP.md, decides action, dispatches workers/advisor, updates state. Exit codes: 0=all done, 1=action taken, 2=waiting, 3=blocked, 4=error. Stateless between invocations.
- **`scripts/atomize_task.py`** — mandatory task atomizer. Splits multi-step tasks into single-step sub-tasks with letter suffixes, chains dependencies, rewrites MAP.md. Rollback on failure restores parents and MAP.md.
- **`hooks/validate_map_transition.py`** — PreToolUse hook on Edit targeting MAP.md. Blocks invalid state transitions (e.g. PENDING→DONE) using hardcoded `VALID_TRANSITIONS` dict. Emits deny with specific reason.
- **`hooks/nudge_orchestrate.py`** — PostToolUse hook on Read of MAP.md. Nudges the orchestrator toward `scripts/orchestrate.py` when actionable tasks (PENDING/REVIEW) exist.
- **315 tests** covering all modules: fsm_core (113), orchestrate (26), atomize (21), hook deny/allow logic (44), frontmatter (9), plus existing repo_map (48), usage_tracker (64).

### Changed

- **Advisor operates per-wave, not per-task.** Workers cascade freely within a wave (a→b→c chains complete without interruption). ONE advisor (Opus) reviews the entire wave output at the boundary. APPROVE opens the gate to wave N+1. REVISE targets specific tasks for re-dispatch (max 3 rounds, then BLOCKED).
- **`advisor.md` agent** rewritten for wave-gate input (list of task files per wave, not single task).
- **`dispatcher.md` agent** updated with per-wave advisor loop, wave completion detection, and wave-gate dispatch template.
- **`install.sh`** extended to copy `src/fsm_core/`, pipeline-enforce hooks, and agent definitions. Now 9 hook registrations (6 repo-map + 1 fsm-trace + 2 pipeline-enforce).
- **`CLAUDE.md` template** updated with per-wave advisor gate docs, orchestrate.py section, enforcement hooks section, `scripts/` inventory.
- **`dispatch_revise`** now uses the task's original `dispatch_role` instead of hardcoding haiku. Integrator tasks get sonnet on REVISE.

### Fixed

- `dispatch_revise` return value was silently discarded — now captured; non-zero exit flips task to FAILED.
- `_append_revise_entry` prepended instead of appended when Registers had existing entries.
- `_map_replace_parent_entry` regex matched sub-task IDs (e.g. `task_801a` when targeting `task_801`) — added negative lookahead.
- `_MapRewriteInput.parent_depends` used `# type: ignore` — fixed to `list[str] | None`.
- `read_map_statuses` returned unrecognized status strings without warning — now validates against `VALID_STATUSES`.
- `advisor_parser` empty stdout returned ambiguous guidance string — now returns `"empty response"`.
- `nudge_orchestrate` used `Path.cwd()` instead of hook event's `cwd` field.
- `atomize_tasks` had no rollback — now restores parent files, sub-task files, and MAP.md on failure.
- `_run_advisor_cycle` didn't check advisor subprocess exit code — burned REVISE rounds on dispatch failures.
- `_handle_revise` exceeded 20-line function limit — extracted `_flip_to_blocked` and `_run_revise_dispatch`.
- `logging.basicConfig` called at module level in `atomize_task.py` — moved to `main()`.
- `validate_map_transition` logged parse errors at DEBUG — changed to WARNING.
- `_find_task_file` silently picked first of multiple glob matches — now logs warning.
- File Directory regex lookahead failed on double-newline section boundaries — changed to `\n+`.

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

[1.1.0]: https://github.com/itsaldrincr/claude-code-fsm-workflow/compare/v0.1.1...v1.1.0
[0.1.1]: https://github.com/itsaldrincr/claude-code-fsm-workflow/releases/tag/v0.1.1
[0.1.0]: https://github.com/itsaldrincr/claude-code-fsm-workflow/releases/tag/v0.1.0
