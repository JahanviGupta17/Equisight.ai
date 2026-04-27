import { useState } from 'react';
import { useStore } from '../../store/useStore';
import { motion, AnimatePresence } from 'framer-motion';
import {
  AlertTriangle, ShieldCheck, ArrowRight, X, Cpu, Search,
  BookOpen, Sparkles, TrendingUp, TrendingDown, ExternalLink,
  ChevronRight, ArrowUpRight, ArrowDownRight, Minus,
} from 'lucide-react';

// ─── Strip any markdown Gemini occasionally outputs ──────────────────────────
function stripMarkdown(text = '') {
  return (text || '')
    .replace(/^#{1,6}\s+/gm, '')
    .replace(/\*\*(.*?)\*\*/g, '$1')
    .replace(/\*(.*?)\*/g, '$1')
    .replace(/__(.*?)__/g, '$1')
    .replace(/_(.*?)_/g, '$1')
    .replace(/^[\-\*]\s+/gm, '')
    .replace(/^\d+\.\s+/gm, '')
    .replace(/`{1,3}([^`]*)`{1,3}/g, '$1')
    .replace(/---+/g, '')
    .trim();
}

// ─── Progress card (while advisory is generating) ───────────────────────────

const STEP_META = {
  scanning:   { icon: Search,        label: 'Scanning market data',      color: 'text-blue-400',    bg: 'bg-blue-500/10'    },
  retrieving: { icon: BookOpen,      label: 'Retrieving news context',   color: 'text-violet-400',  bg: 'bg-violet-500/10'  },
  thinking:   { icon: Cpu,           label: 'AI advisor is thinking',    color: 'text-amber-400',   bg: 'bg-amber-500/10'   },
  saving:     { icon: Sparkles,      label: 'Finalising recommendation', color: 'text-emerald-400', bg: 'bg-emerald-500/10' },
  error:      { icon: AlertTriangle, label: 'Something went wrong',      color: 'text-red-400',     bg: 'bg-red-500/10'     },
};
const STEPS_ORDER = ['scanning', 'retrieving', 'thinking', 'saving'];

function AdvisoryProgressCard({ progress }) {
  const currentIdx = STEPS_ORDER.indexOf(progress.step);
  const meta = STEP_META[progress.step] || STEP_META.thinking;
  const Icon = meta.icon;

  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, scale: 0.97 }}
      className="bg-[#1a1a1a] border border-emerald-500/20 rounded-2xl overflow-hidden shadow-[0_0_40px_rgba(16,185,129,0.05)]"
    >
      <div className="bg-gradient-to-r from-emerald-500/10 to-transparent p-6 border-b border-slate-800 flex items-center gap-4">
        <div className={`w-12 h-12 rounded-full ${meta.bg} flex items-center justify-center`}>
          <Icon className={`w-6 h-6 ${meta.color} ${progress.step !== 'error' ? 'animate-pulse' : ''}`} />
        </div>
        <div>
          <h2 className="text-lg font-bold text-white">Advisory Engine Running</h2>
          <p className={`text-sm font-medium ${meta.color}`}>{progress.message}</p>
        </div>
      </div>
      <div className="px-6 py-5">
        <div className="flex items-center gap-2">
          {STEPS_ORDER.map((step, idx) => {
            const done    = idx < currentIdx;
            const active  = idx === currentIdx;
            const pending = idx > currentIdx;
            const sm = STEP_META[step];
            const StepIcon = sm.icon;
            return (
              <div key={step} className="flex items-center gap-2 flex-1 last:flex-none">
                <div className={`flex items-center gap-2 ${pending ? 'opacity-30' : ''}`}>
                  <div className={`w-8 h-8 rounded-full flex items-center justify-center transition-all
                    ${done   ? 'bg-emerald-500/20 text-emerald-400' : ''}
                    ${active ? `${sm.bg} ${sm.color}` : ''}
                    ${pending ? 'bg-slate-800 text-slate-600' : ''}
                  `}>
                    {done
                      ? <ShieldCheck className="w-4 h-4 text-emerald-400" />
                      : <StepIcon className={`w-4 h-4 ${active ? 'animate-pulse' : ''}`} />
                    }
                  </div>
                  <span className={`text-xs font-medium hidden sm:block ${active ? 'text-slate-200' : 'text-slate-500'}`}>
                    {sm.label}
                  </span>
                </div>
                {idx < STEPS_ORDER.length - 1 && (
                  <div className={`flex-1 h-px mx-1 ${done ? 'bg-emerald-500/40' : 'bg-slate-800'}`} />
                )}
              </div>
            );
          })}
        </div>
        <p className="text-xs text-slate-500 mt-4">
          This usually takes 15–30 seconds. Your advisory will appear here automatically.
        </p>
      </div>
    </motion.div>
  );
}

// ─── Weight change row ───────────────────────────────────────────────────────

function WeightRow({ symbol, current, proposed }) {
  const currentPct  = current  != null ? +(current  * 100).toFixed(1) : null;
  const proposedPct = proposed != null ? +(proposed * 100).toFixed(1) : null;
  const diff = (proposedPct ?? 0) - (currentPct ?? 0);
  const isNew     = current  == null;
  const isRemoved = proposed == null;

  return (
    <div className="flex items-center gap-4 py-3 border-b border-slate-800/60 last:border-0">
      <span className="w-28 text-sm font-mono font-semibold text-slate-200 flex-shrink-0">{symbol}</span>

      {/* current bar */}
      <div className="flex-1">
        <div className="flex items-center justify-between mb-1">
          <span className="text-[11px] text-slate-500">Now</span>
          <span className="text-[11px] text-slate-400">{currentPct != null ? `${currentPct}%` : '—'}</span>
        </div>
        <div className="h-1.5 bg-slate-800 rounded-full overflow-hidden">
          <div className="h-full bg-slate-600 rounded-full" style={{ width: `${currentPct ?? 0}%` }} />
        </div>
      </div>

      {/* arrow */}
      <div className="flex-shrink-0">
        {isNew     ? <ArrowUpRight  className="w-4 h-4 text-emerald-400" /> :
         isRemoved ? <ArrowDownRight className="w-4 h-4 text-red-400" />    :
         diff > 0  ? <TrendingUp    className="w-4 h-4 text-emerald-400" /> :
         diff < 0  ? <TrendingDown  className="w-4 h-4 text-red-400" />     :
                     <Minus         className="w-4 h-4 text-slate-500" />   }
      </div>

      {/* proposed bar */}
      <div className="flex-1">
        <div className="flex items-center justify-between mb-1">
          <span className="text-[11px] text-slate-500">After</span>
          <span className={`text-[11px] font-semibold ${
            isRemoved ? 'text-red-400' :
            diff > 0  ? 'text-emerald-400' :
            diff < 0  ? 'text-red-400' : 'text-slate-400'
          }`}>{proposedPct != null ? `${proposedPct}%` : 'Sell'}</span>
        </div>
        <div className="h-1.5 bg-slate-800 rounded-full overflow-hidden">
          <div
            className={`h-full rounded-full ${isRemoved ? 'bg-red-500/50' : diff > 0 ? 'bg-emerald-500' : diff < 0 ? 'bg-red-500' : 'bg-slate-600'}`}
            style={{ width: `${proposedPct ?? 0}%` }}
          />
        </div>
      </div>

      {/* delta badge */}
      <div className="w-16 text-right flex-shrink-0">
        {!isNew && !isRemoved && (
          <span className={`text-xs font-bold ${diff > 0 ? 'text-emerald-400' : diff < 0 ? 'text-red-400' : 'text-slate-500'}`}>
            {diff > 0 ? `+${diff.toFixed(1)}` : diff.toFixed(1)}%
          </span>
        )}
        {isNew     && <span className="text-xs font-bold text-emerald-400">New</span>}
        {isRemoved && <span className="text-xs font-bold text-red-400">Exit</span>}
      </div>
    </div>
  );
}

// ─── Detail Drawer ───────────────────────────────────────────────────────────

function RebalanceDrawer({ alert, currentWeights, onConfirm, onClose }) {
  const proposed  = alert.proposedWeights || {};
  const allAssets = Array.from(new Set([...Object.keys(currentWeights), ...Object.keys(proposed)]));

  // Split scenario text on "---" if LLM returned both sections together
  const scenarioParts  = (alert.scenario?.details || '').split(/---+/).map((s) => s.trim()).filter(Boolean);
  const ifIgnored      = stripMarkdown(scenarioParts[1] || scenarioParts[0] || alert.scenario?.details || '');
  const ifRebalanced   = 'Risk-aligned portfolio. Each asset within its target band, reducing concentration risk and unintended sector exposure.';

  const sources = (alert.ragSources || []).filter(Boolean);

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 z-50 flex items-end sm:items-center justify-center p-4 bg-black/70 backdrop-blur-sm"
      onClick={onClose}
    >
      <motion.div
        initial={{ opacity: 0, y: 40 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: 40 }}
        transition={{ type: 'spring', damping: 28, stiffness: 280 }}
        className="w-full max-w-2xl max-h-[90vh] bg-[#0f1117] border border-slate-800 rounded-2xl shadow-2xl flex flex-col overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b border-slate-800">
          <div>
            <h2 className="text-xl font-bold text-white">Rebalancing Details</h2>
            <p className="text-sm text-slate-400 mt-0.5">Exactly what will change if you accept</p>
          </div>
          <button onClick={onClose} className="p-2 rounded-lg text-slate-500 hover:text-slate-200 hover:bg-slate-800 transition-colors">
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Scrollable body */}
        <div className="flex-1 overflow-y-auto p-6 space-y-8">

          {/* Weight changes */}
          <section>
            <h3 className="text-xs font-bold text-slate-400 uppercase tracking-widest mb-4">Portfolio Weight Changes</h3>
            <div className="bg-slate-900/60 rounded-xl p-4 border border-slate-800">
              {allAssets.length === 0
                ? <p className="text-sm text-slate-500 text-center py-4">No proposed weight data available.</p>
                : allAssets.map((sym) => (
                    <WeightRow
                      key={sym}
                      symbol={sym}
                      current={currentWeights[sym]}
                      proposed={proposed[sym]}
                    />
                  ))
              }
            </div>
          </section>

          {/* If ignored vs if rebalanced */}
          <section>
            <h3 className="text-xs font-bold text-slate-400 uppercase tracking-widest mb-4">What Happens Next</h3>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div className="bg-[#140c0c] rounded-xl p-4 border border-red-500/20 relative overflow-hidden">
                <div className="absolute top-0 left-0 w-1 h-full bg-red-500" />
                <p className="text-xs font-bold text-red-400 uppercase tracking-wider mb-2">If Ignored</p>
                <p className="text-sm text-slate-300 leading-relaxed">{ifIgnored || 'Portfolio may drift further from target, increasing unintended risk.'}</p>
              </div>
              <div className="bg-[#0a140c] rounded-xl p-4 border border-emerald-500/20 relative overflow-hidden">
                <div className="absolute top-0 left-0 w-1 h-full bg-emerald-500" />
                <p className="text-xs font-bold text-emerald-400 uppercase tracking-wider mb-2">If Rebalanced</p>
                <p className="text-sm text-slate-300 leading-relaxed">{ifRebalanced}</p>
              </div>
            </div>
          </section>

          {/* News sources */}
          {sources.length > 0 && (
            <section>
              <h3 className="text-xs font-bold text-slate-400 uppercase tracking-widest mb-3">Intelligence Sources</h3>
              <div className="space-y-2">
                {sources.map((src, i) => (
                  <a
                    key={i}
                    href={src}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex items-center gap-2 text-sm text-slate-400 hover:text-emerald-400 transition-colors truncate group"
                  >
                    <ExternalLink className="w-3.5 h-3.5 flex-shrink-0 group-hover:text-emerald-400" />
                    <span className="truncate">{src}</span>
                  </a>
                ))}
              </div>
            </section>
          )}
        </div>

        {/* Footer */}
        <div className="p-6 border-t border-slate-800 flex items-center gap-3">
          <button
            onClick={onConfirm}
            className="flex-1 bg-emerald-500 hover:bg-emerald-400 text-slate-900 font-bold py-3 px-6 rounded-xl transition-all shadow-[0_0_20px_rgba(16,185,129,0.3)] hover:shadow-[0_0_30px_rgba(16,185,129,0.5)] active:scale-95 flex items-center justify-center gap-2"
          >
            Confirm Rebalance <ArrowRight className="w-4 h-4" />
          </button>
          <button
            onClick={onClose}
            className="px-6 py-3 rounded-xl border border-slate-700 text-slate-300 font-medium hover:bg-slate-800 transition-colors"
          >
            Cancel
          </button>
        </div>
      </motion.div>
    </motion.div>
  );
}

// ─── Alert card (compact summary) ───────────────────────────────────────────

function AlertCard({ alert, onAccept, onPostpone, onReject, onViewDetails }) {
  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.95, y: 20 }}
      animate={{ opacity: 1, scale: 1, y: 0 }}
      exit={{ opacity: 0, scale: 0.95, filter: 'blur(4px)' }}
      transition={{ duration: 0.4, type: 'spring', bounce: 0.3 }}
      className="bg-[#1a1a1a] border border-red-500/20 rounded-2xl overflow-hidden shadow-[0_0_40px_rgba(220,38,38,0.05)]"
    >
      {/* Header */}
      <div className="bg-gradient-to-r from-red-500/10 to-transparent p-5 border-b border-slate-800 flex justify-between items-start">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-full bg-red-500/20 flex items-center justify-center text-red-400">
            <AlertTriangle className="w-5 h-5" />
          </div>
          <div>
            <h2 className="text-base font-bold text-white">{alert.title}</h2>
            <p className="text-xs text-red-400/80 font-medium mt-0.5">Portfolio drift detected</p>
          </div>
        </div>
        <button
          onClick={onReject}
          className="text-slate-500 hover:text-slate-300 transition-colors p-1.5 rounded-full hover:bg-slate-800"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      {/* Explanation */}
      <div className="px-5 pt-4 pb-2">
        <p className="text-sm text-slate-300 leading-relaxed">{stripMarkdown(alert.explanation)}</p>
      </div>

      {/* Actions */}
      <div className="px-5 pb-5 pt-4 flex items-center gap-3">
        <button
          onClick={onViewDetails}
          className="flex-1 flex items-center justify-center gap-2 bg-emerald-500 hover:bg-emerald-400 text-slate-900 font-bold py-2.5 px-4 rounded-xl transition-all shadow-[0_0_20px_rgba(16,185,129,0.2)] hover:shadow-[0_0_28px_rgba(16,185,129,0.4)] active:scale-95 text-sm"
        >
          Accept & Rebalance <ChevronRight className="w-4 h-4" />
        </button>
        <button
          onClick={onPostpone}
          className="px-4 py-2.5 rounded-xl border border-slate-700 text-slate-300 text-sm font-medium hover:bg-slate-800 transition-colors"
        >
          Postpone
        </button>
        <button
          onClick={onReject}
          className="px-4 py-2.5 rounded-xl text-slate-500 text-sm font-medium hover:text-slate-300 transition-colors"
        >
          Reject
        </button>
      </div>
    </motion.div>
  );
}

// ─── Page ────────────────────────────────────────────────────────────────────

export default function Alerts() {
  const { alerts, setAlertStatus, advisoryProgress, analyticsData } = useStore();
  const [drawerAlert, setDrawerAlert] = useState(null);

  const activeAlerts = alerts.filter((a) => a.status === 'pending');

  // Build current weights from analytics store so the drawer can diff them
  const currentWeights = analyticsData?.current_weights || {};

  const handleConfirmRebalance = (alertId) => {
    setAlertStatus(alertId, 'accepted');
    setDrawerAlert(null);
  };

  if (!advisoryProgress && activeAlerts.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-[60vh] text-slate-500">
        <ShieldCheck className="w-16 h-16 mb-4 text-emerald-500/50" />
        <h2 className="text-xl font-medium text-slate-300">Your Portfolio is Optimized</h2>
        <p className="text-sm mt-2">No active drift alerts detected.</p>
      </div>
    );
  }

  return (
    <>
      <div className="max-w-3xl mx-auto space-y-5">
        <AnimatePresence mode="popLayout">
          {advisoryProgress && (
            <AdvisoryProgressCard key="progress" progress={advisoryProgress} />
          )}

          {activeAlerts.map((alert) => (
            <AlertCard
              key={alert.id}
              alert={alert}
              onViewDetails={() => setDrawerAlert(alert)}
              onPostpone={() => setAlertStatus(alert.id, 'postponed')}
              onReject={() => setAlertStatus(alert.id, 'rejected')}
              onAccept={() => setDrawerAlert(alert)}
            />
          ))}
        </AnimatePresence>
      </div>

      {/* Rebalance detail drawer */}
      <AnimatePresence>
        {drawerAlert && (
          <RebalanceDrawer
            alert={drawerAlert}
            currentWeights={currentWeights}
            onConfirm={() => handleConfirmRebalance(drawerAlert.id)}
            onClose={() => setDrawerAlert(null)}
          />
        )}
      </AnimatePresence>
    </>
  );
}
