import React, { useState, useEffect, useRef } from 'react';
import {
  UploadCloud,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  Play,
  Pause,
  RotateCcw,
  Download,
  Trash2,
  Settings,
  Eye,
  RefreshCw,
  Clock,
  Sparkles,
  Search,
  Filter,
  Layers,
  ChevronRight,
  AlertCircle,
  Folder,
  FolderOpen,
  ArrowRightLeft,
  ArrowRight,
  Languages,
  ImageIcon,
  Edit3,
  X
} from 'lucide-react';
import { apiClient } from '../api/client';
import { Project, ProviderInfo, DocumentItem, DocumentJob, DocumentSegment, DocumentIssue } from '../types';
import { useToast } from '../context/ToastContext';
import { FileFormatIcon } from '../components/common/FileFormatIcon';
import { useConfirm } from '../context/ConfirmDialogContext';
import { DocumentListSkeleton } from '../components/skeletons/DocumentListSkeleton';
import { ProviderModelSelector } from '../components/ProviderModelSelector';
import { getSavedProvider, getSavedModel, resolveHealthyModel } from '../utils/aiPreferences';
import { PageHeader, Card, CardHeader, CardTitle, CardContent, Button, Badge, Modal, EmptyState, Select } from '../components/ui';

interface DocumentsPageProps {
  activeProject: Project | null;
  projects: Project[];
}

export const DocumentsPage: React.FC<DocumentsPageProps> = ({ activeProject, projects }) => {
  const toast = useToast();
  const confirm = useConfirm();

  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [selectedFormatFilter, setSelectedFormatFilter] = useState<'all' | 'docx' | 'xlsx' | 'pptx' | 'pdf'>('all');
  const [docSearchQuery, setDocSearchQuery] = useState('');
  const [providers, setProviders] = useState<ProviderInfo[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);

  const formatCounts = {
    all: documents.length,
    docx: documents.filter(d => d.file_type === 'docx').length,
    xlsx: documents.filter(d => d.file_type === 'xlsx').length,
    pptx: documents.filter(d => d.file_type === 'pptx').length,
    pdf: documents.filter(d => d.file_type === 'pdf').length,
  };

  const isFiltering = selectedFormatFilter !== 'all' || docSearchQuery.trim().length > 0;

  const filteredDocuments = documents.filter(doc => {
    if (selectedFormatFilter !== 'all' && doc.file_type !== selectedFormatFilter) {
      return false;
    }
    if (docSearchQuery.trim()) {
      const q = docSearchQuery.trim().toLowerCase();
      if (!doc.filename.toLowerCase().includes(q)) {
        return false;
      }
    }
    return true;
  });

  // Selected file for translation configuration modal
  const [configDoc, setConfigDoc] = useState<DocumentItem | null>(null);
  const [sourceLang, setSourceLang] = useState<string>('auto');
  const [targetLang, setTargetLang] = useState('vi');
  const [targetFilename, setTargetFilename] = useState<string>('');
  const [isFilenameEdited, setIsFilenameEdited] = useState<boolean>(false);

  const computeDefaultFilename = (originalName: string, tgtLang: string) => {
    const lastDot = originalName.lastIndexOf('.');
    if (lastDot > 0) {
      const stem = originalName.substring(0, lastDot);
      const ext = originalName.substring(lastDot);
      return `${stem}_${tgtLang.toUpperCase()}${ext}`;
    }
    return `${originalName}_${tgtLang.toUpperCase()}`;
  };
  const [selectedProjectId, setSelectedProjectId] = useState<string>(activeProject?.id || '');
  const [style, setStyle] = useState('Auto');
  const [selectedProvider, setSelectedProvider] = useState<string>(() => getSavedProvider('gemini'));
  const [selectedModel, setSelectedModel] = useState<string>(() => getSavedModel('gemini-3.7-flash'));
  const [translateNotes, setTranslateNotes] = useState(true);
  const [useOcr, setUseOcr] = useState(true);
  const [translateImages, setTranslateImages] = useState(true);
  const [ocrEngine, setOcrEngine] = useState<'paddleocr' | 'gemini_vision'>('paddleocr');
  const [translateSheetNames, setTranslateSheetNames] = useState<boolean>(true);
  const [translateTabTitles, setTranslateTabTitles] = useState<boolean>(true);
  const [selectedSheets, setSelectedSheets] = useState<string[]>([]);
  const STORAGE_KEY = 'at_last_output_dir';
  const [customOutputDir, setCustomOutputDir] = useState<string>(
    () => localStorage.getItem(STORAGE_KEY) || ''
  );
  const [isBrowsingFolder, setIsBrowsingFolder] = useState<boolean>(false);
  const [commonPaths, setCommonPaths] = useState<{
    desktop: string;
    downloads: string;
    documents: string;
    default_output: string;
  } | null>(null);

  // Live Tracking Job
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [jobProgress, setJobProgress] = useState<any | null>(null);

  // Segment Review Modal
  const [reviewDoc, setReviewDoc] = useState<DocumentItem | null>(null);
  const [reviewJob, setReviewJob] = useState<DocumentJob | null>(null);
  const [segments, setSegments] = useState<DocumentSegment[]>([]);
  const [issues, setIssues] = useState<DocumentIssue[]>([]);
  const [editingSegmentId, setEditingSegmentId] = useState<string | null>(null);
  const [editingText, setEditingText] = useState('');
  const [isRegenerating, setIsRegenerating] = useState<string | null>(null);
  const [segmentSearch, setSegmentSearch] = useState('');
  const [segmentFilter, setSegmentFilter] = useState<'all' | 'translated' | 'failed' | 'issues'>('all');
  const [isDeletingAll, setIsDeletingAll] = useState(false);

  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    loadDocuments();
    loadProviders();
  }, [activeProject]);

  useEffect(() => {
    if (activeProject) {
      setSelectedProjectId(activeProject.id);
    }
  }, [activeProject]);

  // Polling for active job progress
  useEffect(() => {
    if (!activeJobId) return;

    const pollInterval = setInterval(async () => {
      try {
        const prog = await apiClient.getJobProgress(activeJobId);
        setJobProgress(prog);

        if (['completed', 'partially_completed', 'failed', 'cancelled'].includes(prog.status)) {
          clearInterval(pollInterval);
          loadDocuments();
        }
      } catch (err) {
        console.error('Failed to poll job progress:', err);
      }
    }, 1500);

    return () => clearInterval(pollInterval);
  }, [activeJobId]);

  const loadDocuments = async () => {
    setIsLoading(true);
    try {
      const data = await apiClient.getDocuments(activeProject?.id);
      setDocuments(data);

      const runningDoc = data.find(d => d.active_job && ['queued', 'analyzing', 'segmenting', 'translating', 'qa', 'rendering'].includes(d.active_job.status));
      if (runningDoc && runningDoc.active_job) {
        setActiveJobId(runningDoc.active_job.id);
      } else {
        setActiveJobId(null);
        setJobProgress(null);
      }
    } catch (e) {
      console.error('Failed to load documents:', e);
    } finally {
      setIsLoading(false);
    }
  };

  const loadProviders = async () => {
    try {
      const provs = await apiClient.getProviders();
      setProviders(provs);
      const healthy = resolveHealthyModel(provs);
      setSelectedProvider(healthy.provider);
      setSelectedModel(healthy.model);
    } catch (e) {
      console.error('Failed to load providers:', e);
    }
  };

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setIsUploading(true);
    setUploadError(null);

    try {
      const doc = await apiClient.uploadDocument(file, activeProject?.id);
      await loadDocuments();
      toast.success(`Tải lên thành công: ${doc.filename}`, 'Upload Document');
      openTranslateConfig(doc);
    } catch (err: any) {
      const msg = err.response?.data?.detail || 'Failed to upload document';
      setUploadError(msg);
      toast.error(msg, 'Upload Failed');
    } finally {
      setIsUploading(false);
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
    }
  };

  const handleDelete = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    const ok = await confirm({
      title: 'Xóa tài liệu',
      message: 'Bạn có chắc chắn muốn xóa tài liệu này và toàn bộ các tác vụ dịch liên quan? Thao tác này không thể hoàn tác.',
      isDestructive: true,
      confirmText: 'Xóa tài liệu',
      cancelText: 'Hủy'
    });
    if (!ok) return;

    try {
      await apiClient.deleteDocument(id);
      setDocuments(docs => docs.filter(d => d.id !== id));
      if (configDoc?.id === id) setConfigDoc(null);
      if (reviewDoc?.id === id) setReviewDoc(null);
      toast.success('Đã xóa tài liệu thành công');
    } catch (err: any) {
      toast.error(err.response?.data?.detail || 'Failed to delete document');
    }
  };

  const handleDeleteAll = async () => {
    const targetDocs = isFiltering ? filteredDocuments : documents;
    if (targetDocs.length === 0) return;

    const count = targetDocs.length;
    const ok = await confirm({
      title: isFiltering ? `Xóa ${count} tài liệu đang lọc` : `Xóa tất cả (${count}) tài liệu`,
      message: isFiltering
        ? `Bạn có chắc muốn xóa vĩnh viễn ${count} tài liệu đang hiển thị theo bộ lọc? Thao tác này không thể hoàn tác.`
        : `Bạn có chắc muốn xóa TOÀN BỘ ${count} tài liệu trong danh sách? Toàn bộ file gốc, segments và file dịch sẽ bị xóa. Thao tác này không thể hoàn tác.`,
      isDestructive: true,
      confirmText: `Xóa ${count} tài liệu`,
      cancelText: 'Hủy'
    });
    if (!ok) return;

    setIsDeletingAll(true);
    let successCount = 0;
    let failCount = 0;

    for (const doc of targetDocs) {
      try {
        await apiClient.deleteDocument(doc.id);
        successCount++;
      } catch (err) {
        console.error(`Failed to delete document ${doc.id}:`, err);
        failCount++;
      }
    }

    setIsDeletingAll(false);
    await loadDocuments();
    setConfigDoc(null);
    setReviewDoc(null);

    if (failCount === 0) {
      toast.success(`Đã xóa thành công ${successCount} tài liệu`);
    } else {
      toast.warning(`Đã xóa ${successCount} tài liệu, thất bại ${failCount} tài liệu`);
    }
  };

  const openTranslateConfig = (doc: DocumentItem) => {
    setConfigDoc(doc);
    const initialTgt = 'vi';
    setTargetLang(initialTgt);
    setTargetFilename(computeDefaultFilename(doc.filename, initialTgt));
    setIsFilenameEdited(false);

    if (doc.detected_language) {
      setSourceLang(doc.detected_language);
    } else {
      setSourceLang('auto');
    }

    apiClient.getCommonPaths().then(paths => {
      setCommonPaths(paths);
      if (!customOutputDir && paths?.default_output) {
        setCustomOutputDir('');
      }
    }).catch(console.warn);
  };

  const handleSwapLanguages = () => {
    const effectiveSrc = sourceLang === 'auto' ? (configDoc?.detected_language || 'ja') : sourceLang;
    const newTarget = effectiveSrc === 'vi' ? 'ja' : 'vi';
    const newSource = targetLang;
    setSourceLang(newSource);
    setTargetLang(newTarget);
    if (configDoc && !isFilenameEdited) {
      setTargetFilename(computeDefaultFilename(configDoc.filename, newTarget));
    }
  };

  const handleSelectTargetLang = (langId: string) => {
    setTargetLang(langId);
    if (configDoc && !isFilenameEdited) {
      setTargetFilename(computeDefaultFilename(configDoc.filename, langId));
    }
  };

  const startTranslation = async () => {
    if (!configDoc) return;

    try {
      const job = await apiClient.startDocumentTranslation(configDoc.id, {
        source_language: sourceLang,
        target_language: targetLang,
        project_id: selectedProjectId || null,
        style,
        provider: selectedProvider,
        model: selectedModel,
        translate_notes: translateNotes,
        use_ocr: useOcr,
        translate_images: translateImages,
        ocr_mode: ocrEngine,
        translate_sheet_names: translateSheetNames,
        translate_tab_titles: translateTabTitles,
        selected_units: selectedSheets.length > 0 ? selectedSheets : null,
        custom_output_dir: customOutputDir.trim() || undefined,
        target_filename: targetFilename.trim() || undefined
      });

      setActiveJobId(job.id);
      setConfigDoc(null);
      await loadDocuments();
      toast.success(`Đã khởi tạo tiến trình dịch: ${configDoc.filename}`);
    } catch (err: any) {
      toast.error(err.response?.data?.detail || 'Failed to start translation job');
    }
  };

  const handlePauseJob = async () => {
    if (!activeJobId) return;
    await apiClient.pauseJob(activeJobId);
    const prog = await apiClient.getJobProgress(activeJobId);
    setJobProgress(prog);
  };

  const handleResumeJob = async () => {
    if (!activeJobId) return;
    await apiClient.resumeJob(activeJobId);
    const prog = await apiClient.getJobProgress(activeJobId);
    setJobProgress(prog);
  };

  const handleCancelJob = async () => {
    if (!activeJobId) return;
    const ok = await confirm({
      title: 'Hủy tiến trình dịch',
      message: 'Bạn có chắc muốn hủy tiến trình dịch này? Các đoạn văn đã dịch xong vẫn sẽ được lưu trữ.',
      isDestructive: true,
      confirmText: 'Hủy tác vụ'
    });
    if (!ok) return;

    const targetJobId = activeJobId;
    setActiveJobId(null);
    setJobProgress(null);
    try {
      await apiClient.cancelJob(targetJobId);
    } catch (err) {
      console.warn('Cancel job error:', err);
    }
    await loadDocuments();
    toast.info('Đã hủy tiến trình dịch');
  };

  const handleOpenJobFolder = async (jobId: string) => {
    try {
      const res = await apiClient.openJobFolder(jobId);
      toast.success(`Đã mở thư mục: ${res.folder}`);
    } catch (err: any) {
      toast.error(err.response?.data?.detail || 'Không thể mở thư mục trên hệ thống');
    }
  };

  const updateOutputDir = (path: string) => {
    setCustomOutputDir(path);
    if (path) {
      localStorage.setItem(STORAGE_KEY, path);
    } else {
      localStorage.removeItem(STORAGE_KEY);
    }
  };

  const handleBrowseFolder = async () => {
    setIsBrowsingFolder(true);
    try {
      const res = await apiClient.browseDirectory(customOutputDir || localStorage.getItem(STORAGE_KEY) || '');
      if (res && res.success && !res.canceled && res.path) {
        updateOutputDir(res.path);
        toast.success(`Đã chọn thư mục: ${res.path}`);
      } else if (res && res.error) {
        toast.error(res.error);
      }
    } catch (err: any) {
      console.error('Failed to open folder dialog:', err);
      toast.error('Không thể mở hộp thoại chọn thư mục.');
    } finally {
      setIsBrowsingFolder(false);
    }
  };

  const openReviewModal = async (doc: DocumentItem) => {
    if (!doc.active_job) return;
    setReviewDoc(doc);
    setReviewJob(doc.active_job);
    setEditingSegmentId(null);
    setSegmentSearch('');
    setSegmentFilter('all');
    try {
      const [segsRes, issuesRes] = await Promise.all([
        apiClient.getJobSegments(doc.active_job.id, 200, 0),
        apiClient.getJobIssues(doc.active_job.id)
      ]);

      const rawSegs = Array.isArray(segsRes) ? segsRes : (segsRes?.segments || []);
      const normalizedSegs: DocumentSegment[] = rawSegs.map((s: any) => ({
        id: s.id,
        job_id: s.job_id || doc.active_job?.id || '',
        segment_id: s.segment_id || s.id,
        source_text: s.source_text || '',
        target_text: s.target_text !== undefined && s.target_text !== null ? s.target_text : (s.translated_text || ''),
        translatable: s.translatable ?? true,
        unit_name: s.unit_name || s.context_hint || `Segment #${(s.segment_index ?? 0) + 1}`,
        unit_index: s.unit_index || (s.segment_index !== undefined ? s.segment_index + 1 : 1),
        status: s.status || 'translated',
        error_message: s.error_message || null,
        user_edited: Boolean(s.user_edited || s.status === 'user_edited'),
        qa_status: s.qa_status || 'ok',
        qa_issues: s.qa_issues || null
      }));

      setSegments(normalizedSegs);
      setIssues(issuesRes || []);
    } catch (err) {
      console.error('Failed to load review data:', err);
      toast.error('Không thể tải dữ liệu segments để review');
    }
  };

  const handleSaveSegment = async (segmentId: string) => {
    if (!reviewJob) return;
    try {
      await apiClient.updateSegment(reviewJob.id, segmentId, editingText);
      setSegments(prev => prev.map(s => (s.segment_id === segmentId || s.id === segmentId) ? { ...s, target_text: editingText, user_edited: true, status: 'translated' } : s));
      setEditingSegmentId(null);
      toast.success('Đã lưu chỉnh sửa đoạn văn');
    } catch (err) {
      console.error('Failed to update segment:', err);
      toast.error('Không thể cập nhật đoạn văn');
    }
  };

  const handleRegenerateSegment = async (segmentId: string) => {
    if (!reviewJob) return;
    setIsRegenerating(segmentId);
    try {
      const res = await apiClient.regenerateSegment(reviewJob.id, segmentId);
      const updatedText = res.target_text || res.translated_text || '';
      setSegments(prev => prev.map(s => (s.segment_id === segmentId || s.id === segmentId) ? { ...s, target_text: updatedText, status: 'translated', qa_status: 'ok' } : s));
      toast.success('Đã dịch lại đoạn văn');
    } catch (err: any) {
      toast.error(err.response?.data?.detail || 'Failed to regenerate segment');
    } finally {
      setIsRegenerating(null);
    }
  };

  const getFormatIcon = (type: string, name?: string) => {
    return <FileFormatIcon type={type} name={name} size="md" />;
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'completed':
        return (
          <Badge variant="success" size="sm">
            <CheckCircle2 className="w-3 h-3 mr-1" /> Completed
          </Badge>
        );
      case 'partially_completed':
        return (
          <Badge variant="warning" size="sm">
            <AlertTriangle className="w-3 h-3 mr-1" /> With Warnings
          </Badge>
        );
      case 'failed':
        return (
          <Badge variant="danger" size="sm">
            <XCircle className="w-3 h-3 mr-1" /> Failed
          </Badge>
        );
      case 'paused':
        return (
          <Badge variant="neutral" size="sm">
            <Pause className="w-3 h-3 mr-1" /> Paused
          </Badge>
        );
      case 'translating':
      case 'analyzing':
      case 'segmenting':
      case 'rendering':
      case 'qa':
        return (
          <Badge variant="primary" size="sm" className="animate-pulse">
            <RefreshCw className="w-3 h-3 mr-1 animate-spin" /> {status.toUpperCase()}
          </Badge>
        );
      default:
        return (
          <Badge variant="default" size="sm">
            {status}
          </Badge>
        );
    }
  };

  const filteredSegments = segments.filter(seg => {
    if (segmentSearch) {
      const q = segmentSearch.toLowerCase();
      const matchSource = seg.source_text?.toLowerCase().includes(q);
      const matchTarget = (seg.target_text || (seg as any).translated_text)?.toLowerCase().includes(q);
      if (!matchSource && !matchTarget) return false;
    }
    if (segmentFilter === 'translated') return seg.status === 'translated' || seg.user_edited;
    if (segmentFilter === 'failed') return seg.status === 'failed';
    if (segmentFilter === 'issues') return seg.qa_status === 'warning' || seg.qa_status === 'error' || (issues.some(i => i.segment_id === seg.segment_id || i.segment_id === seg.id));
    return true;
  });

  return (
    <div className="flex-1 flex flex-col h-full overflow-hidden bg-canvas">
      {/* Top Header */}
      <div className="p-4 sm:p-6 pb-0 flex-shrink-0">
        <PageHeader
          title="Dịch tài liệu"
          actions={
            <>
              <input
                type="file"
                ref={fileInputRef}
                onChange={handleFileUpload}
                accept=".docx,.xlsx,.pptx,.pdf"
                className="hidden"
              />
              <Button
                variant="primary"
                size="sm"
                onClick={() => fileInputRef.current?.click()}
                disabled={isUploading}
                isLoading={isUploading}
                leftIcon={<UploadCloud className="w-4 h-4" />}
              >
                {isUploading ? 'Đang tải lên...' : 'Tải tài liệu'}
              </Button>
            </>
          }
        />
      </div>

      {/* Main Content Area */}
      <div className="flex-1 overflow-y-auto p-4 sm:p-6 space-y-6">
        {/* Upload Error Banner */}
        {uploadError && (
          <div className="p-3.5 rounded-xl bg-rose-500/10 border border-rose-500/20 text-rose-600 dark:text-rose-400 text-xs flex items-center justify-between">
            <div className="flex items-center gap-2">
              <AlertCircle className="w-4 h-4 text-rose-500 flex-shrink-0" />
              <span>{uploadError}</span>
            </div>
            <button
              type="button"
              onClick={() => setUploadError(null)}
              className="text-text-muted hover:text-text-primary p-1"
            >
              ✕
            </button>
          </div>
        )}

        {/* Failed Job Banner */}
        {jobProgress && jobProgress.status === 'failed' && (
          <div className="bg-rose-500/10 rounded-xl border border-rose-500/30 p-5 relative overflow-hidden">
            <div className="flex items-start justify-between gap-4">
              <div className="flex items-start gap-3">
                <div className="w-9 h-9 rounded-lg bg-rose-500/20 border border-rose-500/30 flex items-center justify-center text-rose-600 dark:text-rose-400 flex-shrink-0 mt-0.5">
                  <XCircle className="w-5 h-5" />
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <h3 className="text-sm font-semibold text-text-primary">
                      Tiến trình dịch tài liệu thất bại (Translation Failed)
                    </h3>
                    <Badge variant="danger" size="sm">FAILED</Badge>
                  </div>
                  <p className="text-xs text-rose-600 dark:text-rose-300 mt-1.5 bg-rose-500/10 p-2.5 rounded-lg border border-rose-500/20 font-mono">
                    {jobProgress.error_message || jobProgress.current_stage || "Lỗi mô hình AI (quá tải hoặc hết hạn ngạch)."}
                  </p>
                  <p className="text-[11px] text-text-secondary mt-2">
                    Hệ thống đã dừng lại an toàn. Bạn có thể đổi sang mô hình khác (ví dụ: Groq hoặc Gemini Flash) và thử lại.
                  </p>
                </div>
              </div>

              <div className="flex items-center gap-2 flex-shrink-0">
                <Button
                  variant="primary"
                  size="sm"
                  onClick={() => {
                    const failedDoc = documents.find(d => d.id === jobProgress.document_id || d.active_job?.id === jobProgress.id);
                    if (failedDoc) openTranslateConfig(failedDoc);
                  }}
                  leftIcon={<RotateCcw className="w-3.5 h-3.5" />}
                >
                  Đổi Model & Thử Lại
                </Button>
                <button
                  type="button"
                  onClick={() => setJobProgress(null)}
                  className="p-1 rounded-md text-text-muted hover:text-text-primary"
                >
                  ✕
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Active Job Progress Widget */}
        {jobProgress && ['queued', 'analyzing', 'segmenting', 'translating', 'qa', 'rendering'].includes(jobProgress.status) && (
          <Card className="p-5 border-primary/40 relative overflow-hidden">
            <div className="absolute top-0 left-0 right-0 h-1 bg-surface-subtle">
              <div
                className="h-full bg-primary transition-all duration-300"
                style={{ width: `${jobProgress.progress_pct}%` }}
              />
            </div>

            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-3">
                <div className="w-9 h-9 rounded-lg bg-primary/10 border border-primary/20 flex items-center justify-center text-primary">
                  <RefreshCw className="w-4 h-4 animate-spin" />
                </div>
                <div>
                  <h3 className="text-sm font-semibold text-text-primary flex items-center gap-2">
                    Translating Document
                    <Badge variant="primary" size="sm">
                      {jobProgress.status.toUpperCase()}
                    </Badge>
                  </h3>
                  <p className="text-xs text-text-secondary mt-0.5">
                    {jobProgress.current_unit && <span className="text-primary font-medium">{jobProgress.current_unit} · </span>}
                    {jobProgress.current_stage ? (
                      <span className="text-primary font-medium">{jobProgress.current_stage}</span>
                    ) : jobProgress.current_item ? (
                      <span>Current: "{jobProgress.current_item}"</span>
                    ) : null}
                  </p>
                </div>
              </div>

              <div className="flex items-center gap-2">
                {jobProgress.status === 'translating' ? (
                  <Button variant="secondary" size="sm" onClick={handlePauseJob} leftIcon={<Pause className="w-3.5 h-3.5" />}>
                    Pause
                  </Button>
                ) : (
                  <Button variant="primary" size="sm" onClick={handleResumeJob} leftIcon={<Play className="w-3.5 h-3.5" />}>
                    Resume
                  </Button>
                )}
                <Button variant="danger" size="sm" onClick={handleCancelJob} leftIcon={<XCircle className="w-3.5 h-3.5" />}>
                  Cancel
                </Button>
              </div>
            </div>

            {/* Progress Metrics */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 pt-3 border-t border-border-subtle text-xs">
              <div>
                <span className="text-text-muted block text-[10px] uppercase font-semibold">Segments Progress</span>
                <span className="text-text-primary font-mono font-medium">
                  {jobProgress.completed_segments ?? 0} / {jobProgress.total_segments ?? 0} ({jobProgress.progress_pct ?? jobProgress.progress_percent ?? 0}%)
                </span>
              </div>
              <div>
                <span className="text-text-muted block text-[10px] uppercase font-semibold">QA Validation</span>
                <span className="text-emerald-600 dark:text-emerald-400 font-mono font-medium">{jobProgress.qa_pct ?? 0}% Checked</span>
              </div>
              <div>
                <span className="text-text-muted block text-[10px] uppercase font-semibold">Pending / Failed</span>
                <span className="text-text-secondary font-mono font-medium">
                  {jobProgress.pending_segments ?? Math.max(0, (jobProgress.total_segments || 0) - (jobProgress.completed_segments || 0) - (jobProgress.failed_segments || 0))} pending · <span className={(jobProgress.failed_segments || 0) > 0 ? "text-rose-500" : "text-text-muted"}>{jobProgress.failed_segments ?? 0} failed</span>
                </span>
              </div>
              <div>
                <span className="text-text-muted block text-[10px] uppercase font-semibold">Elapsed Time</span>
                <span className="text-text-secondary font-mono font-medium flex items-center gap-1">
                  <Clock className="w-3 h-3" /> {jobProgress.elapsed_seconds ?? 0}s
                </span>
              </div>
            </div>
          </Card>
        )}

        {/* Drag & Drop Upload Quick Target */}
        <div
          onClick={() => fileInputRef.current?.click()}
          className="border-2 border-dashed border-border-default hover:border-primary/50 rounded-xl p-8 bg-surface-subtle/50 hover:bg-surface-subtle transition-all cursor-pointer flex flex-col items-center justify-center text-center group"
        >
          <div className="w-12 h-12 rounded-xl bg-surface-elevated border border-border-subtle group-hover:border-primary/30 text-text-muted group-hover:text-primary flex items-center justify-center transition-colors mb-3 shadow-subtle">
            <UploadCloud className="w-6 h-6" />
          </div>
          <h3 className="text-sm font-semibold text-text-primary group-hover:text-primary transition-colors">
            Drop your DOCX, XLSX, PPTX, or PDF document here
          </h3>
          <p className="text-xs text-text-muted mt-1 max-w-md">
            The engine automatically segments text, protects formulas/URLs/code, preserves typography & tables, and translates with context.
          </p>
          <div className="flex items-center gap-3 mt-4 text-[11px] text-text-secondary font-medium flex-wrap justify-center">
            <span className="flex items-center gap-1.5"><FileFormatIcon type="doc" size="xs" /> Word (.docx)</span>
            <span className="flex items-center gap-1.5"><FileFormatIcon type="sheet" size="xs" /> Excel (.xlsx)</span>
            <span className="flex items-center gap-1.5"><FileFormatIcon type="slide" size="xs" /> PowerPoint (.pptx)</span>
            <span className="flex items-center gap-1.5"><FileFormatIcon type="pdf" size="xs" /> PDF + OCR</span>
          </div>
        </div>

        {/* Document Inventory Table */}
        <Card className="overflow-hidden">
          <CardHeader>
            <div className="flex items-center gap-2">
              <CardTitle>
                Document Repository {isFiltering ? `(${filteredDocuments.length}/${documents.length})` : `(${documents.length})`}
              </CardTitle>
              {isFiltering && (
                <Badge variant="primary" size="sm">
                  Đang lọc
                </Badge>
              )}
            </div>
            <div className="flex items-center gap-2">
              {(isFiltering ? filteredDocuments.length > 0 : documents.length > 0) && (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={handleDeleteAll}
                  disabled={isDeletingAll}
                  className="text-rose-600 dark:text-rose-400"
                  leftIcon={<Trash2 className="w-3.5 h-3.5" />}
                >
                  {isDeletingAll
                    ? 'Đang xóa...'
                    : isFiltering
                    ? `Xóa đã lọc (${filteredDocuments.length})`
                    : 'Xóa tất cả'}
                </Button>
              )}
              <button
                type="button"
                onClick={loadDocuments}
                className="p-1.5 rounded-lg text-text-muted hover:text-text-primary hover:bg-surface-hover transition-colors"
                title="Refresh document list"
                aria-label="Refresh document list"
              >
                <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? 'animate-spin' : ''}`} />
              </button>
            </div>
          </CardHeader>

          {/* Sub-Header Toolbar: Format Classification Tabs & Search Input */}
          <div className="px-4 py-2.5 bg-surface-subtle/40 border-b border-border-subtle flex flex-wrap items-center justify-between gap-3">
            {/* Format Filter Tabs */}
            <div className="flex items-center gap-1 overflow-x-auto py-0.5">
              {(
                [
                  { key: 'all', label: 'Tất cả', icon: null },
                  { key: 'docx', label: 'Word', icon: <FileFormatIcon type="doc" size="xs" /> },
                  { key: 'xlsx', label: 'Excel', icon: <FileFormatIcon type="sheet" size="xs" /> },
                  { key: 'pptx', label: 'PowerPoint', icon: <FileFormatIcon type="slide" size="xs" /> },
                  { key: 'pdf', label: 'PDF', icon: <FileFormatIcon type="pdf" size="xs" /> },
                ] as const
              ).map(tab => {
                const count = formatCounts[tab.key];
                const isActive = selectedFormatFilter === tab.key;

                return (
                  <button
                    key={tab.key}
                    type="button"
                    onClick={() => setSelectedFormatFilter(tab.key)}
                    className={`px-2.5 py-1 rounded-lg text-xs font-medium flex items-center gap-1.5 transition-all ${
                      isActive
                        ? 'bg-surface-elevated text-primary border border-border-subtle shadow-subtle'
                        : 'text-text-secondary hover:text-text-primary hover:bg-surface-hover'
                    }`}
                  >
                    {tab.icon}
                    <span>{tab.label}</span>
                    <span
                      className={`px-2 py-0.5 rounded-full text-[10px] font-mono leading-none ${
                        isActive ? 'bg-primary/10 text-primary font-semibold' : 'bg-surface-hover text-text-muted'
                      }`}
                    >
                      {count}
                    </span>
                  </button>
                );
              })}
            </div>

            {/* Search Input Box */}
            <div className="relative flex-1 sm:max-w-xs min-w-[200px]">
              <Search className="w-3.5 h-3.5 text-text-muted absolute left-2.5 top-1/2 -translate-y-1/2 pointer-events-none" />
              <input
                type="text"
                value={docSearchQuery}
                onChange={e => setDocSearchQuery(e.target.value)}
                placeholder="Tìm kiếm theo tên tài liệu..."
                className="w-full pl-8 pr-7 py-1.5 rounded-lg bg-surface border border-border-default focus:border-primary focus:outline-none text-xs text-text-primary placeholder:text-text-muted transition-colors"
              />
              {docSearchQuery && (
                <button
                  type="button"
                  onClick={() => setDocSearchQuery('')}
                  className="absolute right-2 top-1/2 -translate-y-1/2 text-text-muted hover:text-text-primary p-0.5"
                  title="Xóa tìm kiếm"
                >
                  <X className="w-3 h-3" />
                </button>
              )}
            </div>
          </div>

          {isLoading ? (
            <div className="p-4">
              <DocumentListSkeleton count={4} />
            </div>
          ) : documents.length === 0 ? (
            <EmptyState
              icon={<UploadCloud className="w-6 h-6 text-text-muted" />}
              title="No documents uploaded yet"
              description="Upload a DOCX, XLSX, PPTX, or PDF to begin structured document translation."
              action={
                <Button
                  variant="primary"
                  size="sm"
                  onClick={() => fileInputRef.current?.click()}
                  leftIcon={<UploadCloud className="w-4 h-4" />}
                >
                  Upload File
                </Button>
              }
            />
          ) : filteredDocuments.length === 0 ? (
            <div className="p-10 text-center space-y-2.5">
              <Search className="w-8 h-8 text-text-muted mx-auto" />
              <p className="text-text-secondary text-xs font-medium">
                Không tìm thấy tài liệu nào phù hợp với bộ lọc hiện tại.
              </p>
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  setSelectedFormatFilter('all');
                  setDocSearchQuery('');
                }}
              >
                Đặt lại bộ lọc
              </Button>
            </div>
          ) : (
            <div className="divide-y divide-border-subtle">
              {filteredDocuments.map(doc => {
                const job = doc.active_job;
                const hasOutput = job && ['completed', 'partially_completed'].includes(job.status);

                return (
                  <div
                    key={doc.id}
                    className="p-4 hover:bg-surface-hover/50 transition-colors flex items-center justify-between gap-4"
                  >
                    <div className="flex items-center gap-3.5 min-w-0">
                      <div className="w-10 h-10 rounded-lg bg-surface-subtle border border-border-subtle flex items-center justify-center flex-shrink-0 shadow-subtle">
                        {getFormatIcon(doc.file_type, doc.filename)}
                      </div>
                      <div className="min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          <h4 className="text-xs sm:text-sm font-semibold text-text-primary truncate" title={doc.filename}>
                            {doc.filename}
                          </h4>
                          <span className="text-[10px] uppercase font-mono px-1.5 py-0.5 rounded bg-surface-subtle text-text-secondary border border-border-subtle">
                            {doc.file_type}
                          </span>
                          {job && getStatusBadge(job.status)}
                        </div>
                        <div className="flex items-center gap-2.5 text-xs text-text-secondary mt-1 flex-wrap">
                          <span>{(doc.file_size / 1024).toFixed(1)} KB</span>
                          <span>·</span>
                          <span>{doc.unit_count} {doc.unit_label}</span>
                          <span>·</span>
                          <span className="uppercase font-mono text-[10px] bg-surface-subtle px-1.5 py-0.5 rounded border border-border-subtle">
                            {job?.source_language || doc.detected_language || 'auto'} → {job?.target_language || 'vi'}
                          </span>
                          {job && (
                            <>
                              <span>·</span>
                              <span className="text-text-primary font-mono text-[11px]">
                                {job.completed_segments} / {job.total_segments} segments
                              </span>
                            </>
                          )}
                        </div>
                        {job?.error_message && job.status === 'failed' && (
                          <div className="mt-1 text-[11px] text-rose-600 dark:text-rose-400 bg-rose-500/10 px-2.5 py-1 rounded border border-rose-500/20 font-mono flex items-center gap-1.5" title={job.error_message}>
                            <AlertCircle className="w-3.5 h-3.5 flex-shrink-0 text-rose-500" />
                            <span className="truncate">{job.error_message}</span>
                          </div>
                        )}
                      </div>
                    </div>

                    {/* Action Buttons */}
                    <div className="flex items-center gap-2 flex-shrink-0">
                      {job?.status === 'failed' && (
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => openTranslateConfig(doc)}
                          leftIcon={<RotateCcw className="w-3.5 h-3.5" />}
                        >
                          Đổi Model / Thử lại
                        </Button>
                      )}
                      {hasOutput && (
                        <>
                          <a
                            href={apiClient.getDocumentDownloadUrl(job.id)}
                            download
                            className="inline-flex items-center justify-center font-medium rounded-lg text-xs px-2.5 py-1.5 gap-1.5 bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20 transition-colors"
                          >
                            <Download className="w-3.5 h-3.5" />
                            <span>Download</span>
                          </a>
                          <Button
                            variant="secondary"
                            size="sm"
                            onClick={() => handleOpenJobFolder(job.id)}
                            title="Mở thư mục chứa file dịch trên máy tính"
                            leftIcon={<FolderOpen className="w-3.5 h-3.5 text-amber-500" />}
                          >
                            <span className="hidden sm:inline">Mở thư mục</span>
                          </Button>
                        </>
                      )}

                      {job && (
                        <Button
                          variant="secondary"
                          size="sm"
                          onClick={() => openReviewModal(doc)}
                          leftIcon={<Eye className="w-3.5 h-3.5 text-primary" />}
                        >
                          <span className="hidden sm:inline">Review & Edit</span>
                        </Button>
                      )}

                      <Button
                        variant={job ? 'outline' : 'primary'}
                        size="sm"
                        onClick={() => openTranslateConfig(doc)}
                        leftIcon={<Sparkles className="w-3.5 h-3.5" />}
                      >
                        <span>{job ? 'Re-Translate' : 'Translate'}</span>
                      </Button>

                      <button
                        type="button"
                        onClick={(e) => handleDelete(doc.id, e)}
                        className="p-1.5 rounded-lg hover:bg-rose-500/10 text-text-muted hover:text-rose-500 transition-colors"
                        title="Delete document"
                        aria-label="Delete document"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </Card>
      </div>

      {/* Translation Configuration Modal */}
      <Modal
        isOpen={Boolean(configDoc)}
        onClose={() => setConfigDoc(null)}
        title={
          configDoc && (
            <div className="flex items-center gap-2.5">
              <FileFormatIcon type={configDoc.file_type} name={configDoc.filename} size="sm" />
              <div>
                <span className="font-semibold text-text-primary text-sm">Translate Document</span>
                <p className="text-xs text-text-secondary truncate max-w-xs">{configDoc.filename}</p>
              </div>
            </div>
          )
        }
        size="lg"
        footer={
          <>
            <Button variant="secondary" size="sm" onClick={() => setConfigDoc(null)}>
              Cancel
            </Button>
            <Button
              variant="primary"
              size="sm"
              onClick={startTranslation}
              leftIcon={<Sparkles className="w-3.5 h-3.5" />}
            >
              Start Translation Job
            </Button>
          </>
        }
      >
        {configDoc && (
          <div className="space-y-4 text-xs">
            {/* Language Configuration: Source & Target */}
            <div className="p-3.5 bg-surface-subtle rounded-xl border border-border-subtle space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-text-primary font-semibold flex items-center gap-1.5 text-xs">
                  <Languages className="w-4 h-4 text-primary" />
                  Cặp ngôn ngữ dịch thuật (Language Pair)
                </span>
                {configDoc.detected_language && (
                  <Badge variant="primary" size="sm">
                    Tự động phát hiện: {configDoc.detected_language === 'ja' ? '🇯🇵 Tiếng Nhật' : configDoc.detected_language === 'vi' ? '🇻🇳 Tiếng Việt' : '🇬🇧 English'}
                  </Badge>
                )}
              </div>

              <div className="grid grid-cols-1 md:grid-cols-[1fr,auto,1fr] gap-2 items-center">
                {/* Source Language */}
                <div>
                  <label className="block text-[11px] text-text-secondary font-medium mb-1">
                    Ngôn ngữ nguồn (Source)
                  </label>
                  <div className="grid grid-cols-3 gap-1.5">
                    {[
                      { id: 'ja', label: '🇯🇵 Nhật' },
                      { id: 'vi', label: '🇻🇳 Việt' },
                      { id: 'en', label: '🇬🇧 Anh' }
                    ].map(lang => {
                      const isSelected = (sourceLang === lang.id) || (sourceLang === 'auto' && (configDoc.detected_language || 'ja') === lang.id);
                      return (
                        <button
                          key={lang.id}
                          type="button"
                          onClick={() => {
                            setSourceLang(lang.id);
                            if (targetLang === lang.id) {
                              setTargetLang(lang.id === 'vi' ? 'ja' : 'vi');
                            }
                          }}
                          className={`p-2 rounded-lg border text-center transition-all text-xs ${
                            isSelected
                              ? 'bg-primary/10 border-primary text-primary font-semibold shadow-subtle'
                              : 'bg-surface border-border-default text-text-secondary hover:bg-surface-hover'
                          }`}
                        >
                          {lang.label}
                        </button>
                      );
                    })}
                  </div>
                </div>

                {/* Swap Button */}
                <div className="flex items-center justify-center pt-5">
                  <button
                    type="button"
                    onClick={handleSwapLanguages}
                    title="Đảo ngược cặp ngôn ngữ"
                    className="p-2 rounded-lg bg-surface hover:bg-surface-hover border border-border-default text-text-secondary hover:text-primary transition-all active:scale-95 shadow-subtle"
                  >
                    <ArrowRightLeft className="w-4 h-4" />
                  </button>
                </div>

                {/* Target Language */}
                <div>
                  <label className="block text-[11px] text-text-secondary font-medium mb-1">
                    Ngôn ngữ đích (Target)
                  </label>
                  <div className="grid grid-cols-3 gap-1.5">
                    {[
                      { id: 'vi', label: '🇻🇳 Việt' },
                      { id: 'ja', label: '🇯🇵 Nhật' },
                      { id: 'en', label: '🇬🇧 Anh' }
                    ].map(lang => (
                      <button
                        key={lang.id}
                        type="button"
                        onClick={() => {
                          handleSelectTargetLang(lang.id);
                          const currentSrc = sourceLang === 'auto' ? (configDoc.detected_language || 'ja') : sourceLang;
                          if (currentSrc === lang.id) {
                            setSourceLang(lang.id === 'vi' ? 'ja' : 'vi');
                          }
                        }}
                        className={`p-2 rounded-lg border text-center transition-all text-xs ${
                          targetLang === lang.id
                            ? 'bg-emerald-500/10 border-emerald-500 text-emerald-600 dark:text-emerald-400 font-semibold shadow-subtle'
                            : 'bg-surface border-border-default text-text-secondary hover:bg-surface-hover'
                        }`}
                      >
                        {lang.label}
                      </button>
                    ))}
                  </div>
                </div>
              </div>

              {/* Translation Direction Banner */}
              <div className="flex items-center justify-center gap-2 py-1.5 px-3 bg-surface rounded-lg border border-border-subtle text-[11px] text-text-secondary">
                <span className="font-semibold text-primary uppercase font-mono">
                  {sourceLang === 'auto' ? (configDoc.detected_language || 'JA') : sourceLang}
                </span>
                <ArrowRight className="w-3.5 h-3.5 text-text-muted" />
                <span className="font-semibold text-emerald-600 dark:text-emerald-400 uppercase font-mono">
                  {targetLang}
                </span>
              </div>
            </div>

            {/* Project Workspace */}
            <div>
              <label className="block text-text-secondary font-medium mb-1">Không gian dự án</label>
              <Select
                value={selectedProjectId}
                onChange={(val) => setSelectedProjectId(val)}
                size="md"
                className="w-full"
                options={[
                  { value: '', label: '-- Toàn cục (Global) --' },
                  ...projects.map(p => ({
                    value: p.id,
                    label: p.name,
                    sublabel: p.code
                  }))
                ]}
              />
            </div>

            {/* Tone / Style */}
            <div>
              <label className="block text-text-secondary font-medium mb-1">Văn phong</label>
              <div className="grid grid-cols-4 gap-2">
                {[
                  { id: 'Auto', label: 'Tự động' },
                  { id: 'Polite', label: 'Lịch sự' },
                  { id: 'Formal', label: 'Trang trọng' },
                  { id: 'Technical', label: 'Kỹ thuật' }
                ].map(s => (
                  <button
                    key={s.id}
                    type="button"
                    onClick={() => setStyle(s.id)}
                    className={`p-2 rounded-lg border text-center text-xs transition-all cursor-pointer ${
                      style === s.id
                        ? 'bg-primary/10 border-primary text-primary font-semibold shadow-subtle'
                        : 'bg-surface border-border-default text-text-secondary hover:bg-surface-hover'
                    }`}
                  >
                    {s.label}
                  </button>
                ))}
              </div>
            </div>

            {/* AI Provider & Model (Searchable Combobox) */}
            <ProviderModelSelector
              providers={providers}
              selectedProvider={selectedProvider}
              onChangeProvider={setSelectedProvider}
              selectedModel={selectedModel}
              onChangeModel={setSelectedModel}
              allowAutoRouter={false}
              layout="stacked"
            />

            {/* Format-specific configurations */}
            {['docx', 'xlsx', 'pdf', 'pptx'].includes(configDoc.file_type) && (
              <div className="p-3 bg-surface-subtle rounded-xl border border-border-subtle hover:border-primary/40 transition-colors">
                <label className="flex items-start gap-3 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={translateImages}
                    onChange={(e) => setTranslateImages(e.target.checked)}
                    className="mt-0.5 rounded border-border-default text-primary focus:ring-primary"
                  />
                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      <ImageIcon className="w-4 h-4 text-primary" />
                      <span className="text-text-primary font-medium text-xs">
                        Dịch chữ trong hình ảnh (AI Vision & Inpainting)
                      </span>
                    </div>
                    <p className="text-[11px] text-text-muted mt-1 leading-relaxed">
                      Tự động phát hiện sơ đồ kiến trúc, screenshot UI, xóa chữ cũ bằng màu nền và dán chữ dịch bằng font tiếng Nhật/Việt chuẩn.
                    </p>

                    {translateImages && (
                      <div className="mt-2 text-[11px] px-2.5 py-1.5 rounded bg-amber-500/10 border border-amber-500/25 text-amber-700 dark:text-amber-300 flex items-center gap-1.5">
                        <Clock className="w-3.5 h-3.5 flex-shrink-0 text-amber-500" />
                        <span>Lưu ý: Dịch hình ảnh & sơ đồ (OCR) qua AI sẽ chạy từng ảnh một nên sẽ tốn thêm thời gian khi xuất file PDF/PPTX.</span>
                      </div>
                    )}

                    {translateImages && (
                      <div className="mt-2.5 pt-2 border-t border-border-subtle flex flex-col gap-1.5">
                        <span className="text-[10px] uppercase tracking-wider font-semibold text-text-muted">
                          Công nghệ OCR bóc tách chữ trong ảnh:
                        </span>
                        <div className="grid grid-cols-2 gap-1.5">
                          <button
                            type="button"
                            onClick={(e) => { e.preventDefault(); setOcrEngine('paddleocr'); }}
                            className={`px-2.5 py-1.5 rounded text-[11px] text-left border transition-all ${
                              ocrEngine === 'paddleocr'
                                ? 'bg-primary/10 border-primary text-primary font-medium shadow-subtle'
                                : 'bg-surface border-border-default text-text-secondary hover:bg-surface-hover'
                            }`}
                          >
                            <div className="font-semibold flex items-center gap-1">
                              <span>⚡ PaddleOCR (Local)</span>
                            </div>
                            <div className="text-[10px] text-text-muted">Chuyên dụng tiếng Nhật & Việt</div>
                          </button>

                          <button
                            type="button"
                            onClick={(e) => { e.preventDefault(); setOcrEngine('gemini_vision'); }}
                            className={`px-2.5 py-1.5 rounded text-[11px] text-left border transition-all ${
                              ocrEngine === 'gemini_vision'
                                ? 'bg-primary/10 border-primary text-primary font-medium shadow-subtle'
                                : 'bg-surface border-border-default text-text-secondary hover:bg-surface-hover'
                            }`}
                          >
                            <div className="font-semibold text-text-primary flex items-center gap-1">
                              <span>☁️ Gemini Vision</span>
                            </div>
                            <div className="text-[10px] text-text-muted">Cloud Multi-modal API</div>
                          </button>
                        </div>
                      </div>
                    )}
                  </div>
                </label>
              </div>
            )}

            {configDoc.file_type === 'xlsx' && (
              <div className="p-3 bg-surface-subtle rounded-xl border border-border-subtle">
                <label className="flex items-start gap-2.5 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={translateSheetNames}
                    onChange={(e) => setTranslateSheetNames(e.target.checked)}
                    className="mt-0.5 rounded border-border-default text-emerald-500 focus:ring-emerald-400"
                  />
                  <div>
                    <span className="text-text-primary font-medium text-xs">
                      Dịch tên các Trang tính / Sheet (Translate Sheet Names)
                    </span>
                    <p className="text-[11px] text-text-muted mt-0.5 leading-relaxed">
                      Tự động dịch tên các sheet/trang tính trên thanh tab của bảng tính sang ngôn ngữ đích.
                    </p>
                  </div>
                </label>
              </div>
            )}

            {configDoc.file_type === 'docx' && (
              <div className="p-3 bg-surface-subtle rounded-xl border border-border-subtle">
                <label className="flex items-start gap-2.5 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={translateTabTitles}
                    onChange={(e) => setTranslateTabTitles(e.target.checked)}
                    className="mt-0.5 rounded border-border-default text-primary focus:ring-primary"
                  />
                  <div>
                    <span className="text-text-primary font-medium text-xs">
                      Dịch tiêu đề các Thẻ tài liệu (Translate Tab Titles)
                    </span>
                    <p className="text-[11px] text-text-muted mt-0.5 leading-relaxed">
                      Tự động dịch tên các thẻ trên thanh tab bar sang ngôn ngữ đích.
                    </p>
                  </div>
                </label>
              </div>
            )}

            {configDoc.file_type === 'pptx' && (
              <div className="p-3 bg-surface-subtle rounded-xl border border-border-subtle">
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={translateNotes}
                    onChange={(e) => setTranslateNotes(e.target.checked)}
                    className="rounded border-border-default text-primary focus:ring-primary"
                  />
                  <span className="text-text-primary font-medium">Translate Speaker Notes in Slides</span>
                </label>
              </div>
            )}

            {configDoc.file_type === 'pdf' && (
              <div className="p-3 bg-surface-subtle rounded-xl border border-border-subtle">
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={useOcr}
                    onChange={(e) => setUseOcr(e.target.checked)}
                    className="rounded border-border-default text-primary focus:ring-primary"
                  />
                  <span className="text-text-primary font-medium">Use OCR engine for scanned / image pages</span>
                </label>
              </div>
            )}

            {/* Output Filename (Customizable) */}
            <div className="p-3 bg-surface-subtle rounded-xl border border-border-subtle space-y-2">
              <div className="flex items-center justify-between">
                <label className="text-xs font-semibold text-text-primary flex items-center gap-1.5">
                  <Edit3 className="w-3.5 h-3.5 text-primary" />
                  <span>Tên tệp sau khi dịch (Output Filename)</span>
                </label>
                {isFilenameEdited && (
                  <button
                    type="button"
                    onClick={() => {
                      if (configDoc) {
                        setTargetFilename(computeDefaultFilename(configDoc.filename, targetLang));
                        setIsFilenameEdited(false);
                      }
                    }}
                    className="text-[10px] text-primary hover:underline flex items-center gap-1 font-medium transition-colors"
                    title="Khôi phục lại tên gợi ý ban đầu"
                  >
                    <RotateCcw className="w-3 h-3" />
                    <span>Đặt lại mặc định</span>
                  </button>
                )}
              </div>
              <input
                type="text"
                value={targetFilename}
                onChange={(e) => {
                  setTargetFilename(e.target.value);
                  setIsFilenameEdited(true);
                }}
                placeholder={`Gợi ý: ${configDoc ? computeDefaultFilename(configDoc.filename, targetLang) : ''}`}
                className="w-full bg-surface border border-border-default rounded-lg px-3 py-2 text-xs text-text-primary placeholder:text-text-muted focus:outline-none focus:border-primary font-mono"
              />
              <p className="text-[10px] text-text-muted">
                Mặc định sẽ gắn mã ngôn ngữ <code className="text-primary bg-surface px-1 py-0.5 rounded font-mono">_{targetLang.toUpperCase()}</code> vào tên tệp gốc.
              </p>
            </div>

            {/* Output Directory / Save Location */}
            <div className="p-3 bg-surface-subtle rounded-xl border border-border-subtle space-y-2">
              <div className="flex items-center justify-between">
                <label className="text-xs font-semibold text-text-primary flex items-center gap-1.5">
                  <Folder className="w-3.5 h-3.5 text-primary" />
                  <span>Đường dẫn thư mục lưu file dịch (Save Location)</span>
                </label>
                <span className="text-[10px] text-text-muted">Tùy chọn</span>
              </div>
              <div className="flex items-center gap-2">
                <div className="relative flex-1">
                  <input
                    type="text"
                    value={customOutputDir}
                    onChange={(e) => updateOutputDir(e.target.value)}
                    placeholder="Mặc định: data/documents/output"
                    className="w-full bg-surface border border-border-default rounded-lg px-3 py-2 text-xs text-text-primary placeholder:text-text-muted focus:outline-none focus:border-primary font-mono pr-7"
                  />
                  {customOutputDir && (
                    <button
                      type="button"
                      onClick={() => updateOutputDir('')}
                      className="absolute right-2.5 top-2 text-text-muted hover:text-text-primary text-xs"
                      title="Xóa để dùng mặc định"
                    >
                      ✕
                    </button>
                  )}
                </div>
                <Button
                  variant="primary"
                  size="sm"
                  onClick={handleBrowseFolder}
                  disabled={isBrowsingFolder}
                  leftIcon={<FolderOpen className="w-4 h-4" />}
                >
                  {isBrowsingFolder ? 'Đang chọn...' : 'Chọn thư mục...'}
                </Button>
              </div>
              <div className="flex items-center gap-1.5 pt-0.5 flex-wrap">
                <span className="text-[10px] text-text-muted">Gợi ý nhanh:</span>
                <button
                  type="button"
                  onClick={() => updateOutputDir('')}
                  className={`text-[10px] px-2 py-0.5 rounded border transition-colors ${
                    !customOutputDir ? 'bg-primary/10 text-primary border-primary/20' : 'bg-surface text-text-muted border-border-subtle hover:text-text-primary'
                  }`}
                >
                  Mặc định
                </button>
                {commonPaths?.desktop && (
                  <button
                    type="button"
                    onClick={() => updateOutputDir(commonPaths.desktop)}
                    className={`text-[10px] px-2 py-0.5 rounded border transition-colors ${
                      customOutputDir === commonPaths.desktop ? 'bg-primary/10 text-primary border-primary/20' : 'bg-surface text-text-muted border-border-subtle hover:text-text-primary'
                    }`}
                  >
                    Desktop
                  </button>
                )}
                {commonPaths?.downloads && (
                  <button
                    type="button"
                    onClick={() => updateOutputDir(commonPaths.downloads)}
                    className={`text-[10px] px-2 py-0.5 rounded border transition-colors ${
                      customOutputDir === commonPaths.downloads ? 'bg-primary/10 text-primary border-primary/20' : 'bg-surface text-text-muted border-border-subtle hover:text-text-primary'
                    }`}
                  >
                    Downloads
                  </button>
                )}
              </div>
            </div>

            {/* Preservation Guarantees Card */}
            <div className="p-3 bg-surface rounded-xl border border-border-subtle text-[11px] text-text-secondary space-y-1">
              <div className="text-text-primary font-semibold flex items-center gap-1.5">
                <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500" />
                Preservation Guarantee Active:
              </div>
              <p>• Excel formulas (=...) and sheet cross-references are strictly preserved.</p>
              <p>• Inline formatting (bold, color, fonts, hyperlinks) is maintained.</p>
              <p>• URLs, email addresses, and camelCase code tokens are protected.</p>
            </div>
          </div>
        )}
      </Modal>

      {/* Document Review & Segment Inspector Modal */}
      <Modal
        isOpen={Boolean(reviewDoc && reviewJob)}
        onClose={() => setReviewDoc(null)}
        title={
          reviewDoc && reviewJob && (
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 rounded-lg bg-surface-subtle flex items-center justify-center">
                {getFormatIcon(reviewDoc.file_type)}
              </div>
              <div>
                <div className="text-sm font-semibold text-text-primary flex items-center gap-2">
                  <span>Review: {reviewDoc.filename}</span>
                  {getStatusBadge(reviewJob.status)}
                </div>
                <p className="text-xs text-text-muted">
                  {reviewJob.completed_segments} of {reviewJob.total_segments} segments translated · {issues.length} QA issues flagged
                </p>
              </div>
            </div>
          )
        }
        size="5xl"
        footer={
          <div className="w-full flex items-center justify-between text-xs text-text-muted">
            <span>Showing {filteredSegments.length} segments</span>
            <div className="flex items-center gap-2">
              {reviewJob && ['completed', 'partially_completed'].includes(reviewJob.status) && (
                <a
                  href={apiClient.getDocumentDownloadUrl(reviewJob.id)}
                  download
                  className="inline-flex items-center justify-center font-medium rounded-lg text-xs px-3 py-1.5 gap-1.5 bg-emerald-600 hover:bg-emerald-500 text-white transition-colors shadow-sm"
                >
                  <Download className="w-3.5 h-3.5" />
                  <span>Download File</span>
                </a>
              )}
              <Button variant="secondary" size="sm" onClick={() => setReviewDoc(null)}>
                Close Review
              </Button>
            </div>
          </div>
        }
      >
        <div className="space-y-4">
          {/* QA Issues summary banner if any */}
          {issues.length > 0 && (
            <div className="p-3 rounded-lg bg-amber-500/10 border border-amber-500/20 text-xs flex items-center justify-between text-amber-700 dark:text-amber-300">
              <div className="flex items-center gap-2">
                <AlertTriangle className="w-4 h-4 text-amber-500 flex-shrink-0" />
                <span>
                  QA detected <strong>{issues.length}</strong> issues (e.g. text overflow or formatting warning). Inspect flagged segments below.
                </span>
              </div>
              <div className="flex items-center gap-1.5 text-[11px] flex-wrap">
                {issues.slice(0, 2).map((iss, i) => (
                  <Badge key={i} variant="warning" size="sm">
                    {iss.category}: {iss.message}
                  </Badge>
                ))}
              </div>
            </div>
          )}

          {/* Search & Filter Toolbar */}
          <div className="flex items-center justify-between gap-4 flex-wrap">
            <div className="relative flex-1 max-w-sm min-w-[200px]">
              <Search className="w-3.5 h-3.5 absolute left-3 top-2.5 text-text-muted" />
              <input
                type="text"
                value={segmentSearch}
                onChange={(e) => setSegmentSearch(e.target.value)}
                placeholder="Search segments by source or translation..."
                className="w-full bg-surface border border-border-default rounded-lg pl-9 pr-3 py-1.5 text-xs text-text-primary placeholder:text-text-muted focus:outline-none focus:border-primary"
              />
            </div>

            <div className="flex items-center gap-1">
              {(['all', 'translated', 'failed', 'issues'] as const).map(f => (
                <button
                  key={f}
                  onClick={() => setSegmentFilter(f)}
                  className={`px-3 py-1 rounded-md text-xs capitalize transition-colors ${
                    segmentFilter === f
                      ? 'bg-primary/10 text-primary font-semibold border border-primary/20'
                      : 'text-text-secondary hover:text-text-primary hover:bg-surface-hover'
                  }`}
                >
                  {f}
                </button>
              ))}
            </div>
          </div>

          {/* Segments Table */}
          <div className="border border-border-subtle rounded-xl divide-y divide-border-subtle max-h-[55vh] overflow-y-auto">
            {filteredSegments.length === 0 ? (
              <div className="p-12 text-center text-text-muted text-xs">
                {segments.length === 0 ? 'Chưa có dữ liệu phân đoạn cho tài liệu này.' : 'Không có đoạn văn nào khớp với bộ lọc hiện tại.'}
              </div>
            ) : (
              filteredSegments.map(seg => {
                const segId = seg.segment_id || seg.id;
                const isEditing = editingSegmentId === segId;
                const isRegen = isRegenerating === segId;

                return (
                  <div
                    key={seg.id || segId}
                    className="p-3.5 hover:bg-surface-hover/40 transition-colors grid grid-cols-12 gap-4 items-start text-xs"
                  >
                    {/* Location Badge */}
                    <div className="col-span-2">
                      <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-surface-subtle text-text-secondary border border-border-subtle block truncate" title={seg.unit_name || `Unit ${seg.unit_index}`}>
                        {seg.unit_name || `Item ${seg.unit_index}`}
                      </span>
                      <div className="mt-1">
                        {seg.user_edited && (
                          <Badge variant="warning" size="sm">
                            Edited
                          </Badge>
                        )}
                      </div>
                    </div>

                    {/* Source Text */}
                    <div className="col-span-5 text-text-primary leading-relaxed font-sans select-text">
                      {seg.source_text}
                    </div>

                    {/* Target Text / Editor */}
                    <div className="col-span-5 space-y-2">
                      {isEditing ? (
                        <div className="space-y-2">
                          <textarea
                            value={editingText}
                            onChange={(e) => setEditingText(e.target.value)}
                            rows={3}
                            className="w-full bg-surface border border-primary rounded-lg p-2 text-xs text-text-primary focus:outline-none resize-y font-sans"
                          />
                          <div className="flex items-center gap-2">
                            <Button size="sm" variant="primary" onClick={() => handleSaveSegment(segId)}>
                              Save
                            </Button>
                            <Button size="sm" variant="secondary" onClick={() => setEditingSegmentId(null)}>
                              Cancel
                            </Button>
                          </div>
                        </div>
                      ) : (
                        <div className="group relative">
                          <div className="text-emerald-600 dark:text-emerald-400 leading-relaxed select-text min-h-[1.5rem] font-sans">
                            {seg.target_text || <span className="text-text-muted italic">No translation yet</span>}
                          </div>
                          <div className="flex items-center gap-2 mt-2">
                            <button
                              type="button"
                              onClick={() => {
                                setEditingSegmentId(segId);
                                setEditingText(seg.target_text || '');
                              }}
                              className="text-[11px] text-text-muted hover:text-text-primary transition-colors underline"
                            >
                              Edit
                            </button>
                            <span className="text-border-default">·</span>
                            <button
                              type="button"
                              onClick={() => handleRegenerateSegment(segId)}
                              disabled={isRegen}
                              className="text-[11px] text-primary hover:opacity-80 flex items-center gap-1 transition-colors disabled:opacity-50"
                            >
                              <RefreshCw className={`w-3 h-3 ${isRegen ? 'animate-spin' : ''}`} />
                              <span>{isRegen ? 'Regenerating...' : 'Regenerate'}</span>
                            </button>
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>
      </Modal>
    </div>
  );
};
