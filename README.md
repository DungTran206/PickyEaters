# Codex setup for Personal Food Agent

## Contents

- `AGENTS.md` — repository-level engineering and architecture rules.
- `skills/food-agent-architecture/SKILL.md` — architecture workflow.
- `skills/taskmodel-contract/SKILL.md` — TaskModel contract and semantic extraction rules.
- `skills/food-agent-testing/SKILL.md` — testing workflow and regression matrix.
- `skills/food-agent-code-review/SKILL.md` — review checklist.

## Suggested repository layout

```text
your-project/
├── AGENTS.md
├── skills/
│   ├── food-agent-architecture/
│   │   └── SKILL.md
│   ├── taskmodel-contract/
│   │   └── SKILL.md
│   ├── food-agent-testing/
│   │   └── SKILL.md
│   └── food-agent-code-review/
│       └── SKILL.md
└── ...
```

Keep AGENTS.md short enough to be useful as always-on project guidance. Keep workflow-specific detail in skills so Codex can load it when relevant.
