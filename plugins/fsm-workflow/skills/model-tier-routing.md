---
name: Model Tier Defaults
description: Tier assignments for each FSM agent role
color: yellow
---

## Model Tier Defaults (Max Account)

No cost difference on Max. Tier choice is quality, speed, and rate limit pressure.

| Role | Default Model | Rationale |
|---|---|---|
| task-planner | opus | Highest-stakes planning. Free on Max. |
| architect | opus | Manifest quality determines build quality. |
| bug-scanner (×2) | sonnet | Paired wave-boundary reviewers on deterministic shards; unanimous APPROVE required. |
| fsm-integrator | sonnet | Cross-module wiring with explicit specs. Opus escalation via dispatcher override. |
| fsm-executor | haiku (via dispatcher `**Model:**` override) | All executor tasks are atomized single-step. Speed + 529 headroom. |
| debugger | sonnet | Reasoning about failures. Opus escalation for complex bugs. |
| dispatcher | sonnet | Decision routing, not deep reasoning. |
| code-fixer | haiku | Mechanical fixes from auditor reports. |
| explore-scout | haiku | Fast file reads, structured reports. |
| explore-superscout | sonnet | Dense document reasoning. |

---
