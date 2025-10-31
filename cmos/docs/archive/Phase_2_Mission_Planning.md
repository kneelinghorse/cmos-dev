# Phase 2: Mission Planning

## Overview

**Goal:** Transform your foundational documents (roadmap.md and technical_architecture.md) into concrete, executable missions for Sprint 1.

Phase 2 is where planning becomes action. You'll create the folder structure and individual mission files that AI agents will execute in later phases.

---

## Prerequisites

Before starting Phase 2, you must have:

- [ ] Completed Phase 1 (both foundational documents finished)
- [ ] Sprint 1 clearly defined in both roadmap.md and technical_architecture.md
- [ ] Clear understanding of Sprint 1 deliverables

---

## Phase 2 Process

### Step 1: Create Sprint 1 Folder Structure

Set up the directory structure for Sprint 1 missions.

**Action Items:**
- [ ] Create `/missions/sprint-01/` directory
- [ ] Create `/missions/sprint-01/research/` subdirectory


```
missions/
└── sprint-01/
    ├── research/R1.1_Research_Mission_name.yaml
    └── B1.1_Build-Mission-Name.yaml
```

### Step 2: Decision Point - Research vs. Build

**Critical Question:** Does Sprint 1 need research to inform the build missions?

#### How to Decide

Ask yourself (or an AI assistant):
- Do I have sufficient technical details to begin building?
- Are there unknowns about algorithms, performance, or implementation approaches?
- Would targeted research help inform better technical decisions?
- Did my initial research leave gaps specific to Sprint 1 work?

**Common scenarios:**

**Research IS needed when:**
- Technical architecture has open questions or unknowns
- Sprint 1 involves unfamiliar technologies or patterns
- Performance requirements need validation
- Multiple implementation approaches need evaluation
- Integration patterns need investigation

**Research is NOT needed when:**
- Sprint 1 is boilerplate or well-understood setup
- Technical details are fully specified in architecture doc
- Prior research already covers all Sprint 1 needs
- Using established patterns or libraries

**Action Items:**
- [ ] Review your technical_architecture.md Sprint 1 section
- [ ] Identify any unknowns or open questions
- [ ] Make the decision: Research first, or proceed to build?

### Step 3A: If Research Needed - Create Research Missions

If you determined research is needed, create research missions that will inform your build missions.

#### Mission Naming Convention

Research missions are numbered sequentially:
- `R1.1_[topic].md` - First research mission
- `R1.2_[topic].md` - Second research mission
- `R1.3_[topic].md` - Third research mission
- etc.

#### Using the Research Template

Location: `/missions/templates/RESEARCH_TEMPLATE.md`

**For each research mission:**

1. **Copy the template** to `/missions/sprint-01/research/R1.#_[topic].md`
2. **Fill in Mission Metadata**
   - Estimated tokens (5k-25k recommended)
   - AI system you'll use
   - Parallel tracks (other missions running simultaneously)
   - Dependencies (previous missions this builds on)

3. **Define Research Objectives**
   - 3-5 specific questions that fit within a single session
   - Focus on quantitative, qualitative, feasibility, and technical depth
   - Keep scope to what can be answered in one session

4. **Plan Token Budget**
   - Initial prompt with context: ~2k tokens
   - Research queries: ~3k tokens
   - Response space: ~15-20k tokens
   - Follow-up refinements: ~5k tokens

5. **Define Success Criteria**
   - What specific insights will enable build missions?
   - What performance metrics need to be discovered?
   - What implementation patterns need to be documented?

**Example Research Missions for Sprint 1:**
```
R1.1_algorithm_selection.md     - Which algorithm/approach to use?
R1.2_performance_benchmarks.md  - What are realistic performance targets?
R1.3_integration_patterns.md    - How should components integrate?
```

#### Research Synthesis (Optional)

For complex research efforts, you may want to create a synthesis document that consolidates findings across multiple research missions. This is context-dependent and most valuable when:
- You have 3+ research missions with overlapping insights
- Findings need to be cross-validated
- Multiple build missions will reference the same research

**If creating synthesis:**
- Create `/missions/research/RS1.1_SYNTHESIS-Topic.md`
- Consolidate key findings from all R1.# missions
- Document consensus findings across different research
- Resolve any contradictions
- Extract actionable insights for build missions

**Action Items (if research needed):**
- [ ] Identify n research topics for Sprint 1
- [ ] Create R1.1, R1.2, R1.3... mission files using mission protocol template
- [ ] Sythensize research missions and use findings to guide build implementation details
- [ ] Determine if contextual examples, cross-referenced files or additional contextual files are needed, cross link to research in cmoss/missions/research/

### Step 3B: If No Research Needed - Skip to Build Planning

If your Sprint 1 technical details are fully specified, proceed directly to creating build missions (Step 4).

### Step 4: Create Build Missions

Create the build mission files that will implement Sprint 1 deliverables.

#### Mission Naming Convention

Build missions are numbered sequentially:
- `B1.1_[component].yaml` - First build mission
- `B1.2_[component].yaml` - Second build mission
- `B1.3_[component].yaml` - Third build mission
- etc.

#### Using the Build Template

Location: `/missions/templates/Build.Implementation.v1.yaml

**For each build mission:**

1. **Copy the template** to `/missions/sprint-01/build/B1.#_[component].yaml`

2. **Fill in Mission Metadata**
   - Estimated tokens (10k-30k recommended per session)
   - Complexity (Low/Medium/High)
   - Dependencies (previous missions required - can be research or other build missions)
   - Enables (future missions this unblocks)

3. **Plan Token Budget**// this is covered by Mission prtocol
   ```yaml
   context_load:
     project_context: 2k
     previous_code: 3k
     research_findings: 2k
   
   generation_budget:
     implementation: 15k
     tests: 5k
     documentation: 3k
   
   validation_reserve: 5k
   total_estimated: 35k
   ```

4. **Reference Research Foundation** (if applicable)
   
   Link to research missions that inform this build:
   ```markdown
   ## Research Foundation
   Applied findings from research missions:
   - **R1.1**: [Specific algorithm/pattern to implement]
   - **R1.2**: [Performance target to meet]
   - **R1.3**: [Constraint to respect]
   ```
   
   **Example with file path reference:**
   ```markdown
   ## Research Foundation
   - **R1.1**: Please review algorithm research here: 
     `/missions/sprint-01/research/R1.1_algorithm_selection.md`
   - **R1.2**: Performance benchmarks documented here:
     `/missions/sprint-01/research/R1.2_performance_benchmarks.md`
   ```

5. **Define Implementation Scope**
   - Core deliverable for THIS session
   - What's explicitly out of scope (for future missions)
   - Keep scope to what fits in one session

6. **Set Success Criteria**
   - Core functionality checkpoints
   - Test coverage requirements
   - Performance baselines
   - Documentation completeness

7. **Create Implementation Checklist**
   - Essential (This Session) - must complete
   - Deferred (Next Mission) - explicitly postponed

#### Mission Sizing Guidelines

**Split this mission if:**
- Estimated tokens > 40k
- Multiple unrelated components
- Can't complete in one session
- Dependencies not ready

**Combine with next if:**
- Under 10k tokens estimated
- Tightly coupled logic
- Same test suite
- Minimal context switch

**Action Items:**
- [ ] Break down Sprint 1 into individual build missions
- [ ] Create B1.1, B1.2, B1.3... mission files using template
- [ ] Fill out all sections of each build mission
- [ ] Cross-reference any research missions in dependencies
- [ ] Verify each mission is properly scoped for single session
- [ ] Document what each mission enables for future work

### Step 5: Map Dependencies and Sequence

While parallelization is optional, understanding dependencies helps with planning.

**Dependency Mapping:**

For each mission (research and build), document:
- **Dependencies**: What must be completed before this mission?
- **Enables**: What does this mission unlock?

**Example dependency chain:**
```
R1.1 (Algorithm Research)
  ↓
B1.1 (Core Implementation) ← depends on R1.1
  ↓
B1.2 (Tests) ← depends on B1.1
  ↓
B1.3 (Integration) ← depends on B1.1, B1.2

R1.2 (Performance Research) ← can run parallel to B1.1
  ↓
B1.4 (Optimization) ← depends on B1.1, B1.2, R1.2
```

**Notes on Parallelization:**
- Parallelization is optional - you can execute all missions sequentially
- Human manages dependencies outside the system
- If you have team/capacity, missions without dependencies can run simultaneously
- Most individual builders will execute missions one at a time

**Action Items:**
- [ ] Review dependencies field in all mission files
- [ ] Verify logical sequence makes sense
- [ ] Identify which missions (if any) could run in parallel
- [ ] Document the intended execution order

### step 5.1 Initialize Backlog

The backlog captures all missions for the current sprint at a glance.

**Create `/missions/backlog.yaml`:**

```yaml
# backlog.yaml - Sprint Plan Metadata
name: "Planning.SprintPlan.v1"
version: "1.0.0"
displayName: "Sprint Plan Orchestrator"
description: "Master backlog tracking all sprints, missions, and dependencies"
author: "Your Name/Team"
schema: "./schemas/SprintPlan.v1.json"

---

# Mission File: project-main-backlog.yaml

missionId: "SP-MAIN-001"

objective: "To successfully track, manage, and complete all planned development sprints from foundation through final delivery."

context: |
  This mission file represents the master backlog and sprint plan for the [Your Project Name] project.
  It provides a single source of truth for what has been completed, what is in progress, and what is planned.
  This structured format allows for automated status tracking and dependency management.

successCriteria:
  - "All missions within the current sprint are moved through 'Current' to 'Completed' status."
  - "Sprint transitions are properly documented with learnings captured."

deliverables:
  - "A fully updated version of this mission file with accurate sprint and mission status."

domainFields:
  type: "Planning.SprintPlan.v1"

  sprints:
    # Completed Sprints (example structure)
    - sprintId: "Sprint 1"
      title: "Foundation - [Your Sprint Theme]"
      focus: "[Brief description from roadmap]"
      status: "Completed"
      missions:
        - { id: "B1.1", name: "[Component Name]", status: "Completed" }
        - { id: "B1.2", name: "[Component Name]", status: "Completed" }
        - { id: "B1.3", name: "[Component Name]", status: "Completed" }

    # Current Sprint
    - sprintId: "Sprint N"
      title: "[Sprint Theme]"
      focus: "[Brief description from roadmap]"
      status: "In Progress"
      missions:
        - { id: "BN.1", name: "[Component Name]", status: "Current" }
        - { id: "BN.2", name: "[Component Name]", status: "Queued" }
        - { id: "BN.3", name: "[Component Name]", status: "Queued" }

    # Future Sprints
    - sprintId: "Sprint N+1"
      title: "[Next Sprint Theme]"
      focus: "[Brief description from roadmap]"
      status: "Planned"
      missions:
        - { id: "BN+1.1", name: "[Component Name]", status: "Planned" }
        - { id: "BN+1.2", name: "[Component Name]", status: "Planned" }

  # Mission Dependencies
  missionDependencies:
    - { from: "BN.1", to: "BN.2", type: "Blocks" }
    - { from: "BN.1", to: "BN.3", type: "Blocks" }
    - { from: "BN.2", to: "BN.4", type: "Blocks" }
    - { from: "BN.3", to: "BN.4", type: "Blocks" }

  # Sprint Success Metrics
  successMetrics:
    - "[Key metric from roadmap]"
    - "[Key metric from roadmap]"
    - "[Key metric from roadmap]"
```

**Key Points:**
- List ALL current sprint missions
- Mark completed missions with status "Completed"
- Mark first build mission as status "Current"
- Keep other missions as status "Queued"
- Include success metrics from roadmap

**Action Items:**
- [ ] Copy template above to `/missions/backlog.yaml`
- [ ] Fill in current sprint mission details from Phase 2
- [ ] Add mission dependency relationships
- [ ] List success metrics from roadmap.md


### Step 6: Cross-Validate Mission Plan

Ensure your missions align with your foundational documents and are properly scoped.

**Validation Checklist:**

**Alignment with Roadmap:**
- [ ] All Sprint 1 deliverables from roadmap.md are covered by missions
- [ ] Mission scope matches Sprint 1 complexity estimate
- [ ] Success criteria align with roadmap metrics

**Alignment with Architecture:**
- [ ] All Sprint 1 components from technical_architecture.md have build missions
- [ ] Research missions address architectural unknowns
- [ ] Mission sequence follows architecture build order

**Mission Quality:**
- [ ] Each mission is scoped for single session completion
- [ ] Token budgets are realistic (10k-40k per mission)
- [ ] Dependencies are clearly documented
- [ ] Success criteria are measurable
- [ ] Research missions have 3-5 specific questions
- [ ] Build missions reference relevant research

**Completeness:**
- [ ] All necessary research missions created
- [ ] All Sprint 1 components have build missions
- [ ] First mission has no dependencies (can start immediately)
- [ ] Last mission delivers complete Sprint 1 functionality

### Step 7: Finalize Sprint 1 Mission Plan

Review and prepare for execution.


**Final Checklist:**
- [ ] Sprint 1 folder structure is complete
- [ ] All research missions are done and properly referenced in the build mission
- [ ] All build missions are detailed and ready to execute
- [ ] Dependencies are clearly mapped
- [ ] Each mission uses the appropriate template
- [ ] Mission files are properly named (R1.#, B1.#)
- [ ] Cross-references between missions are accurate
- [ ] Token budgets are estimated for all missions
- [ ] Success criteria are defined for all missions

---

## What Happens After Phase 2?

Once your Sprint 1 missions are planned and documented, you'll move to **Phase 3: Session Execution**, where individual missions are executed by AI agents in single sessions.

Phase 3 will detail:
- How to execute a single research mission
- How to execute a single build mission
- Session-level process and validation
- Capturing results and updating mission status
- Transitioning between missions

---

## Tips for Effective Mission Planning

### Start with Research First
If in doubt about whether research is needed, err on the side of doing targeted research. A few focused research missions can save significant rework in build missions.

### Keep Missions Atomic
Each mission should deliver one complete thing. If a mission feels like it's doing multiple things, split it into multiple missions.

### Size Missions Conservatively
Better to have 8 well-scoped missions that succeed than 4 ambitious missions that overflow. You can always combine missions later, but splitting mid-session is disruptive.

### Document the "Why"
In both research and build missions, capture the reasoning behind decisions. This context is invaluable for later missions and future sprints.

### Reference, Don't Duplicate
Build missions should reference research missions by file path. Don't copy research findings into build missions - link to the source of truth.

### Think in Sessions
A "session" is a single AI agent working period. Plan missions around what can be accomplished in one focused session, not calendar time.

---

## Common Pitfalls to Avoid

### Pitfall 1: Mission Scope Creep
**Problem:** Missions expand beyond single session as you plan
**Solution:** Be ruthless about scope. Split missions early and often.

### Pitfall 2: Skipping Research
**Problem:** Building without sufficient technical detail, leading to rework
**Solution:** When in doubt, create a focused research mission.

### Pitfall 3: Unclear Dependencies
**Problem:** Can't determine what to execute next
**Solution:** Explicitly document dependencies in mission metadata.

### Pitfall 4: No Success Criteria
**Problem:** Can't determine when a mission is "done"
**Solution:** Define measurable success criteria before execution.

### Pitfall 5: Research Without Build Connection
**Problem:** Research missions that don't inform specific build missions
**Solution:** Each research mission should enable 1+ build missions.

---

## Phase 2 Completion Checklist

You're ready to move to Phase 3 when:

- [ ] `/missions/sprint-01/` directory structure exists
- [ ] All necessary research missions are created and detailed
- [ ] All necessary build missions are created and detailed
- [ ] Each mission file is complete (all template sections filled)
- [ ] Dependencies are mapped between missions
- [ ] Token budgets are estimated for all missions
- [ ] Success criteria are defined for all missions
- [ ] First mission (R1.1 or B1.1) is ready to execute
- [ ] You can explain what Sprint 1 will deliver via these missions

**Next Step:** Proceed to Phase 3 - Session Execution (individual mission execution process)
