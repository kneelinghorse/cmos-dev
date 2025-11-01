# Conversational Trigger Automation

Mission **B2.1 – Memory Core (decisions, facts)** delivers a lightweight helper that maps natural-language phrases to the sprint workflow. The new `cmosctl.triggers` module keeps the database, backlog YAML, sessions log, and project context in sync so assistants no longer edit those files manually.

## Quick Start

```python
from datetime import datetime, timezone
from cmosctl import MissionRunOutcome, default_registry

registry = default_registry(agent="codex")

def finish_active_mission(ctx):
    # Run mission-specific work here (build features, update docs, etc.)
    return MissionRunOutcome(
        summary="Memory Core helpers delivered",
        notes="Trigger registry + documentation added",
        next_hint="Confirm B2.2 research hooks once available",
        completed_at=datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    )

result = registry.handle("run current mission", executor=finish_active_mission)
print(result.message)
```

`run current mission` performs the full session workflow:

- Promotes the correct mission to `In Progress` when needed
- Logs a `start` event in the session table (and regenerates `cmos/SESSIONS.jsonl`)
- Executes the provided callback
- Marks the mission `Completed`, promotes the next queued mission, and writes `completed_at` + notes
- Logs a `complete` event with optional `next_hint`
- Updates `cmos/PROJECT_CONTEXT.json` with the new session metadata

## Check-In Summary

```python
registry = default_registry()
summary = registry.handle("let's check-in")
print(summary.payload["summary"])
```

The check-in trigger reads the latest project and master context files, then returns:

- Compact headline summary (project name, session totals, active/next mission)
- Last recorded session timestamp
- A short list of recent key decisions for quick recall

## Extending the Registry

```python
from cmosctl.triggers import TriggerResult

registry = default_registry()

def log_fact(ctx, *, fact):
    # Example: persist additional context or route to future memory tables.
    ...
    return TriggerResult(trigger="remember this", success=True, message="Fact captured.")

registry.register("remember this", log_fact, description="Capture an ad-hoc fact for later recall.")
```

Each trigger normalizes the phrase (case insensitive) and accepts aliases, so variants like `run the current mission` map to the same handler.

Stay within the helper for file updates—manual edits remain available for recovery, but the trigger registry is now the default path for mission execution and check-ins.
