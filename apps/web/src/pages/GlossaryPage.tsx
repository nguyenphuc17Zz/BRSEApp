import React, { useState, useEffect } from 'react';
import { 
  BookA, 
  Plus, 
  Search, 
  Trash2, 
  Filter, 
  BookOpen, 
  Tag,
  Check,
  FolderOpen,
  Globe
} from 'lucide-react';
import { apiClient } from '../api/client';
import { GlossaryTerm, Project } from '../types';
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

interface GlossaryPageProps {
  activeProject: Project | null;
  projects: Project[];
}

export const GlossaryPage: React.FC<GlossaryPageProps> = ({
  activeProject,
  projects
}) => {
  const toast = useToast();
  const confirm = useConfirm();
  const [terms, setTerms] = useState<GlossaryTerm[]>([]);
  const [search, setSearch] = useState('');
  const [selectedCategory, setSelectedCategory] = useState('');
  const [selectedScope, setSelectedScope] = useState('');
  const [selectedProjectFilter, setSelectedProjectFilter] = useState<string>(activeProject?.id || 'all');
  const [loading, setLoading] = useState(true);

  // Modal State
  const [showModal, setShowModal] = useState(false);
  const [modalProjectId, setModalProjectId] = useState<string>('');
  const [sourceTerm, setSourceTerm] = useState('');
  const [targetTerm, setTargetTerm] = useState('');
  const [definition, setDefinition] = useState('');
  const [category, setCategory] = useState('IT');
  const [scope, setScope] = useState('project');
  const [notes, setNotes] = useState('');

  const handleOpenCreateModal = () => {
    const defaultPid = (selectedProjectFilter !== 'all' && selectedProjectFilter !== 'global_only')
      ? selectedProjectFilter
      : (activeProject?.id || (projects.length > 0 ? projects[0].id : ''));
    setModalProjectId(defaultPid);
    setSourceTerm('');
    setTargetTerm('');
    setDefinition('');
    setNotes('');
    setCategory('IT');
    setScope('project');
    setShowModal(true);
  };

  useEffect(() => {
    if (activeProject?.id) {
      setSelectedProjectFilter(activeProject.id);
    }
  }, [activeProject]);

  useEffect(() => {
    loadGlossary();
  }, [selectedProjectFilter, search, selectedCategory, selectedScope]);

  const loadGlossary = async () => {
    setLoading(true);
    try {
      const list = await apiClient.getGlossary({
        project_id: selectedProjectFilter,
        search: search || undefined,
        category: selectedCategory || undefined,
        scope: selectedScope || undefined
      });
      setTerms(list);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  const handleCreate = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!sourceTerm.trim() || !targetTerm.trim()) return;

    const targetProjectId = scope === 'project' 
      ? (modalProjectId || (selectedProjectFilter !== 'all' && selectedProjectFilter !== 'global_only' ? selectedProjectFilter : (activeProject?.id || null)))
      : null;

    try {
      await apiClient.createGlossaryTerm({
        project_id: targetProjectId,
        scope,
        source_term: sourceTerm.trim(),
        target_term: targetTerm.trim(),
        definition,
        category,
        notes,
        priority: 1
      });
      setShowModal(false);
      setSourceTerm('');
      setTargetTerm('');
      setDefinition('');
      setNotes('');
      loadGlossary();
      toast.success('Đã lưu thuật ngữ thành công');
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || e.message, 'Failed to save glossary term');
    }
  };

  const handleDelete = async (id: string) => {
    const ok = await confirm({
      title: 'Xóa thuật ngữ',
      message: 'Bạn có chắc chắn muốn xóa thuật ngữ này khỏi Glossary? Thao tác này không thể hoàn tác.',
      isDestructive: true,
      confirmText: 'Xóa thuật ngữ'
    });
    if (!ok) return;

    try {
      await apiClient.deleteGlossaryTerm(id);
      loadGlossary();
      toast.success('Đã xóa thuật ngữ thành công');
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || e.message, 'Failed to delete term');
    }
  };

  const currentFilteredProject = projects.find((p) => p.id === selectedProjectFilter);

  const handleDeleteAllForProject = async () => {
    if (!currentFilteredProject) return;

    const projectTermsCount = terms.filter((t) => t.project_id === currentFilteredProject.id).length;

    const ok = await confirm({
      title: `Xóa toàn bộ thuật ngữ dự án "${currentFilteredProject.name}"`,
      message: `Bạn có chắc chắn muốn xóa tất cả thuật ngữ riêng của dự án "${currentFilteredProject.name}" (${projectTermsCount} thuật ngữ)? Các thuật ngữ Global dùng chung sẽ KHÔNG bị ảnh hưởng. Thao tác này không thể hoàn tác!`,
      isDestructive: true,
      confirmText: 'Xóa toàn bộ thuật ngữ dự án'
    });
    if (!ok) return;

    try {
      const res = await apiClient.deleteProjectGlossary(currentFilteredProject.id);
      await loadGlossary();
      toast.success(`Đã xóa thành công ${res.deleted_count} thuật ngữ của dự án "${currentFilteredProject.name}"!`);
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || e.message, 'Xóa thất bại');
    }
  };

  return (
    <div className="flex-1 flex flex-col h-screen overflow-hidden bg-canvas p-6 space-y-4">
      {/* Header */}
      <PageHeader
        title="Từ điển thuật ngữ"
        actions={
          <Button
            variant="primary"
            onClick={handleOpenCreateModal}
          >
            <Plus className="w-4 h-4 mr-1.5" />
            Thêm thuật ngữ
          </Button>
        }
      />

      {/* Filter Bar */}
      <Card className="p-3 border border-border-subtle bg-surface">
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex-1 min-w-[220px] relative">
            <Search className="w-4 h-4 text-text-muted absolute left-3 top-2.5 pointer-events-none" />
            <Input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search Japanese or Vietnamese terms..."
              className="pl-9"
            />
          </div>

          <Select
            value={selectedProjectFilter}
            onChange={(val) => setSelectedProjectFilter(val)}
            prefix={<FolderOpen className="w-3.5 h-3.5 text-primary" />}
            size="md"
            triggerClassName="min-w-[190px]"
            options={[
              { value: 'all', label: 'Tất cả dự án' },
              ...projects.map((p) => ({
                value: p.id,
                label: p.name,
                sublabel: p.code
              })),
              { value: 'global_only', label: 'Chỉ từ điển toàn cục' }
            ]}
          />

          <Select
            value={selectedScope}
            onChange={(val) => setSelectedScope(val)}
            size="md"
            triggerClassName="min-w-[130px]"
            options={[
              { value: '', label: 'All Scopes' },
              { value: 'project', label: 'Project Scope' },
              { value: 'global', label: 'Global Scope' },
              { value: 'company', label: 'Company Scope' },
            ]}
          />

          <Select
            value={selectedCategory}
            onChange={(val) => setSelectedCategory(val)}
            size="md"
            triggerClassName="min-w-[130px]"
            options={[
              { value: '', label: 'All Categories' },
              { value: 'IT', label: 'IT' },
              { value: 'Security', label: 'Security' },
              { value: 'Management', label: 'Management' },
              { value: 'Architecture', label: 'Architecture' },
              { value: 'Scope', label: 'Scope' },
            ]}
          />

          {currentFilteredProject && (
            <Button
              variant="danger"
              size="sm"
              onClick={handleDeleteAllForProject}
              className="ml-auto"
              title={`Xóa toàn bộ thuật ngữ của dự án ${currentFilteredProject.name}`}
            >
              <Trash2 className="w-3.5 h-3.5 mr-1.5" />
              <span>Xóa tất cả ({currentFilteredProject.name})</span>
            </Button>
          )}
        </div>
      </Card>

      {/* Terms Table */}
      <Card className="flex-1 flex flex-col overflow-hidden p-0 border border-border-subtle bg-surface min-h-0">
        {loading ? (
          <div className="p-4">
            <TableSkeleton rows={8} columns={6} />
          </div>
        ) : terms.length === 0 ? (
          <div className="flex-1 flex items-center justify-center p-8">
            <EmptyState
              icon={<BookA className="w-10 h-10" />}
              title="No terms found"
              description="No glossary entries match your current search or project filters."
              action={
                <Button variant="outline" size="sm" onClick={handleOpenCreateModal}>
                  <Plus className="w-3.5 h-3.5 mr-1" /> Add New Term
                </Button>
              }
            />
          </div>
        ) : (
          <div className="overflow-x-auto flex-1">
            <table className="w-full text-left text-xs">
              <thead className="bg-surface-elevated text-text-muted uppercase font-semibold text-[10px] tracking-wider border-b border-border-subtle sticky top-0 z-10">
                <tr>
                  <th className="py-3 px-4 w-1/4">Japanese (Source)</th>
                  <th className="py-3 px-4 w-1/4">Vietnamese (Target)</th>
                  <th className="py-3 px-4">Category</th>
                  <th className="py-3 px-4">Scope</th>
                  <th className="py-3 px-4">Notes / Context</th>
                  <th className="py-3 px-4 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border-subtle font-sans">
                {terms.map((term) => (
                  <tr key={term.id} className="hover:bg-surface-hover transition-colors">
                    <td className="py-3 px-4 font-semibold text-text-primary">
                      {term.source_term}
                    </td>
                    <td className="py-3 px-4 text-emerald-500 font-medium">
                      {term.target_term}
                    </td>
                    <td className="py-3 px-4">
                      <Badge variant="neutral" size="sm" className="font-mono text-[10px]">
                        {term.category || 'IT'}
                      </Badge>
                    </td>
                    <td className="py-3 px-4">
                      <Badge 
                        variant={term.scope === 'project' ? 'info' : 'purple'} 
                        size="sm"
                        className="text-[10px] uppercase font-semibold"
                      >
                        {term.scope} {term.project_name ? `(${term.project_name})` : ''}
                      </Badge>
                    </td>
                    <td className="py-3 px-4 text-text-muted text-[11px] max-w-xs truncate" title={term.notes || term.definition || undefined}>
                      {term.notes || term.definition || '—'}
                    </td>
                    <td className="py-3 px-4 text-right">
                      <button
                        onClick={() => handleDelete(term.id)}
                        className="p-1.5 text-text-muted hover:text-danger hover:bg-danger/10 rounded transition-colors"
                        title="Delete Term"
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

      {/* Add Term Modal */}
      <Modal
        isOpen={showModal}
        onClose={() => setShowModal(false)}
        title="Add New Terminology Entry"
        description="Establish mandatory source-to-target translations for AI consistency."
        size="md"
        footer={
          <>
            <Button variant="secondary" onClick={() => setShowModal(false)}>
              Cancel
            </Button>
            <Button variant="primary" onClick={() => handleCreate()}>
              Save Term
            </Button>
          </>
        }
      >
        <form onSubmit={handleCreate} className="space-y-3.5 text-xs">
          <div>
            <label className="text-text-secondary font-medium block mb-1">Source Term (Japanese / English) *</label>
            <Input
              required
              value={sourceTerm}
              onChange={(e) => setSourceTerm(e.target.value)}
              placeholder="e.g. 障害 or OAuth認証"
            />
          </div>

          <div>
            <label className="text-text-secondary font-medium block mb-1">Target Term (Vietnamese) *</label>
            <Input
              required
              value={targetTerm}
              onChange={(e) => setTargetTerm(e.target.value)}
              placeholder="e.g. sự cố or Xác thực OAuth"
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-text-secondary font-medium block mb-1">Scope</label>
              <Select
                value={scope}
                onChange={(val) => setScope(val)}
                size="md"
                className="w-full"
                options={[
                  { value: 'project', label: 'Project Scope' },
                  { value: 'global', label: 'Global (All Projects)' },
                  { value: 'company', label: 'Company Wide' },
                ]}
              />
            </div>

            <div>
              <label className="text-text-secondary font-medium block mb-1">Category</label>
              <Input
                value={category}
                onChange={(e) => setCategory(e.target.value)}
                placeholder="IT, Security, etc."
              />
            </div>
          </div>

          {scope === 'project' && (
            <div>
              <label className="text-text-secondary font-medium block mb-1">Áp dụng cho Dự án *</label>
              <Select
                value={modalProjectId}
                onChange={(val) => setModalProjectId(val)}
                size="md"
                className="w-full"
                options={projects.map((p) => ({
                  value: p.id,
                  label: p.name,
                  sublabel: p.code
                }))}
              />
            </div>
          )}

          <div>
            <label className="text-text-secondary font-medium block mb-1">Notes / Context of Usage</label>
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="When to apply this term..."
              className="w-full h-18 bg-surface-elevated border border-border-subtle rounded-lg px-3 py-2 text-text-primary text-xs focus:outline-none focus:border-primary resize-none placeholder-text-muted"
            />
          </div>
        </form>
      </Modal>
    </div>
  );
};
