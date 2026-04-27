/**
 * ScenarioSimulator.jsx
 *
 * Phase 3 — "What-If" Scenario Simulator
 *
 * Reads analyticsData + optimizationData from the Zustand store and renders
 * a side-by-side risk comparison card with:
 *   • Current vs Optimised volatility / Sharpe / E[R] panels
 *   • Recharts BarChart for visual risk delta
 *   • Dynamic insight tooltip (Lightbulb) quantifying the benefit
 *
 * No backend call required — all data is already in store after "Analyse Portfolio".
 */
import { motion } from 'framer-motion';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Cell,
} from 'recharts';
import { Lightbulb, TrendingDown, TrendingUp, ShieldCheck, Zap } from 'lucide-react';

// ── Helpers ────────────────────────────────────────────────────────────────────

const pct = (v) => (v != null ? `${(v * 100).toFixed(1)}%` : '—');
const num = (v, dp = 2) => (v != null ? v.toFixed(dp) : '—');

function MetricPill({ label, value, sub, color }) {
  const colorMap = {
    red:    'bg-red-500/10 border-red-500/20 text-red-400',
    emerald:'bg-emerald-500/10 border-emerald-500/20 text-emerald-400',
    blue:   'bg-blue-500/10 border-blue-500/20 text-blue-400',
    amber:  'bg-amber-500/10 border-amber-500/20 text-amber-400',
  };
  return (
    <div className={`rounded-xl border px-4 py-3 flex flex-col gap-0.5 ${colorMap[color] || colorMap.blue}`}>
      <span className="text-[10px] uppercase tracking-widest font-semibold opacity-60">{label}</span>
      <span className="text-2xl font-bold tabular-nums">{value}</span>
      {sub && <span className="text-[11px] opacity-50">{sub}</span>}
    </div>
  );
}

// ── Custom chart tooltip ───────────────────────────────────────────────────────

function ChartTooltip({ active, payload }) {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;
  return (
    <div className="bg-slate-900 border border-slate-700 rounded-xl px-3 py-2.5 text-xs shadow-xl">
      <p className="font-semibold text-slate-200 mb-1">{d.name}</p>
      <p className="text-slate-400">Volatility: <span className="text-slate-200 font-semibold">{pct(payload[0].value / 100)}</span></p>
    </div>
  );
}

// ── Main component ─────────────────────────────────────────────────────────────

export default function ScenarioSimulator({ analyticsData, optimizationData }) {
  if (!analyticsData || !optimizationData) return null;

  const currentVol  = analyticsData?.rolling_volatility_30d
    ? Object.values(analyticsData.rolling_volatility_30d).reduce((a, b) => a + b, 0) /
      Math.max(Object.keys(analyticsData.rolling_volatility_30d).length, 1)
    : null;

  const optVol      = optimizationData?.annual_volatility ?? null;
  const optReturn   = optimizationData?.expected_annual_return ?? null;
  const optSharpe   = optimizationData?.sharpe_ratio ?? null;
  const engine      = (optimizationData?.model ?? 'markowitz').replace(/_/g, ' ');
  const isDoNotTrade = optimizationData?.do_not_trade === true;

  // Derive "current" Sharpe estimate if not in analytics
  const currentSharpe = analyticsData?.portfolio_beta?.portfolio_beta != null
    ? null  // we don't have current Sharpe in analytics — show only opt Sharpe
    : null;

  // Chart data — two bars
  const barData = [
    { name: 'Current Risk',   value: currentVol != null ? parseFloat((currentVol * 100).toFixed(2)) : null, fill: '#ef4444' },
    { name: 'Optimised Risk', value: optVol     != null ? parseFloat((optVol * 100).toFixed(2)) : null,     fill: '#10b981' },
  ].filter((d) => d.value != null);

  // Dynamic insight text
  const volDeltaPct = (currentVol != null && optVol != null)
    ? ((currentVol - optVol) * 100).toFixed(1)
    : null;
  const saving = (analyticsData?.total_portfolio_value && volDeltaPct)
    ? Math.round(analyticsData.total_portfolio_value * (currentVol - optVol) * 0.3)
    : null;

  let insightText = null;
  if (isDoNotTrade) {
    insightText =
      "Your portfolio is already well-optimised. The AI engine found no rebalancing scenario that improves the Sharpe ratio by more than the transaction cost threshold — no action needed.";
  } else if (volDeltaPct != null && parseFloat(volDeltaPct) > 0) {
    insightText = `By executing this rebalance, you reduce your portfolio's annualised volatility by ~${volDeltaPct}%` +
      (saving ? ` — potentially preserving ₹${saving.toLocaleString('en-IN')} in a market correction.` : '.');
  } else if (volDeltaPct != null && parseFloat(volDeltaPct) <= 0) {
    insightText = `The optimised allocation accepts slightly higher volatility (+${Math.abs(volDeltaPct)}%) in exchange for a meaningfully higher expected Sharpe ratio of ${num(optSharpe)}.`;
  } else {
    insightText = "Run a full portfolio analysis to unlock the scenario comparison.";
  }

  const engineLabel = engine.charAt(0).toUpperCase() + engine.slice(1);

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4 }}
      className="bg-slate-900/50 border border-slate-800 rounded-2xl p-6 shadow-xl space-y-5"
    >
      {/* Header */}
      <div className="flex items-center gap-3">
        <div className="w-9 h-9 rounded-xl bg-violet-500/10 border border-violet-500/20 flex items-center justify-center">
          <Zap className="w-4 h-4 text-violet-400" />
        </div>
        <div>
          <h3 className="text-sm font-bold text-slate-200">What-If Scenario Simulator</h3>
          <p className="text-[11px] text-slate-500 mt-0.5">
            {engineLabel} engine · Compare your current allocation against the AI-optimised target
          </p>
        </div>
        {isDoNotTrade && (
          <div className="ml-auto flex items-center gap-1.5 bg-emerald-500/10 border border-emerald-500/20 rounded-full px-3 py-1">
            <ShieldCheck className="w-3.5 h-3.5 text-emerald-400" />
            <span className="text-[11px] text-emerald-300 font-semibold">Already Optimal</span>
          </div>
        )}
      </div>

      {/* Side-by-side panels */}
      <div className="grid grid-cols-2 gap-4">
        {/* LEFT — Current */}
        <div className="rounded-2xl bg-red-500/5 border border-red-500/15 p-4 space-y-3">
          <div className="flex items-center gap-2 mb-1">
            <TrendingDown className="w-4 h-4 text-red-400" />
            <span className="text-xs font-semibold text-red-300 uppercase tracking-wider">Current Portfolio</span>
          </div>
          <MetricPill
            label="30d Avg Volatility"
            value={currentVol != null ? pct(currentVol) : '—'}
            sub="avg across assets (annualised)"
            color="red"
          />
          <div className="text-xs text-slate-500 space-y-1 pt-1">
            <p>Sharpe ratio: <span className="text-slate-300">—</span></p>
            <p>E[R] (annualised): <span className="text-slate-300">—</span></p>
          </div>
        </div>

        {/* RIGHT — Optimised */}
        <div className="rounded-2xl bg-emerald-500/5 border border-emerald-500/15 p-4 space-y-3">
          <div className="flex items-center gap-2 mb-1">
            <TrendingUp className="w-4 h-4 text-emerald-400" />
            <span className="text-xs font-semibold text-emerald-300 uppercase tracking-wider">Optimised Target</span>
          </div>
          <MetricPill
            label="Annual Volatility"
            value={optVol != null ? pct(optVol) : '—'}
            sub={engineLabel}
            color="emerald"
          />
          <div className="text-xs text-slate-500 space-y-1 pt-1">
            <p>Sharpe ratio: <span className="text-emerald-300 font-semibold">{num(optSharpe)}</span></p>
            <p>E[R] (annualised): <span className="text-emerald-300 font-semibold">{pct(optReturn)}</span></p>
          </div>
        </div>
      </div>

      {/* Bar chart */}
      {barData.length >= 2 && (
        <div className="h-44">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={barData} margin={{ top: 4, right: 8, left: -16, bottom: 4 }} barSize={48}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
              <XAxis
                dataKey="name"
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
                width={36}
              />
              <Tooltip content={<ChartTooltip />} />
              <Bar dataKey="value" radius={[6, 6, 0, 0]}>
                {barData.map((d, i) => (
                  <Cell key={i} fill={d.fill} fillOpacity={0.85} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Insight tooltip */}
      {insightText && (
        <div className="flex items-start gap-3 bg-amber-500/5 border border-amber-500/15 rounded-xl px-4 py-3.5">
          <Lightbulb className="w-4 h-4 text-amber-400 flex-shrink-0 mt-0.5" />
          <p className="text-xs text-slate-300 leading-relaxed">{insightText}</p>
        </div>
      )}
    </motion.div>
  );
}
