# CMOS v2.0 — Simplified Technical Architecture

## Philosophy: Lightweight & Practical

**Core Principle**: Replace manual flat file upkeep with minimal automation. Like `.git`, CMOS should be small, hidden (`.cmos`), and portable.

**Key Goals**:
1. Automate session/progress tracking (currently manual in playbook)
2. Better sprint-to-sprint transitions (capture learnings systematically)
3. Systematic knowledge capture (decisions, findings)
4. Simple CLI to eliminate manual file edits
5. Keep it portable (single `.cmos` folder, one database file)

---

## A) What We're Building

### Core Replacement
- **`backlog.yaml`** → SQLite `missions` table
- **`SESSIONS.jsonl`** → SQLite `sessions` table  
- **`PROJECT_CONTEXT.json`** → SQLite `project_state` table + simple queries

### Automation Added
- **CLI (`cmosctl`)**: Replace manual file edits
  - `mission next` - Get current mission (replaces reading backlog.yaml)
  - `mission complete <id>` - Auto-update status, promote next
  - `session log` - Track work (replaces manual SESSIONS.jsonl edits)
  - `hook install` - Auto-track git commits

- **Simple Memory**: Capture learnings
  - `decisions` table - Choices + rationale (for sprint transitions)
  - `facts` table - Append-only truth statements
  
- **Basic KB (Optional, Deferred)**: For finding context
  - Index `cmos/docs/**` and `cmos/missions/**` 
  - FTS5 search when needed
  - Can be added in Week 2 if useful

### What We're NOT Building (Yet)
- Complex FSM with many states → Keep state simple
- Validation gates → Start manual approval
- Heavy metrics → Add if needed later
- Mission Protocol RPC → Manual integration first
- Policies system → Use defaults

---

## B) Minimal Database Schema

**Single File**: `.cmos/memory.db` (hidden like `.git`)

```sql
-- Core tracking (replaces flat files)
CREATE TABLE IF NOT EXISTS missions (
  id TEXT PRIMARY KEY,              -- e.g., "B1.1"
  sprint_id TEXT,                   -- e.g., "sprint-01"
  name TEXT,
  status TEXT DEFAULT 'Queued',     -- Queued, Current, In Progress, Completed, Blocked
  created_at TEXT DEFAULT (datetime('now')),
  completed_at TEXT,
  notes TEXT
);

CREATE TABLE IF NOT EXISTS sessions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT DEFAULT (datetime('now')),
  mission_id TEXT,
  action TEXT,                      -- start, complete, blocked, commit
  agent TEXT,                       -- gpt, claude, human, GitHook
  summary TEXT,
  details TEXT                      -- JSON string for flexibility
);

CREATE TABLE IF NOT EXISTS project_state (
  key TEXT PRIMARY KEY,              -- 'current_sprint', 'current_mission', 'phase'
  value TEXT                         -- JSON or simple string
);

-- Simple memory (for sprint transitions)
CREATE TABLE IF NOT EXISTS decisions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT DEFAULT (datetime('now')),
  mission_id TEXT,
  title TEXT,
  rationale TEXT
);

CREATE TABLE IF NOT EXISTS facts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT DEFAULT (datetime('now')),
  mission_id TEXT,
  kind TEXT,                        -- e.g., 'completed', 'finding', 'risk'
  content TEXT
);

-- KB (deferred to Week 2, optional)
CREATE TABLE IF NOT EXISTS kb_sources (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  path TEXT UNIQUE,
  last_indexed_ts TEXT
);

CREATE TABLE IF NOT EXISTS kb_chunks (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source_id INTEGER REFERENCES kb_sources(id),
  text TEXT
);

CREATE VIRTUAL TABLE IF NOT EXISTS kb_chunks_fts USING fts5(text, content='kb_chunks', content_rowid='id');
```

---

## C) CLI Interface (`cmosctl`)

**Minimal surface area** - only what's needed to eliminate manual file edits + auditability:

```bash
# Database
cmosctl db init          # Create .cmos/memory.db with schema
cmosctl db migrate       # Run migrations if schema changes
cmosctl db shell         # Open SQLite shell for direct access (for manual tweaks)
cmosctl db export [format] # Export to YAML/JSON (backup or audit)
cmosctl db import [file]  # Import from YAML/JSON (restore or fix)

# Missions (replace backlog.yaml manual edits)
cmosctl mission list              # Show all missions
cmosctl mission next              # Get current mission (for AI prompts)
cmosctl mission complete <id>    # Mark done, auto-promote next
cmosctl mission block <id>        # Mark blocked with reason
cmosctl mission add <id> <name>  # Add new mission manually
cmosctl mission edit <id>        # Edit mission (opens editor or --field flags)
cmosctl mission show <id>        # Show full mission details (for QA)

# Mission QA/Validation
cmosctl mission verify            # Check all missions for completeness/issues
cmosctl mission incomplete        # List missions missing required fields
cmosctl mission audit [sprint]    # Audit sprint for gaps/inconsistencies

# Sessions (replace SESSIONS.jsonl manual edits)
cmosctl session log --type <action> --mission <id> --summary <text>
  # Types: start, complete, blocked, commit
  # Auto-detects agent from environment or --agent flag
cmosctl session list              # List all sessions (with filters)
cmosctl session show <id>         # Show session details

# Git integration
cmosctl hook install              # Write .git/hooks/post-commit

# Memory (for capturing learnings)
cmosctl decision --title "..." --rationale "..."
cmosctl fact --kind <kind> --content "..."
cmosctl memory list               # List decisions/facts (with filters)

# KB (Week 2, optional)
cmosctl kb index                  # Index cmos/docs and cmos/missions
cmosctl kb search "query"         # Search indexed content

# Status/Context (for AI prompts)
cmosctl status                    # Show current sprint/mission state
cmosctl context                   # Export context for AI (JSON)

# Export/Backup (for auditability and manual editing)
cmosctl export backlog           # Export missions to YAML (like old backlog.yaml)
cmosctl export sessions          # Export sessions to JSONL (like old SESSIONS.jsonl)
cmosctl export all                # Export everything to readable formats
```

---

## D) Integration with Current Playbook

### Phase 3 Session Execution (Current Manual Flow)

**Before (Manual)**:
```
1. Human reads backlog.yaml → finds "Current" mission
2. AI executes mission
3. Human edits backlog.yaml → mark complete, promote next
4. Human edits SESSIONS.jsonl → append completion
```

**After (Automated)**:
```
1. AI runs: cmosctl mission next → gets current mission
2. AI executes mission  
3. AI runs: cmosctl mission complete <id> → auto-updates everything
4. Git commit → hook auto-logs session (optional)
```

### Sprint Transitions

**Before (Manual)**:
- Review backlog.yaml
- Manually update roadmap
- Remember learnings/decisions

**After (Automated)**:
- `cmosctl status` → see sprint summary
- Decisions captured in `decisions` table
- Facts captured in `facts` table
- Can query: `SELECT * FROM decisions WHERE mission_id LIKE 'B1.%'`

---

## E) Mission Protocol Integration

**Simple Integration** (not RPC, just compatible):

1. **Mission Planning**: Mission Protocol generates mission YAML files
   - Save to `cmos/missions/sprint-XX/`
   - Use `cmosctl mission add` to register in database
   - Or: Parse YAML files and auto-register

2. **Mission Protocol Can Read CMOS**:
   - Mission Protocol can call `cmosctl context` to get project state
   - Mission Protocol can call `cmosctl kb search` to find relevant docs
   - Both tools remain standalone but work together

3. **Future RPC** (optional):
   - If needed, add `cmosctl mp call <action>` later
   - For now, manual integration is fine

---

## F) Build Plan (Simplified)

### Week 1: Core Automation MVP
**Goal**: Eliminate manual file edits for session execution

**Deliverables**:
1. Database schema + `cmosctl db init`
2. Basic CLI:
   - `mission list|next|complete|block`
   - `session log`
   - `hook install`
3. Git hook that logs commits
4. Simple state tracking (no complex FSM)

**Acceptance**:
- ✅ Can execute playbook Phase 3 without touching YAML/JSON files
- ✅ Git commits auto-log as sessions
- ✅ Mission completion auto-promotes next mission

### Week 2: Memory & KB (Optional)
**Goal**: Systematic knowledge capture

**Deliverables**:
1. `decisions` and `facts` tables working
2. `cmosctl decision` and `cmosctl fact` commands
3. Basic KB indexing (`cmosctl kb index`)
4. FTS5 search (`cmosctl kb search`)

**Acceptance**:
- ✅ Can capture decisions during sprint
- ✅ Can search project docs contextually
- ✅ Sprint transitions have captured learnings

### Week 3: Polish & Integration
**Goal**: Smooth Mission Protocol integration + any missing pieces

**Deliverables**:
1. `cmosctl context` exports for Mission Protocol
2. Auto-register missions from YAML files (optional)
3. Better status/summary commands
4. Documentation

---

## G) File Structure

```
.cmos/                           # Hidden folder (like .git)
  └── memory.db                  # Single SQLite file

cmos/                            # Project structure (unchanged)
  ├── docs/
  │   ├── roadmap.md
  │   ├── technical_architecture.md
  ├── missions/
  │   ├── sprint-01/
  │   │   ├── B1.1_mission.yaml  # Mission Protocol generates these
  │   │   └── B1.2_mission.yaml
  │   └── templates/
  └── context/
      └── MASTER_CONTEXT.json     # Optional, can query DB instead
```

**Portability**: Copy entire project folder → `.cmos/memory.db` comes along.

**Auditability**: 
- Use `cmosctl export` to generate readable YAML/JSON files for inspection
- Use `cmosctl db shell` for direct SQL queries
- Use `cmosctl mission verify` for automated QA checks
- Mission YAML files still exist in `cmos/missions/` for reference

---

## H) Design Decisions

### Why SQLite?
- Single file, portable
- No server needed
- Atomic operations
- Built into Python/Node

### Why `.cmos` (hidden)?
- Like `.git`, keeps project clean
- Clear it's tooling, not user files
- Easy to gitignore if needed

### Why Simple State?
- FSM can be added later if needed
- Current playbook works fine without complex state machine
- Start with: "What's current mission?" → simple query

### Why Defer KB?
- Can add if needed
- Current playbook doesn't require it
- FTS5 is simple to add later

### Why Manual Mission Protocol Integration?
- Both tools work standalone
- Manual integration is clearer initially
- Can add RPC if workflow demands it

---

## I) Risks & Mitigation

**Risk**: Over-engineering  
**Mitigation**: Cut features ruthlessly. If it's not eliminating manual work, defer it.

**Risk**: Database becomes unportable  
**Mitigation**: Single file, SQLite is widely supported. Can export to JSON if needed.

**Risk**: CLI complexity  
**Mitigation**: Start with 5-6 commands. Add only if manually doing it repeatedly.

**Risk**: Breaking existing workflow  
**Mitigation**: Keep playbook unchanged. CLI is just automation layer.

---

## J) Success Criteria

**MVP (Week 1) is successful when**:
1. ✅ Can execute full Phase 3 session without editing YAML/JSON files
2. ✅ Git commits automatically tracked
3. ✅ Mission completion auto-promotes next mission
4. ✅ All existing playbook steps work, just automated

**Week 2 is successful when**:
1. ✅ Decisions/findings captured during sprint
2. ✅ Sprint transition has systematic knowledge to review
3. ✅ Can search project docs when needed

---

## K) Auditability & Manual Intervention

### Problem: DB is opaque compared to flat files

**Solutions**:

1. **Export Commands** (Human-readable formats)
   - `cmosctl export backlog` → `backlog.yaml` (for inspection)
   - `cmosctl export sessions` → `SESSIONS.jsonl` (for audit)
   - `cmosctl export all` → Full export for backup/review

2. **Direct DB Access**
   - `cmosctl db shell` → Opens SQLite REPL for manual queries
   - Standard SQLite tools work: `sqlite3 .cmos/memory.db`

3. **Validation/QA Commands**
   - `cmosctl mission verify` → Check all missions for issues
   - `cmosctl mission incomplete` → List missions missing fields
   - `cmosctl mission audit <sprint>` → Audit sprint for gaps

4. **Edit Commands**
   - `cmosctl mission edit <id>` → Edit mission (opens editor)
   - `cmosctl mission edit <id> --status <status>` → Quick field updates
   - Direct DB editing via `cmosctl db shell` if needed

5. **Inspection Commands**
   - `cmosctl mission show <id>` → Full mission details
   - `cmosctl session list --mission <id>` → Sessions for a mission
   - `cmosctl status --verbose` → Detailed state inspection

### Workflow for QA/Debugging

**Before (with flat files)**:
```
1. Open backlog.yaml → visually inspect
2. Check SESSIONS.jsonl → grep for issues
3. Edit YAML directly if needed
```

**After (with DB)**:
```
1. cmosctl mission verify → automated checks
2. cmosctl export backlog → inspect YAML if needed
3. cmosctl mission show <id> → detailed view
4. cmosctl db shell → direct SQL for complex queries
5. cmosctl mission edit <id> → fix issues
```

**Or** (if you prefer flat files):
```
1. cmosctl export all → generate files
2. Edit exported files manually
3. cmosctl db import → load back into DB
```

---

## L) Installation & Distribution

### Phase 1: Development (Current)
- Install locally: `pip install -e .` from repo
- CLI available as `cmosctl` after install

### Phase 2: Distribution (Post-Sprint 3)
- **Primary**: `pip install cmos` (Python package on PyPI)
- **Alternative**: `npm install -g cmos` (if Node.js preferred)
- **Binary**: Single executable (via PyInstaller/Nuitka) - future

### Installation Experience

```bash
# Install
pip install cmos

# Initialize project (one-time per project)
cd my-project
cmosctl db init

# Use
cmosctl mission next
cmosctl mission complete B1.1
```

### Requirements
- **Python 3.8+** (primary)
- **SQLite 3.x** (built-in with Python)
- **Optional**: Node.js if offering npm package

### Package Structure (for pip install)

```
cmos/
  ├── __init__.py
  ├── cli/
  │   ├── __init__.py
  │   ├── commands.py       # All CLI commands
  │   └── db.py             # DB operations
  ├── core/
  │   ├── schema.py         # DB schema
  │   └── models.py         # Data models
  └── setup.py              # pip install config
```

**Entry Point**: `cmosctl` command available after `pip install`

---

## Summary

**This is a lightweight automation layer** that:
- Replaces manual file edits with simple CLI
- Captures knowledge systematically (decisions, facts)
- Stays hidden and portable (`.cmos/memory.db`)
- Works with existing playbook (no changes needed)
- Integrates with Mission Protocol (manual, compatible)

**Not building**: Complex orchestration, heavy validation, metrics dashboards, or heavy infrastructure.

**Future additions**: Only if manually doing something repeatedly that could be automated.

