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
  BookPlus,
  RotateCcw
} from 'lucide-react';
import { apiClient } from '../api/client';
import { Project, TranslationResponse, CandidateTranslation } from '../types';
import { useToast } from '../context/ToastContext';
import { AiThinkingLoader } from '../components/skeletons/AiThinkingLoader';
import { ProviderModelSelector } from '../components/ProviderModelSelector';
import { getSavedProvider, getSavedModel, resolveHealthyModel } from '../utils/aiPreferences';
import { Button, Badge, Modal, EmptyState, Select } from '../components/ui';

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
    <div className="flex-1 flex flex-col h-full overflow-hidden bg-canvas">
      {/* Top Workspace Toolbar */}
      <div className="px-4 sm:px-6 py-2.5 border-b border-border-subtle bg-surface/70 backdrop-blur-sm flex flex-wrap items-center justify-between gap-3 flex-shrink-0">
        <div className="flex items-center gap-3 flex-wrap">
          {/* Direction Toggle */}
          <div className="flex items-center bg-surface-subtle rounded-lg p-0.5 border border-border-subtle">
            <button
              type="button"
              onClick={() => setDirection('ja-vi')}
              className={`px-3 py-1 rounded-md text-xs font-medium transition-all ${
                direction === 'ja-vi'
                  ? 'bg-surface-elevated text-primary font-semibold shadow-subtle border border-border-subtle'
                  : 'text-text-secondary hover:text-text-primary'
              }`}
            >
              JA → VI
            </button>
            <button
              type="button"
              onClick={() => setDirection('vi-ja')}
              className={`px-3 py-1 rounded-md text-xs font-medium transition-all ${
                direction === 'vi-ja'
                  ? 'bg-surface-elevated text-primary font-semibold shadow-subtle border border-border-subtle'
                  : 'text-text-secondary hover:text-text-primary'
              }`}
            >
              VI → JA
            </button>
            <button
              type="button"
              onClick={() => setDirection('auto')}
              className={`px-2.5 py-1 rounded-md text-xs font-medium transition-all ${
                direction === 'auto'
                  ? 'bg-surface-elevated text-primary font-semibold shadow-subtle border border-border-subtle'
                  : 'text-text-secondary hover:text-text-primary'
              }`}
            >
              Auto
            </button>
          </div>

          <div className="h-4 w-px bg-border-subtle hidden sm:block" />

          {/* Style Selector */}
          <div className="flex items-center gap-1.5 text-xs text-text-secondary">
            <span className="font-medium shrink-0">Văn phong:</span>
            <Select
              value={style}
              onChange={(val) => setStyle(val)}
              size="sm"
              triggerClassName="min-w-[135px]"
              options={[
                { value: 'auto', label: 'Tự động' },
                { value: 'business', label: 'Thương mại' },
                { value: 'technical', label: 'Kỹ thuật' },
                { value: 'very_polite', label: 'Kính ngữ' },
                { value: 'natural', label: 'Tự nhiên' },
                { value: 'concise', label: 'Súc tích' },
                { value: 'customer_facing', label: 'Khách hàng' },
                { value: 'internal', label: 'Nội bộ' },
                { value: 'casual', label: 'Thân mật' },
              ]}
            />
          </div>
        </div>

        {/* AI Provider & Searchable Model Combobox */}
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

      {/* Main Translation Grid: Source (Left) | Output (Right) */}
      <div className="flex-1 grid grid-cols-1 lg:grid-cols-2 gap-4 p-4 overflow-y-auto min-h-0">
        {/* Source Column */}
        <div className="flex flex-col rounded-xl border border-border-subtle bg-surface shadow-subtle overflow-hidden">
          {/* Header */}
          <div className="px-4 py-2.5 border-b border-border-subtle flex items-center justify-between text-xs bg-surface-subtle/50">
            <span className="font-semibold text-text-primary uppercase tracking-wider text-[11px] flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-primary" />
              Source ({direction === 'vi-ja' ? 'Vietnamese' : 'Japanese'})
            </span>
            <div className="flex items-center gap-3">
              <span className="text-[11px] font-mono text-text-muted">{sourceText.length} chars</span>
              {sourceText && (
                <button
                  type="button"
                  onClick={() => setSourceText('')}
                  className="hover:text-rose-500 text-text-muted transition-colors p-1"
                  title="Clear text"
                  aria-label="Clear source text"
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
              className="w-full h-full min-h-[260px] bg-transparent text-text-primary placeholder:text-text-muted text-sm leading-relaxed resize-none focus:outline-none font-sans"
            />
          </div>

          {/* Action Footer */}
          <div className="p-3 border-t border-border-subtle bg-surface-subtle/30 flex items-center justify-between gap-3">
            <div className="flex items-center gap-2 min-w-0">
              {activeProject && (
                <Badge variant="primary" size="sm" className="truncate">
                  <BookOpen className="w-3 h-3 mr-1" />
                  {activeProject.name} rules active
                </Badge>
              )}
            </div>

            <div className="flex items-center gap-2 flex-shrink-0">
              <Button
                variant="secondary"
                size="sm"
                onClick={handleOpenReplyModal}
                disabled={!sourceText.trim() || isLoading}
                leftIcon={<MessageSquareReply className="w-3.5 h-3.5 text-primary" />}
              >
                Reply Suggestion
              </Button>

              <Button
                variant="primary"
                size="sm"
                onClick={handleTranslate}
                disabled={!sourceText.trim() || isLoading}
                isLoading={isLoading}
                leftIcon={<Sparkles className="w-3.5 h-3.5" />}
              >
                <span>Translate</span>
                <span className="text-[10px] text-white/70 font-mono hidden sm:inline">(Ctrl+Enter)</span>
              </Button>
            </div>
          </div>
        </div>

        {/* Translation Output Column */}
        <div className="flex flex-col rounded-xl border border-border-subtle bg-surface shadow-subtle overflow-hidden">
          {/* Output Header */}
          <div className="px-4 py-2.5 border-b border-border-subtle flex items-center justify-between text-xs bg-surface-subtle/50">
            <span className="font-semibold text-text-primary uppercase tracking-wider text-[11px] flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-emerald-500" />
              Translation ({direction === 'vi-ja' ? 'Japanese' : 'Vietnamese'})
            </span>

            {response && (
              <div className="flex items-center gap-3 text-[11px] text-text-muted font-mono">
                <span className="flex items-center gap-1">
                  <Cpu className="w-3 h-3 text-primary" />
                  {response.provider} ({response.model})
                </span>
                <span className="flex items-center gap-1">
                  <Clock className="w-3 h-3 text-text-muted" />
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
              <div className="p-3.5 rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-600 dark:text-rose-400 text-xs flex items-start gap-2.5">
                <AlertTriangle className="w-4 h-4 text-rose-500 flex-shrink-0 mt-0.5" />
                <div>
                  <div className="font-semibold mb-0.5">Translation Error</div>
                  <div className="text-rose-500/90 leading-relaxed">{error}</div>
                </div>
              </div>
            )}

            {/* QA Warnings */}
            {!isLoading && response && response.qa_warnings && response.qa_warnings.length > 0 && (
              <div className="p-3 rounded-lg bg-amber-500/10 border border-amber-500/20 text-amber-700 dark:text-amber-300 text-xs space-y-1">
                <div className="font-semibold flex items-center gap-1.5">
                  <AlertTriangle className="w-3.5 h-3.5 text-amber-500" />
                  Translation QA Notices ({response.qa_warnings.length}):
                </div>
                <ul className="list-disc list-inside space-y-0.5 text-amber-600 dark:text-amber-400 pl-1">
                  {response.qa_warnings.map((warn, i) => (
                    <li key={i}>{warn}</li>
                  ))}
                </ul>
              </div>
            )}

            {/* Ambiguity Alert Notice */}
            {!isLoading && response && response.ambiguity_detected && (
              <div className="p-3 rounded-lg bg-primary/10 border border-primary/20 text-primary text-xs">
                <div className="font-semibold flex items-center gap-1.5 mb-1">
                  <Layers className="w-3.5 h-3.5 text-primary" />
                  Multiple Interpretations Detected (Ambiguity)
                </div>
                <p className="text-text-secondary leading-relaxed">
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
                    ? 'border-border-default bg-surface-elevated shadow-subtle'
                    : 'border-border-subtle bg-surface-subtle/50 hover:border-border-default'
                }`}
              >
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-semibold px-2 py-0.5 rounded bg-surface-hover text-text-primary font-mono border border-border-subtle">
                      Option {idx + 1}
                    </span>
                    <Badge variant="primary" size="sm">
                      {candidate.style}
                    </Badge>
                    <span className="text-[11px] text-text-muted font-mono">
                      Confidence: {Math.round(candidate.confidence * 100)}%
                    </span>
                  </div>

                  {/* Candidate Action Buttons */}
                  <div className="flex items-center gap-1">
                    <button
                      type="button"
                      onClick={() => copyToClipboard(candidate.text, idx)}
                      className="p-1.5 rounded-md hover:bg-surface-hover text-text-muted hover:text-text-primary transition-colors"
                      title="Copy to clipboard"
                      aria-label="Copy translation"
                    >
                      {copiedIndex === idx ? (
                        <Check className="w-4 h-4 text-emerald-500" />
                      ) : (
                        <Copy className="w-4 h-4" />
                      )}
                    </button>
                    <button
                      type="button"
                      onClick={() => handleExplain(candidate)}
                      className="p-1.5 rounded-md hover:bg-surface-hover text-text-muted hover:text-primary transition-colors"
                      title="Explain translation nuances"
                      aria-label="Explain nuance"
                    >
                      <HelpCircle className="w-4 h-4" />
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        setCorrectingCandidate(candidate);
                        setCorrectionInput(candidate.text);
                      }}
                      className="p-1.5 rounded-md hover:bg-surface-hover text-text-muted hover:text-amber-500 transition-colors"
                      title="Edit / Teach correction"
                      aria-label="Teach correction"
                    >
                      <Edit3 className="w-4 h-4" />
                    </button>
                    <button
                      type="button"
                      onClick={() => handleOpenGlossaryModal(candidate)}
                      className="p-1.5 rounded-md hover:bg-surface-hover text-text-muted hover:text-emerald-500 transition-colors"
                      title="Lưu thuật ngữ vào Glossary"
                      aria-label="Add to glossary"
                    >
                      <BookPlus className="w-4 h-4" />
                    </button>
                  </div>
                </div>

                <p className="text-text-primary text-sm leading-relaxed whitespace-pre-wrap font-sans">
                  {candidate.text}
                </p>

                {candidate.reason && (
                  <div className="mt-2.5 pt-2 border-t border-border-subtle text-[11px] text-text-muted italic">
                    Reason: {candidate.reason}
                  </div>
                )}
              </div>
            ))}

            {!response && !isLoading && (
              <EmptyState
                icon={<Sparkles className="w-6 h-6 text-primary" />}
                title="Ready for Translation"
                description="Input Japanese or Vietnamese text, select your desired style and provider, and execute translation."
              />
            )}
          </div>

          {/* Applied Glossaries and TM tags */}
          {response && (
            <div className="p-3 border-t border-border-subtle bg-surface-subtle/50 text-xs flex flex-wrap items-center gap-2">
              <span className="text-[11px] text-text-muted uppercase tracking-wider font-semibold">
                Context Applied:
              </span>
              {response.used_glossary.map((g, i) => (
                <span
                  key={i}
                  className="px-2 py-0.5 rounded-md bg-emerald-500/10 border border-emerald-500/20 text-emerald-600 dark:text-emerald-400 text-[11px] flex items-center gap-1 font-mono"
                  title={`Glossary term: ${g.source_term} -> ${g.target_term}`}
                >
                  <BookOpen className="w-3 h-3 text-emerald-500" />
                  {g.source_term} → {g.target_term}
                </span>
              ))}
              {response.used_memory.map((m, i) => (
                <span
                  key={i}
                  className="px-2 py-0.5 rounded-md bg-indigo-500/10 border border-indigo-500/20 text-indigo-600 dark:text-indigo-400 text-[11px] flex items-center gap-1 font-mono"
                  title={`Translation memory similarity: ${m.similarity}`}
                >
                  <Layers className="w-3 h-3 text-indigo-500" />
                  TM Match ({Math.round(m.similarity * 100)}%)
                </span>
              ))}
              <Button
                variant="ghost"
                size="sm"
                onClick={() => handleOpenGlossaryModal()}
                className="ml-auto text-emerald-600 dark:text-emerald-400"
                leftIcon={<BookPlus className="w-3 h-3" />}
              >
                + Thêm thuật ngữ
              </Button>
            </div>
          )}
        </div>
      </div>

      {/* Explanation Modal */}
      <Modal
        isOpen={Boolean(explainData)}
        onClose={() => setExplainData(null)}
        title={
          <div className="flex items-center gap-2">
            <HelpCircle className="w-4 h-4 text-primary" />
            <span>Translation Explanation & Nuance</span>
          </div>
        }
        size="lg"
      >
        {explainData && (
          <div className="space-y-4 text-xs text-text-secondary">
            <div>
              <span className="font-semibold text-text-primary block mb-1">Summary:</span>
              <p className="text-text-primary bg-surface-subtle p-3 rounded-lg border border-border-subtle leading-relaxed">
                {explainData.summary}
              </p>
            </div>

            {explainData.grammar_and_nuances && explainData.grammar_and_nuances.length > 0 && (
              <div>
                <span className="font-semibold text-text-primary block mb-1">Grammar & Business Nuances:</span>
                <ul className="list-disc list-inside space-y-1 bg-surface-subtle p-3 rounded-lg border border-border-subtle leading-relaxed">
                  {explainData.grammar_and_nuances.map((n: string, i: number) => (
                    <li key={i}>{n}</li>
                  ))}
                </ul>
              </div>
            )}

            {explainData.technical_terms && explainData.technical_terms.length > 0 && (
              <div>
                <span className="font-semibold text-text-primary block mb-1">Technical Terminology:</span>
                <div className="space-y-1.5">
                  {explainData.technical_terms.map((t: any, i: number) => (
                    <div key={i} className="p-2.5 rounded-lg bg-surface-subtle border border-border-subtle">
                      <span className="font-semibold text-primary">{t.term}:</span> {t.explanation}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </Modal>

      {/* Reply Modal */}
      <Modal
        isOpen={showReplyModal}
        onClose={() => setShowReplyModal(false)}
        title={
          <div className="flex items-center gap-2">
            <MessageSquareReply className="w-4 h-4 text-primary" />
            <span>Reply Suggestion (Soạn phản hồi đối ứng khách hàng)</span>
          </div>
        }
        size="2xl"
      >
        <div className="space-y-4">
          {/* Incoming Message Summary */}
          <div className="p-3 rounded-lg bg-surface-subtle border border-border-subtle text-xs">
            <span className="text-[11px] font-semibold text-text-muted block mb-1">
              Tin nhắn nhận được từ khách (Incoming Message):
            </span>
            <p className="text-text-primary italic font-mono text-[11px] line-clamp-3">
              "{sourceText}"
            </p>
          </div>

          {/* User Reply Intent Field */}
          <div className="space-y-1.5">
            <div className="flex items-center justify-between">
              <label className="text-xs font-semibold text-text-primary flex items-center gap-1.5">
                <Sparkles className="w-3.5 h-3.5 text-primary" />
                Ý chính bạn muốn trả lời (Your Reply Intent):
              </label>
              <span className="text-[10px] text-text-muted">Gõ tiếng Việt hoặc tiếng Nhật thô</span>
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
                className="flex-1 bg-surface border border-border-default rounded-lg px-3 py-2 text-xs text-text-primary placeholder:text-text-muted focus:outline-none focus:border-primary"
              />
              <Button
                variant="primary"
                size="sm"
                onClick={handleGenerateReply}
                disabled={isReplying}
                isLoading={isReplying}
                leftIcon={<Send className="w-3.5 h-3.5" />}
              >
                Tạo câu trả lời
              </Button>
            </div>
          </div>

          {/* Reply Options List */}
          <div className="space-y-3 max-h-[50vh] overflow-y-auto pr-1">
            {isReplying && !replyData && (
              <div className="py-8 flex flex-col items-center justify-center text-text-muted gap-2">
                <AiThinkingLoader mode="analyze" />
                <span className="text-xs">AI đang soạn các phương án phản hồi bằng Business Keigo...</span>
              </div>
            )}

            {replyData && replyData.options && (
              replyData.options.map((opt: any, i: number) => (
                <div key={i} className="p-3.5 rounded-xl border border-border-subtle bg-surface-subtle/50 space-y-2 hover:border-border-default transition-colors">
                  <div className="flex items-center justify-between">
                    <Badge variant="primary" size="sm">
                      {opt.style}
                    </Badge>
                    <div className="flex items-center gap-2">
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => setEditingReplyIndex(editingReplyIndex === i ? null : i)}
                        leftIcon={<Edit3 className="w-3 h-3" />}
                      >
                        {editingReplyIndex === i ? 'Xong' : 'Sửa'}
                      </Button>
                      <Button
                        variant="secondary"
                        size="sm"
                        onClick={() => {
                          navigator.clipboard.writeText(opt.text);
                          toast.success('Đã sao chép phản hồi vào clipboard');
                        }}
                        leftIcon={<Copy className="w-3 h-3 text-primary" />}
                      >
                        Copy
                      </Button>
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
                      className="w-full h-20 bg-surface border border-primary rounded-lg p-2 text-xs text-text-primary font-sans focus:outline-none"
                    />
                  ) : (
                    <p className="text-xs text-text-primary whitespace-pre-wrap leading-relaxed font-sans">
                      {opt.text}
                    </p>
                  )}

                  {opt.notes && (
                    <p className="text-[11px] text-text-muted italic">When to use: {opt.notes}</p>
                  )}
                </div>
              ))
            )}
          </div>
        </div>
      </Modal>

      {/* Correction Learning Modal */}
      <Modal
        isOpen={Boolean(correctingCandidate)}
        onClose={() => setCorrectingCandidate(null)}
        title={
          <div className="flex items-center gap-2">
            <Edit3 className="w-4 h-4 text-amber-500" />
            <span>Teach AI Correction (Continuous Learning)</span>
          </div>
        }
        size="lg"
        footer={
          <>
            <Button variant="secondary" size="sm" onClick={() => setCorrectingCandidate(null)}>
              Cancel
            </Button>
            <Button
              variant="primary"
              size="sm"
              onClick={handleSaveCorrection}
              leftIcon={correctionSaved ? <Check className="w-3.5 h-3.5" /> : <BookmarkPlus className="w-3.5 h-3.5" />}
            >
              {correctionSaved ? 'Saved to TM & Knowledge!' : 'Save & Teach AI'}
            </Button>
          </>
        }
      >
        {correctingCandidate && (
          <div className="space-y-3.5 text-xs">
            <div>
              <label className="text-text-muted block mb-1 font-medium">Source Text:</label>
              <div className="p-2.5 rounded-lg bg-surface-subtle text-text-primary border border-border-subtle">
                {sourceText}
              </div>
            </div>

            <div>
              <label className="text-text-muted block mb-1 font-medium">Original AI Output:</label>
              <div className="p-2.5 rounded-lg bg-surface-subtle text-text-muted border border-border-subtle line-through">
                {correctingCandidate.text}
              </div>
            </div>

            <div>
              <label className="text-text-primary font-semibold block mb-1">
                Your Corrected / Preferred Translation:
              </label>
              <textarea
                value={correctionInput}
                onChange={(e) => setCorrectionInput(e.target.value)}
                className="w-full h-24 bg-surface border border-border-default rounded-lg p-2.5 text-text-primary focus:outline-none focus:border-primary text-xs leading-relaxed"
                placeholder="Enter the ideal translation..."
              />
            </div>

            <div>
              <label className="text-text-secondary font-medium block mb-1">Remember this correction:</label>
              <div className="flex items-center gap-4 text-text-secondary">
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
        )}
      </Modal>

      {/* Quick Add to Glossary Modal */}
      <Modal
        isOpen={showGlossaryModal}
        onClose={() => setShowGlossaryModal(false)}
        title={
          <div className="flex items-center gap-2">
            <BookPlus className="w-4 h-4 text-emerald-500" />
            <span>Thêm nhanh vào Glossary</span>
          </div>
        }
        size="md"
        footer={
          <>
            <Button variant="secondary" size="sm" onClick={() => setShowGlossaryModal(false)}>
              Hủy
            </Button>
            <Button
              variant="primary"
              size="sm"
              onClick={handleSaveGlossary}
              disabled={isSavingGlossary}
              isLoading={isSavingGlossary}
              leftIcon={<Check className="w-3.5 h-3.5" />}
            >
              Lưu vào Glossary
            </Button>
          </>
        }
      >
        <div className="space-y-3.5 text-xs">
          <div>
            <label className="text-text-secondary font-medium block mb-1.5 flex items-center justify-between">
              <span>Source Term (Từ gốc tiếng Nhật):</span>
              <span className="text-[10px] text-amber-500 font-mono">Bắt buộc</span>
            </label>
            <input
              type="text"
              value={glossarySource}
              onChange={(e) => setGlossarySource(e.target.value)}
              placeholder="Ví dụ: 解約, 認証, 本番環境..."
              className="w-full bg-surface border border-border-default rounded-lg p-2.5 text-text-primary focus:outline-none focus:border-primary text-xs"
            />
          </div>

          <div>
            <label className="text-text-secondary font-medium block mb-1.5 flex items-center justify-between">
              <span>Target Term (Nghĩa dịch chuẩn):</span>
              <span className="text-[10px] text-amber-500 font-mono">Bắt buộc</span>
            </label>
            <input
              type="text"
              value={glossaryTarget}
              onChange={(e) => setGlossaryTarget(e.target.value)}
              placeholder="Ví dụ: Chấm dứt hợp đồng, Authentication..."
              className="w-full bg-surface border border-border-default rounded-lg p-2.5 text-text-primary focus:outline-none focus:border-primary text-xs"
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-text-secondary font-medium block mb-1.5">Danh mục:</label>
              <Select
                value={glossaryCategory}
                onChange={(val) => setGlossaryCategory(val)}
                size="sm"
                className="w-full"
                options={[
                  { value: 'IT', label: 'Kỹ thuật IT' },
                  { value: 'UI', label: 'Giao diện UI' },
                  { value: 'Banking', label: 'Tài chính' },
                  { value: 'Business', label: 'Nghiệp vụ' },
                  { value: 'General', label: 'Chung' },
                ]}
              />
            </div>

            <div>
              <label className="text-text-secondary font-medium block mb-1.5">Phạm vi:</label>
              <Select
                value={glossaryScope}
                onChange={(val) => setGlossaryScope(val as 'project' | 'global')}
                size="sm"
                className="w-full"
                options={[
                  { value: 'project', label: activeProject ? activeProject.name : 'Dự án' },
                  { value: 'global', label: 'Toàn cục (Global)' },
                ]}
              />
            </div>
          </div>
        </div>
      </Modal>
    </div>
  );
};
