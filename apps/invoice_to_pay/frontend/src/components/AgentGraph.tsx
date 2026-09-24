import { motion } from 'framer-motion';
import { Bot, Cpu, Crosshair, Hand, Maximize2, Minus, MousePointer2, Play, Plus, RotateCcw, Square } from 'lucide-react';
import { PointerEvent as ReactPointerEvent, WheelEvent as ReactWheelEvent, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { AgentNode } from '../types';

const NODE_W = 176;
const NODE_H = 58;
const TIER_GAP = 250;
const ROW_GAP = 74;
const PADDING = 34;

/** The order the front man calls its down-chain agents in, used by the run playback. */
const RUN_ORDER = [
  'Invoice_Orchestrator',
  'Intake_And_Classification_Agent',
  'Extraction_Agent',
  'Redaction_Agent',
  'Claim_Matching_Agent',
  'Rate_Card_Validation_Agent',
  'Entitlement_And_Authorisation_Agent',
  'Tolerance_And_Anomaly_Agent',
  'Exception_Router_Agent',
  'Settlement_And_Dispute_Agent',
  'Payment_And_Writeback_Agent',
  'Communications_Agent',
];

type Point = { x: number; y: number };
type Layout = { positions: Record<string, Point>; width: number; height: number };

/** Assign every node a tier by walking down-chain edges out from the front man. */
function computeLayout(nodes: AgentNode[]): Layout {
  const byName = new Map(nodes.map((node) => [node.name, node]));
  const frontMan = nodes.find((node) => node.is_front_man) ?? nodes[0];
  const tiers: string[][] = [];
  const seen = new Set<string>();

  let frontier = frontMan ? [frontMan.name] : [];
  while (frontier.length) {
    const unique = Array.from(new Set(frontier.filter((name) => !seen.has(name) && byName.has(name))));
    if (!unique.length) break;
    unique.forEach((name) => seen.add(name));
    tiers.push(unique);
    frontier = unique.flatMap((name) => byName.get(name)?.down_chain ?? []);
  }
  const orphans = nodes.filter((node) => !seen.has(node.name)).map((node) => node.name);
  if (orphans.length) tiers.push(orphans);

  const tallest = Math.max(...tiers.map((tier) => tier.length), 1);
  const height = tallest * ROW_GAP + PADDING * 2;
  const width = tiers.length * TIER_GAP + PADDING * 2;

  const positions: Record<string, Point> = {};
  tiers.forEach((tier, tierIndex) => {
    const top = (height - tier.length * ROW_GAP) / 2;
    tier.forEach((name, rowIndex) => {
      positions[name] = { x: PADDING + tierIndex * TIER_GAP, y: top + rowIndex * ROW_GAP + (ROW_GAP - NODE_H) / 2 };
    });
  });
  return { positions, width, height };
}

/** Cubic bezier between the right edge of one node and the left edge of another. */
function edgePath(from: Point, to: Point): string {
  const x1 = from.x + NODE_W;
  const y1 = from.y + NODE_H / 2;
  const x2 = to.x;
  const y2 = to.y + NODE_H / 2;
  const bend = Math.max(48, Math.abs(x2 - x1) / 2);
  return `M${x1} ${y1} C${x1 + bend} ${y1}, ${x2 - bend} ${y2}, ${x2} ${y2}`;
}

export function AgentGraph({
  nodes,
  edges,
  onSelect,
  selected,
}: {
  nodes: AgentNode[];
  edges: Array<{ source: string; target: string }>;
  onSelect?: (node: AgentNode | null) => void;
  selected?: string;
}) {
  const layout = useMemo(() => computeLayout(nodes), [nodes]);
  const byName = useMemo(() => new Map(nodes.map((node) => [node.name, node])), [nodes]);

  const [positions, setPositions] = useState<Record<string, Point>>(layout.positions);
  const [view, setView] = useState({ x: 0, y: 0, scale: 1 });
  const [hover, setHover] = useState('');
  const [isolated, setIsolated] = useState('');
  const [running, setRunning] = useState(false);
  const [step, setStep] = useState(-1);
  const [mode, setMode] = useState<'select' | 'pan'>('select');
  const [dragging, setDragging] = useState<string>('');

  const svgRef = useRef<SVGSVGElement | null>(null);
  const panRef = useRef<{ x: number; y: number; viewX: number; viewY: number } | null>(null);
  const nodeDragRef = useRef<{ name: string; offsetX: number; offsetY: number; moved: boolean } | null>(null);
  const timer = useRef<number | undefined>(undefined);

  useEffect(() => {
    setPositions(layout.positions);
  }, [layout]);

  // Run playback: light each agent in call order so the fan-out is legible at a glance.
  useEffect(() => {
    if (!running) return;
    const sequence = RUN_ORDER.filter((name) => byName.has(name));
    timer.current = window.setInterval(() => {
      setStep((current) => {
        if (current + 1 >= sequence.length) {
          window.clearInterval(timer.current);
          setRunning(false);
          return current;
        }
        return current + 1;
      });
    }, 620);
    return () => window.clearInterval(timer.current);
  }, [running, byName]);

  /** Convert a client point into SVG user space, accounting for pan and zoom. */
  const toGraph = useCallback(
    (clientX: number, clientY: number): Point => {
      const rect = svgRef.current?.getBoundingClientRect();
      if (!rect) return { x: 0, y: 0 };
      return { x: (clientX - rect.left - view.x) / view.scale, y: (clientY - rect.top - view.y) / view.scale };
    },
    [view],
  );

  function onWheel(event: ReactWheelEvent<SVGSVGElement>) {
    event.preventDefault();
    const rect = svgRef.current?.getBoundingClientRect();
    if (!rect) return;
    const pointerX = event.clientX - rect.left;
    const pointerY = event.clientY - rect.top;
    const factor = event.deltaY < 0 ? 1.12 : 1 / 1.12;
    setView((current) => {
      const scale = Math.max(0.35, Math.min(2.4, current.scale * factor));
      const ratio = scale / current.scale;
      // Keep the point under the cursor fixed while zooming.
      return { scale, x: pointerX - (pointerX - current.x) * ratio, y: pointerY - (pointerY - current.y) * ratio };
    });
  }

  function onNodePointerDown(event: ReactPointerEvent<SVGGElement>, node: AgentNode) {
    if (mode === 'pan') return;
    event.stopPropagation();
    (event.target as Element).setPointerCapture?.(event.pointerId);
    const point = toGraph(event.clientX, event.clientY);
    const position = positions[node.name] ?? { x: 0, y: 0 };
    nodeDragRef.current = { name: node.name, offsetX: point.x - position.x, offsetY: point.y - position.y, moved: false };
    setDragging(node.name);
  }

  function onBackgroundPointerDown(event: ReactPointerEvent<SVGSVGElement>) {
    panRef.current = { x: event.clientX, y: event.clientY, viewX: view.x, viewY: view.y };
  }

  function onPointerMove(event: ReactPointerEvent<SVGSVGElement>) {
    if (nodeDragRef.current) {
      const point = toGraph(event.clientX, event.clientY);
      const drag = nodeDragRef.current;
      drag.moved = true;
      setPositions((current) => ({ ...current, [drag.name]: { x: point.x - drag.offsetX, y: point.y - drag.offsetY } }));
      return;
    }
    if (panRef.current) {
      const start = panRef.current;
      setView((current) => ({ ...current, x: start.viewX + (event.clientX - start.x), y: start.viewY + (event.clientY - start.y) }));
    }
  }

  function onPointerUp() {
    // A press that never moved is a click, so selection still works while dragging is enabled.
    const drag = nodeDragRef.current;
    if (drag && !drag.moved) {
      const node = byName.get(drag.name);
      if (node) onSelect?.(selected === node.name ? null : node);
    }
    nodeDragRef.current = null;
    panRef.current = null;
    setDragging('');
  }

  function reset() {
    window.clearInterval(timer.current);
    setRunning(false);
    setStep(-1);
    setPositions(layout.positions);
    setView({ x: 0, y: 0, scale: 1 });
    setIsolated('');
  }

  const sequence = RUN_ORDER.filter((name) => byName.has(name));
  const activeName = running || step >= 0 ? sequence[step] : '';
  const doneNames = new Set(sequence.slice(0, Math.max(0, step)));

  // Isolation pins a subtree; hover gives a transient version of the same thing.
  const focus = isolated || hover || selected || '';
  const focusEdges = new Set(
    edges.filter((edge) => edge.source === focus || edge.target === focus).map((edge) => `${edge.source}->${edge.target}`),
  );
  const subtree = useMemo(() => {
    if (!isolated) return null;
    const keep = new Set<string>([isolated]);
    let frontier = byName.get(isolated)?.down_chain ?? [];
    while (frontier.length) {
      const next: string[] = [];
      for (const name of frontier) {
        if (keep.has(name)) continue;
        keep.add(name);
        next.push(...(byName.get(name)?.down_chain ?? []));
      }
      frontier = next;
    }
    return keep;
  }, [isolated, byName]);

  return (
    <div className="graphShell">
      <div className="graphBar">
        <div className="btnRow">
          {running ? (
            <button className="btn secondary" onClick={reset} type="button"><Square size={13} /> Stop</button>
          ) : (
            <button className="btn" onClick={() => { setStep(-1); setRunning(true); }} type="button"><Play size={13} /> Play a run</button>
          )}
          <button className={`btn ${mode === 'select' ? '' : 'secondary'}`} onClick={() => setMode('select')} title="Drag nodes to rearrange" type="button">
            <MousePointer2 size={13} /> Move nodes
          </button>
          <button className={`btn ${mode === 'pan' ? '' : 'secondary'}`} onClick={() => setMode('pan')} title="Drag the canvas to pan" type="button">
            <Hand size={13} /> Pan
          </button>
          <button className="btn secondary" onClick={reset} type="button"><RotateCcw size={13} /> Reset</button>
        </div>
        <div className="btnRow">
          <button aria-label="Zoom out" className="btn secondary iconBtn" onClick={() => setView((v) => ({ ...v, scale: Math.max(0.35, v.scale / 1.15) }))} type="button"><Minus size={14} /></button>
          <span className="zoomLabel">{Math.round(view.scale * 100)}%</span>
          <button aria-label="Zoom in" className="btn secondary iconBtn" onClick={() => setView((v) => ({ ...v, scale: Math.min(2.4, v.scale * 1.15) }))} type="button"><Plus size={14} /></button>
          <button aria-label="Fit" className="btn secondary iconBtn" onClick={() => setView({ x: 0, y: 0, scale: 1 })} type="button"><Maximize2 size={14} /></button>
        </div>
      </div>

      <div className="graphLegend">
        <span><i className="dot frontman" /> front man</span>
        <span><i className="dot agent" /> LLM agent</span>
        <span><i className="dot coded" /> coded tool</span>
        {isolated ? (
          <button className="filterChip on" onClick={() => setIsolated('')} type="button">
            <Crosshair size={12} /> isolated: {isolated.replace(/_/g, ' ')} · clear
          </button>
        ) : (
          <span style={{ color: 'var(--text-muted)' }}>double-click a node to isolate its branch</span>
        )}
      </div>

      {activeName ? (
        <p className="graphStatus">
          <span className="pulse" /> Step {step + 1} of {sequence.length}: <strong>{activeName.replace(/_/g, ' ')}</strong>
        </p>
      ) : null}

      <div className="graphViewport">
        <svg
          height={520}
          onPointerDown={onBackgroundPointerDown}
          onPointerLeave={onPointerUp}
          onPointerMove={onPointerMove}
          onPointerUp={onPointerUp}
          onWheel={onWheel}
          ref={svgRef}
          role="img"
          style={{ cursor: dragging ? 'grabbing' : mode === 'pan' ? 'grab' : 'default', touchAction: 'none', display: 'block', width: '100%' }}
        >
          <title>Neuro SAN agent network topology. Drag to rearrange, scroll to zoom.</title>
          <defs>
            <marker id="arrow" markerHeight="6" markerWidth="7" orient="auto" refX="6" refY="3">
              <path d="M0 0 L7 3 L0 6 z" fill="var(--border)" />
            </marker>
            <marker id="arrowLive" markerHeight="6" markerWidth="7" orient="auto" refX="6" refY="3">
              <path d="M0 0 L7 3 L0 6 z" fill="var(--primary)" />
            </marker>
          </defs>

          <g transform={`translate(${view.x} ${view.y}) scale(${view.scale})`}>
            {edges.map((edge) => {
              const from = positions[edge.source];
              const to = positions[edge.target];
              if (!from || !to) return null;
              const key = `${edge.source}->${edge.target}`;
              const lit = focus ? focusEdges.has(key) : false;
              const live = doneNames.has(edge.source) || activeName === edge.source;
              const outside = subtree ? !(subtree.has(edge.source) && subtree.has(edge.target)) : false;
              const path = edgePath(from, to);
              return (
                <g key={key}>
                  <path
                    d={path}
                    fill="none"
                    markerEnd={lit || live ? 'url(#arrowLive)' : 'url(#arrow)'}
                    opacity={outside ? 0.1 : focus && !lit ? 0.2 : 1}
                    stroke={lit || live ? 'var(--primary)' : 'var(--border)'}
                    strokeWidth={lit ? 2.4 : 1.6}
                  />
                  {live && !outside ? (
                    <circle fill="var(--accent)" r="3.6">
                      <animateMotion dur="1.5s" path={path} repeatCount="indefinite" />
                      <animate attributeName="opacity" dur="1.5s" repeatCount="indefinite" values="0;1;1;0" />
                    </circle>
                  ) : null}
                </g>
              );
            })}

            {nodes.map((node) => {
              const position = positions[node.name];
              if (!position) return null;
              const isCoded = node.kind === 'coded_tool';
              const isActive = activeName === node.name;
              const isDone = doneNames.has(node.name);
              const outside = subtree ? !subtree.has(node.name) : false;
              const dim =
                outside ||
                (focus !== '' && focus !== node.name && !focusEdges.has(`${focus}->${node.name}`) && !focusEdges.has(`${node.name}->${focus}`));
              return (
                <motion.g
                  animate={{ opacity: dim ? 0.22 : 1 }}
                  key={node.name}
                  onDoubleClick={() => setIsolated(isolated === node.name ? '' : node.name)}
                  onMouseEnter={() => setHover(node.name)}
                  onMouseLeave={() => setHover('')}
                  onPointerDown={(event) => onNodePointerDown(event, node)}
                  style={{ cursor: mode === 'pan' ? 'grab' : dragging === node.name ? 'grabbing' : 'pointer' }}
                  transition={{ duration: 0.2 }}
                >
                  <rect
                    className={`gNode${node.is_front_man ? ' frontman' : ''}${isCoded ? ' coded' : ''}${selected === node.name ? ' selected' : ''}${isActive ? ' active' : ''}${isDone ? ' done' : ''}`}
                    height={NODE_H}
                    rx="13"
                    width={NODE_W}
                    x={position.x}
                    y={position.y}
                  />
                  {isActive ? (
                    <rect className="gHalo" height={NODE_H} rx="13" width={NODE_W} x={position.x} y={position.y}>
                      <animate attributeName="opacity" dur="1.1s" repeatCount="indefinite" values="0.9;0.25;0.9" />
                    </rect>
                  ) : null}
                  <text className="gNodeTitle" x={position.x + 34} y={position.y + 24}>
                    {node.name.replace(/_Agent$/, '').replace(/_/g, ' ').slice(0, 22)}
                  </text>
                  <text className="gNodeSub" x={position.x + 34} y={position.y + 41}>
                    {isCoded ? 'deterministic tool' : node.is_front_man ? 'front man' : `calls ${node.down_chain.length}`}
                  </text>
                  <g transform={`translate(${position.x + 12} ${position.y + 20})`}>
                    {isCoded ? <Cpu color="var(--accent-2)" size={15} /> : <Bot color={node.is_front_man ? 'var(--primary)' : 'var(--accent)'} size={15} />}
                  </g>
                </motion.g>
              );
            })}
          </g>
        </svg>
      </div>

      <p className="cardNote" style={{ marginTop: 10 }}>
        <strong>Drag</strong> a node to rearrange it, <strong>scroll</strong> to zoom at the cursor, <strong>drag the
        background</strong> in Pan mode, <strong>click</strong> to pin details, <strong>double-click</strong> to isolate a
        branch, or press <strong>Play a run</strong> to watch the front man fan out.
      </p>
    </div>
  );
}
