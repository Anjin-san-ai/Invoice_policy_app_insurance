import {
  BarChart3,
  CreditCard,
  FileText,
  Gauge,
  ListChecks,
  MessageSquareWarning,
  PiggyBank,
  Radar,
  ScrollText,
  ShieldCheck,
  Tags,
  Users,
} from 'lucide-react';
import { ReactNode } from 'react';
import { GlobalSearch } from '../components/GlobalSearch';
import { TheoWidget } from '../components/TheoWidget';
import { ThemeToggle } from '../components/ThemeToggle';
import { navigate } from '../router';

/** Left navigation for the insurer portal.
 *
 * Home is the front door, which is the only route to the customer portal: the customer product is
 * deliberately not reachable from inside the staff workspace. Ask Theo sits directly under Home
 * because a handler's day starts with "what needs me", not with a dashboard. */
const NAV_GROUPS = [
  // The daily path through a claim, in the order the work actually happens. There is no Home item:
  // the brand in the top left is the way back to the front door, and Theo is a floating widget.
  [
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
    // The insurer portal keeps bg2 behind every module, so the whole app is photographic.
    <div className="shell hasBackdrop" data-backdrop="bg2">
      <aside className="sidebar">
        {/* Top left returns to the front door, the same as on the customer side. */}
        <button className="brandBtn" onClick={() => navigate('/')} type="button">
          <span className="brand">CMP-UC-002</span>
          <small className="brandSub">Invoice to pay</small>
        </button>
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
        {/* One search bar for every screen: it lives in the shell, not in each page. The brand
            repeats here because the sidebar is hidden on narrow screens, and the brand must always
            be a way back to the front door. */}
        <div className="topBar">
          <button className="topBrand" onClick={() => navigate('/')} title="Back to the front door" type="button">
            <span className="portalMark">
              <ShieldCheck size={17} />
            </span>
            <b>Cognizant</b>
          </button>
          <GlobalSearch />
          <ThemeToggle />
        </div>
        {children}
      </main>
      {/* Theo follows the handler across every module rather than owning a page of his own. */}
      <TheoWidget />
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
