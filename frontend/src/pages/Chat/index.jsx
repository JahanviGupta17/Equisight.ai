import { useState, useRef, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useStore } from '../../store/useStore';
import {
  Send, Paperclip, Bot, User, Loader2, X,
  FileText, AlertCircle, Sparkles, ChevronRight,
} from 'lucide-react';

// ─── Plain text renderer — strips all markdown Gemini occasionally outputs ─────
function renderContent(raw) {
  // 1. Strip heading markers (# ## ###) at line start
  // 2. Strip bold/italic markers (** __ * _)
  // 3. Strip leading bullet/dash/numbered-list characters
  const cleaned = raw
    .replace(/^#{1,6}\s+/gm, '')          // # headings
    .replace(/\*\*(.*?)\*\*/g, '$1')       // **bold**
    .replace(/\*(.*?)\*/g, '$1')           // *italic*
    .replace(/__(.*?)__/g, '$1')           // __bold__
    .replace(/_(.*?)_/g, '$1')             // _italic_
    .replace(/^[\-\*]\s+/gm, '')           // bullet points
    .replace(/^\d+\.\s+/gm, '')            // numbered lists
    .replace(/`{1,3}([^`]*)`{1,3}/g, '$1') // `code`
    .trim();

  // Split on newlines for paragraph rendering
  return cleaned.split('\n').map((line, i) => (
    <span key={i}>
      {line}
      {i < cleaned.split('\n').length - 1 && <br />}
    </span>
  ));
}

// ─── Message bubble ───────────────────────────────────────────────────────────
function MessageBubble({ msg }) {
  const isUser = msg.role === 'user';
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2 }}
      className={`flex gap-3 ${isUser ? 'flex-row-reverse' : 'flex-row'}`}
    >
      {/* Avatar */}
      <div className={`flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center shadow-md ${
        isUser
          ? 'bg-emerald-500/20 border border-emerald-500/30 text-emerald-400'
          : 'bg-slate-700/80 border border-slate-600/50 text-slate-300'
      }`}>
        {isUser ? <User className="w-4 h-4" /> : <Bot className="w-4 h-4" />}
      </div>

      {/* Bubble */}
      <div className={`max-w-[78%] rounded-2xl px-4 py-3 text-sm leading-relaxed ${
        isUser
          ? 'bg-emerald-500/12 border border-emerald-500/20 text-slate-200 rounded-tr-sm'
          : 'bg-slate-800/70 border border-slate-700/50 text-slate-300 rounded-tl-sm'
      }`}>
        <div className="whitespace-pre-wrap">{renderContent(msg.content)}</div>

        {/* Sources */}
        {msg.sources?.length > 0 && (
          <div className="mt-3 pt-2 border-t border-slate-700/50 space-y-1">
            <p className="text-[10px] text-slate-500 font-semibold uppercase tracking-wider">Sources</p>
            {msg.sources.map((s, i) => (
              <a
                key={i}
                href={s.startsWith('uploaded://') ? undefined : s}
                target="_blank"
                rel="noopener noreferrer"
                className="block text-xs text-emerald-400/60 hover:text-emerald-400 truncate transition-colors"
              >
                {s.replace('uploaded://', '📄 ')}
              </a>
            ))}
          </div>
        )}
      </div>
    </motion.div>
  );
}

// ─── Typing indicator ─────────────────────────────────────────────────────────
function TypingIndicator() {
  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex gap-3">
      <div className="w-8 h-8 rounded-full bg-slate-700/80 border border-slate-600/50 flex items-center justify-center flex-shrink-0">
        <Bot className="w-4 h-4 text-slate-300" />
      </div>
      <div className="bg-slate-800/70 border border-slate-700/50 rounded-2xl rounded-tl-sm px-4 py-3 flex items-center gap-1.5">
        {[0, 0.15, 0.3].map((delay, i) => (
          <motion.div
            key={i}
            className="w-1.5 h-1.5 rounded-full bg-emerald-400"
            animate={{ scale: [1, 1.5, 1], opacity: [0.4, 1, 0.4] }}
            transition={{ duration: 0.8, repeat: Infinity, delay }}
          />
        ))}
      </div>
    </motion.div>
  );
}

// ─── Suggested questions ───────────────────────────────────────────────────────
const SUGGESTIONS = [
  { label: 'Portfolio risk level?', text: 'What is the current risk level of my portfolio and how can I reduce it?' },
  { label: 'Top performers?', text: 'Which stocks are performing best in my portfolio right now?' },
  { label: 'Should I rebalance?', text: 'Based on the optimization results, should I rebalance my portfolio now?' },
  { label: 'Explain Sharpe ratio', text: 'Explain my portfolio Sharpe ratio in simple terms.' },
  { label: 'Biggest risk?', text: 'What is the biggest risk in my current portfolio allocation?' },
];

// ─── Main component ────────────────────────────────────────────────────────────
export default function Chat() {
  const portfolioId      = useStore((s) => s.portfolioId);
  const analyticsData    = useStore((s) => s.analyticsData);
  const optimizationData = useStore((s) => s.optimizationData);

  const [messages, setMessages] = useState([
    {
      id: 'intro',
      role: 'assistant',
      content:
        "Hi! I'm your Equisight AI advisor. I have full visibility into your portfolio — holdings, analytics, optimization results, and uploaded documents.\n\nWhat would you like to know?",
    },
  ]);
  const [input, setInput]           = useState('');
  const [loading, setLoading]       = useState(false);
  const [uploadedDoc, setUploadedDoc]   = useState(null);
  const [uploadLoading, setUploadLoading] = useState(false);
  const [uploadError, setUploadError]   = useState('');
  const [error, setError]           = useState('');

  const bottomRef   = useRef(null);
  const fileRef     = useRef(null);
  const textareaRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

  // ── Document ingestion ─────────────────────────────────────────────────────
  const handleDocUpload = async (file) => {
    if (!file) return;
    setUploadLoading(true);
    setUploadError('');
    const form = new FormData();
    form.append('file', file);
    try {
      const res = await fetch('/api/v1/chat/ingest', { method: 'POST', body: form });
      if (!res.ok) {
        const e = await res.json().catch(() => ({}));
        throw new Error(e.detail || 'Upload failed');
      }
      const data = await res.json();
      setUploadedDoc({ name: file.name, chunks: data.chunks });
      setMessages((m) => [
        ...m,
        {
          id: Date.now(),
          role: 'assistant',
          content: `I've indexed **"${file.name}"** (${data.chunks} chunks). You can now ask me questions about it alongside your portfolio.`,
        },
      ]);
    } catch (err) {
      setUploadError(err.message);
    } finally {
      setUploadLoading(false);
    }
  };

  // ── Send message ──────────────────────────────────────────────────────────
  const sendMessage = async (overrideText) => {
    const question = (overrideText ?? input).trim();
    if (!question || loading) return;
    setInput('');
    setError('');

    const userMsg = { id: Date.now(), role: 'user', content: question };
    setMessages((m) => [...m, userMsg]);
    setLoading(true);

    // Build history: all messages except the intro greeting (id='intro')
    // Use only actual user/assistant turns (not the intro)
    const historyForApi = messages
      .filter((m) => m.id !== 'intro')
      .map((m) => ({ role: m.role, content: m.content }));

    try {
      const res = await fetch('/api/v1/chat/ask', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          question,
          portfolio_id: portfolioId,
          include_portfolio_context: true,
          history: historyForApi,
          // Send full snapshots so Gemini has rich context without extra DB round-trips
          analytics_snapshot: analyticsData || null,
          optimization_snapshot: optimizationData || null,
        }),
      });

      if (!res.ok) {
        const e = await res.json().catch(() => ({}));
        throw new Error(e.detail || `Server error ${res.status}`);
      }
      const data = await res.json();
      setMessages((m) => [
        ...m,
        { id: Date.now() + 1, role: 'assistant', content: data.answer, sources: data.sources },
      ]);
    } catch (err) {
      setError(err.message);
      setMessages((m) => [
        ...m,
        {
          id: Date.now() + 1,
          role: 'assistant',
          content: `I ran into an issue: **${err.message}**\n\nPlease try again, or check that the backend is running.`,
        },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  const hasPortfolioData = Boolean(analyticsData || optimizationData);
  const userMessageCount = messages.filter((m) => m.role === 'user').length;

  return (
    <div className="flex flex-col h-[calc(100vh-8rem)] max-w-3xl mx-auto">

      {/* ── Header ── */}
      <div className="flex items-center justify-between mb-4 pb-4 border-b border-slate-800/60">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-emerald-500/20 to-emerald-600/10 border border-emerald-500/20 flex items-center justify-center shadow-[0_0_16px_rgba(16,185,129,0.1)]">
            <Sparkles className="w-5 h-5 text-emerald-400" />
          </div>
          <div>
            <h1 className="text-base font-bold text-white">Portfolio AI Advisor</h1>
            <p className="text-xs text-slate-500">
              Powered by Gemini ·{' '}
              {hasPortfolioData
                ? <span className="text-emerald-500">Portfolio context loaded</span>
                : <span className="text-amber-500">No portfolio data yet</span>}
            </p>
          </div>
        </div>

        {/* Doc upload control */}
        <div className="flex items-center gap-2">
          {uploadedDoc && (
            <div className="flex items-center gap-1.5 bg-emerald-500/10 border border-emerald-500/20 rounded-full px-3 py-1">
              <FileText className="w-3.5 h-3.5 text-emerald-400" />
              <span className="text-xs text-emerald-300 max-w-[110px] truncate">{uploadedDoc.name}</span>
              <button onClick={() => setUploadedDoc(null)} className="text-slate-500 hover:text-slate-300 ml-0.5">
                <X className="w-3 h-3" />
              </button>
            </div>
          )}
          <input
            type="file"
            ref={fileRef}
            className="hidden"
            accept=".pdf,.txt,.csv"
            onChange={(e) => e.target.files?.[0] && handleDocUpload(e.target.files[0])}
          />
          <button
            onClick={() => fileRef.current?.click()}
            disabled={uploadLoading}
            title="Upload a document to chat about"
            className="flex items-center gap-1.5 text-xs text-slate-400 hover:text-slate-200 border border-slate-700 hover:border-slate-600 bg-slate-800/50 hover:bg-slate-800 rounded-full px-3 py-1.5 transition-all disabled:opacity-50"
          >
            {uploadLoading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Paperclip className="w-3.5 h-3.5" />}
            {uploadLoading ? 'Indexing…' : 'Add Doc'}
          </button>
        </div>
      </div>

      {/* Upload error */}
      {uploadError && (
        <div className="flex items-center gap-2 bg-red-500/10 border border-red-500/20 rounded-xl px-4 py-2.5 mb-3 text-sm text-red-400">
          <AlertCircle className="w-4 h-4 flex-shrink-0" />
          {uploadError}
          <button onClick={() => setUploadError('')} className="ml-auto"><X className="w-3.5 h-3.5" /></button>
        </div>
      )}

      {/* ── Messages ── */}
      <div className="flex-1 overflow-y-auto space-y-4 pr-1 pb-4" style={{ scrollbarWidth: 'thin', scrollbarColor: '#1e293b transparent' }}>
        <AnimatePresence initial={false}>
          {messages.map((msg) => (
            <MessageBubble key={msg.id} msg={msg} />
          ))}
        </AnimatePresence>

        {loading && <TypingIndicator />}
        <div ref={bottomRef} />
      </div>

      {/* ── Suggestions (show when no user messages yet) ── */}
      <AnimatePresence>
        {userMessageCount === 0 && (
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 8 }}
            className="flex flex-wrap gap-2 mb-3"
          >
            {SUGGESTIONS.map((s) => (
              <button
                key={s.label}
                onClick={() => sendMessage(s.text)}
                disabled={loading}
                className="flex items-center gap-1 text-xs text-slate-400 hover:text-slate-200 border border-slate-700 hover:border-emerald-500/40 hover:bg-emerald-500/5 bg-slate-800/40 rounded-full px-3 py-1.5 transition-all disabled:opacity-50 group"
              >
                <ChevronRight className="w-3 h-3 text-emerald-500 opacity-0 group-hover:opacity-100 transition-opacity" />
                {s.label}
              </button>
            ))}
          </motion.div>
        )}
      </AnimatePresence>

      {/* ── Input bar ── */}
      <div className="border border-slate-700/80 bg-slate-900/60 backdrop-blur-sm rounded-2xl p-3 flex items-end gap-3 focus-within:border-emerald-500/40 focus-within:shadow-[0_0_20px_rgba(16,185,129,0.05)] transition-all">
        <textarea
          ref={textareaRef}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask anything about your portfolio…"
          rows={1}
          className="flex-1 bg-transparent text-slate-200 text-sm placeholder-slate-600 resize-none outline-none max-h-36 leading-relaxed"
          style={{ scrollbarWidth: 'none' }}
        />
        <button
          onClick={() => sendMessage()}
          disabled={!input.trim() || loading}
          className="flex-shrink-0 w-9 h-9 rounded-xl bg-emerald-500 hover:bg-emerald-400 disabled:opacity-40 disabled:cursor-not-allowed text-slate-900 flex items-center justify-center transition-all active:scale-95 shadow-[0_0_12px_rgba(16,185,129,0.3)]"
        >
          {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
        </button>
      </div>
      <p className="text-center text-[11px] text-slate-600 mt-2">
        Enter to send · Shift+Enter for new line · Context-aware across {messages.length - 1} message{messages.length !== 2 ? 's' : ''}
      </p>
    </div>
  );
}
