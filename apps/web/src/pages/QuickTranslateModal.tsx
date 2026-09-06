import React, { useState, useEffect } from 'react';
import {
  Sparkles,
  Copy,
  Check,
  X,
  MessageSquare,
  HelpCircle,
  RefreshCw,
  Monitor,
  ChevronRight,
  ArrowRight
} from 'lucide-react';
import { apiClient } from '../api/client';
import { Project, QuickTranslateResult } from '../types';
import { useToast } from '../context/ToastContext';

interface QuickTranslateModalProps {
  isOpen: boolean;
  onClose: () => void;
  activeProject: Project | null;
  projects: Project[];
}

export const QuickTranslateModal: React.FC<QuickTranslateModalProps> = ({
  isOpen,
  onClose,
  activeProject,
  projects
}) => {
  const toast = useToast();
  const [sourceText, setSourceText] = useState('');
  const [translationResult, setTranslationResult] = useState<QuickTranslateResult | null>(null);
  const [activeWindow, setActiveWindow] = useState<any | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isCopied, setIsCopied] = useState(false);
  const [explanation, setExplanation] = useState<string | null>(null);
  const [quickReplies, setQuickReplies] = useState<any[]>([]);

  useEffect(() => {
    if (isOpen) {
      loadActiveWindowAndClipboard();
    }
  }, [isOpen]);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onClose]);

  const loadActiveWindowAndClipboard = async () => {
    setIsLoading(true);
    try {
      const winRes = await apiClient.getActiveWindow();
      setActiveWindow(winRes);

      // Attempt quick translate
      const res = await apiClient.quickTranslate({
        target_language: 'vi',
        project_id: activeProject?.id || winRes.matched_project?.id || undefined
      });

      if (res && res.source_text) {
        setSourceText(res.source_text);
        setTranslationResult(res);
      }
    } catch (e) {
      console.error('Failed quick translate initialize:', e);
    } finally {
      setIsLoading(false);
    }
  };

  const handleTranslateManual = async (tone?: string) => {
    if (!sourceText.trim()) return;
    setIsLoading(true);
    setExplanation(null);
    setQuickReplies([]);
    try {
      const res = await apiClient.quickTranslate({
        text: sourceText,
        target_language: 'vi',
        project_id: activeProject?.id || undefined,
        style: tone || 'Auto'
      });
      setTranslationResult(res);
    } catch (e) {
      toast.error('Failed to translate');
    } finally {
      setIsLoading(false);
    }
  };

  const handleExplain = async () => {
    if (!sourceText.trim() || !translationResult) return;
    setIsLoading(true);
    try {
      const res = await apiClient.explain(sourceText, translationResult.translation, activeProject?.id);
      setExplanation(res.explanation || res.nuance || 'Explanation generated.');
    } catch (e) {
      toast.error('Failed to generate explanation');
    } finally {
      setIsLoading(false);
    }
  };

  const handleReply = async () => {
    if (!sourceText.trim()) return;
    setIsLoading(true);
    try {
      const res = await apiClient.quickReply({ text: sourceText });
      setQuickReplies(res.reply_options || []);
    } catch (e) {
      toast.error('Failed to generate quick replies');
    } finally {
      setIsLoading(false);
    }
  };

  const handleCopy = () => {
    if (!translationResult?.translation) return;
    navigator.clipboard.writeText(translationResult.translation);
    setIsCopied(true);
    setTimeout(() => setIsCopied(false), 2000);
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4 select-none">
      <div className="bg-slate-900 border border-sky-500/40 rounded-xl shadow-2xl max-w-xl w-full overflow-hidden flex flex-col animate-in fade-in zoom-in-95 duration-150">
        {/* Header */}
        <div className="px-4 py-3 border-b border-slate-800 flex items-center justify-between bg-slate-950/50">
          <div className="flex items-center gap-2">
            <div className="w-6 h-6 rounded-md bg-sky-500/20 text-sky-400 flex items-center justify-center">
              <Sparkles className="w-3.5 h-3.5" />
            </div>
            <h3 className="text-xs font-bold text-white tracking-tight flex items-center gap-1.5">
              Quick Translation Popup
              <span className="text-[10px] font-mono font-normal text-slate-500 bg-slate-800 px-1 rounded">
                Ctrl+Shift+T
              </span>
            </h3>
          </div>

          <div className="flex items-center gap-2">
            {activeWindow?.process_name && (
              <span className="text-[10px] font-mono text-amber-400 bg-amber-500/10 px-1.5 py-0.5 rounded border border-amber-500/20 flex items-center gap-1">
                <Monitor className="w-2.5 h-2.5" />
                {activeWindow.process_name}
              </span>
            )}
            <button
              onClick={onClose}
              className="text-slate-400 hover:text-white p-1 rounded hover:bg-slate-800"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Body */}
        <div className="p-4 space-y-3 text-xs">
          {/* Source Text Box */}
          <div className="space-y-1">
            <div className="flex items-center justify-between text-[11px] text-slate-400">
              <span className="font-semibold uppercase tracking-wider text-[10px]">Source (Japanese)</span>
              <button
                onClick={loadActiveWindowAndClipboard}
                className="text-sky-400 hover:underline flex items-center gap-1 text-[10px]"
              >
                <RefreshCw className="w-2.5 h-2.5" />
                <span>Read Clipboard</span>
              </button>
            </div>
            <textarea
              value={sourceText}
              onChange={(e) => setSourceText(e.target.value)}
              placeholder="Paste or type Japanese text here..."
              rows={3}
              className="w-full bg-slate-800 border border-slate-700 rounded-lg p-2.5 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-sky-500 select-text resize-none"
            />
          </div>

          {/* Translation Result Box */}
          <div className="space-y-1">
            <div className="flex items-center justify-between text-[11px] text-slate-400">
              <span className="font-semibold uppercase tracking-wider text-[10px] text-emerald-400">
                Translation (Vietnamese)
              </span>
              <span className="text-[10px] text-slate-500 font-mono">
                {activeProject ? activeProject.name : 'Global Context'}
              </span>
            </div>
            <div className="w-full bg-slate-950/80 border border-slate-800 rounded-lg p-3 text-xs text-emerald-300 min-h-[4rem] select-text leading-relaxed">
              {isLoading ? (
                <div className="flex items-center gap-2 text-slate-400">
                  <RefreshCw className="w-3.5 h-3.5 animate-spin text-sky-400" />
                  <span>Translating with context...</span>
                </div>
              ) : (
                translationResult?.translation || <span className="text-slate-500 italic">Translation will appear here...</span>
              )}
            </div>
          </div>

          {/* Explanation if requested */}
          {explanation && (
            <div className="p-2.5 bg-blue-500/10 border border-blue-500/20 rounded-lg text-xs text-blue-200 select-text">
              <span className="font-bold text-blue-400 block mb-1">Nuance & Context Explanation:</span>
              {explanation}
            </div>
          )}

          {/* Quick Replies if requested */}
          {quickReplies.length > 0 && (
            <div className="space-y-1.5 pt-1 border-t border-slate-800">
              <span className="text-[10px] font-bold uppercase text-white block">Suggested Japanese Replies:</span>
              <div className="grid grid-cols-2 gap-2">
                {quickReplies.map((r, i) => (
                  <div
                    key={i}
                    onClick={() => {
                      navigator.clipboard.writeText(r.text);
                      toast.success(`Đã sao chép phản hồi ${r.style} vào clipboard`);
                    }}
                    className="p-2 bg-slate-800/80 hover:bg-slate-800 rounded-lg border border-slate-700/80 cursor-pointer transition-colors"
                  >
                    <span className="text-[9px] font-bold text-emerald-400 uppercase font-mono block">{r.style}</span>
                    <p className="text-[11px] text-slate-200 truncate" title={r.text}>{r.text}</p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Quick Tone & Action Toolbar */}
          <div className="flex items-center justify-between pt-2 border-t border-slate-800">
            <div className="flex items-center gap-1.5">
              <button
                onClick={() => handleTranslateManual('Polite')}
                className="px-2 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 text-[10px] transition-colors"
              >
                More Polite
              </button>
              <button
                onClick={() => handleTranslateManual('Auto')}
                className="px-2 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 text-[10px] transition-colors"
              >
                Natural
              </button>
              <button
                onClick={() => handleTranslateManual('Concise')}
                className="px-2 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 text-[10px] transition-colors"
              >
                Concise
              </button>
              <button
                onClick={handleExplain}
                className="px-2 py-1 rounded bg-slate-800 hover:bg-slate-700 text-sky-400 text-[10px] transition-colors flex items-center gap-1"
              >
                <HelpCircle className="w-2.5 h-2.5" />
                <span>Explain</span>
              </button>
              <button
                onClick={handleReply}
                className="px-2 py-1 rounded bg-slate-800 hover:bg-slate-700 text-emerald-400 text-[10px] transition-colors flex items-center gap-1"
              >
                <MessageSquare className="w-2.5 h-2.5" />
                <span>Reply</span>
              </button>
            </div>

            <div className="flex items-center gap-2">
              <button
                onClick={handleCopy}
                disabled={!translationResult?.translation}
                className="px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold flex items-center gap-1.5 transition-colors shadow-sm disabled:opacity-50"
              >
                {isCopied ? <Check className="w-3.5 h-3.5" /> : <Copy className="w-3.5 h-3.5" />}
                <span>{isCopied ? 'Copied' : 'Copy (Ctrl+C)'}</span>
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
