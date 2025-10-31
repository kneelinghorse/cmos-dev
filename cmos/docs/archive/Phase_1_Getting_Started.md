# Getting Started with CMOS

## What is CMOS?

**CMOS** (Context + Mission Orchestration System) is an AI-agent-powered framework for building products through structured, session-based development. Rather than traditional time-based planning, CMOS organizes work into missions and sprints that can be executed by AI agents in modular sessions.

## Overview

The CMOS process is divided into phases. This guide covers **Phase 1: Foundation**, where you establish the core documents that will guide your entire project.

## Prerequisites

Before starting Phase 1, you must have:

- **Validated research and assumptions** about your product idea
- Sufficient understanding of the problem space to make informed architectural decisions
- Clear vision of what you're building and why

> **Note:** Research and validation are currently out of scope for CMOS. This system assumes you've already done the groundwork to understand your market, users, and technical feasibility.

---

structure

```
cmos
    ├── context
    │   └── MASTER_CONTEXT.json
    ├── docs
    │   ├── cmos-technical_architecture.md
    │   ├── roadmap.md
    │   └── sprint-00-research-plan.md
    ├── missions
    │   ├── backlog.yaml
    │   ├── research
    │   ├── sprint-00
    │   │   
    │   └── templates
    │       ├── Build.Implementation.v1.yaml
    │       └── Build.TechnicalResearch.v1.yaml
    ├── PROJECT_CONTEXT.json
    ├── reports
    └── SESSIONS.jsonl
    
```

## Phase 1: Foundation

**Goal:** Create the two foundational documents that will guide all subsequent development.

### The Two Core Documents

1. **`roadmap.md`** - Your project timeline, milestones, and success metrics
2. **`technical_architecture.md`** - Your technical implementation plan and system design

These documents serve as the "source of truth" for your project. As your build progresses and your vision evolves, you'll update these documents to reflect pivots, new learnings, and changing priorities.

---

## Step-by-Step: Completing Phase 1

### Step 1: Review the Template Files

Both foundational documents have template examples in the `/docs` directory:

- `/docs/roadmap.md` - Example: Smart API Client Generator roadmap
- `/docs/technical_architecture.md` - Example: OSS Health Monitor architecture

**Action Items:**
- [ ] Read both template files completely
- [ ] Note the structure and level of detail
- [ ] Identify which sections are most relevant to your project

### Step 2: Complete Your `roadmap.md`

Using the template as a guide, create your project roadmap.

**Key Sections to Include:**

1. **Executive Summary**
   - What you're building
   - Target timeline (in sprints, not calendar time)
   - Key success metrics

2. **Sprint Overview**
   - Break your project into logical sprints
   - Each sprint should have clear deliverables
   - Avoid calendar dates - use "Sprint 1", "Sprint 2", etc.

3. **Sprint-by-Sprint Breakdown**
   - Technical milestones for each sprint
   - Key decisions to be made
   - Success criteria
   - Dependencies between sprints

4. **Success Metrics**
   - How you'll measure progress at each sprint
   - Long-term goals (3-6 sprints out)
   - Leading indicators of success

5. **Risk Mitigation**
   - Technical risks and mitigation strategies
   - Market/business risks
   - Resource requirements

**Action Items:**
- [ ] Draft your executive summary
- [ ] Define your sprint structure (how many sprints to MVP?)
- [ ] Detail Sprint 1 completely
- [ ] Outline remaining sprints at high level
- [ ] Define success metrics for each sprint
- [ ] Document known risks and mitigation plans

### Step 3: Complete Your `technical_architecture.md`

Using the template as a guide, design your technical implementation.

**Key Sections to Include:**

1. **System Overview**
   - High-level architecture diagram (in text/ASCII or reference to image)
   - Core components and their relationships
   - Technology stack decisions

2. **Sprint-by-Sprint Implementation**
   - What gets built in each sprint
   - Technical dependencies
   - Service/component structure

3. **Data Architecture**
   - Database schemas
   - API structures
   - Data flow patterns

4. **Deployment Strategy**
   - Where and how you'll deploy
   - Environment setup
   - Infrastructure requirements

5. **Mission Planning Framework**
   - How work will be split into AI agent missions
   - Session-level planning approach
   - Parallel vs. sequential mission structure

**Action Items:**
- [ ] Define your core system architecture
- [ ] Map architecture to your roadmap sprints
- [ ] Document key technical decisions and rationale
- [ ] Identify which components can be built in parallel
- [ ] Plan your deployment approach
- [ ] Outline how Sprint 1 will be broken into missions

### Step 4: Cross-Validate Your Documents

Your roadmap and technical architecture should align perfectly.

**Validation Checklist:**
- [ ] Each roadmap sprint has corresponding technical detail
- [ ] Technical dependencies match roadmap sequence
- [ ] Success metrics are measurable with your architecture
- [ ] Resource requirements are realistic for your technical approach
- [ ] Sprint timelines align with architectural complexity
- [ ] Risk mitigation strategies are technically feasible

### Step 5: Review & Finalize

Before moving to Phase 2, ensure both documents are complete and coherent.

**Final Review Checklist:**
- [ ] Both documents are complete (no major TBD sections)
- [ ] Sprint 1 is detailed enough to begin mission planning
- [ ] Technical decisions are documented with rationale
- [ ] Success criteria are clear and measurable
- [ ] Documents are stored in `/docs` directory
- [ ] Both files are version controlled (recommended)

---

## What Happens After Phase 1?

Once your foundational documents are complete, you'll move to **Phase 2: Mission Planning**.

Phase 2 begins with a critical decision point:

**Question:** Does Sprint 1 require additional research to inform the technical build?

- **If YES** → Proceed to research sessions aimed at informing Sprint 1 build missions
- **If NO** → Proceed directly to creating `sprint-01_build.yaml`, which details all build missions for Sprint 1

### Understanding Mission-Based Planning

In CMOS, work is organized into:

- **Sessions** - Individual AI agent working periods (token-bounded)
- **Missions** - Specific pieces of work completed in one or more sessions
- **Sprints** - Groups of related missions that deliver meaningful project milestones

Missions can:
- Have dependencies on other missions
- Run in parallel when independent
- Be combined to complete a sprint

This avoids traditional time estimation issues and works naturally with AI agent workflows.
Missions should be created using the mission protocol system
---

## Tips for Success

### Start Specific, Stay Flexible

- Be highly detailed for Sprint 1
- Keep later sprints at a higher level
- Update documents as you learn and pivot

### Think in Missions

- When planning, ask: "Could an AI agent complete this in one session?"
- If no, break it down further
- If yes, that's a good mission scope

### Use Your Templates

- The example roadmap and architecture are realistic references
- Match their level of detail
- Adapt their structure to your domain

### Document Decisions

- Capture *why* you made technical choices
- Future you (or future AI agents) will need this context
- Rationale is as important as the decision itself

---

## Getting Help

Your foundational documents will be used by AI agents throughout the build process. The better detailed they are, the more effectively agents can:

- Understand project context
- Make aligned decisions
- Execute missions independently
- Maintain consistency across sprints

If you're unsure about any section, refer back to the template examples or consider whether additional research would help inform that area.

---

## Phase 1 Completion Checklist

You're ready to move to Phase 2 when:

- [ ] `roadmap.md` is complete with all sections filled out
- [ ] `technical_architecture.md` is complete with all sections filled out
- [ ] Sprint 1 is detailed in both documents
- [ ] Technical and roadmap documents are cross-validated
- [ ] You can clearly articulate what Sprint 1 will deliver
- [ ] You know whether Sprint 1 requires research or can proceed to build

**Next Step:** Determine if research is needed for Sprint 1, then proceed to Phase 2 documentation.
