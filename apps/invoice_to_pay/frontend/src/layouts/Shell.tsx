import {
  BarChart3,
  CreditCard,
  FileText,
  Gauge,
  Home,
  ListChecks,
  MessageSquareWarning,
  PiggyBank,
  Radar,
  ScrollText,
  ShieldCheck,
  Sparkles,
  Tags,
  Users,
} from 'lucide-react';
import { ReactNode } from 'react';
import { GlobalSearch } from '../components/GlobalSearch';
import { ThemeToggle } from '../components/ThemeToggle';
import { navigate } from '../router';

/** Left navigation for the insurer portal.
 *
 * Home is the front door, which is the only route to the customer portal: the customer product is
 * deliberately not reachable from inside the staff workspace. Ask Theo sits directly under Home
 * because a handler's day starts with "what needs me", not with a dashboard. */
const NAV_GROUPS = [
  // The front door on its own: it is the only way to the customer portal.
  [{ path: '/', label: 'Home', Icon: Home }],
  // The daily path through a claim, in the order the work actually happens.
  [
    { path: '/ask-theo', label: 'Ask Theo', Icon: Sparkles },
    { path: '/dashboard', label: 'Dashboard', Icon: Gauge },
    { path: '/claims', label: 'Claim 360', Icon: Radar },
    { path: '/queue', label: 'Invoice Work Queue', Icon: FileText },
    { path: '/approvals', label: 'Approvals & Payments', Icon: CreditCard },
  ],
  // Things that need chasing, and the reference data behind them. Settings lives inside
  // Policies, because every threshold on it is a policy control.
  [
    { path: '/exceptions', label: 'Exceptions', Icon: ListChecks },
    { path: '/disputes', label: 'Disputes', Icon: MessageSquareWarning },
    { path: '/suppliers', label: 'Suppliers', Icon: Users },
    { path: '/rate-cards', label: 'Policies', Icon: Tags },
  ],
  // Reporting and assurance.
  [
    { path: '/analytics', label: 'Analytics', Icon: BarChart3 },
    { path: '/benefits', label: 'Benefits Tracker', Icon: PiggyBank },
    { path: '/audit', label: 'Audit Trail', Icon: ShieldCheck },
  ],
] as const;

/** Flat list of every navigable module, for anything that needs to resolve a route to a label. */
export const NAV = NAV_GROUPS.flat();

export function Shell({ activePath, children }: { activePath: string; children: ReactNode }) {
  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">CMP-UC-002</div>
        <p className="brandSub">Invoice to pay</p>
        <nav aria-label="Modules">
          {NAV_GROUPS.map((group, groupIndex) => (
            <div key={group[0].path}>
              {groupIndex > 0 ? <hr className="navDivider" /> : null}
              {group.map(({ path, label, Icon }) => {
                // A drilldown is reached from its list, so keep the list lit while on it.
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
            </div>
          ))}
        </nav>
        <p className="brandSub" style={{ marginTop: 20, fontSize: 11 }}>
          <ScrollText size={12} style={{ verticalAlign: '-2px' }} /> Audit-first prototype
        </p>
      </aside>
      <main className="content">
        {/* One search bar for every screen: it lives in the shell, not in each page. */}
        <div className="topBar">
          <GlobalSearch />
          <ThemeToggle />
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
