import { AnimatePresence } from 'framer-motion';
import { Page } from '../animations/Page';
import { Shell } from '../layouts/Shell';
import { BACK_OFFICE_PATH, DEFAULT_PATH, useRoute } from '../router';
import { Analytics } from './Analytics';
import { Approvals } from './Approvals';
import { AskTheo } from './AskTheo';
import { AuditTrail } from './AuditTrail';
import { Benefits } from './Benefits';
import { Claim360 } from './Claim360';
import { Dashboard } from './Dashboard';
import { Disputes } from './Disputes';
import { Exceptions } from './Exceptions';
import { InvoiceDrilldown } from './InvoiceDrilldown';
import { Landing } from './Landing';
import { Portal } from './Portal';
import { RateCards } from './RateCards';
import { Suppliers } from './Suppliers';
import { WorkQueue } from './WorkQueue';

export function App() {
  const route = useRoute();
  const { path, params } = route;

  // Two parameterised routes: /invoice/<id> and /claim/<id>.
  const invoiceId = path.startsWith('/invoice/') ? path.slice('/invoice/'.length) : null;
  const claimId = path.startsWith('/claim/') ? path.slice('/claim/'.length) : null;

  // The landing page and the customer portal are separate audiences: they render without the
  // staff shell, sidebar or global search, so they short-circuit before Shell wraps anything.
  if (path === DEFAULT_PATH || path === '/portal') {
    return (
      <AnimatePresence mode="wait">
        <Page key={path}>{path === '/portal' ? <Portal /> : <Landing />}</Page>
      </AnimatePresence>
    );
  }

  function screen() {
    if (invoiceId) return <InvoiceDrilldown invoiceId={invoiceId} />;
    if (claimId) return <Claim360 claimId={claimId} />;
    switch (path) {
      case '/queue':
        return (
          <WorkQueue
            initialSearch={params.get('search') ?? ''}
            reason={params.get('reason') ?? ''}
            status={params.get('status') ?? ''}
            supplierId={params.get('supplier') ?? ''}
          />
        );
      case '/claims':
        return <Claim360 claimId="" />;
      case '/exceptions':
        return <Exceptions reason={params.get('reason') ?? ''} />;
      case '/disputes':
        return <Disputes />;
      case '/approvals':
        return <Approvals />;
      case '/suppliers':
        return <Suppliers />;
      case '/rate-cards':
        return <RateCards />;
      case '/analytics':
        return <Analytics />;
      case '/benefits':
        return <Benefits />;
      case '/audit':
        return <AuditTrail />;
      case '/ask-theo':
        return <AskTheo />;
      case BACK_OFFICE_PATH:
      default:
        return <Dashboard />;
    }
  }

  return (
    <Shell activePath={path}>
      <AnimatePresence mode="wait">
        <Page key={path + params.toString()}>{screen()}</Page>
      </AnimatePresence>
    </Shell>
  );
}
