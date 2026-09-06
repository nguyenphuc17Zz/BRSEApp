import React, { useState, useEffect, useMemo } from 'react';
import { 
  AlertCircle, 
  CheckCircle2, 
  Clock, 
  HelpCircle, 
  Flame, 
  Sparkles, 
  RefreshCw, 
  Copy, 
  Check, 
  Filter, 
  X, 
  CheckSquare, 
  ShieldAlert,
  Calendar,
  MessageSquare,
  Search,
  Languages,
  FolderGit2,
  ExternalLink,
  ChevronDown,
  Hash,
  Radio,
  Zap,
  User,
  Users,
  UserPlus,
  Edit2,
  Trash2,
  RotateCcw
} from 'lucide-react';
import { useToast } from '../context/ToastContext';
import { useConfirm } from '../context/ConfirmDialogContext';
import { apiClient } from '../api/client';
import { 
  DashboardMetrics, 
  WorkInboxResponse, 
  WorkInboxItem, 
  Project, 
  ProviderInfo,
  ProjectStakeholder
} from '../types';
import { AiThinkingLoader } from '../components/skeletons/AiThinkingLoader';
import { TableSkeleton } from '../components/skeletons/TableSkeleton';
import { MarkdownView } from '../components/MarkdownView';
import { ProviderModelSelector } from '../components/ProviderModelSelector';
import { resolveHealthyModel } from '../utils/aiPreferences';
import { StakeholderManagerModal } from '../components/modals/StakeholderManagerModal';

interface BrSEDashboardProps {
  activeProject: Project | null;
  projects?: Project[];
  setActiveProject?: (project: Project) => void;
}

export const BrSEDashboardPage: React.FC<BrSEDashboardProps> = ({ 
  activeProject, 
  projects = [], 
  setActiveProject 
}) => {
  const [metrics, setMetrics] = useState<DashboardMetrics | null>(null);
  const [inbox, setInbox] = useState<WorkInboxResponse | null>(null);
  const [activeTab, setActiveTab] = useState<'requirements' | 'bugs' | 'decisions' | 'questions' | 'deadlines'>('requirements');
  const [loading, setLoading] = useState<boolean>(true);
  const [analyzing, setAnalyzing] = useState<boolean>(false);
  const [generatingSummary, setGeneratingSummary] = useState<boolean>(false);
  
  // Realtime Live Sync State
  const [autoSync, setAutoSync] = useState<boolean>(true);
  const [lastSyncSeconds, setLastSyncSeconds] = useState<number>(0);
  const [syncingNow, setSyncingNow] = useState<boolean>(false);

  // AI Provider & Model State
  const [providers, setProviders] = useState<ProviderInfo[]>([]);
  const [selectedProvider, setSelectedProvider] = useState<string>('auto');
  const [selectedModel, setSelectedModel] = useState<string>('');

  // Briefing Settings
  const [summaryLanguage, setSummaryLanguage] = useState<'vi' | 'ja' | 'bilingual'>('vi');
  const [summaryMarkdown, setSummaryMarkdown] = useState<string>('');
  const [summaryType, setSummaryType] = useState<'morning' | 'evening'>('morning');
  const [copiedSummary, setCopiedSummary] = useState<boolean>(false);

  // Chat input (Left column)
  const [inputChat, setInputChat] = useState<string>('');
  const [chatAuthor, setChatAuthor] = useState<string>('Client (PM / Lead)');
  const [chatSource, setChatSource] = useState<'slack' | 'line' | 'manual'>('slack');
  const [latestAnalysis, setLatestAnalysis] = useState<any | null>(null);

  // Stakeholders State & Modal
  const [stakeholders, setStakeholders] = useState<ProjectStakeholder[]>([]);
  const [isStakeholderModalOpen, setIsStakeholderModalOpen] = useState<boolean>(false);
  const [editingStakeholderForModal, setEditingStakeholderForModal] = useState<ProjectStakeholder | null>(null);
  const [isCustomAuthor, setIsCustomAuthor] = useState<boolean>(false);

  const toast = useToast();
  const confirm = useConfirm();

  const currentStakeholder = useMemo(() => {
    if (isCustomAuthor || !chatAuthor) return null;
    return stakeholders.find(s => s.name === chatAuthor) || null;
  }, [stakeholders, chatAuthor, isCustomAuthor]);

  const handleQuickEditCurrentStakeholder = () => {
    if (!currentStakeholder) return;
    setEditingStakeholderForModal(currentStakeholder);
    setIsStakeholderModalOpen(true);
  };

  const handleQuickDeleteCurrentStakeholder = async () => {
    if (!currentStakeholder) return;
    const ok = await confirm({
      title: 'Xóa Người nhắn / Stakeholder',
      message: `Bạn có chắc chắn muốn xóa "${currentStakeholder.name}" (${currentStakeholder.role} · ${currentStakeholder.organization}) khỏi danh sách người nhắn của dự án? Thao tác này không thể hoàn tác.`,
      isDestructive: true,
      confirmText: 'Xóa người này',
      cancelText: 'Hủy'
    });
    if (!ok) return;

    try {
      await apiClient.deleteStakeholder(currentStakeholder.id);
      toast.info(`Đã xóa ${currentStakeholder.name} khỏi danh sách.`, 'Đã xóa');
      const remaining = stakeholders.filter(s => s.id !== currentStakeholder.id);
      setStakeholders(remaining);
      if (remaining.length > 0) {
        setChatAuthor(remaining[0].name);
        if (remaining[0].platform === 'line' || remaining[0].platform === 'slack') {
          setChatSource(remaining[0].platform as any);
        }
      } else {
        setChatAuthor('Client (PM / Lead)');
      }
    } catch (err: any) {
      console.error('Delete stakeholder failed:', err);
      toast.error('Không thể xóa người nhắn.', 'Lỗi');
    }
  };

  // Inbox Filters (Right column)
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [filterMeetingId, setFilterMeetingId] = useState<string>('all');
  const [filterPriority, setFilterPriority] = useState<string>('all');
  const [filterConflictOnly, setFilterConflictOnly] = useState<boolean>(false);
  const [filterSource, setFilterSource] = useState<'all' | 'meeting' | 'line' | 'slack' | 'manual'>('all');
  const [statusFilter, setStatusFilter] = useState<'pending' | 'confirmed' | 'rejected' | 'all'>('pending');

  // Feedback Notification
  const [actionFeedback, setActionFeedback] = useState<{ message: string; type: 'success' | 'info' } | null>(null);

  const showFeedback = (message: string, type: 'success' | 'info' = 'success') => {
    setActionFeedback({ message, type });
    setTimeout(() => setActionFeedback(null), 3000);
  };

  const loadData = async (silent: boolean = false) => {
    try {
      if (!silent) setLoading(true);
      else setSyncingNow(true);
      const [m, inb] = await Promise.all([
        apiClient.getBrSEMetrics(activeProject?.id),
        apiClient.getWorkInbox(activeProject?.id)
      ]);
      setMetrics(m);
      setInbox(inb);
      setLastSyncSeconds(0);
    } catch (e) {
      console.error("Failed loading BrSE dashboard data", e);
    } finally {
      setLoading(false);
      setSyncingNow(false);
    }
  };

  const loadStakeholders = async () => {
    if (!activeProject?.id) return;
    try {
      const list = await apiClient.getStakeholders(activeProject.id);
      setStakeholders(list);
      if (list.length > 0) {
        // If current author is not in list, auto-select the first PM or first item
        const hasCurrent = list.some(s => s.name === chatAuthor);
        if (!hasCurrent && !isCustomAuthor) {
          const pm = list.find(s => s.role.toLowerCase().includes('pm')) || list[0];
          setChatAuthor(pm.name);
          if (pm.platform && (pm.platform === 'line' || pm.platform === 'slack')) {
            setChatSource(pm.platform as any);
          }
        }
      } else {
        if (!isCustomAuthor) setChatAuthor('');
      }
    } catch (e) {
      console.error("Failed to load stakeholders", e);
    }
  };

  useEffect(() => {
    loadData(false);
    loadStakeholders();
  }, [activeProject?.id]);

  // Live seconds elapsed counter
  useEffect(() => {
    const timer = setInterval(() => {
      setLastSyncSeconds(prev => prev + 1);
    }, 1000);
    return () => clearInterval(timer);
  }, []);

  // Background Auto-sync polling every 12 seconds
  useEffect(() => {
    if (!autoSync) return;
    const interval = setInterval(() => {
      loadData(true);
    }, 12000);
    return () => clearInterval(interval);
  }, [autoSync, activeProject?.id]);

  useEffect(() => {
    apiClient.getProviders().then((provs) => {
      setProviders(provs);
      const healthy = resolveHealthyModel(provs, 'auto', '');
      setSelectedProvider(healthy.provider);
      setSelectedModel(healthy.model);
    }).catch(console.error);
  }, []);

  const handleAnalyzeChat = async () => {
    if (!inputChat.trim()) return;
    try {
      setAnalyzing(true);
      const res = await apiClient.analyzeConversation({
        text: inputChat,
        project_id: activeProject?.id || 'default-project',
        source_type: chatSource,
        author: chatAuthor,
        save_drafts: true
      });
      setLatestAnalysis(res.analysis);
      setInputChat('');
      showFeedback('Chat analyzed & drafted to Work Inbox!');
      await loadData();
    } catch (e) {
      console.error("Chat analysis failed", e);
    } finally {
      setAnalyzing(false);
    }
  };

  const updateItemStatusInInbox = (id: string, newStatus: string) => {
    setInbox(prev => {
      if (!prev) return prev;
      const updateList = (list: WorkInboxItem[] = []) =>
        list.map(it => it.id === id ? { ...it, status: newStatus } : it);
      return {
        ...prev,
        requirements: updateList(prev.requirements),
        bugs: updateList(prev.bugs),
        decisions: updateList(prev.decisions),
        questions: updateList(prev.questions),
        deadlines: updateList(prev.deadlines)
      };
    });
  };

  const handleConfirmItem = async (id: string) => {
    try {
      updateItemStatusInInbox(id, 'CONFIRMED');
      toast.success('Đã xác nhận mục công việc & đồng bộ vào Tri thức dự án!', 'Đã duyệt');
      await apiClient.confirmWorkItem(id);
      loadData(true);
    } catch (e) {
      console.error("Confirm failed", e);
      toast.error('Không thể duyệt mục này. Vui lòng thử lại.', 'Lỗi');
      loadData(true);
    }
  };

  const handleRejectItem = async (id: string) => {
    try {
      updateItemStatusInInbox(id, 'REJECTED');
      toast.info('Đã từ chối mục công việc.', 'Đã từ chối');
      await apiClient.rejectWorkItem(id);
      loadData(true);
    } catch (e) {
      console.error("Reject failed", e);
      toast.error('Không thể từ chối mục này.', 'Lỗi');
      loadData(true);
    }
  };

  const handleResetItem = async (id: string) => {
    try {
      updateItemStatusInInbox(id, 'PROPOSED');
      toast.info('Đã hoàn tác mục công việc về trạng thái Chờ duyệt.', 'Đã hoàn tác');
      await apiClient.resetWorkItem(id);
      loadData(true);
    } catch (e) {
      console.error("Reset failed", e);
      toast.error('Không thể hoàn tác mục này.', 'Lỗi');
      loadData(true);
    }
  };

  const handleGenerateSummary = async (type: 'morning' | 'evening') => {
    try {
      setGeneratingSummary(true);
      setSummaryType(type);
      const res = await apiClient.generateDailySummary(
        activeProject?.id, 
        type === 'morning' ? 'morning' : 'evening',
        selectedProvider,
        selectedModel,
        summaryLanguage
      );
      setSummaryMarkdown(res.markdown);
      showFeedback(`${type === 'morning' ? 'Morning Briefing' : 'End-of-Day Wrap-up'} generated!`);
    } catch (e) {
      console.error("Summary generation failed", e);
    } finally {
      setGeneratingSummary(false);
    }
  };

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedSummary(true);
    setTimeout(() => setCopiedSummary(false), 2000);
  };

  // Compute platform source counts for the active tab
  const sourceCounts = useMemo(() => {
    if (!inbox) return { all: 0, meeting: 0, line: 0, slack: 0, manual: 0 };
    let baseList: WorkInboxItem[] = [];
    switch (activeTab) {
      case 'requirements': baseList = inbox.requirements || []; break;
      case 'bugs': baseList = inbox.bugs || []; break;
      case 'decisions': baseList = inbox.decisions || []; break;
      case 'questions': baseList = inbox.questions || []; break;
      case 'deadlines': baseList = inbox.deadlines || []; break;
      default: baseList = [];
    }
    const counts = { all: baseList.length, meeting: 0, line: 0, slack: 0, manual: 0 };
    for (const it of baseList) {
      const s = (it.source_type || it.evidence?.[0]?.source_type || (it.meeting_id ? 'meeting' : 'manual')).toLowerCase();
      if (s.includes('meeting')) counts.meeting++;
      else if (s.includes('line')) counts.line++;
      else if (s.includes('slack')) counts.slack++;
      else counts.manual++;
    }
    return counts;
  }, [inbox, activeTab]);

  // Compute status breakdown counts for the active tab
  const statusCounts = useMemo(() => {
    if (!inbox) return { pending: 0, confirmed: 0, rejected: 0, all: 0 };
    let baseList: WorkInboxItem[] = [];
    switch (activeTab) {
      case 'requirements': baseList = inbox.requirements || []; break;
      case 'bugs': baseList = inbox.bugs || []; break;
      case 'decisions': baseList = inbox.decisions || []; break;
      case 'questions': baseList = inbox.questions || []; break;
      case 'deadlines': baseList = inbox.deadlines || []; break;
      default: baseList = [];
    }
    const counts = { pending: 0, confirmed: 0, rejected: 0, all: baseList.length };
    for (const it of baseList) {
      const st = (it.status || 'PROPOSED').toUpperCase();
      if (st === 'CONFIRMED') counts.confirmed++;
      else if (st === 'REJECTED') counts.rejected++;
      else counts.pending++;
    }
    return counts;
  }, [inbox, activeTab]);

  // Filter inbox items
  const filteredItems = useMemo(() => {
    if (!inbox) return [];
    
    let baseList: WorkInboxItem[] = [];
    switch (activeTab) {
      case 'requirements': baseList = inbox.requirements || []; break;
      case 'bugs': baseList = inbox.bugs || []; break;
      case 'decisions': baseList = inbox.decisions || []; break;
      case 'questions': baseList = inbox.questions || []; break;
      case 'deadlines': baseList = inbox.deadlines || []; break;
      default: baseList = [];
    }

    return baseList.filter((item) => {
      // Status filter
      const st = (item.status || 'PROPOSED').toUpperCase();
      if (statusFilter === 'pending' && (st === 'CONFIRMED' || st === 'REJECTED')) return false;
      if (statusFilter === 'confirmed' && st !== 'CONFIRMED') return false;
      if (statusFilter === 'rejected' && st !== 'REJECTED') return false;

      // Source platform filter
      if (filterSource !== 'all') {
        const itemSource = (item.source_type || item.evidence?.[0]?.source_type || (item.meeting_id ? 'meeting' : 'manual')).toLowerCase();
        if (filterSource === 'meeting' && !itemSource.includes('meeting')) return false;
        if (filterSource === 'line' && !itemSource.includes('line')) return false;
        if (filterSource === 'slack' && !itemSource.includes('slack')) return false;
        if (filterSource === 'manual' && (itemSource.includes('line') || itemSource.includes('slack') || itemSource.includes('meeting'))) return false;
      }

      // Conflict filter
      if (filterConflictOnly && !item.is_conflict) return false;

      // Priority filter
      if (filterPriority !== 'all' && (item.priority || '').toUpperCase() !== filterPriority) {
        return false;
      }

      // Meeting filter
      if (filterMeetingId !== 'all' && item.meeting_id !== filterMeetingId) {
        return false;
      }

      // Keyword search
      if (searchQuery.trim()) {
        const query = searchQuery.toLowerCase();
        const inTitle = (item.title || '').toLowerCase().includes(query);
        const inDesc = (item.description || '').toLowerCase().includes(query);
        const inNotes = (item.conflict_notes || '').toLowerCase().includes(query);
        const inEvidence = (item.evidence || []).some(ev => (ev.quote || '').toLowerCase().includes(query));
        if (!inTitle && !inDesc && !inNotes && !inEvidence) {
          return false;
        }
      }

      return true;
    });
  }, [inbox, activeTab, statusFilter, searchQuery, filterMeetingId, filterPriority, filterConflictOnly, filterSource]);

  return (
    <div className="flex-1 overflow-y-auto bg-slate-950 p-6 space-y-6">
      {/* Toast Feedback */}
      {actionFeedback && (
        <div className="fixed bottom-6 right-6 z-50 flex items-center gap-2 px-4 py-2.5 rounded-xl bg-slate-900 border border-emerald-500/50 text-emerald-300 text-xs font-medium shadow-2xl shadow-emerald-950/50 animate-in fade-in slide-in-from-bottom-3 duration-200">
          <CheckCircle2 className="w-4 h-4 text-emerald-400" />
          <span>{actionFeedback.message}</span>
        </div>
      )}

      {/* Top Header & Operational Control Bar */}
      <div className="flex flex-col xl:flex-row xl:items-center justify-between gap-4 border-b border-slate-800 pb-5">
        <div className="space-y-1">
          <div className="flex items-center gap-2.5 flex-wrap">
            <span className="px-2 py-0.5 rounded text-[11px] font-bold uppercase tracking-wider bg-sky-500/20 text-sky-400 border border-sky-500/30">
              Phase 4 Core
            </span>
            <h1 className="text-xl font-bold text-white tracking-tight">BrSE Daily Workspace</h1>

            {/* Project Switcher Dropdown */}
            {projects && projects.length > 0 && (
              <div className="flex items-center gap-1.5 bg-slate-900 border border-slate-700/80 rounded-lg px-2.5 py-1 text-xs">
                <FolderGit2 className="w-3.5 h-3.5 text-sky-400" />
                <select
                  value={activeProject?.id || ''}
                  onChange={(e) => {
                    const found = projects.find(p => p.id === e.target.value);
                    if (found && setActiveProject) setActiveProject(found);
                  }}
                  className="bg-transparent text-slate-200 font-medium focus:outline-none cursor-pointer"
                >
                  {projects.map((p) => (
                    <option key={p.id} value={p.id} className="bg-slate-900 text-slate-200">
                      {p.name}
                    </option>
                  ))}
                </select>
              </div>
            )}
          </div>
          <p className="text-xs text-slate-400">
            Real-time project intelligence, meeting decisions review, and automated executive daily briefings.
          </p>
        </div>

        {/* AI Model & Executive Briefing Toolbar */}
        <div className="flex items-center gap-2.5 flex-wrap">
          {/* Provider & Model Selector */}
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

          {/* Language Selector for Briefings */}
          <div className="flex items-center bg-slate-900 border border-slate-800 rounded-xl p-0.5 text-xs">
            <button
              onClick={() => setSummaryLanguage('vi')}
              className={`px-2.5 py-1 rounded-lg font-medium transition ${
                summaryLanguage === 'vi'
                  ? 'bg-sky-500/20 text-sky-300 border border-sky-500/30 font-semibold'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
              title="Tiếng Việt 100% (Dành cho Dev Team Việt Nam)"
            >
              Tiếng Việt
            </button>
            <button
              onClick={() => setSummaryLanguage('ja')}
              className={`px-2.5 py-1 rounded-lg font-medium transition ${
                summaryLanguage === 'ja'
                  ? 'bg-sky-500/20 text-sky-300 border border-sky-500/30 font-semibold'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
              title="日本語 100% (Chuẩn Business Keigo gửi Khách Nhật)"
            >
              日本語 (Khách Nhật)
            </button>
            <button
              onClick={() => setSummaryLanguage('bilingual')}
              className={`px-2.5 py-1 rounded-lg font-medium transition ${
                summaryLanguage === 'bilingual'
                  ? 'bg-sky-500/20 text-sky-300 border border-sky-500/30 font-semibold'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
              title="Song ngữ Nhật - Việt (Chuẩn BrSE)"
            >
              Song ngữ (JP/VI)
            </button>
          </div>

          {/* Daily Briefing Actions */}
          <button
            onClick={() => handleGenerateSummary('morning')}
            disabled={generatingSummary}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-amber-500/10 text-amber-300 border border-amber-500/30 hover:bg-amber-500/20 text-xs font-semibold transition disabled:opacity-50"
            title="Tạo tóm tắt chuẩn bị đầu ngày từ các meeting và quyết định mới"
          >
            <Sparkles className="w-3.5 h-3.5 text-amber-400" />
            {generatingSummary && summaryType === 'morning' ? 'Generating...' : 'Morning Briefing'}
          </button>

          <button
            onClick={() => handleGenerateSummary('evening')}
            disabled={generatingSummary}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-indigo-500/10 text-indigo-300 border border-indigo-500/30 hover:bg-indigo-500/20 text-xs font-semibold transition disabled:opacity-50"
            title="Tạo báo cáo tổng hợp cuối ngày cho khách hàng và team dev"
          >
            <Clock className="w-3.5 h-3.5 text-indigo-400" />
            {generatingSummary && summaryType === 'evening' ? 'Generating...' : 'End-of-Day Wrap-up'}
          </button>

          {/* Live Auto-Sync Indicator & Toggle */}
          <div className="flex items-center gap-2 bg-slate-900 border border-slate-800 rounded-xl px-2.5 py-1 text-xs">
            <button
              onClick={() => setAutoSync(!autoSync)}
              className="flex items-center gap-1.5 text-slate-300 hover:text-white transition"
              title={autoSync ? "Tự động đồng bộ mỗi 12 giây đang BẬT. Nhấp để tạm dừng." : "Tự động đồng bộ đang TẮT. Nhấp để bật."}
            >
              <span className="relative flex h-2 w-2">
                {autoSync && (
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                )}
                <span className={`relative inline-flex rounded-full h-2 w-2 ${autoSync ? 'bg-emerald-500' : 'bg-slate-600'}`}></span>
              </span>
              <span className="font-mono text-[11px]">
                {autoSync ? (syncingNow ? 'Syncing...' : `Live (${lastSyncSeconds}s)`) : 'Sync Paused'}
              </span>
            </button>
            <div className="h-3 w-[1px] bg-slate-800" />
            <button
              onClick={() => loadData(false)}
              className="text-slate-400 hover:text-sky-400 transition"
              title="Refresh All Metrics & Inbox"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${loading || syncingNow ? 'animate-spin text-sky-400' : ''}`} />
            </button>
          </div>
        </div>
      </div>

      {/* Metrics Row (Interactive overview) */}
      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-3.5">
        <div 
          onClick={() => { setActiveTab('requirements'); setFilterPriority('CRITICAL'); }}
          className="bg-slate-900/70 border border-rose-500/30 rounded-xl p-4 flex items-center gap-3 cursor-pointer hover:border-rose-500/60 hover:bg-slate-900 transition"
        >
          <div className="w-10 h-10 rounded-lg bg-rose-500/20 flex items-center justify-center text-rose-400">
            <Flame className="w-5 h-5" />
          </div>
          <div>
            <div className="text-2xl font-bold text-white">{metrics?.urgent_count ?? 0}</div>
            <div className="text-[11px] text-slate-400 font-medium">🔴 Urgent Items</div>
          </div>
        </div>

        <div 
          onClick={() => { setActiveTab('questions'); setFilterPriority('all'); }}
          className="bg-slate-900/70 border border-amber-500/30 rounded-xl p-4 flex items-center gap-3 cursor-pointer hover:border-amber-500/60 hover:bg-slate-900 transition"
        >
          <div className="w-10 h-10 rounded-lg bg-amber-500/20 flex items-center justify-center text-amber-400">
            <HelpCircle className="w-5 h-5" />
          </div>
          <div>
            <div className="text-2xl font-bold text-white">{metrics?.open_questions_count ?? 0}</div>
            <div className="text-[11px] text-slate-400 font-medium">🟠 Open Questions</div>
          </div>
        </div>

        <div 
          onClick={() => { setActiveTab('deadlines'); setFilterPriority('all'); }}
          className="bg-slate-900/70 border border-yellow-500/30 rounded-xl p-4 flex items-center gap-3 cursor-pointer hover:border-yellow-500/60 hover:bg-slate-900 transition"
        >
          <div className="w-10 h-10 rounded-lg bg-yellow-500/20 flex items-center justify-center text-yellow-400">
            <Clock className="w-5 h-5" />
          </div>
          <div>
            <div className="text-2xl font-bold text-white">{metrics?.deadlines_count ?? 0}</div>
            <div className="text-[11px] text-slate-400 font-medium">🟡 Deadlines</div>
          </div>
        </div>

        <div 
          onClick={() => { setFilterConflictOnly(!filterConflictOnly); }}
          className={`bg-slate-900/70 border rounded-xl p-4 flex items-center gap-3 cursor-pointer transition ${
            filterConflictOnly 
              ? 'border-orange-500 bg-orange-950/20 ring-1 ring-orange-500' 
              : 'border-orange-500/30 hover:border-orange-500/60'
          }`}
          title="Click to toggle Conflict filter"
        >
          <div className="w-10 h-10 rounded-lg bg-orange-500/20 flex items-center justify-center text-orange-400">
            <ShieldAlert className="w-5 h-5" />
          </div>
          <div>
            <div className="text-2xl font-bold text-white">{metrics?.conflicts_count ?? 0}</div>
            <div className="text-[11px] text-slate-400 font-medium">
              ⚠️ Conflicts {filterConflictOnly ? '(Filtered)' : ''}
            </div>
          </div>
        </div>

        <div 
          onClick={() => { setActiveTab('decisions'); setFilterPriority('all'); }}
          className="bg-slate-900/70 border border-emerald-500/30 rounded-xl p-4 flex items-center gap-3 cursor-pointer hover:border-emerald-500/60 hover:bg-slate-900 transition"
        >
          <div className="w-10 h-10 rounded-lg bg-emerald-500/20 flex items-center justify-center text-emerald-400">
            <CheckCircle2 className="w-5 h-5" />
          </div>
          <div>
            <div className="text-2xl font-bold text-white">{metrics?.recent_decisions_count ?? metrics?.completed_count ?? 0}</div>
            <div className="text-[11px] text-slate-400 font-medium">🟢 Decisions / Done</div>
          </div>
        </div>
      </div>

      {/* Daily Summary Preview Box (Enhanced with MarkdownView) */}
      {(summaryMarkdown || generatingSummary) && (
        <div className="bg-slate-900/95 border border-sky-500/40 rounded-xl p-5 space-y-3 shadow-xl relative animate-in fade-in duration-200">
          <div className="flex items-center justify-between border-b border-slate-800 pb-3">
            <div className="flex items-center gap-2 text-sky-400 text-xs font-semibold">
              <Sparkles className="w-4 h-4 text-sky-400 animate-pulse" />
              <span>
                {summaryLanguage === 'ja'
                  ? (summaryType === 'morning' ? '朝会サマリー・本日の進捗計画' : '日次進捗報告・夕会ラップアップ')
                  : (summaryType === 'morning' ? 'Executive Morning Briefing' : 'End-of-Day Wrap-up Report')}
                {' — '}
                <span className="text-slate-300 font-normal">
                  {summaryLanguage === 'vi' 
                    ? '🇻🇳 Tiếng Việt (Dev Team)' 
                    : summaryLanguage === 'ja' 
                    ? '🇯🇵 日本語 (ビジネス敬語)' 
                    : '🌐 Song ngữ JP / VI'}
                </span>
              </span>
            </div>
            <div className="flex items-center gap-2">
              {summaryMarkdown && (
                <button
                  onClick={() => copyToClipboard(summaryMarkdown)}
                  className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 font-medium transition shadow-sm"
                >
                  {copiedSummary ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
                  {copiedSummary ? 'Copied to Clipboard' : 'Copy Markdown'}
                </button>
              )}
              <button
                onClick={() => setSummaryMarkdown('')}
                className="p-1.5 rounded-lg text-slate-500 hover:text-slate-300 hover:bg-slate-800 transition"
                title="Close summary"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
          </div>

          {generatingSummary ? (
            <div className="py-6">
              <AiThinkingLoader mode="rag" title="Đang tổng hợp dữ liệu họp & quyết định thành Executive Briefing..." />
            </div>
          ) : (
            <div className="bg-slate-950/80 p-4 rounded-xl border border-slate-800/80 max-h-[500px] overflow-y-auto">
              <MarkdownView content={summaryMarkdown} accent="sky" />
            </div>
          )}
        </div>
      )}

      {/* Main Two Column Area: Chat Analyzer & Work Item Review Inbox */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left Column: Smart Conversation / Message Analyzer */}
        <div className="lg:col-span-5 bg-slate-900/70 border border-slate-800 rounded-xl p-5 flex flex-col space-y-4">
          <div className="flex items-center justify-between border-b border-slate-800 pb-3">
            <div className="flex items-center gap-2">
              <MessageSquare className="w-4 h-4 text-sky-400" />
              <h2 className="text-sm font-semibold text-white">Smart Message Analyzer</h2>
            </div>
            <span className="text-[11px] text-slate-400 font-mono">Slack / LINE / Chat</span>
          </div>

          <p className="text-xs text-slate-400">
            Dán tin nhắn trao đổi với khách hàng Nhật để AI tự động trích xuất Yêu cầu (Requirements), Task cần làm (TODOs), Deadlines và kiểm tra xung đột với Specs hiện tại.
          </p>

          <div className="grid grid-cols-2 gap-2 text-xs">
            <div>
              <label className="text-slate-400 text-[11px] block mb-1 font-medium">Source Platform</label>
              <select
                value={chatSource}
                onChange={(e) => setChatSource(e.target.value as any)}
                className="w-full bg-slate-950 border border-slate-800 rounded-lg px-2.5 py-1.5 text-slate-200 text-xs focus:ring-1 focus:ring-sky-500 focus:outline-none"
              >
                <option value="slack">Slack Thread</option>
                <option value="line">LINE Message</option>
                <option value="manual">Direct / Pasted Chat</option>
              </select>
            </div>
            <div>
              <div className="flex items-center justify-between mb-1">
                <label className="text-slate-400 text-[11px] font-medium">Speaker / Author</label>
                <button
                  type="button"
                  onClick={() => {
                    setEditingStakeholderForModal(null);
                    setIsStakeholderModalOpen(true);
                  }}
                  className="text-[10.5px] text-sky-400 hover:text-sky-300 flex items-center gap-1 cursor-pointer transition font-medium"
                  title="Quản lý danh sách Người nhắn & Stakeholders"
                >
                  <Users className="w-3 h-3" />
                  <span>Quản lý ({stakeholders.length})</span>
                </button>
              </div>

              {isCustomAuthor ? (
                <div className="flex items-center gap-1.5">
                  <input
                    type="text"
                    value={chatAuthor}
                    onChange={(e) => setChatAuthor(e.target.value)}
                    placeholder="Nhập tên người nhắn..."
                    className="flex-1 bg-slate-950 border border-slate-800 rounded-lg px-2.5 py-1.5 text-slate-200 text-xs focus:ring-1 focus:ring-sky-500 focus:outline-none"
                    autoFocus
                  />
                  <button
                    type="button"
                    onClick={() => {
                      setIsCustomAuthor(false);
                      if (stakeholders.length > 0) setChatAuthor(stakeholders[0].name);
                    }}
                    className="px-2 py-1.5 text-[10px] rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 transition shrink-0 cursor-pointer"
                    title="Quay lại danh sách chọn"
                  >
                    Chọn lại
                  </button>
                </div>
              ) : (
                <div className="flex items-center gap-1.5">
                  <select
                    value={chatAuthor}
                    onChange={(e) => {
                      if (e.target.value === '__custom__') {
                        setIsCustomAuthor(true);
                        setChatAuthor('');
                      } else {
                        setChatAuthor(e.target.value);
                        const found = stakeholders.find(s => s.name === e.target.value);
                        if (found && (found.platform === 'line' || found.platform === 'slack')) {
                          setChatSource(found.platform as any);
                        }
                      }
                    }}
                    className="flex-1 min-w-0 bg-slate-950 border border-slate-800 rounded-lg px-2.5 py-1.5 text-slate-200 text-xs focus:ring-1 focus:ring-sky-500 focus:outline-none cursor-pointer truncate"
                  >
                    {stakeholders.length === 0 && (
                      <option value="">Chưa có người nhắn nào</option>
                    )}
                    {stakeholders.map((s) => (
                      <option key={s.id} value={s.name}>
                        {s.name} ({s.role} · {s.organization})
                      </option>
                    ))}
                    <option value="__custom__">➕ Nhập tên tùy chỉnh...</option>
                  </select>

                  <div className="flex items-center gap-1 shrink-0">
                    <button
                      type="button"
                      onClick={() => {
                        setEditingStakeholderForModal(null);
                        setIsStakeholderModalOpen(true);
                      }}
                      className="p-1.5 rounded-lg text-slate-400 hover:text-emerald-400 hover:bg-slate-800 border border-slate-800/80 transition cursor-pointer"
                      title="Thêm người nhắn mới"
                    >
                      <UserPlus className="w-3.5 h-3.5" />
                    </button>
                    <button
                      type="button"
                      onClick={handleQuickEditCurrentStakeholder}
                      disabled={!currentStakeholder}
                      className="p-1.5 rounded-lg text-slate-400 hover:text-amber-300 hover:bg-slate-800 disabled:opacity-30 disabled:cursor-not-allowed border border-slate-800/80 transition cursor-pointer"
                      title={currentStakeholder ? `Sửa thông tin: ${currentStakeholder.name}` : 'Chọn một người để sửa'}
                    >
                      <Edit2 className="w-3.5 h-3.5" />
                    </button>
                    <button
                      type="button"
                      onClick={handleQuickDeleteCurrentStakeholder}
                      disabled={!currentStakeholder}
                      className="p-1.5 rounded-lg text-slate-400 hover:text-rose-400 hover:bg-slate-800 disabled:opacity-30 disabled:cursor-not-allowed border border-slate-800/80 transition cursor-pointer"
                      title={currentStakeholder ? `Xóa người nhắn: ${currentStakeholder.name}` : 'Chọn một người để xóa'}
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>
              )}
            </div>
          </div>

          <textarea
            value={inputChat}
            onChange={(e) => setInputChat(e.target.value)}
            placeholder="Dán tin nhắn trao đổi (tiếng Nhật hoặc tiếng Việt) từ khách hàng, Slack hoặc LINE để AI tự động phân tích và trích xuất..."
            rows={6}
            className="w-full bg-slate-950 border border-slate-800 rounded-xl p-3 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-sky-500 transition resize-none font-mono leading-relaxed"
          />

          <button
            onClick={handleAnalyzeChat}
            disabled={analyzing || !inputChat.trim()}
            className={`flex items-center justify-center gap-2 w-full py-2.5 px-4 rounded-xl bg-sky-600 hover:bg-sky-500 disabled:opacity-50 text-white text-xs font-semibold transition shadow-md ${
              analyzing ? 'btn-loading-shimmer shadow-lg shadow-sky-600/30' : ''
            }`}
          >
            {analyzing ? (
              <>
                <div className="w-3.5 h-3.5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                <span>Analyzing Intelligence & Conflict Check...</span>
              </>
            ) : (
              <>
                <Sparkles className="w-3.5 h-3.5" />
                <span>Analyze & Draft to Work Inbox</span>
              </>
            )}
          </button>

          {analyzing && (
            <AiThinkingLoader mode="analyze" className="mt-2" />
          )}

          {/* Quick analysis output preview */}
          {latestAnalysis && (
            <div className="border-t border-slate-800 pt-3 space-y-2 text-xs">
              <div className="text-[11px] font-semibold text-slate-300 uppercase tracking-wider flex items-center gap-1.5">
                <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
                Latest Analysis Highlights
              </div>
              <div className="bg-slate-950/80 p-3 rounded-lg border border-slate-800 space-y-1.5 text-slate-300">
                <div className="text-sky-400 font-medium">Context: {latestAnalysis.summary?.context || 'Analyzed message'}</div>
                {latestAnalysis.requirements?.length > 0 && (
                  <div className="text-amber-300">⚡ {latestAnalysis.requirements.length} requirement(s) drafted</div>
                )}
                {latestAnalysis.todos?.length > 0 && (
                  <div className="text-emerald-300">✅ {latestAnalysis.todos.length} action item(s) drafted</div>
                )}
              </div>
            </div>
          )}
        </div>

        {/* Right Column: Work Inbox (Human-in-the-loop Approval) */}
        <div className="lg:col-span-7 bg-slate-900/70 border border-slate-800 rounded-xl p-5 flex flex-col space-y-4">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-slate-800 pb-3">
            <div>
              <h2 className="text-sm font-semibold text-white">Work Inbox — Operational Review</h2>
              <p className="text-[11px] text-slate-400">
                AI trích xuất & đối chiếu tự động. BrSE xác nhận (Confirm) để đưa vào Project Brain hoặc Từ chối (Reject).
              </p>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-xs px-2.5 py-0.5 rounded-full bg-sky-500/10 text-sky-300 border border-sky-500/20 font-mono">
                {inbox?.total_pending ?? 0} Pending
              </span>
            </div>
          </div>

          {/* Search and Filters Bar */}
          <div className="grid grid-cols-1 sm:grid-cols-12 gap-2 text-xs">
            {/* Search Input */}
            <div className="sm:col-span-6 relative">
              <Search className="w-3.5 h-3.5 text-slate-500 absolute left-3 top-1/2 -translate-y-1/2" />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Tìm theo tiêu đề, trích dẫn, specs..."
                className="w-full bg-slate-950 border border-slate-800 rounded-lg pl-8 pr-8 py-1.5 text-xs text-slate-200 placeholder-slate-500 focus:ring-1 focus:ring-sky-500 focus:outline-none"
              />
              {searchQuery && (
                <button
                  onClick={() => setSearchQuery('')}
                  className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300"
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              )}
            </div>

            {/* Meeting Filter Dropdown */}
            <div className="sm:col-span-3">
              <select
                value={filterMeetingId}
                onChange={(e) => setFilterMeetingId(e.target.value)}
                className="w-full bg-slate-950 border border-slate-800 rounded-lg px-2.5 py-1.5 text-xs text-slate-300 focus:ring-1 focus:ring-sky-500 focus:outline-none"
              >
                <option value="all">Tất cả Meetings</option>
                {(inbox?.meetings || []).map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.date ? `${m.date.split('T')[0]}: ` : ''}{m.title.length > 25 ? m.title.substring(0, 25) + '...' : m.title}
                  </option>
                ))}
              </select>
            </div>

            {/* Priority Filter */}
            <div className="sm:col-span-3">
              <select
                value={filterPriority}
                onChange={(e) => setFilterPriority(e.target.value)}
                className="w-full bg-slate-950 border border-slate-800 rounded-lg px-2.5 py-1.5 text-xs text-slate-300 focus:ring-1 focus:ring-sky-500 focus:outline-none"
              >
                <option value="all">Mọi Priority</option>
                <option value="CRITICAL">🔴 Critical</option>
                <option value="HIGH">🟠 High</option>
                <option value="MEDIUM">🟡 Medium</option>
                <option value="LOW">⚪ Low</option>
              </select>
            </div>
          </div>

          {/* Source Platform Filter Pills */}
          <div className="flex items-center gap-1.5 overflow-x-auto pb-1 text-xs">
            <span className="text-[11px] text-slate-500 font-medium mr-1 flex items-center gap-1 flex-shrink-0">
              <Filter className="w-3 h-3" /> Source:
            </span>
            <button
              type="button"
              onClick={() => setFilterSource('all')}
              className={`px-2.5 py-1 rounded-lg font-medium transition flex items-center gap-1.5 flex-shrink-0 text-xs ${
                filterSource === 'all'
                  ? 'bg-slate-800 text-white border border-slate-700 font-semibold shadow-sm'
                  : 'text-slate-400 hover:text-slate-200 bg-slate-950/60 border border-slate-800/80'
              }`}
            >
              All Sources ({sourceCounts.all})
            </button>
            <button
              type="button"
              onClick={() => setFilterSource('line')}
              className={`px-2.5 py-1 rounded-lg font-medium transition flex items-center gap-1.5 flex-shrink-0 text-xs ${
                filterSource === 'line'
                  ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 font-semibold shadow-sm shadow-emerald-950/50'
                  : 'text-slate-400 hover:text-emerald-300 bg-slate-950/60 border border-slate-800/80'
              }`}
            >
              <MessageSquare className="w-3 h-3 text-emerald-400" />
              LINE Chat ({sourceCounts.line})
            </button>
            <button
              type="button"
              onClick={() => setFilterSource('slack')}
              className={`px-2.5 py-1 rounded-lg font-medium transition flex items-center gap-1.5 flex-shrink-0 text-xs ${
                filterSource === 'slack'
                  ? 'bg-purple-500/20 text-purple-300 border border-purple-500/40 font-semibold shadow-sm shadow-purple-950/50'
                  : 'text-slate-400 hover:text-purple-300 bg-slate-950/60 border border-slate-800/80'
              }`}
            >
              <Hash className="w-3 h-3 text-purple-400" />
              Slack ({sourceCounts.slack})
            </button>
            <button
              type="button"
              onClick={() => setFilterSource('meeting')}
              className={`px-2.5 py-1 rounded-lg font-medium transition flex items-center gap-1.5 flex-shrink-0 text-xs ${
                filterSource === 'meeting'
                  ? 'bg-sky-500/20 text-sky-300 border border-sky-500/40 font-semibold shadow-sm shadow-sky-950/50'
                  : 'text-slate-400 hover:text-sky-300 bg-slate-950/60 border border-slate-800/80'
              }`}
            >
              <Calendar className="w-3 h-3 text-sky-400" />
              Meetings ({sourceCounts.meeting})
            </button>
            <button
              type="button"
              onClick={() => setFilterSource('manual')}
              className={`px-2.5 py-1 rounded-lg font-medium transition flex items-center gap-1.5 flex-shrink-0 text-xs ${
                filterSource === 'manual'
                  ? 'bg-amber-500/20 text-amber-300 border border-amber-500/40 font-semibold shadow-sm shadow-amber-950/50'
                  : 'text-slate-400 hover:text-amber-300 bg-slate-950/60 border border-slate-800/80'
              }`}
            >
              <User className="w-3 h-3 text-amber-400" />
              Direct / Web ({sourceCounts.manual})
            </button>
          </div>

          {/* Inbox Category Tabs */}
          <div className="flex items-center gap-1.5 overflow-x-auto pb-1 border-b border-slate-800/80 text-xs">
            <button
              onClick={() => setActiveTab('requirements')}
              className={`px-3 py-1.5 rounded-lg font-medium transition flex items-center gap-1.5 flex-shrink-0 cursor-pointer ${
                activeTab === 'requirements' ? 'bg-sky-500/20 text-sky-300 border border-sky-500/30' : 'text-slate-400 hover:text-white'
              }`}
            >
              Requirements ({inbox?.requirements?.length ?? 0})
            </button>
            <button
              onClick={() => setActiveTab('bugs')}
              className={`px-3 py-1.5 rounded-lg font-medium transition flex items-center gap-1.5 flex-shrink-0 cursor-pointer ${
                activeTab === 'bugs' ? 'bg-rose-500/20 text-rose-300 border border-rose-500/30' : 'text-slate-400 hover:text-white'
              }`}
            >
              Bugs ({inbox?.bugs?.length ?? 0})
            </button>
            <button
              onClick={() => setActiveTab('decisions')}
              className={`px-3 py-1.5 rounded-lg font-medium transition flex items-center gap-1.5 flex-shrink-0 cursor-pointer ${
                activeTab === 'decisions' ? 'bg-indigo-500/20 text-indigo-300 border border-indigo-500/30' : 'text-slate-400 hover:text-white'
              }`}
            >
              Decisions ({inbox?.decisions?.length ?? 0})
            </button>
            <button
              onClick={() => setActiveTab('questions')}
              className={`px-3 py-1.5 rounded-lg font-medium transition flex items-center gap-1.5 flex-shrink-0 cursor-pointer ${
                activeTab === 'questions' ? 'bg-amber-500/20 text-amber-300 border border-amber-500/30' : 'text-slate-400 hover:text-white'
              }`}
            >
              Questions ({inbox?.questions?.length ?? 0})
            </button>
            <button
              onClick={() => setActiveTab('deadlines')}
              className={`px-3 py-1.5 rounded-lg font-medium transition flex items-center gap-1.5 flex-shrink-0 cursor-pointer ${
                activeTab === 'deadlines' ? 'bg-yellow-500/20 text-yellow-300 border border-yellow-500/30' : 'text-slate-400 hover:text-white'
              }`}
            >
              Deadlines ({inbox?.deadlines?.length ?? 0})
            </button>
          </div>

          {/* Status Sub-filter Bar */}
          <div className="flex items-center justify-between bg-slate-950/70 p-1.5 rounded-lg border border-slate-800 text-xs">
            <div className="flex items-center gap-1 flex-wrap">
              <button
                type="button"
                onClick={() => setStatusFilter('pending')}
                className={`px-2.5 py-1 rounded-md text-[11px] font-medium transition flex items-center gap-1.5 cursor-pointer ${
                  statusFilter === 'pending'
                    ? 'bg-amber-500/20 text-amber-300 border border-amber-500/40 shadow-sm'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                <span>⏳ Chờ duyệt</span>
                <span className={`px-1.5 py-0.2 rounded-full text-[10px] font-bold ${
                  statusFilter === 'pending' ? 'bg-amber-500 text-slate-950' : 'bg-slate-800 text-slate-400'
                }`}>
                  {statusCounts.pending}
                </span>
              </button>

              <button
                type="button"
                onClick={() => setStatusFilter('confirmed')}
                className={`px-2.5 py-1 rounded-md text-[11px] font-medium transition flex items-center gap-1.5 cursor-pointer ${
                  statusFilter === 'confirmed'
                    ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 shadow-sm'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                <span>✓ Đã duyệt</span>
                <span className={`px-1.5 py-0.2 rounded-full text-[10px] font-bold ${
                  statusFilter === 'confirmed' ? 'bg-emerald-500 text-slate-950' : 'bg-slate-800 text-slate-400'
                }`}>
                  {statusCounts.confirmed}
                </span>
              </button>

              <button
                type="button"
                onClick={() => setStatusFilter('rejected')}
                className={`px-2.5 py-1 rounded-md text-[11px] font-medium transition flex items-center gap-1.5 cursor-pointer ${
                  statusFilter === 'rejected'
                    ? 'bg-rose-500/20 text-rose-300 border border-rose-500/40 shadow-sm'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                <span>✗ Đã từ chối</span>
                <span className={`px-1.5 py-0.2 rounded-full text-[10px] font-bold ${
                  statusFilter === 'rejected' ? 'bg-rose-500 text-white' : 'bg-slate-800 text-slate-400'
                }`}>
                  {statusCounts.rejected}
                </span>
              </button>

              <button
                type="button"
                onClick={() => setStatusFilter('all')}
                className={`px-2.5 py-1 rounded-md text-[11px] font-medium transition flex items-center gap-1 cursor-pointer ${
                  statusFilter === 'all'
                    ? 'bg-sky-500/20 text-sky-300 border border-sky-500/40 shadow-sm'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                <span>Tất cả</span>
                <span className="text-[10px] text-slate-500">({statusCounts.all})</span>
              </button>
            </div>
          </div>

          {/* List of items */}
          <div className="space-y-3 max-h-[540px] overflow-y-auto pr-1">
            {loading ? (
              <TableSkeleton rows={4} columns={3} />
            ) : filteredItems.length === 0 ? (
              <div className="p-8 text-center text-slate-500 text-xs bg-slate-950/40 rounded-xl border border-dashed border-slate-800">
                <CheckSquare className="w-8 h-8 mx-auto mb-2 text-slate-600" />
                {searchQuery || filterMeetingId !== 'all' || filterPriority !== 'all' || filterConflictOnly || statusFilter !== 'pending' ? (
                  <div>Không tìm thấy mục nào khớp với bộ lọc hiện tại. Thử chuyển tab hoặc chọn lại bộ lọc.</div>
                ) : (
                  <div>Tuyệt vời! Không còn mục nào đang chờ duyệt trong phân loại này.</div>
                )}
              </div>
            ) : (
              filteredItems.map((item) => (
                <div
                  key={item.id}
                  className={`p-4 rounded-xl border transition duration-150 ${
                    item.is_conflict
                      ? 'bg-rose-950/20 border-rose-500/50 shadow-sm shadow-rose-950/20'
                      : (item.status || '').toUpperCase() === 'CONFIRMED'
                      ? 'bg-emerald-950/10 border-emerald-500/30'
                      : (item.status || '').toUpperCase() === 'REJECTED'
                      ? 'bg-slate-950/40 border-slate-800/60 opacity-70'
                      : 'bg-slate-950/70 border-slate-800/90 hover:border-slate-700'
                  }`}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="space-y-1.5 flex-1 min-w-0">
                      {/* Badges row */}
                      <div className="flex items-center gap-2 flex-wrap">
                        {/* Status Badge */}
                        {(() => {
                          const st = (item.status || 'PROPOSED').toUpperCase();
                          if (st === 'CONFIRMED') {
                            return (
                              <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 flex items-center gap-1">
                                <Check className="w-3 h-3 text-emerald-400" /> Đã duyệt
                              </span>
                            );
                          }
                          if (st === 'REJECTED') {
                            return (
                              <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-rose-500/20 text-rose-300 border border-rose-500/40 flex items-center gap-1">
                                <X className="w-3 h-3 text-rose-400" /> Đã từ chối
                              </span>
                            );
                          }
                          return (
                            <span className="px-2 py-0.5 rounded text-[10px] font-medium bg-amber-500/15 text-amber-300 border border-amber-500/30 flex items-center gap-1">
                              <Clock className="w-3 h-3 text-amber-400" /> Chờ duyệt
                            </span>
                          );
                        })()}

                        {item.is_conflict && (
                          <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-rose-500 text-white uppercase tracking-wider flex items-center gap-1">
                            <ShieldAlert className="w-3 h-3" /> Conflict Detected
                          </span>
                        )}

                        {/* Dynamic Source Platform Badges */}
                        {(() => {
                          const src = (item.source_type || item.evidence?.[0]?.source_type || (item.meeting_id ? 'meeting' : 'manual')).toLowerCase();
                          if (src.includes('line')) {
                            return (
                              <span 
                                onClick={() => setFilterSource('line')}
                                className="px-2 py-0.5 rounded text-[10px] font-semibold bg-emerald-500/15 text-emerald-300 border border-emerald-500/30 flex items-center gap-1 cursor-pointer hover:bg-emerald-500/25 transition"
                                title="Click to filter by LINE chat"
                              >
                                <MessageSquare className="w-3 h-3 text-emerald-400" />
                                LINE {item.author ? `• ${item.author}` : ''}
                              </span>
                            );
                          }
                          if (src.includes('slack')) {
                            return (
                              <span 
                                onClick={() => setFilterSource('slack')}
                                className="px-2 py-0.5 rounded text-[10px] font-semibold bg-purple-500/15 text-purple-300 border border-purple-500/30 flex items-center gap-1 cursor-pointer hover:bg-purple-500/25 transition"
                                title="Click to filter by Slack"
                              >
                                <Hash className="w-3 h-3 text-purple-400" />
                                Slack {item.author ? `• ${item.author}` : ''}
                              </span>
                            );
                          }
                          if (src.includes('meeting') || item.meeting_title) {
                            return (
                              <span 
                                onClick={() => setFilterSource('meeting')}
                                className="px-2 py-0.5 rounded text-[10px] font-semibold bg-sky-500/15 text-sky-300 border border-sky-500/30 flex items-center gap-1 cursor-pointer hover:bg-sky-500/25 transition"
                                title="Click to filter by Meetings"
                              >
                                <Calendar className="w-3 h-3 text-sky-400" />
                                {item.meeting_title || 'Meeting'} {item.meeting_date ? `(${item.meeting_date.split('T')[0]})` : ''}
                              </span>
                            );
                          }
                          return (
                            <span 
                              onClick={() => setFilterSource('manual')}
                              className="px-2 py-0.5 rounded text-[10px] font-semibold bg-amber-500/15 text-amber-300 border border-amber-500/30 flex items-center gap-1 cursor-pointer hover:bg-amber-500/25 transition"
                              title="Click to filter by Direct/Manual"
                            >
                              <User className="w-3 h-3 text-amber-400" />
                              Direct {item.author ? `• ${item.author}` : ''}
                            </span>
                          );
                        })()}

                        {/* Type & Priority Badges */}
                        <span className="px-1.5 py-0.5 rounded text-[10px] font-semibold bg-slate-800 text-slate-300 uppercase">
                          {item.type}
                        </span>

                        <span className={`px-1.5 py-0.5 rounded text-[10px] font-semibold uppercase ${
                          (item.priority || '').toUpperCase() === 'CRITICAL' ? 'bg-rose-500/20 text-rose-300 border border-rose-500/30' :
                          (item.priority || '').toUpperCase() === 'HIGH' ? 'bg-amber-500/20 text-amber-300 border border-amber-500/30' :
                          'bg-slate-800 text-slate-400'
                        }`}>
                          {item.priority || 'NORMAL'}
                        </span>

                        {item.confidence > 0 && (
                          <span className="text-[10px] text-slate-400">
                            Confidence: {(item.confidence * 100).toFixed(0)}%
                          </span>
                        )}

                        {item.deadline_date && (
                          <span className="text-[11px] text-amber-400 font-medium flex items-center gap-1">
                            <Clock className="w-3 h-3" /> Due: {item.deadline_date}
                          </span>
                        )}
                      </div>

                      {/* Title & Description */}
                      <h3 className="text-xs font-semibold text-white leading-snug">{item.title}</h3>
                      <p className="text-[11px] text-slate-300 leading-relaxed">{item.description}</p>

                      {/* Conflict Alert Note */}
                      {item.conflict_notes && (
                        <div className="mt-1 text-[11px] text-rose-300 bg-rose-900/30 p-2.5 rounded-lg border border-rose-800/60 leading-relaxed">
                          ⚠️ <strong>Conflict Warning:</strong> {item.conflict_notes}
                        </div>
                      )}

                      {/* Concrete Evidence Quote */}
                      {item.evidence && item.evidence.length > 0 && (
                        <div className="mt-2 text-[11px] bg-slate-900/90 p-2.5 rounded-lg border border-slate-800 text-slate-300 font-mono leading-relaxed">
                          <span className="text-slate-500 font-semibold uppercase text-[10px] mr-1.5">Quote:</span>
                          <span className="text-slate-200">"{item.evidence[0].quote}"</span>
                          {item.evidence[0].author && (
                            <span className="text-sky-400 ml-2 font-sans font-medium">— {item.evidence[0].author}</span>
                          )}
                          {item.evidence[0].source_type && (
                            <span className="text-slate-500 ml-1.5 uppercase text-[9px] font-sans">({item.evidence[0].source_type})</span>
                          )}
                        </div>
                      )}
                    </div>

                    {/* Action buttons (Human in the loop approval) */}
                    <div className="flex flex-col gap-1.5 flex-shrink-0 pt-0.5">
                      {(() => {
                        const st = (item.status || 'PROPOSED').toUpperCase();
                        if (st === 'CONFIRMED') {
                          return (
                            <button
                              type="button"
                              onClick={() => handleResetItem(item.id)}
                              className="px-2.5 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white text-[11px] font-medium transition flex items-center gap-1 border border-slate-700/80 cursor-pointer"
                              title="Hoàn tác về trạng thái Chờ duyệt"
                            >
                              <RotateCcw className="w-3.5 h-3.5 text-amber-400" /> Hoàn tác
                            </button>
                          );
                        }
                        if (st === 'REJECTED') {
                          return (
                            <div className="flex flex-col gap-1">
                              <button
                                type="button"
                                onClick={() => handleConfirmItem(item.id)}
                                className="px-2.5 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-[11px] font-semibold transition shadow-sm flex items-center gap-1 cursor-pointer"
                                title="Duyệt lại mục này"
                              >
                                <Check className="w-3.5 h-3.5" /> Duyệt lại
                              </button>
                              <button
                                type="button"
                                onClick={() => handleResetItem(item.id)}
                                className="px-2.5 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 text-[10px] font-medium transition flex items-center gap-1 border border-slate-700 cursor-pointer"
                                title="Hoàn tác về trạng thái Chờ duyệt"
                              >
                                <RotateCcw className="w-3 h-3 text-amber-400" /> Hoàn tác
                              </button>
                            </div>
                          );
                        }
                        // Default: PROPOSED / PENDING
                        return (
                          <>
                            <button
                              type="button"
                              onClick={() => handleConfirmItem(item.id)}
                              className="px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-[11px] font-semibold transition shadow-sm flex items-center gap-1 cursor-pointer"
                              title="Xác nhận mục này và đồng bộ vào Tri thức dự án"
                            >
                              <Check className="w-3.5 h-3.5" /> Confirm
                            </button>
                            <button
                              type="button"
                              onClick={() => handleRejectItem(item.id)}
                              className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-rose-950/60 hover:text-rose-300 text-slate-400 text-[11px] font-medium transition flex items-center gap-1 border border-slate-700/60 cursor-pointer"
                              title="Từ chối đề xuất này"
                            >
                              <X className="w-3.5 h-3.5" /> Reject
                            </button>
                          </>
                        );
                      })()}
                    </div>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
      {/* Stakeholder CRUD Manager Modal */}
      {activeProject && (
        <StakeholderManagerModal
          isOpen={isStakeholderModalOpen}
          onClose={() => {
            setIsStakeholderModalOpen(false);
            setEditingStakeholderForModal(null);
          }}
          projectId={activeProject.id}
          projectName={activeProject.name}
          initialEditingStakeholder={editingStakeholderForModal}
          onStakeholderSelected={(s) => {
            setChatAuthor(s.name);
            setIsCustomAuthor(false);
            if (s.platform === 'line' || s.platform === 'slack') {
              setChatSource(s.platform as any);
            }
          }}
          onStakeholdersChanged={() => {
            loadStakeholders();
          }}
        />
      )}
    </div>
  );
};
