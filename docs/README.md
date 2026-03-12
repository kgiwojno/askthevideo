# AskTheVideo — Documentation Structure

## Overview

All project documentation lives in `docs/`. The folder is split into two layers: **project documentation** (created during and after the build) and **original planning specs** (created before the build, kept as reference).

## File Map

```
docs/
├── README.md                  # This file — explains the docs structure
├── HANDOFF_ASKTHEVIDEO.md     # Master handoff document for presentations
├── API_ENDPOINTS.md           # Full API reference (11 endpoints)
├── DEVIATIONS.md              # 35 spec deviations, all documented
├── KNOWN_ISSUES.md            # Non-critical issues for future fix (7 items)
├── BUG_CASCADE_FAILURE.md     # Tool failure cascade bug analysis and fix
├── SUPABASE_SETUP.md          # Supabase setup: tables, RLS policies, maintenance
└── spec/                      # Original planning documents (pre-build)
    ├── PROJECT_PLAN.md        # High-level project plan and timeline
    ├── SYSTEM_DESIGN.md       # Architecture design and component diagrams
    ├── FASTAPI_BACKEND_SPEC.md # Backend API specification
    ├── ADMIN_PANEL_BACKEND_SPEC.md # Admin panel specification
    ├── CLAUDE_CODE_HANDOFF.md # Instructions for Claude Code (the AI builder)
    ├── COST_BREAKDOWN.md      # Token/cost projections
    └── SETUP_GUIDE.md         # Local development setup instructions
```

## Document Descriptions

### Project Documentation (root of `docs/`)

| File | Purpose | Audience |
|------|---------|----------|
| **HANDOFF_ASKTHEVIDEO.md** | Master document covering architecture, development journey, challenges, what worked/didn't, testing, costs, and key numbers. Use this to build presentations and commercial materials. | Presentation prep, stakeholders |
| **API_ENDPOINTS.md** | Complete API reference: every endpoint with request/response schemas, error codes, SSE streaming format, session management, and free tier limits. | Developers, API consumers |
| **DEVIATIONS.md** | Every place where the actual build differs from the original spec. 35 entries with root cause, fix, and rationale. Summary table at the bottom. | Technical review, grading |
| **KNOWN_ISSUES.md** | Non-critical issues and edge cases identified during final review. Each entry has location, impact, why it was deferred, and a suggested future fix. 7 items documented. | Future development |
| **BUG_CASCADE_FAILURE.md** | Detailed analysis of the tool failure cascade bug: root cause, options considered, fix applied, and remaining edge case. | Technical reference |
| **SUPABASE_SETUP.md** | Complete Supabase setup guide: table schemas, RLS policies, environment separation, verification steps, and maintenance SQL. | Setup, ops |

### Original Planning Specs (`docs/spec/`)

These are the **pre-build planning documents** — the original specifications written before any code was implemented. They are kept as reference to show what was planned vs what was built. The differences are tracked in `DEVIATIONS.md`.

| File | What it defined |
|------|----------------|
| **PROJECT_PLAN.md** | Project scope, phases, timeline, and deliverables |
| **SYSTEM_DESIGN.md** | Full architecture: components, data flow, embedding strategy, caching, session management, deployment |
| **FASTAPI_BACKEND_SPEC.md** | Backend API spec: endpoints, request/response formats, error handling, SSE streaming |
| **ADMIN_PANEL_BACKEND_SPEC.md** | Admin dashboard: metrics endpoints, event logging, Pinecone stats |
| **CLAUDE_CODE_HANDOFF.md** | Instructions given to Claude Code for the Phase 2 production build |
| **COST_BREAKDOWN.md** | Token usage projections and cost estimates per tool |
| **SETUP_GUIDE.md** | Local development environment setup |

## How to Use

- **Starting a presentation?** Read `HANDOFF_ASKTHEVIDEO.md` — it has everything in one place.
- **Need API details?** Read `API_ENDPOINTS.md` — full request/response specs.
- **Reviewing what changed from the plan?** Read `DEVIATIONS.md` — 35 documented differences with explanations.
- **Want to understand the original vision?** Read `docs/spec/SYSTEM_DESIGN.md` and `docs/spec/FASTAPI_BACKEND_SPEC.md`.
- **Looking for open issues?** Read `KNOWN_ISSUES.md` — 7 items documented for future work.
- **Understanding the cascade failure bug?** Read `BUG_CASCADE_FAILURE.md` — full analysis, options, and fix.
