---
name: MAP.md Format
description: Active task tracking and file directory
color: green
---

## MAP.md Format

```markdown
# MAP

## Active Tasks

### Wave 1 (parallel — no dependencies)
Project/
  src/engine/      [task_801_model_registry.md] ........ PENDING
  src/types/       [task_802_message_types.md] ......... PENDING

### Wave 2 (depends on Wave 1)
Project/
  src/composites/  [task_803_tier_rewrite.md] .......... PENDING  depends: 801, 802

## Completed (awaiting audit)
— none —

## File Directory

### task_801 → src/engine/ + src/config.ts
Creates:
  src/engine/model-registry.ts      # ModelRole, resolveModel(role)
  tests/engine/model-registry.test.ts
Modifies:
  src/config.ts                     # MODEL_ROLES, PHASE_CONFIGS
Reads:
  src/config.ts                     # current structure
  #docs/specs/v4_spec.md            # model roster
```

The File Directory mirrors each task file's `## Files` section. Both are mandatory and must match.
