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
  Users,
  UserPlus,
  Edit2,
  Trash2,
  RotateCcw,
  Hash,
  User,
  Layers,
  Send,
  FileText
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
import { ReportCenterModal } from '../components/modals/ReportCenterModal';
import { QuickQACopilotModal } from '../components/modals/QuickQACopilotModal';
import { PageHeader } from '../components/ui/PageHeader';
import { Card, CardContent } from '../components/ui/Card';
import { Badge } from '../components/ui/Badge';
import { Button } from '../components/ui/Button';
import { Select } from '../components/ui/Select';

interface BrSEDashboardProps {
  activeProject: Project | null;
  projects?: Project[];
  setActiveProject?: (project: Project) => void;
  onNavigateTab?: (tab: string) => void;
}

export const BrSEDashboardPage: React.FC<BrSEDashboardProps> = ({ 
  activeProject, 
  projects = [], 
  setActiveProject,
  onNavigateTab
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
  const [isReportCenterOpen, setIsReportCenterOpen] = useState<boolean>(false);
  const [isQuickQAOpen, setIsQuickQAOpen] = useState<boolean>(false);

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

  useEffect(() => {
    const timer = setInterval(() => {
      setLastSyncSeconds(prev => prev + 1);
    }, 1000);
    return () => clearInterval(timer);
  }, []);

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
      toast.success('Đã phân tích tin nhắn và lưu nháp vào Work Inbox!', 'Thành công');
      await loadData();
    } catch (e) {
      console.error("Chat analysis failed", e);
      toast.error('Lỗi khi phân tích tin nhắn.', 'Lỗi');
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
      toast.success(`${type === 'morning' ? 'Morning Briefing' : 'End-of-Day Wrap-up'} đã được tạo!`, 'Thành công');
    } catch (e) {
      console.error("Summary generation failed", e);
      toast.error('Tạo báo cáo tóm tắt thất bại.', 'Lỗi');
    } finally {
      setGeneratingSummary(false);
    }
  };

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedSummary(true);
    toast.success('Đã sao chép nội dung tóm tắt vào clipboard!', 'Đã chép');
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
      const st = (item.status || 'PROPOSED').toUpperCase();
      if (statusFilter === 'pending' && (st === 'CONFIRMED' || st === 'REJECTED')) return false;
      if (statusFilter === 'confirmed' && st !== 'CONFIRMED') return false;
      if (statusFilter === 'rejected' && st !== 'REJECTED') return false;

      if (filterSource !== 'all') {
        const itemSource = (item.source_type || item.evidence?.[0]?.source_type || (item.meeting_id ? 'meeting' : 'manual')).toLowerCase();
        if (filterSource === 'meeting' && !itemSource.includes('meeting')) return false;
        if (filterSource === 'line' && !itemSource.includes('line')) return false;
        if (filterSource === 'slack' && !itemSource.includes('slack')) return false;
        if (filterSource === 'manual' && (itemSource.includes('line') || itemSource.includes('slack') || itemSource.includes('meeting'))) return false;
      }

      if (filterConflictOnly && !item.is_conflict) return false;

      if (filterPriority !== 'all' && (item.priority || '').toUpperCase() !== filterPriority) {
        return false;
      }

      if (filterMeetingId !== 'all' && item.meeting_id !== filterMeetingId) {
        return false;
      }

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
    <div className="flex-1 overflow-y-auto bg-canvas px-4 py-6 sm:px-8 sm:py-8 lg:px-10">
      <div className="max-w-[1536px] mx-auto space-y-6">
        {/* Tier 1: Page Header */}
        <PageHeader
          title="BrSE Workspace"
          actions={
            <div className="flex items-center gap-2 bg-surface-elevated border border-border-subtle rounded-xl px-3 py-1.5 text-xs shadow-2xs">
              <button
                type="button"
                onClick={() => setAutoSync(!autoSync)}
                className="flex items-center gap-2 text-text-secondary hover:text-text-primary transition cursor-pointer"
                title={autoSync ? "Tự động đồng bộ đang BẬT. Nhấp để tạm dừng." : "Tự động đồng bộ đang TẮT. Nhấp để bật."}
              >
                <span className="relative flex h-2 w-2">
                  {autoSync && (
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                  )}
                  <span className={`relative inline-flex rounded-full h-2 w-2 ${autoSync ? 'bg-emerald-500' : 'bg-text-muted'}`}></span>
                </span>
                <span className="font-mono text-[11px] font-medium">
                  {autoSync ? (syncingNow ? 'Syncing...' : `Live (${lastSyncSeconds}s)`) : 'Paused'}
                </span>
              </button>
              <div className="h-3.5 w-px bg-border-subtle" />
              <button
                type="button"
                onClick={() => loadData(false)}
                className="text-text-muted hover:text-primary transition cursor-pointer p-0.5 rounded hover:bg-surface-hover"
                title="Tải lại toàn bộ dữ liệu"
              >
                <RefreshCw className={`w-3.5 h-3.5 ${loading || syncingNow ? 'animate-spin text-primary' : ''}`} />
              </button>
            </div>
          }
        />

        {/* Tier 2: Dedicated Operational Toolbar (Control Bar Card) */}
        <div className="bg-surface border border-border-subtle rounded-xl p-3 shadow-xs flex flex-wrap items-center justify-between gap-3">
          {/* Segment 1: AI Provider & Model Selector */}
          <div className="flex items-center gap-2">
            <span className="text-[11px] font-medium text-text-muted uppercase tracking-wider hidden md:inline">
              Mô hình AI:
            </span>
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

          <div className="flex items-center gap-3 flex-wrap">
            {/* Segment 2: Language Selector for Briefings */}
            <div className="flex items-center gap-1.5">
              <span className="text-[11px] font-medium text-text-muted uppercase tracking-wider hidden lg:inline">
                Ngôn ngữ:
              </span>
              <div className="flex items-center bg-surface-subtle border border-border-subtle rounded-lg p-0.5 text-xs">
                <button
                  type="button"
                  onClick={() => setSummaryLanguage('vi')}
                  className={`px-2.5 py-1 rounded-md font-medium transition cursor-pointer ${
                    summaryLanguage === 'vi'
                      ? 'bg-surface-elevated text-primary font-semibold shadow-2xs border border-border-subtle'
                      : 'text-text-muted hover:text-text-primary'
                  }`}
                >
                  Tiếng Việt
                </button>
                <button
                  type="button"
                  onClick={() => setSummaryLanguage('ja')}
                  className={`px-2.5 py-1 rounded-md font-medium transition cursor-pointer ${
                    summaryLanguage === 'ja'
                      ? 'bg-surface-elevated text-primary font-semibold shadow-2xs border border-border-subtle'
                      : 'text-text-muted hover:text-text-primary'
                  }`}
                >
                  日本語
                </button>
                <button
                  type="button"
                  onClick={() => setSummaryLanguage('bilingual')}
                  className={`px-2.5 py-1 rounded-md font-medium transition cursor-pointer ${
                    summaryLanguage === 'bilingual'
                      ? 'bg-surface-elevated text-primary font-semibold shadow-2xs border border-border-subtle'
                      : 'text-text-muted hover:text-text-primary'
                  }`}
                >
                  Song ngữ JP-VI
                </button>
              </div>
            </div>

            <div className="h-5 w-px bg-border-subtle hidden sm:block" />

            {/* Segment 3: Daily Briefing Action Triggers */}
            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => handleGenerateSummary('morning')}
                disabled={generatingSummary}
                leftIcon={<Sparkles className="w-3.5 h-3.5 text-amber-500" />}
                className="text-amber-600 dark:text-amber-400 border-amber-500/30 hover:bg-amber-500/10"
              >
                {generatingSummary && summaryType === 'morning' ? 'Đang tạo...' : 'Tóm tắt sáng'}
              </Button>

              <Button
                variant="outline"
                size="sm"
                onClick={() => handleGenerateSummary('evening')}
                disabled={generatingSummary}
                leftIcon={<Clock className="w-3.5 h-3.5 text-indigo-500" />}
                className="text-indigo-600 dark:text-indigo-400 border-indigo-500/30 hover:bg-indigo-500/10"
              >
                {generatingSummary && summaryType === 'evening' ? 'Đang tạo...' : 'Tổng kết ngày'}
              </Button>

              <div className="h-5 w-px bg-border-subtle hidden sm:block" />

              <Button
                size="sm"
                onClick={() => {
                  if (onNavigateTab) {
                    onNavigateTab('reports');
                  } else {
                    setIsReportCenterOpen(true);
                  }
                }}
                leftIcon={<FileText className="w-3.5 h-3.5 text-white" />}
                className="bg-blue-600 hover:bg-blue-700 text-white font-semibold shadow-sm"
              >
                Báo cáo Tiến độ (日報・週報)
              </Button>

              <Button
                variant="outline"
                size="sm"
                onClick={() => setIsQuickQAOpen(true)}
                leftIcon={<Sparkles className="w-3.5 h-3.5 text-purple-500" />}
                className="text-purple-600 dark:text-purple-400 border-purple-500/30 hover:bg-purple-500/10 font-semibold"
              >
                Quick QA Studio
              </Button>
            </div>
          </div>
        </div>

      {/* Metrics Row (Interactive overview) */}
      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-3.5">
        <Card 
          onClick={() => { setActiveTab('requirements'); setFilterPriority('CRITICAL'); }}
          className="cursor-pointer hover:border-rose-500/50 hover:shadow-xs transition p-4 flex items-center gap-3 border-rose-500/30"
        >
          <div className="w-10 h-10 rounded-xl bg-rose-500/10 flex items-center justify-center text-rose-500 dark:text-rose-400 shrink-0">
            <Flame className="w-5 h-5" />
          </div>
          <div>
            <div className="text-2xl font-bold text-text-primary tracking-tight">{metrics?.urgent_count ?? 0}</div>
            <div className="text-[11px] text-text-secondary font-medium">Khẩn cấp</div>
          </div>
        </Card>

        <Card 
          onClick={() => { setActiveTab('questions'); setFilterPriority('all'); }}
          className="cursor-pointer hover:border-amber-500/50 hover:shadow-xs transition p-4 flex items-center gap-3 border-amber-500/30"
        >
          <div className="w-10 h-10 rounded-xl bg-amber-500/10 flex items-center justify-center text-amber-500 dark:text-amber-400 shrink-0">
            <HelpCircle className="w-5 h-5" />
          </div>
          <div>
            <div className="text-2xl font-bold text-text-primary tracking-tight">{metrics?.open_questions_count ?? 0}</div>
            <div className="text-[11px] text-text-secondary font-medium">Câu hỏi tồn</div>
          </div>
        </Card>

        <Card 
          onClick={() => { setActiveTab('deadlines'); setFilterPriority('all'); }}
          className="cursor-pointer hover:border-yellow-500/50 hover:shadow-xs transition p-4 flex items-center gap-3 border-yellow-500/30"
        >
          <div className="w-10 h-10 rounded-xl bg-yellow-500/10 flex items-center justify-center text-yellow-500 dark:text-yellow-400 shrink-0">
            <Clock className="w-5 h-5" />
          </div>
          <div>
            <div className="text-2xl font-bold text-text-primary tracking-tight">{metrics?.deadlines_count ?? 0}</div>
            <div className="text-[11px] text-text-secondary font-medium">Hạn chót</div>
          </div>
        </Card>

        <Card 
          onClick={() => { setFilterConflictOnly(!filterConflictOnly); }}
          className={`cursor-pointer transition p-4 flex items-center gap-3 ${
            filterConflictOnly 
              ? 'border-orange-500 bg-orange-500/10 ring-1 ring-orange-500' 
              : 'border-orange-500/30 hover:border-orange-500/50'
          }`}
          title="Bật/tắt lọc chỉ các mục bị xung đột specs"
        >
          <div className="w-10 h-10 rounded-xl bg-orange-500/10 flex items-center justify-center text-orange-500 dark:text-orange-400 shrink-0">
            <ShieldAlert className="w-5 h-5" />
          </div>
          <div>
            <div className="text-2xl font-bold text-text-primary tracking-tight">{metrics?.conflicts_count ?? 0}</div>
            <div className="text-[11px] text-text-secondary font-medium">
              Xung đột {filterConflictOnly ? '(Đang lọc)' : ''}
            </div>
          </div>
        </Card>

        <Card 
          onClick={() => { setActiveTab('decisions'); setFilterPriority('all'); }}
          className="cursor-pointer hover:border-emerald-500/50 hover:shadow-xs transition p-4 flex items-center gap-3 border-emerald-500/30"
        >
          <div className="w-10 h-10 rounded-xl bg-emerald-500/10 flex items-center justify-center text-emerald-500 dark:text-emerald-400 shrink-0">
            <CheckCircle2 className="w-5 h-5" />
          </div>
          <div>
            <div className="text-2xl font-bold text-text-primary tracking-tight">{metrics?.recent_decisions_count ?? metrics?.completed_count ?? 0}</div>
            <div className="text-[11px] text-text-secondary font-medium">Quyết định</div>
          </div>
        </Card>
      </div>

      {/* Daily Summary Preview Box */}
      {(summaryMarkdown || generatingSummary) && (
        <Card className="border-primary-500/40 p-5 space-y-3 shadow-md relative animate-in fade-in duration-200">
          <div className="flex items-center justify-between border-b border-border-subtle pb-3">
            <div className="flex items-center gap-2 text-primary-600 dark:text-primary-400 text-xs font-semibold">
              <Sparkles className="w-4 h-4 animate-pulse" />
              <span>
                {summaryLanguage === 'ja'
                  ? (summaryType === 'morning' ? '朝会サマリー・本日の進捗計画' : '日次進捗報告・夕会ラップアップ')
                  : (summaryType === 'morning' ? 'Executive Morning Briefing' : 'End-of-Day Wrap-up Report')}
                {' — '}
                <span className="text-text-secondary font-normal">
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
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => copyToClipboard(summaryMarkdown)}
                  leftIcon={copiedSummary ? <Check className="w-3.5 h-3.5 text-emerald-500" /> : <Copy className="w-3.5 h-3.5" />}
                >
                  {copiedSummary ? 'Đã sao chép' : 'Copy Markdown'}
                </Button>
              )}
              <button
                onClick={() => setSummaryMarkdown('')}
                className="p-1.5 rounded-lg text-text-muted hover:text-text-primary hover:bg-surface-elevated transition cursor-pointer"
                title="Đóng bản tóm tắt"
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
            <div className="bg-surface-subtle p-5 rounded-xl border border-border-subtle shadow-inner max-h-[500px] overflow-y-auto">
              <MarkdownView content={summaryMarkdown} accent="sky" />
            </div>
          )}
        </Card>
      )}

      {/* Main Two Column Area: Chat Analyzer & Work Item Review Inbox */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left Column: Smart Conversation / Message Analyzer */}
        <div className="lg:col-span-5 flex flex-col">
          <Card className="p-5 flex flex-col space-y-4 h-full">
            <div className="flex items-center justify-between border-b border-border-subtle pb-3">
              <div className="flex items-center gap-2">
                <MessageSquare className="w-4 h-4 text-primary" />
                <h2 className="text-sm font-semibold text-text-primary">Phân tích tin nhắn</h2>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-2.5 text-xs">
              <div>
                <label className="text-text-muted text-[11px] block mb-1 font-medium">Nền tảng</label>
                <Select
                  value={chatSource}
                  onChange={(val) => setChatSource(val as any)}
                  size="sm"
                  className="w-full"
                  options={[
                    { value: 'slack', label: 'Slack Thread', icon: <Hash className="w-3 h-3 text-[#E01E5A]" /> },
                    { value: 'line', label: 'LINE Message', icon: <MessageSquare className="w-3 h-3 text-[#06C755]" /> },
                    { value: 'manual', label: 'Nhập trực tiếp', icon: <Send className="w-3 h-3 text-text-muted" /> },
                  ]}
                />
              </div>
              <div>
                <div className="flex items-center justify-between mb-1">
                  <label className="text-text-muted text-[11px] font-medium">Người gửi</label>
                  <button
                    type="button"
                    onClick={() => {
                      setEditingStakeholderForModal(null);
                      setIsStakeholderModalOpen(true);
                    }}
                    className="text-[10.5px] text-primary-500 hover:text-primary-600 dark:hover:text-primary-400 flex items-center gap-1 cursor-pointer transition font-medium"
                    title="Quản lý người liên hệ"
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
                      className="flex-1 bg-canvas border border-border-subtle rounded-lg px-2.5 py-1.5 text-text-primary text-xs focus:ring-1 focus:ring-primary-500 focus:outline-none"
                      autoFocus
                    />
                    <button
                      type="button"
                      onClick={() => {
                        setIsCustomAuthor(false);
                        if (stakeholders.length > 0) setChatAuthor(stakeholders[0].name);
                      }}
                      className="px-2 py-1.5 text-[10px] rounded-lg bg-surface-elevated hover:bg-border-subtle text-text-secondary transition shrink-0 cursor-pointer"
                    >
                      Chọn lại
                    </button>
                  </div>
                ) : (
                  <div className="flex items-center gap-1.5">
                    <Select
                      value={chatAuthor}
                      onChange={(val) => {
                        if (val === '__custom__') {
                          setIsCustomAuthor(true);
                          setChatAuthor('');
                        } else {
                          setChatAuthor(val);
                          const found = stakeholders.find(s => s.name === val);
                          if (found && (found.platform === 'line' || found.platform === 'slack')) {
                            setChatSource(found.platform as any);
                          }
                        }
                      }}
                      size="sm"
                      className="flex-1 min-w-0"
                      options={[
                        ...(stakeholders.length === 0 ? [{ value: '', label: 'Chưa có người nhắn nào' }] : []),
                        ...stakeholders.map((s) => ({
                          value: s.name,
                          label: s.name,
                          sublabel: `${s.role} · ${s.organization}`
                        })),
                        { value: '__custom__', label: '➕ Nhập tên tùy chỉnh...' }
                      ]}
                    />

                    <div className="flex items-center gap-1 shrink-0">
                      <button
                        type="button"
                        onClick={() => {
                          setEditingStakeholderForModal(null);
                          setIsStakeholderModalOpen(true);
                        }}
                        className="p-1.5 rounded-lg text-text-muted hover:text-emerald-500 hover:bg-surface-elevated border border-border-subtle transition cursor-pointer"
                        title="Thêm người nhắn mới"
                      >
                        <UserPlus className="w-3.5 h-3.5" />
                      </button>
                      <button
                        type="button"
                        onClick={handleQuickEditCurrentStakeholder}
                        disabled={!currentStakeholder}
                        className="p-1.5 rounded-lg text-text-muted hover:text-amber-500 hover:bg-surface-elevated disabled:opacity-30 disabled:cursor-not-allowed border border-border-subtle transition cursor-pointer"
                        title={currentStakeholder ? `Sửa thông tin: ${currentStakeholder.name}` : 'Chọn một người để sửa'}
                      >
                        <Edit2 className="w-3.5 h-3.5" />
                      </button>
                      <button
                        type="button"
                        onClick={handleQuickDeleteCurrentStakeholder}
                        disabled={!currentStakeholder}
                        className="p-1.5 rounded-lg text-text-muted hover:text-rose-500 hover:bg-surface-elevated disabled:opacity-30 disabled:cursor-not-allowed border border-border-subtle transition cursor-pointer"
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
              className="w-full bg-canvas border border-border-subtle rounded-xl p-3 text-xs text-text-primary placeholder:text-text-muted focus:outline-none focus:border-primary-500 transition resize-none font-mono leading-relaxed"
            />

            <Button
              variant="primary"
              onClick={handleAnalyzeChat}
              disabled={analyzing || !inputChat.trim()}
              isLoading={analyzing}
              leftIcon={<Sparkles className="w-3.5 h-3.5" />}
              className="w-full"
            >
              Analyze & Draft to Work Inbox
            </Button>

            {analyzing && (
              <AiThinkingLoader mode="analyze" className="mt-2" />
            )}

            {/* Quick analysis output preview */}
            {latestAnalysis && (
              <div className="border-t border-border-subtle pt-3 space-y-2 text-xs">
                <div className="text-[11px] font-semibold text-text-secondary uppercase tracking-wider flex items-center gap-1.5">
                  <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500" />
                  Latest Analysis Highlights
                </div>
                <div className="bg-canvas p-3 rounded-lg border border-border-subtle space-y-1.5 text-text-secondary">
                  <div className="text-primary-500 font-medium">Context: {latestAnalysis.summary?.context || 'Analyzed message'}</div>
                  {latestAnalysis.requirements?.length > 0 && (
                    <div className="text-amber-500 dark:text-amber-400 font-medium">⚡ {latestAnalysis.requirements.length} requirement(s) drafted</div>
                  )}
                  {latestAnalysis.todos?.length > 0 && (
                    <div className="text-emerald-500 dark:text-emerald-400 font-medium">✅ {latestAnalysis.todos.length} action item(s) drafted</div>
                  )}
                </div>
              </div>
            )}
          </Card>
        </div>

        {/* Right Column: Work Inbox (Human-in-the-loop Approval) */}
        <div className="lg:col-span-7 flex flex-col">
          <Card className="p-5 flex flex-col space-y-4 h-full">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-border-subtle pb-3">
              <div>
                <h2 className="text-sm font-semibold text-text-primary">Work Inbox — Operational Review</h2>
                <p className="text-[11px] text-text-muted">
                  AI trích xuất & đối chiếu tự động. BrSE duyệt (Confirm) để lưu vào Project Brain hoặc Từ chối (Reject).
                </p>
              </div>
              <Badge variant="primary" size="sm">
                {inbox?.total_pending ?? 0} Pending
              </Badge>
            </div>

            {/* Search and Filters Bar */}
            <div className="grid grid-cols-1 sm:grid-cols-12 gap-2 text-xs">
              {/* Search Input */}
              <div className="sm:col-span-6 relative">
                <Search className="w-3.5 h-3.5 text-text-muted absolute left-3 top-1/2 -translate-y-1/2" />
                <input
                  type="text"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="Tìm theo tiêu đề, trích dẫn, specs..."
                  className="w-full bg-canvas border border-border-subtle rounded-lg pl-8 pr-8 py-1.5 text-xs text-text-primary placeholder:text-text-muted focus:ring-1 focus:ring-primary-500 focus:outline-none"
                />
                {searchQuery && (
                  <button
                    onClick={() => setSearchQuery('')}
                    className="absolute right-2.5 top-1/2 -translate-y-1/2 text-text-muted hover:text-text-primary cursor-pointer"
                  >
                    <X className="w-3.5 h-3.5" />
                  </button>
                )}
              </div>

              {/* Meeting Filter Dropdown */}
              <div className="sm:col-span-3">
                <Select
                  value={filterMeetingId}
                  onChange={(val) => setFilterMeetingId(val)}
                  size="sm"
                  className="w-full"
                  options={[
                    { value: 'all', label: 'Tất cả Meetings' },
                    ...(inbox?.meetings || []).map((m) => ({
                      value: m.id,
                      label: m.date ? `${m.date.split('T')[0]}: ${m.title}` : m.title
                    }))
                  ]}
                />
              </div>

              {/* Priority Filter */}
              <div className="sm:col-span-3">
                <Select
                  value={filterPriority}
                  onChange={(val) => setFilterPriority(val)}
                  size="sm"
                  className="w-full"
                  options={[
                    { value: 'all', label: 'Mọi Priority' },
                    { value: 'CRITICAL', label: 'Critical', icon: <span className="w-2 h-2 rounded-full bg-red-500 inline-block shrink-0" /> },
                    { value: 'HIGH', label: 'High', icon: <span className="w-2 h-2 rounded-full bg-orange-500 inline-block shrink-0" /> },
                    { value: 'MEDIUM', label: 'Medium', icon: <span className="w-2 h-2 rounded-full bg-amber-500 inline-block shrink-0" /> },
                    { value: 'LOW', label: 'Low', icon: <span className="w-2 h-2 rounded-full bg-slate-400 inline-block shrink-0" /> },
                  ]}
                />
              </div>
            </div>

            {/* Source Platform Filter Pills */}
            <div className="flex items-center gap-1.5 overflow-x-auto pb-1 text-xs">
              <span className="text-[11px] text-text-muted font-medium mr-1 flex items-center gap-1 shrink-0">
                <Filter className="w-3 h-3" /> Nguồn:
              </span>
              <button
                type="button"
                onClick={() => setFilterSource('all')}
                className={`px-2.5 py-1 rounded-lg font-medium transition flex items-center gap-1.5 shrink-0 text-xs cursor-pointer ${
                  filterSource === 'all'
                    ? 'bg-surface-elevated text-text-primary border border-border-subtle font-semibold shadow-xs'
                    : 'text-text-muted hover:text-text-primary bg-canvas border border-border-subtle'
                }`}
              >
                All Sources ({sourceCounts.all})
              </button>
              <button
                type="button"
                onClick={() => setFilterSource('line')}
                className={`px-2.5 py-1 rounded-lg font-medium transition flex items-center gap-1.5 shrink-0 text-xs cursor-pointer ${
                  filterSource === 'line'
                    ? 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 border border-emerald-500/30 font-semibold'
                    : 'text-text-muted hover:text-emerald-500 bg-canvas border border-border-subtle'
                }`}
              >
                <MessageSquare className="w-3 h-3 text-emerald-500" />
                LINE Chat ({sourceCounts.line})
              </button>
              <button
                type="button"
                onClick={() => setFilterSource('slack')}
                className={`px-2.5 py-1 rounded-lg font-medium transition flex items-center gap-1.5 shrink-0 text-xs cursor-pointer ${
                  filterSource === 'slack'
                    ? 'bg-purple-500/15 text-purple-600 dark:text-purple-400 border border-purple-500/30 font-semibold'
                    : 'text-text-muted hover:text-purple-500 bg-canvas border border-border-subtle'
                }`}
              >
                <Hash className="w-3 h-3 text-purple-500" />
                Slack ({sourceCounts.slack})
              </button>
              <button
                type="button"
                onClick={() => setFilterSource('meeting')}
                className={`px-2.5 py-1 rounded-lg font-medium transition flex items-center gap-1.5 shrink-0 text-xs cursor-pointer ${
                  filterSource === 'meeting'
                    ? 'bg-primary-500/15 text-primary-600 dark:text-primary-400 border border-primary-500/30 font-semibold'
                    : 'text-text-muted hover:text-primary-500 bg-canvas border border-border-subtle'
                }`}
              >
                <Calendar className="w-3 h-3 text-primary-500" />
                Meetings ({sourceCounts.meeting})
              </button>
              <button
                type="button"
                onClick={() => setFilterSource('manual')}
                className={`px-2.5 py-1 rounded-lg font-medium transition flex items-center gap-1.5 shrink-0 text-xs cursor-pointer ${
                  filterSource === 'manual'
                    ? 'bg-amber-500/15 text-amber-600 dark:text-amber-400 border border-amber-500/30 font-semibold'
                    : 'text-text-muted hover:text-amber-500 bg-canvas border border-border-subtle'
                }`}
              >
                <User className="w-3 h-3 text-amber-500" />
                Direct / Web ({sourceCounts.manual})
              </button>
            </div>

            {/* Inbox Category Tabs */}
            <div className="flex items-center gap-1.5 overflow-x-auto pb-1 border-b border-border-subtle text-xs">
              <button
                onClick={() => setActiveTab('requirements')}
                className={`px-3 py-1.5 rounded-lg font-medium transition flex items-center gap-1.5 shrink-0 cursor-pointer ${
                  activeTab === 'requirements' 
                    ? 'bg-primary-500/15 text-primary-600 dark:text-primary-400 border border-primary-500/30 font-semibold' 
                    : 'text-text-muted hover:text-text-primary'
                }`}
              >
                Requirements ({inbox?.requirements?.length ?? 0})
              </button>
              <button
                onClick={() => setActiveTab('bugs')}
                className={`px-3 py-1.5 rounded-lg font-medium transition flex items-center gap-1.5 shrink-0 cursor-pointer ${
                  activeTab === 'bugs' 
                    ? 'bg-rose-500/15 text-rose-600 dark:text-rose-400 border border-rose-500/30 font-semibold' 
                    : 'text-text-muted hover:text-text-primary'
                }`}
              >
                Bugs ({inbox?.bugs?.length ?? 0})
              </button>
              <button
                onClick={() => setActiveTab('decisions')}
                className={`px-3 py-1.5 rounded-lg font-medium transition flex items-center gap-1.5 shrink-0 cursor-pointer ${
                  activeTab === 'decisions' 
                    ? 'bg-indigo-500/15 text-indigo-600 dark:text-indigo-400 border border-indigo-500/30 font-semibold' 
                    : 'text-text-muted hover:text-text-primary'
                }`}
              >
                Decisions ({inbox?.decisions?.length ?? 0})
              </button>
              <button
                onClick={() => setActiveTab('questions')}
                className={`px-3 py-1.5 rounded-lg font-medium transition flex items-center gap-1.5 shrink-0 cursor-pointer ${
                  activeTab === 'questions' 
                    ? 'bg-amber-500/15 text-amber-600 dark:text-amber-400 border border-amber-500/30 font-semibold' 
                    : 'text-text-muted hover:text-text-primary'
                }`}
              >
                Questions ({inbox?.questions?.length ?? 0})
              </button>
              <button
                onClick={() => setActiveTab('deadlines')}
                className={`px-3 py-1.5 rounded-lg font-medium transition flex items-center gap-1.5 shrink-0 cursor-pointer ${
                  activeTab === 'deadlines' 
                    ? 'bg-yellow-500/15 text-yellow-600 dark:text-yellow-400 border border-yellow-500/30 font-semibold' 
                    : 'text-text-muted hover:text-text-primary'
                }`}
              >
                Deadlines ({inbox?.deadlines?.length ?? 0})
              </button>
            </div>

            {/* Status Sub-filter Bar */}
            <div className="flex items-center justify-between bg-canvas p-1.5 rounded-lg border border-border-subtle text-xs">
              <div className="flex items-center gap-1 flex-wrap">
                <button
                  type="button"
                  onClick={() => setStatusFilter('pending')}
                  className={`px-2.5 py-1 rounded-md text-[11px] font-medium transition flex items-center gap-1.5 cursor-pointer ${
                    statusFilter === 'pending'
                      ? 'bg-amber-500/15 text-amber-600 dark:text-amber-400 border border-amber-500/30 shadow-xs'
                      : 'text-text-muted hover:text-text-primary'
                  }`}
                >
                  <span>⏳ Chờ duyệt</span>
                  <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${
                    statusFilter === 'pending' ? 'bg-amber-500 text-white' : 'bg-surface-elevated text-text-muted'
                  }`}>
                    {statusCounts.pending}
                  </span>
                </button>

                <button
                  type="button"
                  onClick={() => setStatusFilter('confirmed')}
                  className={`px-2.5 py-1 rounded-md text-[11px] font-medium transition flex items-center gap-1.5 cursor-pointer ${
                    statusFilter === 'confirmed'
                      ? 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 border border-emerald-500/30 shadow-xs'
                      : 'text-text-muted hover:text-text-primary'
                  }`}
                >
                  <span>✓ Đã duyệt</span>
                  <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${
                    statusFilter === 'confirmed' ? 'bg-emerald-500 text-white' : 'bg-surface-elevated text-text-muted'
                  }`}>
                    {statusCounts.confirmed}
                  </span>
                </button>

                <button
                  type="button"
                  onClick={() => setStatusFilter('rejected')}
                  className={`px-2.5 py-1 rounded-md text-[11px] font-medium transition flex items-center gap-1.5 cursor-pointer ${
                    statusFilter === 'rejected'
                      ? 'bg-rose-500/15 text-rose-600 dark:text-rose-400 border border-rose-500/30 shadow-xs'
                      : 'text-text-muted hover:text-text-primary'
                  }`}
                >
                  <span>✗ Đã từ chối</span>
                  <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${
                    statusFilter === 'rejected' ? 'bg-rose-500 text-white' : 'bg-surface-elevated text-text-muted'
                  }`}>
                    {statusCounts.rejected}
                  </span>
                </button>

                <button
                  type="button"
                  onClick={() => setStatusFilter('all')}
                  className={`px-2.5 py-1 rounded-md text-[11px] font-medium transition flex items-center gap-1 cursor-pointer ${
                    statusFilter === 'all'
                      ? 'bg-primary-500/15 text-primary-600 dark:text-primary-400 border border-primary-500/30 shadow-xs'
                      : 'text-text-muted hover:text-text-primary'
                  }`}
                >
                  <span>Tất cả</span>
                  <span className="text-[10px] text-text-muted">({statusCounts.all})</span>
                </button>
              </div>
            </div>

            {/* List of items */}
            <div className="space-y-3 max-h-[540px] overflow-y-auto pr-1">
              {loading ? (
                <TableSkeleton rows={4} columns={3} />
              ) : filteredItems.length === 0 ? (
                <div className="p-8 text-center text-text-muted text-xs bg-canvas rounded-xl border border-dashed border-border-subtle">
                  <CheckSquare className="w-8 h-8 mx-auto mb-2 text-text-muted opacity-60" />
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
                        ? 'bg-rose-500/5 border-rose-500/40 shadow-xs'
                        : (item.status || '').toUpperCase() === 'CONFIRMED'
                        ? 'bg-emerald-500/5 border-emerald-500/30'
                        : (item.status || '').toUpperCase() === 'REJECTED'
                        ? 'bg-canvas border-border-subtle opacity-60'
                        : 'bg-canvas border-border-subtle hover:border-primary-500/40'
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
                                <Badge variant="success" size="sm">
                                  <Check className="w-3 h-3 mr-0.5" /> Đã duyệt
                                </Badge>
                              );
                            }
                            if (st === 'REJECTED') {
                              return (
                                <Badge variant="danger" size="sm">
                                  <X className="w-3 h-3 mr-0.5" /> Đã từ chối
                                </Badge>
                              );
                            }
                            return (
                              <Badge variant="warning" size="sm">
                                <Clock className="w-3 h-3 mr-0.5" /> Chờ duyệt
                              </Badge>
                            );
                          })()}

                          {item.is_conflict && (
                            <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-rose-500 text-white uppercase tracking-wider flex items-center gap-1 shadow-xs">
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
                                  className="px-2 py-0.5 rounded text-[10px] font-semibold bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 border border-emerald-500/30 flex items-center gap-1 cursor-pointer hover:bg-emerald-500/25 transition"
                                  title="Lọc theo LINE chat"
                                >
                                  <MessageSquare className="w-3 h-3 text-emerald-500" />
                                  LINE {item.author ? `• ${item.author}` : ''}
                                </span>
                              );
                            }
                            if (src.includes('slack')) {
                              return (
                                <span 
                                  onClick={() => setFilterSource('slack')}
                                  className="px-2 py-0.5 rounded text-[10px] font-semibold bg-purple-500/15 text-purple-600 dark:text-purple-400 border border-purple-500/30 flex items-center gap-1 cursor-pointer hover:bg-purple-500/25 transition"
                                  title="Lọc theo Slack"
                                >
                                  <Hash className="w-3 h-3 text-purple-500" />
                                  Slack {item.author ? `• ${item.author}` : ''}
                                </span>
                              );
                            }
                            if (src.includes('meeting') || item.meeting_title) {
                              return (
                                <span 
                                  onClick={() => setFilterSource('meeting')}
                                  className="px-2 py-0.5 rounded text-[10px] font-semibold bg-primary-500/15 text-primary-600 dark:text-primary-400 border border-primary-500/30 flex items-center gap-1 cursor-pointer hover:bg-primary-500/25 transition"
                                  title="Lọc theo Meetings"
                                >
                                  <Calendar className="w-3 h-3 text-primary-500" />
                                  {item.meeting_title || 'Meeting'} {item.meeting_date ? `(${item.meeting_date.split('T')[0]})` : ''}
                                </span>
                              );
                            }
                            return (
                              <span 
                                onClick={() => setFilterSource('manual')}
                                className="px-2 py-0.5 rounded text-[10px] font-semibold bg-amber-500/15 text-amber-600 dark:text-amber-400 border border-amber-500/30 flex items-center gap-1 cursor-pointer hover:bg-amber-500/25 transition"
                                title="Lọc theo Direct/Manual"
                              >
                                <User className="w-3 h-3 text-amber-500" />
                                Direct {item.author ? `• ${item.author}` : ''}
                              </span>
                            );
                          })()}

                          {/* Type & Priority Badges */}
                          <span className="px-1.5 py-0.5 rounded text-[10px] font-semibold bg-surface-elevated text-text-secondary uppercase">
                            {item.type}
                          </span>

                          <span className={`px-1.5 py-0.5 rounded text-[10px] font-semibold uppercase ${
                            (item.priority || '').toUpperCase() === 'CRITICAL' ? 'bg-rose-500/15 text-rose-600 dark:text-rose-400 border border-rose-500/30' :
                            (item.priority || '').toUpperCase() === 'HIGH' ? 'bg-amber-500/15 text-amber-600 dark:text-amber-400 border border-amber-500/30' :
                            'bg-surface-elevated text-text-muted'
                          }`}>
                            {item.priority || 'NORMAL'}
                          </span>

                          {item.confidence > 0 && (
                            <span className="text-[10px] text-text-muted font-mono">
                              {(item.confidence * 100).toFixed(0)}% conf
                            </span>
                          )}

                          {item.deadline_date && (
                            <span className="text-[11px] text-amber-600 dark:text-amber-400 font-medium flex items-center gap-1">
                              <Clock className="w-3 h-3" /> Due: {item.deadline_date}
                            </span>
                          )}
                        </div>

                        {/* Title & Description */}
                        <h3 className="text-xs font-semibold text-text-primary leading-snug">{item.title}</h3>
                        <p className="text-[11px] text-text-secondary leading-relaxed">{item.description}</p>

                        {/* Conflict Alert Note */}
                        {item.conflict_notes && (
                          <div className="mt-1 text-[11px] text-rose-600 dark:text-rose-300 bg-rose-500/10 p-2.5 rounded-lg border border-rose-500/30 leading-relaxed">
                            ⚠️ <strong>Conflict Warning:</strong> {item.conflict_notes}
                          </div>
                        )}

                        {/* Concrete Evidence Quote */}
                        {item.evidence && item.evidence.length > 0 && (
                          <div className="mt-2 text-[11px] bg-surface-elevated p-2.5 rounded-lg border border-border-subtle text-text-secondary font-mono leading-relaxed">
                            <span className="text-text-muted font-semibold uppercase text-[10px] mr-1.5">Quote:</span>
                            <span className="text-text-primary italic">"{item.evidence[0].quote}"</span>
                            {item.evidence[0].author && (
                              <span className="text-primary-600 dark:text-primary-400 ml-2 font-sans font-medium">— {item.evidence[0].author}</span>
                            )}
                            {item.evidence[0].source_type && (
                              <span className="text-text-muted ml-1.5 uppercase text-[9px] font-sans">({item.evidence[0].source_type})</span>
                            )}
                          </div>
                        )}
                      </div>

                      {/* Action buttons (Human in the loop approval) */}
                      <div className="flex flex-col gap-1.5 shrink-0 pt-0.5">
                        {(() => {
                          const st = (item.status || 'PROPOSED').toUpperCase();
                          if (st === 'CONFIRMED') {
                            return (
                              <Button
                                variant="ghost"
                                size="sm"
                                onClick={() => handleResetItem(item.id)}
                                leftIcon={<RotateCcw className="w-3.5 h-3.5 text-amber-500" />}
                                className="text-[11px]"
                              >
                                Hoàn tác
                              </Button>
                            );
                          }
                          if (st === 'REJECTED') {
                            return (
                              <div className="flex flex-col gap-1">
                                <Button
                                  variant="primary"
                                  size="sm"
                                  onClick={() => handleConfirmItem(item.id)}
                                  leftIcon={<Check className="w-3.5 h-3.5" />}
                                  className="text-[11px]"
                                >
                                  Duyệt lại
                                </Button>
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  onClick={() => handleResetItem(item.id)}
                                  leftIcon={<RotateCcw className="w-3 h-3 text-amber-500" />}
                                  className="text-[10px]"
                                >
                                  Hoàn tác
                                </Button>
                              </div>
                            );
                          }
                          return (
                            <>
                              <Button
                                variant="primary"
                                size="sm"
                                onClick={() => handleConfirmItem(item.id)}
                                leftIcon={<Check className="w-3.5 h-3.5" />}
                                className="text-[11px] bg-emerald-600 hover:bg-emerald-500 text-white"
                              >
                                Confirm
                              </Button>
                              <Button
                                variant="ghost"
                                size="sm"
                                onClick={() => handleRejectItem(item.id)}
                                leftIcon={<X className="w-3.5 h-3.5 text-rose-500" />}
                                className="text-[11px] hover:text-rose-500"
                              >
                                Reject
                              </Button>
                            </>
                          );
                        })()}
                      </div>
                    </div>
                  </div>
                ))
              )}
            </div>
          </Card>
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

      {/* Automated Reporting Suite Modal */}
      <ReportCenterModal
        isOpen={isReportCenterOpen}
        onClose={() => setIsReportCenterOpen(false)}
        activeProject={activeProject}
        projects={projects}
        defaultSenderName="Nguyen Phuc (BrSE)"
        defaultRecipientName="お客様 (Client PM / Tech Lead)"
      />

      {/* Quick QA Copilot Studio Modal */}
      <QuickQACopilotModal
        isOpen={isQuickQAOpen}
        onClose={() => setIsQuickQAOpen(false)}
        activeProject={activeProject}
        projects={projects}
      />
    </div>
  );
};
