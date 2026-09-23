---
name: food-agent-architecture
description: Review or modify the Personal Food Agent while preserving its Understand→TaskModel→Plan→Act→Observe→Validate→Re-plan→Compose→Rank→Respond boundaries. Use when changing agent flow, tools, orchestration, memory, or architecture.
---

Use this skill for architecture changes or when a requested change may cross agent layers.

## Workflow

1. Locate the affected entrypoint, agent loop, tool(s), TaskModel/session models, and tests.
2. Draw the smallest relevant call flow in notes:
   `input → layer → contract → next layer`.
3. Decide which layer should own the requested behavior.
4. Prefer changing the owner layer rather than adding cross-layer fallback logic.
5. Keep tool boundaries narrow and deterministic.
6. Add a regression test at the contract boundary.

## Boundary checks

- Understand: raw language → TaskModel only.
- Plan: TaskModel + memory → strategy/actions.
- Act: strategy → deterministic tool calls.
- Observe: tool calls → structured evidence.
- Validate: evidence + hard constraints → pass/fail reasons.
- Re-plan: failure → bounded alternative strategy.
- Compose: compatible objects/candidates → order candidates.
- Rank: candidates + preferences → ordered candidates.
- Respond: validated evidence → user-facing explanation.

## Reject the change if it causes

- downstream raw-text parsing;
- LLM-generated restaurant/menu facts;
- a new god tool;
- hidden defaults in Understand;
- hard constraints being relaxed without an explicit policy;
- duplicated NLU paths that can drift.

If a legacy design forces a temporary compatibility layer, isolate it, document it, and add a test proving the intended migration boundary.
