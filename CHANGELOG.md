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

## [1.2.5] — 2026-04-13

Enforce orchestrate.py for pipeline dispatch. New PreToolUse hook blocks direct Agent dispatch of pipeline roles (fsm-executor, fsm-integrator, code-fixer, debugger, bug-scanner) when no pending intents exist — forces the orchestrator to run orchestrate.py first instead of dispatching manually.

### Added

- `enforce_orchestrate.py` — PreToolUse hook on Agent that blocks pipeline role dispatch without pending `.fsm-intents/`. Allows non-pipeline roles (scouts, architect, planner) and brainstorming agents unconditionally.
- Hook registered in `install.sh` for both copy and `settings.json` merge.
- Test suite: `tests/test_enforce_orchestrate.py` (8 tests covering all allow/block paths).

### Changed

- `install.sh` — copies `enforce_orchestrate.py` alongside existing enforcement hooks, registers it on the `PreToolUse Agent` matcher.
- Clean session state after full wave completion and test pass.

---

## [1.2.4] — 2026-04-12

Recovery stabilization. Dispatch runtime is now Claude-session intent/result only — legacy subprocess and SDK dispatch code removed. Wave gate runs via a required bug-scanner pair verdict. REVISE loops route flagged tasks to `code-fixer` (simple/mechanical) or `debugger` (complex/logic).

### Added

- **Bug-scanner pair wave gate** — two bug-scanners review wave output in parallel on deterministic file shards. Unanimous APPROVE required to open the gate. Replaces the single Opus advisor.
- **REVISE routing heuristic** — `code-fixer` for simple hints (lint, format, imports, discipline), `debugger` for complex/logic fixes.
- **Pair-result correlation** on `.fsm-results/`; ungate only after both scanner results arrive.

### Removed

- **`src/fsm_core/subprocess_dispatch.py`** — legacy subprocess dispatch runtime.
- **`src/fsm_core/sdk_worker.py`**, **`sdk_tools.py`**, **`sdk_path_guards.py`**, **`sdk_discipline_gate.py`** — SDK dispatch modules (superseded by claude-session backend).
- **Associated tests** for all removed modules.

### Changed

- **`CLAUDE.md` template** updated: bug-scanner pair wave gate, code-fixer/debugger REVISE routing, clarified kickoff path.
- **`scripts/split_claude_md.py`** now sources `Default behaviour`, `Rules`, and `Project Notes` directly from `CLAUDE.md` to reduce drift.
- **All 6 skill files** regenerated from the updated `CLAUDE.md`.

### Validation

- 466 tests pass.

---

## [1.2.3] — 2026-04-12

Pipeline speed release. Converts `orchestrate.py` into an async event-driven daemon, replaces the single Opus wave-advisor with a three-gate pipeline (deterministic → cache → bug-scanner pair), flips atomization from mandatory to opt-in. One new third-party dep: `anthropic>=0.40`.

### Added

- **`src/config.py`** — central constants (DISPATCH_MODE, MODEL_MAP, HTTP pool, rate-limit, daemon poll, heartbeat, cache).
- **10 new `src/fsm_core/` modules**: `advisor_cache.py` (content-hash verdict cache), `auto_heal.py` (startup stale-task healer), `claude_session_backend.py` (intent/result transport), `dispatch_contract.py` (dispatch dataclasses), `dispatch_router.py` (claude-session dispatch router), `orchestrate_lock.py` (lockfile context manager), `startup_checks.py` (MAP/task state drift warnings), `wave_deterministic_gate.py` (deterministic pre-gate), `worker_heartbeat.py` (atomic heartbeat writer).
- **`scripts/claude_session_driver.py`** — intent/result driver bridge for claude-session dispatch.
- **`requirements.txt`** — `anthropic>=0.40` (single third-party dep).
- **`conftest.py`** — root pytest config for sys.path setup.
- **`--daemon` flag** on `orchestrate.py` for persistent async polling loop.
- **`--clear-advisor-cache` flag** on `orchestrate.py`.
- **`--dry-run` flag** on `atomize_task.py`.
- **Three-gate wave pipeline**: (1) `wave_deterministic_gate.evaluate_wave` runs audit + deps + pytest, (2) `advisor_cache.lookup_verdict` checks content-hash cache, (3) two `bug-scanner` agents on disjoint file shards.
- **`install.sh install-deps`** subcommand for `pip install -r requirements.txt`.
- **163 new tests** across 14 test files.

### Changed

- **`scripts/orchestrate.py`** — async daemon mode, three-gate wave cycle, lock acquisition, auto-heal preload, signal handlers.
- **`scripts/orchestrate_monitor.sh`** — removed outer 20s poll loop; single `orchestrate.py --daemon` invocation.
- **`scripts/atomize_task.py`** — atomization now opt-in (`atomize: required` only). `--dry-run` flag added.
- **`scripts/audit_discipline.py`** — new `check_file(path)` public API; synthetic F0 on parse failure.
- **`src/fsm_core/frontmatter.py`** — `atomize: str = "optional"` field on TaskFrontmatter.
- **`src/fsm_core/trace.py`** — `SDK_EVENT_TYPES` constant, `build_sdk_event` helper.
- **`src/fsm_core/session_state.py`** — `checkpoints_skipped_this_session` changed from `bool` to `list[str]` with legacy coercion.

### Deprecated

- `dispatch_advisor` renamed to `dispatch_bug_scanner_pair`; deprecated shim retained for v1.2.5 removal.

### Validation

- 590 tests pass.

---

## [1.2.2] — 2026-04-12

Release ergonomics + opt-in user gates + progressive disclosure. Three features ship together: optional PHASE CHECKPOINT via `AskUserQuestion`, SWE-bench Verified harness skeleton under `bench/`, and a slim downstream `CLAUDE.md` with six carved skills. Parallel worker dispatch and wave-batch advisor land alongside. Backwards compatible — pipelines with no flagged tasks behave byte-identically to v1.1.2.

Repo: https://github.com/itsaldrincr/claude-code-fsm-workflow

### Added

- **`requires_user_confirmation: bool = false` frontmatter field** on task files. When set on any task in a wave, `orchestrate.py` writes a `.checkpoint_pending` JSON sentinel under `map_lock()` at wave completion and returns `EXIT_WAITING`. The orchestrator agent reads the sentinel and fires Claude Code's `AskUserQuestion` with wave number, triggering task IDs, next-wave plan, and four options (Approve / Revise / Abort / Skip-for-remainder). Decline writes `status: "paused"` to `session_state.json`.
- **`bench/` directory** — SWE-bench Verified harness skeleton. `bench/prepare_instance.py` creates isolated workspaces from SWE-bench instances with git baseline commits. `bench/evaluate.py` ships a local heuristic diff-match backend with a pluggable interface for the official `swebench` eval. `bench/run_one.py` drives `orchestrate.py` end-to-end against a prepared workspace and emits per-instance `bench_result.json`. `bench/runner.py` is the batch entry point, aggregating results under `bench/baselines/run_<timestamp>.json`. `bench/requirements.txt` is the first third-party deps in the repo, scoped strictly to `bench/`. `BENCH_INSTANCE_TIMEOUT_SECONDS = 1800` (30-minute per-instance timeout). No baseline numbers shipped.
- **Six Claude Code skills** under `plugins/fsm-workflow/skills/`: `fsm-roles.md`, `fsm-task-format.md`, `fsm-map-format.md`, `fsm-workflow-phases.md`, `fsm-hook-enforcement.md`, `model-tier-routing.md`. Carved from the monolithic `CLAUDE.md` rules body. Each skill has `name`, `description`, `color` frontmatter and loads on-demand via Claude Code's skill loader.
- **`scripts/orchestrate_monitor.sh`** — persistent shell loop for Claude Code's Monitor tool. Drives `orchestrate.py` in a loop, emits timestamped state-count events on stdout, exits on pipeline completion / BLOCKED / ERROR. `--dry-run` flag for smoke testing.
- **`scripts/split_claude_md.py`** — release-prep helper that splits the local authoritative `CLAUDE.md` into the slim downstream template + six skill files. Prevents drift when `CLAUDE.md` changes.
- **Parallel worker dispatch** — `dispatch_workers_parallel(requests: list[WorkerDispatchRequest])` in `src/fsm_core/subprocess_dispatch.py` uses `ThreadPoolExecutor(max_workers=8)` to launch multiple workers concurrently. `_handle_dispatch_wave` in `scripts/orchestrate.py` flips all ready tasks to `IN_PROGRESS`, parallel-dispatches, then flips each to `REVIEW` or `FAILED` based on exit code.
- **Wave-batch advisor** — `_maybe_advisor_at_wave_gate` in `src/fsm_core/action_decider.py` returns a single `DISPATCH_ADVISOR` action containing every REVIEW task in the earliest-REVIEW wave. Advisor reviews the full batch in one pass. APPROVE flips every wave task REVIEW → DONE. REVISE parses an explicit `FAILING TASKS: task_NNNa, ...` line and flips only flagged tasks to PENDING.
- **`extract_flagged_task_ids(guidance, candidates)`** in `src/fsm_core/advisor_parser.py` — prefers the explicit `FAILING TASKS:` line, falls back to free-text scanning for task_id patterns.
- **`WAVE_CHECKPOINT_PENDING`** action type + `_find_wave_checkpoint` helper in `action_decider.py`.
- **`"paused"` SessionState variant** + optional `checkpoints_skipped_this_session: bool` field on `SessionState`. Orchestrator writes paused state on user decline; `_should_skip_dispatch` guards against advancing a paused session.
- **`MAX_PARALLEL_WORKERS: int = 8`** constant in `subprocess_dispatch.py`.
- **`--permission-mode bypassPermissions`** flag on `claude -p` worker subprocess invocations. Fixes a silent failure mode where the Write tool was blocked by default on fresh paths.
- **Hardened worker prompt** (`_build_worker_prompt`) with seven explicit rules: real tool calls only (no hallucinated DONE), verify-before-DONE via Read/Bash, flip every `- [ ]` acceptance checkbox to `- [x]`, nonce proof in Registers, correct state transition, never read MAP.md / CLAUDE.md, REVISE awareness via Registers re-read.
- **Install step for skills** — `install.sh` now copies `plugins/fsm-workflow/skills/*.md` into `~/.claude/skills/` idempotently with a count printout.
- **`init-workflow` self-installs skills** if `~/.claude/skills/fsm-*.md` are missing, so the slim downstream `CLAUDE.md` always has its on-demand references available.
- **`bench/` test suite** under `tests/bench/`: `test_prepare_instance.py`, `test_evaluate.py`, `test_run_one.py`, `test_runner.py`. Full suite now 458 tests.

### Changed

- **`plugins/fsm-workflow/templates/CLAUDE.md` slimmed** from 399 to 134 lines. Contains coding discipline, MAP.md write authority, worker context isolation, default behaviour, rules, project notes, and a 6-line skill footer. The six carved skills carry the detailed reference material and load on-demand.
- **`AdvisorDispatchRequest.task_paths: list[str]`** (was `task_path: str`). `_build_advisor_prompt` rewritten to review the whole wave in one review pass, requiring the advisor to return an explicit second-line `FAILING TASKS: task_NNNa, task_NNNb, ...` on REVISE.
- **`DEFAULT_TIMEOUT_SECONDS`** bumped from 900 to 1800 seconds for integrator headroom.
- **`GUIDANCE_SUMMARY_LIMIT`** bumped from 100 to 2000 characters so advisor REVISE feedback survives truncation into task Registers.
- **`TaskStatus.wave: int = 0`** field added to `src/fsm_core/action_decider.py`. `_all_deps_satisfied` treats REVIEW as "worker complete" for intra-wave cascade purposes: a dep is satisfied if the predecessor is DONE OR (REVIEW AND same wave). Cross-wave deps still require DONE.
- **`decide_action` refactored** into a `_DECISION_CASCADE` tuple: `_check_blocked → _check_wave_advisor → _find_wave_checkpoint → _check_ready_wave → _check_all_done`. Checkpoint precedes ready-wave to prevent a DONE wave with `requires_user_confirmation=true` from being bypassed by a ready-wave dispatch.
- **`README.md` Benchmarking section** documents the `bench/` harness with Prerequisites, Running Single/Batch, Known Limitations, and a Third-party Dependencies callout explaining that `bench/` is the one subdirectory allowed non-stdlib deps.

### Fixed

- **Worker hallucinated-DONE silent failure.** Workers dispatched via `claude -p` were failing silently on CREATE-heavy tasks because the subprocess Write tool was blocked by default. `orchestrate.py` parsed the worker's final response as `state: DONE` but no files landed on disk. Fixed by adding `--permission-mode bypassPermissions` to the subprocess invocation and mandating real tool calls in the worker prompt.
- **`_revise_wave_batch` deadlock.** Previously short-circuited on the first task to hit `MAX_REVISE_ROUNDS`, leaving remaining REVIEW tasks in limbo. Now accumulates BLOCKED results across all targets and returns the first after processing every flagged task.
- **`_DECISION_CASCADE` ordering bypass.** `_find_wave_checkpoint` was evaluated AFTER `_check_ready_wave`, meaning a DONE wave with `requires_user_confirmation=true` could be bypassed if wave N+1 had ready PENDING tasks. Moved checkpoint ahead of ready-wave.
- **`SessionState._parse_state_file`** silently dropped `checkpoints_skipped_this_session` on every read. Skip-for-session shortcut was effectively broken. Now round-trips the field via `data.get("checkpoints_skipped_this_session", False)`.
- **Checkpoint sentinel race window.** `_run_cycle` now re-checks `_should_skip_dispatch` after `decide_action` to shrink the write-race window where a concurrent process could write `.checkpoint_pending` between the initial check and dispatch.
- **CHANGELOG footer compare links** for `[1.2.2]` added alongside the new entry.

### Removed

- **Dead per-task REVISE path.** `_handle_revise`, `_run_revise_dispatch`, `_flip_to_blocked`, and `ReviseContext` are no longer reachable now that wave-batch REVISE re-dispatches flagged tasks via the normal `_find_ready_tasks` → `_handle_dispatch_wave` path.

---

## [1.1.2] — 2026-04-11

Model-tier drift fix. `fsm-executor` and `fsm-integrator` agent defaults now match the intended tier scheme documented in `CLAUDE.md`. Two-line frontmatter change; no behavior change outside model routing.

Repo: https://github.com/itsaldrincr/claude-code-fsm-workflow

### Fixed

- **`fsm-executor` default model.** Was `sonnet`; should be `haiku`. The `Model Tier Defaults` table in `CLAUDE.md` has always listed executor as `haiku` ("all executor tasks are atomized single-step. Speed + 529 headroom"), but the agent frontmatter has been shipping `sonnet` since v1.1.0. Corrected in `plugins/fsm-workflow/agents/fsm-executor.md`.
- **`fsm-integrator` default model.** Was `opus`; should be `sonnet`. The `Model Tier Defaults` table lists integrator as `sonnet` with "Opus escalation via dispatcher override", but the agent frontmatter has been shipping `opus`. Corrected in `plugins/fsm-workflow/agents/fsm-integrator.md`.
- **CHANGELOG footer compare links for `[1.1.1]` and `[Unreleased]`** were never added during the v1.1.1 bump. Added alongside the new `[1.1.2]` entry.

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
- **`install.sh` direct-clone path was incomplete.** Users who cloned the repo and ran `./install.sh` got hooks, agents, and `src/fsm_core/` but were missing slash commands, project templates, and orchestrator scripts — causing `/init-workflow` to fail silently because the paths it references didn't exist. Three new copy steps added: (1) `plugins/fsm-workflow/commands/*.md` → `~/.claude/commands/` (ships `init-workflow.md` and `fsm-setup-hooks.md`); (2) `plugins/fsm-workflow/templates/` → `~/.claude/templates/` (ships the 390-line `CLAUDE.md` template, `settings.json`, and `hooks/discipline-gate.sh`, chmod +x'd); (3) `scripts/*.py` → `~/.claude/scripts/` (all 5: `orchestrate.py`, `atomize_task.py`, `audit_discipline.py`, `check_deps.py`, `session_close.py`, all chmod +x'd). Installer summary now reports 3 additional target directories. After this fix, `./install.sh` against a fresh clone is byte-for-byte equivalent to marketplace install + `/fsm-setup-hooks`.
- **`/init-workflow` hardcoded the author's machine path.** The command copied orchestrator scripts from `~/projects/claude-harness/scripts/` — a path that exists only on the author's machine. Every other user silently got an incomplete project scaffold. Rewritten to: (1) declare `~/.claude/templates/` and `~/.claude/scripts/` as prerequisites in a new "Prerequisites" section at the top; (2) check both paths exist before proceeding and route to `/fsm-setup-hooks` if missing; (3) copy all 5 orchestrator scripts from `~/.claude/scripts/` into `<CWD>/scripts/` instead of the hardcoded harness path; (4) expand the verify checklist to name all 5 script paths; (5) update the confirmation message to mention `python scripts/orchestrate.py`. Command now works for any user on any machine.

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

[Unreleased]: https://github.com/itsaldrincr/claude-code-fsm-workflow/compare/v1.2.5...HEAD
[1.2.5]: https://github.com/itsaldrincr/claude-code-fsm-workflow/compare/v1.2.4...v1.2.5
[1.2.4]: https://github.com/itsaldrincr/claude-code-fsm-workflow/compare/v1.2.3...v1.2.4
[1.2.3]: https://github.com/itsaldrincr/claude-code-fsm-workflow/compare/v1.2.2...v1.2.3
[1.2.2]: https://github.com/itsaldrincr/claude-code-fsm-workflow/compare/v1.1.2...v1.2.2
[1.1.2]: https://github.com/itsaldrincr/claude-code-fsm-workflow/compare/v1.1.1...v1.1.2
[1.1.1]: https://github.com/itsaldrincr/claude-code-fsm-workflow/compare/v1.1.0...v1.1.1
[1.1.0]: https://github.com/itsaldrincr/claude-code-fsm-workflow/compare/v0.1.1...v1.1.0
[0.1.1]: https://github.com/itsaldrincr/claude-code-fsm-workflow/releases/tag/v0.1.1
[0.1.0]: https://github.com/itsaldrincr/claude-code-fsm-workflow/releases/tag/v0.1.0
