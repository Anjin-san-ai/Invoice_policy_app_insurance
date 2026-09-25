import React from 'react';
import { createRoot } from 'react-dom/client';
import { App } from './pages/App';
import { ThemeProvider } from './theme/useTheme';
import './style.css';

createRoot(document.getElementById('root') as HTMLElement).render(
  <React.StrictMode>
    <ThemeProvider>
      <App />
    </ThemeProvider>
  </React.StrictMode>,
);
