import { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { useStore } from '../../store/useStore';
import { useNavigate } from 'react-router-dom';
import { Lock, User, Eye, EyeOff, ShieldCheck } from 'lucide-react';

const COOKIE_KEY = 'equisight_remember';

/** Read the "remember me" cookie if it exists. */
function readRememberCookie() {
  const match = document.cookie.split('; ').find((c) => c.startsWith(`${COOKIE_KEY}=`));
  if (!match) return null;
  try {
    return JSON.parse(decodeURIComponent(match.split('=').slice(1).join('=')));
  } catch {
    return null;
  }
}

/** Write a 30-day secure cookie with the saved credentials. */
function writeRememberCookie(username, password) {
  const expires = new Date(Date.now() + 30 * 24 * 60 * 60 * 1000).toUTCString();
  const payload = encodeURIComponent(JSON.stringify({ username, password }));
  document.cookie = `${COOKIE_KEY}=${payload}; expires=${expires}; path=/; SameSite=Strict`;
}

/** Clear the remember-me cookie. */
function clearRememberCookie() {
  document.cookie = `${COOKIE_KEY}=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;`;
}

export default function Login() {
  const { login, rememberedUsername } = useStore();
  const navigate = useNavigate();

  // Pre-fill from cookie if it exists
  const savedCookie = readRememberCookie();

  const [username, setUsername]     = useState(savedCookie?.username ?? rememberedUsername ?? '');
  const [password, setPassword]     = useState(savedCookie?.password ?? '');
  const [remember, setRemember]     = useState(Boolean(savedCookie));
  const [showPw, setShowPw]         = useState(false);
  const [error, setError]           = useState('');
  const [shake, setShake]           = useState(false);

  // If already authenticated, skip login
  const isAuthenticated = useStore((s) => s.isAuthenticated);
  useEffect(() => {
    if (isAuthenticated) navigate('/', { replace: true });
  }, [isAuthenticated, navigate]);

  const handleLogin = (e) => {
    e.preventDefault();
    if (
      username === import.meta.env.VITE_USERNAME &&
      password === import.meta.env.VITE_PASSWORD
    ) {
      if (remember) {
        writeRememberCookie(username, password);
      } else {
        clearRememberCookie();
      }
      login(username, remember);
      navigate('/');
    } else {
      setError('Invalid credentials. Please try again.');
      setShake(true);
      setTimeout(() => setShake(false), 600);
    }
  };

  return (
    <div className="min-h-screen bg-[#0a0a0a] flex items-center justify-center p-4 selection:bg-emerald-500/30">
      {/* Ambient glow */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div className="absolute top-1/3 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[400px] bg-emerald-500/5 rounded-full blur-3xl" />
      </div>

      <motion.div
        initial={{ opacity: 0, y: 24 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, ease: 'easeOut' }}
        className={`relative w-full max-w-md bg-slate-900/60 backdrop-blur-xl border border-slate-800 rounded-3xl p-8 shadow-[0_0_60px_rgba(16,185,129,0.07)] ${shake ? 'animate-[shake_0.4s_ease-in-out]' : ''}`}
        style={shake ? { animation: 'shake 0.4s ease-in-out' } : {}}
      >
        {/* Logo */}
        <div className="flex justify-center mb-8">
          <motion.div
            whileHover={{ scale: 1.05 }}
            className="w-16 h-16 rounded-2xl bg-emerald-500 flex items-center justify-center font-bold text-3xl text-[#0a0a0a] shadow-[0_0_30px_rgba(16,185,129,0.5)]"
          >
            E
          </motion.div>
        </div>

        <h1 className="text-2xl font-bold text-center text-white mb-1">Welcome to Equisight</h1>
        <p className="text-center text-slate-400 text-sm mb-8">Sign in to your portfolio dashboard</p>

        <form onSubmit={handleLogin} className="space-y-5">
          {/* Username */}
          <div>
            <label htmlFor="login-username" className="block text-sm font-medium text-slate-300 mb-1.5">
              Username
            </label>
            <div className="relative group">
              <User className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500 group-focus-within:text-emerald-400 transition-colors" />
              <input
                id="login-username"
                name="username"
                type="text"
                value={username}
                onChange={(e) => { setUsername(e.target.value); setError(''); }}
                className="w-full bg-[#0f0f0f] border border-slate-800 rounded-xl py-3 pl-10 pr-4 text-slate-200 focus:outline-none focus:ring-1 focus:ring-emerald-500 focus:border-emerald-500 transition-all placeholder:text-slate-600"
                placeholder="admin"
                autoComplete="username"
                autoFocus
              />
            </div>
          </div>

          {/* Password */}
          <div>
            <label htmlFor="login-password" className="block text-sm font-medium text-slate-300 mb-1.5">
              Password
            </label>
            <div className="relative group">
              <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500 group-focus-within:text-emerald-400 transition-colors" />
              <input
                id="login-password"
                name="password"
                type={showPw ? 'text' : 'password'}
                value={password}
                onChange={(e) => { setPassword(e.target.value); setError(''); }}
                className="w-full bg-[#0f0f0f] border border-slate-800 rounded-xl py-3 pl-10 pr-11 text-slate-200 focus:outline-none focus:ring-1 focus:ring-emerald-500 focus:border-emerald-500 transition-all placeholder:text-slate-600"
                placeholder="••••••••"
                autoComplete="current-password"
              />
              <button
                type="button"
                id="toggle-password-visibility"
                onClick={() => setShowPw((v) => !v)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300 transition-colors"
                tabIndex={-1}
                aria-label={showPw ? 'Hide password' : 'Show password'}
              >
                {showPw ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              </button>
            </div>
          </div>

          {/* Remember me */}
          <label className="flex items-center gap-3 cursor-pointer group select-none">
            <div className="relative">
              <input
                id="remember-me"
                type="checkbox"
                checked={remember}
                onChange={(e) => setRemember(e.target.checked)}
                className="sr-only"
              />
              <div
                className={`w-5 h-5 rounded-md border transition-all ${
                  remember
                    ? 'bg-emerald-500 border-emerald-500'
                    : 'bg-transparent border-slate-600 group-hover:border-slate-400'
                } flex items-center justify-center`}
              >
                {remember && (
                  <motion.svg
                    initial={{ scale: 0 }} animate={{ scale: 1 }} transition={{ duration: 0.15 }}
                    className="w-3 h-3 text-[#0a0a0a]" viewBox="0 0 12 10" fill="none"
                  >
                    <path d="M1 5l3.5 3.5L11 1" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                  </motion.svg>
                )}
              </div>
            </div>
            <span className="text-sm text-slate-400 group-hover:text-slate-300 transition-colors">
              Remember me for 30 days
            </span>
          </label>

          {/* Error */}
          {error && (
            <motion.p
              initial={{ opacity: 0, y: -4 }} animate={{ opacity: 1, y: 0 }}
              className="text-red-400 text-sm text-center font-medium bg-red-500/10 border border-red-500/20 rounded-lg py-2.5 px-4"
            >
              {error}
            </motion.p>
          )}

          {/* Submit */}
          <motion.button
            type="submit"
            id="login-submit"
            whileHover={{ scale: 1.01 }}
            whileTap={{ scale: 0.98 }}
            className="w-full bg-emerald-500 hover:bg-emerald-400 text-[#0a0a0a] font-bold py-3.5 rounded-xl mt-2 transition-colors shadow-[0_0_25px_rgba(16,185,129,0.25)] hover:shadow-[0_0_35px_rgba(16,185,129,0.45)] flex items-center justify-center gap-2"
          >
            <ShieldCheck className="w-4 h-4" />
            Sign In
          </motion.button>
        </form>

        {/* Footer hint */}
        <p className="text-center text-xs text-slate-600 mt-6">
          Your session is secured and encrypted.
        </p>
      </motion.div>

      {/* Shake keyframe injected inline so no Tailwind config required */}
      <style>{`
        @keyframes shake {
          0%, 100% { transform: translateX(0); }
          15%       { transform: translateX(-8px); }
          30%       { transform: translateX(8px); }
          45%       { transform: translateX(-6px); }
          60%       { transform: translateX(6px); }
          75%       { transform: translateX(-3px); }
          90%       { transform: translateX(3px); }
        }
      `}</style>
    </div>
  );
}
