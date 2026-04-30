import { useEffect, useRef, useState } from 'react';
import { createRun, getRunDetail, listRuns, submitReview } from './api/client';
import { subscribeToRun } from './api/stream';
import type { ReviewDecisionInput, RunDetailDto, RunSummaryDto, UiPhase } from './api/types';
import { DraftSourcesTab } from './components/DraftSourcesTab';
import { EvaluationTab } from './components/EvaluationTab';
import { LogTab } from './components/LogTab';
import { NewRunPanel } from './components/NewRunPanel';
import { PipelineGraph } from './components/PipelineGraph';
import { ReviewPanel } from './components/ReviewPanel';
import { Sidebar } from './components/Sidebar';
import { TopBar } from './components/TopBar';
import { Label } from './components/primitives';

type Tab = 'review' | 'draft' | 'evals' | 'log';

const TABS: Array<{ id: Tab; label: string }> = [
  { id: 'review', label: 'Human Review' },
  { id: 'draft', label: 'Draft & Sources' },
  { id: 'evals', label: 'Evaluation' },
  { id: 'log', label: 'Log' },
];

function isStreamable(phase: UiPhase, isActiveSession: boolean): boolean {
  return isActiveSession && !['done', 'rejected', 'failed'].includes(phase);
}

export default function App() {
  const [runs, setRuns] = useState<RunSummaryDto[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [detail, setDetail] = useState<RunDetailDto | null>(null);
  const [tab, setTab] = useState<Tab>('review');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [submittingReview, setSubmittingReview] = useState(false);
  const [newRunOpen, setNewRunOpen] = useState(false);
  const streamCleanupRef = useRef<(() => void) | null>(null);

  async function refreshRuns(preferredRunId?: string | null) {
    const rows = await listRuns();
    setRuns(rows);
    const activeRun = rows.find((run) => isStreamable(run.phase, run.is_active_session));
    const nextRunId = preferredRunId ?? selectedRunId ?? activeRun?.id ?? rows[0]?.id ?? null;
    if (nextRunId && nextRunId !== selectedRunId) {
      setSelectedRunId(nextRunId);
    } else if (!nextRunId) {
      setSelectedRunId(null);
      setDetail(null);
    }
    return rows;
  }

  async function loadRun(runId: string) {
    const nextDetail = await getRunDetail(runId);
    setDetail(nextDetail);
    setError(null);
    return nextDetail;
  }

  async function refreshCurrent() {
    if (!selectedRunId) {
      await refreshRuns();
      return;
    }
    await refreshRuns(selectedRunId);
    await loadRun(selectedRunId);
  }

  useEffect(() => {
    void (async () => {
      try {
        const rows = await refreshRuns();
        const initialRun = rows.find((run) => isStreamable(run.phase, run.is_active_session)) ?? rows[0];
        if (initialRun) {
          setSelectedRunId(initialRun.id);
          await loadRun(initialRun.id);
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load runs');
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  useEffect(() => {
    if (!selectedRunId) return;
    void (async () => {
      try {
        await loadRun(selectedRunId);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load run detail');
      }
    })();
  }, [selectedRunId]);

  useEffect(() => {
    streamCleanupRef.current?.();
    streamCleanupRef.current = null;

    if (!detail || !isStreamable(detail.summary.phase, detail.summary.is_active_session)) return;

    streamCleanupRef.current = subscribeToRun(
      detail.summary.id,
      async () => {
        try {
          await refreshRuns(detail.summary.id);
          await loadRun(detail.summary.id);
        } catch (err) {
          setError(err instanceof Error ? err.message : 'Failed to refresh stream state');
        }
      },
      () => {
        setError('Live stream disconnected. The run may have finished or the server may have restarted.');
      },
    );

    return () => {
      streamCleanupRef.current?.();
      streamCleanupRef.current = null;
    };
  }, [detail?.summary.id, detail?.summary.phase, detail?.summary.is_active_session]);

  async function handleCreateRun(input: {
    topic: string;
    mode: 'dev' | 'live' | 'eval';
    report_format: 'deep_dive' | 'executive_brief';
    max_loops: number;
  }) {
    try {
      setCreating(true);
      const created = await createRun(input);
      setNewRunOpen(false);
      setSelectedRunId(created.run_id);
      await refreshRuns(created.run_id);
      await loadRun(created.run_id);
      setTab('review');
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create run');
    } finally {
      setCreating(false);
    }
  }

  async function handleReview(decision: ReviewDecisionInput) {
    if (!detail) return;
    try {
      setSubmittingReview(true);
      await submitReview(detail.summary.id, decision);
      await refreshRuns(detail.summary.id);
      await loadRun(detail.summary.id);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to submit review');
    } finally {
      setSubmittingReview(false);
    }
  }

  return (
    <div style={{ position: 'relative', zIndex: 1, maxWidth: 1440, margin: '0 auto', padding: '26px 28px 60px' }}>
      <TopBar detail={detail} onRefresh={() => void refreshCurrent()} onNewRun={() => setNewRunOpen(true)} />
      <div style={{ height: 18 }} />

      {error && (
        <div style={{ marginBottom: 18, padding: '12px 14px', border: '1px solid var(--red)', background: 'var(--red-soft)', color: 'var(--red)' }}>
          {error}
        </div>
      )}

      {detail ? (
        <>
          <PipelineGraph
            nodes={detail.pipeline.nodes}
            currentNode={detail.pipeline.current_node}
            phase={detail.pipeline.phase}
            hasLooped={detail.pipeline.has_looped}
            threadId={detail.raw_state_meta.thread_id}
            loopCount={detail.pipeline.loop_count}
            maxLoops={detail.pipeline.max_loops}
          />
          <div style={{ height: 22 }} />

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 320px', gap: 22, alignItems: 'flex-start' }}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 22 }}>
              <TabBar tab={tab} setTab={setTab} phase={detail.summary.phase} />
              {tab === 'review' && <ReviewPanel detail={detail} submitting={submittingReview} onDecision={handleReview} />}
              {tab === 'draft' && <DraftSourcesTab detail={detail} />}
              {tab === 'evals' && <EvaluationTab detail={detail} />}
              {tab === 'log' && <LogTab detail={detail} />}
            </div>
            <Sidebar runs={runs} activeRunId={selectedRunId} onPickRun={(run) => setSelectedRunId(run.id)} />
          </div>
        </>
      ) : (
        <EmptyState loading={loading} onNewRun={() => setNewRunOpen(true)} />
      )}

      <Footer />
      <NewRunPanel open={newRunOpen} creating={creating} onClose={() => setNewRunOpen(false)} onCreate={handleCreateRun} />
    </div>
  );
}

function TabBar({ tab, setTab, phase }: { tab: Tab; setTab: (tab: Tab) => void; phase: UiPhase }) {
  return (
    <div style={{ display: 'flex', gap: 2, alignItems: 'flex-end', borderBottom: '1px solid var(--hair)' }}>
      {TABS.map((item) => {
        const active = tab === item.id;
        const showDot = item.id === 'review' && phase === 'paused_interrupt';
        return (
          <button
            key={item.id}
            onClick={() => setTab(item.id)}
            style={{
              padding: '10px 16px',
              fontSize: 13,
              color: active ? 'var(--ink)' : 'var(--ink-3)',
              fontWeight: active ? 600 : 450,
              background: active ? 'var(--card)' : 'transparent',
              border: active ? '1px solid var(--hair)' : '1px solid transparent',
              borderBottom: active ? '1px solid var(--card)' : '1px solid transparent',
              marginBottom: -1,
              borderRadius: '2px 2px 0 0',
              display: 'flex',
              alignItems: 'center',
              gap: 8,
            }}
          >
            {item.label}
            {showDot && <span style={{ color: 'var(--red)', fontSize: 18, lineHeight: 0 }}>•</span>}
          </button>
        );
      })}
    </div>
  );
}

function EmptyState({ loading, onNewRun }: { loading: boolean; onNewRun: () => void }) {
  return (
    <div style={{ background: 'var(--card)', border: '1px solid var(--hair)', borderRadius: 2, padding: '32px 24px' }}>
      <Label style={{ marginBottom: 10 }}>Research Console</Label>
      <div className="serif" style={{ fontSize: 22, color: 'var(--ink-3)' }}>
        {loading ? 'Loading runs…' : 'No run selected'}
      </div>
      {!loading && (
        <button
          onClick={onNewRun}
          className="mono"
          style={{ marginTop: 12, padding: '8px 12px', background: 'var(--ink)', color: 'var(--paper)', borderRadius: 2, fontSize: 11, letterSpacing: '0.08em' }}
        >
          START NEW RUN
        </button>
      )}
    </div>
  );
}

function Footer() {
  return (
    <footer
      style={{
        marginTop: 40,
        paddingTop: 20,
        borderTop: '1px solid var(--hair)',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        gap: 12,
        flexWrap: 'wrap',
      }}
    >
      <div className="mono" style={{ fontSize: 10.5, color: 'var(--ink-4)', letterSpacing: '0.12em' }}>
        RESEARCH CONSOLE · LANGGRAPH + FASTAPI + SSE
      </div>
      <div className="mono" style={{ fontSize: 10.5, color: 'var(--ink-4)', letterSpacing: '0.12em', display: 'flex', gap: 18, flexWrap: 'wrap' }}>
        <span>review actions from browser</span>
        <span>live reattach within process</span>
        <span>restart loses active sessions</span>
      </div>
    </footer>
  );
}
