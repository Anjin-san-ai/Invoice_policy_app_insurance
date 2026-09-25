import { AnimatePresence, motion } from 'framer-motion';
import {
  Bot,
  Check,
  ChevronRight,
  Cog,
  FileText,
  Loader2,
  MousePointerClick,
  Truck,
  Zap,
} from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { useApi } from '../api/useApi';
import { navigate } from '../router';
import { ClaimAgentWorkflows, ClaimWorkflow, WorkflowAgent, gbp } from '../types';
import { Empty, Loading } from './Common';

/** An LLM agent, deterministic coded tool and external tool read differently, so they look different. */
const KIND_META: Record<WorkflowAgent['kind'], { label: string; Icon: typeof Bot }> = {
  llm: { label: 'LLM agent', Icon: Bot },
  coded: { label: 'Coded tool', Icon: Cog },
  tool: { label: 'Integration', Icon: Zap },
};

/** Graph geometry. Laid out left to right: triage fans out into one lane per supplier. */
const ROOT_X = 96;
const LANE_X0 = 268;
const LANE_DX = 176;
const LANE_Y0 = 78;
const LANE_DY = 104;
const NODE_W = 132;
const NODE_H = 56;

type GraphNode = {
  id: string;
  x: number;
  y: number;
  label: string;
  sub: string;
  state: ClaimWorkflow['state'];
  stage: ClaimWorkflow;
  /** Present on supplier phase nodes; absent on the claim-level triage root. */
  lane?: { supplierName: string; serviceType: string; workOrderId: string; invoiceId: string | null; value: number };
};

/**
 * The agent network for one claim, as a graph.
 *
 * Triage is the root; each instructed supplier is a lane fanning out from it, and each lane runs
 * assignment → work → invoice → settlement. Node colour is that phase's real state and the badge
 * is how many of its agents have finished, so the shape of the graph alone tells you which
 * supplier is holding the claim up. Clicking a node opens the agents behind it.
 *
 * There is no run button: nothing here is simulated. Every state is derived from the claim, its
 * work orders and its invoices, so a node lights up when the work actually reaches it.
 */
export function ClaimAgentFlow({
  claimId,
  focusSupplier = null,
}: {
  claimId: string;
  /** Work order id selected in the supplier panel; its lane is highlighted and the rest dimmed. */
  focusSupplier?: string | null;
}) {
  const { data, error, loading } = useApi<ClaimAgentWorkflows>(`/api/claims/${claimId}/agent-workflows`);
  const [selectedId, setSelectedId] = useState<string>('triage');

  // Selecting a supplier jumps the detail panel to whatever that lane is currently doing.
  useEffect(() => {
    if (!focusSupplier || !data) return;
    const lane = data.suppliers.find((item) => item.work_order_id === focusSupplier);
    if (!lane) return;
    const live = lane.stages.find((stage) => stage.state === 'active') ?? lane.stages[0];
    setSelectedId(`${focusSupplier}-${live.id}`);
  }, [focusSupplier, data]);

  const nodes = useMemo<GraphNode[]>(() => {
    if (!data) return [];
    const laneCount = Math.max(1, data.suppliers.length);
    const built: GraphNode[] = [
      {
        id: 'triage',
        x: ROOT_X,
        y: LANE_Y0 + ((laneCount - 1) * LANE_DY) / 2,
        label: 'Claim triage',
        sub: 'Intake, cover, severity',
        state: data.triage.state,
        stage: data.triage,
      },
    ];
    data.suppliers.forEach((lane, laneIndex) => {
      lane.stages.forEach((stage, stageIndex) => {
        built.push({
          id: `${lane.work_order_id}-${stage.id}`,
          x: LANE_X0 + stageIndex * LANE_DX,
          y: LANE_Y0 + laneIndex * LANE_DY,
          // Strip the "1 · " ordinal: position in the graph already says which phase this is.
          label: stage.title.replace(/^\d+\s*·\s*/, ''),
          sub: `${stage.agents.filter((agent) => agent.state === 'done').length}/${stage.agents.length} agents`,
          state: stage.state,
          stage,
          lane: {
            supplierName: lane.supplier_name,
            serviceType: lane.service_type,
            workOrderId: lane.work_order_id,
            invoiceId: lane.invoice_id,
            value: lane.authorised_value_gbp,
          },
        });
      });
    });
    return built;
  }, [data]);

  if (loading) return <Loading rows={3} />;
  if (error) return <Empty>Could not load the agent workflows: {error}</Empty>;
  if (!data) return <Empty>No agent workflows for this claim.</Empty>;

  const laneCount = Math.max(1, data.suppliers.length);
  const width = LANE_X0 + 3 * LANE_DX + NODE_W + 40;
  const height = LANE_Y0 + (laneCount - 1) * LANE_DY + NODE_H + 40;
  const selected = nodes.find((node) => node.id === selectedId) ?? nodes[0];

  const allStages = [data.triage, ...data.suppliers.flatMap((lane) => lane.stages)];
  const doneCount = allStages.reduce((sum, s) => sum + s.agents.filter((a) => a.state === 'done').length, 0);
  const runningCount = allStages.reduce((sum, s) => sum + s.agents.filter((a) => a.state === 'active').length, 0);

  return (
    <article className="card section">
      <div className="bentoCardHead">
        <h2>Agent network on this claim</h2>
        <div className="btnRow">
          <span className="chip within">
            <Check size={11} /> {doneCount} done
          </span>
          {runningCount > 0 ? (
            <span className="chip warn">
              <Loader2 size={11} /> {runningCount} running
            </span>
          ) : null}
        </div>
      </div>
      <p className="cardNote">
        <MousePointerClick size={13} style={{ verticalAlign: '-2px' }} /> Click any node to see which
        agents have finished and which are running. Triage runs once; each supplier then has its own
        lane, so the shape shows who is holding the claim up.
      </p>

      <div className="graphScroll">
        <svg
          className="agentGraph"
          height={height}
          role="img"
          viewBox={`0 0 ${width} ${height}`}
          width="100%"
        >
          <title>Agent network for this claim</title>
          <defs>
            <marker id="agEdge" markerHeight="6" markerWidth="7" orient="auto" refX="6" refY="3">
              <path d="M0 0 L7 3 L0 6 Z" fill="var(--border)" />
            </marker>
            <marker id="agEdgeDone" markerHeight="6" markerWidth="7" orient="auto" refX="6" refY="3">
              <path d="M0 0 L7 3 L0 6 Z" fill="var(--success)" />
            </marker>
          </defs>

          {/* Edges: triage fans out to each lane, then each lane chains left to right. */}
          {data.suppliers.map((lane, laneIndex) => {
            const laneY = LANE_Y0 + laneIndex * LANE_DY + NODE_H / 2;
            const rootY = LANE_Y0 + ((laneCount - 1) * LANE_DY) / 2 + NODE_H / 2;
            const fanDone = data.triage.state === 'done';
            const dimmed = focusSupplier !== null && focusSupplier !== lane.work_order_id;
            return (
              <g className={dimmed ? 'laneDimmed' : undefined} key={lane.work_order_id}>
                <path
                  d={`M${ROOT_X + NODE_W / 2} ${rootY} C${ROOT_X + NODE_W / 2 + 60} ${rootY}, ${LANE_X0 - NODE_W / 2 - 60} ${laneY}, ${LANE_X0 - NODE_W / 2 - 8} ${laneY}`}
                  fill="none"
                  markerEnd={fanDone ? 'url(#agEdgeDone)' : 'url(#agEdge)'}
                  stroke={fanDone ? 'var(--success)' : 'var(--border)'}
                  strokeDasharray={fanDone ? undefined : '5 4'}
                  strokeWidth="2"
                />
                {lane.stages.slice(0, -1).map((stage, stageIndex) => {
                  const from = LANE_X0 + stageIndex * LANE_DX + NODE_W / 2;
                  const to = LANE_X0 + (stageIndex + 1) * LANE_DX - NODE_W / 2 - 8;
                  const done = stage.state === 'done';
                  return (
                    <line
                      key={stage.id}
                      markerEnd={done ? 'url(#agEdgeDone)' : 'url(#agEdge)'}
                      stroke={done ? 'var(--success)' : 'var(--border)'}
                      strokeDasharray={done ? undefined : '5 4'}
                      strokeWidth="2"
                      x1={from}
                      x2={to}
                      y1={laneY}
                      y2={laneY}
                    />
                  );
                })}
                {/* Lane label, so a node is always attributable to a supplier. */}
                <text className="graphLaneLabel" x={LANE_X0 - NODE_W / 2} y={laneY - NODE_H / 2 - 8}>
                  {lane.supplier_name} · {lane.service_type}
                </text>
              </g>
            );
          })}

          {/* Nodes. */}
          {nodes.map((node) => {
            const isSelected = node.id === selected?.id;
            // A focused supplier recolours its own lane and mutes every other node.
            const focused = focusSupplier !== null && node.lane?.workOrderId === focusSupplier;
            const muted = focusSupplier !== null && node.id !== 'triage' && !focused;
            return (
              <g
                className={`graphNode ${node.state}${isSelected ? ' selected' : ''}${focused ? ' focused' : ''}${muted ? ' muted' : ''}`}
                key={node.id}
                onClick={() => setSelectedId(node.id)}
                role="button"
                tabIndex={0}
                onKeyDown={(event) => {
                  if (event.key === 'Enter' || event.key === ' ') setSelectedId(node.id);
                }}
                transform={`translate(${node.x - NODE_W / 2} ${node.y})`}
              >
                {node.state === 'active' ? (
                  <motion.rect
                    animate={{ opacity: [0.5, 0, 0.5] }}
                    height={NODE_H + 10}
                    rx="16"
                    transition={{ duration: 2, repeat: Infinity }}
                    width={NODE_W + 10}
                    x={-5}
                    y={-5}
                  />
                ) : null}
                <rect className="graphNodeBox" height={NODE_H} rx="13" width={NODE_W} />
                <text className="graphNodeTitle" x="12" y="23">
                  {node.label}
                </text>
                <text className="graphNodeSub" x="12" y="41">
                  {node.sub}
                </text>
                {node.state === 'done' ? (
                  <g transform={`translate(${NODE_W - 24} 8)`}>
                    <circle className="graphTick" cx="8" cy="8" r="8" />
                    <path d="M4 8 L7 11 L12 5" fill="none" stroke="var(--text-on-primary)" strokeLinecap="round" strokeWidth="2" />
                  </g>
                ) : null}
              </g>
            );
          })}
        </svg>
      </div>

      {/* Detail for the selected node. */}
      <AnimatePresence mode="wait">
        {selected ? (
          <motion.div
            animate={{ opacity: 1, y: 0 }}
            className="graphDetail"
            exit={{ opacity: 0, y: -6 }}
            initial={{ opacity: 0, y: 8 }}
            key={selected.id}
            transition={{ duration: 0.18 }}
          >
            <header className="graphDetailHead">
              <div>
                <b>{selected.stage.title}</b>
                {selected.lane ? (
                  <small>
                    <Truck size={11} /> {selected.lane.supplierName} · {selected.lane.serviceType} ·{' '}
                    {selected.lane.workOrderId} · {gbp(selected.lane.value)} authorised
                  </small>
                ) : (
                  <small>Runs once per claim, before any supplier is instructed</small>
                )}
                <em className="graphDetailTrigger">{selected.stage.trigger}</em>
              </div>
              <div className="btnRow">
                <span className={`agentColumnState ${selected.state}`}>
                  {selected.state === 'done' ? 'complete' : selected.state === 'active' ? 'running' : 'waiting'}
                </span>
                {selected.lane?.invoiceId ? (
                  <button
                    className="btn secondary small"
                    onClick={() => navigate(`/invoice/${selected.lane?.invoiceId}`)}
                    type="button"
                  >
                    <FileText size={12} /> Invoice <ChevronRight size={12} />
                  </button>
                ) : null}
              </div>
            </header>

            <div className="phaseAgents">
              {selected.stage.agents.map((agent, index) => {
                const meta = KIND_META[agent.kind];
                return (
                  <motion.div
                    animate={{ opacity: 1, y: 0 }}
                    className={`agentPill ${agent.kind} ${agent.state}`}
                    initial={{ opacity: 0, y: 6 }}
                    key={agent.name}
                    transition={{ delay: Math.min(index * 0.03, 0.25) }}
                  >
                    <span className="agentPillIcon">
                      {agent.state === 'done' ? (
                        <Check size={11} strokeWidth={3.2} />
                      ) : agent.state === 'active' ? (
                        <motion.span
                          animate={{ rotate: 360 }}
                          style={{ display: 'flex' }}
                          transition={{ duration: 1.4, repeat: Infinity, ease: 'linear' }}
                        >
                          <Loader2 size={11} />
                        </motion.span>
                      ) : (
                        <meta.Icon size={11} />
                      )}
                    </span>
                    <span className="agentPillText">
                      <b>{agent.name}</b>
                      <small>{meta.label}</small>
                      <em>{agent.detail}</em>
                    </span>
                  </motion.div>
                );
              })}
            </div>
          </motion.div>
        ) : null}
      </AnimatePresence>

      <div className="agentFlowLegend">
        <span>
          <i className="agentDot doneDot" /> phase complete
        </span>
        <span>
          <i className="agentDot activeDot" /> running now
        </span>
        <span>
          <i className="agentDot" style={{ background: 'var(--border)' }} /> waiting
        </span>
        {Object.entries(KIND_META).map(([kind, meta]) => (
          <span key={kind}>
            <i className={`agentDot ${kind}`} /> {meta.label}
          </span>
        ))}
      </div>
    </article>
  );
}
