import React, { useState, useEffect, useMemo, useRef } from 'react';
import {
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
  FileSpreadsheet,
  Presentation,
  Mail,
  ToggleLeft,
  ToggleRight,
  ExternalLink,
  ChevronDown,
  ChevronRight,
  HelpCircle,
  X,
  Bold,
  Italic,
  List,
  ListOrdered,
  Quote,
  Code,
  CheckSquare
} from 'lucide-react';
import { Project, ProviderInfo } from '../../types';
import { apiClient } from '../../api/client';
import { useToast } from '../../context/ToastContext';
import { useConfirm } from '../../context/ConfirmDialogContext';
import { ProviderModelSelector } from '../ProviderModelSelector';
import { MarkdownView } from '../MarkdownView';
import { Button } from '../ui/Button';
import { Badge } from '../ui/Badge';

interface ReportCenterModalProps {
  isOpen: boolean;
  onClose: () => void;
  activeProject: Project | null;
  projects?: Project[];
  defaultSenderName?: string;
  defaultRecipientName?: string;
}

export const ReportCenterModal: React.FC<ReportCenterModalProps> = ({
  isOpen,
  onClose,
  activeProject,
  projects = [],
  defaultSenderName = 'BrSE / Offshore Lead',
  defaultRecipientName = 'お客様 (Client PM / Tech Lead)'
}) => {
  const toast = useToast();
  const confirm = useConfirm();

  // Active Main Tab
  const [activeMainTab, setActiveMainTab] = useState<'create' | 'history'>('create');

  // Report Setup
  const [reportType, setReportType] = useState<'client_nippo' | 'client_shuho' | 'internal_standup'>('client_nippo');
  const [reportDate, setReportDate] = useState<string>(() => new Date().toISOString().split('T')[0]);
  const [senderName, setSenderName] = useState<string>(defaultSenderName);
  const [recipientName, setRecipientName] = useState<string>(defaultRecipientName);
  const [targetLanguage, setTargetLanguage] = useState<'ja' | 'vi' | 'bilingual'>('ja');
  const [additionalNotes, setAdditionalNotes] = useState<string>('');

  // Auto-Harvest Toggle & State
  const [isAutoHarvest, setIsAutoHarvest] = useState<boolean>(false); // Default OFF per user preference
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

  // Output Result
  const [generatedReport, setGeneratedReport] = useState<any | null>(null);
  const [outputChannelTab, setOutputChannelTab] = useState<'email' | 'chatwork' | 'slack' | 'vietnamese'>('email');
  const [copiedType, setCopiedType] = useState<string | null>(null);

  // History Tab
  const [reportHistory, setReportHistory] = useState<any[]>([]);
  const [loadingHistory, setLoadingHistory] = useState<boolean>(false);

  // Fetch Providers on Open
  useEffect(() => {
    if (isOpen) {
      loadProviders();
      loadHistory();
      if (isAutoHarvest && activeProject) {
        handleHarvestData();
      }
    }
  }, [isOpen, activeProject?.id]);

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
      const hist = await apiClient.getReportHistory(activeProject.id, 20);
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
      // Pre-select completed items and questions by default
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
        toast.success('Tải template mẫu thành công', `Đã áp dụng mẫu ${typeLabel}: ${file.name}`);
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
      toast.warning('Chưa nhập nội dung', 'Vui lòng nhập các công việc hoàn thành vào ô bên dưới, hoặc bật Auto-Harvest.');
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
      toast.success('Tạo báo cáo thành công!', 'Báo cáo đã sẵn sàng cho đa kênh (Outlook, Chatwork, Slack, Slide).');
      loadHistory();
    } catch (err: any) {
      toast.error('Lỗi tạo báo cáo', err?.message || 'Không thể tạo báo cáo. Vui lòng thử lại.');
    } finally {
      setGenerating(false);
    }
  };

  // Clipboard Copy Handling
  const handleCopyRichText = async () => {
    if (!generatedReport?.content_html) return;
    try {
      const typeHtml = 'text/html';
      const typeText = 'text/plain';
      const blobHtml = new Blob([generatedReport.content_html], { type: typeHtml });
      const blobText = new Blob([generatedReport.content_markdown], { type: typeText });

      if (navigator.clipboard && window.ClipboardItem) {
        const item = new ClipboardItem({ [typeHtml]: blobHtml, [typeText]: blobText });
        await navigator.clipboard.write([item]);
      } else {
        await navigator.clipboard.writeText(generatedReport.content_markdown);
      }
      setCopiedType('email');
      toast.success('Đã copy Rich Text HTML', 'Dán thẳng vào Outlook / Gmail sẽ giữ nguyên in đậm, gạch đầu dòng và màu sắc!');
      setTimeout(() => setCopiedType(null), 3000);
    } catch (e) {
      await navigator.clipboard.writeText(generatedReport.content_markdown);
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

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-6 overflow-y-auto bg-black/60 backdrop-blur-sm animate-in fade-in duration-200">
      <div 
        className="relative flex flex-col w-full max-w-6xl max-h-[92vh] bg-surface border border-border rounded-2xl shadow-2xl overflow-hidden text-primary"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-border bg-subtle/50">
          <div className="flex items-center gap-3">
            <div className="p-2.5 rounded-xl bg-blue-500/10 text-blue-500 border border-blue-500/20">
              <FileText className="w-6 h-6" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-xl font-bold tracking-tight">Trung tâm Báo cáo Tiến độ (業務報告センター)</h2>
                {activeProject && (
                  <Badge variant="outline" className="text-xs font-semibold px-2.5 py-0.5 border-blue-500/30 text-blue-500 bg-blue-500/5">
                    {activeProject.name}
                  </Badge>
                )}
              </div>
              <p className="text-xs text-muted-foreground mt-0.5">
                Tự động hóa Báo cáo Ngày (日報), Báo cáo Tuần (週報) chuẩn Business Keigo & Nhắc việc khéo (催促)
              </p>
            </div>
          </div>

          <div className="flex items-center gap-3">
            {/* Main Tabs */}
            <div className="flex items-center p-1 bg-canvas border border-border rounded-xl">
              <button
                type="button"
                onClick={() => setActiveMainTab('create')}
                className={`px-3 py-1.5 text-xs font-medium rounded-lg transition-all ${
                  activeMainTab === 'create'
                    ? 'bg-blue-600 text-white shadow-sm'
                    : 'text-muted-foreground hover:text-primary hover:bg-subtle'
                }`}
              >
                📝 Soạn Báo Cáo
              </button>
              <button
                type="button"
                onClick={() => setActiveMainTab('history')}
                className={`px-3 py-1.5 text-xs font-medium rounded-lg transition-all flex items-center gap-1.5 ${
                  activeMainTab === 'history'
                    ? 'bg-blue-600 text-white shadow-sm'
                    : 'text-muted-foreground hover:text-primary hover:bg-subtle'
                }`}
              >
                <Clock className="w-3.5 h-3.5" />
                Lịch Sử ({reportHistory.length})
              </button>
            </div>

            <button
              onClick={onClose}
              className="p-2 text-muted-foreground hover:text-primary hover:bg-subtle rounded-xl transition-colors"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Modal Body */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          {activeMainTab === 'create' ? (
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
              {/* LEFT COLUMN: Controls & Input (7 cols) */}
              <div className="lg:col-span-7 space-y-5">
                {/* 1. Report Type & Language */}
                <div className="p-4 rounded-xl bg-canvas border border-border space-y-3.5">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Loại Báo Cáo & Ngôn Ngữ</span>
                    <span className="text-xs text-muted-foreground">Format chuẩn Nhật</span>
                  </div>

                  <div className="grid grid-cols-3 gap-2">
                    <button
                      type="button"
                      onClick={() => setReportType('client_nippo')}
                      className={`p-3 text-left rounded-xl border transition-all ${
                        reportType === 'client_nippo'
                          ? 'border-blue-500 bg-blue-500/10 text-blue-500 font-semibold shadow-sm'
                          : 'border-border bg-surface text-muted-foreground hover:border-border-hover hover:text-primary'
                      }`}
                    >
                      <div className="text-xs font-bold">🇯🇵 日報 (Nippo)</div>
                      <div className="text-[11px] opacity-80 mt-0.5">Báo cáo ngày gửi khách</div>
                    </button>

                    <button
                      type="button"
                      onClick={() => setReportType('client_shuho')}
                      className={`p-3 text-left rounded-xl border transition-all ${
                        reportType === 'client_shuho'
                          ? 'border-blue-500 bg-blue-500/10 text-blue-500 font-semibold shadow-sm'
                          : 'border-border bg-surface text-muted-foreground hover:border-border-hover hover:text-primary'
                      }`}
                    >
                      <div className="text-xs font-bold">🇯🇵 週報 (Shuho)</div>
                      <div className="text-[11px] opacity-80 mt-0.5">Tiến độ tuần & Slide WBS</div>
                    </button>

                    <button
                      type="button"
                      onClick={() => setReportType('internal_standup')}
                      className={`p-3 text-left rounded-xl border transition-all ${
                        reportType === 'internal_standup'
                          ? 'border-emerald-500 bg-emerald-500/10 text-emerald-500 font-semibold shadow-sm'
                          : 'border-border bg-surface text-muted-foreground hover:border-border-hover hover:text-primary'
                      }`}
                    >
                      <div className="text-xs font-bold">🇻🇳 Standup Nội Bộ</div>
                      <div className="text-[11px] opacity-80 mt-0.5">Tiếng Việt cho PM/Dev</div>
                    </button>
                  </div>

                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 pt-1">
                    <div>
                      <label className="text-[11px] font-medium text-muted-foreground block mb-1">Ngày báo cáo</label>
                      <input
                        type="date"
                        value={reportDate}
                        onChange={(e) => setReportDate(e.target.value)}
                        className="w-full px-2.5 py-1.5 text-xs rounded-lg border border-border bg-surface text-primary focus:outline-none focus:ring-1 focus:ring-blue-500"
                      />
                    </div>

                    <div>
                      <label className="text-[11px] font-medium text-muted-foreground block mb-1">Ngôn ngữ đích</label>
                      <select
                        value={targetLanguage}
                        onChange={(e: any) => setTargetLanguage(e.target.value)}
                        className="w-full px-2.5 py-1.5 text-xs rounded-lg border border-border bg-surface text-primary focus:outline-none focus:ring-1 focus:ring-blue-500"
                      >
                        <option value="ja">🇯🇵 Tiếng Nhật (Keigo)</option>
                        <option value="vi">🇻🇳 Tiếng Việt</option>
                        <option value="bilingual">🌐 Song ngữ (JP+VI)</option>
                      </select>
                    </div>

                    <div>
                      <label className="text-[11px] font-medium text-muted-foreground block mb-1">Người gửi (BrSE)</label>
                      <input
                        type="text"
                        value={senderName}
                        onChange={(e) => setSenderName(e.target.value)}
                        placeholder="Nguyen Phuc (BrSE)"
                        className="w-full px-2.5 py-1.5 text-xs rounded-lg border border-border bg-surface text-primary focus:outline-none focus:ring-1 focus:ring-blue-500"
                      />
                    </div>

                    <div>
                      <label className="text-[11px] font-medium text-muted-foreground block mb-1">Người nhận (Khách)</label>
                      <input
                        type="text"
                        value={recipientName}
                        onChange={(e) => setRecipientName(e.target.value)}
                        placeholder="Yamada-san (PM)"
                        className="w-full px-2.5 py-1.5 text-xs rounded-lg border border-border bg-surface text-primary focus:outline-none focus:ring-1 focus:ring-blue-500"
                      />
                    </div>
                  </div>
                </div>

                {/* 2. AUTO-HARVEST TOGGLE & INPUT SELECTION */}
                <div className="p-4 rounded-xl bg-canvas border border-border space-y-3.5">
                  <div className="flex items-center justify-between pb-2 border-b border-border/60">
                    <div className="flex items-center gap-2.5">
                      <span className="text-xs font-bold text-primary">Tự động gom dữ liệu dự án (Auto-Harvest)</span>
                      {isAutoHarvest ? (
                        <Badge variant="outline" className="text-[10px] px-2 py-0.5 border-emerald-500/30 text-emerald-500 bg-emerald-500/10">
                          ĐANG BẬT
                        </Badge>
                      ) : (
                        <Badge variant="outline" className="text-[10px] px-2 py-0.5 border-muted text-muted-foreground bg-muted/10">
                          ĐANG TẮT (Ưu tiên nhập tay)
                        </Badge>
                      )}
                    </div>

                    <button
                      type="button"
                      onClick={() => toggleAutoHarvest(!isAutoHarvest)}
                      className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus:outline-none ${
                        isAutoHarvest ? 'bg-blue-600' : 'bg-muted'
                      }`}
                    >
                      <span
                        className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                          isAutoHarvest ? 'translate-x-6' : 'translate-x-1'
                        }`}
                      />
                    </button>
                  </div>

                  {/* If Auto-Harvest is OFF: Prominent Google Chat / Slack Style Composer */}
                  {!isAutoHarvest ? (
                    <div className="space-y-2.5">
                      <div className="flex items-center justify-between">
                        <label className="text-xs font-bold text-primary flex items-center gap-1.5">
                          <MessageSquare className="w-3.5 h-3.5 text-blue-500" />
                          Nhập công việc & tiến độ tự do (Chat Composer):
                        </label>
                        <div className="flex items-center gap-2">
                          {detectedLanguage && (
                            <span className={`px-2 py-0.5 text-[10px] font-medium rounded-full border ${detectedLanguage.color} animate-in fade-in`}>
                              {detectedLanguage.label}
                            </span>
                          )}
                        </div>
                      </div>

                      {/* Top Pill Buttons (Quick Insert Categories) */}
                      <div className="flex flex-wrap items-center gap-1.5 p-2 rounded-xl bg-canvas border border-border">
                        <span className="text-[11px] font-semibold text-muted-foreground flex items-center gap-1 mr-1">
                          <Sparkles className="w-3 h-3 text-blue-400" /> Chèn nhanh:
                        </span>
                        <button
                          type="button"
                          onClick={() => handleInsertPrefix('- ✅ Đã hoàn thành: ')}
                          className="px-2.5 py-1 text-[11px] font-medium rounded-lg bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 hover:bg-emerald-500/20 active:scale-95 transition-all flex items-center gap-1"
                        >
                          ✅ Hoàn thành
                        </button>
                        <button
                          type="button"
                          onClick={() => handleInsertPrefix('- ⏳ Đang tiến hành: ')}
                          className="px-2.5 py-1 text-[11px] font-medium rounded-lg bg-blue-500/10 border border-blue-500/30 text-blue-400 hover:bg-blue-500/20 active:scale-95 transition-all flex items-center gap-1"
                        >
                          ⏳ Đang làm
                        </button>
                        <button
                          type="button"
                          onClick={() => handleInsertPrefix('- ❓ Cần khách confirm (Saisoku): ')}
                          className="px-2.5 py-1 text-[11px] font-medium rounded-lg bg-amber-500/10 border border-amber-500/30 text-amber-400 hover:bg-amber-500/20 active:scale-95 transition-all flex items-center gap-1"
                        >
                          ❓ Cần Saisoku
                        </button>
                        <button
                          type="button"
                          onClick={() => handleInsertPrefix('- 🚀 Kế hoạch tiếp theo: ')}
                          className="px-2.5 py-1 text-[11px] font-medium rounded-lg bg-purple-500/10 border border-purple-500/30 text-purple-400 hover:bg-purple-500/20 active:scale-95 transition-all flex items-center gap-1"
                        >
                          🚀 Kế hoạch mai
                        </button>
                        <button
                          type="button"
                          onClick={() => handleInsertPrefix('- ⚠️ Vướng mắc/Blocker: ')}
                          className="px-2.5 py-1 text-[11px] font-medium rounded-lg bg-red-500/10 border border-red-500/30 text-red-400 hover:bg-red-500/20 active:scale-95 transition-all flex items-center gap-1"
                        >
                          ⚠️ Blocker
                        </button>
                      </div>

                      {/* Rich Composer Card with Markdown Toolbar */}
                      <div className="flex flex-col rounded-xl bg-canvas border border-border focus-within:border-blue-500 focus-within:ring-2 focus-within:ring-blue-500/20 shadow-xs transition-all overflow-hidden">
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
                          rows={7}
                          placeholder={`Nhập tự do công việc bằng tiếng Việt, tiếng Nhật hoặc gõ lẫn lộn tuỳ ý:\n\nVí dụ:\n- Hôm nay đã hoàn thành fix 3 bug 画面 ログイン và thanh toán 決済\n- Đang tiến hành test hồi quy luồng mua hàng trên staging\n- Vướng mắc: Đang chờ khách chốt 割引仕様 để hoàn thiện spec (cần saisoku)\n- Kế hoạch ngày mai: Release bản v1.2 lên môi trường UAT...`}
                          className="w-full p-3 text-xs bg-transparent border-0 resize-y min-h-[170px] focus:outline-none focus:ring-0 leading-relaxed font-sans text-primary placeholder:text-muted-foreground/50"
                        />

                        {/* Bottom Formatting Toolbar (Google Chat / Slack Style) */}
                        <div className="flex flex-wrap items-center justify-between px-3 py-2 border-t border-border bg-subtle/50 gap-2">
                          {/* Left Formatting Buttons */}
                          <div className="flex items-center gap-0.5">
                            <button
                              type="button"
                              onClick={() => handleWrapSelection('**', '**', 'in đậm')}
                              className="p-1.5 rounded-lg text-muted-foreground hover:text-primary hover:bg-surface transition-colors font-bold text-xs"
                              title="In đậm (Ctrl+B)"
                            >
                              <Bold className="w-3.5 h-3.5" />
                            </button>
                            <button
                              type="button"
                              onClick={() => handleWrapSelection('*', '*', 'in nghiêng')}
                              className="p-1.5 rounded-lg text-muted-foreground hover:text-primary hover:bg-surface transition-colors italic text-xs"
                              title="In nghiêng (Ctrl+I)"
                            >
                              <Italic className="w-3.5 h-3.5" />
                            </button>
                            <div className="h-3.5 w-px bg-border mx-1" />
                            <button
                              type="button"
                              onClick={() => handleInsertPrefix('- ')}
                              className="p-1.5 rounded-lg text-muted-foreground hover:text-primary hover:bg-surface transition-colors"
                              title="Gạch đầu dòng (- )"
                            >
                              <List className="w-3.5 h-3.5" />
                            </button>
                            <button
                              type="button"
                              onClick={() => handleInsertPrefix('1. ')}
                              className="p-1.5 rounded-lg text-muted-foreground hover:text-primary hover:bg-surface transition-colors"
                              title="Đánh số (1. )"
                            >
                              <ListOrdered className="w-3.5 h-3.5" />
                            </button>
                            <button
                              type="button"
                              onClick={() => handleInsertPrefix('- [ ] ')}
                              className="p-1.5 rounded-lg text-muted-foreground hover:text-primary hover:bg-surface transition-colors"
                              title="Checkbox (- [ ] )"
                            >
                              <CheckSquare className="w-3.5 h-3.5" />
                            </button>
                            <div className="h-3.5 w-px bg-border mx-1" />
                            <button
                              type="button"
                              onClick={() => handleWrapSelection('`', '`', 'code')}
                              className="p-1.5 rounded-lg text-muted-foreground hover:text-primary hover:bg-surface transition-colors"
                              title="Đoạn mã (`code`)"
                            >
                              <Code className="w-3.5 h-3.5" />
                            </button>
                            <button
                              type="button"
                              onClick={() => handleInsertPrefix('> ')}
                              className="p-1.5 rounded-lg text-muted-foreground hover:text-primary hover:bg-surface transition-colors"
                              title="Trích dẫn (> )"
                            >
                              <Quote className="w-3.5 h-3.5" />
                            </button>
                          </div>

                          {/* Right Info & Clear */}
                          <div className="flex items-center gap-3 text-[11px] text-muted-foreground">
                            <span>{composerStats.lines} dòng • {composerStats.chars} ký tự</span>
                            {manualInput && (
                              <button
                                type="button"
                                onClick={handleClearInput}
                                className="text-[11px] text-muted-foreground hover:text-red-400 transition-colors flex items-center gap-1"
                                title="Xóa toàn bộ nội dung đã nhập"
                              >
                                <Trash2 className="w-3 h-3" />
                                Xóa sạch
                              </button>
                            )}
                          </div>
                        </div>
                      </div>
                    </div>
                  ) : (
                    /* If Auto-Harvest is ON: Show checklist from DB */
                    <div className="space-y-3">
                      {harvestLoading ? (
                        <div className="flex items-center justify-center py-8 text-xs text-muted-foreground">
                          <RefreshCw className="w-4 h-4 animate-spin mr-2 text-blue-500" />
                          Đang quét WorkItems, Q&A và quyết định cuộc họp...
                        </div>
                      ) : harvestData ? (
                        <div className="space-y-3">
                          {/* Completed Items */}
                          <div className="p-2.5 rounded-lg border border-border bg-surface/50">
                            <div className="flex items-center justify-between text-xs font-semibold text-emerald-500 mb-2">
                              <span>✅ Đã hoàn thành ({harvestData.completed_items?.length || 0})</span>
                            </div>
                            <div className="max-h-32 overflow-y-auto space-y-1 pr-1">
                              {harvestData.completed_items?.length ? (
                                harvestData.completed_items.map((item: any) => (
                                  <label key={item.id} className="flex items-start gap-2 text-xs text-muted-foreground hover:text-primary cursor-pointer">
                                    <input
                                      type="checkbox"
                                      checked={selectedItemIds.includes(item.id)}
                                      onChange={(e) => {
                                        if (e.target.checked) setSelectedItemIds(prev => [...prev, item.id]);
                                        else setSelectedItemIds(prev => prev.filter(id => id !== item.id));
                                      }}
                                      className="mt-0.5 rounded text-blue-600 focus:ring-blue-500"
                                    />
                                    <span>
                                      <strong className="text-primary">[{item.req_code}]</strong> {item.title}
                                    </span>
                                  </label>
                                ))
                              ) : (
                                <p className="text-[11px] text-muted-foreground italic">Không có task nào hoàn thành hôm nay</p>
                              )}
                            </div>
                          </div>

                          {/* Questions / Saisoku Items */}
                          <div className="p-2.5 rounded-lg border border-border bg-surface/50">
                            <div className="flex items-center justify-between text-xs font-semibold text-amber-500 mb-2">
                              <span>⚠️ Q&A chờ khách duyệt (Nhắc khéo 催促) ({harvestData.pending_questions?.length || 0})</span>
                            </div>
                            <div className="max-h-32 overflow-y-auto space-y-1 pr-1">
                              {harvestData.pending_questions?.length ? (
                                harvestData.pending_questions.map((item: any) => (
                                  <label key={item.id} className="flex items-start gap-2 text-xs text-muted-foreground hover:text-primary cursor-pointer">
                                    <input
                                      type="checkbox"
                                      checked={selectedItemIds.includes(item.id)}
                                      onChange={(e) => {
                                        if (e.target.checked) setSelectedItemIds(prev => [...prev, item.id]);
                                        else setSelectedItemIds(prev => prev.filter(id => id !== item.id));
                                      }}
                                      className="mt-0.5 rounded text-amber-600 focus:ring-amber-500"
                                    />
                                    <span>
                                      <strong className="text-primary">[{item.req_code}]</strong> {item.title}
                                      {item.days_pending > 1 && (
                                        <span className="ml-1 text-[10px] text-amber-500 font-bold">
                                          (Chờ {item.days_pending} ngày)
                                        </span>
                                      )}
                                    </span>
                                  </label>
                                ))
                              ) : (
                                <p className="text-[11px] text-muted-foreground italic">Không có Q&A nào đang pending</p>
                              )}
                            </div>
                          </div>

                          {/* Optional Extra Manual bullets in Auto mode */}
                          <div>
                            <label className="text-[11px] font-medium text-muted-foreground block mb-1">
                              Bổ sung thêm task ngoài lề (nếu có):
                            </label>
                            <textarea
                              rows={2}
                              value={manualInput}
                              onChange={(e) => setManualInput(e.target.value)}
                              placeholder="- Viết thêm ghi chú hoặc công việc ngoài hệ thống..."
                              className="w-full p-2 text-xs rounded-lg border border-border bg-surface text-primary focus:outline-none focus:ring-1 focus:ring-blue-500"
                            />
                          </div>
                        </div>
                      ) : null}
                    </div>
                  )}

                  {/* Notes / Special Remarks */}
                  <div>
                    <label className="text-[11px] font-medium text-muted-foreground block mb-1">
                      Ghi chú / Thông báo khác (Nghỉ phép, OT, lưu ý môi trường Staging/Prod):
                    </label>
                    <input
                      type="text"
                      value={additionalNotes}
                      onChange={(e) => setAdditionalNotes(e.target.value)}
                      placeholder="Ví dụ: Ngày mai Tuấn nghỉ phép, có Nam phụ trách thay thế."
                      className="w-full px-2.5 py-1.5 text-xs rounded-lg border border-border bg-surface text-primary focus:outline-none focus:ring-1 focus:ring-blue-500"
                    />
                  </div>
                </div>

                {/* 3. TEMPLATE SLIDE & TEXT STUDIO */}
                <div className="p-4 rounded-xl bg-canvas border border-border space-y-3.5">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <Presentation className="w-4 h-4 text-orange-500" />
                      <span className="text-xs font-bold text-primary">Mẫu Báo Cáo & Định Dạng (Template Studio)</span>
                    </div>
                    <div className="flex items-center gap-1.5">
                      {customTextTemplate.trim() && (
                        <Badge variant="outline" className="text-[10px] px-2 py-0.5 border-blue-500/30 text-blue-500 bg-blue-500/10">
                          ✨ Áp dụng mẫu Text
                        </Badge>
                      )}
                      {templateFile && (
                        <Badge variant="outline" className="text-[10px] px-2 py-0.5 border-orange-500/30 text-orange-500 bg-orange-500/10">
                          📄 {templateFile.name.endsWith('.pptx') ? 'Slide PPTX' : 'Word DOCX'}
                        </Badge>
                      )}
                    </div>
                  </div>

                  {/* Sub-tab Switcher: Mẫu Text vs File Mẫu */}
                  <div className="flex items-center p-1 rounded-xl bg-surface border border-border gap-1">
                    <button
                      type="button"
                      onClick={() => setTemplateSubTab('text')}
                      className={`flex-1 py-1.5 px-3 rounded-lg text-xs font-semibold transition-all flex items-center justify-center gap-1.5 ${
                        templateSubTab === 'text'
                          ? 'bg-canvas text-blue-500 shadow-xs border border-border'
                          : 'text-muted-foreground hover:text-primary'
                      }`}
                    >
                      <MessageSquare className="w-3.5 h-3.5" />
                      Mẫu Định dạng Text (Chat / Email)
                    </button>
                    <button
                      type="button"
                      onClick={() => setTemplateSubTab('file')}
                      className={`flex-1 py-1.5 px-3 rounded-lg text-xs font-semibold transition-all flex items-center justify-center gap-1.5 ${
                        templateSubTab === 'file'
                          ? 'bg-canvas text-orange-500 shadow-xs border border-border'
                          : 'text-muted-foreground hover:text-primary'
                      }`}
                    >
                      <Presentation className="w-3.5 h-3.5" />
                      File Mẫu Slide / Word (.pptx, .docx, .md, .txt)
                    </button>
                  </div>

                  {/* SUB-TAB 1: MẪU VĂN BẢN (TEXT / CHAT / EMAIL) */}
                  {templateSubTab === 'text' && (
                    <div className="space-y-3 pt-1 animate-in fade-in duration-150">
                      <div>
                        <span className="text-[11px] font-medium text-muted-foreground block mb-1.5">
                          Chọn nhanh mẫu chuẩn hoặc dán mẫu riêng của công ty bạn:
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
                                  : 'bg-surface text-secondary border-border hover:border-blue-500/30'
                              }`}
                            >
                              <div className="font-semibold">{preset.name}</div>
                              <div className="text-[10px] text-muted-foreground mt-0.5 line-clamp-1">{preset.desc}</div>
                            </button>
                          ))}
                        </div>
                      </div>

                      <div className="space-y-1.5">
                        <div className="flex items-center justify-between">
                          <label className="text-[11px] font-medium text-muted-foreground">
                            Nội dung khung mẫu văn bản:
                          </label>
                          {customTextTemplate && (
                            <button
                              type="button"
                              onClick={() => {
                                setCustomTextTemplate('');
                                toast.info('Đã hủy mẫu', 'Báo cáo sẽ trở về định dạng mặc định.');
                              }}
                              className="text-[10px] text-muted-foreground hover:text-red-500 flex items-center gap-1 transition-colors"
                            >
                              <Trash2 className="w-3 h-3" />
                              Khôi phục mặc định
                            </button>
                          )}
                        </div>

                        <textarea
                          value={customTextTemplate}
                          onChange={(e) => setCustomTextTemplate(e.target.value)}
                          placeholder={`Dán khung mẫu tin nhắn Chatwork, Slack hoặc Email của công ty bạn vào đây. Ví dụ:\n[info][title]【Dự án】Báo cáo ngày {{date}}[/title]\n1. Đã hoàn thành:\n{{achievements}}\n2. Kế hoạch:\n{{plans}}\n3. Vấn đề:\n{{issues}}\n[/info]`}
                          rows={5}
                          className="w-full p-2.5 text-xs font-mono rounded-xl bg-surface border border-border text-primary focus:outline-none focus:ring-1 focus:ring-blue-500 leading-relaxed"
                        />

                        {/* Smart Variable Insertion Pills */}
                        <div className="flex flex-wrap items-center gap-1.5 pt-1">
                          <span className="text-[10px] text-muted-foreground mr-1">Chèn biến số:</span>
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
                              className="px-2 py-0.5 rounded-md text-[10px] font-mono bg-subtle hover:bg-surface border border-border text-muted-foreground hover:text-blue-500 transition-colors"
                            >
                              + {v.tag}
                            </button>
                          ))}
                        </div>
                      </div>
                    </div>
                  )}

                  {/* SUB-TAB 2: FILE MẪU SLIDE / WORD */}
                  {templateSubTab === 'file' && (
                    <div className="space-y-3 pt-1 animate-in fade-in duration-150">
                      {templateFile ? (
                        <div className="flex items-center justify-between p-3 rounded-xl border border-orange-500/30 bg-orange-500/5">
                          <div className="flex items-center gap-2.5">
                            <Presentation className="w-5 h-5 text-orange-500" />
                            <div>
                              <p className="text-xs font-semibold text-primary">{templateFile.name}</p>
                              <p className="text-[11px] text-muted-foreground">
                                {templateAnalysis?.file_type === 'docx'
                                  ? `Word DOCX: ${templateAnalysis.paragraph_count || 0} đoạn, ${templateAnalysis.table_count || 0} bảng`
                                  : (templateAnalysis?.slide_count
                                      ? `${templateAnalysis.slide_count} slides layout phát hiện`
                                      : 'Đã sẵn sàng Smart Clone & Fill')}
                              </p>
                            </div>
                          </div>
                          <button
                            type="button"
                            onClick={handleRemoveTemplate}
                            className="p-1.5 rounded-lg text-muted-foreground hover:text-red-500 hover:bg-subtle transition-colors"
                          >
                            <Trash2 className="w-4 h-4" />
                          </button>
                        </div>
                      ) : (
                        <label className="flex flex-col items-center justify-center p-4 border-2 border-dashed border-border hover:border-orange-500/50 rounded-xl cursor-pointer bg-surface/50 hover:bg-orange-500/5 transition-all text-center">
                          <Upload className="w-5 h-5 text-muted-foreground mb-1" />
                          <span className="text-xs font-medium text-primary">
                            {uploadingTemplate ? 'Đang phân tích layout...' : 'Kéo thả hoặc tải lên file mẫu (.pptx, .docx, .txt, .md)'}
                          </span>
                          <span className="text-[10px] text-muted-foreground mt-0.5">
                            Hỗ trợ Slide PowerPoint, Báo cáo Word có logo/bảng biểu, hoặc file Text/Markdown
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
                </div>

                {/* 4. AI Provider & Generate Action */}
                <div className="p-4 rounded-xl bg-canvas border border-border flex flex-col sm:flex-row items-center justify-between gap-3">
                  <div className="w-full sm:w-auto">
                    <ProviderModelSelector
                      providers={providers}
                      selectedProvider={selectedProvider}
                      selectedModel={selectedModel}
                      onChangeProvider={setSelectedProvider}
                      onChangeModel={setSelectedModel}
                    />
                  </div>

                  <Button
                    type="button"
                    onClick={handleGenerateReport}
                    disabled={generating}
                    className="w-full sm:w-auto px-6 py-2.5 bg-blue-600 hover:bg-blue-700 text-white font-semibold text-xs shadow-md shadow-blue-500/20 flex items-center justify-center gap-2"
                  >
                    {generating ? (
                      <>
                        <RefreshCw className="w-4 h-4 animate-spin" />
                        Đang tạo báo cáo Keigo...
                      </>
                    ) : (
                      <>
                        <Sparkles className="w-4 h-4" />
                        Tạo Báo Cáo Thông Minh
                      </>
                    )}
                  </Button>
                </div>
              </div>

              {/* RIGHT COLUMN: Output & Multi-Channel Export (5 cols) */}
              <div className="lg:col-span-5 flex flex-col h-full space-y-4">
                {generatedReport ? (
                  <div className="flex-1 flex flex-col rounded-xl border border-border bg-canvas overflow-hidden">
                    {/* Channel Selector Header */}
                    <div className="flex items-center justify-between px-4 py-2.5 border-b border-border bg-subtle/50">
                      <div className="flex items-center gap-1">
                        <button
                          type="button"
                          onClick={() => setOutputChannelTab('email')}
                          className={`px-2.5 py-1 text-xs font-medium rounded-lg transition-colors flex items-center gap-1 ${
                            outputChannelTab === 'email'
                              ? 'bg-blue-600 text-white'
                              : 'text-muted-foreground hover:text-primary hover:bg-subtle'
                          }`}
                        >
                          <Mail className="w-3.5 h-3.5" />
                          Outlook/Gmail
                        </button>
                        <button
                          type="button"
                          onClick={() => setOutputChannelTab('chatwork')}
                          className={`px-2.5 py-1 text-xs font-medium rounded-lg transition-colors flex items-center gap-1 ${
                            outputChannelTab === 'chatwork'
                              ? 'bg-red-600 text-white'
                              : 'text-muted-foreground hover:text-primary hover:bg-subtle'
                          }`}
                        >
                          <MessageSquare className="w-3.5 h-3.5" />
                          Chatwork
                        </button>
                        <button
                          type="button"
                          onClick={() => setOutputChannelTab('slack')}
                          className={`px-2.5 py-1 text-xs font-medium rounded-lg transition-colors flex items-center gap-1 ${
                            outputChannelTab === 'slack'
                              ? 'bg-emerald-600 text-white'
                              : 'text-muted-foreground hover:text-primary hover:bg-subtle'
                          }`}
                        >
                          <Send className="w-3.5 h-3.5" />
                          Slack/Teams
                        </button>
                        <button
                          type="button"
                          onClick={() => setOutputChannelTab('vietnamese')}
                          className={`px-2.5 py-1 text-xs font-medium rounded-lg transition-colors flex items-center gap-1 ${
                            outputChannelTab === 'vietnamese'
                              ? 'bg-purple-600 text-white'
                              : 'text-muted-foreground hover:text-primary hover:bg-subtle'
                          }`}
                        >
                          🇻🇳 Đối chiếu
                        </button>
                      </div>

                      {/* Copy Action Button */}
                      {outputChannelTab === 'email' && (
                        <button
                          type="button"
                          onClick={handleCopyRichText}
                          className="px-2.5 py-1 text-xs font-semibold rounded-lg bg-blue-500/10 text-blue-500 hover:bg-blue-500/20 border border-blue-500/20 flex items-center gap-1 transition-all"
                        >
                          {copiedType === 'email' ? <Check className="w-3.5 h-3.5" /> : <Copy className="w-3.5 h-3.5" />}
                          Copy Rich Text
                        </button>
                      )}
                      {outputChannelTab === 'chatwork' && (
                        <button
                          type="button"
                          onClick={() => handleCopyText(generatedReport.content_chatwork, 'cw', 'Chatwork')}
                          className="px-2.5 py-1 text-xs font-semibold rounded-lg bg-red-500/10 text-red-500 hover:bg-red-500/20 border border-red-500/20 flex items-center gap-1 transition-all"
                        >
                          {copiedType === 'cw' ? <Check className="w-3.5 h-3.5" /> : <Copy className="w-3.5 h-3.5" />}
                          Copy [info]
                        </button>
                      )}
                      {outputChannelTab === 'slack' && (
                        <button
                          type="button"
                          onClick={() => handleCopyText(generatedReport.content_slack, 'slack', 'Slack')}
                          className="px-2.5 py-1 text-xs font-semibold rounded-lg bg-emerald-500/10 text-emerald-500 hover:bg-emerald-500/20 border border-emerald-500/20 flex items-center gap-1 transition-all"
                        >
                          {copiedType === 'slack' ? <Check className="w-3.5 h-3.5" /> : <Copy className="w-3.5 h-3.5" />}
                          Copy Slack
                        </button>
                      )}
                      {outputChannelTab === 'vietnamese' && (
                        <button
                          type="button"
                          onClick={() => handleCopyText(generatedReport.content_vietnamese_preview || '', 'vi', 'Tiếng Việt')}
                          className="px-2.5 py-1 text-xs font-semibold rounded-lg bg-purple-500/10 text-purple-500 hover:bg-purple-500/20 border border-purple-500/20 flex items-center gap-1 transition-all"
                        >
                          {copiedType === 'vi' ? <Check className="w-3.5 h-3.5" /> : <Copy className="w-3.5 h-3.5" />}
                          Copy
                        </button>
                      )}
                    </div>

                    {/* Preview Content Area */}
                    <div className="flex-1 p-4 overflow-y-auto max-h-[460px] text-xs font-mono leading-relaxed bg-surface/50">
                      {outputChannelTab === 'email' && (
                        <div className="space-y-3 font-sans">
                          <div className="p-3 rounded-lg bg-blue-500/5 border border-blue-500/15 text-[11px] text-blue-600 dark:text-blue-400">
                            💡 <strong>Mẹo:</strong> Nút "Copy Rich Text" cho phép dán trực tiếp vào Outlook hoặc Gmail mà không mất định dạng in đậm, gạch đầu dòng và tiêu đề.
                          </div>
                          <div 
                            className="p-3 rounded-lg bg-canvas border border-border"
                            dangerouslySetInnerHTML={{ __html: generatedReport.content_html || '' }} 
                          />
                        </div>
                      )}

                      {outputChannelTab === 'chatwork' && (
                        <pre className="whitespace-pre-wrap text-muted-foreground p-3 rounded-lg bg-canvas border border-border">
                          {generatedReport.content_chatwork}
                        </pre>
                      )}

                      {outputChannelTab === 'slack' && (
                        <pre className="whitespace-pre-wrap text-muted-foreground p-3 rounded-lg bg-canvas border border-border">
                          {generatedReport.content_slack}
                        </pre>
                      )}

                      {outputChannelTab === 'vietnamese' && (
                        <div className="p-3 rounded-lg bg-canvas border border-border font-sans text-primary whitespace-pre-wrap">
                          {generatedReport.content_vietnamese_preview || 'Không có bản dịch tóm tắt tiếng Việt.'}
                        </div>
                      )}
                    </div>

                    {/* File Downloads Bar */}
                    <div className="p-3 border-t border-border bg-subtle/30 flex items-center justify-between gap-2 flex-wrap">
                      <span className="text-[11px] font-semibold text-muted-foreground">Tải file báo cáo:</span>
                      <div className="flex items-center gap-2">
                        <a
                          href={apiClient.getReportExportUrl(generatedReport.id, 'pptx')}
                          download
                          className="px-2.5 py-1 text-xs font-medium rounded-lg bg-orange-500/10 text-orange-500 hover:bg-orange-500/20 border border-orange-500/20 flex items-center gap-1 transition-all"
                        >
                          <Presentation className="w-3.5 h-3.5" />
                          Slide (.pptx)
                        </a>

                        <a
                          href={apiClient.getReportExportUrl(generatedReport.id, 'docx')}
                          download
                          className="px-2.5 py-1 text-xs font-medium rounded-lg bg-blue-500/10 text-blue-500 hover:bg-blue-500/20 border border-blue-500/20 flex items-center gap-1 transition-all"
                        >
                          <FileText className="w-3.5 h-3.5" />
                          Word (.docx)
                        </a>

                        <a
                          href={apiClient.getReportExportUrl(generatedReport.id, 'xlsx')}
                          download
                          className="px-2.5 py-1 text-xs font-medium rounded-lg bg-emerald-500/10 text-emerald-500 hover:bg-emerald-500/20 border border-emerald-500/20 flex items-center gap-1 transition-all"
                        >
                          <FileSpreadsheet className="w-3.5 h-3.5" />
                          Excel (.xlsx)
                        </a>
                      </div>
                    </div>
                  </div>
                ) : (
                  <div className="flex-1 flex flex-col items-center justify-center p-8 rounded-xl border border-dashed border-border bg-canvas/50 text-center">
                    <div className="p-4 rounded-2xl bg-blue-500/5 text-blue-500 mb-3 border border-blue-500/10">
                      <Sparkles className="w-8 h-8" />
                    </div>
                    <h3 className="text-sm font-bold text-primary mb-1">Báo cáo sẽ hiển thị tại đây</h3>
                    <p className="text-xs text-muted-foreground max-w-xs leading-relaxed">
                      Nhập danh sách công việc ở cột bên trái và bấm <strong>"Tạo Báo Cáo Thông Minh"</strong> để sinh báo cáo đa kênh chuẩn Business Keigo.
                    </p>
                  </div>
                )}
              </div>
            </div>
          ) : (
            /* HISTORY TAB */
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-muted-foreground">
                  Danh sách báo cáo đã tạo cho dự án ({reportHistory.length})
                </span>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={loadHistory}
                  className="text-xs flex items-center gap-1.5"
                >
                  <RefreshCw className="w-3.5 h-3.5" />
                  Làm mới
                </Button>
              </div>

              {loadingHistory ? (
                <div className="flex items-center justify-center py-12 text-xs text-muted-foreground">
                  <RefreshCw className="w-4 h-4 animate-spin mr-2 text-blue-500" />
                  Đang tải lịch sử...
                </div>
              ) : reportHistory.length === 0 ? (
                <div className="text-center py-12 text-xs text-muted-foreground">
                  Chưa có báo cáo nào được tạo trong dự án này.
                </div>
              ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  {reportHistory.map((rep) => (
                    <div
                      key={rep.id}
                      className="p-4 rounded-xl border border-border bg-canvas hover:border-blue-500/40 transition-all space-y-2.5"
                    >
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <Badge variant="outline" className="text-[10px] uppercase font-bold text-blue-500 border-blue-500/30">
                            {rep.report_type === 'client_nippo' ? '日報 (Ngày)' : rep.report_type === 'client_shuho' ? '週報 (Tuần)' : 'Standup'}
                          </Badge>
                          <span className="text-xs text-muted-foreground">{rep.report_date}</span>
                        </div>
                        <div className="flex items-center gap-1">
                          <button
                            type="button"
                            onClick={() => {
                              setGeneratedReport(rep);
                              setActiveMainTab('create');
                              toast.info('Đã tải báo cáo', 'Bạn có thể xem lại và sao chép ở tab Soạn Báo Cáo.');
                            }}
                            className="p-1 rounded text-muted-foreground hover:text-blue-500 hover:bg-subtle"
                            title="Mở báo cáo"
                          >
                            <Eye className="w-4 h-4" />
                          </button>
                          <button
                            type="button"
                            onClick={() => handleDeleteHistory(rep.id)}
                            className="p-1 rounded text-muted-foreground hover:text-red-500 hover:bg-subtle"
                            title="Xóa"
                          >
                            <Trash2 className="w-4 h-4" />
                          </button>
                        </div>
                      </div>

                      <h4 className="text-xs font-bold text-primary truncate">{rep.title}</h4>
                      <p className="text-[11px] text-muted-foreground line-clamp-2">
                        {rep.content_vietnamese_preview || rep.content_markdown?.slice(0, 100)}
                      </p>

                      <div className="flex items-center gap-2 pt-2 border-t border-border/50 text-[10px]">
                        <a
                          href={apiClient.getReportExportUrl(rep.id, 'pptx')}
                          className="text-orange-500 hover:underline flex items-center gap-0.5"
                        >
                          <Presentation className="w-3 h-3" /> Slide
                        </a>
                        <span className="text-muted-foreground">•</span>
                        <a
                          href={apiClient.getReportExportUrl(rep.id, 'docx')}
                          className="text-blue-500 hover:underline flex items-center gap-0.5"
                        >
                          <FileText className="w-3 h-3" /> Word
                        </a>
                        <span className="text-muted-foreground">•</span>
                        <a
                          href={apiClient.getReportExportUrl(rep.id, 'xlsx')}
                          className="text-emerald-500 hover:underline flex items-center gap-0.5"
                        >
                          <FileSpreadsheet className="w-3 h-3" /> Excel
                        </a>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
