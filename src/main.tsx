import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';

import { App } from './app/App';
import { SessionProvider } from './app/session';
import { ThemeProvider } from './app/theme';
import { ToastProvider } from './components/ui';

import './styles/globals.css';

const root = document.getElementById('root');
if (!root) throw new Error('Missing #root element');

ReactDOM.createRoot(root).render(
  <React.StrictMode>
    <ThemeProvider>
      <ToastProvider>
        <SessionProvider>
          <BrowserRouter>
            <App />
          </BrowserRouter>
        </SessionProvider>
      </ToastProvider>
    </ThemeProvider>
  </React.StrictMode>,
);
