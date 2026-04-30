export type UiPhase =
  | 'initializing'
  | 'searching'
  | 'synthesizing'
  | 'paused_interrupt'
  | 'resuming'
  | 'writing_report'
  | 'done'
  | 'rejected'
  | 'failed';

export interface RunSummaryDto {
  id: string;
  topic: string;
  status: UiPhase;
  phase: UiPhase;
  created_at: string;
  updated_at: string;
  mode: 'dev' | 'live' | 'eval';
  report_format: 'deep_dive' | 'executive_brief';
  loop_count: number;
  max_loops: number;
  overall_score: number | null;
  token_total: number;
  cost_usd: number;
  artifact_available: boolean;
  is_active_session: boolean;
}

export interface SourceDto {
  id: number;
  url: string;
  domain: string;
  path: string;
  title: string;
  snippet: string;
}

export interface PipelineNodeDto {
  id: 'search_agent' | 'synthesis_agent' | 'human_review' | 'report_agent';
  label: string;
  tokens: number;
  secs: number;
  cost: number;
}

export interface ReviewPayloadDto {
  topic: string;
  draft: string;
  confidence: number;
  findings: Array<{ content: string; source_url: string; confidence: number }>;
  sources: Array<{ url: string; title: string; snippet: string }>;
  unresolved_gaps: string[];
  limitations: string[];
  loop_count: number;
  max_loops: number;
}

export interface ReviewDecisionInput {
  action: 'approve' | 'edit' | 'reject';
  additional_queries?: string[];
  edited_draft?: string;
  notes?: string;
  rejection_reason?: string;
}

export interface DraftViewDto {
  text: string;
  source_kind: 'none' | 'synthesis_draft' | 'edited_draft' | 'final_report';
  confidence: number | null;
  limitations: string[];
  sources: SourceDto[];
  title: string;
  executive_summary: string;
}

export interface EvaluationViewDto {
  ready: boolean;
  overall: number | null;
  scores: Record<string, number>;
  notes: string[];
  mode: string;
  model_name: string;
  search_provider: string;
  token_usage: Record<string, number>;
  node_timings: Record<string, number>;
  costs: Record<string, number>;
  limitations: string[];
  errors: string[];
}

export interface LogEntryDto {
  id: string;
  t: string;
  node: string | null;
  level: 'info' | 'ok' | 'warn' | 'err' | 'halt';
  msg: string;
}

export interface RunDetailDto {
  summary: RunSummaryDto;
  pipeline: {
    current_node: PipelineNodeDto['id'] | null;
    phase: UiPhase;
    loop_count: number;
    max_loops: number;
    nodes: PipelineNodeDto[];
    has_looped: boolean;
  };
  review: {
    is_pending: boolean;
    payload: ReviewPayloadDto | null;
    last_decision: {
      approved: boolean;
      rejected: boolean;
      edited_draft: string | null;
      additional_queries: string[];
      notes: string;
      rejection_reason: string;
    } | null;
  };
  draft: DraftViewDto;
  evaluation: EvaluationViewDto;
  log: { entries: LogEntryDto[] };
  raw_state_meta: {
    status: string;
    thread_id: string | null;
    artifact_path: string | null;
    error: string | null;
  };
}

export interface RunSnapshotDto {
  run_id: string;
  thread_id: string;
  phase: UiPhase;
  current_node: PipelineNodeDto['id'] | null;
  status: string;
  loop_count: number;
  max_loops: number;
  updated_at: string;
  review_required: boolean;
  artifact_path: string | null;
  error: string | null;
}

export interface SseEventDto {
  event_id: string;
  run_id: string;
  ts: string;
  type:
    | 'run.created'
    | 'run.phase_changed'
    | 'node.started'
    | 'node.completed'
    | 'review.required'
    | 'review.resolved'
    | 'run.completed'
    | 'run.failed'
    | 'heartbeat';
  snapshot_version: number;
  data: {
    node?: PipelineNodeDto['id'];
    snapshot?: RunSnapshotDto;
    review?: ReviewPayloadDto;
  };
}
