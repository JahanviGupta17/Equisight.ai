import { useEffect } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import AppLayout from './components/AppLayout';
import { useStore } from './store/useStore';

import Dashboard from './pages/Dashboard';
import Alerts from './pages/Alerts';
import Settings from './pages/Settings';
import Login from './pages/Login';
import Upload from './pages/Upload';
// Analytics page removed — analytics are now inline in Dashboard
import Chat from './pages/Chat';

function App() {
  const isAuthenticated = useStore((state) => state.isAuthenticated);
  const portfolioId = useStore((state) => state.portfolioId);
  const connectWebSocket = useStore((state) => state.connectWebSocket);
  const ws = useStore((state) => state.ws);

  // Connect WebSocket only after confirming the backend is reachable.
  // Retries every 5 s so reopening the project without the backend running
  // never floods the console with ECONNREFUSED errors.
  useEffect(() => {
    if (!isAuthenticated || !portfolioId) return;
    let timer;

    const tryConnect = () => {
      fetch('/api/v1/health', { signal: AbortSignal.timeout(2000) })
        .then((r) => {
          if (r.ok) {
            const current = useStore.getState().ws;
            if (!current || current.readyState > 1) connectWebSocket(portfolioId);
          } else {
            timer = setTimeout(tryConnect, 5000);
          }
        })
        .catch(() => { timer = setTimeout(tryConnect, 5000); });
    };

    tryConnect();
    return () => clearTimeout(timer);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isAuthenticated, portfolioId]);

  return (
    <BrowserRouter>
      <Routes>
        {/* Login always accessible — redirects to / if already authenticated */}
        <Route
          path="/login"
          element={isAuthenticated ? <Navigate to="/" replace /> : <Login />}
        />

        {isAuthenticated ? (
          <Route path="/" element={<AppLayout />}>
            <Route index element={<Dashboard />} />
            <Route path="upload" element={<Upload />} />
            <Route path="analytics" element={<Navigate to="/" replace />} />
            <Route path="alerts" element={<Alerts />} />
            <Route path="chat" element={<Chat />} />
            <Route path="settings" element={<Settings />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        ) : (
          <Route path="*" element={<Navigate to="/login" replace />} />
        )}
      </Routes>
    </BrowserRouter>
  );
}

export default App;
