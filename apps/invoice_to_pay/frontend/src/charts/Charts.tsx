import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { useChartTokens } from '../theme/useTheme';
import { gbp, reasonLabel } from '../types';

/* Categorical hues stay distinguishable without relying on colour alone; every chart that encodes
   meaning is paired with a label or a legend. The hues come from the active theme's tokens, so the
   same series reads correctly on both the light and the dark surface.

   Recharts needs concrete colours rather than var() references, so axis, grid and tooltip styling
   is derived per render from the resolved tokens. */
function useChartChrome() {
  const tokens = useChartTokens();
  return {
    tokens,
    axis: { stroke: tokens.axis, fontSize: 11 },
    grid: tokens.grid,
    tooltip: {
      contentStyle: {
        background: tokens.surface,
        border: `1px solid ${tokens.grid}`,
        borderRadius: 12,
        color: tokens.text,
        fontSize: 12,
      },
      labelStyle: { color: tokens.text, fontWeight: 700 },
      itemStyle: { color: tokens.text },
    },
    legend: (value: string) => <span style={{ color: tokens.text, fontSize: 11 }}>{value}</span>,
  };
}

export function ExceptionDonut({ data, onSelect }: { data: Record<string, number>; onSelect?: (reason: string) => void }) {
  const { tokens, tooltip, legend } = useChartChrome();
  const chartData = Object.entries(data).map(([name, value]) => ({ name: reasonLabel(name), raw: name, value }));
  if (!chartData.length) return <p className="empty">No open exceptions.</p>;

  return (
    <ResponsiveContainer height={240}>
      <PieChart>
        <Pie
          data={chartData}
          dataKey="value"
          innerRadius={52}
          onClick={(entry: { raw?: string }) => entry.raw && onSelect?.(entry.raw)}
          outerRadius={86}
          paddingAngle={2}
        >
          {chartData.map((item, index) => (
            <Cell
              cursor={onSelect ? 'pointer' : 'default'}
              fill={tokens.series[index % tokens.series.length]}
              key={item.raw}
            />
          ))}
        </Pie>
        <Legend formatter={legend} />
        <Tooltip {...tooltip} formatter={(value: number) => [`${value} invoices`, 'Count']} />
      </PieChart>
    </ResponsiveContainer>
  );
}

export function LeakageByCategory({ data, label }: { data: Record<string, number>; label: string }) {
  const { tokens, axis, grid, tooltip } = useChartChrome();
  const chartData = Object.entries(data)
    .map(([name, value]) => ({ name: reasonLabel(name), value: Math.round(value) }))
    .sort((left, right) => right.value - left.value);
  if (!chartData.length) return <p className="empty">No variance recorded.</p>;

  return (
    <ResponsiveContainer height={260}>
      <BarChart data={chartData} layout="vertical" margin={{ left: 10, right: 16 }}>
        <CartesianGrid horizontal={false} stroke={grid} />
        <XAxis {...axis} tickFormatter={(value: number) => gbp(value)} type="number" />
        <YAxis {...axis} dataKey="name" type="category" width={132} />
        <Tooltip {...tooltip} formatter={(value: number) => [gbp(value), label]} />
        <Bar dataKey="value" fill={tokens.primary} radius={[0, 5, 5, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}

export function VarianceWaterfall({ rows }: { rows: Array<{ line_no: number; service_type: string; variance_gbp: number; tolerance_outcome: string }> }) {
  const { tokens, axis, grid, tooltip } = useChartChrome();
  const chartData = rows.map((row) => ({
    name: `L${row.line_no} ${row.service_type}`,
    value: Math.round(row.variance_gbp),
    outside: row.tolerance_outcome === 'outside',
  }));
  if (!chartData.length) return <p className="empty">No lines to chart.</p>;

  return (
    <ResponsiveContainer height={190}>
      <BarChart data={chartData} margin={{ left: 0, right: 8 }}>
        <CartesianGrid stroke={grid} vertical={false} />
        <XAxis {...axis} dataKey="name" />
        <YAxis {...axis} tickFormatter={(value: number) => gbp(value)} />
        <Tooltip {...tooltip} formatter={(value: number) => [gbp(value), 'Variance']} />
        <Bar dataKey="value" radius={[5, 5, 0, 0]}>
          {chartData.map((item) => (
            <Cell fill={item.outside ? tokens.danger : tokens.success} key={item.name} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

export function StatusDistribution({ data, onSelect }: { data: Record<string, number>; onSelect?: (status: string) => void }) {
  const { tokens, axis, grid, tooltip } = useChartChrome();
  const chartData = Object.entries(data).map(([name, value]) => ({ name, value }));
  if (!chartData.length) return <p className="empty">No invoices.</p>;

  return (
    <ResponsiveContainer height={240}>
      <BarChart data={chartData} margin={{ left: 0, right: 8 }}>
        <CartesianGrid stroke={grid} vertical={false} />
        <XAxis {...axis} dataKey="name" />
        <YAxis {...axis} />
        <Tooltip {...tooltip} formatter={(value: number) => [`${value} invoices`, 'Count']} />
        <Bar
          dataKey="value"
          onClick={(entry: { name?: string }) => entry.name && onSelect?.(entry.name)}
          radius={[5, 5, 0, 0]}
        >
          {chartData.map((item, index) => (
            <Cell
              cursor={onSelect ? 'pointer' : 'default'}
              fill={tokens.series[index % tokens.series.length]}
              key={item.name}
            />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

export function BenefitProjection({ baseline, growthPct, realised, target }: { baseline: number; growthPct: number; realised: number; target: number }) {
  const { tokens, axis, grid, tooltip, legend } = useChartChrome();
  const data = [0, 1, 2, 3].map((year) => {
    const volume = Math.round(baseline * Math.pow(1 + growthPct / 100, year));
    return {
      name: year === 0 ? 'Now' : `Year ${year}`,
      Volume: volume,
      Realised: Number((realised * Math.pow(1 + growthPct / 100, year)).toFixed(2)),
      Target: target,
    };
  });

  return (
    <ResponsiveContainer height={250}>
      <LineChart data={data} margin={{ left: 0, right: 12 }}>
        <CartesianGrid stroke={grid} vertical={false} />
        <XAxis {...axis} dataKey="name" />
        <YAxis {...axis} yAxisId="fte" />
        <YAxis {...axis} orientation="right" yAxisId="volume" />
        <Tooltip {...tooltip} />
        <Legend formatter={legend} />
        <Line dataKey="Realised" stroke={tokens.primary} strokeWidth={2} yAxisId="fte" />
        <Line dataKey="Target" stroke={tokens.warning} strokeDasharray="5 4" strokeWidth={2} yAxisId="fte" />
        <Line dataKey="Volume" stroke={tokens.accent} strokeWidth={1.5} yAxisId="volume" />
      </LineChart>
    </ResponsiveContainer>
  );
}
