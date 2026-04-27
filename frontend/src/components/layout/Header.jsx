import { Bell, Search } from "lucide-react";
import { useState, useEffect } from "react";
import { cn } from "../../lib/utils";

export default function Header() {
  const [time, setTime] = useState(new Date());
  
  useEffect(() => {
    const timer = setInterval(() => setTime(new Date()), 1000);
    return () => clearInterval(timer);
  }, []);

  const hasAlert = true; // Mock true for now to see the pulsing effect

  return (
    <header className="h-16 bg-[#121212]/95 backdrop-blur supports-[backdrop-filter]:bg-[#121212]/80 border-b border-slate-800 flex items-center justify-between px-8 sticky top-0 z-10">
      <div className="flex items-center gap-4">
        <h1 className="text-slate-200 font-medium text-lg">My Primary Portfolio</h1>
        <div className="flex items-center gap-2 text-xs font-medium px-2.5 py-1 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
          <div className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
          Market Open
        </div>
      </div>

      <div className="flex items-center gap-6">
        <span className="text-slate-400 text-sm font-medium tabular-nums">
          {time.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
        </span>
        
        <div className="relative">
          <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
          <input 
            id="header-search"
            name="header-search"
            type="text" 
            placeholder="Search assets..." 
            className="bg-slate-900 border border-slate-800 rounded-full pl-9 pr-4 py-1.5 text-sm text-slate-200 placeholder:text-slate-600 focus:outline-none focus:ring-1 focus:ring-emerald-500 transition-all w-64"
          />
        </div>

        <button className="relative p-2 text-slate-400 hover:text-white transition-colors rounded-full hover:bg-slate-800">
          <Bell className="w-5 h-5" />
          {hasAlert && (
            <span className="absolute top-1.5 right-1.5 flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-crimson-400 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-2 w-2 bg-red-500"></span>
            </span>
          )}
        </button>
      </div>
    </header>
  );
}
