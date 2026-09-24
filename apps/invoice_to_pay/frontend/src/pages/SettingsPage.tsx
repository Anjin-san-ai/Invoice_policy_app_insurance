import { useApi } from '../api/useApi';
import { Empty, KeyValues, Loading } from '../components/Common';
import { PageHead } from '../layouts/Shell';
import { SettingsResponse, gbp } from '../types';

export function SettingsPage() {
  const { data, error, loading } = useApi<SettingsResponse>('/api/settings');

  if (loading) return <Loading rows={3} />;
  if (error) return <Empty>Could not load settings: {error}</Empty>;
  if (!data) return <Empty>No settings.</Empty>;

  const settings = data.settings;

  return (
    <>
      <PageHead
        eyebrow="Configuration"
        title="Settings"
        sub="Thresholds and GDPR redaction rules are configuration-driven, loaded from the seed file rather than hard-coded. Read-only in this build."
      />

      <section className="grid two section">
        <article className="card">
          <h2>Validation thresholds</h2>
          <KeyValues
            items={[
              ['High value threshold', gbp(settings.high_value_threshold_gbp)],
              ['Tolerance percent', `${settings.tolerance_pct}%`],
              ['Tolerance absolute', gbp(settings.tolerance_gbp)],
              ['Minimum extraction confidence', settings.min_extraction_confidence],
              ['Minimum match confidence', settings.min_match_confidence],
              ['Rate card staleness window', `${settings.rate_card_stale_days} days`],
            ]}
          />
        </article>
        <article className="card">
          <h2>Benefit model parameters</h2>
          <KeyValues items={Object.entries(data.metadata).map(([key, value]) => [key.replace(/_/g, ' '), String(value)])} />
        </article>
      </section>

      <article className="card">
        <h2>GDPR and PII redaction rules</h2>
        <p className="cardNote">Applied by the deterministic rule engine before any model exposure. Each match writes a what-and-why audit entry.</p>
        <div className="tableWrap">
          <table>
            <thead><tr><th>Rule</th><th>Reason</th><th>Pattern</th></tr></thead>
            <tbody>
              {settings.redaction_rules.map((rule) => (
                <tr key={rule.id}>
                  <td className="mono">{rule.id}</td>
                  <td>{rule.reason}</td>
                  <td className="mono">{rule.pattern}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </article>
    </>
  );
}
