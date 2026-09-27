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
  ArrowRight,
  Clipboard
} from 'lucide-react';
import { apiClient } from '../api/client';
import { Project, QuickTranslateResult } from '../types';
import { useToast } from '../context/ToastContext';
import { Button } from '../components/ui/Button';
import { Badge } from '../components/ui/Badge';

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
    toast.success('Đã sao chép vào clipboard');
    setTimeout(() => setIsCopied(false), 2000);
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 bg-black/60 dark:bg-black/75 backdrop-blur-xs flex items-center justify-center p-4 select-none animate-backdrop-in">
      <div className="bg-surface border border-border-default rounded-xl shadow-2xl max-w-xl w-full overflow-hidden flex flex-col ring-1 ring-border-subtle animate-modal-in">
        {/* Header */}
        <div className="px-4 py-3 border-b border-border-subtle flex items-center justify-between bg-surface-elevated/50">
          <div className="flex items-center gap-2">
            <div className="w-7 h-7 rounded-lg bg-primary/10 text-primary flex items-center justify-center">
              <Sparkles className="w-4 h-4" />
            </div>
            <div>
              <h3 className="text-xs font-bold text-text-primary tracking-tight flex items-center gap-1.5">
                Quick Translation Companion
                <span className="text-[10px] font-mono font-normal text-text-muted bg-surface px-1.5 py-0.5 rounded border border-border-subtle">
                  Ctrl+Shift+T
                </span>
              </h3>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {activeWindow?.process_name && (
              <Badge variant="warning" size="sm" className="font-mono text-[10px] flex items-center gap-1">
                <Monitor className="w-3 h-3" />
                {activeWindow.process_name}
              </Badge>
            )}
            <button
              onClick={onClose}
              className="text-text-muted hover:text-text-primary p-1 rounded-lg hover:bg-surface-elevated transition"
              aria-label="Close"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Body */}
        <div className="p-4 space-y-3.5 text-xs">
          {/* Source Text Box */}
          <div className="space-y-1.5">
            <div className="flex items-center justify-between text-[11px] text-text-muted">
              <span className="font-semibold uppercase tracking-wider text-[10px] text-text-secondary">Source (Japanese)</span>
              <button
                onClick={loadActiveWindowAndClipboard}
                className="text-primary hover:underline flex items-center gap-1 text-[11px] font-medium"
              >
                <Clipboard className="w-3 h-3" />
                <span>Read Clipboard</span>
              </button>
            </div>
            <textarea
              value={sourceText}
              onChange={(e) => setSourceText(e.target.value)}
              placeholder="Paste or type Japanese text here..."
              rows={3}
              className="w-full bg-surface-elevated border border-border-subtle rounded-lg p-2.5 text-xs text-text-primary placeholder-text-muted focus:outline-none focus:border-primary select-text resize-none font-sans"
            />
          </div>

          {/* Translation Result Box */}
          <div className="space-y-1.5">
            <div className="flex items-center justify-between text-[11px] text-text-muted">
              <span className="font-semibold uppercase tracking-wider text-[10px] text-emerald-500">
                Translation (Vietnamese)
              </span>
              <span className="text-[10px] text-text-muted font-mono">
                {activeProject ? activeProject.name : 'Global Context'}
              </span>
            </div>
            <div className="w-full bg-surface-elevated border border-border-subtle rounded-lg p-3 text-xs text-emerald-500 min-h-[4.5rem] select-text leading-relaxed">
              {isLoading ? (
                <div className="flex items-center gap-2 text-text-muted">
                  <RefreshCw className="w-3.5 h-3.5 animate-spin text-primary" />
                  <span>Translating with domain context...</span>
                </div>
              ) : (
                translationResult?.translation || <span className="text-text-muted italic">Translation will appear here...</span>
              )}
            </div>
          </div>

          {/* Explanation if requested */}
          {explanation && (
            <div className="p-3 bg-primary/5 border border-primary/20 rounded-lg text-xs text-text-primary select-text leading-relaxed">
              <span className="font-bold text-primary block mb-1">Nuance & Context Explanation:</span>
              {explanation}
            </div>
          )}

          {/* Quick Replies if requested */}
          {quickReplies.length > 0 && (
            <div className="space-y-1.5 pt-2 border-t border-border-subtle">
              <span className="text-[10px] font-bold uppercase text-text-secondary block">Suggested Japanese Replies:</span>
              <div className="grid grid-cols-2 gap-2">
                {quickReplies.map((r, i) => (
                  <div
                    key={i}
                    onClick={() => {
                      navigator.clipboard.writeText(r.text);
                      toast.success(`Đã sao chép phản hồi ${r.style} vào clipboard`);
                    }}
                    className="p-2.5 bg-surface-elevated hover:bg-surface-elevated/80 rounded-lg border border-border-subtle cursor-pointer transition"
                  >
                    <span className="text-[9px] font-bold text-emerald-500 uppercase font-mono block mb-0.5">{r.style}</span>
                    <p className="text-[11px] text-text-primary truncate" title={r.text}>{r.text}</p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Quick Tone & Action Toolbar */}
          <div className="flex items-center justify-between pt-2.5 border-t border-border-subtle">
            <div className="flex items-center gap-1.5 flex-wrap">
              <button
                onClick={() => handleTranslateManual('Polite')}
                className="px-2.5 py-1.5 rounded-md bg-surface-elevated hover:bg-surface-hover active:scale-[0.96] text-text-secondary text-[11px] font-medium border border-border-subtle transition-all duration-150 ease-[cubic-bezier(0.16,1,0.3,1)] cursor-pointer"
              >
                More Polite
              </button>
              <button
                onClick={() => handleTranslateManual('Auto')}
                className="px-2.5 py-1.5 rounded-md bg-surface-elevated hover:bg-surface-hover active:scale-[0.96] text-text-secondary text-[11px] font-medium border border-border-subtle transition-all duration-150 ease-[cubic-bezier(0.16,1,0.3,1)] cursor-pointer"
              >
                Natural
              </button>
              <button
                onClick={() => handleTranslateManual('Concise')}
                className="px-2.5 py-1.5 rounded-md bg-surface-elevated hover:bg-surface-hover active:scale-[0.96] text-text-secondary text-[11px] font-medium border border-border-subtle transition-all duration-150 ease-[cubic-bezier(0.16,1,0.3,1)] cursor-pointer"
              >
                Concise
              </button>
              <button
                onClick={handleExplain}
                className="px-2.5 py-1.5 rounded-md bg-surface-elevated hover:bg-surface-hover active:scale-[0.96] text-primary text-[11px] font-medium border border-border-subtle transition-all duration-150 ease-[cubic-bezier(0.16,1,0.3,1)] cursor-pointer flex items-center gap-1"
              >
                <HelpCircle className="w-3 h-3" />
                <span>Explain</span>
              </button>
              <button
                onClick={handleReply}
                className="px-2.5 py-1.5 rounded-md bg-surface-elevated hover:bg-surface-hover active:scale-[0.96] text-emerald-500 text-[11px] font-medium border border-border-subtle transition-all duration-150 ease-[cubic-bezier(0.16,1,0.3,1)] cursor-pointer flex items-center gap-1"
              >
                <MessageSquare className="w-3 h-3" />
                <span>Reply</span>
              </button>
            </div>

            <Button
              variant="primary"
              size="sm"
              onClick={handleCopy}
              disabled={!translationResult?.translation}
            >
              {isCopied ? (
                <>
                  <Check className="w-3.5 h-3.5 mr-1" /> Copied
                </>
              ) : (
                <>
                  <Copy className="w-3.5 h-3.5 mr-1" /> Copy
                </>
              )}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
};
