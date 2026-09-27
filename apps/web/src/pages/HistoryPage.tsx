import React, { useState, useEffect } from 'react';
import { 
  History as HistoryIcon, 
  Search, 
  Trash2, 
  Copy, 
  Check, 
  Cpu, 
  Clock, 
  Layers,
  AlertTriangle,
  FileText
} from 'lucide-react';
import { apiClient } from '../api/client';
import { HistoryItem, Project } from '../types';
import { useToast } from '../context/ToastContext';
import { useConfirm } from '../context/ConfirmDialogContext';
import { TableSkeleton } from '../components/skeletons/TableSkeleton';
import { PageHeader } from '../components/ui/PageHeader';
import { Card } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { Badge } from '../components/ui/Badge';
import { Input } from '../components/ui/Input';
import { Modal } from '../components/ui/Modal';
import { EmptyState } from '../components/ui/EmptyState';

interface HistoryPageProps {
  activeProject: Project | null;
}

export const HistoryPage: React.FC<HistoryPageProps> = ({ activeProject }) => {
  const toast = useToast();
  const confirm = useConfirm();
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [selectedItem, setSelectedItem] = useState<HistoryItem | null>(null);

  useEffect(() => {
    loadHistory();
  }, [activeProject, search]);

  const loadHistory = async () => {
    setLoading(true);
    try {
      const list = await apiClient.getHistory({
        project_id: activeProject?.id,
        search: search || undefined
      });
      setHistory(list);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  const handleCopy = (text: string, id: string) => {
    navigator.clipboard.writeText(text);
    setCopiedId(id);
    toast.success('Đã sao chép vào clipboard');
    setTimeout(() => setCopiedId(null), 1800);
  };

  const handleDelete = async (id: string) => {
    const ok = await confirm({
      title: 'Xóa bản ghi lịch sử',
      message: 'Bạn có chắc chắn muốn xóa bản ghi lịch sử dịch này? Thao tác này không thể hoàn tác.',
      isDestructive: true,
      confirmText: 'Xóa bản ghi'
    });
    if (!ok) return;

    try {
      await apiClient.deleteHistoryItem(id);
      loadHistory();
      if (selectedItem?.id === id) setSelectedItem(null);
      toast.success('Đã xóa bản ghi lịch sử');
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || e.message, 'Failed to delete history item');
    }
  };

  return (
    <div className="flex-1 flex flex-col h-full overflow-y-auto bg-canvas px-4 py-6 sm:px-8 sm:py-8 lg:px-10">
      <div className="max-w-[1536px] mx-auto w-full space-y-6">
        {/* Header */}
      <PageHeader
        title="Lịch sử dịch"
      />

      {/* Search Filter */}
      <Card className="p-3 border border-border-subtle bg-surface">
        <div className="flex items-center gap-3">
          <div className="flex-1 relative">
            <Search className="w-4 h-4 text-text-muted absolute left-3 top-2.5 pointer-events-none" />
            <Input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Tìm kiếm nội dung lịch sử dịch..."
              className="pl-9"
            />
          </div>
          <Badge variant="neutral" size="sm" className="font-mono text-xs">
            {history.length} bản ghi
          </Badge>
        </div>
      </Card>

      {/* History Table */}
      <Card className="flex-1 flex flex-col overflow-hidden p-0 border border-border-subtle bg-surface min-h-0">
        {loading ? (
          <div className="p-4">
            <TableSkeleton rows={8} columns={6} />
          </div>
        ) : history.length === 0 ? (
          <div className="flex-1 flex items-center justify-center p-8">
            <EmptyState
              icon={<HistoryIcon className="w-10 h-10" />}
              title="No history records found"
              description="Translations performed across CAT workspace and quick popup will automatically be indexed here."
            />
          </div>
        ) : (
          <div className="overflow-x-auto flex-1">
            <table className="w-full text-left text-xs">
              <thead className="bg-surface-elevated text-text-muted uppercase font-semibold text-[10px] tracking-wider border-b border-border-subtle sticky top-0 z-10">
                <tr>
                  <th className="py-3 px-4 w-1/4">Source Text (JA)</th>
                  <th className="py-3 px-4 w-1/3">Selected Translation (VI)</th>
                  <th className="py-3 px-4">AI Route & Latency</th>
                  <th className="py-3 px-4">Signals</th>
                  <th className="py-3 px-4">Time</th>
                  <th className="py-3 px-4 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border-subtle font-sans">
                {history.map((h) => (
                  <tr
                    key={h.id}
                    onClick={() => setSelectedItem(h)}
                    className="hover:bg-surface-hover transition-colors cursor-pointer"
                  >
                    <td className="py-3 px-4 text-text-primary font-medium truncate max-w-xs" title={h.source_text}>
                      {h.source_text}
                    </td>
                    <td className="py-3 px-4 text-text-secondary truncate max-w-sm" title={h.selected_translation}>
                      {h.selected_translation}
                    </td>
                    <td className="py-3 px-4 font-mono text-[11px] text-text-muted">
                      <div className="text-primary font-medium">{h.provider}</div>
                      <div className="text-text-muted text-[10px]">{h.model} • {h.latency_ms}ms</div>
                    </td>
                    <td className="py-3 px-4">
                      <div className="flex items-center gap-1.5 flex-wrap">
                        {h.ambiguity_detected && (
                          <Badge variant="purple" size="sm" className="text-[10px]">
                            Ambiguous
                          </Badge>
                        )}
                        {h.qa_warnings && h.qa_warnings.length > 0 && (
                          <Badge variant="warning" size="sm" className="text-[10px]">
                            QA Warning
                          </Badge>
                        )}
                      </div>
                    </td>
                    <td className="py-3 px-4 text-text-muted text-[11px] font-mono whitespace-nowrap">
                      {new Date(h.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                    </td>
                    <td className="py-3 px-4 text-right">
                      <div className="flex items-center justify-end gap-1" onClick={(e) => e.stopPropagation()}>
                        <button
                          onClick={() => handleCopy(h.selected_translation, h.id)}
                          className="p-1.5 text-text-muted hover:text-text-primary hover:bg-surface-elevated rounded transition-colors"
                          title="Copy Translation"
                        >
                          {copiedId === h.id ? (
                            <Check className="w-3.5 h-3.5 text-emerald-500" />
                          ) : (
                            <Copy className="w-3.5 h-3.5" />
                          )}
                        </button>
                        <button
                          onClick={() => handleDelete(h.id)}
                          className="p-1.5 text-text-muted hover:text-danger hover:bg-danger/10 rounded transition-colors"
                          title="Delete record"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
      </div>

      {/* Details Modal */}
      {selectedItem && (
        <Modal
          isOpen={!!selectedItem}
          onClose={() => setSelectedItem(null)}
          title="Translation Audit Details"
          description="Detailed inspection of the prompt context, model latency, and alternative translation candidates."
          size="lg"
          footer={
            <Button variant="secondary" onClick={() => setSelectedItem(null)}>
              Close
            </Button>
          }
        >
          <div className="space-y-4 text-xs">
            <div>
              <span className="text-text-muted font-medium block mb-1">Source Text:</span>
              <div className="p-3 rounded-lg bg-surface-elevated border border-border-subtle text-text-primary font-sans leading-relaxed select-text">
                {selectedItem.source_text}
              </div>
            </div>

            <div>
              <span className="text-text-muted font-medium block mb-1">Selected Translation:</span>
              <div className="p-3 rounded-lg bg-surface-elevated border border-border-subtle text-emerald-700 dark:text-emerald-400 font-medium font-sans leading-relaxed select-text">
                {selectedItem.selected_translation}
              </div>
            </div>

            {selectedItem.candidate_translations && selectedItem.candidate_translations.length > 1 && (
              <div>
                <span className="text-text-muted font-medium block mb-1.5">All Candidate Options:</span>
                <div className="space-y-2">
                  {selectedItem.candidate_translations.map((c, i) => (
                    <div key={i} className="p-2.5 rounded-lg bg-surface-elevated border border-border-subtle text-text-secondary">
                      <div className="text-[10px] text-text-muted font-mono mb-1 flex items-center justify-between">
                        <span>Option {i+1} ({c.style})</span>
                        <span className="text-primary font-semibold">{Math.round(c.confidence * 100)}% confidence</span>
                      </div>
                      <div className="text-text-primary">{c.text}</div>
                      {c.reason && <div className="text-[11px] text-text-muted italic mt-1">{c.reason}</div>}
                    </div>
                  ))}
                </div>
              </div>
            )}

            <div className="p-3 rounded-lg bg-surface-elevated border border-border-subtle font-mono text-[11px] text-text-muted grid grid-cols-2 gap-2">
              <div>Provider: <strong className="text-primary">{selectedItem.provider}</strong></div>
              <div>Model: <strong className="text-text-primary">{selectedItem.model}</strong></div>
              <div>Latency: <strong className="text-text-primary">{selectedItem.latency_ms}ms</strong></div>
              <div>Style: <strong className="text-text-primary">{selectedItem.style}</strong></div>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
};
