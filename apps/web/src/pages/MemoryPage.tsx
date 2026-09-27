import React, { useState, useEffect } from 'react';
import { 
  Database, 
  Plus, 
  Search, 
  Trash2, 
  Layers, 
  CheckCircle2, 
  Sparkles,
  Bot,
  Filter
} from 'lucide-react';
import { apiClient } from '../api/client';
import { TranslationMemoryItem, Project } from '../types';
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
import { Select } from '../components/ui/Select';

interface MemoryPageProps {
  activeProject: Project | null;
}

export const MemoryPage: React.FC<MemoryPageProps> = ({ activeProject }) => {
  const toast = useToast();
  const confirm = useConfirm();
  const [memories, setMemories] = useState<TranslationMemoryItem[]>([]);
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);

  // Modal
  const [showModal, setShowModal] = useState(false);
  const [sourceText, setSourceText] = useState('');
  const [targetText, setTargetText] = useState('');
  const [style, setStyle] = useState('business');

  useEffect(() => {
    loadMemory();
  }, [activeProject, search]);

  const loadMemory = async () => {
    setLoading(true);
    try {
      const list = await apiClient.getTranslationMemory({
        project_id: activeProject?.id,
        search: search || undefined
      });
      setMemories(list);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  const handleCreate = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!sourceText.trim() || !targetText.trim()) return;

    try {
      await apiClient.createTranslationMemory({
        project_id: activeProject?.id || null,
        source_text: sourceText.trim(),
        target_text: targetText.trim(),
        style,
        provider: 'manual_entry',
        model: 'human',
        quality_signal: 1.0,
        user_edited: true
      });
      setShowModal(false);
      setSourceText('');
      setTargetText('');
      loadMemory();
      toast.success('Đã lưu mục Translation Memory thành công');
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || e.message, 'Failed to save memory');
    }
  };

  const handleDelete = async (id: string) => {
    const ok = await confirm({
      title: 'Xóa Translation Memory',
      message: 'Bạn có chắc chắn muốn xóa bản ghi bộ nhớ dịch này? Thao tác này không thể hoàn tác.',
      isDestructive: true,
      confirmText: 'Xóa bản ghi'
    });
    if (!ok) return;

    try {
      await apiClient.deleteTranslationMemory(id);
      loadMemory();
      toast.success('Đã xóa bản ghi Translation Memory');
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || e.message, 'Failed to delete memory');
    }
  };

  return (
    <div className="flex-1 flex flex-col h-screen overflow-hidden bg-canvas p-6 space-y-4">
      {/* Header */}
      <PageHeader
        title="Bộ nhớ dịch (TM)"
        actions={
          <Button
            variant="primary"
            onClick={() => setShowModal(true)}
          >
            <Plus className="w-4 h-4 mr-1.5" />
            Thêm câu mẫu
          </Button>
        }
      />

      {/* Search Bar */}
      <Card className="p-3 border border-border-subtle bg-surface">
        <div className="flex items-center gap-3">
          <div className="flex-1 relative">
            <Search className="w-4 h-4 text-text-muted absolute left-3 top-2.5 pointer-events-none" />
            <Input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Tìm kiếm câu mẫu tiếng Nhật hoặc tiếng Việt..."
              className="pl-9"
            />
          </div>
          <Badge variant="neutral" size="sm" className="font-mono text-xs">
            {memories.length} segments loaded
          </Badge>
        </div>
      </Card>

      {/* TM Table */}
      <Card className="flex-1 flex flex-col overflow-hidden p-0 border border-border-subtle bg-surface min-h-0">
        {loading ? (
          <div className="p-4">
            <TableSkeleton rows={8} columns={5} />
          </div>
        ) : memories.length === 0 ? (
          <div className="flex-1 flex items-center justify-center p-8">
            <EmptyState
              icon={<Database className="w-10 h-10" />}
              title="No memory segments found"
              description="No translation memory records match your current query or project scope."
              action={
                <Button variant="outline" size="sm" onClick={() => setShowModal(true)}>
                  <Plus className="w-3.5 h-3.5 mr-1" /> Add Segment
                </Button>
              }
            />
          </div>
        ) : (
          <div className="overflow-x-auto flex-1">
            <table className="w-full text-left text-xs">
              <thead className="bg-surface-elevated text-text-muted uppercase font-semibold text-[10px] tracking-wider border-b border-border-subtle sticky top-0 z-10">
                <tr>
                  <th className="py-3 px-4 w-1/3">Source Segment (JA)</th>
                  <th className="py-3 px-4 w-1/3">Target Segment (VI)</th>
                  <th className="py-3 px-4">Metadata</th>
                  <th className="py-3 px-4">Verification</th>
                  <th className="py-3 px-4 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border-subtle font-sans">
                {memories.map((m) => (
                  <tr key={m.id} className="hover:bg-surface-hover transition-colors">
                    <td className="py-3 px-4 text-text-primary font-medium leading-relaxed">
                      {m.source_text}
                    </td>
                    <td className="py-3 px-4 text-text-secondary leading-relaxed">
                      {m.target_text}
                    </td>
                    <td className="py-3 px-4 text-[11px] font-mono text-text-muted">
                      <div>Style: <span className="text-text-secondary">{m.style || 'business'}</span></div>
                      <div className="text-[10px]">Provider: {m.provider || 'human'}</div>
                    </td>
                    <td className="py-3 px-4">
                      {m.user_edited ? (
                        <Badge variant="success" size="sm" className="flex items-center gap-1 w-fit">
                          <CheckCircle2 className="w-3 h-3" /> User Verified
                        </Badge>
                      ) : (
                        <Badge variant="neutral" size="sm" className="flex items-center gap-1 w-fit">
                          <Bot className="w-3 h-3" /> AI Generated
                        </Badge>
                      )}
                    </td>
                    <td className="py-3 px-4 text-right">
                      <button
                        onClick={() => handleDelete(m.id)}
                        className="p-1.5 text-text-muted hover:text-danger hover:bg-danger/10 rounded transition-colors"
                        title="Delete TM Entry"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {/* Add Memory Modal */}
      <Modal
        isOpen={showModal}
        onClose={() => setShowModal(false)}
        title="Add Translation Memory Entry"
        description="Save verified translation pairs into TM for instant 100% exact or fuzzy similarity matching."
        size="md"
        footer={
          <>
            <Button variant="secondary" onClick={() => setShowModal(false)}>
              Cancel
            </Button>
            <Button variant="primary" onClick={() => handleCreate()}>
              Save Memory
            </Button>
          </>
        }
      >
        <form onSubmit={handleCreate} className="space-y-3.5 text-xs">
          <div>
            <label className="text-text-secondary font-medium block mb-1">Source Segment (Japanese) *</label>
            <textarea
              required
              value={sourceText}
              onChange={(e) => setSourceText(e.target.value)}
              placeholder="e.g. 本番環境にて障害が発生いたしました。"
              className="w-full h-20 bg-surface-elevated border border-border-subtle rounded-lg p-2.5 text-text-primary text-xs focus:outline-none focus:border-primary resize-none placeholder-text-muted"
            />
          </div>

          <div>
            <label className="text-text-secondary font-medium block mb-1">Target Segment (Vietnamese) *</label>
            <textarea
              required
              value={targetText}
              onChange={(e) => setTargetText(e.target.value)}
              placeholder="e.g. Đã xảy ra sự cố tại môi trường Production."
              className="w-full h-20 bg-surface-elevated border border-border-subtle rounded-lg p-2.5 text-text-primary text-xs focus:outline-none focus:border-primary resize-none placeholder-text-muted"
            />
          </div>

          <div>
            <label className="text-text-secondary font-medium block mb-1">Style Preset</label>
            <Select
              value={style}
              onChange={(val) => setStyle(val)}
              size="md"
              className="w-full"
              options={[
                { value: 'business', label: 'Business' },
                { value: 'technical', label: 'Technical' },
                { value: 'very_polite', label: 'Very Polite' },
                { value: 'natural', label: 'Natural' },
                { value: 'concise', label: 'Concise' },
              ]}
            />
          </div>
        </form>
      </Modal>
    </div>
  );
};
