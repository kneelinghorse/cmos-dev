CMOS: Agent Memory & Orchestration System
System Name: "CMOS" (Contextual Memory Orchestration System) MVP Target: 1-week refactor → Migrating from flat files to SQLite with a live FSM process guide.

Core Architecture Stack:
Local Memory: A single, project-local cmos/memory.db (SQLite) file for atomic, transactional state management. Replaces all JSON/YAML flat files.

Work Triggers: A .git/hooks/post-commit script to automatically log code-related work from the .git repo into the .cmos memory.

Process Orchestration: A database-driven Finite State Machine (FSM) that guides the agent, anticipates next steps, and creates gates for user approval.

External Integration: The Mission Protocol server, which is called by the FSM for high-level templates (e.g., sprint planning, reports).

Phase 1: Database Schema Refactor (The .cmos/memory.db)
This phase migrates all existing flat files into a single, resilient SQLite database. This provides atomicity for all agent operations.

Database Schema (SQLAlchemy / Python-style definition):

Python

# The single source of truth: cmos/memory.db

# Replaces: cmos/missions/backlog.yaml
class Mission(Base):
    __tablename__ = 'missions'
    mission_id = Column(String, primary_key=True)
    sprint_id = Column(String, nullable=True)
    description = Column(Text)
    status = Column(String, default='Queued') # Queued, Current, In Progress, Completed, Blocked
    created_at = Column(DateTime, default=func.now())
    completed_at = Column(DateTime, nullable=True)
    notes = Column(Text)
    needs = Column(Text) # For blocked status

# Replaces: cmos/SESSIONS.jsonl
class Session(Base):
    __tablename__ = 'sessions'
    session_id = Column(Integer, primary_key=True, autoincrement=True)
    ts = Column(DateTime, default=func.now())
    agent = Column(String)
    mission_id = Column(String, ForeignKey('missions.mission_id'))
    action = Column(String) # start, complete, blocked, commit_log
    status = Column(String)
    summary = Column(Text)
    
# Replaces: cmos/context/MASTER_CONTEXT.json
class Strategy(Base):
    __tablename__ = 'strategy'
    strategy_id = Column(Integer, primary_key=True, autoincrement=True)
    ts = Column(DateTime, default=func.now())
    architecture = Column(Text)
    roadmap = Column(Text)
    sprint_plan = Column(Text)
    # This is now a log, not just one file.
    
# --- NEW TABLES FOR FSM ORCHESTRATION ---

# Replaces: cmos/PROJECT_CONTEXT.json (and makes it smarter)
class ProjectState(Base):
    __tablename__ = 'project_state'
    key = Column(String, primary_key=True)
    value = Column(String)
    # Example rows:
    # ('current_state', 'In_Sprint')
    # ('active_sprint_id', 'sprint_004')
    # ('last_commit', 'a83fde0')

# This is your "Process Diagram as Data"
class ProcessGraph(Base):
    __tablename__ = 'process_graph'
    id = Column(Integer, primary_key=True, autoincrement=True)
    current_state = Column(String) # e.g., 'In_Sprint'
    event = Column(String)         # e.g., 'sprint_tasks_done'
    next_state = Column(String)    # e.g., 'Sprint_Review'
    suggested_action = Column(String) # e.g., 'run:sprint_report'
Phase 2: Trigger Integration (The .git -> .cmos Bridge)
This phase implements the post-commit Git hook to create an automatic, low-friction bridge between coding work and agent memory.

File: .git/hooks/post-commit (must be executable: chmod +x)

Bash

#!/bin/sh

# This script runs automatically after every successful commit.

# 1. Get commit details
COMMIT_HASH=$(git rev-parse HEAD)
COMMIT_MSG=$(git log -1 --pretty=%B)
FILES_CHANGED=$(git diff-tree --no-commit-id --name-only -r HEAD)

# 2. Get current state from our DB (optional, but powerful)
# This assumes a small CLI script or agent command exists
# CURRENT_MISSION=$(my_agent_cli get-active-mission)
CURRENT_MISSION="unknown" # Placeholder

# 3. Log this commit as a "Session" event in the SQLite DB
# We use the agent's own CLI to ensure it respects the DB schema
my_agent_cli log-event \
  --type "commit" \
  --agent "GitHook" \
  --mission "$CURRENT_MISSION" \
  --summary "$COMMIT_MSG" \
  --details "Commit: $COMMIT_HASH. Files: $FILES_CHANGED"

# 4. Update the project's 'last_commit' state
my_agent_cli set-state --key "last_commit" --value "$COMMIT_HASH"
Phase 3: Process Engine Implementation (The FSM)
This phase implements the agent's new "brain." Instead of a hard-coded prompt, the agent uses a simple loop guided by the process_graph table.

Example process_graph Data (Your "Diagram"):

current_state	event	next_state	suggested_action
In_Sprint	mission_completed	In_Sprint	select_next_mission
In_Sprint	sprint_tasks_done	Sprint_Review	call:MissionProtocol(sprint_report)
In_Sprint	mission_blocked	Blocked	log:blocker_and_notify_user
Blocked	unblocked	In_Sprint	select_next_mission
Sprint_Review	review_approved	Sprint_Planning	call:MissionProtocol(sprint_planning)
Sprint_Planning	plan_approved	In_Sprint	start_new_sprint
Startup	init_complete	Sprint_Planning	call:MissionProtocol(sprint_planning)

Export to Sheets

New Agent Logic (Python-style pseudo-code):

Python

class AgentOrchestrator:
    
    def __init__(self, db_path="cmos/memory.db"):
        self.db = connect_to_sqlite(db_path)

    def get_current_state(self):
        # "SELECT value FROM project_state WHERE key = 'current_state'"
        return self.db.query(ProjectState.value).filter_by(key='current_state').first()

    def get_next_step(self, current_state, event):
        # "SELECT * FROM process_graph WHERE ..."
        return self.db.query(ProcessGraph).filter_by(
            current_state=current_state, 
            event=event
        ).first()

    def set_current_state(self, new_state):
        # "UPDATE project_state SET value = ... WHERE key = 'current_state'"
        self.db.query(ProjectState).filter_by(key='current_state').update({'value': new_state})
        self.db.commit()

    def run_main_loop(self):
        # 1. AGENT WAKES UP
        state = self.get_current_state()
        print(f"Agent is in state: {state}")
        
        # 2. RUNS ACTION (This is your old logic, now simplified)
        #    e.g., run_mission(state)
        #    ...
        #    ... after running, an event is generated
        event_that_happened = "mission_completed" # or "sprint_tasks_done", etc.
        
        # 3. AGENT CONSULTS GUIDE
        next_step = self.get_next_step(state, event_that_happened)
        
        if not next_step:
            print(f"No defined process for state '{state}' and event '{event_that_happened}'. Awaiting instructions.")
            return

        # 4. AGENT SUGGESTS (THE "GATE")
        print(f"EVENT: {event_that_happened}")
        print(f"CURRENT STATE: {state}")
        print(f"SUGGESTED NEXT STATE: {next_step.next_state}")
        print(f"SUGGESTED ACTION: {next_step.suggested_action}")
        
        if get_user_approval("Shall I proceed?"):
            # 5. EXECUTE & UPDATE STATE
            self.execute_action(next_step.suggested_action) # This could call Mission Protocol
            self.set_current_state(next_step.next_state)
            print(f"State updated to: {next_step.next_state}")
        else:
            print("Action cancelled. Awaiting new instructions.")
Phase 4: Mission Protocol Integration
This defines the separation of concerns, clarifying the .git (local) vs. .github (server) analogy.

.cmos/memory.db (Local): Is the state tracker. It knows what sprint you're in, which task is active, and what the project's high-level state is (e.g., In_Sprint).

Mission Protocol (Server): Is the process server. It knows how to perform complex, templated tasks. It doesn't store the state, it just provides the process.

The suggested_action in the process_graph is the glue.

select_next_mission is a local action (agent queries its own DB).

call:MissionProtocol(sprint_report) is an external action (agent makes an API call to your server to get the templates and steps for building a sprint report).

MVP Refactor Deliverables
Week 1:

All agent logic refactored to use the central cmos/memory.db.

All jsonl and yaml state files are deprecated.

The post-commit hook is active and successfully populating the sessions table.

The AgentOrchestrator class is implemented.

A simple 3-step process (e.g., Sprint_Planning -> In_Sprint -> Sprint_Review) is defined in the process_graph and is functional.

Next Steps
Mission 1: Agent Self-Installation: Create a mission for the agent: "Write a script that, when run, creates the .git/hooks/post-commit file with the correct content and makes it executable."

Mission 2: Dynamic Process Loading: Create a mission: "Update the agent to query the Mission Protocol server for a list of available process maps. Allow the user to select one, and then populate the process_graph table with it."