import React, { useState, useEffect, useRef } from 'react';
import { 
  Brain, 
  Search, 
  Sparkles, 
  GitCompare, 
  Layers, 
  FileText, 
  ShieldAlert, 
  CheckCircle2, 
  HelpCircle,
  MessageSquare,
  RefreshCw,
  Copy,
  Check,
  Calendar,
  CheckSquare,
  Quote,
  Filter,
  User,
  Bot,
  ArrowRight,
  Database,
  Code,
  FolderKanban
} from 'lucide-react';
import { apiClient } from '../api/client';
import { 
  Project, 
  AskProjectCitation, 
  DocumentDiffResponse, 
  ImpactAnalysisResponse,
  ProjectBrainStats,
  ProviderInfo
} from '../types';
import { MarkdownView } from '../components/MarkdownView';
import { AiThinkingLoader } from '../components/skeletons/AiThinkingLoader';
import { ProviderModelSelector } from '../components/ProviderModelSelector';
import { resolveHealthyModel } from '../utils/aiPreferences';
import { PageHeader } from '../components/ui/PageHeader';
import { Card, CardContent } from '../components/ui/Card';
import { Badge } from '../components/ui/Badge';
import { Button } from '../components/ui/Button';
import { Select } from '../components/ui/Select';

interface ProjectBrainProps {
  activeProject: Project | null;
  projects?: Project[];
  setActiveProject?: (p: Project | null) => void;
}

interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: string;
  citations?: AskProjectCitation[];
  known_unknowns?: string[];
  follow_up_suggestions?: string[];
  rawMode?: boolean;
}

export const ProjectBrainPage: React.FC<ProjectBrainProps> = ({ 
  activeProject,
  projects = [],
  setActiveProject
}) => {
  const [activeTab, setActiveTab] = useState<'ask' | 'diff' | 'impact'>('ask');
  
  // Knowledge Stats
  const [stats, setStats] = useState<ProjectBrainStats | null>(null);
  const [loadingStats, setLoadingStats] = useState<boolean>(false);

  // AI Provider & Model State
  const [providers, setProviders] = useState<ProviderInfo[]>([]);
  const [selectedProvider, setSelectedProvider] = useState<string>('auto');
  const [selectedModel, setSelectedModel] = useState<string>('');

  // Ask Project State
  const [askQuery, setAskQuery] = useState<string>('');
  const [asking, setAsking] = useState<boolean>(false);
  const [scope, setScope] = useState<'all' | 'meetings' | 'work_items' | 'evidences'>('all');
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Diff State
  const [diffTitle, setDiffTitle] = useState<string>('');
  const [oldText, setOldText] = useState<string>('');
  const [newText, setNewText] = useState<string>('');
  const [diffing, setDiffing] = useState<boolean>(false);
  const [diffResult, setDiffResult] = useState<DocumentDiffResponse | null>(null);

  // Impact Analysis State
  const [changeDesc, setChangeDesc] = useState<string>('');
  const [affectedComponent, setAffectedComponent] = useState<string>('');
  const [analyzingImpact, setAnalyzingImpact] = useState<boolean>(false);
  const [impactResult, setImpactResult] = useState<ImpactAnalysisResponse | null>(null);

  // Fetch Project Stats
  const fetchStats = async () => {
    try {
      setLoadingStats(true);
      const res = await apiClient.getProjectBrainStats(activeProject?.id || 'all');
      setStats(res);
    } catch (e) {
      console.error("Failed to load brain stats", e);
    } finally {
      setLoadingStats(false);
    }
  };

  useEffect(() => {
    fetchStats();
    setMessages([]);
  }, [activeProject?.id]);

  useEffect(() => {
    apiClient.getProviders().then((provs) => {
      setProviders(provs);
      const healthy = resolveHealthyModel(provs, 'auto', '');
      setSelectedProvider(healthy.provider);
      setSelectedModel(healthy.model);
    }).catch(console.error);
  }, []);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, asking]);

  const handleAskProject = async (overrideQuery?: string) => {
    const q = (overrideQuery || askQuery).trim();
    if (!q) return;

    const userMsg: ChatMessage = {
      id: Date.now().toString(),
      role: 'user',
      content: q,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    };

    const newMessages = [...messages, userMsg];
    setMessages(newMessages);
    setAskQuery('');
    setAsking(true);

    try {
      const history = newMessages.slice(0, -1).map(m => ({
        role: m.role,
        content: m.content
      }));

      const res = await apiClient.askProjectBrain(
        activeProject?.id || 'all',
        q,
        history,
        scope,
        selectedProvider === 'auto' ? undefined : selectedProvider,
        selectedModel || undefined
      );

      const assistantMsg: ChatMessage = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: res.answer || 'Không tìm thấy câu trả lời phù hợp trong dữ liệu dự án.',
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        citations: res.citations || [],
        known_unknowns: res.known_unknowns || [],
        follow_up_suggestions: res.follow_up_suggestions || []
      };

      setMessages([...newMessages, assistantMsg]);
    } catch (e) {
      console.error("Ask Project failed", e);
      const errorMsg: ChatMessage = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: 'Đã xảy ra lỗi khi truy vấn Project Brain. Vui lòng thử lại sau giây lát.',
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
      };
      setMessages([...newMessages, errorMsg]);
    } finally {
      setAsking(false);
    }
  };

  const handleCopy = (id: string, text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  const toggleRawMode = (msgId: string) => {
    setMessages(prev => prev.map(m => m.id === msgId ? { ...m, rawMode: !m.rawMode } : m));
  };

  const handleDiffDocuments = async () => {
    if (!oldText.trim() || !newText.trim()) return;
    try {
      setDiffing(true);
      const res = await apiClient.diffDocuments(activeProject?.id || 'all', oldText, newText, diffTitle);
      setDiffResult(res);
    } catch (e) {
      console.error("Diff failed", e);
    } finally {
      setDiffing(false);
    }
  };

  const handleAnalyzeImpact = async () => {
    if (!changeDesc.trim()) return;
    try {
      setAnalyzingImpact(true);
      const res = await apiClient.analyzeImpact(activeProject?.id || 'all', changeDesc, affectedComponent);
      setImpactResult(res);
    } catch (e) {
      console.error("Impact analysis failed", e);
    } finally {
      setAnalyzingImpact(false);
    }
  };

  const samplePrompts = [
    { label: "Tiến trình họp T6-T8", query: "Tổng quan các mốc làm việc và tiến trình trao đổi qua các cuộc họp của dự án từ tháng 6 đến tháng 8?" },
    { label: "Quy tắc Import CSV", query: "Quy định về việc Import CSV trên màn hình Quản lý ngoại vụ là gì?" },
    { label: "Tính phí KOT & Minute-charge", query: "Dự án đã có những quyết định và công việc nào liên quan đến KOT (King Of Time) và tính phí công đoạn?" },
    { label: "Vấn đề chờ xác nhận", query: "Hiện tại dự án còn những câu hỏi hoặc vấn đề nào đang chờ khách hàng xác nhận?" }
  ];

  const getCitationBadgeStyle = (sourceType?: string) => {
    switch (sourceType?.toLowerCase()) {
      case 'meeting':
        return {
          border: 'border-emerald-500/30 bg-emerald-500/10',
          text: 'text-emerald-600 dark:text-emerald-400',
          icon: <Calendar className="w-3.5 h-3.5 text-emerald-500 shrink-0" />,
          label: 'Cuộc họp'
        };
      case 'work_item':
      case 'decision':
        return {
          border: 'border-indigo-500/30 bg-indigo-500/10',
          text: 'text-indigo-600 dark:text-indigo-400',
          icon: <CheckSquare className="w-3.5 h-3.5 text-indigo-500 shrink-0" />,
          label: 'Quyết định / Task'
        };
      case 'chat':
      case 'evidence':
        return {
          border: 'border-amber-500/30 bg-amber-500/10',
          text: 'text-amber-600 dark:text-amber-400',
          icon: <Quote className="w-3.5 h-3.5 text-amber-500 shrink-0" />,
          label: 'Bằng chứng trích dẫn'
        };
      default:
        return {
          border: 'border-primary-500/30 bg-primary-500/10',
          text: 'text-primary-600 dark:text-primary-400',
          icon: <FileText className="w-3.5 h-3.5 text-primary-500 shrink-0" />,
          label: 'Tài liệu dự án'
        };
    }
  };

  return (
    <div className="flex-1 overflow-y-auto bg-canvas p-6 space-y-6 flex flex-col min-h-screen">
      {/* Header & Project Knowledge Bar */}
      <PageHeader
        title={`${activeProject ? activeProject.name : 'Tất cả dự án'} · Kho tri thức`}
        actions={
          <div className="flex items-center gap-3 flex-wrap">
            {/* Project Selector Dropdown */}
            <Select
              value={activeProject?.id || ''}
              onChange={(val) => {
                const found = (projects || []).find(p => p.id === val);
                if (setActiveProject) {
                  setActiveProject(found || null);
                }
              }}
              prefix={<FolderKanban className="w-4 h-4 text-primary" />}
              size="sm"
              triggerClassName="min-w-[190px] max-w-[240px] text-xs font-semibold"
              options={[
                { value: '', label: 'Tất cả dự án' },
                ...(projects || []).map((p) => ({
                  value: p.id,
                  label: p.name,
                  sublabel: p.code
                }))
              ]}
            />

            {/* AI Provider & Searchable Model Combobox */}
            <div className="bg-surface border border-border-subtle rounded-xl px-2.5 py-1 shadow-xs">
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

            {/* Sub Navigation Tabs */}
            <div className="flex items-center gap-1 bg-surface-elevated p-1 rounded-xl border border-border-subtle">
              <button
                onClick={() => setActiveTab('ask')}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition cursor-pointer ${
                  activeTab === 'ask'
                    ? 'bg-primary-600 text-white shadow-xs'
                    : 'text-text-muted hover:text-text-primary'
                }`}
              >
                <MessageSquare className="w-3.5 h-3.5" />
                Hỏi đáp AI
              </button>

              <button
                onClick={() => setActiveTab('diff')}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition cursor-pointer ${
                  activeTab === 'diff'
                    ? 'bg-primary-600 text-white shadow-xs'
                    : 'text-text-muted hover:text-text-primary'
                }`}
              >
                <GitCompare className="w-3.5 h-3.5" />
                So khớp Spec
              </button>

              <button
                onClick={() => setActiveTab('impact')}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition cursor-pointer ${
                  activeTab === 'impact'
                    ? 'bg-primary-600 text-white shadow-xs'
                    : 'text-text-muted hover:text-text-primary'
                }`}
              >
                <Layers className="w-3.5 h-3.5" />
                Phân tích tác động
              </button>
            </div>
          </div>
        }
      />

      {/* Real-time Knowledge Lake Metrics Bar */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3.5">
        <Card className="px-3.5 py-2.5 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-emerald-500/10 flex items-center justify-center text-emerald-500">
              <Calendar className="w-4 h-4" />
            </div>
            <div>
              <div className="text-[11px] text-text-muted font-medium">Cuộc họp</div>
              <div className="text-sm font-bold text-text-primary font-mono">
                {loadingStats ? '...' : (stats?.total_meetings ?? 0)}
              </div>
            </div>
          </div>
          <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" title="Live Synced" />
        </Card>

        <Card className="px-3.5 py-2.5 flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-indigo-500/10 flex items-center justify-center text-indigo-500">
            <CheckSquare className="w-4 h-4" />
          </div>
          <div>
            <div className="text-[11px] text-text-muted font-medium">Mục công việc</div>
            <div className="text-sm font-bold text-text-primary font-mono">
              {loadingStats ? '...' : (stats?.total_work_items ?? 0)}
            </div>
          </div>
        </Card>

        <Card className="px-3.5 py-2.5 flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-amber-500/10 flex items-center justify-center text-amber-500">
            <Quote className="w-4 h-4" />
          </div>
          <div>
            <div className="text-[11px] text-text-muted font-medium">Trích dẫn</div>
            <div className="text-sm font-bold text-text-primary font-mono">
              {loadingStats ? '...' : (stats?.total_evidences ?? 0)}
            </div>
          </div>
        </Card>

        <Card className="px-3.5 py-2.5 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-primary-500/10 flex items-center justify-center text-primary-500">
              <Database className="w-4 h-4" />
            </div>
            <div>
              <div className="text-[11px] text-text-muted font-medium">Engine AI Đang chọn</div>
              <div 
                className="text-xs font-bold text-primary-600 dark:text-primary-400 font-mono truncate max-w-[130px]"
                title={selectedProvider === 'auto' ? '⚡ Auto Router' : `${selectedProvider}: ${selectedModel || 'default'}`}
              >
                {selectedProvider === 'auto' ? '⚡ Auto Router' : `${selectedProvider} (${selectedModel || 'default'})`}
              </div>
            </div>
          </div>
          <button 
            onClick={fetchStats}
            title="Làm mới trạng thái tri thức" 
            className="p-1.5 rounded-lg text-text-muted hover:text-text-primary hover:bg-surface-elevated transition cursor-pointer"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loadingStats ? 'animate-spin text-primary-500' : ''}`} />
          </button>
        </Card>
      </div>

      {/* ================= TAB 1: ASK PROJECT BRAIN (COPILOT CHAT) ================= */}
      {activeTab === 'ask' && (
        <div className="flex-1 flex flex-col space-y-4 min-h-0">
          {/* Scope Filters & Controls */}
          <div className="flex items-center justify-between flex-wrap gap-2 shrink-0">
            <div className="flex items-center gap-1.5 text-xs">
              <span className="text-text-muted flex items-center gap-1 mr-1 text-[11px] font-semibold uppercase tracking-wider">
                <Filter className="w-3 h-3" /> Phạm vi:
              </span>
              {[
                { id: 'all', label: 'Tất cả tri thức' },
                { id: 'meetings', label: 'Chỉ Cuộc họp & Quyết định' },
                { id: 'work_items', label: 'Chỉ Task & Trạng thái' },
                { id: 'evidences', label: 'Chỉ Bằng chứng nguyên văn' }
              ].map(s => (
                <button
                  key={s.id}
                  onClick={() => setScope(s.id as any)}
                  className={`px-3 py-1 rounded-full text-xs font-medium transition cursor-pointer ${
                    scope === s.id
                      ? 'bg-primary-500/15 text-primary-600 dark:text-primary-400 border border-primary-500/30 shadow-xs font-semibold'
                      : 'bg-surface text-text-muted hover:text-text-primary border border-border-subtle'
                  }`}
                >
                  {s.label}
                </button>
              ))}
            </div>

            {messages.length > 0 && (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setMessages([])}
                leftIcon={<RefreshCw className="w-3 h-3" />}
                className="text-[11px] text-text-muted hover:text-rose-500"
              >
                Cuộc trò chuyện mới
              </Button>
            )}
          </div>

          {/* Conversation Thread Area */}
          <div className="flex-1 overflow-y-auto space-y-4 pr-1 min-h-[360px]">
            {messages.length === 0 ? (
              /* Empty State with Guided Suggestions */
              <Card className="p-8 text-center space-y-5 my-auto max-w-3xl mx-auto border-dashed">
                <div className="w-12 h-12 rounded-2xl bg-primary-500/10 flex items-center justify-center text-primary-500 mx-auto">
                  <Sparkles className="w-6 h-6" />
                </div>
                <div className="space-y-1.5 max-w-md mx-auto">
                  <h3 className="text-base font-bold text-text-primary tracking-tight">
                    Hỏi bất kỳ điều gì về {activeProject ? `Dự án ${activeProject.name}` : 'Toàn bộ Dự án'}
                  </h3>
                  <p className="text-xs text-text-muted leading-relaxed">
                    AI Copilot được kết nối trực tiếp với toàn bộ {stats?.total_meetings ?? 0} biên bản cuộc họp, {stats?.total_work_items ?? 0} quyết định & công việc, cùng {stats?.total_evidences ?? 0} bằng chứng trích dẫn thực tế.
                  </p>
                </div>

                {/* Suggested Prompts Grid */}
                <div className="pt-2 max-w-2xl mx-auto w-full">
                  <div className="text-[11px] font-semibold text-text-muted uppercase tracking-wider mb-2.5">
                    Câu hỏi gợi ý thực tế cho dự án:
                  </div>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5 text-left">
                    {samplePrompts.map((sp, idx) => (
                      <button
                        key={idx}
                        onClick={() => handleAskProject(sp.query)}
                        className="p-3 rounded-xl bg-canvas hover:bg-surface-elevated border border-border-subtle hover:border-primary-500/40 text-xs text-text-primary transition group space-y-1 flex flex-col justify-between cursor-pointer"
                      >
                        <div className="font-semibold text-primary-600 dark:text-primary-400 flex items-center justify-between">
                          <span>{sp.label}</span>
                          <ArrowRight className="w-3.5 h-3.5 opacity-0 group-hover:opacity-100 transition-opacity" />
                        </div>
                        <p className="text-[11px] text-text-muted line-clamp-2 leading-snug">
                          {sp.query}
                        </p>
                      </button>
                    ))}
                  </div>
                </div>
              </Card>
            ) : (
              /* Chat Messages Stream */
              messages.map((msg) => (
                <div
                  key={msg.id}
                  className={`flex gap-3 text-xs ${
                    msg.role === 'user' ? 'justify-end' : 'justify-start'
                  }`}
                >
                  {msg.role === 'assistant' && (
                    <div className="w-8 h-8 rounded-xl bg-primary-500/10 border border-primary-500/20 flex items-center justify-center text-primary-500 shrink-0 mt-1">
                      <Bot className="w-4 h-4" />
                    </div>
                  )}

                  <div
                    className={`max-w-[85%] rounded-2xl p-4 space-y-3.5 ${
                      msg.role === 'user'
                        ? 'bg-primary-600 text-white rounded-br-none shadow-xs'
                        : 'bg-surface border border-border-subtle rounded-bl-none text-text-primary shadow-xs'
                    }`}
                  >
                    {/* Header line */}
                    <div className="flex items-center justify-between gap-3 text-[11px] pb-1 border-b border-border-subtle/50">
                      <span className="font-semibold opacity-90">
                        {msg.role === 'user' ? 'Bạn (BrSE / Comtor)' : 'Project Brain AI Copilot'}
                      </span>
                      <div className="flex items-center gap-2">
                        <span className="opacity-60">{msg.timestamp}</span>
                        {msg.role === 'assistant' && (
                          <>
                            <button
                              onClick={() => toggleRawMode(msg.id)}
                              className="opacity-70 hover:opacity-100 flex items-center gap-1 hover:text-primary-500 transition cursor-pointer"
                              title={msg.rawMode ? "Xem dạng biên dịch" : "Xem mã Markdown"}
                            >
                              <Code className="w-3 h-3" />
                              <span className="text-[10px]">{msg.rawMode ? "Render" : "MD"}</span>
                            </button>
                            <button
                              onClick={() => handleCopy(msg.id, msg.content)}
                              className="opacity-70 hover:opacity-100 flex items-center gap-1 hover:text-primary-500 transition cursor-pointer"
                              title="Sao chép câu trả lời"
                            >
                              {copiedId === msg.id ? (
                                <Check className="w-3 h-3 text-emerald-500" />
                              ) : (
                                <Copy className="w-3 h-3" />
                              )}
                              <span className="text-[10px]">{copiedId === msg.id ? "Đã copy" : "Copy"}</span>
                            </button>
                          </>
                        )}
                      </div>
                    </div>

                    {/* Content */}
                    {msg.role === 'user' ? (
                      <div className="text-xs leading-relaxed whitespace-pre-wrap font-medium">
                        {msg.content}
                      </div>
                    ) : (
                      <div className="space-y-4">
                        {msg.rawMode ? (
                          <pre className="p-3 bg-canvas rounded-lg text-text-secondary font-mono text-xs overflow-x-auto whitespace-pre-wrap border border-border-subtle">
                            {msg.content}
                          </pre>
                        ) : (
                          <MarkdownView content={msg.content} accent="sky" />
                        )}

                        {/* Citations & Evidence Cards */}
                        {msg.citations && msg.citations.length > 0 && (
                          <div className="space-y-2 pt-2 border-t border-border-subtle">
                            <div className="text-[11px] font-bold text-text-muted uppercase tracking-wider flex items-center gap-1.5">
                              <CheckCircle2 className="w-3.5 h-3.5 text-primary-500" />
                              Bằng chứng & Nguồn trích dẫn ({msg.citations.length})
                            </div>
                            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                              {msg.citations.map((c, idx) => {
                                const style = getCitationBadgeStyle(c.source_type || c.source);
                                return (
                                  <div
                                    key={idx}
                                    className={`p-2.5 rounded-lg border ${style.border} text-xs space-y-1`}
                                  >
                                    <div className="flex items-center justify-between text-[11px] font-medium">
                                      <span className={`flex items-center gap-1.5 ${style.text}`}>
                                        {style.icon}
                                        <span>{style.label}: {c.title || c.source}</span>
                                      </span>
                                      {c.date && <span className="text-text-muted font-mono text-[10px]">{c.date}</span>}
                                    </div>
                                    <p className="text-text-secondary italic text-[11px] leading-snug">
                                      "{c.quote}"
                                    </p>
                                    {c.author && (
                                      <div className="text-[10px] text-text-muted">
                                        Phát biểu / Phụ trách: {c.author}
                                      </div>
                                    )}
                                  </div>
                                );
                              })}
                            </div>
                          </div>
                        )}

                        {/* Known Unknowns / Unresolved Nuances Alert */}
                        {msg.known_unknowns && msg.known_unknowns.length > 0 && (
                          <div className="bg-amber-500/10 border border-amber-500/30 rounded-xl p-3 space-y-1.5">
                            <div className="text-[11px] font-bold text-amber-600 dark:text-amber-400 uppercase tracking-wider flex items-center gap-1.5">
                              <HelpCircle className="w-3.5 h-3.5" />
                              Vấn đề tồn đọng / Cần làm rõ với khách hàng:
                            </div>
                            <ul className="text-xs text-amber-700 dark:text-amber-200 space-y-1 list-disc list-inside">
                              {msg.known_unknowns.map((ku, i) => (
                                <li key={i}>{ku}</li>
                              ))}
                            </ul>
                          </div>
                        )}

                        {/* Follow-up Suggestions Chips */}
                        {msg.follow_up_suggestions && msg.follow_up_suggestions.length > 0 && (
                          <div className="space-y-1.5 pt-1">
                            <div className="text-[10.5px] font-semibold text-text-muted uppercase tracking-wider">
                              Gợi ý câu hỏi tiếp theo:
                            </div>
                            <div className="flex flex-wrap gap-1.5">
                              {msg.follow_up_suggestions.map((sug, i) => (
                                <button
                                  key={i}
                                  onClick={() => handleAskProject(sug)}
                                  className="text-[11px] text-text-secondary hover:text-text-primary bg-canvas hover:bg-surface-elevated border border-border-subtle hover:border-primary-500/40 px-2.5 py-1 rounded-lg transition text-left flex items-center gap-1 group cursor-pointer"
                                >
                                  <span>{sug}</span>
                                  <ArrowRight className="w-2.5 h-2.5 opacity-0 group-hover:opacity-100 transition-opacity" />
                                </button>
                              ))}
                            </div>
                          </div>
                        )}
                      </div>
                    )}
                  </div>

                  {msg.role === 'user' && (
                    <div className="w-8 h-8 rounded-xl bg-primary-500/20 border border-primary-500/30 flex items-center justify-center text-primary-500 shrink-0 mt-1">
                      <User className="w-4 h-4" />
                    </div>
                  )}
                </div>
              ))
            )}

            {/* AI Reasoning / Loading Indicator */}
            {asking && (
              <div className="flex gap-3 text-xs justify-start">
                <div className="w-8 h-8 rounded-xl bg-primary-500/10 border border-primary-500/20 flex items-center justify-center text-primary-500 shrink-0 mt-1">
                  <Bot className="w-4 h-4" />
                </div>
                <div className="flex-1 max-w-[85%]">
                  <AiThinkingLoader mode="rag" title="Project Brain đang tổng hợp tri thức đa nguồn..." />
                </div>
              </div>
            )}

            <div ref={messagesEndRef} />
          </div>

          {/* Sticky Prompt Input Bar */}
          <Card className="p-3 space-y-2 shrink-0 shadow-md">
            <div className="flex gap-2">
              <input
                type="text"
                value={askQuery}
                onChange={(e) => setAskQuery(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && !e.shiftKey && handleAskProject()}
                placeholder="Hỏi bất kỳ điều gì về cuộc họp, quyết định, KOT, quy tắc Import CSV, hay lịch running test..."
                className="flex-1 bg-canvas border border-border-subtle rounded-xl px-4 py-2.5 text-xs text-text-primary placeholder:text-text-muted focus:outline-none focus:border-primary-500 transition font-sans"
              />
              <Button
                variant="primary"
                onClick={() => handleAskProject()}
                disabled={asking || !askQuery.trim()}
                isLoading={asking}
                leftIcon={<Sparkles className="w-3.5 h-3.5" />}
              >
                Hỏi AI
              </Button>
            </div>

            {/* Micro hint */}
            <div className="flex items-center justify-between text-[11px] text-text-muted px-1">
              <span>Nhấn Enter để gửi • Hỗ trợ hội thoại đa vòng (Multi-turn Context)</span>
              <span>Đang kết nối 100% dữ liệu {activeProject ? activeProject.name : 'Tất cả dự án'}</span>
            </div>
          </Card>
        </div>
      )}

      {/* ================= TAB 2: SPEC DIFF ================= */}
      {activeTab === 'diff' && (
        <div className="space-y-5">
          <Card className="p-5 space-y-4">
            <div className="flex items-center gap-2 border-b border-border-subtle pb-3">
              <GitCompare className="w-4 h-4 text-primary-500" />
              <h2 className="text-sm font-semibold text-text-primary">
                So sánh Phiên bản Đặc tả Yêu cầu (What Changed? Spec Diff)
              </h2>
            </div>
            <p className="text-xs text-text-muted">
              Dán đặc tả cũ vs đặc tả mới (hoặc quyết định cuộc họp) để AI tự động bóc tách các điểm thay đổi, breaking changes và cảnh báo xung đột.
            </p>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="text-[11px] text-text-muted font-medium block mb-1">Phiên bản A (Đặc tả cũ / Existing Spec)</label>
                <textarea
                  value={oldText}
                  onChange={(e) => setOldText(e.target.value)}
                  placeholder="Dán nội dung đặc tả phiên bản cũ (v1) hoặc quyết định trước đó..."
                  rows={6}
                  className="w-full bg-canvas border border-border-subtle rounded-lg p-2.5 text-xs text-text-primary font-mono resize-none focus:outline-none focus:border-primary-500 placeholder:text-text-muted"
                />
              </div>

              <div>
                <label className="text-[11px] text-text-muted font-medium block mb-1">Phiên bản B (Đặc tả mới / New Revision)</label>
                <textarea
                  value={newText}
                  onChange={(e) => setNewText(e.target.value)}
                  placeholder="Dán nội dung đặc tả phiên bản mới (v2) hoặc yêu cầu mới từ khách hàng..."
                  rows={6}
                  className="w-full bg-canvas border border-border-subtle rounded-lg p-2.5 text-xs text-text-primary font-mono resize-none focus:outline-none focus:border-primary-500 placeholder:text-text-muted"
                />
              </div>
            </div>

            <Button
              variant="primary"
              onClick={handleDiffDocuments}
              disabled={diffing || !oldText.trim() || !newText.trim()}
              isLoading={diffing}
              leftIcon={<Sparkles className="w-3.5 h-3.5" />}
            >
              So sánh & Phát hiện Xung đột
            </Button>
          </Card>

          {/* Diff Result Card */}
          {diffResult && (
            <Card className="p-5 space-y-4">
              {diffResult.conflicts?.length > 0 && (
                <div className="bg-rose-500/10 border border-rose-500/30 rounded-lg p-3 space-y-1">
                  <div className="text-xs font-bold text-rose-600 dark:text-rose-400 flex items-center gap-1.5">
                    <ShieldAlert className="w-4 h-4" /> Phát hiện Xung đột Kỹ thuật (Potential Conflicts)
                  </div>
                  {diffResult.conflicts.map((c, i) => (
                    <div key={i} className="text-xs text-rose-700 dark:text-rose-300">
                      • {c.issue} ({c.recommendation})
                    </div>
                  ))}
                </div>
              )}

              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                {/* Added */}
                <div className="bg-canvas border border-emerald-500/30 p-3 rounded-lg space-y-2">
                  <div className="text-[11px] font-bold text-emerald-600 dark:text-emerald-400 uppercase tracking-wider">
                    ➕ Bổ sung mới ({diffResult.added?.length ?? 0})
                  </div>
                  {diffResult.added?.map((a, i) => (
                    <div key={i} className="text-xs text-text-primary">
                      <span className="font-semibold text-emerald-600 dark:text-emerald-400">{a.item}:</span> {a.description}
                    </div>
                  ))}
                </div>

                {/* Modified */}
                <div className="bg-canvas border border-amber-500/30 p-3 rounded-lg space-y-2">
                  <div className="text-[11px] font-bold text-amber-600 dark:text-amber-400 uppercase tracking-wider">
                    ⚡ Thay đổi / Điều chỉnh ({diffResult.modified?.length ?? 0})
                  </div>
                  {diffResult.modified?.map((m, i) => (
                    <div key={i} className="text-xs text-text-primary space-y-0.5">
                      <div className="font-semibold text-amber-600 dark:text-amber-400">{m.item} ({m.significance})</div>
                      <div className="text-[11px] text-text-muted">Trước: {m.before}</div>
                      <div className="text-[11px] text-text-primary">Sau: {m.after}</div>
                    </div>
                  ))}
                </div>

                {/* Removed */}
                <div className="bg-canvas border border-rose-500/30 p-3 rounded-lg space-y-2">
                  <div className="text-[11px] font-bold text-rose-600 dark:text-rose-400 uppercase tracking-wider">
                    ➖ Loại bỏ ({diffResult.removed?.length ?? 0})
                  </div>
                  {diffResult.removed?.map((r, i) => (
                    <div key={i} className="text-xs text-text-primary">
                      <span className="font-semibold text-rose-600 dark:text-rose-400">{r.item}:</span> {r.description}
                    </div>
                  ))}
                </div>
              </div>
            </Card>
          )}
        </div>
      )}

      {/* ================= TAB 3: CHANGE IMPACT ANALYSIS ================= */}
      {activeTab === 'impact' && (
        <div className="space-y-5">
          <Card className="p-5 space-y-4">
            <div className="flex items-center gap-2 border-b border-border-subtle pb-3">
              <Layers className="w-4 h-4 text-primary-500" />
              <h2 className="text-sm font-semibold text-text-primary">
                Phân tích Tác động của Yêu cầu Thay đổi (Change Impact Analysis)
              </h2>
            </div>
            <p className="text-xs text-text-muted">
              Khi khách hàng yêu cầu thay đổi (CR), lập tức đánh giá ảnh hưởng dây chuyền đến các API, UI Frontend, Test cases và Tiến độ dự án.
            </p>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <div>
                <label className="text-[11px] text-text-muted block mb-1">Mô tả Yêu cầu Thay đổi (Change Request)</label>
                <input
                  type="text"
                  value={changeDesc}
                  onChange={(e) => setChangeDesc(e.target.value)}
                  placeholder="VD: Chuyển đổi định dạng Seiban sang mã 8 ký tự..."
                  className="w-full bg-canvas border border-border-subtle rounded-lg px-3 py-2 text-xs text-text-primary placeholder:text-text-muted focus:outline-none focus:border-primary-500"
                />
              </div>
              <div>
                <label className="text-[11px] text-text-muted block mb-1">Module / Thành phần bị tác động</label>
                <input
                  type="text"
                  value={affectedComponent}
                  onChange={(e) => setAffectedComponent(e.target.value)}
                  placeholder="VD: Quản lý gia công ngoài, Import CSV, KOT..."
                  className="w-full bg-canvas border border-border-subtle rounded-lg px-3 py-2 text-xs text-text-primary placeholder:text-text-muted focus:outline-none focus:border-primary-500"
                />
              </div>
            </div>

            <Button
              variant="primary"
              onClick={handleAnalyzeImpact}
              disabled={analyzingImpact || !changeDesc.trim()}
              isLoading={analyzingImpact}
              leftIcon={<Sparkles className="w-3.5 h-3.5" />}
            >
              Phân tích Ảnh hưởng Hệ thống
            </Button>
          </Card>

          {/* Impact Result Card */}
          {impactResult && (
            <Card className="p-5 space-y-4">
              <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
                <div className="bg-canvas border border-border-subtle p-3 rounded-lg">
                  <div className="text-[11px] font-semibold text-primary-500">API Bị Ảnh hưởng</div>
                  <ul className="text-xs text-text-secondary mt-1 space-y-1">
                    {impactResult.impacted_apis?.map((a, i) => (
                      <li key={i}>• {a}</li>
                    ))}
                  </ul>
                </div>

                <div className="bg-canvas border border-border-subtle p-3 rounded-lg">
                  <div className="text-[11px] font-semibold text-indigo-500">Frontend UI Bị Ảnh hưởng</div>
                  <ul className="text-xs text-text-secondary mt-1 space-y-1">
                    {impactResult.impacted_frontend?.map((f, i) => (
                      <li key={i}>• {f}</li>
                    ))}
                  </ul>
                </div>

                <div className="bg-canvas border border-border-subtle p-3 rounded-lg">
                  <div className="text-[11px] font-semibold text-amber-500">Test Cases Cần Bổ sung</div>
                  <ul className="text-xs text-text-secondary mt-1 space-y-1">
                    {impactResult.impacted_tests?.map((t, i) => (
                      <li key={i}>• {t}</li>
                    ))}
                  </ul>
                </div>

                <div className="bg-canvas border border-border-subtle p-3 rounded-lg">
                  <div className="text-[11px] font-semibold text-rose-500">Rủi ro Tiến độ</div>
                  <div className="text-sm font-bold text-text-primary mt-1">{impactResult.schedule_risk}</div>
                  <div className="text-[11px] text-text-muted mt-1">Cơ sở dữ liệu: {impactResult.database_impact}</div>
                </div>
              </div>

              {impactResult.recommended_actions?.length > 0 && (
                <div className="border-t border-border-subtle pt-3">
                  <div className="text-[11px] font-semibold text-emerald-600 dark:text-emerald-400 uppercase tracking-wider mb-1">
                    Hành động Đề xuất cho BrSE
                  </div>
                  <ul className="text-xs text-text-secondary space-y-1 list-disc list-inside">
                    {impactResult.recommended_actions.map((act, i) => (
                      <li key={i}>{act}</li>
                    ))}
                  </ul>
                </div>
              )}
            </Card>
          )}
        </div>
      )}
    </div>
  );
};
