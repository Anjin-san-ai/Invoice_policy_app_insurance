import {
  BarChart3,
  CreditCard,
  FileText,
  Gauge,
  ListChecks,
  MessageSquareWarning,
  Network,
  PiggyBank,
  Radar,
  ScrollText,
  Settings,
  ShieldCheck,
  Tags,
  Users,
} from 'lucide-react';
import { ReactNode } from 'react';
import { GlobalSearch } from '../components/GlobalSearch';
import { navigate } from '../router';

/** Left navigation modules, in the order mandated by spec section 13.2. */
export const NAV = [
  { path: '/dashboard', label: 'Dashboard', Icon: Gauge },
  { path: '/queue', label: 'Invoice Work Queue', Icon: FileText },
  { path: '/claims', label: 'Claim 360', Icon: Radar },
  { path: '/exceptions', label: 'Exceptions', Icon: ListChecks },
  { path: '/disputes', label: 'Disputes', Icon: MessageSquareWarning },
  { path: '/approvals', label: 'Approvals & Payments', Icon: CreditCard },
  { path: '/suppliers', label: 'Suppliers', Icon: Users },
  { path: '/rate-cards', label: 'Rate Cards', Icon: Tags },
  { path: '/analytics', label: 'Analytics', Icon: BarChart3 },
  { path: '/benefits', label: 'Benefits Tracker', Icon: PiggyBank },
  { path: '/audit', label: 'Audit Trail', Icon: ShieldCheck },
  { path: '/agent-studio', label: 'Agent Studio', Icon: Network },
  { path: '/settings', label: 'Settings', Icon: Settings },
] as const;

export function Shell({ activePath, children }: { activePath: string; children: ReactNode }) {
  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">CMP-UC-002</div>
        <p className="brandSub">Invoice to pay</p>
        <nav aria-label="Modules">
          {NAV.map(({ path, label, Icon }) => {
            // The invoice drilldown is reached from the queue, so keep the queue lit while on it.
            const isActive =
              activePath === path ||
              (path === '/queue' && activePath.startsWith('/invoice/')) ||
              (path === '/claims' && activePath.startsWith('/claim/'));
            return (
              <button
                aria-current={isActive ? 'page' : undefined}
                className={`navItem${isActive ? ' active' : ''}`}
                key={path}
                onClick={() => navigate(path)}
                type="button"
              >
                <Icon size={17} />
                <span>{label}</span>
              </button>
            );
          })}
        </nav>
        <p className="brandSub" style={{ marginTop: 20, fontSize: 11 }}>
          <ScrollText size={12} style={{ verticalAlign: '-2px' }} /> Audit-first prototype
        </p>
      </aside>
      <main className="content">
        {/* One search bar for every screen: it lives in the shell, not in each page. */}
        <div className="topBar">
          <GlobalSearch />
        </div>
        {children}
      </main>
    </div>
  );
}

export function PageHead({ eyebrow, title, sub, actions }: { eyebrow: string; title: string; sub: string; actions?: ReactNode }) {
  return (
    <header className="pageHead">
      <div>
        <p className="eyebrow">{eyebrow}</p>
        <h1>{title}</h1>
        <p className="sub">{sub}</p>
      </div>
      {actions ? <div className="btnRow">{actions}</div> : null}
    </header>
  );
}
