import React, { useState, useEffect } from 'react';
import { 
  ArrowRightLeft, 
  Sparkles, 
  Copy, 
  Check, 
  HelpCircle, 
  MessageSquareReply, 
  Edit3, 
  AlertTriangle, 
  BookOpen, 
  Cpu, 
  Clock, 
  Layers, 
  Send,
  Trash2,
  BookmarkPlus,
  BookPlus
} from 'lucide-react';
import { apiClient } from '../api/client';
import { Project, TranslationResponse, CandidateTranslation } from '../types';
import { useToast } from '../context/ToastContext';
import { AiThinkingLoader } from '../components/skeletons/AiThinkingLoader';
import { ProviderModelSelector } from '../components/ProviderModelSelector';
import { getSavedProvider, getSavedModel, resolveHealthyModel } from '../utils/aiPreferences';

interface TranslatorPageProps {
  activeProject: Project | null;
  projects: Project[];
  setActiveProject: (p: Project | null) => void;
}

export const TranslatorPage: React.FC<TranslatorPageProps> = ({
  activeProject,
  projects,
  setActiveProject
}) => {
  const toast = useToast();
  const [sourceText, setSourceText] = useState('');
  const [direction, setDirection] = useState<'ja-vi' | 'vi-ja' | 'auto'>('ja-vi');
  const [style, setStyle] = useState('business');
  const [selectedProvider, setSelectedProvider] = useState<string>(() => getSavedProvider('auto'));
  const [selectedModel, setSelectedModel] = useState<string>(() => getSavedModel(''));
  const [providers, setProviders] = useState<any[]>([]);
  
  useEffect(() => {
    apiClient.getProviders().then((provs) => {
      setProviders(provs);
      const healthy = resolveHealthyModel(provs, 'auto', '');
      setSelectedProvider(healthy.provider);
      setSelectedModel(healthy.model);
    }).catch(console.error);
  }, []);

  // State
  const [isLoading, setIsLoading] = useState(false);
  const [statusStep, setStatusStep] = useState<string>('Idle');
  const [response, setResponse] = useState<TranslationResponse | null>(null);
  const [copiedIndex, setCopiedIndex] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Modal / Drawers
  const [explainData, setExplainData] = useState<any | null>(null);
  const [isExplaining, setIsExplaining] = useState(false);
  
  const [replyData, setReplyData] = useState<any | null>(null);
  const [isReplying, setIsReplying] = useState(false);
  const [showReplyModal, setShowReplyModal] = useState(false);
  const [userReplyIntent, setUserReplyIntent] = useState('');
  const [editingReplyIndex, setEditingReplyIndex] = useState<number | null>(null);

  // User Correction Dialog
  const [correctingCandidate, setCorrectingCandidate] = useState<CandidateTranslation | null>(null);
  const [correctionInput, setCorrectionInput] = useState('');
  const [correctionScope, setCorrectionScope] = useState<'project' | 'global'>('project');
  const [correctionSaved, setCorrectionSaved] = useState(false);

  // Quick Add Glossary Dialog
  const [showGlossaryModal, setShowGlossaryModal] = useState(false);
  const [glossarySource, setGlossarySource] = useState('');
  const [glossaryTarget, setGlossaryTarget] = useState('');
  const [glossaryCategory, setGlossaryCategory] = useState('IT');
  const [glossaryScope, setGlossaryScope] = useState<'project' | 'global'>('project');
  const [isSavingGlossary, setIsSavingGlossary] = useState(false);

  // Handle Translate
  const handleTranslate = async () => {
    if (!sourceText.trim() || isLoading) return;
    setIsLoading(true);
    setError(null);
    setStatusStep('Retrieving project rules & glossary...');

    try {
      const source_lang = direction === 'ja-vi' ? 'ja' : direction === 'vi-ja' ? 'vi' : 'auto';
      const target_lang = direction === 'ja-vi' ? 'vi' : direction === 'vi-ja' ? 'ja' : 'vi';

      let preferred_provider: string | undefined = undefined;
      let force_model: string | undefined = undefined;

      if (selectedProvider && selectedProvider !== 'auto') {
        preferred_provider = selectedProvider;
        if (selectedModel) {
          force_model = selectedModel;
        }
      }

      setStatusStep('Selecting AI model & translating...');
      const res = await apiClient.translate({
        source_text: sourceText,
        source_language: source_lang,
        target_language: target_lang,
        project_id: activeProject?.id || null,
        style: style,
        preferred_provider: preferred_provider,
        force_model: force_model
      });

      setResponse(res);
      setStatusStep('Completed');
    } catch (err: any) {
      console.error('Translation error:', err);
      setError(err?.response?.data?.detail || err.message || 'Translation failed');
      setStatusStep('Error');
    } finally {
      setIsLoading(false);
    }
  };

  // Keyboard shortcut Ctrl+Enter
  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
      e.preventDefault();
      handleTranslate();
    }
  };

  const copyToClipboard = (text: string, index: number) => {
    navigator.clipboard.writeText(text);
    setCopiedIndex(index);
    setTimeout(() => setCopiedIndex(null), 2000);
  };

  // Explain Feature
  const handleExplain = async (candidate: CandidateTranslation) => {
    setIsExplaining(true);
    setExplainData(null);
    try {
      const preferred_provider = selectedProvider && selectedProvider !== 'auto' ? selectedProvider : undefined;
      const force_model = selectedModel || undefined;
      const res = await apiClient.explain(sourceText, candidate.text, activeProject?.id, preferred_provider, force_model);
      setExplainData(res);
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || err.message, 'Explanation Failed');
    } finally {
      setIsExplaining(false);
    }
  };

  // Reply Feature
  const handleOpenReplyModal = () => {
    setShowReplyModal(true);
    if (!replyData) {
      handleGenerateReply();
    }
  };

  const handleGenerateReply = async () => {
    if (!sourceText.trim()) return;
    setIsReplying(true);
    try {
      const preferred_provider = selectedProvider && selectedProvider !== 'auto' ? selectedProvider : undefined;
      const force_model = selectedModel || undefined;
      const res = await apiClient.reply(
        sourceText, 
        undefined, 
        activeProject?.id, 
        preferred_provider, 
        force_model,
        userReplyIntent.trim() || undefined
      );
      setReplyData(res);
      setEditingReplyIndex(null);
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || err.message, 'Tạo câu trả lời thất bại');
    } finally {
      setIsReplying(false);
    }
  };

  // Save Correction
  const handleSaveCorrection = async () => {
    if (!correctingCandidate || !correctionInput.trim()) return;
    try {
      await apiClient.recordCorrection({
        project_id: activeProject?.id || null,
        source_text: sourceText,
        original_translation: correctingCandidate.text,
        corrected_translation: correctionInput.trim(),
        apply_scope: correctionScope,
        save_to_tm: true
      });
      setCorrectionSaved(true);
      toast.success('Đã lưu hiệu chỉnh vào Translation Memory');
      setTimeout(() => {
        setCorrectingCandidate(null);
        setCorrectionSaved(false);
      }, 1500);
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || err.message, 'Failed to save correction');
    }
  };

  // Open Quick Glossary Modal
  const handleOpenGlossaryModal = (candidate?: CandidateTranslation) => {
    const selection = window.getSelection()?.toString().trim();
    if (selection) {
      const hasJp = /[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FAF]/.test(selection);
      if (hasJp) {
        setGlossarySource(selection);
        setGlossaryTarget('');
      } else {
        setGlossaryTarget(selection);
        setGlossarySource('');
      }
    } else {
      setGlossarySource('');
      setGlossaryTarget('');
    }
    setGlossaryCategory('IT');
    setGlossaryScope('project');
    setShowGlossaryModal(true);
  };

  // Save to Glossary
  const handleSaveGlossary = async () => {
    if (!glossarySource.trim() || !glossaryTarget.trim()) {
      toast.warning('Vui lòng nhập cả từ gốc và từ dịch!');
      return;
    }
    setIsSavingGlossary(true);
    try {
      await apiClient.createGlossaryTerm({
        source_term: glossarySource.trim(),
        target_term: glossaryTarget.trim(),
        source_language: direction === 'vi-ja' ? 'vi' : 'ja',
        target_language: direction === 'vi-ja' ? 'ja' : 'vi',
        category: glossaryCategory.trim() || 'IT',
        scope: glossaryScope,
        project_id: glossaryScope === 'project' ? (activeProject?.id || null) : null,
        is_active: true
      });
      toast.success(`Đã lưu thuật ngữ "${glossarySource.trim()}" vào Glossary!`);
      setShowGlossaryModal(false);
      setGlossarySource('');
      setGlossaryTarget('');
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || err.message, 'Lỗi khi lưu thuật ngữ');
    } finally {
      setIsSavingGlossary(false);
    }
  };

  return (
    <div className="flex-1 flex flex-col h-screen overflow-hidden bg-slate-950">
      {/* Top Toolbar */}
      <div className="px-6 py-3 border-b border-slate-800/80 bg-slate-900/50 flex flex-wrap items-center justify-between gap-3">
        {/* Project Selector */}
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1.5 text-xs text-slate-400">
            <span className="font-semibold text-slate-300">Project:</span>
            <select
              value={activeProject?.id || ''}
              onChange={(e) => {
                const found = projects.find(p => p.id === e.target.value);
                setActiveProject(found || null);
              }}
              className="bg-slate-800 border border-slate-700 text-slate-200 text-xs rounded px-2.5 py-1 focus:outline-none focus:border-sky-500"
            >
              <option value="">Global (No Project)</option>
              {projects.map(p => (
                <option key={p.id} value={p.id}>{p.name} ({p.code})</option>
              ))}
            </select>
          </div>

          <div className="h-4 w-px bg-slate-800" />

          {/* Direction Toggle */}
          <div className="flex items-center bg-slate-800/80 rounded-md p-0.5 border border-slate-700">
            <button
              onClick={() => setDirection('ja-vi')}
              className={`px-2.5 py-1 rounded text-xs font-medium transition-colors ${
                direction === 'ja-vi' ? 'bg-sky-600 text-white' : 'text-slate-400 hover:text-white'
              }`}
            >
              Japanese → Vietnamese
            </button>
            <button
              onClick={() => setDirection('vi-ja')}
              className={`px-2.5 py-1 rounded text-xs font-medium transition-colors ${
                direction === 'vi-ja' ? 'bg-sky-600 text-white' : 'text-slate-400 hover:text-white'
              }`}
            >
              Vietnamese → Japanese
            </button>
            <button
              onClick={() => setDirection('auto')}
              className={`px-2.5 py-1 rounded text-xs font-medium transition-colors ${
                direction === 'auto' ? 'bg-sky-600 text-white' : 'text-slate-400 hover:text-white'
              }`}
            >
              Auto
            </button>
          </div>

          <div className="h-4 w-px bg-slate-800" />

          {/* Style Selector */}
          <div className="flex items-center gap-1.5 text-xs text-slate-400">
            <span className="font-semibold text-slate-300">Style:</span>
            <select
              value={style}
              onChange={(e) => setStyle(e.target.value)}
              className="bg-slate-800 border border-slate-700 text-slate-200 text-xs rounded px-2.5 py-1 focus:outline-none focus:border-sky-500"
            >
              <option value="auto">Auto / Smart Context</option>
              <option value="business">Business (Doanh nghiệp chuẩn)</option>
              <option value="technical">Technical (Kỹ thuật chính xác)</option>
              <option value="very_polite">Very Polite (Kính ngữ cao)</option>
              <option value="natural">Natural (Tự nhiên lưu loát)</option>
              <option value="concise">Concise (Ngắn gọn súc tích)</option>
              <option value="customer_facing">Customer-facing (Giao tiếp khách hàng)</option>
              <option value="internal">Internal (Nội bộ nhóm phát triển)</option>
              <option value="casual">Casual (Thân mật)</option>
            </select>
          </div>
        </div>

        {/* Split AI Provider & Searchable Model Combobox */}
        <ProviderModelSelector
          providers={providers}
          selectedProvider={selectedProvider}
          onChangeProvider={setSelectedProvider}
          selectedModel={selectedModel}
          onChangeModel={setSelectedModel}
          allowAutoRouter={true}
          layout="inline"
        />
      </div>

      {/* Main Translation Grid */}
      <div className="flex-1 grid grid-cols-1 lg:grid-cols-2 gap-4 p-4 overflow-y-auto">
        {/* Source Column */}
        <div className="flex flex-col rounded-xl border border-slate-800 bg-slate-900/60 shadow-lg overflow-hidden">
          {/* Header */}
          <div className="px-4 py-2.5 border-b border-slate-800 flex items-center justify-between text-xs text-slate-400 bg-slate-900/90">
            <span className="font-semibold text-slate-200 uppercase tracking-wider text-[11px] flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-sky-400" />
              Source ({direction === 'vi-ja' ? 'Vietnamese' : 'Japanese'})
            </span>
            <div className="flex items-center gap-3">
              <span className="text-[11px] font-mono text-slate-500">{sourceText.length} chars</span>
              {sourceText && (
                <button
                  onClick={() => setSourceText('')}
                  className="hover:text-rose-400 transition-colors p-1"
                  title="Clear text"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              )}
            </div>
          </div>

          {/* Text Area */}
          <div className="flex-1 p-4 relative">
            <textarea
              value={sourceText}
              onChange={(e) => setSourceText(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Paste Japanese requirement, bug report, or message here... (e.g. この件は対象外です。)"
              className="w-full h-full min-h-[260px] bg-transparent text-slate-100 placeholder-slate-500 text-sm leading-relaxed resize-none focus:outline-none font-sans"
            />
          </div>

          {/* Action Footer */}
          <div className="p-3 border-t border-slate-800 bg-slate-900/90 flex items-center justify-between">
            <div className="flex items-center gap-2">
              {activeProject && (
                <span className="text-[11px] text-sky-400/90 bg-sky-950/40 border border-sky-800/40 px-2 py-0.5 rounded flex items-center gap-1">
                  <BookOpen className="w-3 h-3" />
                  {activeProject.name} rules active
                </span>
              )}
            </div>

            <div className="flex items-center gap-2">
              <button
                onClick={handleOpenReplyModal}
                disabled={!sourceText.trim() || isLoading}
                className="px-3 py-1.5 rounded-lg border border-slate-700 bg-slate-800 hover:bg-slate-750 text-slate-200 text-xs font-medium flex items-center gap-1.5 transition-colors disabled:opacity-40"
              >
                <MessageSquareReply className="w-3.5 h-3.5 text-sky-400" />
                Reply Suggestion
              </button>

              <button
                onClick={handleTranslate}
                disabled={!sourceText.trim() || isLoading}
                className={`px-4 py-1.5 rounded-lg bg-gradient-to-r from-sky-500 to-indigo-600 hover:from-sky-400 hover:to-indigo-500 text-white text-xs font-semibold flex items-center gap-2 shadow-md shadow-sky-600/30 transition-all disabled:opacity-50 ${isLoading ? 'btn-loading-shimmer shadow-sky-500/50' : ''}`}
              >
                {isLoading ? (
                  <>
                    <div className="w-3.5 h-3.5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                    <span>Translating with AI...</span>
                  </>
                ) : (
                  <>
                    <Sparkles className="w-3.5 h-3.5" />
                    <span>Translate</span>
                    <span className="text-[10px] text-sky-200 font-mono opacity-80">(Ctrl+Enter)</span>
                  </>
                )}
              </button>
            </div>
          </div>
        </div>

        {/* Translation Output Column */}
        <div className="flex flex-col rounded-xl border border-slate-800 bg-slate-900/60 shadow-lg overflow-hidden">
          {/* Output Header */}
          <div className="px-4 py-2.5 border-b border-slate-800 flex items-center justify-between text-xs text-slate-400 bg-slate-900/90">
            <span className="font-semibold text-slate-200 uppercase tracking-wider text-[11px] flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-emerald-400" />
              Translation ({direction === 'vi-ja' ? 'Japanese' : 'Vietnamese'})
            </span>

            {response && (
              <div className="flex items-center gap-3 text-[11px] text-slate-400 font-mono">
                <span className="flex items-center gap-1">
                  <Cpu className="w-3 h-3 text-sky-400" />
                  {response.provider} ({response.model})
                </span>
                <span className="flex items-center gap-1">
                  <Clock className="w-3 h-3 text-slate-500" />
                  {response.latency_ms}ms
                </span>
              </div>
            )}
          </div>

          {/* Results Area */}
          <div className="flex-1 p-4 overflow-y-auto space-y-4">
            {isLoading && (
              <AiThinkingLoader mode="translate" />
            )}

            {!isLoading && error && (
              <div className="p-3.5 rounded-lg bg-rose-950/40 border border-rose-800/60 text-rose-300 text-xs flex items-start gap-2.5">
                <AlertTriangle className="w-4 h-4 text-rose-400 flex-shrink-0 mt-0.5" />
                <div>
                  <div className="font-semibold mb-0.5">Translation Error</div>
                  <div className="text-rose-200/90">{error}</div>
                </div>
              </div>
            )}

            {/* QA Warnings */}
            {!isLoading && response && response.qa_warnings && response.qa_warnings.length > 0 && (
              <div className="p-3 rounded-lg bg-amber-950/40 border border-amber-800/60 text-amber-300 text-xs space-y-1">
                <div className="font-semibold flex items-center gap-1.5 text-amber-200">
                  <AlertTriangle className="w-3.5 h-3.5 text-amber-400" />
                  Translation QA Notices ({response.qa_warnings.length}):
                </div>
                <ul className="list-disc list-inside space-y-0.5 text-amber-200/90 pl-1">
                  {response.qa_warnings.map((warn, i) => (
                    <li key={i}>{warn}</li>
                  ))}
                </ul>
              </div>
            )}

            {/* Ambiguity Alert Notice */}
            {!isLoading && response && response.ambiguity_detected && (
              <div className="p-3 rounded-lg bg-indigo-950/40 border border-indigo-800/60 text-indigo-300 text-xs">
                <div className="font-semibold flex items-center gap-1.5 text-indigo-200 mb-1">
                  <Layers className="w-3.5 h-3.5 text-indigo-400" />
                  Multiple Interpretations Detected (Ambiguity)
                </div>
                <p className="text-indigo-200/80">
                  {response.ambiguity_reason || 'The source text has multiple valid business or technical nuances. Review the candidate options below.'}
                </p>
              </div>
            )}

            {/* Candidates */}
            {!isLoading && response && response.translations.map((candidate, idx) => (
              <div
                key={idx}
                className={`p-4 rounded-xl border transition-all ${
                  idx === 0
                    ? 'border-slate-700 bg-slate-850/80 shadow-md'
                    : 'border-slate-800/80 bg-slate-900/40 hover:border-slate-700'
                }`}
              >
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-semibold px-2 py-0.5 rounded bg-slate-700/80 text-slate-200 font-mono">
                      Option {idx + 1}
                    </span>
                    <span className="text-[11px] font-medium uppercase tracking-wider px-2 py-0.5 rounded bg-sky-950/80 text-sky-300 border border-sky-800/40">
                      {candidate.style}
                    </span>
                    <span className="text-[11px] text-slate-400 font-mono">
                      Confidence: {Math.round(candidate.confidence * 100)}%
                    </span>
                  </div>

                  {/* Actions */}
                  <div className="flex items-center gap-1.5">
                    <button
                      onClick={() => copyToClipboard(candidate.text, idx)}
                      className="p-1.5 rounded-md hover:bg-slate-700 text-slate-400 hover:text-white transition-colors"
                      title="Copy to clipboard"
                    >
                      {copiedIndex === idx ? (
                        <Check className="w-4 h-4 text-emerald-400" />
                      ) : (
                        <Copy className="w-4 h-4" />
                      )}
                    </button>
                    <button
                      onClick={() => handleExplain(candidate)}
                      className="p-1.5 rounded-md hover:bg-slate-700 text-slate-400 hover:text-white transition-colors"
                      title="Explain translation nuances"
                    >
                      <HelpCircle className="w-4 h-4 text-sky-400" />
                    </button>
                    <button
                      onClick={() => {
                        setCorrectingCandidate(candidate);
                        setCorrectionInput(candidate.text);
                      }}
                      className="p-1.5 rounded-md hover:bg-slate-700 text-slate-400 hover:text-white transition-colors"
                      title="Edit / Teach correction"
                    >
                      <Edit3 className="w-4 h-4 text-amber-400" />
                    </button>
                    <button
                      onClick={() => handleOpenGlossaryModal(candidate)}
                      className="p-1.5 rounded-md hover:bg-slate-700 text-slate-400 hover:text-emerald-400 transition-colors"
                      title="Lưu thuật ngữ vào Glossary"
                    >
                      <BookPlus className="w-4 h-4 text-emerald-400" />
                    </button>
                  </div>
                </div>

                <p className="text-slate-100 text-sm leading-relaxed whitespace-pre-wrap font-sans">
                  {candidate.text}
                </p>

                {candidate.reason && (
                  <div className="mt-2.5 pt-2 border-t border-slate-800/80 text-[11px] text-slate-400 italic">
                    Reason: {candidate.reason}
                  </div>
                )}
              </div>
            ))}

            {!response && !isLoading && (
              <div className="h-full min-h-[220px] flex flex-col items-center justify-center text-slate-500 text-center p-6">
                <Sparkles className="w-8 h-8 mb-2 opacity-30 text-sky-400" />
                <p className="text-xs font-medium">Ready to translate with project context and glossary.</p>
                <p className="text-[11px] text-slate-600 mt-1">
                  Type or paste Japanese text and press Translate.
                </p>
              </div>
            )}
          </div>

          {/* Applied Glossaries and TM tags */}
          {response && (
            <div className="p-3 border-t border-slate-800 bg-slate-900/90 text-xs flex flex-wrap items-center gap-2">
              <span className="text-[11px] text-slate-500 uppercase tracking-wider font-semibold">
                Context Applied:
              </span>
              {response.used_glossary.map((g, i) => (
                <span
                  key={i}
                  className="px-2 py-0.5 rounded-md bg-emerald-950/60 border border-emerald-800/40 text-emerald-300 text-[11px] flex items-center gap-1 font-mono"
                  title={`Glossary term: ${g.source_term} -> ${g.target_term}`}
                >
                  <BookOpen className="w-3 h-3 text-emerald-400" />
                  {g.source_term} → {g.target_term}
                </span>
              ))}
              {response.used_memory.map((m, i) => (
                <span
                  key={i}
                  className="px-2 py-0.5 rounded-md bg-indigo-950/60 border border-indigo-800/40 text-indigo-300 text-[11px] flex items-center gap-1 font-mono"
                  title={`Translation memory similarity: ${m.similarity}`}
                >
                  <Layers className="w-3 h-3 text-indigo-400" />
                  TM Match ({Math.round(m.similarity * 100)}%)
                </span>
              ))}
              <button
                onClick={() => handleOpenGlossaryModal()}
                className="ml-auto px-2 py-0.5 rounded-md bg-emerald-500/10 hover:bg-emerald-500/20 border border-emerald-500/30 text-emerald-300 text-[11px] font-medium flex items-center gap-1 transition-colors"
                title="Thêm thuật ngữ mới vào Glossary"
              >
                <BookPlus className="w-3 h-3 text-emerald-400" />
                <span>+ Thêm thuật ngữ</span>
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Explanation Drawer / Modal */}
      {explainData && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-700 rounded-xl max-w-lg w-full p-5 shadow-2xl space-y-4">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <h3 className="text-sm font-semibold text-white flex items-center gap-2">
                <HelpCircle className="w-4 h-4 text-sky-400" />
                Translation Explanation & Nuance
              </h3>
              <button
                onClick={() => setExplainData(null)}
                className="text-slate-400 hover:text-white text-xs"
              >
                ✕ Close
              </button>
            </div>

            <div className="space-y-3 text-xs text-slate-300 max-h-[70vh] overflow-y-auto pr-1">
              <div>
                <span className="font-semibold text-slate-200 block mb-1">Summary:</span>
                <p className="text-slate-300 bg-slate-850 p-2.5 rounded border border-slate-800">
                  {explainData.summary}
                </p>
              </div>

              {explainData.grammar_and_nuances && explainData.grammar_and_nuances.length > 0 && (
                <div>
                  <span className="font-semibold text-slate-200 block mb-1">Grammar & Business Nuances:</span>
                  <ul className="list-disc list-inside space-y-1 bg-slate-850 p-2.5 rounded border border-slate-800">
                    {explainData.grammar_and_nuances.map((n: string, i: number) => (
                      <li key={i}>{n}</li>
                    ))}
                  </ul>
                </div>
              )}

              {explainData.technical_terms && explainData.technical_terms.length > 0 && (
                <div>
                  <span className="font-semibold text-slate-200 block mb-1">Technical Terminology:</span>
                  <div className="space-y-1.5">
                    {explainData.technical_terms.map((t: any, i: number) => (
                      <div key={i} className="p-2 rounded bg-slate-850 border border-slate-800">
                        <span className="font-semibold text-sky-400">{t.term}:</span> {t.explanation}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Reply Drawer / Modal */}
      {showReplyModal && (
        <div className="fixed inset-0 bg-black/70 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-700/90 rounded-2xl max-w-2xl w-full p-6 shadow-2xl space-y-4 animate-in fade-in zoom-in-95 duration-150">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <h3 className="text-sm font-semibold text-white flex items-center gap-2">
                <MessageSquareReply className="w-4 h-4 text-sky-400" />
                Reply Suggestion (Soạn phản hồi đối ứng khách hàng)
              </h3>
              <button
                onClick={() => setShowReplyModal(false)}
                className="text-slate-400 hover:text-white text-xs p-1"
              >
                ✕
              </button>
            </div>

            {/* Incoming Message Summary */}
            <div className="p-2.5 rounded-lg bg-slate-950/70 border border-slate-800 text-xs">
              <span className="text-[11px] font-semibold text-slate-400 block mb-1">
                Tin nhắn nhận được từ khách (Incoming Message):
              </span>
              <p className="text-slate-300 line-clamp-2 italic font-mono text-[11px]">
                "{sourceText}"
              </p>
            </div>

            {/* User Reply Intent Field */}
            <div className="space-y-1.5">
              <div className="flex items-center justify-between">
                <label className="text-xs font-semibold text-slate-200 flex items-center gap-1.5">
                  <Sparkles className="w-3.5 h-3.5 text-sky-400" />
                  Ý chính bạn muốn trả lời (Your Reply Intent):
                </label>
                <span className="text-[10px] text-slate-400">Gõ tiếng Việt hoặc tiếng Nhật thô</span>
              </div>
              <div className="flex gap-2">
                <input
                  type="text"
                  value={userReplyIntent}
                  onChange={(e) => setUserReplyIntent(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && !isReplying) {
                      e.preventDefault();
                      handleGenerateReply();
                    }
                  }}
                  placeholder="Ví dụ: Dự kiến 17h xong, do dev đang sửa API và test lại staging..."
                  className="flex-1 bg-slate-850 border border-slate-700 rounded-lg px-3 py-2 text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:border-sky-500"
                />
                <button
                  onClick={handleGenerateReply}
                  disabled={isReplying}
                  className="px-3.5 py-2 rounded-lg bg-sky-600 hover:bg-sky-500 disabled:opacity-50 text-white text-xs font-medium flex items-center gap-1.5 transition whitespace-nowrap"
                >
                  {isReplying ? (
                    <>
                      <div className="w-3 h-3 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                      <span>Đang tạo...</span>
                    </>
                  ) : (
                    <>
                      <Send className="w-3 h-3" />
                      <span>Tạo câu trả lời</span>
                    </>
                  )}
                </button>
              </div>
            </div>

            {/* Reply Options List */}
            <div className="space-y-3 max-h-[50vh] overflow-y-auto pr-1">
              {isReplying && !replyData && (
                <div className="py-8 flex flex-col items-center justify-center text-slate-400 gap-2">
                  <div className="w-5 h-5 border-2 border-sky-400/30 border-t-sky-400 rounded-full animate-spin" />
                  <span className="text-xs">AI đang soạn các phương án phản hồi bằng Business Keigo...</span>
                </div>
              )}

              {replyData && replyData.options && (
                replyData.options.map((opt: any, i: number) => (
                  <div key={i} className="p-3.5 rounded-xl border border-slate-800 bg-slate-850/90 space-y-2 hover:border-slate-700 transition">
                    <div className="flex items-center justify-between">
                      <span className="text-[11px] font-semibold uppercase px-2 py-0.5 rounded bg-sky-950 text-sky-300 border border-sky-800/40">
                        {opt.style}
                      </span>
                      <div className="flex items-center gap-2">
                        <button
                          onClick={() => setEditingReplyIndex(editingReplyIndex === i ? null : i)}
                          className="text-xs text-slate-400 hover:text-amber-400 flex items-center gap-1 p-1"
                          title="Chỉnh sửa câu này"
                        >
                          <Edit3 className="w-3.5 h-3.5" />
                          <span>{editingReplyIndex === i ? 'Xong' : 'Sửa'}</span>
                        </button>
                        <button
                          onClick={() => {
                            navigator.clipboard.writeText(opt.text);
                            toast.success('Đã sao chép phản hồi vào clipboard');
                          }}
                          className="text-xs text-sky-400 hover:text-sky-300 flex items-center gap-1 p-1 font-medium"
                          title="Copy vào clipboard"
                        >
                          <Copy className="w-3.5 h-3.5" />
                          <span>Copy</span>
                        </button>
                      </div>
                    </div>

                    {editingReplyIndex === i ? (
                      <textarea
                        value={opt.text}
                        onChange={(e) => {
                          const updated = [...replyData.options];
                          updated[i] = { ...updated[i], text: e.target.value };
                          setReplyData({ ...replyData, options: updated });
                        }}
                        className="w-full h-20 bg-slate-900 border border-sky-500 rounded p-2 text-xs text-slate-100 font-sans focus:outline-none"
                      />
                    ) : (
                      <p className="text-xs text-slate-100 whitespace-pre-wrap leading-relaxed font-sans">
                        {opt.text}
                      </p>
                    )}

                    {opt.notes && (
                      <p className="text-[10px] text-slate-400 italic">When to use: {opt.notes}</p>
                    )}
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      )}

      {/* Correction Learning Modal */}
      {correctingCandidate && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-700 rounded-xl max-w-lg w-full p-5 shadow-2xl space-y-4">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <h3 className="text-sm font-semibold text-white flex items-center gap-2">
                <Edit3 className="w-4 h-4 text-amber-400" />
                Teach AI Correction (Continuous Learning)
              </h3>
              <button
                onClick={() => setCorrectingCandidate(null)}
                className="text-slate-400 hover:text-white text-xs"
              >
                ✕ Cancel
              </button>
            </div>

            <div className="space-y-3 text-xs">
              <div>
                <label className="text-slate-400 block mb-1">Source Text:</label>
                <div className="p-2 rounded bg-slate-850 text-slate-300 border border-slate-800">
                  {sourceText}
                </div>
              </div>

              <div>
                <label className="text-slate-400 block mb-1">Original AI Output:</label>
                <div className="p-2 rounded bg-slate-850 text-slate-400 border border-slate-800 line-through">
                  {correctingCandidate.text}
                </div>
              </div>

              <div>
                <label className="text-slate-200 font-semibold block mb-1">
                  Your Corrected / Preferred Translation:
                </label>
                <textarea
                  value={correctionInput}
                  onChange={(e) => setCorrectionInput(e.target.value)}
                  className="w-full h-24 bg-slate-850 border border-slate-700 rounded p-2.5 text-slate-100 focus:outline-none focus:border-amber-400 text-xs leading-relaxed"
                  placeholder="Enter the ideal translation..."
                />
              </div>

              <div>
                <label className="text-slate-300 font-medium block mb-1">Remember this correction:</label>
                <div className="flex items-center gap-4 text-slate-300">
                  <label className="flex items-center gap-1.5 cursor-pointer">
                    <input
                      type="radio"
                      name="scope"
                      checked={correctionScope === 'project'}
                      onChange={() => setCorrectionScope('project')}
                    />
                    <span>For this project only</span>
                  </label>
                  <label className="flex items-center gap-1.5 cursor-pointer">
                    <input
                      type="radio"
                      name="scope"
                      checked={correctionScope === 'global'}
                      onChange={() => setCorrectionScope('global')}
                    />
                    <span>Globally for all projects</span>
                  </label>
                </div>
              </div>
            </div>

            <div className="flex items-center justify-end gap-2 pt-2 border-t border-slate-800">
              <button
                onClick={() => setCorrectingCandidate(null)}
                className="px-3 py-1.5 rounded bg-slate-800 text-slate-300 text-xs hover:bg-slate-700"
              >
                Cancel
              </button>
              <button
                onClick={handleSaveCorrection}
                className="px-4 py-1.5 rounded bg-amber-600 hover:bg-amber-500 text-white text-xs font-medium flex items-center gap-1.5"
              >
                {correctionSaved ? (
                  <>
                    <Check className="w-3.5 h-3.5" />
                    Saved to TM & Knowledge!
                  </>
                ) : (
                  <>
                    <BookmarkPlus className="w-3.5 h-3.5" />
                    Save & Teach AI
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Quick Add to Glossary Modal */}
      {showGlossaryModal && (
        <div className="fixed inset-0 bg-black/70 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-700/80 rounded-2xl max-w-md w-full p-6 shadow-2xl space-y-4 animate-in fade-in zoom-in-95 duration-150">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <h3 className="text-sm font-semibold text-white flex items-center gap-2">
                <BookPlus className="w-4 h-4 text-emerald-400" />
                Thêm nhanh vào Glossary
              </h3>
              <button
                onClick={() => setShowGlossaryModal(false)}
                className="text-slate-400 hover:text-white text-xs p-1"
              >
                ✕
              </button>
            </div>

            <div className="space-y-3.5 text-xs">
              <div>
                <label className="text-slate-300 font-medium block mb-1.5 flex items-center justify-between">
                  <span>Source Term (Từ gốc tiếng Nhật):</span>
                  <span className="text-[10px] text-amber-400/80 font-mono">Bắt buộc</span>
                </label>
                <input
                  type="text"
                  value={glossarySource}
                  onChange={(e) => setGlossarySource(e.target.value)}
                  placeholder="Ví dụ: 解約, 認証, 本番環境..."
                  className="w-full bg-slate-850 border border-slate-700 rounded-lg p-2.5 text-slate-100 focus:outline-none focus:border-emerald-500 text-xs"
                />
              </div>

              <div>
                <label className="text-slate-300 font-medium block mb-1.5 flex items-center justify-between">
                  <span>Target Term (Nghĩa dịch chuẩn):</span>
                  <span className="text-[10px] text-amber-400/80 font-mono">Bắt buộc</span>
                </label>
                <input
                  type="text"
                  value={glossaryTarget}
                  onChange={(e) => setGlossaryTarget(e.target.value)}
                  placeholder="Ví dụ: Chấm dứt hợp đồng, Authentication..."
                  className="w-full bg-slate-850 border border-slate-700 rounded-lg p-2.5 text-slate-100 focus:outline-none focus:border-emerald-500 text-xs"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-slate-300 font-medium block mb-1.5">Category:</label>
                  <select
                    value={glossaryCategory}
                    onChange={(e) => setGlossaryCategory(e.target.value)}
                    className="w-full bg-slate-850 border border-slate-700 rounded-lg p-2 text-slate-200 focus:outline-none focus:border-emerald-500 text-xs"
                  >
                    <option value="IT">IT / Kỹ thuật</option>
                    <option value="UI">UI / Màn hình</option>
                    <option value="Banking">Banking / Tài chính</option>
                    <option value="Business">Business / Nghiệp vụ</option>
                    <option value="General">General / Chung</option>
                  </select>
                </div>

                <div>
                  <label className="text-slate-300 font-medium block mb-1.5">Scope (Phạm vi):</label>
                  <select
                    value={glossaryScope}
                    onChange={(e) => setGlossaryScope(e.target.value as 'project' | 'global')}
                    className="w-full bg-slate-850 border border-slate-700 rounded-lg p-2 text-slate-200 focus:outline-none focus:border-emerald-500 text-xs"
                  >
                    <option value="project">Project {activeProject ? `(${activeProject.name})` : ''}</option>
                    <option value="global">Global (Mọi dự án)</option>
                  </select>
                </div>
              </div>
            </div>

            <div className="flex items-center justify-end gap-2 pt-3 border-t border-slate-800">
              <button
                onClick={() => setShowGlossaryModal(false)}
                className="px-3.5 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs transition"
              >
                Hủy
              </button>
              <button
                onClick={handleSaveGlossary}
                disabled={isSavingGlossary}
                className="px-4 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white text-xs font-medium flex items-center gap-1.5 transition"
              >
                <Check className="w-3.5 h-3.5" />
                <span>{isSavingGlossary ? 'Đang lưu...' : 'Lưu vào Glossary'}</span>
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
