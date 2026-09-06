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
    // Reset conversation on project change
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
      // Build previous turns history
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
          border: 'border-emerald-700/40 bg-emerald-950/40',
          text: 'text-emerald-300',
          icon: <Calendar className="w-3 h-3 text-emerald-400 shrink-0" />,
          label: 'Cuộc họp'
        };
      case 'work_item':
      case 'decision':
        return {
          border: 'border-indigo-700/40 bg-indigo-950/40',
          text: 'text-indigo-300',
          icon: <CheckSquare className="w-3 h-3 text-indigo-400 shrink-0" />,
          label: 'Quyết định / Task'
        };
      case 'chat':
      case 'evidence':
        return {
          border: 'border-amber-700/40 bg-amber-950/40',
          text: 'text-amber-300',
          icon: <Quote className="w-3 h-3 text-amber-400 shrink-0" />,
          label: 'Bằng chứng trích dẫn'
        };
      default:
        return {
          border: 'border-sky-700/40 bg-sky-950/40',
          text: 'text-sky-300',
          icon: <FileText className="w-3 h-3 text-sky-400 shrink-0" />,
          label: 'Tài liệu dự án'
        };
    }
  };

  return (
    <div className="flex-1 overflow-y-auto bg-slate-950 p-6 space-y-6 flex flex-col min-h-screen">
      {/* Header & Project Knowledge Bar */}
      <div className="border-b border-slate-800 pb-5 space-y-4 shrink-0">
        <div className="flex items-center justify-between flex-wrap gap-4">
          <div className="space-y-1">
            <div className="flex items-center gap-2.5">
              <span className="px-2.5 py-0.5 rounded text-[11px] font-bold uppercase tracking-wider bg-indigo-500/20 text-indigo-400 border border-indigo-500/30 flex items-center gap-1.5">
                <Brain className="w-3.5 h-3.5" /> Project Brain AI Copilot
              </span>
              <h1 className="text-xl font-bold text-white tracking-tight">
                {activeProject ? activeProject.name : 'All Projects'} Knowledge Lake
              </h1>
            </div>
            <p className="text-xs text-slate-400">
              Trợ lý AI tổng hợp tri thức đa nguồn: Biên bản cuộc họp, Quyết định kỹ thuật, Bằng chứng nguyên văn và Quản lý thay đổi.
            </p>
          </div>

          {/* Right Controls: Project Selector & Sub Navigation Tabs */}
          <div className="flex items-center gap-3 flex-wrap">
            {/* Project Selector Dropdown */}
            <div className="flex items-center gap-2 bg-slate-900 border border-slate-700/80 hover:border-sky-500/50 rounded-xl px-3 py-1.5 shadow-sm transition">
              <FolderKanban className="w-4 h-4 text-sky-400 shrink-0" />
              <label className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider shrink-0">
                Dự án:
              </label>
              <select
                value={activeProject?.id || ''}
                onChange={(e) => {
                  const found = (projects || []).find(p => p.id === e.target.value);
                  if (setActiveProject) {
                    setActiveProject(found || null);
                  }
                }}
                className="bg-transparent text-xs font-semibold text-sky-300 focus:outline-none cursor-pointer pr-1 max-w-[220px] truncate"
              >
                <option value="" className="bg-slate-900 text-slate-200">
                  -- Tất cả dự án (Toàn cục) --
                </option>
                {(projects || []).map((p) => (
                  <option key={p.id} value={p.id} className="bg-slate-900 text-slate-200">
                    {p.name} ({p.code})
                  </option>
                ))}
              </select>
            </div>

            {/* AI Provider & Searchable Model Combobox */}
            <div className="bg-slate-900 border border-slate-700/80 rounded-xl px-2.5 py-1 shadow-sm">
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
            <div className="flex items-center gap-1.5 bg-slate-900/80 p-1 rounded-xl border border-slate-800">
            <button
              onClick={() => setActiveTab('ask')}
              className={`flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg text-xs font-semibold transition ${
                activeTab === 'ask'
                  ? 'bg-sky-600 text-white shadow-sm'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              <MessageSquare className="w-3.5 h-3.5" />
              AI Copilot Q&A
            </button>

            <button
              onClick={() => setActiveTab('diff')}
              className={`flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg text-xs font-semibold transition ${
                activeTab === 'diff'
                  ? 'bg-sky-600 text-white shadow-sm'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              <GitCompare className="w-3.5 h-3.5" />
              Spec Diff
            </button>

            <button
              onClick={() => setActiveTab('impact')}
              className={`flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg text-xs font-semibold transition ${
                activeTab === 'impact'
                  ? 'bg-sky-600 text-white shadow-sm'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              <Layers className="w-3.5 h-3.5" />
              Impact Analysis
            </button>
          </div>
        </div>
      </div>

        {/* Real-time Knowledge Lake Metrics Bar */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <div className="bg-slate-900/60 border border-slate-800/80 rounded-xl px-3.5 py-2.5 flex items-center justify-between">
            <div className="flex items-center gap-2.5">
              <div className="w-8 h-8 rounded-lg bg-emerald-950/60 border border-emerald-800/40 flex items-center justify-center text-emerald-400">
                <Calendar className="w-4 h-4" />
              </div>
              <div>
                <div className="text-[11px] text-slate-400 font-medium">Cuộc họp đồng bộ</div>
                <div className="text-sm font-bold text-slate-100 font-mono">
                  {loadingStats ? '...' : (stats?.total_meetings ?? 0)} biên bản
                </div>
              </div>
            </div>
            <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" title="Live Synced" />
          </div>

          <div className="bg-slate-900/60 border border-slate-800/80 rounded-xl px-3.5 py-2.5 flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-indigo-950/60 border border-indigo-800/40 flex items-center justify-center text-indigo-400">
              <CheckSquare className="w-4 h-4" />
            </div>
            <div>
              <div className="text-[11px] text-slate-400 font-medium">Work Items & Quyết định</div>
              <div className="text-sm font-bold text-slate-100 font-mono">
                {loadingStats ? '...' : (stats?.total_work_items ?? 0)} mục
              </div>
            </div>
          </div>

          <div className="bg-slate-900/60 border border-slate-800/80 rounded-xl px-3.5 py-2.5 flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-amber-950/60 border border-amber-800/40 flex items-center justify-center text-amber-400">
              <Quote className="w-4 h-4" />
            </div>
            <div>
              <div className="text-[11px] text-slate-400 font-medium">Bằng chứng trích dẫn</div>
              <div className="text-sm font-bold text-slate-100 font-mono">
                {loadingStats ? '...' : (stats?.total_evidences ?? 0)} bằng chứng
              </div>
            </div>
          </div>

          <div className="bg-slate-900/60 border border-slate-800/80 rounded-xl px-3.5 py-2.5 flex items-center justify-between">
            <div className="flex items-center gap-2.5">
              <div className="w-8 h-8 rounded-lg bg-sky-950/60 border border-sky-800/40 flex items-center justify-center text-sky-400">
                <Database className="w-4 h-4" />
              </div>
              <div>
                <div className="text-[11px] text-slate-400 font-medium">Engine AI Đang chọn</div>
                <div 
                  className="text-xs font-bold text-sky-300 font-mono truncate max-w-[140px]"
                  title={selectedProvider === 'auto' ? '⚡ Auto Router (Groq ➔ Gemini)' : `${selectedProvider}: ${selectedModel || 'default'}`}
                >
                  {selectedProvider === 'auto' ? '⚡ Auto Router' : `${selectedProvider} (${selectedModel || 'default'})`}
                </div>
              </div>
            </div>
            <button 
              onClick={fetchStats}
              title="Làm mới trạng thái tri thức" 
              className="p-1.5 rounded-lg text-slate-500 hover:text-slate-300 hover:bg-slate-800 transition"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${loadingStats ? 'animate-spin text-sky-400' : ''}`} />
            </button>
          </div>
        </div>
      </div>

      {/* ================= TAB 1: ASK PROJECT BRAIN (COPILOT CHAT) ================= */}
      {activeTab === 'ask' && (
        <div className="flex-1 flex flex-col space-y-4 min-h-0">
          {/* Scope Filters & Controls */}
          <div className="flex items-center justify-between flex-wrap gap-2 shrink-0">
            <div className="flex items-center gap-1.5 text-xs">
              <span className="text-slate-500 flex items-center gap-1 mr-1 text-[11px] font-semibold uppercase tracking-wider">
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
                  className={`px-3 py-1 rounded-full text-xs font-medium transition ${
                    scope === s.id
                      ? 'bg-sky-500/20 text-sky-300 border border-sky-500/40 shadow-sm'
                      : 'bg-slate-900/60 text-slate-400 hover:text-slate-200 border border-slate-800'
                  }`}
                >
                  {s.label}
                </button>
              ))}
            </div>

            {messages.length > 0 && (
              <button
                onClick={() => setMessages([])}
                className="text-[11px] text-slate-400 hover:text-rose-300 flex items-center gap-1 px-2.5 py-1 rounded-lg bg-slate-900 hover:bg-rose-950/30 border border-slate-800 hover:border-rose-900/40 transition"
              >
                <RefreshCw className="w-3 h-3" />
                Cuộc trò chuyện mới
              </button>
            )}
          </div>

          {/* Conversation Thread Area */}
          <div className="flex-1 overflow-y-auto space-y-4 pr-1 min-h-[360px]">
            {messages.length === 0 ? (
              /* Empty State with Guided Suggestions */
              <div className="bg-slate-900/40 border border-slate-800/80 rounded-2xl p-8 text-center space-y-5 my-auto">
                <div className="w-12 h-12 rounded-2xl bg-gradient-to-tr from-sky-600 to-indigo-600 p-0.5 mx-auto shadow-lg shadow-sky-600/20">
                  <div className="w-full h-full bg-slate-950 rounded-[14px] flex items-center justify-center text-sky-400">
                    <Sparkles className="w-6 h-6" />
                  </div>
                </div>
                <div className="space-y-1.5 max-w-md mx-auto">
                  <h3 className="text-base font-bold text-white tracking-tight">
                    Hỏi bất kỳ điều gì về {activeProject ? `Dự án ${activeProject.name}` : 'Toàn bộ Dự án'}
                  </h3>
                  <p className="text-xs text-slate-400 leading-relaxed">
                    AI Copilot được kết nối trực tiếp với toàn bộ {stats?.total_meetings ?? 0} biên bản cuộc họp, {stats?.total_work_items ?? 0} quyết định & công việc, cùng {stats?.total_evidences ?? 0} bằng chứng trích dẫn thực tế.
                  </p>
                </div>

                {/* Suggested Prompts Grid */}
                <div className="pt-2 max-w-2xl mx-auto">
                  <div className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider mb-2.5">
                    Câu hỏi gợi ý thực tế cho dự án:
                  </div>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-left">
                    {samplePrompts.map((sp, idx) => (
                      <button
                        key={idx}
                        onClick={() => handleAskProject(sp.query)}
                        className="p-3 rounded-xl bg-slate-900/70 hover:bg-slate-850 border border-slate-800 hover:border-sky-500/40 text-xs text-slate-300 hover:text-white transition group space-y-1 flex flex-col justify-between"
                      >
                        <div className="font-semibold text-sky-400 group-hover:text-sky-300 flex items-center justify-between">
                          <span>{sp.label}</span>
                          <ArrowRight className="w-3.5 h-3.5 opacity-0 group-hover:opacity-100 transition-opacity" />
                        </div>
                        <p className="text-[11px] text-slate-400 line-clamp-2 leading-snug">
                          {sp.query}
                        </p>
                      </button>
                    ))}
                  </div>
                </div>
              </div>
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
                    <div className="w-7 h-7 rounded-lg bg-sky-600/20 border border-sky-500/30 flex items-center justify-center text-sky-400 shrink-0 mt-1">
                      <Bot className="w-4 h-4" />
                    </div>
                  )}

                  <div
                    className={`max-w-[85%] rounded-2xl p-4 space-y-3.5 ${
                      msg.role === 'user'
                        ? 'bg-sky-600 text-white rounded-br-none shadow-md shadow-sky-600/10'
                        : 'bg-slate-900/90 border border-slate-800 rounded-bl-none text-slate-200 shadow-sm'
                    }`}
                  >
                    {/* Header line */}
                    <div className="flex items-center justify-between gap-3 text-[11px] pb-1 border-b border-white/10">
                      <span className="font-semibold opacity-90">
                        {msg.role === 'user' ? 'Bạn (BrSE / Comtor)' : 'Project Brain AI Copilot'}
                      </span>
                      <div className="flex items-center gap-2">
                        <span className="opacity-60">{msg.timestamp}</span>
                        {msg.role === 'assistant' && (
                          <>
                            <button
                              onClick={() => toggleRawMode(msg.id)}
                              className="opacity-70 hover:opacity-100 flex items-center gap-1 hover:text-sky-300 transition"
                              title={msg.rawMode ? "Xem dạng biên dịch" : "Xem mã Markdown"}
                            >
                              <Code className="w-3 h-3" />
                              <span className="text-[10px]">{msg.rawMode ? "Render" : "MD"}</span>
                            </button>
                            <button
                              onClick={() => handleCopy(msg.id, msg.content)}
                              className="opacity-70 hover:opacity-100 flex items-center gap-1 hover:text-sky-300 transition"
                              title="Sao chép câu trả lời"
                            >
                              {copiedId === msg.id ? (
                                <Check className="w-3 h-3 text-emerald-400" />
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
                          <pre className="p-3 bg-slate-950 rounded-lg text-slate-300 font-mono text-xs overflow-x-auto whitespace-pre-wrap">
                            {msg.content}
                          </pre>
                        ) : (
                          <MarkdownView content={msg.content} accent="sky" />
                        )}

                        {/* Citations & Evidence Cards */}
                        {msg.citations && msg.citations.length > 0 && (
                          <div className="space-y-2 pt-2 border-t border-slate-800">
                            <div className="text-[11px] font-bold text-slate-400 uppercase tracking-wider flex items-center gap-1.5">
                              <CheckCircle2 className="w-3.5 h-3.5 text-sky-400" />
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
                                      {c.date && <span className="text-slate-500 font-mono text-[10px]">{c.date}</span>}
                                    </div>
                                    <p className="text-slate-300 italic text-[11px] leading-snug">
                                      "{c.quote}"
                                    </p>
                                    {c.author && (
                                      <div className="text-[10px] text-slate-500">
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
                          <div className="bg-amber-950/20 border border-amber-500/30 rounded-xl p-3 space-y-1.5">
                            <div className="text-[11px] font-bold text-amber-400 uppercase tracking-wider flex items-center gap-1.5">
                              <HelpCircle className="w-3.5 h-3.5" />
                              Vấn đề tồn đọng / Cần làm rõ với khách hàng:
                            </div>
                            <ul className="text-xs text-amber-200/90 space-y-1 list-disc list-inside">
                              {msg.known_unknowns.map((ku, i) => (
                                <li key={i}>{ku}</li>
                              ))}
                            </ul>
                          </div>
                        )}

                        {/* Follow-up Suggestions Chips */}
                        {msg.follow_up_suggestions && msg.follow_up_suggestions.length > 0 && (
                          <div className="space-y-1.5 pt-1">
                            <div className="text-[10.5px] font-semibold text-slate-500 uppercase tracking-wider">
                              Gợi ý câu hỏi tiếp theo:
                            </div>
                            <div className="flex flex-wrap gap-1.5">
                              {msg.follow_up_suggestions.map((sug, i) => (
                                <button
                                  key={i}
                                  onClick={() => handleAskProject(sug)}
                                  className="text-[11px] text-slate-300 hover:text-white bg-slate-800 hover:bg-sky-600/30 border border-slate-700/60 hover:border-sky-500/50 px-2.5 py-1 rounded-lg transition text-left flex items-center gap-1 group"
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
                    <div className="w-7 h-7 rounded-lg bg-indigo-600/30 border border-indigo-500/40 flex items-center justify-center text-indigo-300 shrink-0 mt-1">
                      <User className="w-4 h-4" />
                    </div>
                  )}
                </div>
              ))
            )}

            {/* AI Reasoning / Loading Indicator */}
            {asking && (
              <div className="flex gap-3 text-xs justify-start">
                <div className="w-7 h-7 rounded-lg bg-sky-600/20 border border-sky-500/30 flex items-center justify-center text-sky-400 shrink-0 mt-1">
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
          <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-3 space-y-2 shrink-0 shadow-lg">
            <div className="flex gap-2">
              <input
                type="text"
                value={askQuery}
                onChange={(e) => setAskQuery(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && !e.shiftKey && handleAskProject()}
                placeholder="Hỏi bất kỳ điều gì về cuộc họp, quyết định, KOT, quy tắc Import CSV, hay lịch running test..."
                className="flex-1 bg-slate-950 border border-slate-800 rounded-xl px-4 py-2.5 text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:border-sky-500 transition font-sans"
              />
              <button
                onClick={() => handleAskProject()}
                disabled={asking || !askQuery.trim()}
                className={`flex items-center gap-1.5 px-5 py-2.5 rounded-xl bg-sky-600 hover:bg-sky-500 disabled:opacity-40 text-white text-xs font-semibold transition shadow-md shadow-sky-600/20 ${
                  asking ? 'btn-loading-shimmer' : ''
                }`}
              >
                {asking ? (
                  <>
                    <div className="w-3.5 h-3.5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                    <span>Đang suy luận...</span>
                  </>
                ) : (
                  <>
                    <Sparkles className="w-3.5 h-3.5" />
                    <span>Hỏi AI</span>
                  </>
                )}
              </button>
            </div>

            {/* Micro hint */}
            <div className="flex items-center justify-between text-[11px] text-slate-500 px-1">
              <span>Nhấn Enter để gửi • Hỗ trợ hội thoại đa vòng (Multi-turn Context)</span>
              <span>Đang kết nối 100% dữ liệu {activeProject ? activeProject.name : 'Tất cả dự án'}</span>
            </div>
          </div>
        </div>
      )}

      {/* ================= TAB 2: SPEC DIFF ================= */}
      {activeTab === 'diff' && (
        <div className="space-y-5">
          <div className="bg-slate-900/70 border border-slate-800 rounded-xl p-4 space-y-3">
            <h2 className="text-sm font-semibold text-white flex items-center gap-2">
              <GitCompare className="w-4 h-4 text-sky-400" />
              So sánh Phiên bản Đặc tả Yêu cầu (What Changed? Spec Diff)
            </h2>
            <p className="text-xs text-slate-400">
              Dán đặc tả cũ vs đặc tả mới (hoặc quyết định cuộc họp) để AI tự động bóc tách các điểm thay đổi, breaking changes và cảnh báo xung đột.
            </p>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="text-[11px] text-slate-400 font-medium block mb-1">Phiên bản A (Đặc tả cũ / Existing Spec)</label>
                <textarea
                  value={oldText}
                  onChange={(e) => setOldText(e.target.value)}
                  placeholder="Dán nội dung đặc tả phiên bản cũ (v1) hoặc quyết định trước đó..."
                  rows={6}
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg p-2.5 text-xs text-slate-200 font-mono resize-none focus:outline-none focus:border-sky-500 placeholder-slate-600"
                />
              </div>

              <div>
                <label className="text-[11px] text-slate-400 font-medium block mb-1">Phiên bản B (Đặc tả mới / New Revision)</label>
                <textarea
                  value={newText}
                  onChange={(e) => setNewText(e.target.value)}
                  placeholder="Dán nội dung đặc tả phiên bản mới (v2) hoặc yêu cầu mới từ khách hàng..."
                  rows={6}
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg p-2.5 text-xs text-slate-200 font-mono resize-none focus:outline-none focus:border-sky-500 placeholder-slate-600"
                />
              </div>
            </div>

            <button
              onClick={handleDiffDocuments}
              disabled={diffing || !oldText.trim() || !newText.trim()}
              className="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-sky-600 hover:bg-sky-500 disabled:opacity-40 text-white text-xs font-semibold transition"
            >
              <Sparkles className="w-3.5 h-3.5" />
              {diffing ? 'Đang phân tích thay đổi...' : 'So sánh & Phát hiện Xung đột'}
            </button>
          </div>

          {/* Diff Result Card */}
          {diffResult && (
            <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-5 space-y-4">
              {diffResult.conflicts?.length > 0 && (
                <div className="bg-rose-950/30 border border-rose-500/40 rounded-lg p-3 space-y-1">
                  <div className="text-xs font-bold text-rose-300 flex items-center gap-1.5">
                    <ShieldAlert className="w-4 h-4" /> Phát hiện Xung đột Kỹ thuật (Potential Conflicts)
                  </div>
                  {diffResult.conflicts.map((c, i) => (
                    <div key={i} className="text-xs text-rose-200">
                      • {c.issue} ({c.recommendation})
                    </div>
                  ))}
                </div>
              )}

              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                {/* Added */}
                <div className="bg-slate-950/60 border border-emerald-500/30 p-3 rounded-lg space-y-2">
                  <div className="text-[11px] font-bold text-emerald-400 uppercase tracking-wider">
                    ➕ Bổ sung mới ({diffResult.added?.length ?? 0})
                  </div>
                  {diffResult.added?.map((a, i) => (
                    <div key={i} className="text-xs text-slate-200">
                      <span className="font-semibold text-emerald-300">{a.item}:</span> {a.description}
                    </div>
                  ))}
                </div>

                {/* Modified */}
                <div className="bg-slate-950/60 border border-amber-500/30 p-3 rounded-lg space-y-2">
                  <div className="text-[11px] font-bold text-amber-400 uppercase tracking-wider">
                    ⚡ Thay đổi / Điều chỉnh ({diffResult.modified?.length ?? 0})
                  </div>
                  {diffResult.modified?.map((m, i) => (
                    <div key={i} className="text-xs text-slate-200 space-y-0.5">
                      <div className="font-semibold text-amber-300">{m.item} ({m.significance})</div>
                      <div className="text-[11px] text-slate-400">Trước: {m.before}</div>
                      <div className="text-[11px] text-slate-200">Sau: {m.after}</div>
                    </div>
                  ))}
                </div>

                {/* Removed */}
                <div className="bg-slate-950/60 border border-rose-500/30 p-3 rounded-lg space-y-2">
                  <div className="text-[11px] font-bold text-rose-400 uppercase tracking-wider">
                    ➖ Loại bỏ ({diffResult.removed?.length ?? 0})
                  </div>
                  {diffResult.removed?.map((r, i) => (
                    <div key={i} className="text-xs text-slate-200">
                      <span className="font-semibold text-rose-300">{r.item}:</span> {r.description}
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* ================= TAB 3: CHANGE IMPACT ANALYSIS ================= */}
      {activeTab === 'impact' && (
        <div className="space-y-5">
          <div className="bg-slate-900/70 border border-slate-800 rounded-xl p-4 space-y-3">
            <h2 className="text-sm font-semibold text-white flex items-center gap-2">
              <Layers className="w-4 h-4 text-sky-400" />
              Phân tích Tác động của Yêu cầu Thay đổi (Change Impact Analysis)
            </h2>
            <p className="text-xs text-slate-400">
              Khi khách hàng yêu cầu thay đổi (CR), lập tức đánh giá ảnh hưởng dây chuyền đến các API, UI Frontend, Test cases và Tiến độ dự án.
            </p>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <div>
                <label className="text-[11px] text-slate-400 block mb-1">Mô tả Yêu cầu Thay đổi (Change Request)</label>
                <input
                  type="text"
                  value={changeDesc}
                  onChange={(e) => setChangeDesc(e.target.value)}
                  placeholder="VD: Chuyển đổi định dạng Seiban sang mã 8 ký tự..."
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 placeholder-slate-600 focus:outline-none focus:border-sky-500"
                />
              </div>
              <div>
                <label className="text-[11px] text-slate-400 block mb-1">Module / Thành phần bị tác động</label>
                <input
                  type="text"
                  value={affectedComponent}
                  onChange={(e) => setAffectedComponent(e.target.value)}
                  placeholder="VD: Quản lý gia công ngoài, Import CSV, KOT..."
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 placeholder-slate-600 focus:outline-none focus:border-sky-500"
                />
              </div>
            </div>

            <button
              onClick={handleAnalyzeImpact}
              disabled={analyzingImpact || !changeDesc.trim()}
              className="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-sky-600 hover:bg-sky-500 disabled:opacity-40 text-white text-xs font-semibold transition"
            >
              <Sparkles className="w-3.5 h-3.5" />
              {analyzingImpact ? 'Đang phân tích tác động...' : 'Phân tích Ảnh hưởng Hệ thống'}
            </button>
          </div>

          {/* Impact Result Card */}
          {impactResult && (
            <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-5 space-y-4">
              <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
                <div className="bg-slate-950/60 border border-slate-800 p-3 rounded-lg">
                  <div className="text-[11px] font-semibold text-sky-400">API Bị Ảnh hưởng</div>
                  <ul className="text-xs text-slate-300 mt-1 space-y-1">
                    {impactResult.impacted_apis?.map((a, i) => (
                      <li key={i}>• {a}</li>
                    ))}
                  </ul>
                </div>

                <div className="bg-slate-950/60 border border-slate-800 p-3 rounded-lg">
                  <div className="text-[11px] font-semibold text-indigo-400">Frontend UI Bị Ảnh hưởng</div>
                  <ul className="text-xs text-slate-300 mt-1 space-y-1">
                    {impactResult.impacted_frontend?.map((f, i) => (
                      <li key={i}>• {f}</li>
                    ))}
                  </ul>
                </div>

                <div className="bg-slate-950/60 border border-slate-800 p-3 rounded-lg">
                  <div className="text-[11px] font-semibold text-amber-400">Test Cases Cần Bổ sung</div>
                  <ul className="text-xs text-slate-300 mt-1 space-y-1">
                    {impactResult.impacted_tests?.map((t, i) => (
                      <li key={i}>• {t}</li>
                    ))}
                  </ul>
                </div>

                <div className="bg-slate-950/60 border border-slate-800 p-3 rounded-lg">
                  <div className="text-[11px] font-semibold text-rose-400">Rủi ro Tiến độ</div>
                  <div className="text-sm font-bold text-white mt-1">{impactResult.schedule_risk}</div>
                  <div className="text-[11px] text-slate-400 mt-1">Cơ sở dữ liệu: {impactResult.database_impact}</div>
                </div>
              </div>

              {impactResult.recommended_actions?.length > 0 && (
                <div className="border-t border-slate-800 pt-3">
                  <div className="text-[11px] font-semibold text-emerald-400 uppercase tracking-wider mb-1">
                    Hành động Đề xuất cho BrSE
                  </div>
                  <ul className="text-xs text-slate-300 space-y-1 list-disc list-inside">
                    {impactResult.recommended_actions.map((act, i) => (
                      <li key={i}>{act}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
};
