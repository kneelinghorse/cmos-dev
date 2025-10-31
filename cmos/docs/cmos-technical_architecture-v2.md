CMOS v0.2 — Updated Technical Architecture & Build Plan
A) Architecture deltas (what we’re changing/adding)

SQLite is the source of truth (kept)
Continue with a single cmos/memory.db for atomic state and agent operations. (Missions, Sessions, Strategy, ProjectState, ProcessGraph remain.) 

cmos-technical_architecture

Add a first-class Memory Core (facts, decisions, KB, policies)

facts (append-only, durable truth statements, e.g., “B1.1 completed”)

decisions (irreversible choices + rationale)

kb_sources, kb_chunks (project KB; start lexical + FTS5; embeddings optional later)

policies (validation thresholds, tool caps, routing hints; JSON blob)

metrics (tokens_in/out, latency_ms, accepted/defects) tied to sessions

Confidence-gated validation results captured on Sessions/Missions
Add validation_score, validation_state (auto_approved | needs_review | human_required) to align with the 60/80 pattern from research (keeps the gate in data, not prose).

FSM actions get typed + parameterized
Extend process_graph.suggested_action into {action_type, action_ref, params} so the orchestrator can:

run local actions: select_next_mission, kb_index, update_backlog

call remote actions: call:MissionProtocol(sprint_planning|sprint_report) 

cmos-technical_architecture

Git bridge (post-commit) becomes a supported CLI path
Ship cmosctl hook install (writes .git/hooks/post-commit) and cmosctl session log --type commit …; de-placeholder the my_agent_cli seen in the draft. 

cmos-technical_architecture

B) Minimal schema extensions (SQLite DDL)
-- New memory tables
CREATE TABLE IF NOT EXISTS facts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT DEFAULT (datetime('now')),
  mission_id TEXT,
  kind TEXT,           -- e.g., 'mission_completed', 'finding', 'risk'
  payload TEXT         -- JSON string
);

CREATE TABLE IF NOT EXISTS decisions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT DEFAULT (datetime('now')),
  mission_id TEXT,
  title TEXT,
  rationale TEXT
);

-- KB (lexical-first; embeddings optional later)
CREATE TABLE IF NOT EXISTS kb_sources (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  path TEXT UNIQUE,
  bytes INTEGER,
  last_indexed_ts TEXT
);

CREATE TABLE IF NOT EXISTS kb_chunks (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source_id INTEGER REFERENCES kb_sources(id),
  range_start INTEGER,
  range_end INTEGER,
  text TEXT
);

-- Full-text index (SQLite FTS5) for simple RAG v0
CREATE VIRTUAL TABLE IF NOT EXISTS kb_chunks_fts USING fts5(text, content='kb_chunks', content_rowid='id');

-- Policies + metrics
CREATE TABLE IF NOT EXISTS policies (
  key TEXT PRIMARY KEY,      -- 'validation', 'limits', 'routing'
  json TEXT                  -- whole policy block as JSON
);

ALTER TABLE sessions ADD COLUMN tokens_in INTEGER DEFAULT 0;
ALTER TABLE sessions ADD COLUMN tokens_out INTEGER DEFAULT 0;
ALTER TABLE sessions ADD COLUMN latency_ms INTEGER DEFAULT 0;
ALTER TABLE sessions ADD COLUMN validation_score REAL;       -- 0..1
ALTER TABLE sessions ADD COLUMN validation_state TEXT;       -- auto_approved|needs_review|human_required

ALTER TABLE missions ADD COLUMN approval_state TEXT;         -- same states at mission level
ALTER TABLE missions ADD COLUMN validation_score REAL;


Keep your existing missions, sessions, strategy, project_state, process_graph as in the draft; we’re extending, not replacing. 

cmos-technical_architecture

C) Components & responsibilities

SQLite store (cmos/memory.db) — sole source of truth (state + memory + KB)

CLI (cmosctl) — ergonomic façade over the DB & FSM

db init|migrate

mission add|list|next|complete|block

session log … (commit/agent events; writes metrics)

kb index (scans cmos/docs/** and cmos/missions/**, chunks + FTS5)

policy set|get

hook install

fsm step --event <…> (advance via process_graph)

Post-commit hook — calls cmosctl session log --type commit … (no placeholders) 

cmos-technical_architecture

Orchestrator (FSM loop) — reads project_state, process_graph, proposes suggested_action, enforces the gate, runs local actions or calls Mission Protocol. 

cmos-technical_architecture

Mission Protocol (remote) — returns templated procedures for reports/planning; holds no source-of-truth state. Glue is suggested_action. 

cmos-technical_architecture

D) Build plan (concrete, small, shippable)
Week 1 — MVP Refactor (state centralization & FSM skeleton)

Goals

All agent logic uses cmos/memory.db

Sessions flow from code commits and agent runs

Simple FSM loop moves among 3 states

Tasks

DB bootstrap

Migrate/create tables from draft + new DDL above; ship cmosctl db init|migrate. 

cmos-technical_architecture

CLI core

cmosctl mission add|list|complete|block

cmosctl session log --type start|complete|blocked|commit

cmosctl hook install → writes executable .git/hooks/post-commit that shells into cmosctl session log … with commit hash/message/files. 

cmos-technical_architecture

FSM v0

Tables: project_state, process_graph (seed small map)

Orchestrator loop with fsm step --event mission_completed|sprint_tasks_done|mission_blocked

Acceptance

Commit triggers a Session(commit) row

Completing a mission yields the correct next suggestion

project_state.current_state updates correctly

Week 2 — Memory Core & Validation

Goals

Durable memory (facts, decisions)

Lexical KB + FTS5 search

Confidence gates wired to policies and sessions

Tasks

Memory Core

cmosctl memory fact --kind mission_completed --payload …

cmosctl memory decision --title … --rationale …

KB v0 (lexical)

cmosctl kb index → scan → chunk → upsert kb_* + populate FTS

cmosctl kb search "query" → returns chunk refs

Policies + Gates

policy set validation '{ "auto_approve_min": 0.80, "needs_review": [0.60, 0.80] }'

Orchestrator: set sessions.validation_state from score ⇒ require human OK if needed

Acceptance

Mission completes with validation_score recorded; auto-approved ≥0.80; requires approval in [0.60,0.80]; blocked <0.60 with reason

KB search returns relevant chunks for the current sprint files

Week 3 — Metrics, Routing, and Mission Protocol glue

Goals

DX/SPACE-style metrics recorded per session

Model routing hints stored in policies

Remote procedure calls for planning/reporting

Tasks

Metrics

CLI flags --tokens_in --tokens_out --latency_ms --accepted

Weekly rollup query: sessions by mission with means/medians

Routing hints

Persist { simple: "flash", standard: "standard", complex: "premium" }

Orchestrator emits route hint alongside suggested_action

Mission Protocol glue

Action handler for call:MissionProtocol(sprint_report|sprint_planning) passing KB snippets + memory to the server

Acceptance

Weekly report prints metrics/acceptance

Mission Protocol calls succeed and write back outputs via facts

E) CLI & hook sketches (ready to paste)

Post-commit hook (installed by cmosctl hook install)

#!/bin/sh
COMMIT_HASH=$(git rev-parse HEAD)
COMMIT_MSG=$(git log -1 --pretty=%B)
FILES_CHANGED=$(git diff-tree --no-commit-id --name-only -r HEAD | tr '\n' ',')
cmosctl session log \
  --type commit \
  --agent GitHook \
  --mission "$(cmosctl mission active || echo unknown)" \
  --summary "$COMMIT_MSG" \
  --details "commit=$COMMIT_HASH;files=$FILES_CHANGED"


cmos-technical_architecture

Process graph seed (CSV → seed into process_graph)

current_state,event,next_state,action_type,action_ref,params
Startup,init_complete,Sprint_Planning,remote,mission_protocol,"{""name"":""sprint_planning""}"
Sprint_Planning,plan_approved,In_Sprint,local,select_next_mission,{}
In_Sprint,mission_completed,In_Sprint,local,select_next_mission,{}
In_Sprint,sprint_tasks_done,Sprint_Review,remote,mission_protocol,"{""name"":""sprint_report""}"
In_Sprint,mission_blocked,Blocked,local,notify_blocker,{}
Blocked,unblocked,In_Sprint,local,select_next_mission,{}


cmos-technical_architecture

Typer-style CLI stubs (Python)

import typer
from datetime import datetime
app = typer.Typer()

@app.command("session-log")
def session_log(type: str, agent: str, mission: str = "", summary: str = "", details: str = "",
                tokens_in: int = 0, tokens_out: int = 0, latency_ms: int = 0):
    # INSERT INTO sessions (...)
    ...

@app.command("kb-index")
def kb_index():
    # scan cmos/docs/** and cmos/missions/**, chunk, upsert, rebuild FTS
    ...

@app.command("fsm-step")
def fsm_step(event: str):
    # read project_state, lookup process_graph, run action, update state
    ...

if __name__ == "__main__":
    app()

F) Migration from flat-files (one-time)

backlog.yaml → missions (id, sprint_id, status, notes, completed_at)

SESSIONS.jsonl → sessions (ts, agent, mission_id, action, status, summary)

Any durable “notes/decisions” you’ve kept in docs → facts / decisions (use a small importer)

Acceptance: SELECT COUNT(*) parity checks; a few spot verifications.

G) Operational loop (how this ties back to your Playbook)

Phase 1 authoring: architecture/roadmap live in docs, but indexed into KB; strategic snapshots land in strategy (historical log row), while durable facts/decisions get appended to memory tables.

Phase 2 planning: create Sprint missions via cmosctl mission add …; dependencies captured as notes (MVP) or a follow-up mission_edges table.

Phase 3 execution: sessions flow from agent runs and commits; FSM advances; validation gates enforce the human-in-the-loop when needed; weekly metrics roll up automatically.

H) Risks & guardrails (baked in)

Tool/feature creep: enforce caps in policies (e.g., tool_cap=20).

Looping: detect same-summary duplicate session_log within short time window → warn/block.

RAG sprawl: lexical+FTS first; add embeddings behind the same kb_* contract when you truly need it.