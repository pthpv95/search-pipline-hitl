import { Corner, Dot, Label, Pill, Rule } from './primitives';
import type { PipelineNodeDto, UiPhase } from '../api/types';

type NodeId = PipelineNodeDto['id'];
type NodeState = 'pending' | 'active' | 'interrupt' | 'done';

const POSITIONS: Record<NodeId, { x: number; y: number }> = {
  search_agent: { x: 130, y: 110 },
  synthesis_agent: { x: 350, y: 110 },
  human_review: { x: 570, y: 110 },
  report_agent: { x: 790, y: 110 },
};

const ORDER: NodeId[] = ['search_agent', 'synthesis_agent', 'human_review', 'report_agent'];

function currentNodeForPhase(currentNode: NodeId | null, phase: UiPhase): NodeId {
  if (currentNode) return currentNode;
  if (phase === 'searching' || phase === 'initializing' || phase === 'resuming') return 'search_agent';
  if (phase === 'synthesizing') return 'synthesis_agent';
  if (phase === 'paused_interrupt' || phase === 'rejected') return 'human_review';
  return 'report_agent';
}

export function PipelineGraph({
  nodes,
  currentNode,
  phase,
  hasLooped,
  threadId,
  loopCount,
  maxLoops,
}: {
  nodes: PipelineNodeDto[];
  currentNode: NodeId | null;
  phase: UiPhase;
  hasLooped: boolean;
  threadId: string | null;
  loopCount: number;
  maxLoops: number;
}) {
  const W = 900;
  const H = 220;
  const safeCurrentNode = currentNodeForPhase(currentNode, phase);

  const edges: Array<{ from: NodeId; to: NodeId }> = [
    { from: 'search_agent', to: 'synthesis_agent' },
    { from: 'synthesis_agent', to: 'human_review' },
    { from: 'human_review', to: 'report_agent' },
  ];

  const edgeByCurrent: Record<NodeId, number> = {
    search_agent: 0,
    synthesis_agent: 1,
    human_review: phase === 'paused_interrupt' ? 1 : 2,
    report_agent: 2,
  };
  const activeEdgeIdx = edgeByCurrent[safeCurrentNode];

  const nodeState = (id: NodeId): NodeState => {
    const curI = ORDER.indexOf(safeCurrentNode);
    const myI = ORDER.indexOf(id);
    if (phase === 'done' && id === 'report_agent') return 'done';
    if (myI < curI) return 'done';
    if (myI === curI) return phase === 'paused_interrupt' && id === 'human_review' ? 'interrupt' : 'active';
    return 'pending';
  };

  return (
    <div style={{ position: 'relative', width: '100%', background: 'var(--card)', border: '1px solid var(--hair)', borderRadius: 2 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '14px 20px 10px', gap: 12, flexWrap: 'wrap' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
          <Corner style={{ color: 'var(--ink-3)' }} />
          <Label>LangGraph Pipeline</Label>
          <span className="mono" style={{ fontSize: 11, color: 'var(--ink-4)' }}>
            thread_id: {threadId || '—'} · checkpointer: MemorySaver
          </span>
        </div>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <Pill tone={phase === 'paused_interrupt' || phase === 'rejected' || phase === 'failed' ? 'red' : phase === 'done' ? 'green' : 'ink'}>
            <Dot color="currentColor" size={5} /> {phase.replace('_', ' ').toUpperCase()}
          </Pill>
          <Pill>loop {loopCount}/{maxLoops}</Pill>
        </div>
      </div>

      <Rule />

      <svg viewBox={`0 0 ${W} ${H}`} width="100%" style={{ display: 'block' }}>
        <defs>
          <marker id="arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto">
            <path d="M0 0 L10 5 L0 10 z" fill="var(--ink-2)" />
          </marker>
          <marker id="arrow-red" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto">
            <path d="M0 0 L10 5 L0 10 z" fill="var(--red)" />
          </marker>
          <marker id="arrow-soft" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto">
            <path d="M0 0 L10 5 L0 10 z" fill="var(--ink-4)" />
          </marker>
        </defs>

        <path
          d={`M ${POSITIONS.human_review.x} ${POSITIONS.human_review.y - 28}
              C ${POSITIONS.human_review.x} 20, ${POSITIONS.search_agent.x} 20, ${POSITIONS.search_agent.x} ${POSITIONS.search_agent.y - 28}`}
          fill="none"
          stroke="var(--ink-4)"
          strokeWidth="1"
          strokeDasharray="3 4"
          markerEnd="url(#arrow-soft)"
          opacity={hasLooped ? 1 : 0.2}
        />
        <text
          x={(POSITIONS.search_agent.x + POSITIONS.human_review.x) / 2}
          y="14"
          textAnchor="middle"
          fontFamily="JetBrains Mono"
          fontSize="10"
          fill="var(--ink-4)"
          letterSpacing="0.1em"
          opacity={hasLooped ? 1 : 0.3}
        >
          APPROVE + QUERIES ↺
        </text>

        {edges.map((edge, index) => {
          const from = POSITIONS[edge.from];
          const to = POSITIONS[edge.to];
          const isCurrent = index === activeEdgeIdx && phase !== 'paused_interrupt' && phase !== 'done' && phase !== 'rejected' && phase !== 'failed';
          const color = isCurrent ? 'var(--red)' : 'var(--ink-2)';
          return (
            <g key={index}>
              <line
                x1={from.x + 64}
                y1={from.y}
                x2={to.x - 64}
                y2={to.y}
                stroke={color}
                strokeWidth="1.2"
                markerEnd={isCurrent ? 'url(#arrow-red)' : 'url(#arrow)'}
              />
              {isCurrent && (
                <circle r="3" fill="var(--red)">
                  <animateMotion dur="1.6s" repeatCount="indefinite" path={`M${from.x + 64} ${from.y} L${to.x - 64} ${to.y}`} />
                </circle>
              )}
            </g>
          );
        })}

        <g>
          <line
            x1={POSITIONS.report_agent.x + 64}
            y1={POSITIONS.report_agent.y}
            x2={W - 30}
            y2={POSITIONS.report_agent.y}
            stroke="var(--ink-3)"
            strokeWidth="1"
            strokeDasharray="2 3"
          />
          <text x={W - 20} y={POSITIONS.report_agent.y + 4} fontFamily="JetBrains Mono" fontSize="10" fill="var(--ink-3)" textAnchor="end">
            END
          </text>
        </g>

        <g opacity={phase === 'rejected' || phase === 'failed' ? 1 : 0.3}>
          <path
            d={`M ${POSITIONS.human_review.x} ${POSITIONS.human_review.y + 28}
                C ${POSITIONS.human_review.x} 200, ${POSITIONS.human_review.x + 120} 210, ${POSITIONS.human_review.x + 160} ${H - 10}`}
            fill="none"
            stroke="var(--red)"
            strokeWidth="1"
            strokeDasharray="2 3"
          />
          <text x={POSITIONS.human_review.x + 165} y={H - 4} fontFamily="JetBrains Mono" fontSize="9.5" fill="var(--red)" letterSpacing="0.1em">
            REJECT → END
          </text>
        </g>

        {nodes.map((node) => {
          const position = POSITIONS[node.id];
          return <GraphNode key={node.id} node={node} state={nodeState(node.id)} x={position.x} y={position.y} />;
        })}
      </svg>

      <Rule />

      <div style={{ display: 'flex', padding: '10px 20px', gap: 28, flexWrap: 'wrap' }}>
        {nodes.map((node) => (
          <div key={node.id} style={{ flex: 1, minWidth: 150 }}>
            <Label style={{ fontSize: 9.5 }}>{node.label}</Label>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, marginTop: 2 }}>
              <span className="mono" style={{ fontSize: 12, color: 'var(--ink-2)' }}>
                {node.tokens ? node.tokens.toLocaleString() : '—'}
              </span>
              <span className="mono" style={{ fontSize: 10.5, color: 'var(--ink-4)' }}>
                {node.secs ? `${node.secs.toFixed(2)}s` : ''} {node.cost ? `· $${node.cost.toFixed(4)}` : ''}
              </span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function GraphNode({ node, state, x, y }: { node: PipelineNodeDto; state: NodeState; x: number; y: number }) {
  const isInterrupt = state === 'interrupt';
  const isActive = state === 'active';
  const isDone = state === 'done';

  const fill = isInterrupt ? 'var(--red-soft)' : isActive ? 'var(--paper)' : isDone ? 'var(--paper-2)' : 'var(--card)';
  const stroke = isInterrupt ? 'var(--red)' : isActive ? 'var(--ink)' : isDone ? 'var(--ink-3)' : 'var(--ink-4)';
  const text = isInterrupt ? 'var(--red)' : isDone ? 'var(--ink-3)' : 'var(--ink)';

  return (
    <g transform={`translate(${x - 64}, ${y - 28})`}>
      <rect width="128" height="56" rx="2" fill={fill} stroke={stroke} strokeWidth={isActive || isInterrupt ? 1.4 : 1} />
      {isInterrupt && (
        <rect width="128" height="56" rx="2" fill="none" stroke="var(--red)" strokeWidth="1" strokeDasharray="3 3">
          <animate attributeName="stroke-dashoffset" from="0" to="12" dur="0.9s" repeatCount="indefinite" />
        </rect>
      )}
      {isDone && (
        <path d="M 108 12 l 4 4 l 8 -8" stroke="var(--green)" strokeWidth="1.4" fill="none" strokeLinecap="round" strokeLinejoin="round" />
      )}
      {isActive && (
        <circle cx="116" cy="12" r="3" fill="var(--red)">
          <animate attributeName="opacity" values="1;0.2;1" dur="1.2s" repeatCount="indefinite" />
        </circle>
      )}
      <text x="12" y="22" fontFamily="JetBrains Mono" fontSize="11.5" fill={text} fontWeight="500">
        {node.label}
      </text>
      <text x="12" y="40" fontFamily="Inter" fontSize="10.5" fill={isActive || isInterrupt ? 'var(--ink-3)' : 'var(--ink-4)'}>
        {node.id.replace('_', ' ')}
      </text>
    </g>
  );
}
