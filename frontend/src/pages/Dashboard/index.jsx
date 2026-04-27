import { useState, useEffect } from 'react';
import { useStore } from '../../store/useStore';
import { motion, AnimatePresence } from 'framer-motion';
import ScenarioSimulator from './ScenarioSimulator';
import {
  TrendingUp, TrendingDown, DollarSign, UploadCloud,
  Activity, Target, Zap, CheckCircle, AlertCircle, Loader2,
} from 'lucide-react';
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell,
  BarChart, Bar, Legend,
} from 'recharts';
import { useNavigate } from 'react-router-dom';

const formatINR = (v) =>
  new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 0 }).format(v ?? 0);

const makeYFmt = (max) => (v) => {
  if (max >= 10_000_000) return `₹${(v / 10_000_000).toFixed(1)}Cr`;
  if (max >= 100_000)    return `₹${(v / 100_000).toFixed(0)}L`;
  if (max >= 1_000)      return `₹${(v / 1_000).toFixed(0)}K`;
  return `₹${v}`;
};

const COLORS = ['#10b981','#3b82f6','#8b5cf6','#f59e0b','#ec4899','#14b8a6','#f97316'];

// Thin down a daily series to ~52 points (weekly) for chart readability
function downsample(series, targetPoints = 52) {
  if (!series || series.length === 0) return [];
  if (series.length <= targetPoints) return series;
  const step = Math.ceil(series.length / targetPoints);
  const sampled = series.filter((_, i) => i % step === 0);
  // Always include last point
  if (sampled[sampled.length - 1] !== series[series.length - 1]) {
    sampled.push(series[series.length - 1]);
  }
  return sampled;
}

// Format date label: show month abbreviation
function fmtDateLabel(dateStr) {
  if (!dateStr) return '';
  const d = new Date(dateStr);
  return d.toLocaleDateString('en-IN', { month: 'short', day: 'numeric' });
}

// ── Toast ─────────────────────────────────────────────────────────────────────
function Toast({ toast }) {
  if (!toast) return null;
  const isSuccess = toast.type === 'success';
  return (
    <AnimatePresence>
      <motion.div
        key={toast.id}
        initial={{ opacity: 0, y: -20, scale: 0.95 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        exit={{ opacity: 0, y: -20 }}
        className={`fixed top-6 right-6 z-50 flex items-start gap-3 px-5 py-4 rounded-2xl shadow-2xl border max-w-sm ${
          isSuccess
            ? 'bg-slate-900 border-emerald-500/30 text-slate-200'
            : 'bg-slate-900 border-red-500/30 text-slate-200'
        }`}
      >
        {isSuccess
          ? <CheckCircle className="w-5 h-5 text-emerald-400 flex-shrink-0 mt-0.5" />
          : <AlertCircle className="w-5 h-5 text-red-400 flex-shrink-0 mt-0.5" />}
        <div>
          <p className="text-sm font-semibold">{toast.title}</p>
          <p className="text-xs text-slate-400 mt-0.5">{toast.message}</p>
        </div>
      </motion.div>
    </AnimatePresence>
  );
}

// ── Main ──────────────────────────────────────────────────────────────────────
export default function Dashboard() {
  const {
    portfolioId, portfolioValue, overallReturn, overallReturnPercent,
    holdings, analyticsData, optimizationData,
    setAnalytics, setOptimization,
  } = useStore();
  const navigate = useNavigate();

  const [analysing, setAnalysing]     = useState(false);
  const [toast, setToast]             = useState(null);
  const [historySeries, setHistory]   = useState([]);
  const [historyLoading, setHLoading] = useState(false);

  const showToast = (type, title, message) => {
    const id = Date.now();
    setToast({ id, type, title, message });
    setTimeout(() => setToast(null), 5000);
  };

  // Fetch real price-history time-series once portfolio is known.
  // Guards against backend being offline on project reopen — only fires
  // after the health check succeeds, so no ECONNREFUSED noise on startup.
  useEffect(() => {
    if (!portfolioId) return;
    let cancelled = false;
    let retryTimer;

    const attemptFetch = () => {
      setHLoading(true);
      fetch('/api/v1/health', { signal: AbortSignal.timeout(2000) })
        .then((r) => {
          if (!r.ok) throw new Error('not ready');
          return fetch(`/api/v1/portfolio/${portfolioId}/history`);
        })
        .then((r) => r.ok ? r.json() : null)
        .then((data) => {
          if (!cancelled && data?.series) setHistory(data.series);
        })
        .catch(() => {
          if (!cancelled) retryTimer = setTimeout(attemptFetch, 5000);
        })
        .finally(() => { if (!cancelled) setHLoading(false); });
    };

    attemptFetch();
    return () => { cancelled = true; clearTimeout(retryTimer); };
  }, [portfolioId]);

  // ── Run full analysis pipeline ─────────────────────────────────────────────
  const runAnalysis = async () => {
    if (!portfolioId) {
      showToast('error', 'No Portfolio', 'Upload holdings first before running analysis.');
      return;
    }
    setAnalysing(true);
    try {
      const res = await fetch(`/api/v1/analyse/${portfolioId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ objective: 'max_sharpe', force_advisory: true }),
      });
      if (!res.ok) {
        const e = await res.json().catch(() => ({}));
        throw new Error(e.detail || `Error ${res.status}`);
      }
      const data = await res.json();
      if (data.analytics) setAnalytics(data.analytics);
      if (data.optimization) setOptimization(data.optimization);

      const model = data.optimization?.model?.replace(/_/g, ' ') || 'Markowitz';
      showToast(
        'success',
        'Analysis Complete',
        `${model.charAt(0).toUpperCase() + model.slice(1)} optimization done.${
          data.advisory_triggered ? ' Advisory generating via WebSocket…' : ''
        }`
      );
    } catch (err) {
      showToast('error', 'Analysis Failed', err.message);
    } finally {
      setAnalysing(false);
    }
  };

  // ── Empty state ─────────────────────────────────────────────────────────────
  if (!holdings || holdings.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-[70vh] text-center">
        <div className="w-20 h-20 bg-slate-900 rounded-full flex items-center justify-center mb-6 shadow-[0_0_30px_rgba(16,185,129,0.1)]">
          <UploadCloud className="w-10 h-10 text-emerald-500" />
        </div>
        <h2 className="text-2xl font-bold text-slate-200 mb-2">No Portfolio Data</h2>
        <p className="text-slate-400 max-w-md mb-8">
          Upload your CSV holdings file to get full analytics, optimization, and AI advisory.
        </p>
        <button
          onClick={() => navigate('/upload')}
          className="bg-emerald-500 hover:bg-emerald-400 text-[#121212] font-bold py-3 px-8 rounded-xl transition-all shadow-[0_0_20px_rgba(16,185,129,0.2)] active:scale-95"
        >
          Upload Holdings
        </button>
      </div>
    );
  }

  // ── Derived data ────────────────────────────────────────────────────────────
  const historical   = downsample(historySeries);
  const maxHist      = Math.max(...historical.map((d) => d.value), portfolioValue ?? 1, 1);
  const yFmt         = makeYFmt(maxHist);
  const pieData      = holdings.map((h) => ({ ...h, pieAlloc: Math.max(parseFloat(h.allocation) || 0, 0.01) }));
  const optWeights   = optimizationData?.weights || {};
  const driftData    = holdings
    .map((h) => ({
      symbol:  h.symbol.split('.')[0],
      current: parseFloat(h.allocation) || 0,
      target:  optWeights[h.symbol] != null ? parseFloat((optWeights[h.symbol] * 100).toFixed(2)) : null,
    }))
    .filter((d) => d.target != null);

  const portfolioBeta = analyticsData?.portfolio_beta;
  const hasOptimization = Boolean(optimizationData && optimizationData.weights);

  return (
    <div className="space-y-6">
      <Toast toast={toast} />

      {/* ── Analyse bar ──────────────────────────────────────────────────── */}
      <div className="flex items-center justify-between bg-slate-900/50 border border-slate-800 rounded-2xl px-6 py-4">
        <div>
          <p className="text-sm font-semibold text-slate-200">Portfolio Analysis</p>
          <p className="text-xs text-slate-500 mt-0.5">
            {hasOptimization
              ? `Last run: ${optimizationData?.model?.replace(/_/g,'  ') || 'Markowitz'} · Sharpe ${optimizationData?.sharpe_ratio?.toFixed(2) ?? '—'}`
              : 'Run analysis to get optimization & AI advisory'}
          </p>
        </div>
        <button
          onClick={runAnalysis}
          disabled={analysing}
          className="flex items-center gap-2 bg-emerald-500 hover:bg-emerald-400 disabled:opacity-60 text-[#0a0a0a] font-bold px-5 py-2.5 rounded-xl text-sm transition-all active:scale-95 shadow-[0_0_16px_rgba(16,185,129,0.25)]"
        >
          {analysing
            ? <><Loader2 className="w-4 h-4 animate-spin" />Analysing…</>
            : <><Zap className="w-4 h-4" />Analyse Portfolio</>}
        </button>
      </div>

      {/* ── KPI Cards ────────────────────────────────────────────────────── */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
        {/* Total Value */}
        <motion.div
          initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.3 }}
          className="bg-slate-900/50 border border-slate-800 rounded-2xl p-6 shadow-xl"
        >
          <div className="flex items-center gap-3 mb-3">
            <div className="w-10 h-10 rounded-full bg-emerald-500/10 flex items-center justify-center text-emerald-400">
              <DollarSign className="w-5 h-5" />
            </div>
            <p className="text-slate-400 text-sm">Total Value</p>
          </div>
          <h2 className="text-3xl font-bold text-white tracking-tight">{formatINR(portfolioValue)}</h2>
        </motion.div>

        {/* Overall Return */}
        <motion.div
          initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.3, delay: 0.08 }}
          className="bg-slate-900/50 border border-slate-800 rounded-2xl p-6 shadow-xl relative overflow-hidden"
        >
          <div className="absolute inset-0 bg-gradient-to-br from-emerald-500/5 to-transparent pointer-events-none" />
          <div className="flex items-center justify-between mb-2 relative z-10">
            <p className="text-slate-400 text-sm">Overall Return</p>
            <span className={`flex items-center gap-1 text-xs font-semibold px-2.5 py-1 rounded-full ${overallReturn >= 0 ? 'text-emerald-400 bg-emerald-500/10' : 'text-red-400 bg-red-500/10'}`}>
              {overallReturn >= 0 ? <TrendingUp className="w-3.5 h-3.5" /> : <TrendingDown className="w-3.5 h-3.5" />}
              {overallReturn >= 0 ? '+' : ''}{(overallReturnPercent ?? 0).toFixed(2)}%
            </span>
          </div>
          <h2 className={`text-2xl font-bold relative z-10 ${overallReturn >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
            {overallReturn >= 0 ? '+' : ''}{formatINR(overallReturn)}
          </h2>
        </motion.div>

        {/* Beta / Optimization */}
        <motion.div
          initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.3, delay: 0.16 }}
          className="bg-slate-900/50 border border-slate-800 rounded-2xl p-6 shadow-xl relative overflow-hidden"
        >
          <div className="absolute inset-0 bg-gradient-to-br from-blue-500/5 to-transparent pointer-events-none" />
          {hasOptimization ? (
            <>
              <div className="flex items-center gap-3 mb-2 relative z-10">
                <div className="w-10 h-10 rounded-full bg-violet-500/10 flex items-center justify-center text-violet-400">
                  <Target className="w-5 h-5" />
                </div>
                <p className="text-slate-400 text-sm">Optimised Sharpe</p>
              </div>
              <h2 className="text-3xl font-bold text-violet-300 tracking-tight relative z-10">
                {optimizationData.sharpe_ratio?.toFixed(2) ?? '—'}
              </h2>
              <p className="text-xs text-slate-500 mt-1 relative z-10 capitalize">
                {optimizationData.model?.replace(/_/g, ' ')} · E[R] {((optimizationData.expected_annual_return ?? 0) * 100).toFixed(1)}%
              </p>
            </>
          ) : (
            <>
              <div className="flex items-center gap-3 mb-2 relative z-10">
                <div className="w-10 h-10 rounded-full bg-blue-500/10 flex items-center justify-center text-blue-400">
                  <Activity className="w-5 h-5" />
                </div>
                <p className="text-slate-400 text-sm">Portfolio Beta</p>
              </div>
              <h2 className="text-3xl font-bold text-blue-300 tracking-tight relative z-10">
                {portfolioBeta?.portfolio_beta != null ? portfolioBeta.portfolio_beta.toFixed(2) : '—'}
              </h2>
              {portfolioBeta?.interpretation && (
                <p className="text-xs text-slate-500 mt-1 relative z-10 line-clamp-2">{portfolioBeta.interpretation}</p>
              )}
            </>
          )}
        </motion.div>
      </div>

      {/* ── Charts row ───────────────────────────────────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        {/* Area chart */}
        <motion.div
          initial={{ opacity: 0, scale: 0.97 }} animate={{ opacity: 1, scale: 1 }} transition={{ duration: 0.4 }}
          className="lg:col-span-2 bg-slate-900/50 border border-slate-800 rounded-2xl p-6 shadow-xl"
        >
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-semibold text-slate-200">
              Portfolio Value — 1 Year
            </h3>
            {historyLoading && (
              <span className="text-[10px] text-slate-500 flex items-center gap-1">
                <Loader2 className="w-3 h-3 animate-spin" /> Loading…
              </span>
            )}
            {!historyLoading && historical.length === 0 && (
              <span className="text-[10px] text-amber-500">Run analysis to load history</span>
            )}
          </div>
          <div className="h-56">
            {historical.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={historical} margin={{ top: 6, right: 6, left: 6, bottom: 0 }}>
                  <defs>
                    <linearGradient id="areaGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%"  stopColor="#10b981" stopOpacity={0.25} />
                      <stop offset="95%" stopColor="#10b981" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
                  <XAxis
                    dataKey="date"
                    stroke="#64748b"
                    tick={{ fill: '#64748b', fontSize: 10 }}
                    axisLine={false}
                    tickLine={false}
                    tickFormatter={fmtDateLabel}
                    interval="preserveStartEnd"
                  />
                  <YAxis stroke="#64748b" tickFormatter={yFmt} axisLine={false} tickLine={false} tick={{ fill: '#64748b', fontSize: 11 }} width={54} />
                  <Tooltip
                    contentStyle={{ backgroundColor: '#0f172a', borderColor: '#1e293b', borderRadius: '8px' }}
                    itemStyle={{ color: '#10b981' }}
                    labelFormatter={(label) => label}
                    formatter={(v) => [formatINR(v), 'Value']}
                  />
                  <Area type="monotone" dataKey="value" stroke="#10b981" strokeWidth={2} fillOpacity={1} fill="url(#areaGrad)" dot={false} />
                </AreaChart>
              </ResponsiveContainer>
            ) : (
              <div className="h-full flex items-center justify-center text-slate-600 text-sm">
                {historyLoading ? 'Loading price history…' : 'No history data yet — run analysis first'}
              </div>
            )}
          </div>
        </motion.div>

        {/* Donut */}
        <motion.div
          initial={{ opacity: 0, scale: 0.97 }} animate={{ opacity: 1, scale: 1 }} transition={{ duration: 0.4, delay: 0.08 }}
          className="bg-slate-900/50 border border-slate-800 rounded-2xl p-6 shadow-xl flex flex-col"
        >
          <h3 className="text-sm font-semibold text-slate-200 mb-2">Allocation</h3>
          <div className="flex-1 min-h-[190px]">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie data={pieData} cx="50%" cy="50%" innerRadius={50} outerRadius={78} paddingAngle={3} dataKey="pieAlloc" stroke="none">
                  {pieData.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
                </Pie>
                <Tooltip
                  contentStyle={{ backgroundColor: '#0f172a', borderColor: '#1e293b', borderRadius: '8px', color: '#fff' }}
                  formatter={(v, n, p) => [`${parseFloat(p.payload.allocation).toFixed(2)}%`, p.payload.symbol]}
                />
              </PieChart>
            </ResponsiveContainer>
          </div>
          <div className="grid grid-cols-2 gap-1 mt-1">
            {holdings.map((h, i) => (
              <div key={h.symbol} className="flex items-center gap-1.5 text-xs text-slate-400">
                <div className="w-2 h-2 rounded-full flex-shrink-0" style={{ backgroundColor: COLORS[i % COLORS.length] }} />
                <span className="truncate">{h.symbol.split('.')[0]}</span>
              </div>
            ))}
          </div>
        </motion.div>
      </div>

      {/* ── Drift chart (only when optimization data exists) ───────────────── */}
      {driftData.length > 0 && (
        <motion.div
          initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4 }}
          className="bg-slate-900/50 border border-slate-800 rounded-2xl p-6 shadow-xl"
        >
          <div className="flex items-center gap-2 mb-1">
            <Target className="w-4 h-4 text-amber-400" />
            <h3 className="text-sm font-semibold text-slate-200">Portfolio Drift — Current vs Target</h3>
          </div>
          <p className="text-xs text-slate-500 mb-4">How far each position is from the optimized target weight.</p>
          <div className="h-52">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={driftData} margin={{ top: 4, right: 8, left: -12, bottom: 4 }} barGap={4} barSize={14}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
                <XAxis dataKey="symbol" stroke="#64748b" tick={{ fill: '#64748b', fontSize: 11 }} axisLine={false} tickLine={false} />
                <YAxis stroke="#64748b" tick={{ fill: '#64748b', fontSize: 11 }} axisLine={false} tickLine={false} tickFormatter={(v) => `${v}%`} width={36} />
                <Tooltip
                  contentStyle={{ backgroundColor: '#0f172a', borderColor: '#1e293b', borderRadius: '8px' }}
                  formatter={(v, name) => [`${v?.toFixed(2)}%`, name === 'current' ? 'Current' : 'Target']}
                />
                <Legend formatter={(v) => v === 'current' ? 'Current Weight' : 'Target Weight'} wrapperStyle={{ fontSize: '11px', color: '#94a3b8' }} />
                <Bar dataKey="current" fill="#10b981" radius={[3, 3, 0, 0]} name="current" />
                <Bar dataKey="target"  fill="#3b82f6" radius={[3, 3, 0, 0]} name="target" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </motion.div>
      )}

      {/* ── What-If Scenario Simulator ───────────────────────────────────── */}
      {hasOptimization && (
        <ScenarioSimulator
          analyticsData={analyticsData}
          optimizationData={optimizationData}
        />
      )}

      {/* ── Holdings table ───────────────────────────────────────────────── */}
      <motion.div
        initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4, delay: 0.1 }}
        className="bg-slate-900/50 border border-slate-800 rounded-2xl overflow-hidden shadow-xl"
      >
        <div className="p-6 border-b border-slate-800 flex justify-between items-center">
          <h3 className="text-sm font-semibold text-slate-200">Holdings</h3>
          <span className="text-xs text-slate-500">{holdings.length} positions</span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm text-slate-400">
            <thead className="text-xs uppercase bg-slate-800/30 text-slate-500 border-b border-slate-800">
              <tr>
                <th className="px-6 py-4 font-medium">Symbol</th>
                <th className="px-6 py-4 font-medium text-right">Avg Buy</th>
                <th className="px-6 py-4 font-medium text-right">Current</th>
                <th className="px-6 py-4 font-medium text-right">Value</th>
                <th className="px-6 py-4 font-medium text-right">Weight</th>
                <th className="px-6 py-4 font-medium text-right">P&amp;L</th>
                <th className="px-6 py-4 font-medium text-right">Return %</th>
              </tr>
            </thead>
            <tbody>
              {holdings.map((h) => {
                const ret = h?.return ?? 0;
                const pos = ret >= 0;
                return (
                  <tr key={h.id} className="border-b border-slate-800/50 hover:bg-slate-800/20 transition-colors">
                    <td className="px-6 py-4 font-medium text-slate-200">
                      <span className="bg-slate-800 px-2 py-0.5 rounded text-xs">{h.symbol}</span>
                    </td>
                    <td className="px-6 py-4 text-right tabular-nums">{h.avgBuyPrice ? formatINR(h.avgBuyPrice) : '—'}</td>
                    <td className="px-6 py-4 text-right tabular-nums text-slate-200">{h.currentPrice ? formatINR(h.currentPrice) : '—'}</td>
                    <td className="px-6 py-4 text-right font-medium text-slate-200 tabular-nums">{h.value ? formatINR(h.value) : '—'}</td>
                    <td className="px-6 py-4 text-right tabular-nums">{(h.allocation ?? 0).toFixed(2)}%</td>
                    <td className={`px-6 py-4 text-right font-medium tabular-nums ${pos ? 'text-emerald-400' : 'text-red-400'}`}>
                      {pos ? '+' : ''}{formatINR(h.absoluteReturnInr ?? 0)}
                    </td>
                    <td className="px-6 py-4 text-right">
                      <span className={`inline-flex items-center gap-1 text-xs font-semibold px-2 py-0.5 rounded-full ${pos ? 'text-emerald-400 bg-emerald-500/10' : 'text-red-400 bg-red-500/10'}`}>
                        {pos ? <TrendingUp className="w-3 h-3" /> : <TrendingDown className="w-3 h-3" />}
                        {pos ? '+' : ''}{ret.toFixed(2)}%
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </motion.div>

    </div>
  );
}
