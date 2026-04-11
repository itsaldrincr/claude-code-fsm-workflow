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

## [1.1.1] — 2026-04-11

Deterministic audit scripts replace two of the three LLM auditors. `orchestrate.py` gains a post-ALL_DONE audit gate. Bug fix to `atomize_task.py` for cross-parent dependency rewriting. Version drift in `plugin.json` / `marketplace.json` (`0.1.1` → `1.1.1`) fixed to match the tagged release scheme.

Repo: https://github.com/itsaldrincr/claude-code-fsm-workflow

### Added

- **`scripts/audit_discipline.py`** — AST-based coding discipline checker (436 lines). Replaces the `code-auditor` LLM subagent. Enforces F1–F10 + F22 from CLAUDE.md: max 2 params, max 20 body lines, max 3 public methods, type hints, no `print()`, no silent `except`, UPPER_SNAKE_CASE constants, import grouping, unused imports, bool naming via `bool` type annotation, graceful skip on syntax-error files. Uses `ast.NodeVisitor`. Exit 0 clean / 1 violations / 2 error. Output format: `file:line:scope -- rule -- detail`, sorted by (file, line) for determinism. Skips `from __future__ import annotations` correctly.
- **`scripts/check_deps.py`** — Import resolution + unused-import checker (330 lines). Replaces the `dep-checker` LLM subagent. Uses `importlib.util.find_spec` for resolution; honors `__all__` for exported-name verification; handles relative imports, PEP 420 namespace packages, and star imports gracefully. Prepends `Path.cwd()` to `sys.path` at startup so local-package imports resolve in subprocess invocations. One violation per import statement (not per imported name).
- **`scripts/session_close.py`** — Test-gated session cleanup (130 lines). Replaces the `session-closer` subagent. Runs `pytest`; on pass, deletes `task_*.md` files, deletes the `.audit_clean` sentinel, overwrites `MAP.md` with the embedded `CLEAN_MAP_TEMPLATE`. On test failure, no cleanup. Supports `--workspace` and `--dry-run` flags. `SUBPROCESS_TIMEOUT_SECONDS = 600`. Uses `sys.executable` instead of hardcoded `"python"`.
- **Audit gate in `scripts/orchestrate.py`** — post-ALL_DONE hook that runs the deterministic audit scripts via `subprocess.run`, writes `.audit_clean` sentinel on clean audit, runs `session_close.py`, and maps session_close failure to a new `EXIT_ERROR` detail (`"session_close failed"`). New constants `EXIT_AUDIT_FAILED = 5`, `AUDIT_SENTINEL = ".audit_clean"`, `PYTHON_EXECUTABLE = sys.executable`, `SUBPROCESS_TIMEOUT_SECONDS = 600`. New dataclass `AuditGateResult(is_clean, detail)`. Dry-run short-circuits the gate entirely. Sentinel check-and-write guarded by the existing `map_lock` context manager to prevent concurrent-orchestrator races. stderr captured and included in the detail string on subprocess failure.
- **`tests/test_audit_discipline.py`, `tests/test_check_deps.py`, `tests/test_session_close.py`** — 101 new tests covering every requirement (F1–F23, N1–N6), edge cases (syntax errors, BOM files, namespace packages, relative imports, `from __future__`, `from unittest import mock`), and main-entry-point exit codes.
- **Audit gate test coverage** in `tests/test_orchestrate.py` — `TestAuditGateClean`, `TestAuditGateFailed`, `TestAuditGateSentinel`, `TestAuditGateDryRun`, `TestAuditGateSessionCloseFailure`. Existing `TestHandleAllDone` and `TestRunCycleAllDone` updated to mock the new subprocess calls.

### Changed

- **`plugins/fsm-workflow/templates/CLAUDE.md`** refreshed to the canonical 390-line template. Audit-phase bullet now reflects deterministic scripts replacing LLM auditors.
- **Audit phase in pipeline** (`CLAUDE.md` workflow step 7) — changed from "`code-auditor` + `bug-scanner` + `dep-checker` in parallel" (3 LLM subagents) to "`audit_discipline.py` + `check_deps.py` run deterministically via subprocess; `bug-scanner` LLM runs in parallel for logic checks". Net: 2 fewer LLM dispatches per pipeline cycle, zero token cost for discipline + dep checks, no 529 retry risk.
- **`plugins/fsm-workflow/.claude-plugin/plugin.json`** version `0.1.1` → `1.1.1`. Fixes a pre-existing drift where `plugin.json` was never bumped when `v1.1.0` was tagged.
- **`.claude-plugin/marketplace.json`** version `0.1.1` → `1.1.1`. Same drift fix.

### Fixed

- **`scripts/atomize_task.py` cross-parent dependency rewriting.** Previously, atomizing a task whose parent dependencies included other parents in the same batch (e.g. `task_804` depends on `[task_801, task_802, task_803]`) left the newly-created subtask files pointing to the now-deleted parent IDs instead of each parent's last subtask (`task_801c`, `task_802c`, `task_803c`). New `_rewrite_parent_depends()` helper + `DependsReplacement` dataclass + accumulated `rewrites: dict[str, str]` in `atomize_tasks()` rewrite each parent's depends line on disk before atomization. Test: `tests/test_atomize_task.py::TestMultiParentDepsRewrite`.
- **`install.sh` was silently skipping the four top-level enforcement hooks.** `block-map-writes.sh`, `block-worker-reads.sh`, `block-model-override.sh`, and `surface-map-on-start.sh` have always shipped in `hooks/` but were never copied to `~/.claude/hooks/` or registered in `settings.json` by the installer. The `/fsm-setup-hooks` slash command description claimed these hooks were installed — a lie. Fresh marketplace users got the repo-map + pipeline-enforce + fsm-trace hooks (9 files) but none of the 4 enforcement hooks that are the entire moat of this package. Without them: MAP writes aren't blocked, worker reads aren't isolated, model overrides aren't prevented, and MAP status doesn't surface at session start. `install.sh` now copies all 4 to `~/.claude/hooks/` (top-level), chmods them executable, and registers them with the correct matchers (`PreToolUse Write|Edit|MultiEdit`, `PreToolUse Read`, `PreToolUse Agent`, `SessionStart`).
- **`install.sh` was missing `src/repo_map/` source tree and `post_tool_trace.sh`** from the repo. `install.sh` required `$SOURCE_DIR/src/repo_map/` to exist (it tries to `cp -R` the tree into `~/.claude/hooks/repo-map/`) but the repo only had `src/fsm_core/`. Same for `hooks/post_tool_trace.sh` — referenced by `$TRACE_HOOK_SOURCE_DIR/$HOOK_POST_TOOL_TRACE` but missing from the repo's `hooks/`. Any fresh checkout that ran `./install.sh` would have errored out with "source tree not found at .../src/repo_map". Both are now committed, so `install.sh` runs clean end-to-end against a fresh clone.
- **`install.sh` agent source path** was `$SOURCE_DIR/agents/` but the v1.1.0 restructure moved agents to `plugins/fsm-workflow/agents/` for marketplace layout. `install.sh` is now updated to read from the plugin path with a fallback to the legacy top-level for older forks.
- **`plugin.json` and `marketplace.json` version drift.** Both manifests reported `"version": "0.1.1"` through the entire v1.0.0 and v1.1.0 tag history — they were never bumped. Both now match the tag scheme at `"1.1.1"`.
- **Agent count claim corrected.** `plugin.json` description and `fsm-setup-hooks.md` said "22 subagents" — off by one. The plugin actually ships 23 agents (advisor, architect, bug-scanner, code-auditor, code-fixer, code-reviewer, debugger, dep-checker, dispatcher, doc-writer, explore-scout, explore-superscout, file-lister, fsm-executor, fsm-integrator, mock-server, mockup-verifier, research-scout, session-closer, session-handoff, spec-writer, task-planner, test-runner). All descriptions updated.

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
