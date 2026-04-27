import { NavLink, useNavigate } from "react-router-dom";
import { LayoutDashboard, BellRing, PieChart, Settings, UploadCloud, LogOut } from "lucide-react";
import { cn } from "../../lib/utils";
import { useStore } from "../../store/useStore";

const navItems = [
  { name: "Overview",      icon: LayoutDashboard, path: "/" },
  { name: "Upload Data",   icon: UploadCloud,     path: "/upload" },
  { name: "Analytics",     icon: PieChart,        path: "/analytics" },
  { name: "Active Alerts", icon: BellRing,        path: "/alerts" },
  { name: "Settings",      icon: Settings,        path: "/settings" },
];

export default function Sidebar() {
  const logout = useStore((state) => state.logout);
  const alerts = useStore((state) => state.alerts);
  const advisoryProgress = useStore((state) => state.advisoryProgress);
  const navigate = useNavigate();

  const pendingCount = alerts.filter((a) => a.status === 'pending').length;
  const hasProgress  = Boolean(advisoryProgress);

  const handleLogout = () => {
    logout();
    navigate('/login', { replace: true });
  };

  return (
    <aside className="w-64 bg-[#121212] border-r border-slate-800 flex flex-col h-screen fixed top-0 left-0">
      {/* Logo */}
      <div className="h-16 flex items-center px-6 border-b border-slate-800">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-full bg-emerald-500 flex items-center justify-center font-bold text-[#121212]">
            E
          </div>
          <span className="text-white font-semibold text-lg tracking-wide">Equisight.ai</span>
        </div>
      </div>

      {/* Nav */}
      <nav className="flex-1 px-4 py-6 space-y-1">
        {navItems.map((item) => (
          <NavLink
            key={item.name}
            to={item.path}
            end={item.path === '/'}
            className={({ isActive }) =>
              cn(
                "flex items-center gap-3 px-3 py-2.5 rounded-lg transition-colors text-sm font-medium",
                isActive
                  ? "bg-slate-800/50 text-emerald-400"
                  : "text-slate-400 hover:text-slate-200 hover:bg-slate-800/30"
              )
            }
          >
            <item.icon className="w-5 h-5 flex-shrink-0" />
            <span className="flex-1">{item.name}</span>
            {/* Badge: spinning dot while generating, count when ready */}
            {item.path === '/alerts' && (pendingCount > 0 || hasProgress) && (
              <span className={cn(
                "min-w-[20px] h-5 rounded-full text-[11px] font-bold flex items-center justify-center px-1",
                hasProgress && pendingCount === 0
                  ? "bg-amber-500/20 text-amber-400"
                  : "bg-emerald-500/20 text-emerald-400"
              )}>
                {hasProgress && pendingCount === 0 ? '…' : pendingCount}
              </span>
            )}
          </NavLink>
        ))}
      </nav>

      {/* User + logout */}
      <div className="p-4 border-t border-slate-800">
        <div className="flex items-center justify-between px-3 py-2">
          <div className="flex items-center gap-3 min-w-0">
            <div className="w-8 h-8 rounded-full bg-slate-700 flex-shrink-0 flex items-center justify-center text-xs text-white uppercase">
              {import.meta.env.VITE_USERNAME?.slice(0, 2) || 'AD'}
            </div>
            <div className="flex flex-col min-w-0">
              <span className="text-sm font-medium text-slate-200 truncate">
                {import.meta.env.VITE_USERNAME || 'Admin'}
              </span>
              <span className="text-xs text-slate-500">Premium Tier</span>
            </div>
          </div>
          <button
            onClick={handleLogout}
            title="Sign out"
            className="flex-shrink-0 text-slate-500 hover:text-red-400 transition-colors p-1.5 rounded-lg hover:bg-slate-800"
          >
            <LogOut className="w-4 h-4" />
          </button>
        </div>
      </div>
    </aside>
  );
}
