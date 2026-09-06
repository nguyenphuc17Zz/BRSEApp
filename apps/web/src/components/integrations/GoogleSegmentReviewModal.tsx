import React, { useState, useEffect } from 'react';
import {
  FileText,
  FileSpreadsheet,
  Presentation,
  CheckCircle2,
  AlertTriangle,
  RotateCcw,
  ExternalLink,
  Search,
  Filter,
  Edit3,
  Check,
  X,
  Layers,
  Sparkles
} from 'lucide-react';
import { apiClient } from '../../api/client';
import { useToast } from '../../context/ToastContext';
import { FileFormatIcon } from '../common/FileFormatIcon';

interface GoogleSegmentReviewModalProps {
  jobId: string;
  fileTitle: string;
  fileType: string;
  outputUrl?: string;
  onClose: () => void;
}

export const GoogleSegmentReviewModal: React.FC<GoogleSegmentReviewModalProps> = ({
  jobId,
  fileTitle,
  fileType,
  outputUrl,
  onClose
}) => {
  const toast = useToast();
  const [activeTab, setActiveTab] = useState<'segments' | 'issues'>('segments');
  const [segments, setSegments] = useState<any[]>([]);
  const [issues, setIssues] = useState<any[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [statusFilter, setStatusFilter] = useState<'all' | 'translated' | 'user_edited' | 'failed'>('all');

  const [editingSegmentId, setEditingSegmentId] = useState<string | null>(null);
  const [editingText, setEditingText] = useState<string>('');
  const [isSaving, setIsSaving] = useState<boolean>(false);
  const [regeneratingId, setRegeneratingId] = useState<string | null>(null);

  useEffect(() => {
    loadData();
  }, [jobId]);

  const loadData = async () => {
    setIsLoading(true);
    try {
      const [segsRes, issuesRes] = await Promise.all([
        apiClient.getGoogleJobSegments(jobId, 300, 0),
        apiClient.getGoogleJobIssues(jobId)
      ]);
      setSegments(segsRes.segments || []);
      setIssues(issuesRes || []);
    } catch (err) {
      console.error('Failed to load Google segments:', err);
      toast.error('Không thể tải danh sách phân đoạn của file.');
    } finally {
      setIsLoading(false);
    }
  };

  const handleStartEdit = (seg: any) => {
    setEditingSegmentId(seg.id);
    setEditingText(seg.translated_text || seg.target_text || '');
  };

  const handleSaveEdit = async (segmentId: string) => {
    setIsSaving(true);
    try {
      const updated = await apiClient.updateGoogleJobSegment(jobId, segmentId, {
        translated_text: editingText
      });
      setSegments(prev => prev.map(s => s.id === segmentId ? { ...s, translated_text: updated.translated_text, status: 'user_edited' } : s));
      setEditingSegmentId(null);
      toast.success('Đã cập nhật bản dịch phân đoạn thành công');
    } catch (err: any) {
      toast.error(err.response?.data?.detail || 'Không thể lưu bản dịch');
    } finally {
      setIsSaving(false);
    }
  };

  const handleRegenerate = async (segmentId: string) => {
    setRegeneratingId(segmentId);
    try {
      const updated = await apiClient.regenerateGoogleJobSegment(jobId, segmentId);
      setSegments(prev => prev.map(s => s.id === segmentId ? { ...s, translated_text: updated.translated_text, status: 'translated' } : s));
      toast.success('Đã dịch lại phân đoạn với AI');
    } catch (err: any) {
      toast.error(err.response?.data?.detail || 'Lỗi khi dịch lại phân đoạn');
    } finally {
      setRegeneratingId(null);
    }
  };

  // Filtered segments
  const filteredSegments = segments.filter(seg => {
    const matchesSearch =
      (seg.source_text || '').toLowerCase().includes(searchQuery.toLowerCase()) ||
      (seg.translated_text || '').toLowerCase().includes(searchQuery.toLowerCase()) ||
      (seg.unit_name || '').toLowerCase().includes(searchQuery.toLowerCase());

    if (!matchesSearch) return false;

    if (statusFilter === 'all') return true;
    if (statusFilter === 'translated') return seg.status === 'translated';
    if (statusFilter === 'user_edited') return seg.status === 'user_edited';
    if (statusFilter === 'failed') return seg.status === 'failed';
    return true;
  });

  return (
    <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-md flex items-center justify-center p-4">
      <div className="bg-slate-900 border border-slate-700/90 rounded-2xl w-full max-w-5xl h-[88vh] overflow-hidden flex flex-col shadow-2xl">
        {/* Header */}
        <div className="px-6 py-4 border-b border-slate-800 bg-slate-850 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-slate-800/90 border border-slate-700/60 flex items-center justify-center shadow-inner flex-shrink-0">
              <FileFormatIcon type={fileType} name={fileTitle} size="md" />
            </div>
            <div>
              <h3 className="text-sm font-semibold text-white truncate max-w-xl" title={fileTitle}>
                Kiểm tra & Hiệu chỉnh: {fileTitle}
              </h3>
              <p className="text-xs text-slate-400 flex items-center gap-2">
                <span>{segments.length} phân đoạn</span>
                <span>·</span>
                <span className="text-amber-400">{issues.length} cảnh báo QA</span>
                <span>·</span>
                <span>REST API Sync</span>
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {outputUrl && (
              <a
                href={outputUrl}
                target="_blank"
                rel="noreferrer"
                className="px-3.5 py-1.5 rounded-lg bg-sky-600/20 hover:bg-sky-600/30 text-sky-300 border border-sky-500/30 text-xs font-medium flex items-center gap-1.5 transition-colors"
              >
                <ExternalLink className="w-3.5 h-3.5" />
                <span>Mở bản sao Drive</span>
              </a>
            )}
            <button
              onClick={onClose}
              className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition-colors"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Navigation Tabs & Toolbar */}
        <div className="px-6 py-3 border-b border-slate-800 bg-slate-900/90 flex items-center justify-between gap-4">
          <div className="flex items-center gap-2">
            <button
              onClick={() => setActiveTab('segments')}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium flex items-center gap-2 transition-colors ${
                activeTab === 'segments'
                  ? 'bg-sky-600 text-white shadow-sm'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800'
              }`}
            >
              <Layers className="w-3.5 h-3.5" />
              <span>Phân đoạn dịch ({segments.length})</span>
            </button>
            <button
              onClick={() => setActiveTab('issues')}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium flex items-center gap-2 transition-colors ${
                activeTab === 'issues'
                  ? 'bg-amber-600 text-white shadow-sm'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800'
              }`}
            >
              <AlertTriangle className="w-3.5 h-3.5" />
              <span>Cảnh báo QA ({issues.length})</span>
            </button>
          </div>

          {activeTab === 'segments' && (
            <div className="flex items-center gap-3">
              {/* Search */}
              <div className="relative w-64">
                <Search className="w-3.5 h-3.5 absolute left-3 top-2.5 text-slate-500" />
                <input
                  type="text"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="Tìm kiếm nội dung..."
                  className="w-full bg-slate-800 border border-slate-700 rounded-lg pl-8 pr-3 py-1 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-sky-500"
                />
              </div>

              {/* Status Filter */}
              <select
                value={statusFilter}
                onChange={(e: any) => setStatusFilter(e.target.value)}
                className="bg-slate-800 border border-slate-700 rounded-lg px-2.5 py-1 text-xs text-slate-300 focus:outline-none focus:border-sky-500"
              >
                <option value="all">Tất cả trạng thái</option>
                <option value="translated">Đã dịch (AI)</option>
                <option value="user_edited">Đã hiệu chỉnh (Comtor)</option>
                <option value="failed">Lỗi</option>
              </select>
            </div>
          )}
        </div>

        {/* Content Body */}
        <div className="flex-1 overflow-y-auto p-6 space-y-3">
          {isLoading ? (
            <div className="py-20 text-center text-slate-400 text-xs flex flex-col items-center gap-3">
              <div className="w-6 h-6 border-2 border-sky-500 border-t-transparent rounded-full animate-spin"></div>
              <span>Đang tải danh sách phân đoạn...</span>
            </div>
          ) : activeTab === 'issues' ? (
            issues.length === 0 ? (
              <div className="py-20 text-center text-slate-400 text-xs">
                <CheckCircle2 className="w-8 h-8 text-emerald-400 mx-auto mb-2" />
                <p>Không phát hiện cảnh báo QA nào. Bản dịch đạt chuẩn toàn vẹn!</p>
              </div>
            ) : (
              <div className="space-y-2">
                {issues.map((issue, idx) => (
                  <div
                    key={idx}
                    className="p-3.5 rounded-xl bg-amber-500/10 border border-amber-500/25 flex items-start gap-3"
                  >
                    <AlertTriangle className="w-4 h-4 text-amber-400 flex-shrink-0 mt-0.5" />
                    <div className="flex-1 text-xs">
                      <div className="flex items-center gap-2">
                        <span className="font-semibold text-amber-300 uppercase text-[10px] px-1.5 py-0.2 rounded bg-amber-500/20">
                          {issue.category}
                        </span>
                        <span className="text-slate-400">{issue.location_text}</span>
                      </div>
                      <p className="text-slate-200 mt-1">{issue.message}</p>
                    </div>
                  </div>
                ))}
              </div>
            )
          ) : filteredSegments.length === 0 ? (
            <div className="py-20 text-center text-slate-500 text-xs">
              Không tìm thấy phân đoạn nào phù hợp.
            </div>
          ) : (
            filteredSegments.map((seg) => {
              const isEditing = editingSegmentId === seg.id;
              const isRegenerating = regeneratingId === seg.id;

              return (
                <div
                  key={seg.id}
                  className="p-4 rounded-xl bg-slate-850 border border-slate-800/90 hover:border-slate-700 transition-colors space-y-3"
                >
                  {/* Segment Location & Status Badge */}
                  <div className="flex items-center justify-between text-xs">
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-[10px] text-sky-400 bg-sky-950/60 px-2 py-0.5 rounded border border-sky-800/40 font-semibold">
                        #{seg.segment_index + 1}
                      </span>
                      <span className="text-slate-400 font-medium">
                        {seg.unit_name || 'Segment'}
                      </span>
                    </div>

                    <div className="flex items-center gap-2">
                      {seg.status === 'user_edited' && (
                        <span className="text-[10px] text-purple-300 bg-purple-950/60 px-2 py-0.5 rounded border border-purple-800/40">
                          ✍️ Đã sửa tay
                        </span>
                      )}
                      {seg.status === 'translated' && (
                        <span className="text-[10px] text-emerald-300 bg-emerald-950/60 px-2 py-0.5 rounded border border-emerald-800/40">
                          ✓ Đã dịch
                        </span>
                      )}
                      {seg.status === 'failed' && (
                        <span className="text-[10px] text-rose-300 bg-rose-950/60 px-2 py-0.5 rounded border border-rose-800/40">
                          ✕ Lỗi
                        </span>
                      )}
                    </div>
                  </div>

                  {/* Two Column: Source & Translation */}
                  <div className="grid grid-cols-2 gap-4 text-xs">
                    {/* Source */}
                    <div className="p-3 rounded-lg bg-slate-900 border border-slate-800 text-slate-300 leading-relaxed font-sans select-text">
                      <div className="text-[10px] text-slate-500 uppercase font-semibold mb-1">Văn bản gốc</div>
                      <div className="whitespace-pre-wrap">{seg.source_text}</div>
                    </div>

                    {/* Target / Editor */}
                    <div className="p-3 rounded-lg bg-slate-900 border border-slate-800 text-white leading-relaxed flex flex-col justify-between">
                      <div>
                        <div className="flex items-center justify-between text-[10px] text-slate-500 uppercase font-semibold mb-1">
                          <span>Bản dịch</span>
                          {!isEditing && (
                            <div className="flex items-center gap-1.5 lowercase">
                              <button
                                onClick={() => handleStartEdit(seg)}
                                className="text-slate-400 hover:text-sky-300 flex items-center gap-1 transition-colors"
                                title="Chỉnh sửa bản dịch"
                              >
                                <Edit3 className="w-3 h-3" />
                                <span>Sửa</span>
                              </button>
                              <span>·</span>
                              <button
                                onClick={() => handleRegenerate(seg.id)}
                                disabled={isRegenerating}
                                className="text-slate-400 hover:text-emerald-300 flex items-center gap-1 transition-colors disabled:opacity-50"
                                title="Dịch lại bằng AI"
                              >
                                <Sparkles className="w-3 h-3" />
                                <span>{isRegenerating ? 'Đang dịch...' : 'Dịch lại'}</span>
                              </button>
                            </div>
                          )}
                        </div>

                        {isEditing ? (
                          <div className="space-y-2 mt-1">
                            <textarea
                              value={editingText}
                              onChange={(e) => setEditingText(e.target.value)}
                              rows={3}
                              className="w-full bg-slate-950 border border-sky-500/80 rounded-lg p-2 text-xs text-white focus:outline-none focus:ring-1 focus:ring-sky-500 resize-y"
                            />
                            <div className="flex items-center justify-end gap-2">
                              <button
                                onClick={() => setEditingSegmentId(null)}
                                className="px-2.5 py-1 rounded bg-slate-800 text-slate-400 hover:text-white text-[11px]"
                              >
                                Hủy
                              </button>
                              <button
                                onClick={() => handleSaveEdit(seg.id)}
                                disabled={isSaving}
                                className="px-3 py-1 rounded bg-sky-600 hover:bg-sky-500 text-white text-[11px] font-medium flex items-center gap-1"
                              >
                                <Check className="w-3 h-3" />
                                <span>{isSaving ? 'Đang lưu...' : 'Lưu bản dịch'}</span>
                              </button>
                            </div>
                          </div>
                        ) : (
                          <div className="whitespace-pre-wrap select-text text-sky-100">
                            {seg.translated_text || <span className="text-slate-500 italic">Chưa dịch</span>}
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                </div>
              );
            })
          )}
        </div>

        {/* Footer */}
        <div className="px-6 py-3.5 border-t border-slate-800 bg-slate-850 flex items-center justify-between">
          <span className="text-xs text-slate-400">
            Tổng cộng: {filteredSegments.length} / {segments.length} phân đoạn hiển thị
          </span>
          <button
            onClick={onClose}
            className="px-5 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-medium transition-colors"
          >
            Đóng
          </button>
        </div>
      </div>
    </div>
  );
};
