export type RiskLevel = "P0" | "P1" | "P2";
export type VerificationStatus =
  "已确认" | "自动通过" | "代码证据支持" | "部分支持" | "待人工确认" | "证据不足" | "未完成分析" | "存在冲突";

export interface ProjectTodo {
  id: string;
  name: string;
  pendingCount: number;
  approvalCount: number;
  p0Count: number;
  nextAction: string;
}

export interface VerificationTask {
  id: string;
  title: string;
  snapshot: string;
  analysisRun: string;
  reportStatus: string;
  riskSummary: string;
  owner: string;
  updatedAt: string;
}

export interface EvidenceReference {
  id: string;
  kind: "需求" | "代码" | "测试" | "人工补证";
  title: string;
  locator: string;
  excerpt: string;
  state: "已引用" | "待补充";
}

export interface VerificationConclusion {
  id: string;
  requirement: string;
  status: VerificationStatus;
  summary: string;
  needsHumanDecision: boolean;
  risk: RiskLevel | null;
  evidenceIds: string[];
  systemStatus?: string;
  humanDecision?: {
    id: string;
    decision: string;
    note: string;
    actorId: string;
    createdAt: string | null;
  } | null;
  allowedHumanDecisions?: string[];
  evidenceAssessments?: Array<{ evidenceId: string; relation: string; reason: string; producedBy: string }>;
}
