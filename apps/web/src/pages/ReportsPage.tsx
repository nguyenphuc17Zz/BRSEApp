import React, { useState, useEffect, useRef, useMemo } from 'react';
import {
  FileSpreadsheet,
  FileText,
  Sparkles,
  Calendar,
  Clock,
  CheckCircle2,
  AlertTriangle,
  Copy,
  Check,
  Download,
  Upload,
  RefreshCw,
  Trash2,
  Eye,
  Sliders,
  Send,
  MessageSquare,
  Presentation,
  Mail,
  ToggleLeft,
  ToggleRight,
  ExternalLink,
  ChevronDown,
  ChevronRight,
  HelpCircle,
  X,
  FileCode,
  Layers,
  ArrowRight,
  CheckSquare,
  Plus,
  Bold,
  Italic,
  List,
  ListOrdered,
  Quote,
  Code,
  Edit3,
  RotateCcw
} from 'lucide-react';
import { Project, ProviderInfo } from '../types';
import { apiClient } from '../api/client';
import { useToast } from '../context/ToastContext';
import { useConfirm } from '../context/ConfirmDialogContext';
import { ProviderModelSelector } from '../components/ProviderModelSelector';
import { MarkdownView } from '../components/MarkdownView';
import { PageHeader } from '../components/ui/PageHeader';
import { Card, CardContent } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { Badge } from '../components/ui/Badge';
import { Select } from '../components/ui/Select';

interface ReportsPageProps {
  activeProject: Project | null;
  projects?: Project[];
  setActiveProject?: (p: Project | null) => void;
}

export const ReportsPage: React.FC<ReportsPageProps> = ({
  activeProject,
  projects = [],
  setActiveProject
}) => {
  const toast = useToast();
  const confirm = useConfirm();

  // Active Main Tab: Studio vs History
  const [activeMainTab, setActiveMainTab] = useState<'create' | 'history'>('create');

  // Report Setup
  const [reportType, setReportType] = useState<'client_nippo' | 'client_shuho' | 'internal_standup'>('client_nippo');
  const [reportDate, setReportDate] = useState<string>(() => new Date().toISOString().split('T')[0]);
  const [senderName, setSenderName] = useState<string>('BrSE / Offshore Lead');
  const [recipientName, setRecipientName] = useState<string>('お客様 (Client PM / Tech Lead)');
  const [targetLanguage, setTargetLanguage] = useState<'ja' | 'vi' | 'bilingual'>('ja');
  const [additionalNotes, setAdditionalNotes] = useState<string>('');

  // Auto-Harvest Toggle & State (Default: OFF per user requirement)
  const [isAutoHarvest, setIsAutoHarvest] = useState<boolean>(false);
  const [harvestLoading, setHarvestLoading] = useState<boolean>(false);
  const [harvestData, setHarvestData] = useState<any | null>(null);
  const [selectedItemIds, setSelectedItemIds] = useState<string[]>([]);

  // Manual Freeform Input & Composer Ref
  const [manualInput, setManualInput] = useState<string>('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Markdown Formatting Helpers for Google Chat / Slack Composer
  const handleWrapSelection = (prefix: string, suffix: string, defaultPlaceholder: string = 'nội dung') => {
    const el = textareaRef.current;
    if (!el) return;
    const start = el.selectionStart;
    const end = el.selectionEnd;
    const current = manualInput;
    const selected = current.substring(start, end) || defaultPlaceholder;
    const replacement = `${prefix}${selected}${suffix}`;
    const nextVal = current.substring(0, start) + replacement + current.substring(end);
    setManualInput(nextVal);
    setTimeout(() => {
      el.focus();
      el.setSelectionRange(start + prefix.length, start + prefix.length + selected.length);
    }, 0);
  };

  const handleInsertPrefix = (prefix: string) => {
    const el = textareaRef.current;
    if (!el) return;
    const start = el.selectionStart;
    const end = el.selectionEnd;
    const current = manualInput;
    const needsNewline = start > 0 && current[start - 1] !== '\n';
    const toInsert = needsNewline ? `\n${prefix}` : prefix;
    const nextVal = current.substring(0, start) + toInsert + current.substring(end);
    setManualInput(nextVal);
    setTimeout(() => {
      el.focus();
      el.setSelectionRange(start + toInsert.length, start + toInsert.length);
    }, 0);
  };

  const handleClearInput = () => {
    if (!manualInput.trim()) return;
    setManualInput('');
    toast.info('Đã xóa', 'Đã làm trống khung soạn thảo.');
  };

  // Skeleton Frame Presets (1-Click Insertion)
  const handleApplySkeleton = (type: 'yesterday_today' | 'nippo' | 'standup') => {
    let skeleton = '';
    if (type === 'yesterday_today') {
      skeleton = `Hôm qua:\n- \n\nHôm nay:\n- \n\nCần khách confirm / Vướng mắc:\n- `;
    } else if (type === 'nippo') {
      skeleton = `- Đã hoàn thành: \n- Đang tiến hành: \n- Kế hoạch ngày mai: \n- Vấn đề cần trao đổi (Saisoku): `;
    } else if (type === 'standup') {
      skeleton = `- Hôm qua đã làm: \n- Hôm nay sẽ làm: \n- Trở ngại (Blocker): `;
    }

    if (!manualInput.trim()) {
      setManualInput(skeleton);
    } else {
      setManualInput(prev => `${prev}\n\n${skeleton}`);
    }
    toast.info('Đã nạp khung mẫu', 'Bạn chỉ việc điền tiếp nội dung công việc.');
    setTimeout(() => {
      textareaRef.current?.focus();
    }, 50);
  };

  // Language detection indicator (Mixed JP / VI vs Pure VI vs Pure JA)
  const detectedLanguage = useMemo(() => {
    if (!manualInput.trim()) return null;
    const hasJapanese = /[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff]/.test(manualInput);
    const hasVietnamese = /[àáạảãâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễìíịỉĩòóọỏõôồốộổỗơờớợởỡùúụủũưừứựửữỳýỵỷỹđ]/i.test(manualInput);

    if (hasJapanese && hasVietnamese) {
      return { label: '🌐 Hỗn hợp Việt - Nhật (AI Tự động tối ưu)', color: 'text-indigo-400 bg-indigo-500/10 border-indigo-500/30' };
    }
    if (hasJapanese) {
      return { label: '🇯🇵 Tiếng Nhật', color: 'text-blue-400 bg-blue-500/10 border-blue-500/30' };
    }
    return { label: '🇻🇳 Tiếng Việt', color: 'text-emerald-400 bg-emerald-500/10 border-emerald-500/30' };
  }, [manualInput]);

  const composerStats = useMemo(() => {
    const lines = manualInput.split('\n').filter(l => l.trim().length > 0).length;
    const chars = manualInput.length;
    return { lines, chars };
  }, [manualInput]);

  // Slide & Document Template Upload
  const [templateFile, setTemplateFile] = useState<File | null>(null);
  const [templateFilePath, setTemplateFilePath] = useState<string | null>(null);
  const [templateAnalysis, setTemplateAnalysis] = useState<any | null>(null);
  const [uploadingTemplate, setUploadingTemplate] = useState<boolean>(false);

  // Custom Text Template & Format Studio
  const [templateSubTab, setTemplateSubTab] = useState<'text' | 'file'>('text');
  const [customTextTemplate, setCustomTextTemplate] = useState<string>('');

  const TEXT_TEMPLATE_PRESETS = [
    {
      id: 'chatwork',
      name: '🏷️ Chatwork [info] Chuẩn Nhật',
      desc: 'Thẻ khung thông tin, phân đoạn [hr] chuyên nghiệp',
      content: `[info][title]【{{project_name}}】進捗報告（{{date}}）[/title]
【本日の実績】
{{achievements}}

【明日の予定】
{{plans}}

【課題・ご確認事項】
{{issues}}
[hr]
何卒よろしくお願い申し上げます。
[/info]`
    },
    {
      id: 'slack',
      name: '💬 Slack Emoji & Markdown',
      desc: 'Định dạng Slack mrkdwn, gạch đầu dòng và icon rõ ràng',
      content: `:mega: *[BÁO CÁO TIẾN ĐỘ] {{project_name}} — {{date}}*
*Người báo cáo:* {{sender}}

:white_check_mark: *Đã hoàn thành:*
{{achievements}}

:dart: *Kế hoạch tiếp theo:*
{{plans}}

:warning: *Vướng mắc & Cần khách confirm:*
{{issues}}`
    },
    {
      id: 'email',
      name: '✉️ Business Email (Keigo & Chữ ký)',
      desc: 'Thư điện tử chuẩn Nhật có kính gửi, lời chào và chữ ký',
      content: `{{recipient}}様

大変お世話になっております。{{sender}}でございます。
{{date}}の業務進捗をご報告いたします。

■ 本日の実績
{{achievements}}

■ 次回の予定
{{plans}}

■ ご確認・ご相談事項
{{issues}}

以上、ご確認のほどよろしくお願い申し上げます。
--------------------------------------------------
{{sender}}
IT Offshore Project Team
--------------------------------------------------`
    },
    {
      id: 'vi_report',
      name: '🇻🇳 Báo cáo Tiếng Việt Nội Bộ',
      desc: 'Báo cáo quản lý dự án cho sếp/khách hàng Việt Nam',
      content: `Kính gửi: {{recipient}}
Người báo cáo: {{sender}}
Dự án: {{project_name}} (Ngày {{date}})

1. Hạng mục đã hoàn thành:
{{achievements}}

2. Kế hoạch công việc tiếp theo:
{{plans}}

3. Vấn đề vướng mắc / Cần hỗ trợ:
{{issues}}`
    }
  ];

  // AI Provider & Model
  const [providers, setProviders] = useState<ProviderInfo[]>([]);
  const [selectedProvider, setSelectedProvider] = useState<string>('auto');
  const [selectedModel, setSelectedModel] = useState<string>('');
  const [generating, setGenerating] = useState<boolean>(false);

  // Advanced Settings Accordion Drawer
  const [isAdvancedSettingsOpen, setIsAdvancedSettingsOpen] = useState<boolean>(false);

  // Output Result
  const [generatedReport, setGeneratedReport] = useState<any | null>(null);
  const [outputChannelTab, setOutputChannelTab] = useState<'email' | 'chatwork' | 'slack' | 'vietnamese'>('email');
  const [emailSubTab, setEmailSubTab] = useState<'preview' | 'raw'>('preview');
  const [copiedType, setCopiedType] = useState<string | null>(null);

  // Live Edit Mode & Editable Contents
  const [isLiveEditMode, setIsLiveEditMode] = useState<boolean>(false);
  const [editableContent, setEditableContent] = useState<{
    markdown: string;
    chatwork: string;
    slack: string;
    vietnamese: string;
  }>({
    markdown: '',
    chatwork: '',
    slack: '',
    vietnamese: ''
  });

  const isContentModified = useMemo(() => {
    if (!generatedReport) return false;
    return (
      editableContent.markdown !== (generatedReport.content_markdown || '') ||
      editableContent.chatwork !== (generatedReport.content_chatwork || '') ||
      editableContent.slack !== (generatedReport.content_slack || '') ||
      editableContent.vietnamese !== (generatedReport.content_vietnamese_preview || '')
    );
  }, [editableContent, generatedReport]);

  const handleRestoreOriginal = () => {
    if (!generatedReport) return;
    setEditableContent({
      markdown: generatedReport.content_markdown || '',
      chatwork: generatedReport.content_chatwork || '',
      slack: generatedReport.content_slack || '',
      vietnamese: generatedReport.content_vietnamese_preview || ''
    });
    toast.info('Đã khôi phục', 'Nội dung đã được trả về bản gốc do AI tạo.');
  };

  // History Tab
  const [reportHistory, setReportHistory] = useState<any[]>([]);
  const [loadingHistory, setLoadingHistory] = useState<boolean>(false);

  // Fetch Providers on Mount
  useEffect(() => {
    loadProviders();
  }, []);

  // Fetch history and harvest when project changes
  useEffect(() => {
    if (activeProject) {
      loadHistory();
      if (isAutoHarvest) {
        handleHarvestData();
      }
    }
  }, [activeProject?.id]);

  const loadProviders = async () => {
    try {
      const provs = await apiClient.getProviders();
      setProviders(provs);
    } catch (e) {
      console.error('Failed to load providers', e);
    }
  };

  const loadHistory = async () => {
    if (!activeProject) return;
    setLoadingHistory(true);
    try {
      const hist = await apiClient.getReportHistory(activeProject.id, 50);
      setReportHistory(hist);
    } catch (e) {
      console.error('Failed to load report history', e);
    } finally {
      setLoadingHistory(false);
    }
  };

  // Harvest data from project WorkItems/Meetings when enabled
  const handleHarvestData = async () => {
    if (!activeProject) return;
    setHarvestLoading(true);
    try {
      const data = await apiClient.harvestReportData(activeProject.id, reportType, reportDate);
      setHarvestData(data);
      const autoIds = [
        ...(data.completed_items || []).map((i: any) => i.id),
        ...(data.pending_questions || []).map((i: any) => i.id)
      ];
      setSelectedItemIds(autoIds);
    } catch (e: any) {
      toast.error('Lỗi khi thu thập dữ liệu dự án', e?.message);
    } finally {
      setHarvestLoading(false);
    }
  };

  // Toggle Auto-harvest
  const toggleAutoHarvest = (checked: boolean) => {
    setIsAutoHarvest(checked);
    if (checked && !harvestData && activeProject) {
      handleHarvestData();
    }
  };

  // Quick insert manual snippet
  const handleInsertSnippet = (snippet: string) => {
    setManualInput(prev => {
      const trimmed = prev.trim();
      return trimmed ? `${trimmed}\n${snippet}` : snippet;
    });
  };

  // Handle template file upload
  const handleTemplateUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setUploadingTemplate(true);
    try {
      const res = await apiClient.uploadReportTemplate(file);
      setTemplateFile(file);
      setTemplateFilePath(res.template_file_path);
      setTemplateAnalysis(res.analysis);

      if (res.raw_text) {
        setCustomTextTemplate(res.raw_text);
        setTemplateSubTab('text');
        toast.success('Đã tải mẫu văn bản', `Nội dung từ ${file.name} đã được nạp vào ô Mẫu Định Dạng Text.`);
      } else {
        const typeLabel = file.name.endsWith('.docx') ? 'Word (.docx)' : (file.name.endsWith('.pptx') ? 'PowerPoint (.pptx)' : 'tài liệu');
        toast.success('Tải template mẫu thành công', `Đã nhận diện file mẫu ${typeLabel}: ${file.name}`);
      }
    } catch (err: any) {
      toast.error('Lỗi tải template', err?.message || 'Không thể upload file mẫu');
    } finally {
      setUploadingTemplate(false);
    }
  };

  const handleRemoveTemplate = () => {
    setTemplateFile(null);
    setTemplateFilePath(null);
    setTemplateAnalysis(null);
  };

  // Generate Report
  const handleGenerateReport = async () => {
    if (!activeProject) {
      toast.warning('Chưa chọn dự án', 'Vui lòng chọn một dự án để tạo báo cáo.');
      return;
    }

    if (!isAutoHarvest && !manualInput.trim()) {
      toast.warning('Chưa nhập nội dung', 'Vui lòng nhập các công việc hoàn thành vào ô nhập liệu, hoặc bật tính năng Auto-Harvest.');
      return;
    }

    setGenerating(true);
    try {
      const payload = {
        project_id: activeProject.id,
        report_type: reportType,
        is_auto_harvest: isAutoHarvest,
        manual_input_raw: manualInput,
        target_language: targetLanguage,
        sender_name: senderName,
        recipient_name: recipientName,
        selected_item_ids: isAutoHarvest ? selectedItemIds : [],
        additional_notes: additionalNotes,
        report_date: reportDate,
        template_file_path: templateFilePath || undefined,
        custom_text_template: customTextTemplate.trim() || undefined,
        provider: selectedProvider,
        model: selectedModel || undefined
      };

      const result = await apiClient.generateReport(payload);
      setGeneratedReport(result);
      setEditableContent({
        markdown: result.content_markdown || '',
        chatwork: result.content_chatwork || '',
        slack: result.content_slack || '',
        vietnamese: result.content_vietnamese_preview || ''
      });
      setIsLiveEditMode(false);
      toast.success('Tạo báo cáo thành công!', 'Báo cáo chuẩn Keigo đã sẵn sàng cho đa kênh (Outlook, Chatwork, Slack, Slide).');
      loadHistory();
    } catch (err: any) {
      toast.error('Lỗi tạo báo cáo', err?.message || 'Không thể tạo báo cáo. Vui lòng kiểm tra API key hoặc thử lại.');
    } finally {
      setGenerating(false);
    }
  };

  // Clipboard Copy Handling (Supports Live Edited Content)
  const handleCopyRichText = async () => {
    const textToCopy = editableContent.markdown || generatedReport?.content_markdown || '';
    if (!textToCopy) return;

    try {
      const typeHtml = 'text/html';
      const typeText = 'text/plain';

      if (!isContentModified && generatedReport?.content_html && navigator.clipboard && window.ClipboardItem) {
        const blobHtml = new Blob([generatedReport.content_html], { type: typeHtml });
        const blobText = new Blob([textToCopy], { type: typeText });
        const item = new ClipboardItem({ [typeHtml]: blobHtml, [typeText]: blobText });
        await navigator.clipboard.write([item]);
      } else {
        await navigator.clipboard.writeText(textToCopy);
      }
      setCopiedType('email');
      toast.success(isContentModified ? 'Đã copy nội dung vừa chỉnh sửa' : 'Đã copy Rich Text HTML', 'Dán thẳng vào Outlook / Gmail!');
      setTimeout(() => setCopiedType(null), 3000);
    } catch (e) {
      await navigator.clipboard.writeText(textToCopy);
      setCopiedType('email');
      toast.info('Đã copy văn bản', 'Đã copy nội dung báo cáo vào bộ nhớ tạm.');
      setTimeout(() => setCopiedType(null), 3000);
    }
  };

  const handleCopyText = async (text: string, type: string, label: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopiedType(type);
      toast.success(`Đã copy định dạng ${label}`, 'Sẵn sàng dán vào kênh của bạn.');
      setTimeout(() => setCopiedType(null), 3000);
    } catch (e) {
      toast.error('Lỗi sao chép', 'Không thể ghi vào bộ nhớ tạm.');
    }
  };

  // Delete history item
  const handleDeleteHistory = async (reportId: string) => {
    const ok = await confirm({
      title: 'Xóa Báo cáo',
      message: 'Bạn có chắc chắn muốn xóa bản ghi báo cáo này khỏi lịch sử dự án? Thao tác này không thể hoàn tác.',
      isDestructive: true,
      confirmText: 'Xóa báo cáo',
      cancelText: 'Hủy'
    });
    if (!ok) return;

    try {
      await apiClient.deleteReport(reportId);
      setReportHistory(prev => prev.filter(r => r.id !== reportId));
      if (generatedReport?.id === reportId) {
        setGeneratedReport(null);
      }
      toast.success('Đã xóa', 'Báo cáo đã được xóa khỏi lịch sử.');
    } catch (e: any) {
      toast.error('Lỗi khi xóa', e?.message);
    }
  };

  const handleLoadHistoryToStudio = (item: any) => {
    setGeneratedReport(item);
    setEditableContent({
      markdown: item.content_markdown || '',
      chatwork: item.content_chatwork || '',
      slack: item.content_slack || '',
      vietnamese: item.content_vietnamese_preview || ''
    });
    setIsLiveEditMode(false);
    setReportType(item.report_type);
    setTargetLanguage(item.target_language || 'ja');
    setSenderName(item.sender_name || 'BrSE / Offshore Lead');
    setRecipientName(item.recipient_name || 'お客様 (Client PM / Tech Lead)');
    setReportDate(item.report_date || new Date().toISOString().split('T')[0]);
    if (item.manual_input_raw) {
      setManualInput(item.manual_input_raw);
    }
    setActiveMainTab('create');
    toast.info('Đã tải báo cáo vào Studio', 'Bạn có thể xem trước, chỉnh sửa hoặc xuất file lại.');
  };

  return (
    <div className="flex-1 flex flex-col h-full overflow-hidden bg-canvas">
      {/* Top Header */}
      <PageHeader
        title={
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-xl bg-blue-500/10 text-blue-500 border border-blue-500/20">
              <FileSpreadsheet className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="text-lg font-bold text-text-primary">Báo cáo Tiến độ (業務報告センター)</span>
                {activeProject && (
                  <Badge variant="outline" className="text-xs font-semibold px-2 py-0.5 border-blue-500/30 text-blue-500 bg-blue-500/5">
                    {activeProject.name}
                  </Badge>
                )}
              </div>
              <p className="text-xs text-text-muted mt-0.5">
                Tự động hóa Nhật báo (日報), Tuần báo (週報) chuẩn Business Keigo & Nhắc việc khéo léo (催促)
              </p>
            </div>
          </div>
        }
        actions={
          <div className="flex items-center gap-3">
            {/* Project Selector if projects exist */}
            {projects.length > 0 && setActiveProject && (
              <div className="w-52">
                <Select
                  value={activeProject?.id || ''}
                  onChange={(val) => {
                    const found = projects.find(p => p.id === val);
                    if (found) setActiveProject(found);
                  }}
                  options={projects.map(p => ({ value: p.id, label: p.name }))}
                  placeholder="Chọn dự án..."
                />
              </div>
            )}

            {/* Studio vs History Mode Tabs */}
            <div className="flex items-center p-1 bg-surface border border-border-default rounded-xl shadow-xs">
              <button
                type="button"
                onClick={() => setActiveMainTab('create')}
                className={`px-3.5 py-1.5 text-xs font-medium rounded-lg transition-all flex items-center gap-1.5 ${
                  activeMainTab === 'create'
                    ? 'bg-blue-600 text-white shadow-xs font-semibold'
                    : 'text-text-muted hover:text-text-primary hover:bg-surface-hover'
                }`}
              >
                <Sparkles className="w-3.5 h-3.5" />
                Soạn Báo Cáo
              </button>
              <button
                type="button"
                onClick={() => setActiveMainTab('history')}
                className={`px-3.5 py-1.5 text-xs font-medium rounded-lg transition-all flex items-center gap-1.5 ${
                  activeMainTab === 'history'
                    ? 'bg-blue-600 text-white shadow-xs font-semibold'
                    : 'text-text-muted hover:text-text-primary hover:bg-surface-hover'
                }`}
              >
                <Clock className="w-3.5 h-3.5" />
                Lịch Sử
                {reportHistory.length > 0 && (
                  <span className="ml-1 px-1.5 py-0.2 rounded-full text-[10px] bg-blue-500/20 text-blue-400">
                    {reportHistory.length}
                  </span>
                )}
              </button>
            </div>
          </div>
        }
      />

      {/* Main Content Area */}
      <div className="flex-1 overflow-y-auto p-4 sm:p-6">
        {activeMainTab === 'create' ? (
          <div className="grid grid-cols-1 xl:grid-cols-12 gap-6 max-w-[1750px] mx-auto">
            {/* LEFT COLUMN: Compact Ergonomic Input & Settings (5 cols) */}
            <div className="xl:col-span-5 space-y-4">
              {/* 1. Quick Control Header Bar: Report Type & Target Language & Advanced Toggle */}
              <div className="p-3 rounded-2xl bg-surface border border-border-default shadow-xs space-y-2.5">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  {/* Report Type Selector Pills */}
                  <div className="flex items-center gap-1 p-1 bg-canvas rounded-xl border border-border-default">
                    {[
                      { id: 'client_nippo', label: '🇯🇵 日報 Nippo', desc: 'Báo cáo ngày' },
                      { id: 'client_shuho', label: '🇯🇵 週報 Shuho', desc: 'Tiến độ tuần' },
                      { id: 'internal_standup', label: '🇻🇳 Standup', desc: 'Họp nội bộ' }
                    ].map((type) => (
                      <button
                        key={type.id}
                        type="button"
                        onClick={() => setReportType(type.id as any)}
                        className={`px-2.5 py-1.5 text-xs font-semibold rounded-lg transition-all ${
                          reportType === type.id
                            ? 'bg-blue-600 text-white shadow-xs'
                            : 'text-text-muted hover:text-text-primary hover:bg-surface'
                        }`}
                        title={type.desc}
                      >
                        {type.label}
                      </button>
                    ))}
                  </div>

                  {/* Advanced Settings Accordion Toggle Button */}
                  <button
                    type="button"
                    onClick={() => setIsAdvancedSettingsOpen(!isAdvancedSettingsOpen)}
                    className={`px-3 py-1.5 text-xs font-medium rounded-xl border transition-all flex items-center gap-1.5 ${
                      isAdvancedSettingsOpen
                        ? 'bg-blue-500/10 border-blue-500/30 text-blue-500 font-semibold'
                        : 'bg-canvas border-border-default text-text-muted hover:text-text-primary hover:bg-surface'
                    }`}
                  >
                    <Sliders className="w-3.5 h-3.5" />
                    <span>Cài đặt & Mẫu</span>
                    {(customTextTemplate.trim() || templateFile || isAutoHarvest) && (
                      <span className="w-2 h-2 rounded-full bg-blue-500 animate-pulse" title="Đang có thiết lập tùy biến" />
                    )}
                    {isAdvancedSettingsOpen ? (
                      <ChevronDown className="w-3.5 h-3.5 transform rotate-180 transition-transform" />
                    ) : (
                      <ChevronDown className="w-3.5 h-3.5 transition-transform" />
                    )}
                  </button>
                </div>

                {/* Target Language Bar */}
                <div className="flex items-center justify-between pt-1 border-t border-border-subtle text-xs">
                  <span className="text-[11px] font-medium text-text-muted">Ngôn ngữ xuất:</span>
                  <div className="flex items-center gap-1">
                    {[
                      { id: 'ja', label: '🇯🇵 Tiếng Nhật (Keigo)' },
                      { id: 'bilingual', label: '🌐 Song ngữ' },
                      { id: 'vi', label: '🇻🇳 Tiếng Việt' }
                    ].map((item) => (
                      <button
                        key={item.id}
                        type="button"
                        onClick={() => setTargetLanguage(item.id as any)}
                        className={`px-2 py-0.8 text-[11px] rounded-lg border transition-all ${
                          targetLanguage === item.id
                            ? 'bg-blue-600 text-white border-blue-600 font-semibold shadow-xs'
                            : 'bg-canvas text-text-muted border-border-default hover:text-text-primary'
                        }`}
                      >
                        {item.label}
                      </button>
                    ))}
                  </div>
                </div>
              </div>

              {/* 2. HERO CHAT COMPOSER (Main Stage - Rộng rãi, Trực quan, Zero Scroll) */}
              <Card className="border-border-default shadow-xs bg-surface overflow-hidden">
                <CardContent className="p-4 space-y-3">
                  {/* Top Bar: Title & Detected Language Indicator */}
                  <div className="flex items-center justify-between">
                    <label className="text-xs font-bold text-text-primary flex items-center gap-1.5">
                      <MessageSquare className="w-4 h-4 text-blue-500" />
                      Nhập tiến độ công việc tự do (Chat Composer):
                    </label>
                    <div className="flex items-center gap-2">
                      {detectedLanguage && (
                        <span className={`px-2 py-0.5 text-[10px] font-medium rounded-full border ${detectedLanguage.color} animate-in fade-in`}>
                          {detectedLanguage.label}
                        </span>
                      )}
                    </div>
                  </div>

                  {/* 1-Click Frame Presets & Quick Insert Bar */}
                  <div className="p-2 rounded-xl bg-canvas border border-border-subtle space-y-2">
                    {/* Skeletons 1-Click */}
                    <div className="flex flex-wrap items-center gap-1.5">
                      <span className="text-[11px] font-semibold text-text-muted flex items-center gap-1 mr-1">
                        <Sparkles className="w-3 h-3 text-blue-400" /> Nạp khung sườn:
                      </span>
                      <button
                        type="button"
                        onClick={() => handleApplySkeleton('yesterday_today')}
                        className="px-2.5 py-1 text-[11px] font-semibold rounded-lg bg-blue-500/10 border border-blue-500/30 text-blue-400 hover:bg-blue-500/20 active:scale-95 transition-all flex items-center gap-1 shadow-2xs"
                        title="Nạp cấu trúc Hôm qua / Hôm nay / Confirm"
                      >
                        📋 Hôm qua / Hôm nay
                      </button>
                      <button
                        type="button"
                        onClick={() => handleApplySkeleton('nippo')}
                        className="px-2.5 py-1 text-[11px] font-semibold rounded-lg bg-indigo-500/10 border border-indigo-500/30 text-indigo-400 hover:bg-indigo-500/20 active:scale-95 transition-all flex items-center gap-1 shadow-2xs"
                        title="Nạp cấu trúc Daily chuẩn Nhật (Xong / Đang làm / Kế hoạch / Saisoku)"
                      >
                        🇯🇵 Chuẩn Nhật
                      </button>
                      <button
                        type="button"
                        onClick={() => handleApplySkeleton('standup')}
                        className="px-2.5 py-1 text-[11px] font-semibold rounded-lg bg-purple-500/10 border border-purple-500/30 text-purple-400 hover:bg-purple-500/20 active:scale-95 transition-all flex items-center gap-1 shadow-2xs"
                        title="Nạp cấu trúc Standup nhanh"
                      >
                        ⚡ Standup Nhanh
                      </button>
                    </div>

                    {/* Quick Bullet Tags */}
                    <div className="flex flex-wrap items-center gap-1 pt-1 border-t border-border-subtle/60">
                      <button
                        type="button"
                        onClick={() => handleInsertPrefix('- ✅ Đã hoàn thành: ')}
                        className="px-2 py-0.5 text-[10px] font-medium rounded-md bg-emerald-500/10 text-emerald-400 hover:bg-emerald-500/20 transition-colors"
                      >
                        ✅ Xong
                      </button>
                      <button
                        type="button"
                        onClick={() => handleInsertPrefix('- ⏳ Đang tiến hành: ')}
                        className="px-2 py-0.5 text-[10px] font-medium rounded-md bg-blue-500/10 text-blue-400 hover:bg-blue-500/20 transition-colors"
                      >
                        ⏳ Đang làm
                      </button>
                      <button
                        type="button"
                        onClick={() => handleInsertPrefix('- ❓ Cần khách confirm (Saisoku): ')}
                        className="px-2 py-0.5 text-[10px] font-medium rounded-md bg-amber-500/10 text-amber-400 hover:bg-amber-500/20 transition-colors"
                      >
                        ❓ Cần Saisoku
                      </button>
                      <button
                        type="button"
                        onClick={() => handleInsertPrefix('- ⚠️ Vướng mắc/Blocker: ')}
                        className="px-2 py-0.5 text-[10px] font-medium rounded-md bg-red-500/10 text-red-400 hover:bg-red-500/20 transition-colors"
                      >
                        ⚠️ Blocker
                      </button>
                      <button
                        type="button"
                        onClick={() => handleInsertPrefix('- 🚀 Kế hoạch tiếp theo: ')}
                        className="px-2 py-0.5 text-[10px] font-medium rounded-md bg-purple-500/10 text-purple-400 hover:bg-purple-500/20 transition-colors"
                      >
                        🚀 Kế hoạch mai
                      </button>
                    </div>
                  </div>

                  {/* Rich Composer Card with Markdown Toolbar */}
                  <div className="flex flex-col rounded-xl bg-canvas border border-border-default focus-within:border-blue-500 focus-within:ring-2 focus-within:ring-blue-500/20 shadow-xs transition-all overflow-hidden">
                    {/* Spacious Textarea */}
                    <textarea
                      ref={textareaRef}
                      value={manualInput}
                      onChange={(e) => setManualInput(e.target.value)}
                      onKeyDown={(e) => {
                        if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'b') {
                          e.preventDefault();
                          handleWrapSelection('**', '**', 'in đậm');
                        } else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'i') {
                          e.preventDefault();
                          handleWrapSelection('*', '*', 'in nghiêng');
                        } else if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
                          e.preventDefault();
                          handleGenerateReport();
                        }
                      }}
                      rows={9}
                      placeholder={`Nhập tự do công việc bằng tiếng Việt, tiếng Nhật hoặc gõ lẫn lộn tuỳ ý:\n\nVí dụ:\nHôm qua:\n- Hoàn thành fix bug đăng nhập và UT\n- QA-021 đang chờ khách xác nhận\n\nHôm nay:\n- Đã deploy bản sửa lên test\n- Chưa có issue ảnh hưởng schedule...`}
                      className="w-full p-3.5 text-xs bg-transparent border-0 resize-y min-h-[200px] focus:outline-none focus:ring-0 leading-relaxed font-sans text-text-primary placeholder:text-text-muted/50"
                    />

                    {/* Bottom Formatting Toolbar */}
                    <div className="flex flex-wrap items-center justify-between px-3 py-2 border-t border-border-subtle bg-surface-subtle/60 gap-2">
                      <div className="flex items-center gap-0.5">
                        <button
                          type="button"
                          onClick={() => handleWrapSelection('**', '**', 'in đậm')}
                          className="p-1.5 rounded-lg text-text-secondary hover:text-text-primary hover:bg-surface transition-colors font-bold text-xs"
                          title="In đậm (Ctrl+B)"
                        >
                          <Bold className="w-3.5 h-3.5" />
                        </button>
                        <button
                          type="button"
                          onClick={() => handleWrapSelection('*', '*', 'in nghiêng')}
                          className="p-1.5 rounded-lg text-text-secondary hover:text-text-primary hover:bg-surface transition-colors italic text-xs"
                          title="In nghiêng (Ctrl+I)"
                        >
                          <Italic className="w-3.5 h-3.5" />
                        </button>
                        <div className="h-3.5 w-px bg-border-subtle mx-1" />
                        <button
                          type="button"
                          onClick={() => handleInsertPrefix('- ')}
                          className="p-1.5 rounded-lg text-text-secondary hover:text-text-primary hover:bg-surface transition-colors"
                          title="Gạch đầu dòng (- )"
                        >
                          <List className="w-3.5 h-3.5" />
                        </button>
                        <button
                          type="button"
                          onClick={() => handleInsertPrefix('1. ')}
                          className="p-1.5 rounded-lg text-text-secondary hover:text-text-primary hover:bg-surface transition-colors"
                          title="Đánh số (1. )"
                        >
                          <ListOrdered className="w-3.5 h-3.5" />
                        </button>
                        <button
                          type="button"
                          onClick={() => handleInsertPrefix('- [ ] ')}
                          className="p-1.5 rounded-lg text-text-secondary hover:text-text-primary hover:bg-surface transition-colors"
                          title="Checkbox (- [ ] )"
                        >
                          <CheckSquare className="w-3.5 h-3.5" />
                        </button>
                        <div className="h-3.5 w-px bg-border-subtle mx-1" />
                        <button
                          type="button"
                          onClick={() => handleWrapSelection('`', '`', 'code')}
                          className="p-1.5 rounded-lg text-text-secondary hover:text-text-primary hover:bg-surface transition-colors"
                          title="Đoạn mã (`code`)"
                        >
                          <Code className="w-3.5 h-3.5" />
                        </button>
                        <button
                          type="button"
                          onClick={() => handleInsertPrefix('> ')}
                          className="p-1.5 rounded-lg text-text-secondary hover:text-text-primary hover:bg-surface transition-colors"
                          title="Trích dẫn (> )"
                        >
                          <Quote className="w-3.5 h-3.5" />
                        </button>
                      </div>

                      {/* Right Info & Clear */}
                      <div className="flex items-center gap-3 text-[11px] text-text-muted">
                        <span>{composerStats.lines} dòng • {composerStats.chars} ký tự</span>
                        {manualInput && (
                          <button
                            type="button"
                            onClick={handleClearInput}
                            className="text-[11px] text-text-muted hover:text-red-400 transition-colors flex items-center gap-1"
                            title="Xóa toàn bộ nội dung đã nhập"
                          >
                            <Trash2 className="w-3 h-3" />
                            Xóa sạch
                          </button>
                        )}
                      </div>
                    </div>
                  </div>

                  {/* Primary Action Button (Right below composer - Zero Scroll) */}
                  <Button
                    onClick={handleGenerateReport}
                    disabled={generating}
                    className="w-full py-2.5 bg-gradient-to-r from-blue-600 via-indigo-600 to-blue-700 hover:from-blue-700 hover:to-indigo-700 text-white font-bold text-sm shadow-md rounded-xl transition-all flex items-center justify-center gap-2 group"
                  >
                    {generating ? (
                      <>
                        <RefreshCw className="w-4 h-4 animate-spin" />
                        Đang biên soạn báo cáo chuẩn Keigo & Xuất đa kênh...
                      </>
                    ) : (
                      <>
                        <Sparkles className="w-4 h-4 text-blue-200 group-hover:rotate-12 transition-transform" />
                        <span>Tạo Báo Cáo Chuẩn Keigo & Đa Kênh</span>
                        <span className="ml-1.5 px-2 py-0.5 rounded-md text-[10px] font-mono bg-white/20 text-white">Ctrl + Enter</span>
                      </>
                    )}
                  </Button>
                </CardContent>
              </Card>

              {/* 3. COLLAPSIBLE DRAWER: Advanced Settings, Templates & AI Model */}
              {isAdvancedSettingsOpen && (
                <div className="space-y-4 animate-in fade-in slide-in-from-top-2 duration-200">
                  {/* Scope: Date, Sender, Recipient & Notes */}
                  <Card className="border-border-default shadow-xs bg-surface">
                    <CardContent className="p-4 space-y-3">
                      <div className="flex items-center justify-between pb-2 border-b border-border-subtle">
                        <span className="text-xs font-bold uppercase tracking-wider text-text-muted">
                          Thông tin Người gửi, Người nhận & Ngày
                        </span>
                        <span className="text-[10px] text-text-muted font-mono">Metadata</span>
                      </div>

                      <div className="grid grid-cols-3 gap-2.5">
                        <div>
                          <label className="text-[11px] font-medium text-text-muted block mb-1">Ngày báo cáo</label>
                          <input
                            type="date"
                            value={reportDate}
                            onChange={(e) => setReportDate(e.target.value)}
                            className="w-full px-2.5 py-1.5 text-xs rounded-lg bg-canvas border border-border-default text-text-primary focus:outline-none focus:ring-1 focus:ring-blue-500"
                          />
                        </div>
                        <div>
                          <label className="text-[11px] font-medium text-text-muted block mb-1">Người gửi</label>
                          <input
                            type="text"
                            value={senderName}
                            onChange={(e) => setSenderName(e.target.value)}
                            placeholder="BrSE / Offshore Lead"
                            className="w-full px-2.5 py-1.5 text-xs rounded-lg bg-canvas border border-border-default text-text-primary focus:outline-none focus:ring-1 focus:ring-blue-500"
                          />
                        </div>
                        <div>
                          <label className="text-[11px] font-medium text-text-muted block mb-1">Người nhận</label>
                          <input
                            type="text"
                            value={recipientName}
                            onChange={(e) => setRecipientName(e.target.value)}
                            placeholder="Khách hàng / PM"
                            className="w-full px-2.5 py-1.5 text-xs rounded-lg bg-canvas border border-border-default text-text-primary focus:outline-none focus:ring-1 focus:ring-blue-500"
                          />
                        </div>
                      </div>

                      <div>
                        <label className="text-[11px] font-medium text-text-muted block mb-1">
                          Ghi chú thêm cho AI (Văn phong, nhấn mạnh tiến độ...):
                        </label>
                        <input
                          type="text"
                          value={additionalNotes}
                          onChange={(e) => setAdditionalNotes(e.target.value)}
                          placeholder="VD: Nhấn mạnh team đã làm OT, văn phong trang trọng 丁寧語..."
                          className="w-full px-3 py-1.5 text-xs rounded-lg bg-canvas border border-border-default text-text-primary focus:outline-none focus:ring-1 focus:ring-blue-500"
                        />
                      </div>
                    </CardContent>
                  </Card>

                  {/* Auto-Harvest Toggle */}
                  <Card className="border-border-default shadow-xs bg-surface">
                    <CardContent className="p-4 space-y-3">
                      <div className="flex items-center justify-between p-3 rounded-xl bg-canvas border border-border-default">
                        <div>
                          <div className="flex items-center gap-2">
                            <span className="text-xs font-bold text-text-primary">Tính năng Auto-Harvest</span>
                            <Badge variant="outline" className={`text-[10px] ${isAutoHarvest ? 'text-blue-500 border-blue-500/30' : 'text-text-muted'}`}>
                              {isAutoHarvest ? 'Đang BẬT' : 'Đang TẮT (Ưu tiên nhập tay)'}
                            </Badge>
                          </div>
                          <p className="text-[11px] text-text-muted mt-0.5">
                            Tự động quét task đã xong & Q&A tồn đọng từ Project Brain / Biên bản họp.
                          </p>
                        </div>

                        <button
                          type="button"
                          onClick={() => toggleAutoHarvest(!isAutoHarvest)}
                          className={`p-1.5 rounded-lg border transition-all flex items-center gap-1.5 text-xs font-semibold ${
                            isAutoHarvest
                              ? 'bg-blue-600 text-white border-blue-600 shadow-xs'
                              : 'bg-surface text-text-muted border-border-default hover:text-text-primary'
                          }`}
                        >
                          {isAutoHarvest ? (
                            <>
                              <ToggleRight className="w-4 h-4 text-white" />
                              <span>BẬT</span>
                            </>
                          ) : (
                            <>
                              <ToggleLeft className="w-4 h-4 text-text-muted" />
                              <span>TẮT</span>
                            </>
                          )}
                        </button>
                      </div>

                      {isAutoHarvest && (
                        <div className="p-3 rounded-xl bg-blue-500/5 border border-blue-500/20 space-y-3 animate-in fade-in duration-150">
                          <div className="flex items-center justify-between">
                            <span className="text-xs font-semibold text-blue-500 flex items-center gap-1.5">
                              <CheckCircle2 className="w-3.5 h-3.5" />
                              Dữ liệu đã thu thập ({selectedItemIds.length} mục chọn)
                            </span>
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={handleHarvestData}
                              disabled={harvestLoading}
                              className="h-6 text-[10px] text-blue-500 px-2"
                            >
                              <RefreshCw className={`w-3 h-3 mr-1 ${harvestLoading ? 'animate-spin' : ''}`} />
                              Làm mới
                            </Button>
                          </div>

                          {harvestLoading ? (
                            <div className="text-center py-4 text-xs text-text-muted">
                              <RefreshCw className="w-4 h-4 animate-spin mx-auto mb-1 text-blue-500" />
                              Đang tổng hợp dữ liệu từ dự án...
                            </div>
                          ) : harvestData ? (
                            <div className="space-y-2 max-h-44 overflow-y-auto pr-1 text-xs">
                              {harvestData.completed_items?.length === 0 && harvestData.pending_questions?.length === 0 && (
                                <p className="text-text-muted text-[11px] italic">Không tìm thấy task hoặc Q&A mới trong ngày hôm nay.</p>
                              )}
                              {harvestData.completed_items?.map((item: any) => (
                                <label key={item.id} className="flex items-start gap-2 p-1.5 rounded-lg bg-surface/80 border border-border-subtle cursor-pointer hover:bg-surface">
                                  <input
                                    type="checkbox"
                                    checked={selectedItemIds.includes(item.id)}
                                    onChange={(e) => {
                                      if (e.target.checked) setSelectedItemIds(prev => [...prev, item.id]);
                                      else setSelectedItemIds(prev => prev.filter(id => id !== item.id));
                                    }}
                                    className="mt-0.5 rounded text-blue-600 focus:ring-blue-500"
                                  />
                                  <div className="flex-1 min-w-0">
                                    <p className="font-medium text-text-primary truncate">{item.title}</p>
                                    <span className="text-[10px] text-text-muted">{item.category} • {item.assignee || 'Unassigned'}</span>
                                  </div>
                                </label>
                              ))}
                              {harvestData.pending_questions?.map((item: any) => (
                                <label key={item.id} className="flex items-start gap-2 p-1.5 rounded-lg bg-amber-500/10 border border-amber-500/20 cursor-pointer hover:bg-amber-500/15">
                                  <input
                                    type="checkbox"
                                    checked={selectedItemIds.includes(item.id)}
                                    onChange={(e) => {
                                      if (e.target.checked) setSelectedItemIds(prev => [...prev, item.id]);
                                      else setSelectedItemIds(prev => prev.filter(id => id !== item.id));
                                    }}
                                    className="mt-0.5 rounded text-amber-600 focus:ring-amber-500"
                                  />
                                  <div className="flex-1 min-w-0">
                                    <p className="font-medium text-amber-400 truncate">❓ [Cần Saisoku] {item.title}</p>
                                    <span className="text-[10px] text-text-muted">Chờ khách phản hồi: {item.recipient || 'Client'}</span>
                                  </div>
                                </label>
                              ))}
                            </div>
                          ) : null}
                        </div>
                      )}
                    </CardContent>
                  </Card>

                  {/* Template Studio (Custom Text & File Templates) */}
                  <Card className="border-border-default shadow-xs bg-surface overflow-hidden">
                    <CardContent className="p-4 space-y-3.5">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <Presentation className="w-4 h-4 text-indigo-500" />
                          <span className="text-xs font-bold text-text-primary">
                            Mẫu Báo cáo & Định dạng Tùy biến (Template Studio)
                          </span>
                        </div>
                        <div className="flex items-center gap-1.5">
                          {customTextTemplate.trim() && (
                            <Badge variant="primary" className="text-[10px] bg-blue-500/10 text-blue-500 border-blue-500/20">
                              ✨ Đang dùng mẫu Text
                            </Badge>
                          )}
                          {templateFile && (
                            <Badge variant="success" className="text-[10px] bg-emerald-500/10 text-emerald-500 border-emerald-500/20">
                              📄 {templateFile.name.endsWith('.pptx') ? 'Slide PPTX' : 'Word DOCX'}
                            </Badge>
                          )}
                        </div>
                      </div>

                      {/* Sub-tab Switcher: Mẫu Text vs File Mẫu */}
                      <div className="flex items-center p-1 rounded-xl bg-canvas border border-border-default gap-1">
                        <button
                          type="button"
                          onClick={() => setTemplateSubTab('text')}
                          className={`flex-1 py-1.5 px-3 rounded-lg text-xs font-semibold transition-all flex items-center justify-center gap-1.5 ${
                            templateSubTab === 'text'
                              ? 'bg-surface text-blue-500 shadow-xs border border-border-default'
                              : 'text-text-muted hover:text-text-primary'
                          }`}
                        >
                          <MessageSquare className="w-3.5 h-3.5" />
                          Mẫu Định dạng Văn bản (Text / Chat / Email)
                        </button>
                        <button
                          type="button"
                          onClick={() => setTemplateSubTab('file')}
                          className={`flex-1 py-1.5 px-3 rounded-lg text-xs font-semibold transition-all flex items-center justify-center gap-1.5 ${
                            templateSubTab === 'file'
                              ? 'bg-surface text-indigo-500 shadow-xs border border-border-default'
                              : 'text-text-muted hover:text-text-primary'
                          }`}
                        >
                          <Presentation className="w-3.5 h-3.5" />
                          File Mẫu Slide / Word (.pptx, .docx, .txt, .md)
                        </button>
                      </div>

                      {templateSubTab === 'text' && (
                        <div className="space-y-3 pt-1 animate-in fade-in duration-150">
                          <div>
                            <span className="text-[11px] font-medium text-text-muted block mb-1.5">
                              Chọn nhanh mẫu chuẩn (Presets) hoặc dán mẫu riêng của bạn:
                            </span>
                            <div className="grid grid-cols-2 gap-1.5">
                              {TEXT_TEMPLATE_PRESETS.map((preset) => (
                                <button
                                  key={preset.id}
                                  type="button"
                                  onClick={() => {
                                    setCustomTextTemplate(preset.content);
                                    toast.info('Đã áp dụng mẫu', `Đã chuyển sang ${preset.name}`);
                                  }}
                                  className={`p-2 text-left rounded-lg border transition-all text-xs ${
                                    customTextTemplate === preset.content
                                      ? 'bg-blue-500/10 border-blue-500/30 text-blue-500 font-semibold'
                                      : 'bg-canvas text-text-secondary border-border-default hover:border-blue-500/30 hover:bg-surface'
                                  }`}
                                >
                                  <div className="font-semibold">{preset.name}</div>
                                  <div className="text-[10px] text-text-muted mt-0.5 line-clamp-1">{preset.desc}</div>
                                </button>
                              ))}
                            </div>
                          </div>

                          <div className="space-y-1.5">
                            <div className="flex items-center justify-between">
                              <label className="text-[11px] font-medium text-text-muted">
                                Nội dung khung mẫu văn bản:
                              </label>
                              {customTextTemplate && (
                                <button
                                  type="button"
                                  onClick={() => {
                                    setCustomTextTemplate('');
                                    toast.info('Đã hủy mẫu', 'Báo cáo sẽ trở về định dạng mặc định.');
                                  }}
                                  className="text-[10px] text-text-muted hover:text-red-400 flex items-center gap-1 transition-colors"
                                >
                                  <Trash2 className="w-3 h-3" />
                                  Khôi phục mặc định
                                </button>
                              )}
                            </div>

                            <textarea
                              value={customTextTemplate}
                              onChange={(e) => setCustomTextTemplate(e.target.value)}
                              placeholder={`Dán khung mẫu tin nhắn Chatwork, Slack hoặc Email vào đây...\nVí dụ:\n[info][title]【Dự án】Báo cáo ngày {{date}}[/title]\n1. Đã hoàn thành:\n{{achievements}}\n2. Kế hoạch:\n{{plans}}\n[/info]`}
                              rows={5}
                              className="w-full p-2.5 text-xs font-mono rounded-xl bg-canvas border border-border-default text-text-primary focus:outline-none focus:ring-1 focus:ring-blue-500 leading-relaxed"
                            />

                            <div className="flex flex-wrap items-center gap-1.5 pt-1">
                              <span className="text-[10px] text-text-muted mr-1">Chèn biến số:</span>
                              {[
                                { tag: '{{project_name}}', label: 'Tên dự án' },
                                { tag: '{{date}}', label: 'Ngày' },
                                { tag: '{{achievements}}', label: 'Hạng mục hoàn thành' },
                                { tag: '{{plans}}', label: 'Kế hoạch tiếp theo' },
                                { tag: '{{issues}}', label: 'Vấn đề & Saisoku' },
                                { tag: '{{sender}}', label: 'Người gửi' },
                                { tag: '{{recipient}}', label: 'Khách hàng' }
                              ].map((v) => (
                                <button
                                  key={v.tag}
                                  type="button"
                                  onClick={() => setCustomTextTemplate(prev => prev ? `${prev} ${v.tag}` : v.tag)}
                                  className="px-2 py-0.5 rounded-md text-[10px] font-mono bg-surface hover:bg-surface-hover border border-border-default text-text-secondary hover:text-blue-500 transition-colors"
                                  title={`Chèn thẻ ${v.tag}`}
                                >
                                  + {v.tag}
                                </button>
                              ))}
                            </div>
                          </div>
                        </div>
                      )}

                      {templateSubTab === 'file' && (
                        <div className="space-y-3 pt-1 animate-in fade-in duration-150">
                          {templateFile ? (
                            <div className="flex items-center justify-between p-3.5 rounded-xl bg-indigo-500/10 border border-indigo-500/30">
                              <div className="flex items-center gap-3 min-w-0">
                                <div className="p-2 rounded-lg bg-indigo-500/20 text-indigo-400 flex-shrink-0">
                                  {templateFile.name.endsWith('.docx') ? <FileText className="w-5 h-5" /> : <Presentation className="w-5 h-5" />}
                                </div>
                                <div className="min-w-0">
                                  <p className="text-xs font-semibold text-text-primary truncate">{templateFile.name}</p>
                                  <p className="text-[11px] text-indigo-300 mt-0.5">
                                    {templateAnalysis?.file_type === 'docx' 
                                      ? `Word DOCX: ${templateAnalysis.paragraph_count || 0} đoạn, ${templateAnalysis.table_count || 0} bảng`
                                      : (templateAnalysis?.slide_count || templateAnalysis?.total_slides 
                                          ? `PowerPoint: ${templateAnalysis.slide_count || templateAnalysis.total_slides} slides layout`
                                          : 'Đã sẵn sàng Smart Clone & Fill')}
                                  </p>
                                  <span className="inline-block mt-1 text-[10px] font-medium text-emerald-400">
                                    ✓ AI sẽ giữ 100% Logo, Bố cục & Màu sắc khi xuất file
                                  </span>
                                </div>
                              </div>
                              <button
                                type="button"
                                onClick={handleRemoveTemplate}
                                className="p-1.5 rounded-lg text-text-muted hover:text-red-400 hover:bg-surface transition-colors"
                                title="Gỡ file mẫu"
                              >
                                <X className="w-4 h-4" />
                              </button>
                            </div>
                          ) : (
                            <label className="flex flex-col items-center justify-center p-4 border-2 border-dashed border-border-default hover:border-indigo-500/50 rounded-xl cursor-pointer bg-canvas/50 hover:bg-indigo-500/5 transition-all text-center">
                              <Upload className="w-6 h-6 text-indigo-400 mb-1.5" />
                              <span className="text-xs font-semibold text-text-primary">
                                {uploadingTemplate ? 'Đang phân tích layout mẫu...' : 'Tải lên File Mẫu (.pptx, .docx, .txt, .md)'}
                              </span>
                              <span className="text-[11px] text-text-muted mt-1 max-w-sm">
                                Hỗ trợ Slide thuyết trình, Báo cáo Word có sẵn logo/bảng biểu, hoặc file Text mẫu.
                              </span>
                              <span className="mt-2 inline-flex items-center gap-1 text-[10px] font-semibold text-indigo-400 bg-indigo-500/10 px-2 py-0.5 rounded-md border border-indigo-500/20">
                                ✨ Smart Clone & Fill: Giữ 100% Bố cục gốc
                              </span>
                              <input
                                type="file"
                                accept=".pptx,.docx,.xlsx,.txt,.md"
                                onChange={handleTemplateUpload}
                                disabled={uploadingTemplate}
                                className="hidden"
                              />
                            </label>
                          )}
                        </div>
                      )}
                    </CardContent>
                  </Card>

                  {/* AI Provider & Model Config */}
                  <div className="p-3.5 rounded-xl bg-gradient-to-br from-blue-900/20 via-surface to-indigo-900/20 border border-blue-500/30 shadow-xs space-y-2.5">
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-bold text-text-primary flex items-center gap-1.5">
                        <Sparkles className="w-3.5 h-3.5 text-blue-400" />
                        Cấu hình Mô hình Trí tuệ Nhân tạo
                      </span>
                      <span className="text-[11px] text-blue-400 font-mono">Keigo Engine v2.5</span>
                    </div>

                    <ProviderModelSelector
                      providers={providers}
                      selectedProvider={selectedProvider}
                      selectedModel={selectedModel}
                      onChangeProvider={setSelectedProvider}
                      onChangeModel={setSelectedModel}
                    />
                  </div>
                </div>
              )}
            </div>

            {/* RIGHT COLUMN: Realtime Multi-channel Preview & Exporters (7 cols) */}
            <div className="xl:col-span-7 flex flex-col space-y-4">
              {generatedReport ? (
                <div className="flex-1 flex flex-col bg-surface border border-border-default rounded-2xl shadow-xs overflow-hidden">
                  {/* Channel Tab Header */}
                  <div className="flex flex-wrap items-center justify-between p-3 border-b border-border-default bg-canvas gap-2">
                    <div className="flex items-center gap-1 bg-surface p-1 rounded-xl border border-border-subtle">
                      <button
                        type="button"
                        onClick={() => setOutputChannelTab('email')}
                        className={`px-3 py-1.5 text-xs font-medium rounded-lg transition-all flex items-center gap-1.5 ${
                          outputChannelTab === 'email'
                            ? 'bg-blue-600 text-white shadow-xs font-semibold'
                            : 'text-text-muted hover:text-text-primary hover:bg-surface-hover'
                        }`}
                      >
                        <Mail className="w-3.5 h-3.5" />
                        📧 Email / Outlook
                      </button>

                      <button
                        type="button"
                        onClick={() => setOutputChannelTab('chatwork')}
                        className={`px-3 py-1.5 text-xs font-medium rounded-lg transition-all flex items-center gap-1.5 ${
                          outputChannelTab === 'chatwork'
                            ? 'bg-red-600 text-white shadow-xs font-semibold'
                            : 'text-text-muted hover:text-text-primary hover:bg-surface-hover'
                        }`}
                      >
                        <MessageSquare className="w-3.5 h-3.5" />
                        💬 Chatwork
                      </button>

                      <button
                        type="button"
                        onClick={() => setOutputChannelTab('slack')}
                        className={`px-3 py-1.5 text-xs font-medium rounded-lg transition-all flex items-center gap-1.5 ${
                          outputChannelTab === 'slack'
                            ? 'bg-emerald-600 text-white shadow-xs font-semibold'
                            : 'text-text-muted hover:text-text-primary hover:bg-surface-hover'
                        }`}
                      >
                        <Send className="w-3.5 h-3.5" />
                        📱 Slack
                      </button>

                      <button
                        type="button"
                        onClick={() => setOutputChannelTab('vietnamese')}
                        className={`px-3 py-1.5 text-xs font-medium rounded-lg transition-all flex items-center gap-1.5 ${
                          outputChannelTab === 'vietnamese'
                            ? 'bg-purple-600 text-white shadow-xs font-semibold'
                            : 'text-text-muted hover:text-text-primary hover:bg-surface-hover'
                        }`}
                      >
                        <FileText className="w-3.5 h-3.5" />
                        🇻🇳 Bản Dịch Đối Chiếu
                      </button>
                    </div>

                    {/* Copy & Live Edit Action Buttons */}
                    <div className="flex items-center gap-1.5">
                      {/* Live Edit Mode Toggle */}
                      <Button
                        variant={isLiveEditMode ? "primary" : "outline"}
                        size="sm"
                        onClick={() => setIsLiveEditMode(!isLiveEditMode)}
                        className={`h-8 text-xs font-semibold gap-1.5 transition-all ${
                          isLiveEditMode ? 'bg-amber-600 hover:bg-amber-700 text-white border-amber-600 shadow-xs' : 'border-border-default'
                        }`}
                        title="Chỉnh sửa câu chữ trực tiếp trước khi copy hoặc xuất file"
                      >
                        {isLiveEditMode ? <Eye className="w-3.5 h-3.5 mr-1" /> : <Edit3 className="w-3.5 h-3.5 mr-1" />}
                        {isLiveEditMode ? 'Xem trước' : 'Chỉnh sửa trực tiếp'}
                      </Button>

                      {/* Restore Original AI button if modified */}
                      {isContentModified && (
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={handleRestoreOriginal}
                          className="h-8 text-xs text-amber-400 hover:text-amber-300 hover:bg-amber-500/10 gap-1"
                          title="Khôi phục lại nội dung gốc ban đầu do AI tạo"
                        >
                          <RotateCcw className="w-3.5 h-3.5 mr-1" />
                          Khôi phục gốc
                        </Button>
                      )}

                      <div className="h-4 w-px bg-border-subtle mx-0.5" />

                      {outputChannelTab === 'email' && (
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={handleCopyRichText}
                          className="h-8 text-xs font-semibold border-blue-500/40 text-blue-500 hover:bg-blue-500/10"
                        >
                          {copiedType === 'email' ? <Check className="w-3.5 h-3.5 mr-1" /> : <Copy className="w-3.5 h-3.5 mr-1" />}
                          {isContentModified ? 'Copy Nội Dung Đã Sửa' : 'Copy Rich Text (Outlook/Gmail)'}
                        </Button>
                      )}

                      {outputChannelTab === 'chatwork' && (
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => handleCopyText(editableContent.chatwork || '', 'chatwork', 'Chatwork')}
                          className="h-8 text-xs font-semibold border-red-500/40 text-red-500 hover:bg-red-500/10"
                        >
                          {copiedType === 'chatwork' ? <Check className="w-3.5 h-3.5 mr-1" /> : <Copy className="w-3.5 h-3.5 mr-1" />}
                          Copy Mã Chatwork
                        </Button>
                      )}

                      {outputChannelTab === 'slack' && (
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => handleCopyText(editableContent.slack || '', 'slack', 'Slack')}
                          className="h-8 text-xs font-semibold border-emerald-500/40 text-emerald-500 hover:bg-emerald-500/10"
                        >
                          {copiedType === 'slack' ? <Check className="w-3.5 h-3.5 mr-1" /> : <Copy className="w-3.5 h-3.5 mr-1" />}
                          Copy Mã Slack
                        </Button>
                      )}

                      {outputChannelTab === 'vietnamese' && (
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => handleCopyText(editableContent.vietnamese || '', 'vietnamese', 'Tiếng Việt')}
                          className="h-8 text-xs font-semibold border-purple-500/40 text-purple-500 hover:bg-purple-500/10"
                        >
                          {copiedType === 'vietnamese' ? <Check className="w-3.5 h-3.5 mr-1" /> : <Copy className="w-3.5 h-3.5 mr-1" />}
                          Copy Bản Dịch
                        </Button>
                      )}
                    </div>
                  </div>

                  {/* Sub-header with Downloads */}
                  <div className="flex flex-wrap items-center justify-between px-4 py-2 border-b border-border-subtle bg-surface-subtle text-xs gap-2">
                    <div className="flex items-center gap-2">
                      <span className="text-text-muted">Tiêu đề:</span>
                      <span className="font-semibold text-text-primary font-mono">{generatedReport.title}</span>
                      {isContentModified && (
                        <span className="px-1.5 py-0.5 rounded text-[10px] font-medium bg-amber-500/10 border border-amber-500/20 text-amber-400">
                          ✏️ Đã chỉnh sửa
                        </span>
                      )}
                    </div>

                    <div className="flex items-center gap-2">
                      <a
                        href={apiClient.getReportExportUrl(generatedReport.id, 'docx')}
                        target="_blank"
                        rel="noreferrer"
                        className={`px-2.5 py-1 rounded-md transition-all flex items-center gap-1 font-medium text-[11px] ${
                          templateFile?.name.endsWith('.docx')
                            ? 'bg-blue-500/10 border border-blue-500/30 text-blue-500 font-semibold hover:bg-blue-500/20'
                            : 'bg-canvas border border-border-default hover:border-blue-500 hover:text-blue-500'
                        }`}
                        title={templateFile?.name.endsWith('.docx') ? 'Xuất Word theo đúng mẫu của bạn' : 'Tải tài liệu Word chuẩn'}
                      >
                        <Download className="w-3 h-3" />
                        {templateFile?.name.endsWith('.docx') ? 'Tải Word theo Mẫu (.docx)' : 'Tải Word (.docx)'}
                      </a>
                      <a
                        href={apiClient.getReportExportUrl(generatedReport.id, 'xlsx')}
                        target="_blank"
                        rel="noreferrer"
                        className="px-2.5 py-1 rounded-md bg-canvas border border-border-default hover:border-emerald-500 hover:text-emerald-500 transition-all flex items-center gap-1 font-medium text-[11px]"
                      >
                        <Download className="w-3 h-3" />
                        Tải Excel (.xlsx)
                      </a>
                      <a
                        href={apiClient.getReportExportUrl(generatedReport.id, 'pptx')}
                        target="_blank"
                        rel="noreferrer"
                        className={`px-2.5 py-1 rounded-md transition-all flex items-center gap-1 font-semibold text-[11px] ${
                          templateFile?.name.endsWith('.pptx')
                            ? 'bg-indigo-500/20 border border-indigo-500/40 text-indigo-300 hover:bg-indigo-500/30 ring-1 ring-indigo-500/20'
                            : 'bg-indigo-500/10 border border-indigo-500/30 text-indigo-400 hover:bg-indigo-500/20'
                        }`}
                        title={templateFile?.name.endsWith('.pptx') ? 'Xuất Slide theo đúng thiết kế mẫu của bạn' : 'Tải slide thuyết trình chuẩn 16:9'}
                      >
                        <Presentation className="w-3 h-3" />
                        {templateFile?.name.endsWith('.pptx') ? 'Tải Slide theo Mẫu (.pptx)' : 'Tải Slide (.pptx)'}
                      </a>
                    </div>
                  </div>

                  {/* Channel Content Body (View vs Live Edit) */}
                  <div className="flex-1 p-5 overflow-y-auto max-h-[700px]">
                    {/* LIVE EDIT MODE */}
                    {isLiveEditMode ? (
                      <div className="space-y-3 animate-in fade-in duration-150">
                        <div className="flex items-center justify-between text-xs text-amber-400 bg-amber-500/10 p-2.5 rounded-xl border border-amber-500/20">
                          <span className="flex items-center gap-1.5 font-semibold">
                            <Edit3 className="w-4 h-4 text-amber-400" />
                            Đang ở Chế độ Chỉnh sửa Trực tiếp ({outputChannelTab.toUpperCase()})
                          </span>
                          <span className="text-[11px] text-text-muted">
                            Các thay đổi được lưu tự động và áp dụng ngay khi Copy
                          </span>
                        </div>

                        {outputChannelTab === 'email' && (
                          <textarea
                            value={editableContent.markdown}
                            onChange={(e) => setEditableContent(prev => ({ ...prev, markdown: e.target.value }))}
                            rows={18}
                            className="w-full p-4 rounded-xl bg-canvas border border-border-default text-text-primary text-xs font-mono leading-relaxed focus:outline-none focus:ring-1 focus:ring-amber-500 resize-y"
                            placeholder="Chỉnh sửa nội dung email / markdown..."
                          />
                        )}

                        {outputChannelTab === 'chatwork' && (
                          <textarea
                            value={editableContent.chatwork}
                            onChange={(e) => setEditableContent(prev => ({ ...prev, chatwork: e.target.value }))}
                            rows={18}
                            className="w-full p-4 rounded-xl bg-canvas border border-border-default text-text-primary text-xs font-mono leading-relaxed focus:outline-none focus:ring-1 focus:ring-red-500 resize-y"
                            placeholder="Chỉnh sửa mã Chatwork..."
                          />
                        )}

                        {outputChannelTab === 'slack' && (
                          <textarea
                            value={editableContent.slack}
                            onChange={(e) => setEditableContent(prev => ({ ...prev, slack: e.target.value }))}
                            rows={18}
                            className="w-full p-4 rounded-xl bg-canvas border border-border-default text-text-primary text-xs font-mono leading-relaxed focus:outline-none focus:ring-1 focus:ring-emerald-500 resize-y"
                            placeholder="Chỉnh sửa mã Slack..."
                          />
                        )}

                        {outputChannelTab === 'vietnamese' && (
                          <textarea
                            value={editableContent.vietnamese}
                            onChange={(e) => setEditableContent(prev => ({ ...prev, vietnamese: e.target.value }))}
                            rows={18}
                            className="w-full p-4 rounded-xl bg-canvas border border-border-default text-text-primary text-xs font-sans leading-relaxed focus:outline-none focus:ring-1 focus:ring-purple-500 resize-y"
                            placeholder="Chỉnh sửa bản dịch tiếng Việt đối chiếu..."
                          />
                        )}
                      </div>
                    ) : (
                      /* NORMAL PREVIEW MODE */
                      <>
                        {outputChannelTab === 'email' && (
                          <div className="space-y-3">
                            <div className="flex items-center justify-between border-b border-border-subtle pb-2">
                              <span className="text-xs text-text-muted">
                                {targetLanguage === 'vi' 
                                  ? '📧 Dạng hiển thị Email 100% Tiếng Việt chuẩn công sở trang trọng' 
                                  : (targetLanguage === 'bilingual' 
                                      ? '🌐 Dạng hiển thị Email Song ngữ Nhật - Việt song song'
                                      : '🇯🇵 Dạng hiển thị Email chuẩn Keigo (Kính ngữ 丁寧語 / 謙譲語 & Saisoku khéo léo)')}
                              </span>
                              <div className="flex items-center gap-1">
                                <button
                                  type="button"
                                  onClick={() => setEmailSubTab('preview')}
                                  className={`px-2 py-0.5 text-[11px] rounded ${
                                    emailSubTab === 'preview' ? 'bg-blue-600 text-white font-medium' : 'text-text-muted hover:text-text-primary'
                                  }`}
                                >
                                  Hiển thị Xem trước
                                </button>
                                <button
                                  type="button"
                                  onClick={() => setEmailSubTab('raw')}
                                  className={`px-2 py-0.5 text-[11px] rounded ${
                                    emailSubTab === 'raw' ? 'bg-blue-600 text-white font-medium' : 'text-text-muted hover:text-text-primary'
                                  }`}
                                >
                                  Mã Markdown
                                </button>
                              </div>
                            </div>

                            {emailSubTab === 'preview' ? (
                              isContentModified ? (
                                <div className="p-5 rounded-xl bg-canvas border border-border-default">
                                  <MarkdownView content={editableContent.markdown} />
                                </div>
                              ) : (
                                <div
                                  className="p-5 rounded-xl bg-canvas border border-border-default text-text-primary text-xs leading-relaxed font-sans overflow-x-auto select-text"
                                  dangerouslySetInnerHTML={{ __html: generatedReport.content_html || '<p>Không có nội dung HTML</p>' }}
                                />
                              )
                            ) : (
                              <pre className="p-4 rounded-xl bg-canvas border border-border-default text-text-secondary text-xs font-mono whitespace-pre-wrap select-text">
                                {editableContent.markdown}
                              </pre>
                            )}
                          </div>
                        )}

                        {outputChannelTab === 'chatwork' && (
                          <div className="space-y-3">
                            <div className="flex items-center justify-between border-b border-border-subtle pb-2">
                              <span className="text-xs text-text-muted">
                                💬 Chatwork Tag Format [info][title]...[/title][/info]
                              </span>
                            </div>
                            <pre className="p-4 rounded-xl bg-canvas border border-border-default text-text-primary text-xs font-mono whitespace-pre-wrap select-text">
                              {editableContent.chatwork || 'Chưa có nội dung Chatwork'}
                            </pre>
                          </div>
                        )}

                        {outputChannelTab === 'slack' && (
                          <div className="space-y-3">
                            <div className="flex items-center justify-between border-b border-border-subtle pb-2">
                              <span className="text-xs text-text-muted">
                                📱 Slack Markdown & Emoji Format
                              </span>
                            </div>
                            <pre className="p-4 rounded-xl bg-canvas border border-border-default text-text-primary text-xs font-mono whitespace-pre-wrap select-text">
                              {editableContent.slack || 'Chưa có nội dung Slack'}
                            </pre>
                          </div>
                        )}

                        {outputChannelTab === 'vietnamese' && (
                          <div className="space-y-3">
                            <div className="flex items-center justify-between border-b border-border-subtle pb-2">
                              <span className="text-xs text-text-muted">
                                🇻🇳 Bản dịch nghĩa tiếng Việt đối chiếu (Dành cho BrSE/Comtor soát xét nội dung)
                              </span>
                            </div>
                            <div className="p-5 rounded-xl bg-canvas border border-border-default">
                              <MarkdownView content={editableContent.vietnamese || 'Chưa có bản xem trước tiếng Việt'} />
                            </div>
                          </div>
                        )}
                      </>
                    )}
                  </div>
                </div>
              ) : (
                /* Empty state */
                <div className="flex-1 flex flex-col items-center justify-center p-8 bg-surface border border-dashed border-border-default rounded-2xl text-center min-h-[500px]">
                  <div className="w-16 h-16 rounded-2xl bg-blue-500/10 border border-blue-500/20 text-blue-500 flex items-center justify-center mb-4">
                    <FileSpreadsheet className="w-8 h-8" />
                  </div>
                  <h3 className="text-base font-bold text-text-primary">Khu vực Xem trước & Xuất bản Đa Kênh</h3>
                  <p className="text-xs text-text-muted max-w-md mt-1 mb-6 leading-relaxed">
                    Sau khi nhấn <span className="font-semibold text-blue-400">"Tạo Báo Cáo Chuẩn Keigo"</span> ở cột bên trái, báo cáo hoàn chỉnh sẽ hiển thị ở đây với 4 kênh phân phối (Outlook, Chatwork, Slack, Slide PPTX).
                  </p>

                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 w-full max-w-xl text-left">
                    <div className="p-3 rounded-xl bg-canvas border border-border-subtle">
                      <div className="text-xs font-bold text-text-primary mb-1">1. Nhập tay linh hoạt</div>
                      <p className="text-[11px] text-text-muted">Nhập tự do tiếng Việt hoặc Nhật, AI tự động chỉnh kính ngữ Keigo.</p>
                    </div>
                    <div className="p-3 rounded-xl bg-canvas border border-border-subtle">
                      <div className="text-xs font-bold text-text-primary mb-1">2. Slide PPTX Theo Mẫu</div>
                      <p className="text-[11px] text-text-muted">Giữ nguyên form slide PowerPoint dự án hoặc xuất file Word/Excel.</p>
                    </div>
                    <div className="p-3 rounded-xl bg-canvas border border-border-subtle">
                      <div className="text-xs font-bold text-text-primary mb-1">3. Saisoku Khéo Léo</div>
                      <p className="text-[11px] text-text-muted">Tự động nhắc câu hỏi Q&A tồn đọng với lời văn mềm mỏng, tôn trọng.</p>
                    </div>
                  </div>
                </div>
              )}
            </div>
          </div>
        ) : (
          /* HISTORY TAB */
          <div className="max-w-[1500px] mx-auto space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-base font-bold text-text-primary">Lịch sử Báo cáo Dự án</h3>
                <p className="text-xs text-text-muted">Danh sách các bản Nhật báo (日報) và Tuần báo (週報) đã tạo trước đây</p>
              </div>
              <Button
                variant="outline"
                size="sm"
                onClick={loadHistory}
                disabled={loadingHistory}
                leftIcon={<RefreshCw className={`w-3.5 h-3.5 ${loadingHistory ? 'animate-spin' : ''}`} />}
              >
                Làm mới
              </Button>
            </div>

            {loadingHistory ? (
              <div className="p-12 text-center text-xs text-text-muted bg-surface rounded-2xl border border-border-default">
                <RefreshCw className="w-5 h-5 animate-spin mx-auto mb-2 text-blue-500" />
                Đang tải danh sách lịch sử báo cáo...
              </div>
            ) : reportHistory.length === 0 ? (
              <div className="p-12 text-center text-xs text-text-muted bg-surface rounded-2xl border border-dashed border-border-default">
                <FileText className="w-8 h-8 text-text-muted mx-auto mb-2 opacity-50" />
                Chưa có báo cáo nào được lưu trong dự án này. Hãy bấm "Soạn Báo Cáo" để tạo bản đầu tiên!
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {reportHistory.map((item) => (
                  <Card key={item.id} className="border-border-default shadow-xs hover:border-blue-500/50 transition-all bg-surface">
                    <CardContent className="p-4 space-y-3">
                      <div className="flex items-center justify-between">
                        <Badge
                          variant="outline"
                          className={
                            item.report_type === 'client_nippo'
                              ? 'text-blue-500 border-blue-500/30 bg-blue-500/5'
                              : item.report_type === 'client_shuho'
                              ? 'text-indigo-400 border-indigo-500/30 bg-indigo-500/5'
                              : 'text-emerald-500 border-emerald-500/30 bg-emerald-500/5'
                          }
                        >
                          {item.report_type === 'client_nippo'
                            ? '🇯🇵 日報 (Nippo)'
                            : item.report_type === 'client_shuho'
                            ? '🇯🇵 週報 (Shuho)'
                            : '🇻🇳 Standup'}
                        </Badge>
                        <span className="text-[11px] text-text-muted font-mono">{item.report_date}</span>
                      </div>

                      <div>
                        <h4 className="font-semibold text-xs text-text-primary line-clamp-1">{item.title}</h4>
                        <p className="text-[11px] text-text-muted mt-0.5 line-clamp-2">
                          Gửi đến: {item.recipient_name} • Người gửi: {item.sender_name}
                        </p>
                      </div>

                      <div className="flex flex-wrap items-center gap-1.5 pt-2 border-t border-border-subtle">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => handleLoadHistoryToStudio(item)}
                          className="h-7 text-xs text-blue-500 hover:text-blue-400 px-2"
                        >
                          <Eye className="w-3.5 h-3.5 mr-1" />
                          Mở xem & Tải file
                        </Button>

                        <a
                          href={apiClient.getReportExportUrl(item.id, 'docx')}
                          target="_blank"
                          rel="noreferrer"
                          className="p-1.5 rounded-lg text-text-muted hover:text-blue-500 hover:bg-canvas transition-colors"
                          title="Tải Word .docx"
                        >
                          <Download className="w-3.5 h-3.5" />
                        </a>

                        <a
                          href={apiClient.getReportExportUrl(item.id, 'pptx')}
                          target="_blank"
                          rel="noreferrer"
                          className="p-1.5 rounded-lg text-text-muted hover:text-indigo-400 hover:bg-canvas transition-colors"
                          title="Tải Slide .pptx"
                        >
                          <Presentation className="w-3.5 h-3.5" />
                        </a>

                        <button
                          type="button"
                          onClick={() => handleDeleteHistory(item.id)}
                          className="p-1.5 rounded-lg text-text-muted hover:text-red-400 hover:bg-canvas transition-colors ml-auto"
                          title="Xóa báo cáo"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    </CardContent>
                  </Card>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};
