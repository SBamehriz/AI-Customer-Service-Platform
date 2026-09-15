import * as React from 'react';
import { Navigate, Route, Routes, useLocation } from 'react-router-dom';
import { AppShell } from '@/components/layout';
import { Spinner } from '@/components/ui';
import { useSession } from './session';

const LandingPage = React.lazy(() => import('@/features/marketing/LandingPage'));
const LoginPage = React.lazy(() => import('@/features/auth/LoginPage'));
const RegisterPage = React.lazy(() => import('@/features/auth/RegisterPage'));
const PortalPage = React.lazy(() => import('@/features/portal/PortalPage'));
const SetupGuide = React.lazy(() => import('@/features/marketing/SetupGuide'));
const HomePage = React.lazy(() => import('@/features/home/HomePage'));
const InboxPage = React.lazy(() => import('@/features/inbox/InboxPage'));
const TicketsPage = React.lazy(() => import('@/features/tickets/TicketsPage'));
const CustomersPage = React.lazy(() => import('@/features/customers/CustomersPage'));
const KnowledgePage = React.lazy(() => import('@/features/knowledge/KnowledgePage'));
const AnalyticsPage = React.lazy(() => import('@/features/analytics/AnalyticsPage'));
const TapPage = React.lazy(() => import('@/features/tap/TapPage'));
const SettingsPage = React.lazy(() => import('@/features/settings/SettingsPage'));

function FullPageSpinner() {
  return (
    <div className="flex h-dvh items-center justify-center bg-bg">
      <Spinner className="h-5 w-5" />
    </div>
  );
}

/** Blocks the workspace routes until a session exists. */
function RequireAuth({ children }: { children: React.ReactNode }) {
  const { status } = useSession();
  const location = useLocation();

  if (status === 'loading') return <FullPageSpinner />;
  if (status === 'anonymous') {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }
  return <>{children}</>;
}

export function App() {
  const { status } = useSession();

  if (status === 'loading') return <FullPageSpinner />;

  return (
    <React.Suspense fallback={<FullPageSpinner />}>
      <Routes>
        <Route path="/" element={<LandingPage />} />
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />
        <Route path="/portal" element={<PortalPage />} />
        <Route path="/setup" element={<SetupGuide />} />

        <Route
          path="/app"
          element={
            <RequireAuth>
              <AppShell />
            </RequireAuth>
          }
        >
          <Route index element={<HomePage />} />
          <Route path="inbox" element={<InboxPage />} />
          <Route path="tickets" element={<TicketsPage />} />
          <Route path="customers" element={<CustomersPage />} />
          <Route path="knowledge" element={<KnowledgePage />} />
          <Route path="analytics" element={<AnalyticsPage />} />
          <Route path="tap" element={<TapPage />} />
          <Route path="settings" element={<SettingsPage />} />
          <Route path="*" element={<Navigate to="/app" replace />} />
        </Route>

        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </React.Suspense>
  );
}
