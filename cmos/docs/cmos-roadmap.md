# CMOS v2.0 Roadmap

**Goal**: Build a lightweight automation layer that eliminates manual file upkeep from the current CMOS Playbook workflow.

**Timeline**: 3 weeks (3 sprints)

---

## Sprint 1: Core Automation MVP

**Focus**: Eliminate manual file edits during session execution + auditability

**Deliverables**:

1. **Database Foundation**
   - SQLite schema (`missions`, `sessions`, `project_state`, `decisions`, `facts`)
   - `cmosctl db init` command
   - `.cmos/memory.db` creation
   - `cmosctl db shell` - Direct SQL access
   - `cmosctl db export/import` - Backup/restore

2. **Mission Management CLI**
   - `cmosctl mission list` - Show all missions
   - `cmosctl mission next` - Get current mission (for AI prompts)
   - `cmosctl mission complete <id>` - Mark done, auto-promote next
   - `cmosctl mission block <id>` - Mark blocked
   - `cmosctl mission add/edit/show` - Manual management
   - `cmosctl mission verify/incomplete/audit` - QA commands

3. **Session Tracking**
   - `cmosctl session log --type <action> --mission <id> --summary <text>`
   - `cmosctl session list/show` - Inspection commands
   - Replaces manual SESSIONS.jsonl edits

4. **Git Integration**
   - `cmosctl hook install` - Write post-commit hook
   - Auto-log commits as sessions

5. **Status & Export Commands**
   - `cmosctl status` - Show current sprint/mission
   - `cmosctl context` - Export JSON for AI prompts
   - `cmosctl export backlog/sessions/all` - Human-readable exports

**Success Criteria**:
- ✅ Can execute Phase 3 (Session Execution) without editing YAML/JSON files
- ✅ Mission completion automatically promotes next mission
- ✅ Git commits automatically tracked
- ✅ Can audit/verify missions for QA (verify, incomplete, audit commands)
- ✅ Can export to readable formats for inspection (backlog.yaml, SESSIONS.jsonl)
- ✅ Can manually edit missions when needed (edit command, db shell)
- ✅ All existing playbook steps work, just automated

**Out of Scope** (defer):
- KB indexing
- Complex validation
- Mission Protocol RPC
- Metrics dashboards

---

## Sprint 2: Memory & Knowledge Capture

**Focus**: Systematic knowledge capture for better sprint transitions

**Deliverables**:

1. **Memory Commands**
   - `cmosctl decision --title "..." --rationale "..."`
   - `cmosctl fact --kind <kind> --content "..."`
   - Store in `decisions` and `facts` tables

2. **Basic KB (Optional)**
   - `cmosctl kb index` - Index `cmos/docs/**` and `cmos/missions/**`
   - `cmosctl kb search "query"` - FTS5 search
   - Simple chunking (no embeddings)

3. **Sprint Transition Tools**
   - Query commands to review sprint learnings
   - Export decisions/findings for roadmap updates

**Success Criteria**:
- ✅ Can capture decisions during sprint execution
- ✅ Sprint transitions have systematic knowledge to review
- ✅ Can search project docs when planning next sprint
- ✅ Better context available for Mission Protocol integration

**Deferred if Not Needed**:
- KB can be skipped if search isn't valuable
- Can add later if manually searching docs repeatedly

---

## Sprint 3: Polish & Integration

**Focus**: Mission Protocol integration + any missing automation

**Deliverables**:

1. **Mission Protocol Integration**
   - `cmosctl context` format optimized for Mission Protocol
   - Auto-register missions from YAML files (optional)
   - Documentation on integration patterns

2. **Enhanced Status/Reporting**
   - Better `cmosctl status` output
   - Sprint summary queries
   - Context export improvements

3. **Migration Tools** (if needed)
   - One-time import from flat files (for existing projects)

4. **Documentation**
   - User guide
   - Integration guide with Mission Protocol
   - CLI reference

**Success Criteria**:
- ✅ Smooth workflow with Mission Protocol
- ✅ All common manual tasks automated
- ✅ Clear documentation for users
- ✅ System is production-ready

---

## Key Principles

1. **Lightweight**: Single database file, minimal CLI surface
2. **Portable**: Copy folder → everything works
3. **Compatible**: Works with existing playbook (no breaking changes)
4. **Practical**: Only build what eliminates manual work

---

## Success Metrics

**Week 1**:
- Manual file edits eliminated for session execution
- 100% of Phase 3 steps automated

**Week 2**:
- Decisions/findings captured during sprints
- Sprint transitions faster (systematic knowledge available)

**Week 3**:
- Mission Protocol integration smooth
- Documentation complete
- Ready for production use

---

## Risks & Mitigation

**Risk**: Feature creep  
**Mitigation**: Defer anything not eliminating manual work. Can add later.

**Risk**: Breaking existing workflow  
**Mitigation**: CLI is additive. Old flat files can coexist (migration optional).

**Risk**: Over-engineering  
**Mitigation**: Start minimal. Add only if manually doing repeatedly.

---

## Future Enhancements (Post-Sprint 3)

**Only if manually doing repeatedly**:
- Advanced metrics/analytics
- Complex FSM orchestration
- Mission Protocol RPC
- Embeddings for KB
- Validation gates

**Philosophy**: Build only what you're manually doing.

