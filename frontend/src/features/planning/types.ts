export interface RepositoryOption { id: string; display_url: string; credential_ref_configured: boolean }
export interface RepositorySnapshot { id: string; repository_id: string; target_sha: string; content_hash: string; created_at: string }
export interface Idea { id: string; title: string; version: number; created_at: string }
export interface Acceptance { key: string; condition: string; verificationMethod: string; requiredEvidence: string[] }
export interface ReuseRef { path: string; targetSha: string; startLine: number; endLine: number; reason: string }
export interface Deliverable { key: string; kind: 'API' | 'DATA' | 'COMPONENT' | 'DOCUMENT' | 'OTHER'; description: string; version: string; availabilityCondition: string }
export interface PlannedIssue { key: string; title: string; goal: string; scope: string; acceptanceCriteria: Acceptance[]; reuseRefs: ReuseRef[]; deliverables: Deliverable[]; assumptions: string[] }
export interface Dependency { consumer: string; provider: string; deliverable: string; condition: string; reason: string }
export interface PlanBody { kind: 'PLAN'; summary: string; questions: []; issues: PlannedIssue[]; dependencies: Dependency[]; risks: string[] }
export interface PlanVersion { id: string; idea_revision_id: string; idea_revision_no: number; planning_run_id: string; sequence_no: number; version: number; parent_plan_id: string | null; status: 'DRAFT' | 'CONFIRMED' | 'SUPERSEDED'; content_hash: string; repository_id: string; target_sha: string; body: PlanBody; confirmed_at: string | null }
export interface Question { id: string; planning_run_id: string; question_key: string; question: string; reason: string; answer: string | null }
export interface AgentTask { id: string; status: string; last_error_code: string | null }
export interface PlanningDetail { idea: Idea; revision: { id: string; revision_no: number; content: string }; questions: Question[]; latestRun: { id: string; status: string } | null; agentTask: AgentTask | null; plans: PlanVersion[] }
export interface AgentEvent { eventSeq: number; eventType: string; agentInstanceId: string; parentAgentInstanceId: string | null; occurredAt: string; payloadRedacted: { agentKey?: string; childInstanceId?: string; name?: string; ok?: boolean } }
export interface PlanDiff { addedIssueKeys: string[]; removedIssueKeys: string[]; changedIssueKeys: string[]; affectedIssueKeys: string[]; dependenciesChanged: boolean }
export interface PlanningPermissions { role: string; canPlan: boolean; canConfirm: boolean }
