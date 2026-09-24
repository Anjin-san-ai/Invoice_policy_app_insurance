import { motion } from 'framer-motion';
import { Bot, Cpu, Workflow } from 'lucide-react';
import { useState } from 'react';
import { useApi } from '../api/useApi';
import { StatChip } from '../charts/Visuals';
import { AgentGraph } from '../components/AgentGraph';
import { Empty, KeyValues, Loading } from '../components/Common';
import { PageHead } from '../layouts/Shell';
import { AgentNetwork, AgentNode, AgentTrace, Invoice } from '../types';

export function AgentStudio() {
  const network = useApi<AgentNetwork>('/api/agent-network');
  const invoices = useApi<Invoice[]>('/api/invoices?limit=1');
  const sampleId = invoices.data?.[0]?.id ?? null;
  const trace = useApi<AgentTrace[]>(sampleId ? `/api/invoices/${sampleId}/trace` : null);
  const [selected, setSelected] = useState<AgentNode | null>(null);

  if (network.loading) return <Loading rows={4} />;
  if (network.error) return <Empty>Could not load the agent network: {network.error}</Empty>;
  if (!network.data) return <Empty>No agent network data.</Empty>;

  const data = network.data;

  return (
    <>
      <PageHead
        eyebrow="Agent studio"
        title="Neuro SAN agent network"
        sub={`Parsed live from ${data.source_file}. Twelve LLM agents over one shared deterministic tool, so rate arithmetic, tolerance maths and payment adapters never run inside the model.`}
      />

      <section className="chipRow section">
        <StatChip label="LLM agents" value={data.llm_agent_count} />
        <StatChip label="Coded tools" value={data.coded_tool_count} />
        <StatChip label="Down-chain edges" value={data.edges.length} />
        <StatChip label="Provider" value={data.llm_class ?? 'not set'} />
        <StatChip label="Budget" value={`${data.max_execution_seconds}s / ${data.max_steps} steps`} />
      </section>

      <article className="card section">
        <h2><Workflow size={15} /> Interactive topology</h2>
        <AgentGraph edges={data.edges} nodes={data.nodes} onSelect={setSelected} selected={selected?.name} />
      </article>

      <section className="grid two section">
        <article className="card">
          <h2>{selected ? 'Selected agent' : 'Agent roster'}</h2>
          {selected ? (
            <motion.div animate={{ opacity: 1, y: 0 }} initial={{ opacity: 0, y: 10 }} key={selected.name}>
              <h3 style={{ textTransform: 'none', fontSize: 15, color: 'var(--text)' }}>
                {selected.kind === 'coded_tool' ? <Cpu size={14} /> : <Bot size={14} />} {selected.name}
              </h3>
              <KeyValues
                items={[
                  ['Kind', <span className="chip">{selected.kind === 'coded_tool' ? 'deterministic coded tool' : 'LLM agent'}</span>],
                  ['Role', selected.is_front_man ? 'Front man, owns the canonical invoice state' : 'Down-chain specialist'],
                  ['Calls', selected.down_chain.length ? selected.down_chain.join(', ') : 'nothing, it is a leaf'],
                  ...(selected.coded_class ? ([['Class', <span className="mono">{selected.coded_class}</span>]] as Array<[string, React.ReactNode]>) : []),
                ]}
              />
              <h3 style={{ marginTop: 16 }}>What it does</h3>
              <p className="cardNote">{selected.description || 'No description declared.'}</p>
              <button className="btn secondary" onClick={() => setSelected(null)} style={{ marginTop: 10 }} type="button">
                Clear selection
              </button>
            </motion.div>
          ) : (
            <>
              <p className="cardNote">Click any node in the graph to inspect it. Dashed node is the shared coded tool.</p>
              {data.nodes.map((node, index) => (
                <motion.button
                  animate={{ opacity: 1, x: 0 }}
                  className="listRow"
                  initial={{ opacity: 0, x: -8 }}
                  key={node.name}
                  onClick={() => setSelected(node)}
                  transition={{ delay: index * 0.03 }}
                  type="button"
                >
                  <div>
                    <b>{node.kind === 'coded_tool' ? <Cpu size={12} /> : <Bot size={12} />} {node.name.replace(/_/g, ' ')}</b>
                    <small>{node.is_front_man ? 'front man' : node.kind === 'coded_tool' ? 'deterministic tool' : `calls ${node.down_chain.length}`}</small>
                  </div>
                  <div className="listRowRight">
                    <span className="chip">{node.kind === 'coded_tool' ? 'tool' : 'agent'}</span>
                  </div>
                </motion.button>
              ))}
            </>
          )}
        </article>

        <article className="card">
          <h2>Last deterministic run</h2>
          <p className="cardNote">Pipeline trace for {sampleId ?? 'no invoice'}. This is what the coded tool executes on every agent call.</p>
          {trace.loading ? (
            <Loading rows={3} />
          ) : (trace.data ?? []).length === 0 ? (
            <Empty>No trace recorded.</Empty>
          ) : (
            <div className="trace">
              {(trace.data ?? []).map((entry, index) => (
                <motion.details
                  animate={{ opacity: 1, x: 0 }}
                  className="traceItem"
                  initial={{ opacity: 0, x: 8 }}
                  key={entry.id}
                  transition={{ delay: index * 0.05 }}
                >
                  <summary>
                    {entry.sequence}. {entry.agent_name}
                    <div className="meta">{entry.duration_ms} ms · confidence {Math.round(entry.confidence * 100)}%</div>
                  </summary>
                  <pre>{JSON.stringify(entry.output_json, null, 2)}</pre>
                </motion.details>
              ))}
            </div>
          )}
          <h3 style={{ marginTop: 16 }}>Versions</h3>
          <KeyValues
            items={[
              ['Source file', <span className="mono">{data.source_file}</span>],
              ['Prompt version', <span className="mono">{trace.data?.[0]?.prompt_version ?? '—'}</span>],
              ['Model version', <span className="mono">{trace.data?.[0]?.model_version ?? '—'}</span>],
              ['Extraction schema', <span className="mono">invoice-extraction-v1</span>],
            ]}
          />
        </article>
      </section>
    </>
  );
}
