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
  Edit3
} from 'lucide-react';
import { apiClient } from '../api/client';
import { Project, ProviderInfo, DocumentItem, DocumentJob, DocumentSegment, DocumentIssue } from '../types';
import { useToast } from '../context/ToastContext';
import { FileFormatIcon } from '../components/common/FileFormatIcon';
import { useConfirm } from '../context/ConfirmDialogContext';
import { DocumentListSkeleton } from '../components/skeletons/DocumentListSkeleton';
import { ProviderModelSelector } from '../components/ProviderModelSelector';
import { getSavedProvider, getSavedModel, resolveHealthyModel } from '../utils/aiPreferences';

interface DocumentsPageProps {
  activeProject: Project | null;
  projects: Project[];
}

export const DocumentsPage: React.FC<DocumentsPageProps> = ({ activeProject, projects }) => {
  const toast = useToast();
  const confirm = useConfirm();

  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [providers, setProviders] = useState<ProviderInfo[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);

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
  const [selectedSheets, setSelectedSheets] = useState<string[]>([]);
  const STORAGE_KEY = 'at_last_output_dir';
  const [customOutputDir, setCustomOutputDir] = useState<string>(
    () => localStorage.getItem(STORAGE_KEY) || ''
  );
  const [isBrowsingFolder, setIsBrowsingFolder] = useState<boolean>(false);

  // Live Tracking Job
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [jobProgress, setJobProgress] = useState<any | null>(null);

  // Document Review & Segment Modal
  const [reviewDoc, setReviewDoc] = useState<DocumentItem | null>(null);
  const [reviewJob, setReviewJob] = useState<DocumentJob | null>(null);
  const [segments, setSegments] = useState<DocumentSegment[]>([]);
  const [issues, setIssues] = useState<DocumentIssue[]>([]);
  const [segmentSearch, setSegmentSearch] = useState('');
  const [segmentFilter, setSegmentFilter] = useState<'all' | 'translated' | 'failed' | 'issues'>('all');
  const [isRegenerating, setIsRegenerating] = useState<string | null>(null);
  const [editingSegmentId, setEditingSegmentId] = useState<string | null>(null);
  const [editingText, setEditingText] = useState('');

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
          loadDocuments(); // Refresh document list
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

      // Auto-attach any active job to progress tracker
      const runningDoc = data.find(d => d.active_job && ['queued', 'analyzing', 'segmenting', 'translating', 'qa', 'rendering'].includes(d.active_job.status));
      if (runningDoc && runningDoc.active_job) {
        setActiveJobId(runningDoc.active_job.id);
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
      // Auto open config modal
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
      console.error('Failed to delete document:', err);
      toast.error(err?.response?.data?.detail || 'Failed to delete document');
    }
  };

  const openTranslateConfig = (doc: DocumentItem) => {
    setConfigDoc(doc);
    setSelectedProjectId(doc.project_id || activeProject?.id || '');
    if (doc.file_type === 'xlsx') {
      setSelectedSheets([]);
    }
    const detected = doc.detected_language || 'ja';
    setSourceLang(detected);
    // Smart pair defaults: if detected is vi -> target ja; if ja -> target vi; if en -> target vi
    const defaultTgt = detected === 'vi' ? 'ja' : 'vi';
    setTargetLang(defaultTgt);
    setTargetFilename(computeDefaultFilename(doc.filename, defaultTgt));
    setIsFilenameEdited(false);

    if (providers.length > 0) {
      const healthy = resolveHealthyModel(providers);
      setSelectedProvider(healthy.provider);
      setSelectedModel(healthy.model);
    }

    if (['docx', 'xlsx', 'pdf'].includes(doc.file_type)) {
      setTranslateImages(true);
      setOcrEngine('paddleocr');
    }
  };

  const handleSelectTargetLang = (newTgt: string) => {
    setTargetLang(newTgt);
    if (!isFilenameEdited && configDoc) {
      setTargetFilename(computeDefaultFilename(configDoc.filename, newTgt));
    }
  };

  const handleSwapLanguages = () => {
    const currentSrc = sourceLang === 'auto' ? (configDoc?.detected_language || 'ja') : sourceLang;
    const currentTgt = targetLang;
    setSourceLang(currentTgt);
    setTargetLang(currentSrc);
    if (!isFilenameEdited && configDoc) {
      setTargetFilename(computeDefaultFilename(configDoc.filename, currentSrc));
    }
  };

  const startTranslation = async () => {
    if (!configDoc) return;
    const resolvedSource = sourceLang === 'auto' ? (configDoc.detected_language || 'ja') : sourceLang;
    if (resolvedSource === targetLang) {
      toast.error('Ngôn ngữ nguồn và ngôn ngữ đích không được trùng nhau. Vui lòng chọn cặp ngôn ngữ hợp lệ.');
      return;
    }
    try {
      const job = await apiClient.startDocumentTranslation(configDoc.id, {
        source_language: resolvedSource,
        target_language: targetLang,
        project_id: selectedProjectId || null,
        style,
        provider: selectedProvider,
        model: selectedModel,
        translate_notes: translateNotes,
        use_ocr: useOcr,
        translate_images: translateImages,
        ocr_mode: ocrEngine,
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

    await apiClient.cancelJob(activeJobId);
    setActiveJobId(null);
    setJobProgress(null);
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
        return <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 flex items-center gap-1"><CheckCircle2 className="w-3 h-3" /> Completed</span>;
      case 'partially_completed':
        return <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-amber-500/20 text-amber-400 border border-amber-500/30 flex items-center gap-1"><AlertTriangle className="w-3 h-3" /> With Warnings</span>;
      case 'failed':
        return <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-rose-500/20 text-rose-400 border border-rose-500/30 flex items-center gap-1"><XCircle className="w-3 h-3" /> Failed</span>;
      case 'paused':
        return <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-slate-500/20 text-slate-400 border border-slate-500/30 flex items-center gap-1"><Pause className="w-3 h-3" /> Paused</span>;
      case 'translating':
      case 'analyzing':
      case 'segmenting':
      case 'rendering':
      case 'qa':
        return <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-sky-500/20 text-sky-400 border border-sky-500/30 flex items-center gap-1 animate-pulse"><RefreshCw className="w-3 h-3 animate-spin" /> {status.toUpperCase()}</span>;
      default:
        return <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-slate-800 text-slate-400 border border-slate-700">{status}</span>;
    }
  };

  // Filter segments for review modal
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
    <div className="flex-1 flex flex-col h-screen overflow-hidden bg-slate-950 text-slate-100">
      {/* Top Header */}
      <header className="px-6 py-4 border-b border-slate-800/80 bg-slate-900/60 flex items-center justify-between">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-lg font-bold tracking-tight text-white flex items-center gap-2">
              <Layers className="w-5 h-5 text-sky-400" />
              Document Translation Engine
            </h1>
            <span className="text-[10px] font-semibold px-2 py-0.5 rounded bg-sky-500/20 text-sky-400 border border-sky-500/30">
              Phase 2 Production
            </span>
          </div>
          <p className="text-xs text-slate-400 mt-0.5">
            Structure & layout-preserving translation for DOCX, XLSX, PPTX, and PDF (with OCR fallback)
          </p>
        </div>

        <div className="flex items-center gap-3">
          <input
            type="file"
            ref={fileInputRef}
            onChange={handleFileUpload}
            accept=".docx,.xlsx,.pptx,.pdf"
            className="hidden"
          />
          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={isUploading}
            className={`px-3.5 py-2 rounded-lg bg-gradient-to-r from-sky-600 to-indigo-600 hover:from-sky-500 hover:to-indigo-500 text-white font-medium text-xs shadow-lg shadow-sky-600/20 flex items-center gap-2 transition-all disabled:opacity-50 ${isUploading ? 'btn-loading-shimmer shadow-sky-500/50' : ''}`}
          >
            {isUploading ? (
              <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
            ) : (
              <UploadCloud className="w-4 h-4" />
            )}
            <span>{isUploading ? 'Processing Document...' : 'Upload Document'}</span>
          </button>
        </div>
      </header>

      {/* Main Content Area */}
      <div className="flex-1 overflow-y-auto p-6 space-y-6">
        {/* Upload Error Banner */}
        {uploadError && (
          <div className="p-3 rounded-lg bg-rose-500/15 border border-rose-500/30 text-rose-300 text-xs flex items-center justify-between">
            <div className="flex items-center gap-2">
              <AlertCircle className="w-4 h-4 text-rose-400" />
              <span>{uploadError}</span>
            </div>
            <button onClick={() => setUploadError(null)} className="text-rose-400 hover:text-rose-200">
              ✕
            </button>
          </div>
        )}

        {/* Failed Job Banner */}
        {jobProgress && jobProgress.status === 'failed' && (
          <div className="bg-rose-950/40 rounded-xl border border-rose-500/50 p-5 shadow-xl shadow-rose-950/40 relative overflow-hidden">
            <div className="flex items-start justify-between">
              <div className="flex items-start gap-3">
                <div className="w-10 h-10 rounded-lg bg-rose-500/20 border border-rose-500/30 flex items-center justify-center text-rose-400 flex-shrink-0 mt-0.5">
                  <XCircle className="w-6 h-6" />
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <h3 className="text-sm font-semibold text-white">
                      Tiến trình dịch tài liệu thất bại (Translation Failed)
                    </h3>
                    <span className="text-[10px] px-2 py-0.5 rounded bg-rose-500/20 text-rose-300 font-mono border border-rose-500/30 uppercase font-semibold">
                      FAILED
                    </span>
                  </div>
                  <p className="text-xs text-rose-300 mt-1.5 bg-rose-900/40 p-2.5 rounded-lg border border-rose-500/20 font-mono">
                    {jobProgress.error_message || jobProgress.current_stage || "Lỗi mô hình AI (quá tải hoặc hết hạn ngạch)."}
                  </p>
                  <p className="text-[11px] text-slate-400 mt-2">
                    Hệ thống đã dừng lại an toàn và không tạo file rác. Bạn có thể bấm nút bên dưới để đổi sang mô hình khác (ví dụ: Groq hoặc Gemini 3.7) và thử lại.
                  </p>
                </div>
              </div>

              <div className="flex items-center gap-2 flex-shrink-0">
                <button
                  type="button"
                  onClick={() => {
                    const failedDoc = documents.find(d => d.id === jobProgress.document_id || d.active_job?.id === jobProgress.id);
                    if (failedDoc) {
                      openTranslateConfig(failedDoc);
                    }
                  }}
                  className="px-3.5 py-2 rounded-lg bg-sky-600 hover:bg-sky-500 text-white text-xs font-semibold flex items-center gap-1.5 shadow-md shadow-sky-600/30 transition-all"
                >
                  <RotateCcw className="w-3.5 h-3.5" />
                  <span>Đổi Model & Thử Lại</span>
                </button>
                <button
                  type="button"
                  onClick={() => setJobProgress(null)}
                  className="p-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-400 hover:text-white text-xs"
                >
                  ✕
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Active Job Progress Widget */}
        {jobProgress && ['queued', 'analyzing', 'segmenting', 'translating', 'qa', 'rendering'].includes(jobProgress.status) && (
          <div className="bg-gradient-to-r from-slate-900 to-slate-850 rounded-xl border border-sky-500/40 p-5 shadow-xl shadow-sky-950/40 relative overflow-hidden">
            <div className="absolute top-0 left-0 right-0 h-1 bg-slate-800">
              <div
                className="h-full bg-gradient-to-r from-sky-500 to-indigo-500 transition-all duration-300"
                style={{ width: `${jobProgress.progress_pct}%` }}
              />
            </div>

            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-3">
                <div className="w-9 h-9 rounded-lg bg-sky-500/20 border border-sky-500/30 flex items-center justify-center text-sky-400">
                  <RefreshCw className="w-5 h-5 animate-spin" />
                </div>
                <div>
                  <h3 className="text-sm font-semibold text-white flex items-center gap-2">
                    Translating Document
                    <span className="text-[11px] px-2 py-0.5 rounded bg-sky-500/20 text-sky-300 font-mono">
                      {jobProgress.status.toUpperCase()}
                    </span>
                  </h3>
                  <p className="text-xs text-slate-400">
                    {jobProgress.current_unit && <span className="text-sky-300 font-medium">{jobProgress.current_unit} · </span>}
                    {jobProgress.current_item && <span>Current: "{jobProgress.current_item}"</span>}
                  </p>
                </div>
              </div>

              <div className="flex items-center gap-2">
                {jobProgress.status === 'translating' ? (
                  <button
                    onClick={handlePauseJob}
                    className="p-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs flex items-center gap-1 transition-colors"
                  >
                    <Pause className="w-3.5 h-3.5" />
                    <span>Pause</span>
                  </button>
                ) : (
                  <button
                    onClick={handleResumeJob}
                    className="p-1.5 rounded-lg bg-sky-600 hover:bg-sky-500 text-white text-xs flex items-center gap-1 transition-colors"
                  >
                    <Play className="w-3.5 h-3.5" />
                    <span>Resume</span>
                  </button>
                )}
                <button
                  onClick={handleCancelJob}
                  className="p-1.5 rounded-lg bg-slate-800 hover:bg-rose-900/50 text-rose-400 text-xs flex items-center gap-1 transition-colors"
                >
                  <XCircle className="w-3.5 h-3.5" />
                  <span>Cancel</span>
                </button>
              </div>
            </div>

            {/* Progress Metrics */}
            <div className="grid grid-cols-4 gap-4 pt-2 border-t border-slate-800/80 text-xs">
              <div>
                <span className="text-slate-500 block text-[10px] uppercase font-semibold">Segments Progress</span>
                <span className="text-white font-mono font-medium">
                  {jobProgress.completed_segments} / {jobProgress.total_segments} ({jobProgress.progress_pct}%)
                </span>
              </div>
              <div>
                <span className="text-slate-500 block text-[10px] uppercase font-semibold">QA Validation</span>
                <span className="text-emerald-400 font-mono font-medium">{jobProgress.qa_pct}% Checked</span>
              </div>
              <div>
                <span className="text-slate-500 block text-[10px] uppercase font-semibold">Pending / Failed</span>
                <span className="text-slate-300 font-mono font-medium">
                  {jobProgress.pending_segments} pending · <span className={jobProgress.failed_segments > 0 ? "text-rose-400" : "text-slate-400"}>{jobProgress.failed_segments} failed</span>
                </span>
              </div>
              <div>
                <span className="text-slate-500 block text-[10px] uppercase font-semibold">Elapsed Time</span>
                <span className="text-slate-400 font-mono font-medium flex items-center gap-1">
                  <Clock className="w-3 h-3" /> {jobProgress.elapsed_seconds}s
                </span>
              </div>
            </div>
          </div>
        )}

        {/* Drag & Drop Upload Quick Target */}
        <div
          onClick={() => fileInputRef.current?.click()}
          className="border-2 border-dashed border-slate-850 hover:border-sky-500/50 rounded-xl p-8 bg-slate-900/40 hover:bg-slate-900/70 transition-all cursor-pointer flex flex-col items-center justify-center text-center group"
        >
          <div className="w-12 h-12 rounded-xl bg-slate-800 group-hover:bg-sky-600/20 text-slate-400 group-hover:text-sky-400 flex items-center justify-center transition-colors mb-3">
            <UploadCloud className="w-6 h-6" />
          </div>
          <h3 className="text-sm font-semibold text-slate-200 group-hover:text-white transition-colors">
            Drop your DOCX, XLSX, PPTX, or PDF document here
          </h3>
          <p className="text-xs text-slate-500 mt-1 max-w-md">
            The engine automatically segments text, protects formulas/URLs/code, preserves typography & tables, and translates with context.
          </p>
          <div className="flex items-center gap-3 mt-4 text-[11px] text-slate-400 font-medium">
            <span className="flex items-center gap-1.5"><FileFormatIcon type="doc" size="xs" /> Word (.docx)</span>
            <span className="flex items-center gap-1.5"><FileFormatIcon type="sheet" size="xs" /> Excel (.xlsx)</span>
            <span className="flex items-center gap-1.5"><FileFormatIcon type="slide" size="xs" /> PowerPoint (.pptx)</span>
            <span className="flex items-center gap-1.5"><FileFormatIcon type="pdf" size="xs" /> PDF + OCR</span>
          </div>
        </div>

        {/* Document Inventory Table */}
        <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden shadow-lg">
          <div className="px-5 py-3 border-b border-slate-800 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <h2 className="text-xs font-bold uppercase tracking-wider text-slate-400">
                Document Repository ({documents.length})
              </h2>
            </div>
            <button
              onClick={loadDocuments}
              className="p-1 rounded text-slate-400 hover:text-white transition-colors"
              title="Refresh document list"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? 'animate-spin' : ''}`} />
            </button>
          </div>

          {isLoading ? (
            <DocumentListSkeleton count={4} />
          ) : documents.length === 0 ? (
            <div className="p-12 text-center text-slate-500 text-xs">
              No documents uploaded yet. Upload a DOCX, XLSX, PPTX, or PDF to begin.
            </div>
          ) : (
            <div className="divide-y divide-slate-800/80">
              {documents.map(doc => {
                const job = doc.active_job;
                const hasOutput = job && ['completed', 'partially_completed'].includes(job.status);

                return (
                  <div
                    key={doc.id}
                    className="p-4 hover:bg-slate-850/40 transition-colors flex items-center justify-between gap-4"
                  >
                    <div className="flex items-center gap-3.5 min-w-0">
                      <div className="w-10 h-10 rounded-lg bg-slate-800/90 border border-slate-700/60 flex items-center justify-center flex-shrink-0 shadow-inner">
                        {getFormatIcon(doc.file_type, doc.filename)}
                      </div>
                      <div className="min-w-0">
                        <div className="flex items-center gap-2">
                          <h4 className="text-sm font-semibold text-white truncate" title={doc.filename}>
                            {doc.filename}
                          </h4>
                          <span className="text-[10px] uppercase font-mono px-1.5 py-0.5 rounded bg-slate-800 text-slate-400 border border-slate-700">
                            {doc.file_type}
                          </span>
                          {job && getStatusBadge(job.status)}
                        </div>
                        <div className="flex items-center gap-3 text-xs text-slate-400 mt-1">
                          <span>{(doc.file_size / 1024).toFixed(1)} KB</span>
                          <span>·</span>
                          <span>{doc.unit_count} {doc.unit_label}</span>
                          <span>·</span>
                          <span className="uppercase font-mono text-[10px] bg-slate-800 px-1.5 py-0.5 rounded border border-slate-700/60">
                            {job?.source_language || doc.detected_language || 'auto'} → {job?.target_language || 'vi'}
                          </span>
                          {job && (
                            <>
                              <span>·</span>
                              <span className="text-slate-300 font-mono text-[11px]">
                                {job.completed_segments} / {job.total_segments} segments
                              </span>
                            </>
                          )}
                        </div>
                        {job?.error_message && job.status === 'failed' && (
                          <div className="mt-1 text-[11px] text-rose-400 bg-rose-950/40 px-2.5 py-1 rounded border border-rose-500/20 font-mono flex items-center gap-1.5" title={job.error_message}>
                            <AlertCircle className="w-3.5 h-3.5 flex-shrink-0 text-rose-400" />
                            <span className="truncate">{job.error_message}</span>
                          </div>
                        )}
                      </div>
                    </div>

                    {/* Action Buttons */}
                    <div className="flex items-center gap-2 flex-shrink-0">
                      {job?.status === 'failed' && (
                        <button
                          type="button"
                          onClick={() => openTranslateConfig(doc)}
                          className="px-3 py-1.5 rounded-md bg-rose-600/20 hover:bg-rose-600/30 text-rose-300 border border-rose-500/30 text-xs font-medium flex items-center gap-1.5 transition-colors"
                        >
                          <RotateCcw className="w-3.5 h-3.5" />
                          <span>Đổi Model / Thử lại</span>
                        </button>
                      )}
                      {hasOutput && (
                        <>
                          <a
                            href={apiClient.getDocumentDownloadUrl(job.id)}
                            download
                            className="px-3 py-1.5 rounded-md bg-emerald-600/20 hover:bg-emerald-600/30 text-emerald-300 border border-emerald-500/30 text-xs font-medium flex items-center gap-1.5 transition-colors"
                          >
                            <Download className="w-3.5 h-3.5" />
                            <span>Download</span>
                          </a>
                          <button
                            type="button"
                            onClick={() => handleOpenJobFolder(job.id)}
                            title="Mở thư mục chứa file dịch trên máy tính"
                            className="px-2.5 py-1.5 rounded-md bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 text-xs font-medium flex items-center gap-1.5 transition-colors"
                          >
                            <FolderOpen className="w-3.5 h-3.5 text-amber-400" />
                            <span>Mở thư mục</span>
                          </button>
                        </>
                      )}

                      {job && (
                        <button
                          onClick={() => openReviewModal(doc)}
                          className="px-3 py-1.5 rounded-md bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 text-xs font-medium flex items-center gap-1.5 transition-colors"
                        >
                          <Eye className="w-3.5 h-3.5 text-sky-400" />
                          <span>Review & Edit</span>
                        </button>
                      )}

                      <button
                        onClick={() => openTranslateConfig(doc)}
                        className="px-3 py-1.5 rounded-md bg-sky-600/20 hover:bg-sky-600/30 text-sky-300 border border-sky-500/30 text-xs font-medium flex items-center gap-1.5 transition-colors"
                      >
                        <Sparkles className="w-3.5 h-3.5" />
                        <span>{job ? 'Re-Translate' : 'Translate'}</span>
                      </button>

                      <button
                        onClick={(e) => handleDelete(doc.id, e)}
                        className="p-1.5 rounded-md hover:bg-rose-900/30 text-slate-500 hover:text-rose-400 transition-colors"
                        title="Delete document"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>

      {/* Translation Configuration Modal */}
      {configDoc && (
        <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-700 rounded-xl shadow-2xl max-w-lg w-full overflow-hidden flex flex-col">
            <div className="px-5 py-4 border-b border-slate-800 flex items-center justify-between">
              <div className="flex items-center gap-2.5">
                <div className="w-9 h-9 rounded-lg bg-slate-800/90 border border-slate-700/60 flex items-center justify-center shadow-inner flex-shrink-0">
                  <FileFormatIcon type={configDoc.file_type} name={configDoc.filename} size="sm" />
                </div>
                <div>
                  <h3 className="text-sm font-semibold text-white">Translate Document</h3>
                  <p className="text-xs text-slate-400 truncate max-w-xs">{configDoc.filename}</p>
                </div>
              </div>
              <button
                onClick={() => setConfigDoc(null)}
                className="text-slate-400 hover:text-white text-sm"
              >
                ✕
              </button>
            </div>

            <div className="p-5 space-y-4 text-xs overflow-y-auto max-h-[70vh]">
              {/* Language Configuration: Source & Target */}
              <div className="p-3.5 bg-slate-850 rounded-xl border border-slate-700/80 space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-slate-300 font-semibold flex items-center gap-1.5 text-xs">
                    <Languages className="w-4 h-4 text-sky-400" />
                    Cặp ngôn ngữ dịch thuật (Language Pair)
                  </span>
                  {configDoc.detected_language && (
                    <span className="text-[10px] px-2 py-0.5 rounded bg-sky-500/15 text-sky-300 border border-sky-500/30 font-medium">
                      Tự động phát hiện: {configDoc.detected_language === 'ja' ? '🇯🇵 Tiếng Nhật' : configDoc.detected_language === 'vi' ? '🇻🇳 Tiếng Việt' : '🇬🇧 English'}
                    </span>
                  )}
                </div>

                <div className="grid grid-cols-1 md:grid-cols-[1fr,auto,1fr] gap-2 items-center">
                  {/* Source Language */}
                  <div>
                    <label className="block text-[11px] text-slate-400 font-medium mb-1">
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
                                ? 'bg-sky-600/30 border-sky-500 text-white font-semibold shadow-sm'
                                : 'bg-slate-800/60 border-slate-700/80 text-slate-300 hover:bg-slate-800 hover:text-white'
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
                      className="p-2 rounded-lg bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-300 hover:text-sky-400 transition-all active:scale-95 shadow-sm"
                    >
                      <ArrowRightLeft className="w-4 h-4" />
                    </button>
                  </div>

                  {/* Target Language */}
                  <div>
                    <label className="block text-[11px] text-slate-400 font-medium mb-1">
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
                              ? 'bg-emerald-600/30 border-emerald-500 text-white font-semibold shadow-sm'
                              : 'bg-slate-800/60 border-slate-700/80 text-slate-300 hover:bg-slate-800 hover:text-white'
                          }`}
                        >
                          {lang.label}
                        </button>
                      ))}
                    </div>
                  </div>
                </div>

                {/* Translation Direction Banner */}
                <div className="flex items-center justify-center gap-2 py-1.5 px-3 bg-slate-900/80 rounded-lg border border-slate-800 text-[11px] text-slate-300">
                  <span className="font-semibold text-sky-400 uppercase font-mono">
                    {sourceLang === 'auto' ? (configDoc.detected_language || 'JA') : sourceLang}
                  </span>
                  <ArrowRight className="w-3.5 h-3.5 text-slate-500" />
                  <span className="font-semibold text-emerald-400 uppercase font-mono">
                    {targetLang}
                  </span>
                  <span className="text-slate-400 text-[11px] ml-1">
                    (Dịch từ {sourceLang === 'vi' || (sourceLang === 'auto' && configDoc.detected_language === 'vi') ? 'Tiếng Việt' : sourceLang === 'ja' || (sourceLang === 'auto' && configDoc.detected_language === 'ja') ? 'Tiếng Nhật' : 'English'} sang {targetLang === 'vi' ? 'Tiếng Việt' : targetLang === 'ja' ? 'Tiếng Nhật' : 'English'})
                  </span>
                </div>
              </div>

              {/* Project Workspace */}
              <div>
                <label className="block text-slate-400 font-semibold mb-1">Project Workspace Context</label>
                <select
                  value={selectedProjectId}
                  onChange={(e) => setSelectedProjectId(e.target.value)}
                  className="w-full bg-slate-800 border border-slate-700 rounded-lg p-2 text-slate-200 focus:border-sky-500 focus:outline-none"
                >
                  <option value="">-- Global Terminology & TM --</option>
                  {projects.map(p => (
                    <option key={p.id} value={p.id}>{p.name} ({p.code})</option>
                  ))}
                </select>
              </div>

              {/* Tone / Style */}
              <div>
                <label className="block text-slate-400 font-semibold mb-1">Tone & Communication Style</label>
                <div className="grid grid-cols-4 gap-2">
                  {['Auto', 'Polite', 'Formal', 'Technical'].map(s => (
                    <button
                      key={s}
                      type="button"
                      onClick={() => setStyle(s)}
                      className={`p-2 rounded-lg border text-center transition-all ${
                        style === s
                          ? 'bg-sky-600/30 border-sky-500 text-white font-semibold'
                          : 'bg-slate-800/60 border-slate-700 text-slate-300 hover:bg-slate-800'
                      }`}
                    >
                      {s}
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
                <div className="p-3 bg-slate-850 rounded-lg border border-slate-700/80 hover:border-sky-500/50 transition-colors">
                  <label className="flex items-start gap-3 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={translateImages}
                      onChange={(e) => setTranslateImages(e.target.checked)}
                      className="mt-0.5 rounded border-slate-700 text-sky-600 focus:ring-sky-500"
                    />
                    <div className="flex-1">
                      <div className="flex items-center gap-2">
                        <ImageIcon className="w-4 h-4 text-sky-400" />
                        <span className="text-slate-200 font-medium text-xs">
                          Dịch chữ trong hình ảnh (AI Vision & Inpainting)
                        </span>
                        <span className="text-[10px] font-semibold px-1.5 py-0.2 rounded bg-sky-500/20 text-sky-300 border border-sky-500/30">
                          BETA
                        </span>
                      </div>
                      <p className="text-[11px] text-slate-400 mt-1 leading-relaxed">
                        Tự động phát hiện sơ đồ kiến trúc, screenshot UI, xóa chữ cũ bằng màu nền và dán chữ dịch bằng font tiếng Nhật/Việt chuẩn.
                      </p>

                      {translateImages && (
                        <div className="mt-2.5 pt-2 border-t border-slate-700/60 flex flex-col gap-1.5">
                          <span className="text-[10px] uppercase tracking-wider font-semibold text-slate-400">
                            Công nghệ OCR bóc tách chữ trong ảnh:
                          </span>
                          <div className="grid grid-cols-2 gap-1.5">
                            <button
                              type="button"
                              onClick={(e) => { e.preventDefault(); setOcrEngine('paddleocr'); }}
                              className={`px-2.5 py-1.5 rounded text-[11px] text-left border transition-all ${
                                ocrEngine === 'paddleocr'
                                  ? 'bg-sky-500/20 border-sky-500 text-white font-medium shadow-sm'
                                  : 'bg-slate-800 border-slate-700 text-slate-400 hover:text-slate-200'
                              }`}
                            >
                              <div className="font-semibold text-sky-300 flex items-center gap-1">
                                <span>⚡ PaddleOCR (Local)</span>
                              </div>
                              <div className="text-[10px] text-slate-400">Chuyên dụng tiếng Nhật & Việt</div>
                            </button>

                            <button
                              type="button"
                              onClick={(e) => { e.preventDefault(); setOcrEngine('gemini_vision'); }}
                              className={`px-2.5 py-1.5 rounded text-[11px] text-left border transition-all ${
                                ocrEngine === 'gemini_vision'
                                  ? 'bg-sky-500/20 border-sky-500 text-white font-medium shadow-sm'
                                  : 'bg-slate-800 border-slate-700 text-slate-400 hover:text-slate-200'
                              }`}
                            >
                              <div className="font-semibold text-slate-200 flex items-center gap-1">
                                <span>☁️ Gemini Vision</span>
                              </div>
                              <div className="text-[10px] text-slate-400">Cloud Multi-modal API</div>
                            </button>
                          </div>
                        </div>
                      )}
                    </div>
                  </label>
                </div>
              )}

              {configDoc.file_type === 'pptx' && (
                <div className="p-3 bg-slate-850 rounded-lg border border-slate-700/80">
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={translateNotes}
                      onChange={(e) => setTranslateNotes(e.target.checked)}
                      className="rounded border-slate-700 text-sky-600 focus:ring-sky-500"
                    />
                    <span className="text-slate-200 font-medium">Translate Speaker Notes in Slides</span>
                  </label>
                </div>
              )}

              {configDoc.file_type === 'pdf' && (
                <div className="p-3 bg-slate-850 rounded-lg border border-slate-700/80">
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={useOcr}
                      onChange={(e) => setUseOcr(e.target.checked)}
                      className="rounded border-slate-700 text-sky-600 focus:ring-sky-500"
                    />
                    <span className="text-slate-200 font-medium">Use OCR engine for scanned / image pages</span>
                  </label>
                </div>
              )}

              {/* Output Filename (Customizable) */}
              <div className="p-3 bg-slate-850 rounded-lg border border-slate-700/80 space-y-2">
                <div className="flex items-center justify-between">
                  <label className="text-xs font-semibold text-slate-300 flex items-center gap-1.5">
                    <Edit3 className="w-3.5 h-3.5 text-sky-400" />
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
                      className="text-[10px] text-sky-400 hover:text-sky-300 hover:underline flex items-center gap-1 font-medium transition-colors"
                      title="Khôi phục lại tên gợi ý ban đầu"
                    >
                      <RotateCcw className="w-3 h-3" />
                      <span>Đặt lại mặc định</span>
                    </button>
                  )}
                </div>
                <div className="relative">
                  <input
                    type="text"
                    value={targetFilename}
                    onChange={(e) => {
                      setTargetFilename(e.target.value);
                      setIsFilenameEdited(true);
                    }}
                    placeholder={`Gợi ý: ${configDoc ? computeDefaultFilename(configDoc.filename, targetLang) : ''}`}
                    className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-sky-500 font-mono shadow-inner"
                  />
                </div>
                <p className="text-[10px] text-slate-400">
                  Mặc định sẽ gắn mã ngôn ngữ <code className="text-sky-300 bg-slate-800 px-1 py-0.5 rounded font-mono">_{targetLang.toUpperCase()}</code> vào tên tệp gốc. Bạn có thể tự do chỉnh sửa tên theo ý muốn.
                </p>
              </div>

              {/* Output Directory / Save Location */}
              <div className="p-3 bg-slate-850 rounded-lg border border-slate-700/80 space-y-2">
                <div className="flex items-center justify-between">
                  <label className="text-xs font-semibold text-slate-300 flex items-center gap-1.5">
                    <Folder className="w-3.5 h-3.5 text-sky-400" />
                    <span>Đường dẫn thư mục lưu file dịch (Save Location)</span>
                  </label>
                  <span className="text-[10px] text-slate-400">Tùy chọn</span>
                </div>
                <div className="flex items-center gap-2">
                  <div className="relative flex-1">
                    <input
                      type="text"
                      value={customOutputDir}
                      onChange={(e) => updateOutputDir(e.target.value)}
                      placeholder="Mặc định: data/documents/output (hoặc bấm nút bên cạnh để chọn)"
                      className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-sky-500 font-mono pr-7"
                    />
                    {customOutputDir && (
                      <button
                        type="button"
                        onClick={() => updateOutputDir('')}
                        className="absolute right-2.5 top-2 text-slate-400 hover:text-slate-200 text-xs"
                        title="Xóa để dùng mặc định"
                      >
                        ✕
                      </button>
                    )}
                  </div>
                  <button
                    type="button"
                    onClick={handleBrowseFolder}
                    disabled={isBrowsingFolder}
                    className="px-3 py-2 rounded-lg bg-sky-600 hover:bg-sky-500 disabled:bg-slate-700 text-white text-xs font-medium flex items-center gap-1.5 transition-colors flex-shrink-0 shadow-sm"
                    title="Mở cửa sổ chọn thư mục trên máy tính"
                  >
                    <FolderOpen className={`w-4 h-4 ${isBrowsingFolder ? 'animate-spin' : ''}`} />
                    <span>{isBrowsingFolder ? 'Đang chọn...' : 'Chọn thư mục...'}</span>
                  </button>
                </div>
                <div className="flex items-center gap-1.5 pt-0.5">
                  <span className="text-[10px] text-slate-500">Gợi ý nhanh:</span>
                  <button
                    type="button"
                    onClick={() => updateOutputDir('')}
                    className={`text-[10px] px-2 py-0.5 rounded border transition-colors ${
                      !customOutputDir ? 'bg-sky-600/30 text-sky-300 border-sky-500/40' : 'bg-slate-800 text-slate-400 border-slate-700 hover:text-slate-300'
                    }`}
                  >
                    Mặc định
                  </button>
                  <button
                    type="button"
                    onClick={() => updateOutputDir('C:\\Users\\defaultuser0\\Downloads')}
                    className="text-[10px] px-2 py-0.5 rounded bg-slate-800 text-slate-400 border border-slate-700 hover:text-slate-300 transition-colors"
                  >
                    Downloads
                  </button>
                  <button
                    type="button"
                    onClick={() => updateOutputDir('C:\\Users\\defaultuser0\\Desktop')}
                    className="text-[10px] px-2 py-0.5 rounded bg-slate-800 text-slate-400 border border-slate-700 hover:text-slate-300 transition-colors"
                  >
                    Desktop
                  </button>
                </div>
              </div>

              {/* Preservation Guarantees Card */}
              <div className="p-3 bg-slate-950/60 rounded-lg border border-slate-800 text-[11px] text-slate-400 space-y-1">
                <div className="text-slate-300 font-semibold flex items-center gap-1.5">
                  <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
                  Preservation Guarantee Active:
                </div>
                <p>• Excel formulas (=...) and sheet cross-references are strictly preserved.</p>
                <p>• Inline formatting (bold, color, fonts, hyperlinks) is maintained.</p>
                <p>• URLs, email addresses, and camelCase code tokens are protected.</p>
              </div>
            </div>

            <div className="px-5 py-3 border-t border-slate-800 bg-slate-950/40 flex items-center justify-end gap-2">
              <button
                type="button"
                onClick={() => setConfigDoc(null)}
                className="px-4 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-medium transition-colors"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={startTranslation}
                className="px-4 py-2 rounded-lg bg-gradient-to-r from-sky-600 to-indigo-600 hover:from-sky-500 hover:to-indigo-500 text-white text-xs font-medium shadow-lg shadow-sky-600/20 flex items-center gap-1.5 transition-all"
              >
                <Sparkles className="w-3.5 h-3.5" />
                <span>Start Translation Job</span>
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Document Review & Segment Inspector Modal */}
      {reviewDoc && reviewJob && (
        <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-md flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-700 rounded-xl shadow-2xl max-w-5xl w-full h-[88vh] overflow-hidden flex flex-col">
            {/* Header */}
            <div className="px-6 py-4 border-b border-slate-800 flex items-center justify-between bg-slate-950/40">
              <div className="flex items-center gap-3">
                <div className="w-9 h-9 rounded-lg bg-slate-800 flex items-center justify-center">
                  {getFormatIcon(reviewDoc.file_type)}
                </div>
                <div>
                  <h3 className="text-sm font-semibold text-white flex items-center gap-2">
                    Review: {reviewDoc.filename}
                    {getStatusBadge(reviewJob.status)}
                  </h3>
                  <p className="text-xs text-slate-400">
                    {reviewJob.completed_segments} of {reviewJob.total_segments} segments translated · {issues.length} QA issues flagged
                  </p>
                </div>
              </div>

              <div className="flex items-center gap-2">
                {['completed', 'partially_completed'].includes(reviewJob.status) && (
                  <a
                    href={apiClient.getDocumentDownloadUrl(reviewJob.id)}
                    download
                    className="px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-medium flex items-center gap-1.5 transition-colors shadow-sm shadow-emerald-600/20"
                  >
                    <Download className="w-3.5 h-3.5" />
                    <span>Download File</span>
                  </a>
                )}
                <button
                  onClick={() => setReviewDoc(null)}
                  className="p-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-400 hover:text-white"
                >
                  ✕
                </button>
              </div>
            </div>

            {/* QA Issues summary banner if any */}
            {issues.length > 0 && (
              <div className="px-6 py-2.5 bg-amber-500/10 border-b border-amber-500/20 text-xs flex items-center justify-between text-amber-300">
                <div className="flex items-center gap-2">
                  <AlertTriangle className="w-4 h-4 text-amber-400 flex-shrink-0" />
                  <span>
                    QA detected <strong>{issues.length}</strong> issues (e.g. text overflow or formatting warning). Inspect flagged segments below.
                  </span>
                </div>
                <div className="flex items-center gap-1.5 text-[11px]">
                  {issues.slice(0, 2).map((iss, i) => (
                    <span key={i} className="px-2 py-0.5 rounded bg-amber-500/20 text-amber-300 border border-amber-500/30">
                      {iss.category}: {iss.message}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {/* Search & Filter Toolbar */}
            <div className="px-6 py-3 border-b border-slate-800 bg-slate-900 flex items-center justify-between gap-4">
              <div className="relative flex-1 max-w-sm">
                <Search className="w-4 h-4 absolute left-3 top-2.5 text-slate-500" />
                <input
                  type="text"
                  value={segmentSearch}
                  onChange={(e) => setSegmentSearch(e.target.value)}
                  placeholder="Search segments by source or translation..."
                  className="w-full bg-slate-800 border border-slate-700 rounded-lg pl-9 pr-3 py-1.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-sky-500"
                />
              </div>

              <div className="flex items-center gap-1">
                {(['all', 'translated', 'failed', 'issues'] as const).map(f => (
                  <button
                    key={f}
                    onClick={() => setSegmentFilter(f)}
                    className={`px-3 py-1 rounded-md text-xs capitalize transition-colors ${
                      segmentFilter === f
                        ? 'bg-sky-600 text-white font-medium'
                        : 'bg-slate-800/80 text-slate-400 hover:text-white'
                    }`}
                  >
                    {f}
                  </button>
                ))}
              </div>
            </div>

            {/* Segments Table */}
            <div className="flex-1 overflow-y-auto divide-y divide-slate-800/80">
              {filteredSegments.length === 0 ? (
                <div className="p-12 text-center text-slate-500 text-xs">
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
                      className="p-4 hover:bg-slate-850/30 transition-colors grid grid-cols-12 gap-4 items-start text-xs"
                    >
                      {/* Location Badge */}
                      <div className="col-span-2">
                        <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-slate-800 text-slate-400 border border-slate-700 block truncate" title={seg.unit_name || `Unit ${seg.unit_index}`}>
                          {seg.unit_name || `Item ${seg.unit_index}`}
                        </span>
                        <div className="mt-1">
                          {seg.user_edited && (
                            <span className="text-[9px] uppercase font-bold text-amber-400 bg-amber-500/10 px-1 py-0.2 rounded">
                              Edited
                            </span>
                          )}
                        </div>
                      </div>

                      {/* Source Text */}
                      <div className="col-span-5 text-slate-200 leading-relaxed font-sans select-text">
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
                              className="w-full bg-slate-800 border border-sky-500 rounded-lg p-2 text-xs text-white focus:outline-none resize-y font-sans"
                            />
                            <div className="flex items-center gap-2">
                              <button
                                onClick={() => handleSaveSegment(segId)}
                                className="px-2.5 py-1 rounded bg-sky-600 hover:bg-sky-500 text-white text-[11px] font-medium transition-colors"
                              >
                                Save
                              </button>
                              <button
                                onClick={() => setEditingSegmentId(null)}
                                className="px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-400 text-[11px] transition-colors"
                              >
                                Cancel
                              </button>
                            </div>
                          </div>
                        ) : (
                          <div className="group relative">
                            <div className="text-emerald-300 leading-relaxed select-text min-h-[1.5rem] font-sans">
                              {seg.target_text || <span className="text-slate-500 italic">No translation yet</span>}
                            </div>
                            <div className="flex items-center gap-2 mt-2">
                              <button
                                onClick={() => {
                                  setEditingSegmentId(segId);
                                  setEditingText(seg.target_text || '');
                                }}
                                className="text-[11px] text-slate-400 hover:text-white transition-colors underline"
                              >
                                Edit
                              </button>
                              <span className="text-slate-600">·</span>
                              <button
                                onClick={() => handleRegenerateSegment(segId)}
                                disabled={isRegen}
                                className="text-[11px] text-sky-400 hover:text-sky-300 flex items-center gap-1 transition-colors disabled:opacity-50"
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

            {/* Footer */}
            <div className="px-6 py-3 border-t border-slate-800 bg-slate-950/60 flex items-center justify-between text-xs text-slate-400">
              <span>Showing {filteredSegments.length} segments</span>
              <button
                onClick={() => setReviewDoc(null)}
                className="px-4 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-medium transition-colors"
              >
                Close Review
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
