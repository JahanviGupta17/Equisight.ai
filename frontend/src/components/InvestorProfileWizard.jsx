import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useStore } from '../store/useStore';
import {
  Clock, Calendar, CalendarDays,     // time horizon
  ShieldCheck, Scale, Rocket,        // drawdown tolerance
  Wallet, PiggyBank, Lock,           // liquidity needs
  GraduationCap, Briefcase, Cpu,     // experience level
  Grid3x3, SlidersHorizontal, Focus, // diversification
  ChevronRight, ChevronLeft, CheckCircle2, Loader2, X, Info
} from 'lucide-react';

const STEPS = [
  {
    id: 'time_horizon',
    title: 'What is your time horizon?',
    subtitle: 'How long do you plan to keep this money invested?',
    field: 'time_horizon',
    options: [
      {
        value: '1-3 Years', icon: Clock, color: 'blue',
        label: '1-3 Years', tagline: 'Short term',
      },
      {
        value: '4-7 Years', icon: Calendar, color: 'emerald',
        label: '4-7 Years', tagline: 'Medium term',
      },
      {
        value: '8+ Years', icon: CalendarDays, color: 'violet',
        label: '8+ Years', tagline: 'Long term',
      },
    ],
    tooltip: 'Your time horizon determines the length of historical data our engine uses (1y, 3y, or 5y) to calculate market behavior.'
  },
  {
    id: 'drawdown_tolerance',
    title: 'How do you react to market crashes?',
    subtitle: 'Choose your comfort level with temporary losses.',
    field: 'drawdown_tolerance',
    options: [
      {
        value: 'Panic at 5% drop (Protect my capital)', icon: ShieldCheck, color: 'blue',
        label: 'Panic at 5% drop', tagline: 'Protect my capital',
      },
      {
        value: 'Uncomfortable at 15% (Balanced)', icon: Scale, color: 'emerald',
        label: 'Uncomfortable at 15%', tagline: 'Balanced',
      },
      {
        value: 'Can ignore 25%+ crashes (Aggressive)', icon: Rocket, color: 'amber',
        label: 'Can ignore 25%+ crashes', tagline: 'Aggressive',
      },
    ],
    tooltip: 'If you prioritize capital protection, our engine overrides standard models and uses Conditional Value at Risk (CVaR) to mathematically minimize extreme downside.'
  },
  {
    id: 'liquidity_needs',
    title: 'What are your liquidity needs?',
    subtitle: 'How quickly might you need to withdraw cash?',
    field: 'liquidity_needs',
    options: [
      {
        value: 'High (Need cash soon)', icon: Wallet, color: 'emerald',
        label: 'High', tagline: 'Need cash soon',
      },
      {
        value: 'Moderate', icon: PiggyBank, color: 'blue',
        label: 'Moderate', tagline: 'Might need some',
      },
      {
        value: 'Low (Locked away)', icon: Lock, color: 'violet',
        label: 'Low', tagline: 'Locked away for years',
      },
    ],
    tooltip: 'High liquidity needs signal our algorithm to penalize highly volatile or difficult-to-sell assets.'
  },
  {
    id: 'experience_level',
    title: 'What is your investment experience?',
    subtitle: 'How involved do you want to be in the strategy?',
    field: 'experience_level',
    options: [
      {
        value: 'Beginner (Do it for me)', icon: GraduationCap, color: 'blue',
        label: 'Beginner', tagline: 'Do it for me',
      },
      {
        value: 'Intermediate', icon: Briefcase, color: 'emerald',
        label: 'Intermediate', tagline: 'Understand the basics',
      },
      {
        value: 'Advanced (I want to input custom views)', icon: Cpu, color: 'amber',
        label: 'Advanced', tagline: 'I have my own views',
      },
    ],
    tooltip: 'Advanced users unlock the Black-Litterman model, which uses Bayesian inference to blend your personal market views with the algorithmic prior.'
  },
  {
    id: 'diversification_preference',
    title: 'How spread out should your portfolio be?',
    subtitle: 'Diversification limits how much any single asset can dominate.',
    field: 'diversification_preference',
    options: [
      {
        value: 'High (Maximum Spread)', icon: Grid3x3, color: 'emerald',
        label: 'High', tagline: 'Maximum Spread',
      },
      {
        value: 'Standard', icon: SlidersHorizontal, color: 'blue',
        label: 'Standard', tagline: 'Balanced concentration',
      },
      {
        value: 'Focused', icon: Focus, color: 'amber',
        label: 'Focused', tagline: 'Concentrate on best ideas',
      },
    ],
    tooltip: 'Choosing "High" triggers Hierarchical Risk Parity (HRP), an unsupervised machine learning algorithm that mathematically clusters assets for maximum true diversification.'
  },
];

const COLOR_MAP = {
  blue:   { ring: 'ring-blue-500',   bg: 'bg-blue-500/10',   text: 'text-blue-400' },
  emerald:{ ring: 'ring-emerald-500',bg: 'bg-emerald-500/10',text: 'text-emerald-400' },
  amber:  { ring: 'ring-amber-500',  bg: 'bg-amber-500/10',  text: 'text-amber-400' },
  violet: { ring: 'ring-violet-500', bg: 'bg-violet-500/10', text: 'text-violet-400' },
};

const slideVariants = {
  enter: (dir) => ({ x: dir > 0 ? 60 : -60, opacity: 0 }),
  center: { x: 0, opacity: 1, transition: { duration: 0.3, ease: 'easeOut' } },
  exit: (dir) => ({ x: dir > 0 ? -60 : 60, opacity: 0, transition: { duration: 0.2 } }),
};

export default function InvestorProfileWizard({ portfolioId, onComplete, onSkip }) {
  const [step, setStep]     = useState(0);
  const [dir, setDir]       = useState(1);
  const [saving, setSaving] = useState(false);
  const [error, setError]   = useState('');
  const { setAnalytics, setOptimization, setPortfolioId } = useStore();

  const [answers, setAnswers] = useState({
    time_horizon: '',
    drawdown_tolerance: '',
    liquidity_needs: '',
    experience_level: '',
    diversification_preference: '',
  });

  const currentStep   = STEPS[step];
  const selectedValue = answers[currentStep.field];
  const isLast        = step === STEPS.length - 1;
  const isFirst       = step === 0;

  const choose = (value) => setAnswers((a) => ({ ...a, [currentStep.field]: value }));

  const next = () => {
    if (!selectedValue) return;
    if (isLast) return handleSave();
    setDir(1);
    setStep((s) => s + 1);
  };

  const back = () => {
    setDir(-1);
    setStep((s) => s - 1);
  };

  const handleSave = async () => {
    setSaving(true);
    setError('');
    try {
      const res = await fetch(`/api/v1/portfolio/${portfolioId}/preferences`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(answers),
      });
      if (!res.ok) {
        const e = await res.json();
        throw new Error(e.detail || 'Failed to save preferences.');
      }

      // Ensure WS is connected to THIS portfolio before analysis fires,
      // so advisory_progress and new_recommendation events are received.
      setPortfolioId(portfolioId);

      // Re-run analysis so analytics reflect the new preferences
      const analysisRes = await fetch(`/api/v1/analyse/${portfolioId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ objective: 'max_sharpe', force_advisory: true }),
      });
      if (!analysisRes.ok) {
        const e = await analysisRes.json().catch(() => ({}));
        throw new Error(e.detail || 'Analysis failed after saving preferences.');
      }
      const analysisData = await analysisRes.json();
      if (analysisData.analytics) setAnalytics(analysisData.analytics);
      if (analysisData.optimization) setOptimization(analysisData.optimization);

      onComplete(answers);
    } catch (e) {
      setError(e.message);
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm">
      <motion.div
        initial={{ opacity: 0, scale: 0.95, y: 20 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.95, y: 20 }}
        transition={{ duration: 0.35, ease: 'easeOut' }}
        className="relative w-full max-w-2xl bg-[#0f1117] border border-slate-800 rounded-3xl shadow-[0_0_80px_rgba(16,185,129,0.08)] overflow-hidden"
      >
        <button
          onClick={onSkip}
          className="absolute top-4 right-4 z-10 text-slate-500 hover:text-slate-300 transition-colors p-1.5 rounded-lg hover:bg-slate-800/50"
        >
          <X className="w-4 h-4" />
        </button>

        <div className="h-1 bg-slate-800">
          <motion.div
            className="h-full bg-gradient-to-r from-emerald-600 to-emerald-400"
            initial={{ width: '0%' }}
            animate={{ width: `${((step + 1) / STEPS.length) * 100}%` }}
            transition={{ duration: 0.4, ease: 'easeInOut' }}
          />
        </div>

        <div className="p-8">
          <div className="mb-2 flex items-center gap-2">
            <span className="text-xs font-bold text-emerald-500 tracking-widest uppercase">
              Step {step + 1} of {STEPS.length}
            </span>
          </div>

          <AnimatePresence mode="wait" custom={dir}>
            <motion.div
              key={step}
              custom={dir}
              variants={slideVariants}
              initial="enter"
              animate="center"
              exit="exit"
            >
              <h2 className="text-2xl font-bold text-white mb-1">{currentStep.title}</h2>
              <p className="text-sm text-slate-400 mb-7">{currentStep.subtitle}</p>

              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-6">
                {currentStep.options.map((opt) => {
                  const isSelected = selectedValue === opt.value;
                  const c = COLOR_MAP[opt.color];
                  const Icon = opt.icon;

                  return (
                    <motion.button
                      key={opt.value}
                      onClick={() => choose(opt.value)}
                      whileHover={{ scale: 1.02 }}
                      whileTap={{ scale: 0.98 }}
                      className={`relative text-left p-5 rounded-2xl border-2 transition-all duration-200 flex flex-col items-center text-center gap-3 ${
                        isSelected
                          ? `${c.ring} border-opacity-100 bg-slate-800/80 shadow-lg`
                          : 'border-slate-700/60 bg-slate-900/40 hover:border-slate-600 hover:bg-slate-800/40'
                      }`}
                    >
                      {isSelected && (
                        <motion.div
                          initial={{ scale: 0 }} animate={{ scale: 1 }}
                          className="absolute top-2 right-2"
                        >
                          <CheckCircle2 className={`w-4 h-4 ${c.text}`} />
                        </motion.div>
                      )}

                      <div className={`w-12 h-12 rounded-xl ${c.bg} flex items-center justify-center`}>
                        <Icon className={`w-6 h-6 ${c.text}`} />
                      </div>

                      <div>
                        <p className="font-bold text-slate-100 text-[13px] leading-tight mb-1">{opt.label}</p>
                        <p className={`text-[11px] font-semibold ${c.text}`}>{opt.tagline}</p>
                      </div>
                    </motion.button>
                  );
                })}
              </div>

              {/* Explainability Tooltip */}
              <motion.div 
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.2 }}
                className="flex items-start gap-3 bg-slate-800/50 border border-slate-700/50 rounded-xl p-4 mt-2"
              >
                <Info className="w-5 h-5 text-slate-400 mt-0.5 flex-shrink-0" />
                <p className="text-sm text-slate-300 leading-relaxed">
                  <strong className="text-white">Why we ask this:</strong> {currentStep.tooltip}
                </p>
              </motion.div>
            </motion.div>
          </AnimatePresence>

          {error && (
            <p className="mt-4 text-sm text-red-400 bg-red-500/10 border border-red-500/20 rounded-xl px-4 py-2.5">
              {error}
            </p>
          )}

          <div className="flex items-center justify-between mt-8">
            <button
              onClick={back}
              disabled={isFirst}
              className="flex items-center gap-2 text-sm text-slate-400 hover:text-slate-200 disabled:opacity-0 transition-all"
            >
              <ChevronLeft className="w-4 h-4" /> Back
            </button>

            <motion.button
              onClick={next}
              disabled={!selectedValue || saving}
              whileHover={{ scale: selectedValue ? 1.02 : 1 }}
              whileTap={{ scale: selectedValue ? 0.97 : 1 }}
              className="flex items-center gap-2 bg-emerald-500 hover:bg-emerald-400 disabled:opacity-40 disabled:cursor-not-allowed text-[#0a0a0a] font-bold py-2.5 px-7 rounded-xl transition-all shadow-[0_0_20px_rgba(16,185,129,0.25)]"
            >
              {saving ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  Saving…
                </>
              ) : isLast ? (
                <>
                  <CheckCircle2 className="w-4 h-4" />
                  Save Profile
                </>
              ) : (
                <>
                  Continue
                  <ChevronRight className="w-4 h-4" />
                </>
              )}
            </motion.button>
          </div>
        </div>
      </motion.div>
    </div>
  );
}
