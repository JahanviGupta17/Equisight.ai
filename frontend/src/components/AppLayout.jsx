import { Link, useLocation, Outlet, useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import {
  LayoutDashboard,
  UploadCloud,
  Activity,
  Bell,
  Settings,
  LogOut,
  BrainCircuit,
  AlertTriangle,
  Loader2,
  MessageSquare,
} from 'lucide-react';
import { useStore } from '../store/useStore';

const NAV_LINKS = [
  { path: '/',          label: 'Dashboard',      icon: LayoutDashboard },
  { path: '/upload',    label: 'Data Ingestion', icon: UploadCloud },
  { path: '/alerts',    label: 'Active Alerts',  icon: Bell },
  { path: '/chat',      label: 'AI Advisor',     icon: MessageSquare },
  { path: '/settings',  label: 'Settings',       icon: Settings },
];

export default function AppLayout() {
  const location  = useLocation();
  const navigate  = useNavigate();
  const logout    = useStore((s) => s.logout);
  const alerts    = useStore((s) => s.alerts);
  const advisoryProgress = useStore((s) => s.advisoryProgress);

  const pendingCount = alerts.filter((a) => a.status === 'pending').length;
  const isGenerating = Boolean(advisoryProgress);

  const handleLogout = () => {
    logout();
    navigate('/login', { replace: true });
  };

  return (
    <div className="flex h-screen bg-[#0a0a0a] text-slate-200 overflow-hidden font-sans">
      {/* ── Sidebar ── */}
      <aside className="w-64 bg-[#0f1117] border-r border-slate-800 flex flex-col z-20">
        {/* Logo */}
        <div className="p-6 flex items-center gap-3 border-b border-slate-800">
          <motion.div
            animate={{ boxShadow: ['0 0 10px rgba(16,185,129,0.2)', '0 0 20px rgba(16,185,129,0.6)', '0 0 10px rgba(16,185,129,0.2)'] }}
            transition={{ duration: 2, repeat: Infinity }}
            className="w-10 h-10 rounded-xl bg-gradient-to-br from-emerald-400 to-emerald-600 flex items-center justify-center"
          >
            <BrainCircuit className="w-6 h-6 text-white" />
          </motion.div>
          <span className="text-xl font-bold tracking-tight text-white">
            Equisight<span className="text-emerald-500">.ai</span>
          </span>
        </div>

        {/* Nav */}
        <nav className="flex-1 p-4 space-y-1">
          {NAV_LINKS.map((link) => {
            const isActive = link.path === '/'
              ? location.pathname === '/'
              : location.pathname.startsWith(link.path);
            const Icon = link.icon;
            const isAlerts = link.path === '/alerts';

            return (
              <Link key={link.path} to={link.path}>
                <motion.div
                  whileHover={{ x: 4 }}
                  className={`flex items-center gap-3 px-4 py-3 rounded-xl transition-colors ${
                    isActive
                      ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 shadow-[inset_0_0_12px_rgba(16,185,129,0.1)]'
                      : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50'
                  }`}
                >
                  <Icon className="w-5 h-5 flex-shrink-0" />
                  <span className="font-medium text-sm flex-1">{link.label}</span>

                  {/* Alert badge */}
                  {isAlerts && (pendingCount > 0 || isGenerating) && (
                    <span className={`flex items-center justify-center min-w-[22px] h-5 rounded-full text-[11px] font-bold px-1 ${
                      isGenerating && pendingCount === 0
                        ? 'bg-amber-500/20 text-amber-400'
                        : 'bg-red-500/20 text-red-400'
                    }`}>
                      {isGenerating && pendingCount === 0
                        ? <Loader2 className="w-3 h-3 animate-spin" />
                        : pendingCount}
                    </span>
                  )}
                </motion.div>
              </Link>
            );
          })}
        </nav>

        {/* User + logout */}
        <div className="p-4 border-t border-slate-800">
          <div className="flex items-center justify-between px-3 py-2 rounded-xl hover:bg-slate-800/40 transition-colors">
            <div className="flex items-center gap-3 min-w-0">
              <div className="w-8 h-8 rounded-full bg-emerald-500/20 border border-emerald-500/30 flex-shrink-0 flex items-center justify-center text-xs font-bold text-emerald-400 uppercase">
                {import.meta.env.VITE_USERNAME?.slice(0, 2) || 'AD'}
              </div>
              <div className="flex flex-col min-w-0">
                <span className="text-sm font-medium text-slate-200 truncate">
                  {import.meta.env.VITE_USERNAME || 'Admin'}
                </span>
                <span className="text-xs text-slate-500">Premium</span>
              </div>
            </div>
            <button
              onClick={handleLogout}
              title="Sign out"
              className="flex-shrink-0 p-1.5 rounded-lg text-slate-500 hover:text-red-400 hover:bg-red-500/10 transition-colors"
            >
              <LogOut className="w-4 h-4" />
            </button>
          </div>
        </div>
      </aside>

      {/* ── Main ── */}
      <div className="flex-1 flex flex-col overflow-hidden relative">
        {/* Topbar */}
        <header className="h-16 bg-[#0f1117]/80 backdrop-blur-md border-b border-slate-800 flex items-center justify-between px-8 z-10">
          <h1 className="text-lg font-semibold text-slate-100">
            {NAV_LINKS.find((l) => l.path === '/'
              ? location.pathname === '/'
              : location.pathname.startsWith(l.path))?.label || 'Dashboard'}
          </h1>

          {/* Advisory status pill in topbar */}
          <AnimatePresence>
            {isGenerating && (
              <motion.div
                initial={{ opacity: 0, y: -8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -8 }}
                className="flex items-center gap-2 bg-amber-500/10 border border-amber-500/20 rounded-full px-4 py-1.5"
              >
                <Loader2 className="w-3.5 h-3.5 text-amber-400 animate-spin" />
                <span className="text-xs font-medium text-amber-300">{advisoryProgress?.message}</span>
              </motion.div>
            )}
            {!isGenerating && pendingCount > 0 && (
              <motion.div
                initial={{ opacity: 0, y: -8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -8 }}
              >
                <Link
                  to="/alerts"
                  className="flex items-center gap-2 bg-red-500/10 border border-red-500/20 rounded-full px-4 py-1.5 hover:bg-red-500/20 transition-colors"
                >
                  <AlertTriangle className="w-3.5 h-3.5 text-red-400" />
                  <span className="text-xs font-medium text-red-300">
                    {pendingCount} alert{pendingCount > 1 ? 's' : ''} need attention
                  </span>
                </Link>
              </motion.div>
            )}
          </AnimatePresence>
        </header>

        {/* Page */}
        <main className="flex-1 overflow-y-auto bg-[#0a0a0a] p-8">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
