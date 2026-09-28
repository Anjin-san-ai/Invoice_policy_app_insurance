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
import { useEffect, useMemo, useRef, useState } from 'react';
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

/** How long an invocation notification stays up, and the gap between consecutive dismissals. */
const TOAST_MS = 3000;
const TOAST_STAGGER_MS = 110;

/**
 * One live invocation notification. The key is stamped so repeat clicks re-trigger the animation,
 * and `step` names the phase it was invoked from so the notification stands on its own.
 */
type ToastEntry = { key: string; agent: WorkflowAgent; step: string };

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
  refreshKey = 0,
}: {
  claimId: string;
  /** Work order id selected in the supplier panel; its lane is highlighted and the rest dimmed. */
  focusSupplier?: string | null;
  /**
   * Incremented by the parent whenever a supplier action changes the claim. This component owns a
   * second endpoint, so without the signal the graph would keep showing pre-action state.
   */
  refreshKey?: number;
}) {
  const { data, error, loading, reload } = useApi<ClaimAgentWorkflows>(
    `/api/claims/${claimId}/agent-workflows`,
  );
  const [selectedId, setSelectedId] = useState<string>('triage');
  /** The agent whose full suggestion is pinned open under the pill grid; null when none is. */
  const [openAgent, setOpenAgent] = useState<string | null>(null);
  /** Transient "this agent was invoked" notifications, raised by clicking a step. */
  const [toasts, setToasts] = useState<ToastEntry[]>([]);
  const timers = useRef<number[]>([]);

  // A supplier action moved the claim on, so pull the graph's own data again. Skipped on mount,
  // where `useApi` has already fetched, and it revalidates in place so the graph does not blank.
  useEffect(() => {
    if (refreshKey === 0) return;
    reload();
  }, [refreshKey, reload]);

  // Clear any in-flight dismissal timers, so a fast unmount cannot set state on a dead component.
  useEffect(
    () => () => {
      timers.current.forEach((timer) => window.clearTimeout(timer));
    },
    [],
  );

  /**
   * Announce the agents a step invoked. Each notification appears in a stack, staggered so they
   * read in order, and every one dismisses itself after three seconds.
   */
  function announce(agents: WorkflowAgent[], step: string) {
    // Agents that have actually run lead. A step nothing has reached yet still announces its
    // waiting agents, so clicking any node always produces a visible response.
    const ran = agents.filter((agent) => agent.state !== 'pending');
    const invoked = (ran.length > 0 ? ran : agents).slice(0, 4);
    if (invoked.length === 0) return;
    const stamp = Date.now();
    const entries: ToastEntry[] = invoked.map((agent, index) => ({
      key: `${agent.name}-${stamp}-${index}`,
      agent,
      // Strip the "1 · " ordinal, as the graph nodes do.
      step: step.replace(/^\d+\s*·\s*/, ''),
    }));
    setToasts(entries);
    entries.forEach((entry, index) => {
      const timer = window.setTimeout(() => {
        setToasts((current) => current.filter((item) => item.key !== entry.key));
      }, TOAST_MS + index * TOAST_STAGGER_MS);
      timers.current.push(timer);
    });
  }

  /** Selecting a step pins it, resets any open agent, and announces what that step invoked. */
  function selectStep(node: GraphNode) {
    setSelectedId(node.id);
    setOpenAgent(null);
    announce(node.stage.agents, node.stage.title);
  }

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
  // Width follows the longest lane, so merging two phases into one narrows the graph rather than
  // leaving an empty column where the old fourth node used to sit.
  const laneLength = Math.max(1, ...data.suppliers.map((lane) => lane.stages.length));
  const width = LANE_X0 + (laneLength - 1) * LANE_DX + NODE_W + 40;
  const height = LANE_Y0 + (laneCount - 1) * LANE_DY + NODE_H + 40;
  const selected = nodes.find((node) => node.id === selectedId) ?? nodes[0];
  const openAgentDetail = selected?.stage.agents.find((agent) => agent.name === openAgent) ?? null;

  const allStages = [data.triage, ...data.suppliers.flatMap((lane) => lane.stages)];
  const doneCount = allStages.reduce((sum, s) => sum + s.agents.filter((a) => a.state === 'done').length, 0);
  const runningCount = allStages.reduce((sum, s) => sum + s.agents.filter((a) => a.state === 'active').length, 0);

  return (
    <article className="card section agentFlowCard">
      {/* Invocation notifications. Raised by clicking a step, self-dismissing after three seconds. */}
      <div aria-live="polite" className="agentToastStack">
        <AnimatePresence initial={false}>
          {toasts.map((toast, index) => {
            const meta = KIND_META[toast.agent.kind];
            return (
              <motion.div
                animate={{ opacity: 1, x: 0, scale: 1 }}
                className={`agentToast ${toast.agent.state}`}
                exit={{ opacity: 0, x: 24, scale: 0.96 }}
                initial={{ opacity: 0, x: 28, scale: 0.96 }}
                key={toast.key}
                transition={{ duration: 0.26, ease: 'easeOut', delay: index * 0.07 }}
              >
                <span className="agentToastIcon">
                  {toast.agent.state === 'done' ? (
                    <Check size={12} strokeWidth={3.2} />
                  ) : (
                    <meta.Icon size={12} />
                  )}
                </span>
                <span className="agentToastText">
                  <b>{toast.agent.name}</b>
                  <small>
                    {meta.label} · {toast.step} ·{' '}
                    {toast.agent.state === 'done' ? 'completed' : 'running now'}
                  </small>
                  {/* What the agent is for, then what it actually did on this claim. */}
                  <i className="agentToastRole">{toast.agent.role}</i>
                  <em>
                    <b>{toast.agent.state === 'done' ? 'Did:' : 'Doing:'}</b> {toast.agent.detail}
                  </em>
                </span>
              </motion.div>
            );
          })}
        </AnimatePresence>
      </div>

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
                onClick={(event) => {
                  event.stopPropagation();
                  selectStep(node);
                }}
                role="button"
                tabIndex={0}
                onKeyDown={(event) => {
                  if (event.key === 'Enter' || event.key === ' ') {
                    event.preventDefault();
                    selectStep(node);
                  }
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

      {/* Detail for the selected node. Deliberately not wrapped in AnimatePresence: `mode="wait"`
          held the outgoing panel's slot empty while it faded, collapsing the card's height and
          then restoring it on every click, which reads as the page reloading. Keying the panel on
          the selection instead swaps it in place, so only the contents cross-fade. */}
      {selected ? (
          <motion.div
            animate={{ opacity: 1, y: 0 }}
            className="graphDetail"
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

            <p className="cardNote">
              <MousePointerClick size={13} style={{ verticalAlign: '-2px' }} /> Click an agent to read
              what it suggested.
            </p>

            <div className="phaseAgents">
              {selected.stage.agents.map((agent, index) => {
                const meta = KIND_META[agent.kind];
                const isOpen = openAgent === agent.name;
                // Pills named in a live notification pulse, so the toast and the grid agree.
                const announced = toasts.some((toast) => toast.agent.name === agent.name);
                return (
                  <motion.button
                    animate={{ opacity: 1, y: 0 }}
                    aria-expanded={isOpen}
                    className={`agentPill ${agent.kind} ${agent.state}${isOpen ? ' open' : ''}${announced ? ' announced' : ''}`}
                    initial={{ opacity: 0, y: 6 }}
                    key={agent.name}
                    // Stopped and default-prevented so the click cannot reach an ancestor handler
                    // or be treated as a submit, either of which would reload the page.
                    onClick={(event) => {
                      event.preventDefault();
                      event.stopPropagation();
                      setOpenAgent(isOpen ? null : agent.name);
                    }}
                    transition={{ delay: Math.min(index * 0.03, 0.25) }}
                    type="button"
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
                    <ChevronRight className="agentPillChevron" size={12} />
                  </motion.button>
                );
              })}
            </div>

            {/* The pinned agent's full suggestion: its role, its state and what it recommended. */}
            <AnimatePresence initial={false}>
              {openAgentDetail ? (
                <motion.div
                  animate={{ opacity: 1, height: 'auto' }}
                  className="agentSuggestion"
                  exit={{ opacity: 0, height: 0 }}
                  initial={{ opacity: 0, height: 0 }}
                  key={openAgentDetail.name}
                  transition={{ duration: 0.2, ease: 'easeOut' }}
                >
                  <header>
                    <b>{openAgentDetail.name}</b>
                    <span className={`agentColumnState ${openAgentDetail.state}`}>
                      {openAgentDetail.state === 'done'
                        ? 'complete'
                        : openAgentDetail.state === 'active'
                          ? 'running'
                          : 'waiting'}
                    </span>
                    <span className={`agentDot ${openAgentDetail.kind}`} />
                    <small>{KIND_META[openAgentDetail.kind].label}</small>
                  </header>
                  <p className="agentSuggestionRole">{openAgentDetail.role}</p>
                  <p className="agentSuggestionBody">
                    <b>Suggested:</b> {openAgentDetail.detail}
                  </p>
                </motion.div>
              ) : null}
            </AnimatePresence>
          </motion.div>
      ) : null}

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
