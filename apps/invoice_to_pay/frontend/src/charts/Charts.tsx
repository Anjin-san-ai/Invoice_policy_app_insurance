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
import { gbp, reasonLabel } from '../types';

/* Categorical hues kept distinguishable without relying on colour alone; every chart that encodes
   meaning is paired with a label or a legend. */
export const SERIES = ['#0033a0', '#00a5c9', '#6b4fd8', '#d97706', '#059669', '#b91c1c'];

const AXIS = { stroke: '#5a6b85', fontSize: 11 };
const GRID = '#e6ecf5';

export function ExceptionDonut({ data, onSelect }: { data: Record<string, number>; onSelect?: (reason: string) => void }) {
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
            <Cell cursor={onSelect ? 'pointer' : 'default'} fill={SERIES[index % SERIES.length]} key={item.raw} />
          ))}
        </Pie>
        <Legend formatter={(value: string) => <span style={{ color: '#173793', fontSize: 11 }}>{value}</span>} />
        <Tooltip formatter={(value: number) => [`${value} invoices`, 'Count']} />
      </PieChart>
    </ResponsiveContainer>
  );
}

export function LeakageByCategory({ data, label }: { data: Record<string, number>; label: string }) {
  const chartData = Object.entries(data)
    .map(([name, value]) => ({ name: reasonLabel(name), value: Math.round(value) }))
    .sort((left, right) => right.value - left.value);
  if (!chartData.length) return <p className="empty">No variance recorded.</p>;

  return (
    <ResponsiveContainer height={260}>
      <BarChart data={chartData} layout="vertical" margin={{ left: 10, right: 16 }}>
        <CartesianGrid horizontal={false} stroke={GRID} />
        <XAxis {...AXIS} tickFormatter={(value: number) => gbp(value)} type="number" />
        <YAxis {...AXIS} dataKey="name" type="category" width={132} />
        <Tooltip formatter={(value: number) => [gbp(value), label]} />
        <Bar dataKey="value" fill="#0033a0" radius={[0, 5, 5, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}

export function VarianceWaterfall({ rows }: { rows: Array<{ line_no: number; service_type: string; variance_gbp: number; tolerance_outcome: string }> }) {
  const chartData = rows.map((row) => ({
    name: `L${row.line_no} ${row.service_type}`,
    value: Math.round(row.variance_gbp),
    outside: row.tolerance_outcome === 'outside',
  }));
  if (!chartData.length) return <p className="empty">No lines to chart.</p>;

  return (
    <ResponsiveContainer height={190}>
      <BarChart data={chartData} margin={{ left: 0, right: 8 }}>
        <CartesianGrid stroke={GRID} vertical={false} />
        <XAxis {...AXIS} dataKey="name" />
        <YAxis {...AXIS} tickFormatter={(value: number) => gbp(value)} />
        <Tooltip formatter={(value: number) => [gbp(value), 'Variance']} />
        <Bar dataKey="value" radius={[5, 5, 0, 0]}>
          {chartData.map((item) => (
            <Cell fill={item.outside ? '#dc2626' : '#059669'} key={item.name} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

export function StatusDistribution({ data, onSelect }: { data: Record<string, number>; onSelect?: (status: string) => void }) {
  const chartData = Object.entries(data).map(([name, value]) => ({ name, value }));
  if (!chartData.length) return <p className="empty">No invoices.</p>;

  return (
    <ResponsiveContainer height={240}>
      <BarChart data={chartData} margin={{ left: 0, right: 8 }}>
        <CartesianGrid stroke={GRID} vertical={false} />
        <XAxis {...AXIS} dataKey="name" />
        <YAxis {...AXIS} />
        <Tooltip formatter={(value: number) => [`${value} invoices`, 'Count']} />
        <Bar
          dataKey="value"
          onClick={(entry: { name?: string }) => entry.name && onSelect?.(entry.name)}
          radius={[5, 5, 0, 0]}
        >
          {chartData.map((item, index) => (
            <Cell cursor={onSelect ? 'pointer' : 'default'} fill={SERIES[index % SERIES.length]} key={item.name} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

export function BenefitProjection({ baseline, growthPct, realised, target }: { baseline: number; growthPct: number; realised: number; target: number }) {
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
        <CartesianGrid stroke={GRID} vertical={false} />
        <XAxis {...AXIS} dataKey="name" />
        <YAxis {...AXIS} yAxisId="fte" />
        <YAxis {...AXIS} orientation="right" yAxisId="volume" />
        <Tooltip />
        <Legend formatter={(value: string) => <span style={{ color: '#173793', fontSize: 11 }}>{value}</span>} />
        <Line dataKey="Realised" stroke="#0033a0" strokeWidth={2} yAxisId="fte" />
        <Line dataKey="Target" stroke="#d97706" strokeDasharray="5 4" strokeWidth={2} yAxisId="fte" />
        <Line dataKey="Volume" stroke="#00a5c9" strokeWidth={1.5} yAxisId="volume" />
      </LineChart>
    </ResponsiveContainer>
  );
}
