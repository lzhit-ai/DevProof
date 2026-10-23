# AI-CodeReview Workbench UI Design

## Product framing

AI-CodeReview is a research-and-delivery workbench. Projects provide context,
task workspaces hold an immutable evidence snapshot, and the review agent helps
the user inspect, explain, and publish delivery conclusions. It is not a
generic agent builder.

## Shared shell

- A persistent left rail switches between Workbench, Projects, Knowledge,
  Tasks, Approvals, Delivery History, and Integrations.
- The top bar always exposes the active project, search, notifications, and
  current user.
- Dark graphite surfaces, restrained indigo accents, warm evidence highlights,
  and compact desktop-density tables form the visual system.
- Status colors are semantic: blue for running, amber for needs attention,
  red for P0 risks, green for published, and neutral gray for archived facts.

## Page map

### 1. Workbench home

The operational landing page. It shows urgent risks, in-flight review runs,
pending approvals, recent delivery activity, and a project switcher. The
primary action is Create delivery task.

### 2. Project overview

A project-level context page. It combines repository health, source coverage,
current tasks, recent published reports, and team ownership without becoming a
separate project-management product.

### 3. Project knowledge base

The user-facing name for evidence sources. Git repositories, requirement
documents, API references, test results, and attachments are presented as
source collections with freshness, snapshot, and access indicators. The
underlying model remains EvidenceSource, EvidenceSnapshot, and Citation.

### 4. Task center

A task queue with filters for state, risk, owner, and evidence readiness.
Each row exposes task scope, newest run, P0 risk count, report state, and the
next human action. Opening a task enters the notebook review workspace.

### 5. Notebook review workspace

The core daily page and the NotebookLM-inspired view. The left column keeps
the task-scoped knowledge sources visible. The central column pins the review
summary and continues into a context-bound agent conversation. The right
column lists risks and exact citations. Follow-up questions may create a new
analysis attempt, but they cannot mutate an approved or published report.

### 6. Approval and delivery history

The approval tab presents report diff, evidence integrity, decision controls,
and reviewer comments. Published records become immutable delivery history;
new evidence starts a new draft/version instead of overwriting the record.

### 7. Integrations and settings

Low-frequency configuration for read-only Git access, model providers, source
connections, and notification preferences. It is intentionally secondary to
the task workbench.

## Main user flow

1. Enter the workbench and locate a task requiring action.
2. Open the task notebook and inspect the pinned review summary.
3. Trace any risk into source citations, or ask the agent a follow-up question
   constrained to the selected evidence snapshot.
4. Add a permitted supplement or request another analysis attempt when the
   evidence is insufficient.
5. Send the report draft to approval; approve, reject, publish, or create a
   new version without altering previously published facts.

## Boundary rules surfaced by the UI

- Source selection is explicit and snapshot-bound.
- Every review assertion and answer that affects delivery has an evidence path.
- Human approval is visibly separate from agent output.
- The agent never presents a model inference as verified evidence.
- Published reports are read-only; later work is visibly a new version.
