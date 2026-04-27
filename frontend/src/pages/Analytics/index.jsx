import { useStore } from '../../store/useStore';
import { motion } from 'framer-motion';
import CountUp from 'react-countup';
import { Toaster, toast } from 'react-hot-toast';
import {
  TrendingUp, Activity, Target, BrainCircuit,
  Search, Zap, Info, Loader2, UploadCloud,
} from 'lucide-react';
import { useEffect, useState, useMemo } from 'react';
import {
  PieChart, Pie, Cell, Tooltip as RechartsTooltip, ResponsiveContainer,
  ScatterChart, Scatter, XAxis, YAxis, CartesianGrid, ZAxis,
  BarChart, Bar, Legend,
} from 'recharts';
import { useNavigate } from 'react-router-dom';

const COLORS = ['#10b981', '#3b82f6', '#8b5cf6', '#f59e0b', '#ef4444', '#14b8a6', '#f97316', '#06b6d4'];

// ─── Custom scatter tooltip ─────────────────────────────────────────────────
const ScatterTooltip = ({ active, payload }) => {
  if (!active || !payload?.length) return null;
  const d = payload[0]?.payload;
  if (!d) return null;
  return (
    <div className="bg-slate-900 border border-slate-700 rounded-xl p-3 text-xs shadow-xl">
      <p className="text-slate-200 font-bold mb-1">{d.name}</p>
      <p className="text-slate-400">Risk (Vol): <span className="text-white">{(d.risk * 100).toFixed(1)}%</span></p>
      <p className="text-slate-400">Return: <span className="text-emerald-400">{d.return.toFixed(2)}%</span></p>
    </div>
  );
};

// ─── Pie legend ─────────────────────────────────────────────────────────────
const PieLegend = ({ data }) => (
  <div className="flex flex-wrap gap-x-3 gap-y-1.5 justify-center mt-3">
    {data.map((d, i) => (
      <div key={d.name} className="flex items-center gap-1.5 text-xs text-slate-400">
        <div className="w-2 h-2 rounded-full flex-shrink-0" style={{ backgroundColor: COLORS[i % COLORS.length] }} />
        <span>{d.name.split('.')[0]}</span>
        <span className="text-slate-500">{d.value.toFixed(1)}%</span>
      </div>
    ))}
  </div>
);

export default function Analytics() {
  const analytics       = useStore((s) => s.analyticsData);
  const optimization    = useStore((s) => s.optimizationData);
  const portfolioId     = useStore((s) => s.portfolioId);
  const setAnalytics    = useStore((s) => s.setAnalytics);
  const setOptimization = useStore((s) => s.setOptimization);
  const [reanalyzing, setReanalyzing] = useState(false);
  // fetchNeeded: true only when there is a portfolioId but genuinely no data at all.
  // We read getState() synchronously so a just-completed wizard's store update is
  // visible immediately — no spurious fetch after preferences save.
  const [fetchNeeded] = useState(() => {
    const s = useStore.getState();
    return Boolean(s.portfolioId && !s.analyticsData && !s.optimizationData);
  });
  const [loading, setLoading] = useState(fetchNeeded);
  const navigate = useNavigate();

  useEffect(() => {
    if (!fetchNeeded) return;
    fetch(`/api/v1/analyse/${portfolioId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ objective: 'max_sharpe', force_advisory: false }),
    })
      .then((r) => r.ok ? r.json() : Promise.reject('Analysis failed'))
      .then((data) => {
        if (data.analytics)    setAnalytics(data.analytics);
        if (data.optimization) setOptimization(data.optimization);
      })
      .catch((err) => toast.error(String(err)))
      .finally(() => setLoading(false));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleReanalyze = async () => {
    if (!portfolioId || reanalyzing) return;
    setReanalyzing(true);
    try {
      const res = await fetch(`/api/v1/analyse/${portfolioId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ objective: 'max_sharpe', force_advisory: true }),
      });
      if (!res.ok) throw new Error('Re-analysis failed.');
      const data = await res.json();
      if (data.analytics)    setAnalytics(data.analytics);
      if (data.optimization) setOptimization(data.optimization);
      toast.success('Portfolio re-analyzed successfully.');
    } catch (err) {
      toast.error(err.message, { duration: 5000 });
    } finally {
      setReanalyzing(false);
    }
  };

  // Engine explanation toast
  useEffect(() => {
    if (optimization?.engine_explanation) {
      toast.custom((t) => (
        <motion.div
          initial={{ opacity: 0, y: -20 }}
          animate={{ opacity: 1, y: 0 }}
          className="flex items-start gap-3 bg-[#1e293b] border border-emerald-500/30 rounded-2xl shadow-2xl p-4 max-w-lg"
        >
          <div className="flex-shrink-0 w-10 h-10 rounded-full bg-emerald-500/10 flex items-center justify-center mt-0.5">
            {optimization.model === 'markowitz'
              ? <Zap className="w-5 h-5 text-emerald-400" />
              : <BrainCircuit className="w-5 h-5 text-emerald-400" />}
          </div>
          <div>
            <p className="text-sm font-bold text-white mb-0.5">Engine Active: {optimization.model?.toUpperCase()}</p>
            <p className="text-xs text-slate-300 leading-relaxed">{optimization.engine_explanation}</p>
          </div>
        </motion.div>
      ), { duration: 8000, position: 'top-center' });
    }
  }, [optimization]);

  // ── Loading state ─────────────────────────────────────────────────────────
  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center h-[60vh] gap-4">
        <Loader2 className="w-10 h-10 text-emerald-400 animate-spin" />
        <p className="text-slate-400 text-sm">Running portfolio analysis…</p>
      </div>
    );
  }

  // ── No portfolio yet ──────────────────────────────────────────────────────
  if (!portfolioId) {
    return (
      <div className="flex flex-col items-center justify-center h-[60vh] text-center gap-4">
        <UploadCloud className="w-16 h-16 text-emerald-500/40" />
        <h2 className="text-xl font-semibold text-slate-300">No Portfolio Found</h2>
        <p className="text-sm text-slate-500 max-w-sm">Upload your holdings first so the optimization engine has data to work with.</p>
        <button
          onClick={() => navigate('/upload')}
          className="mt-2 bg-emerald-500 hover:bg-emerald-400 text-slate-900 font-bold py-2.5 px-7 rounded-xl transition-all"
        >
          Upload Portfolio
        </button>
      </div>
    );
  }

  // ── Has portfolio but no analytics (shouldn't happen after auto-fetch, but safe) ──
  if (!analytics && !optimization) {
    return (
      <div className="flex flex-col items-center justify-center h-[60vh] text-center gap-4">
        <Activity className="w-16 h-16 text-slate-600" />
        <h2 className="text-xl font-semibold text-slate-300">No Analytics Data</h2>
        <p className="text-sm text-slate-500">Click below to run the optimization engine.</p>
        <button
          onClick={handleReanalyze}
          disabled={reanalyzing}
          className="mt-2 flex items-center gap-2 bg-emerald-500 hover:bg-emerald-400 disabled:opacity-50 text-slate-900 font-bold py-2.5 px-7 rounded-xl transition-all"
        >
          {reanalyzing ? <Loader2 className="w-4 h-4 animate-spin" /> : <Search className="w-4 h-4" />}
          Run Analysis
        </button>
      </div>
    );
  }

  // ── Derived data — wrapped in useMemo to keep scatter stable (no Math.random) ──
  const currentWeights   = analytics?.current_weights  || {};
  const optWeights       = optimization?.weights        || {};
  const absoluteReturns  = analytics?.absolute_returns  || {};
  const volMap           = analytics?.rolling_volatility_30d || {};

  // Allocation pie — optimized weights if available, else current
  const weightsForPie = Object.keys(optWeights).length ? optWeights : currentWeights;
  const pieData = Object.entries(weightsForPie)
    .map(([name, w]) => ({ name, value: +(w * 100).toFixed(2) }))
    .filter((d) => d.value > 0)
    .sort((a, b) => b.value - a.value);

  // Drift bar: current vs optimized weights
  const allAssets = Array.from(new Set([...Object.keys(currentWeights), ...Object.keys(optWeights)]));
  const driftData = allAssets.map((sym) => ({
    symbol: sym.split('.')[0],
    current:   +((currentWeights[sym] || 0) * 100).toFixed(2),
    optimized: +((optWeights[sym]     || 0) * 100).toFixed(2),
  })).filter((d) => d.current > 0 || d.optimized > 0);

  // Scatter: risk (30d vol) vs return — stable, no randomness
  const scatterData = Object.keys(absoluteReturns)
    .filter((sym) => volMap[sym] != null)
    .map((sym) => ({
      name:   sym,
      risk:   volMap[sym],                                    // annualised decimal
      return: absoluteReturns[sym]?.percentage_return ?? 0,  // percentage
    }));

  const expectedReturn = optimization?.expected_annual_return
    ? +(optimization.expected_annual_return * 100).toFixed(2)
    : +(analytics?.portfolio_summary?.total_percentage_return ?? 0).toFixed(2);

  const expectedVol = optimization?.annual_volatility
    ? +(optimization.annual_volatility * 100).toFixed(2)
    : +(((volMap?.portfolio_volatility_30d ?? 0)) * 100).toFixed(2);

  const sharpe = +(optimization?.sharpe_ratio ?? 0).toFixed(2);

  const modelLabel = optimization?.model
    ? optimization.model.replace('_', '-').toUpperCase()
    : 'Markowitz';

  return (
    <div className="max-w-7xl mx-auto py-4 space-y-7">
      <Toaster />

      {/* ── Header ── */}
      <div className="flex flex-col sm:flex-row sm:justify-between sm:items-end gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white">Portfolio Analytics</h1>
          <p className="text-slate-400 text-sm mt-1">
            Engine: <span className="text-emerald-400 font-semibold">{modelLabel}</span>
            {optimization?.investor_profile?.time_horizon && (
              <span className="text-slate-500"> · {optimization.investor_profile.time_horizon}</span>
            )}
          </p>
        </div>
        <button
          onClick={handleReanalyze}
          disabled={reanalyzing || !portfolioId}
          className="flex items-center gap-2 bg-emerald-500 hover:bg-emerald-400 disabled:opacity-50 disabled:cursor-not-allowed text-[#0a0a0a] font-bold py-2.5 px-6 rounded-xl shadow-[0_0_20px_rgba(16,185,129,0.3)] transition-all active:scale-95 text-sm"
        >
          {reanalyzing
            ? <><Loader2 className="w-4 h-4 animate-spin" />Analyzing…</>
            : <><Search className="w-4 h-4" />Re-Analyze Portfolio</>}
        </button>
      </div>

      {/* ── KPI cards ── */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
        {[
          {
            label: 'Expected Return',
            value: expectedReturn,
            suffix: '%',
            icon: TrendingUp,
            color: 'emerald',
            tip: 'Annualized return projected by the optimization model.',
          },
          {
            label: 'Portfolio Volatility (Risk)',
            value: expectedVol,
            suffix: '%',
            icon: Activity,
            color: 'blue',
            tip: '30-day annualized volatility of your portfolio.',
          },
          {
            label: 'Sharpe Ratio',
            value: sharpe,
            suffix: '',
            icon: Target,
            color: 'violet',
            tip: 'Risk-adjusted return: higher is better. >1 is good, >2 is excellent.',
          },
        ].map(({ label, value, suffix, icon: Icon, color, tip }, i) => (
          <motion.div
            key={label}
            initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.1 }}
            className={`bg-gradient-to-br from-[#12141c] to-slate-900 border border-slate-800 rounded-2xl p-6 relative overflow-hidden`}
          >
            <div className={`absolute top-0 right-0 w-24 h-24 bg-${color}-500/5 rounded-full blur-3xl -mr-8 -mt-8`} />
            <div className="flex justify-between items-start mb-4 relative z-10">
              <div>
                <div className="flex items-center gap-1.5 mb-1">
                  <p className="text-slate-400 text-xs font-medium">{label}</p>
                  <div className="group relative">
                    <Info className="w-3 h-3 text-slate-600 cursor-help" />
                    <div className="absolute bottom-full mb-1.5 left-1/2 -translate-x-1/2 w-44 p-2 bg-slate-800 text-xs text-slate-300 rounded-lg shadow-xl opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none z-20">
                      {tip}
                    </div>
                  </div>
                </div>
                <h3 className="text-3xl font-bold text-white mt-1">
                  <CountUp end={value} decimals={2} suffix={suffix} duration={2} />
                </h3>
              </div>
              <div className={`w-10 h-10 bg-${color}-500/10 rounded-xl flex items-center justify-center`}>
                <Icon className={`w-5 h-5 text-${color}-400`} />
              </div>
            </div>
          </motion.div>
        ))}
      </div>

      {/* ── Charts row ── */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">

        {/* Allocation Pie */}
        <motion.div
          initial={{ opacity: 0, scale: 0.97 }} animate={{ opacity: 1, scale: 1 }} transition={{ delay: 0.3 }}
          className="bg-[#12141c] border border-slate-800 rounded-2xl p-6"
        >
          <div className="flex items-center gap-2 mb-4">
            <h3 className="text-base font-bold text-white">
              {Object.keys(optWeights).length ? 'Optimized Allocation' : 'Current Allocation'}
            </h3>
            <div className="group relative">
              <Info className="w-4 h-4 text-slate-500 cursor-help" />
              <div className="absolute bottom-full mb-2 left-0 w-52 p-2 bg-slate-800 text-xs text-slate-300 rounded-lg shadow-xl opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none z-10">
                {Object.keys(optWeights).length
                  ? `Target weights from ${modelLabel} optimization.`
                  : 'Current market-value weights of your holdings.'}
              </div>
            </div>
          </div>
          {pieData.length > 0 ? (
            <>
              <div className="h-[240px]">
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie
                      data={pieData}
                      dataKey="value"
                      nameKey="name"
                      cx="50%"
                      cy="50%"
                      innerRadius={70}
                      outerRadius={100}
                      paddingAngle={3}
                      stroke="none"
                    >
                      {pieData.map((_, idx) => (
                        <Cell key={idx} fill={COLORS[idx % COLORS.length]} />
                      ))}
                    </Pie>
                    <RechartsTooltip
                      formatter={(v) => `${v.toFixed(2)}%`}
                      contentStyle={{ backgroundColor: '#1e293b', border: '1px solid #334155', borderRadius: '10px' }}
                      itemStyle={{ color: '#fff' }}
                    />
                  </PieChart>
                </ResponsiveContainer>
              </div>
              <PieLegend data={pieData} />
            </>
          ) : (
            <div className="h-[240px] flex items-center justify-center text-slate-500 text-sm">No weight data available.</div>
          )}
        </motion.div>

        {/* Risk vs Return Scatter */}
        <motion.div
          initial={{ opacity: 0, scale: 0.97 }} animate={{ opacity: 1, scale: 1 }} transition={{ delay: 0.4 }}
          className="bg-[#12141c] border border-slate-800 rounded-2xl p-6"
        >
          <div className="flex items-center gap-2 mb-4">
            <h3 className="text-base font-bold text-white">Risk vs Return</h3>
            <div className="group relative">
              <Info className="w-4 h-4 text-slate-500 cursor-help" />
              <div className="absolute bottom-full mb-2 left-0 w-52 p-2 bg-slate-800 text-xs text-slate-300 rounded-lg shadow-xl opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none z-10">
                30-day annualized volatility (X) vs total return % (Y) per asset.
              </div>
            </div>
          </div>
          {scatterData.length > 0 ? (
            <div className="h-[270px]">
              <ResponsiveContainer width="100%" height="100%">
                <ScatterChart margin={{ top: 10, right: 20, bottom: 30, left: 10 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                  <XAxis
                    type="number"
                    dataKey="risk"
                    name="Risk (Vol)"
                    stroke="#64748b"
                    tick={{ fill: '#64748b', fontSize: 11 }}
                    tickFormatter={(v) => `${(v * 100).toFixed(0)}%`}
                    label={{ value: 'Volatility (Risk)', position: 'insideBottom', offset: -15, fill: '#475569', fontSize: 10 }}
                  />
                  <YAxis
                    type="number"
                    dataKey="return"
                    name="Return %"
                    stroke="#64748b"
                    tick={{ fill: '#64748b', fontSize: 11 }}
                    tickFormatter={(v) => `${v.toFixed(0)}%`}
                    width={42}
                    label={{ value: 'Return %', angle: -90, position: 'insideLeft', offset: 10, fill: '#475569', fontSize: 10 }}
                  />
                  <ZAxis range={[50, 50]} />
                  <RechartsTooltip content={<ScatterTooltip />} />
                  <Scatter data={scatterData} fill="#10b981">
                    {scatterData.map((_, idx) => (
                      <Cell key={idx} fill={COLORS[idx % COLORS.length]} />
                    ))}
                  </Scatter>
                </ScatterChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <div className="h-[270px] flex items-center justify-center text-slate-500 text-sm">
              Volatility data not yet available. Re-analyze to populate.
            </div>
          )}
        </motion.div>
      </div>

      {/* ── Current vs Optimized weight comparison ── */}
      {driftData.length > 0 && (
        <motion.div
          initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.5 }}
          className="bg-[#12141c] border border-slate-800 rounded-2xl p-6"
        >
          <div className="flex items-center gap-2 mb-4">
            <h3 className="text-base font-bold text-white">Current vs Optimized Weights</h3>
            <div className="group relative">
              <Info className="w-4 h-4 text-slate-500 cursor-help" />
              <div className="absolute bottom-full mb-2 left-0 w-56 p-2 bg-slate-800 text-xs text-slate-300 rounded-lg shadow-xl opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none z-10">
                Green = where you are now. Blue = where the engine says you should be.
              </div>
            </div>
          </div>
          <div className="h-[240px]">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={driftData} margin={{ top: 5, right: 10, left: -10, bottom: 5 }} barGap={3} barSize={12}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
                <XAxis
                  dataKey="symbol"
                  stroke="#64748b"
                  tick={{ fill: '#64748b', fontSize: 11 }}
                  axisLine={false}
                  tickLine={false}
                />
                <YAxis
                  stroke="#64748b"
                  tick={{ fill: '#64748b', fontSize: 11 }}
                  axisLine={false}
                  tickLine={false}
                  tickFormatter={(v) => `${v}%`}
                  width={38}
                />
                <RechartsTooltip
                  contentStyle={{ backgroundColor: '#0f172a', borderColor: '#1e293b', borderRadius: '8px' }}
                  formatter={(v, name) => [`${v?.toFixed(2)}%`, name === 'current' ? 'Current' : 'Optimized']}
                />
                <Legend
                  formatter={(v) => v === 'current' ? 'Current Weight' : 'Optimized Weight'}
                  wrapperStyle={{ fontSize: '11px', color: '#94a3b8' }}
                />
                <Bar dataKey="current"   fill="#10b981" radius={[3, 3, 0, 0]} name="current" />
                <Bar dataKey="optimized" fill="#3b82f6" radius={[3, 3, 0, 0]} name="optimized" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </motion.div>
      )}

      {/* ── Per-asset metrics table ── */}
      {Object.keys(absoluteReturns).length > 0 && (
        <motion.div
          initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.6 }}
          className="bg-[#12141c] border border-slate-800 rounded-2xl overflow-hidden"
        >
          <div className="p-5 border-b border-slate-800">
            <h3 className="text-base font-bold text-white">Asset-Level Risk Metrics</h3>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm text-left">
              <thead className="text-xs text-slate-500 uppercase bg-slate-800/30 border-b border-slate-800">
                <tr>
                  <th className="px-5 py-3">Symbol</th>
                  <th className="px-5 py-3 text-right">Current Weight</th>
                  <th className="px-5 py-3 text-right">Optimized Weight</th>
                  <th className="px-5 py-3 text-right">30d Volatility</th>
                  <th className="px-5 py-3 text-right">Max Drawdown</th>
                  <th className="px-5 py-3 text-right">Return %</th>
                </tr>
              </thead>
              <tbody>
                {Object.keys(absoluteReturns).map((sym) => {
                  const r   = absoluteReturns[sym];
                  const vol = volMap[sym];
                  const dd  = analytics?.max_drawdown_pct?.[sym];
                  const cw  = currentWeights[sym];
                  const ow  = optWeights[sym];
                  const ret = r?.percentage_return ?? 0;
                  return (
                    <tr key={sym} className="border-b border-slate-800/50 hover:bg-slate-800/20 transition-colors">
                      <td className="px-5 py-3 font-mono text-xs">
                        <span className="bg-slate-800 px-2 py-1 rounded text-slate-200">{sym}</span>
                      </td>
                      <td className="px-5 py-3 text-right text-slate-300 tabular-nums">
                        {cw != null ? `${(cw * 100).toFixed(2)}%` : '—'}
                      </td>
                      <td className="px-5 py-3 text-right tabular-nums">
                        {ow != null
                          ? <span className="text-blue-400 font-semibold">{(ow * 100).toFixed(2)}%</span>
                          : <span className="text-slate-600">—</span>}
                      </td>
                      <td className="px-5 py-3 text-right tabular-nums text-amber-400">
                        {vol != null ? `${(vol * 100).toFixed(2)}%` : '—'}
                      </td>
                      <td className="px-5 py-3 text-right tabular-nums text-red-400">
                        {dd != null ? `${dd.toFixed(2)}%` : '—'}
                      </td>
                      <td className="px-5 py-3 text-right tabular-nums">
                        <span className={ret >= 0 ? 'text-emerald-400' : 'text-red-400'}>
                          {ret >= 0 ? '+' : ''}{ret.toFixed(2)}%
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </motion.div>
      )}
    </div>
  );
}
