import { motion } from 'framer-motion';
import { ArrowRight, Hash, Home, LogIn, Mail, Phone, ShieldCheck, User } from 'lucide-react';
import { useState } from 'react';
import { EmotingAgent } from '../components/EmotingAgent';
import { CustomerProfile } from '../types';

/** Identities that exist in the seeded estate, so a booth visitor can sign in and see real claims. */
const DEMO_IDENTITIES: CustomerProfile[] = [
  {
    customer_name: 'Priya Raman',
    contact_number: '07700900123',
    contact_email: 'priya.raman@example.com',
    address: '2 Mill Lane, LS1 4AP',
    insurance_number: 'INS-0000014',
  },
  {
    customer_name: 'Tom Whitfield',
    contact_number: '07700900456',
    contact_email: 'tom.whitfield@example.com',
    address: '3 Station Road, B3 1JJ',
    insurance_number: 'INS-0000027',
  },
  {
    customer_name: 'Aisha Bello',
    contact_number: '07700900789',
    contact_email: 'aisha.bello@example.com',
    address: '4 Victoria Avenue, M60 2AB',
    insurance_number: 'INS-0000040',
  },
];

const FIELDS: Array<{ key: keyof CustomerProfile; label: string; placeholder: string; icon: typeof User; type?: string }> = [
  { key: 'customer_name', label: 'Full name', placeholder: 'Priya Raman', icon: User },
  { key: 'insurance_number', label: 'Insurance number', placeholder: 'INS-0000014', icon: Hash },
  { key: 'contact_number', label: 'Contact number', placeholder: '07700 900123', icon: Phone, type: 'tel' },
  { key: 'contact_email', label: 'Email address', placeholder: 'priya.raman@example.com', icon: Mail, type: 'email' },
  { key: 'address', label: 'Address', placeholder: '2 Mill Lane, Leeds LS1 4AP', icon: Home },
];

/**
 * Portal sign-in. Collects the policyholder details once, so the assistant never has to ask for
 * them and the back office gets them attached to every claim.
 *
 * There is no authentication here: the prototype has no identity provider, so this is identity by
 * assertion and is clearly labelled as such.
 */
export function PortalLogin({ onSignIn }: { onSignIn: (profile: CustomerProfile) => void }) {
  const [profile, setProfile] = useState<CustomerProfile>({
    customer_name: '',
    insurance_number: '',
    contact_number: '',
    contact_email: '',
    address: '',
  });
  const [touched, setTouched] = useState(false);

  const missing = FIELDS.filter((field) => !profile[field.key].trim()).map((field) => field.key);
  const ready = missing.length === 0;

  return (
    <div className="loginWrap">
      <motion.div animate={{ opacity: 1, y: 0 }} className="loginArt" initial={{ opacity: 0, y: 16 }}>
        <EmotingAgent mood="idle" showMood={false} size={250} variant="full" />
        <h1 className="stageTitle">
          Welcome to <em>Cognizant Motor Claims</em>
        </h1>
        <p className="stageBlurb">
          Sign in with your policy details and Theo will take your claim in a couple of minutes — or
          check on a claim you have already made.
        </p>
      </motion.div>

      <motion.form
        animate={{ opacity: 1, y: 0 }}
        className="card loginCard"
        initial={{ opacity: 0, y: 20 }}
        onSubmit={(event) => {
          event.preventDefault();
          setTouched(true);
          if (ready) onSignIn(profile);
        }}
        transition={{ delay: 0.08 }}
      >
        <div className="loginHead">
          <span className="portalMark">
            <ShieldCheck size={19} />
          </span>
          <div>
            <b>Policyholder sign-in</b>
            <small>We use these details on every claim you make.</small>
          </div>
        </div>

        {FIELDS.map((field) => {
          const Icon = field.icon;
          const invalid = touched && !profile[field.key].trim();
          return (
            <label className="loginField" key={field.key}>
              <span className="fieldLabel">{field.label}</span>
              <span className={`loginInput${invalid ? ' invalid' : ''}`}>
                <Icon size={15} />
                <input
                  autoComplete={field.key === 'customer_name' ? 'name' : field.key === 'contact_number' ? 'tel' : 'off'}
                  onChange={(event) => setProfile((current) => ({ ...current, [field.key]: event.target.value }))}
                  placeholder={field.placeholder}
                  type={field.type ?? 'text'}
                  value={profile[field.key]}
                />
              </span>
              {invalid ? <em className="loginError">{field.label} is needed</em> : null}
            </label>
          );
        })}

        <button className="btn big" disabled={!ready} style={{ width: '100%', justifyContent: 'center' }} type="submit">
          <LogIn size={16} /> Sign in
        </button>

        <div className="loginDemo">
          <small>Booth demo — sign in as a seeded policyholder:</small>
          <div className="btnRow">
            {DEMO_IDENTITIES.map((identity) => (
              <button
                className="chatQuickChip"
                key={identity.insurance_number}
                onClick={() => onSignIn(identity)}
                type="button"
              >
                {identity.customer_name} <ArrowRight size={12} />
              </button>
            ))}
          </div>
        </div>

        <p className="loginNote">
          Prototype only: details are taken at face value and are not checked against an identity
          provider.
        </p>
      </motion.form>
    </div>
  );
}
