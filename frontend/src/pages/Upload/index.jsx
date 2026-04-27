import { useState, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { UploadCloud, FileSpreadsheet, Loader2 } from 'lucide-react';
import { toast, Toaster } from 'react-hot-toast';
import { useStore } from '../../store/useStore';
import InvestorProfileWizard from '../../components/InvestorProfileWizard';


export default function UploadView() {
  const [file, setFile] = useState(null);
  const [isDragging, setIsDragging] = useState(false);
  const [loading, setLoading] = useState(false);
  const [showWizard, setShowWizard] = useState(false);
  const [uploadedPortfolioId, setUploadedPortfolioId] = useState(null);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [uploadResult, setUploadResult] = useState(null);

  const fileInputRef = useRef(null);
  const navigate = useNavigate();
  const { setPortfolioId } = useStore();

  const handleDragOver = (e) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = () => {
    setIsDragging(false);
  };

  const handleDrop = (e) => {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      setFile(e.dataTransfer.files[0]);
    }
  };

  const handleFileChange = (e) => {
    if (e.target.files && e.target.files.length > 0) {
      setFile(e.target.files[0]);
    }
  };

  const handleUpload = async () => {
    if (!file) return;
    setLoading(true);
    setUploadProgress(15);

    try {
      // 1. Create Portfolio
      const createRes = await fetch('/api/v1/portfolio/create', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_id: '00000000-0000-0000-0000-000000000001',
          name: 'AI Extracted Portfolio',
          target_return: 0.15,
          target_risk: 0.12,
        }),
      });
      if (!createRes.ok) throw new Error('Failed to create portfolio');
      const portfolioData = await createRes.json();
      const newPortfolioId = portfolioData.id;
      setUploadProgress(45);

      // 2. Upload File
      const formData = new FormData();
      formData.append('file', file);
      const uploadRes = await fetch(
        `/api/v1/portfolio/upload?portfolio_id=${newPortfolioId}`,
        { method: 'POST', body: formData }
      );
      
      if (!uploadRes.ok) {
        let errDetail = 'Failed to process file';
        try {
          const errData = await uploadRes.json();
          errDetail = errData.detail || errDetail;
        } catch (e) {}
        throw new Error(errDetail);
      }

      const uploadData = await uploadRes.json();
      setUploadResult(uploadData);
      setUploadProgress(100);
      setPortfolioId(newPortfolioId);
      setUploadedPortfolioId(newPortfolioId);

      if (uploadData.inserted === 0) {
        throw new Error('No valid holdings could be extracted. Check your file format.');
      }

      const skipped = uploadData.errors?.length || 0;
      const msg = `${uploadData.inserted} holdings imported successfully${skipped > 0 ? ` (${skipped} rows skipped)` : ''}.`;
      toast.success(msg, { duration: 5000 });

      // Transition to Wizard
      setTimeout(() => {
        setShowWizard(true);
      }, 800);

    } catch (err) {
      console.error(err);
      toast.error(err.message, { duration: 8000 });
      setLoading(false);
      setUploadProgress(0);
    }
  };

  // The wizard already ran analysis and updated the store before calling onComplete.
  // We just need to close the wizard and navigate to dashboard (analytics now embedded).
  const handleWizardComplete = () => {
    setShowWizard(false);
    navigate('/');
  };

  return (
    <>
      <Toaster />
      <AnimatePresence>
        {showWizard && (
          <InvestorProfileWizard
            portfolioId={uploadedPortfolioId}
            onComplete={handleWizardComplete}
            onSkip={() => navigate('/')}
          />
        )}
      </AnimatePresence>

      <div className="max-w-4xl mx-auto py-12">
        <div className="text-center mb-10">
          <h1 className="text-4xl font-bold text-white mb-4">Data Ingestion Engine</h1>
          <p className="text-slate-400 text-lg">
            Upload your broker's portfolio export — any format, any column names.
          </p>
        </div>

        {/* Format guide */}
        <div className="mb-6 grid grid-cols-1 md:grid-cols-3 gap-4 text-sm">
          {[
            {
              label: 'Supported Brokers',
              items: ['Zerodha / Kite', 'Groww', 'HDFC Securities', 'ICICI Direct', 'Upstox', 'Angel One', 'Any CSV export'],
            },
            {
              label: 'Recognised Column Names',
              items: ['Symbol / Ticker / Instrument', 'Quantity / Units / Shares', 'AvgBuyPrice / Price / Cost', 'Type / AssetType (optional)'],
            },
            {
              label: 'Notes',
              items: ['.NS suffix auto-added for NSE stocks', 'ISIN codes resolved automatically', 'Extra columns (P&L, etc.) are ignored', 'Max file size: 10 MB'],
            },
          ].map((card) => (
            <div key={card.label} className="bg-slate-900/60 border border-slate-800 rounded-xl p-4">
              <p className="text-slate-300 font-semibold mb-2">{card.label}</p>
              <ul className="space-y-1">
                {card.items.map((item) => (
                  <li key={item} className="text-slate-500 flex items-start gap-1.5">
                    <span className="text-emerald-500 mt-0.5 flex-shrink-0">·</span>{item}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>

        <motion.div
          animate={{ scale: isDragging ? 1.02 : 1 }}
          transition={{ type: 'spring', stiffness: 300, damping: 20 }}
          className={`relative border-2 border-dashed rounded-3xl p-16 transition-colors ${
            isDragging ? 'border-emerald-500 bg-emerald-500/5' : 'border-slate-700 bg-[#12141c]'
          } ${file ? 'border-emerald-500/50 bg-emerald-500/5' : ''}`}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
        >
          <input
            type="file"
            className="hidden"
            ref={fileInputRef}
            onChange={handleFileChange}
            accept=".csv,.pdf,.txt"
          />

          <AnimatePresence mode="wait">
            {!file ? (
              <motion.div
                key="empty"
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, scale: 0.9 }}
                className="flex flex-col items-center justify-center text-center"
              >
                <div className="w-20 h-20 bg-slate-800 rounded-full flex items-center justify-center mb-6 shadow-xl">
                  <UploadCloud className="w-10 h-10 text-slate-400" />
                </div>
                <h3 className="text-2xl font-bold text-white mb-2">Drag & Drop your file</h3>
                <p className="text-slate-400 mb-6 text-sm">or click to browse from your computer</p>
                <button
                  onClick={() => fileInputRef.current?.click()}
                  className="bg-emerald-500 hover:bg-emerald-400 text-[#0a0a0a] font-bold py-2.5 px-8 rounded-full shadow-[0_0_20px_rgba(16,185,129,0.3)] transition-all active:scale-95"
                >
                  Browse Files
                </button>
              </motion.div>
            ) : !loading ? (
              <motion.div
                key="file"
                initial={{ opacity: 0, scale: 0.9 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0, y: -20 }}
                className="flex flex-col items-center text-center"
              >
                <div className="w-24 h-24 bg-emerald-500/20 rounded-2xl flex items-center justify-center mb-6 shadow-[0_0_30px_rgba(16,185,129,0.2)] border border-emerald-500/30">
                  <FileSpreadsheet className="w-12 h-12 text-emerald-400" />
                </div>
                <h3 className="text-2xl font-bold text-white mb-2">{file.name}</h3>
                <p className="text-slate-400 mb-8 font-mono text-sm">{(file.size / 1024).toFixed(2)} KB</p>
                <div className="flex gap-4">
                  <button
                    onClick={() => setFile(null)}
                    className="text-slate-400 hover:text-white px-6 py-2.5 rounded-full border border-slate-700 hover:bg-slate-800 transition-all"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={handleUpload}
                    className="bg-emerald-500 hover:bg-emerald-400 text-[#0a0a0a] font-bold py-2.5 px-8 rounded-full shadow-[0_0_20px_rgba(16,185,129,0.3)] transition-all active:scale-95"
                  >
                    Process Portfolio
                  </button>
                </div>
              </motion.div>
            ) : (
              <motion.div
                key="processing"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                className="flex flex-col items-center text-center w-full max-w-md mx-auto"
              >
                <motion.div
                  animate={{ rotate: 360 }}
                  transition={{ duration: 2, repeat: Infinity, ease: 'linear' }}
                  className="mb-6"
                >
                  <Loader2 className="w-16 h-16 text-emerald-500" />
                </motion.div>
                <h3 className="text-2xl font-bold text-white mb-2">Ingesting Data...</h3>
                <p className="text-slate-400 mb-8">Extracting assets and mapping historical prices</p>
                
                <div className="w-full bg-slate-800 h-2 rounded-full overflow-hidden shadow-inner">
                  <motion.div
                    className="h-full bg-gradient-to-r from-emerald-600 to-emerald-400"
                    initial={{ width: 0 }}
                    animate={{ width: `${uploadProgress}%` }}
                    transition={{ duration: 0.2 }}
                  />
                </div>
                <div className="mt-3 text-sm text-emerald-400 font-mono font-bold">
                  {uploadProgress}%
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </motion.div>
      </div>
    </>
  );
}
