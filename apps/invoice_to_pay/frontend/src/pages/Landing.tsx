import { motion } from 'framer-motion';
import { ArrowRight, Camera, CreditCard, Radar, ShieldCheck, Sparkles, Users } from 'lucide-react';
import { ThemeToggle } from '../components/ThemeToggle';
import { navigate } from '../router';

/** The two audiences this prototype serves, and what each one gets. */
const DOORS = [
  {
    id: 'customer',
    path: '/portal',
    eyebrow: 'For policyholders',
    title: 'Customer portal',
    blurb:
      'Report an incident by talking to Theo, our claims assistant. Add photographs, get a claim reference in minutes, and follow every step.',
    cta: 'Report or track a claim',
    points: [
      { Icon: Sparkles, text: 'AI assistant takes the claim conversationally' },
      { Icon: Camera, text: 'Photograph the damage from your phone' },
      { Icon: Radar, text: 'Track the journey and get updates' },
    ],
  },
  {
    id: 'insurer',
    // Theo is a floating widget inside the workspace now, so this lands on the dashboard.
    path: '/dashboard',
    eyebrow: 'For claims and finance teams',
    title: 'Insurer portal',
    blurb:
      'The back-office workspace: ask Theo what needs you, triage customer claims, instruct suppliers, and validate every supplier invoice against the policy and rate card before it is paid.',
    cta: 'Open the workspace',
    points: [
      { Icon: Sparkles, text: 'Ask Theo anything about the claim estate' },
      { Icon: Users, text: 'Claim 360 with incident evidence and photographs' },
      { Icon: CreditCard, text: 'Instruct suppliers and validate their invoices' },
    ],
  },
] as const;

/** Front door. Sends each audience to the right product rather than defaulting to the back office. */
export function Landing() {
  return (
    <div className="portal hasBackdrop" data-backdrop="bg1">
      <header className="portalBar">
        <button className="portalBrand" onClick={() => navigate('/')} type="button">
          <span className="portalMark">
            <ShieldCheck size={20} />
          </span>
          <div>
            <b>Cognizant Motor Claims</b>
            <small>Claims intake and invoice-to-pay prototype</small>
          </div>
        </button>
        <ThemeToggle />
      </header>

      {/* No hero copy: the photograph sets the scene and the two cards say the rest. */}
      <div className="portalBody landingBody">
        <section className="landingDoors">
          {DOORS.map((door, index) => (
            <motion.button
              animate={{ opacity: 1, y: 0 }}
              className={`landingDoor ${door.id}`}
              initial={{ opacity: 0, y: 20 }}
              key={door.id}
              onClick={() => navigate(door.path)}
              transition={{ delay: 0.1 + index * 0.1 }}
              type="button"
            >
              <p className="heroEyebrow">{door.eyebrow}</p>
              <h2>{door.title}</h2>
              <p className="landingDoorBlurb">{door.blurb}</p>
              <ul className="landingPoints">
                {door.points.map(({ Icon, text }) => (
                  <li key={text}>
                    <span className="bentoIcon">
                      <Icon size={15} />
                    </span>
                    {text}
                  </li>
                ))}
              </ul>
              <span className="landingCta">
                {door.cta} <ArrowRight size={16} />
              </span>
            </motion.button>
          ))}
        </section>

        <p className="loginNote" style={{ textAlign: 'center' }}>
          Prototype for demonstration. Data is synthetic and no real policyholder information is held.
        </p>
      </div>
    </div>
  );
}
