import { motion } from 'framer-motion';
import { ReactNode } from 'react';

/** Page transition wrapper. A div rather than <main>, because Shell already renders the <main>. */
export function Page({ children }: { children: ReactNode }) {
  return (
    <motion.div
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -8 }}
      initial={{ opacity: 0, y: 12 }}
      transition={{ duration: 0.24, ease: 'easeOut' }}
    >
      {children}
    </motion.div>
  );
}
