import React, { useState, useEffect } from 'react';
import { 
  BookA, 
  Plus, 
  Search, 
  Trash2, 
  Edit, 
  Filter, 
  BookOpen, 
  Tag,
  Check
} from 'lucide-react';
import { apiClient } from '../api/client';
import { GlossaryTerm, Project } from '../types';
import { useToast } from '../context/ToastContext';
import { useConfirm } from '../context/ConfirmDialogContext';
import { TableSkeleton } from '../components/skeletons/TableSkeleton';

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

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
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
    <div className="flex-1 flex flex-col h-screen overflow-hidden bg-slate-950 p-6 space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold text-white flex items-center gap-2">
            <BookA className="w-5 h-5 text-emerald-400" />
            Glossary & Terminology
          </h2>
          <p className="text-xs text-slate-400">
            Hierarchical glossary repository ensuring technical IT translation consistency.
          </p>
        </div>

        <button
          onClick={handleOpenCreateModal}
          className="px-3.5 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold flex items-center gap-1.5 shadow-md shadow-emerald-600/20"
        >
          <Plus className="w-3.5 h-3.5" />
          Add Term
        </button>
      </div>

      {/* Filter Bar */}
      <div className="flex flex-wrap items-center gap-3 p-3 rounded-xl border border-slate-800 bg-slate-900/50">
        <div className="flex-1 min-w-[200px] relative">
          <Search className="w-4 h-4 text-slate-400 absolute left-3 top-2.5" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search Japanese or Vietnamese terms..."
            className="w-full bg-slate-850 border border-slate-700 rounded-lg pl-9 pr-3 py-1.5 text-xs text-slate-100 focus:outline-none focus:border-emerald-500"
          />
        </div>

        <select
          value={selectedProjectFilter}
          onChange={(e) => setSelectedProjectFilter(e.target.value)}
          className="bg-slate-850 border border-slate-700 text-xs rounded-lg px-3 py-1.5 text-slate-200 focus:outline-none focus:border-emerald-500 font-medium"
        >
          <option value="all">📂 Tất cả dự án (All Projects)</option>
          {projects.map((p) => (
            <option key={p.id} value={p.id}>
              📁 {p.name}
            </option>
          ))}
          <option value="global_only">🌐 Chỉ thuật ngữ Global</option>
        </select>

        <select
          value={selectedScope}
          onChange={(e) => setSelectedScope(e.target.value)}
          className="bg-slate-850 border border-slate-700 text-xs rounded-lg px-3 py-1.5 text-slate-300 focus:outline-none focus:border-emerald-500"
        >
          <option value="">All Scopes</option>
          <option value="project">Project Scope</option>
          <option value="global">Global Scope</option>
          <option value="company">Company Scope</option>
        </select>

        <select
          value={selectedCategory}
          onChange={(e) => setSelectedCategory(e.target.value)}
          className="bg-slate-850 border border-slate-700 text-xs rounded-lg px-3 py-1.5 text-slate-300 focus:outline-none focus:border-emerald-500"
        >
          <option value="">All Categories</option>
          <option value="IT">IT</option>
          <option value="Security">Security</option>
          <option value="Management">Management</option>
          <option value="Architecture">Architecture</option>
          <option value="Scope">Scope</option>
        </select>

        {currentFilteredProject && (
          <button
            onClick={handleDeleteAllForProject}
            className="px-3 py-1.5 rounded-lg border border-rose-800/60 bg-rose-950/40 hover:bg-rose-900/60 text-rose-300 text-xs font-medium flex items-center gap-1.5 transition ml-auto"
            title={`Xóa toàn bộ thuật ngữ của dự án ${currentFilteredProject.name}`}
          >
            <Trash2 className="w-3.5 h-3.5 text-rose-400" />
            <span>Xóa tất cả ({currentFilteredProject.name})</span>
          </button>
        )}
      </div>

      {/* Terms Table */}
      <div className="flex-1 rounded-xl border border-slate-800 bg-slate-900/50 overflow-hidden flex flex-col">
        {loading ? (
          <TableSkeleton rows={6} columns={6} />
        ) : (
          <div className="overflow-x-auto flex-1">
            <table className="w-full text-left text-xs text-slate-300">
              <thead className="bg-slate-850/90 text-slate-400 uppercase font-semibold text-[10px] tracking-wider border-b border-slate-800">
                <tr>
                  <th className="py-3 px-4">Japanese (Source)</th>
                  <th className="py-3 px-4">Vietnamese (Target)</th>
                  <th className="py-3 px-4">Category</th>
                  <th className="py-3 px-4">Scope</th>
                  <th className="py-3 px-4">Notes / Context</th>
                  <th className="py-3 px-4 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60 font-sans">
                {terms.map((term) => (
                  <tr key={term.id} className="hover:bg-slate-800/40 transition-colors">
                    <td className="py-3 px-4 font-semibold text-white">
                      {term.source_term}
                    </td>
                    <td className="py-3 px-4 text-emerald-400 font-medium">
                      {term.target_term}
                    </td>
                    <td className="py-3 px-4">
                      <span className="px-2 py-0.5 rounded bg-slate-800 text-slate-300 text-[10px] font-mono border border-slate-700">
                        {term.category || 'IT'}
                      </span>
                    </td>
                    <td className="py-3 px-4">
                      <span className={`px-2 py-0.5 rounded text-[10px] uppercase font-semibold ${
                        term.scope === 'project'
                          ? 'bg-sky-950 text-sky-300 border border-sky-800/40'
                          : 'bg-indigo-950 text-indigo-300 border border-indigo-800/40'
                      }`}>
                        {term.scope} {term.project_name ? `(${term.project_name})` : ''}
                      </span>
                    </td>
                    <td className="py-3 px-4 text-slate-400 text-[11px]">
                      {term.notes || term.definition || '-'}
                    </td>
                    <td className="py-3 px-4 text-right">
                      <button
                        onClick={() => handleDelete(term.id)}
                        className="p-1 text-slate-500 hover:text-rose-400 transition-colors"
                        title="Delete Term"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </td>
                  </tr>
                ))}

                {terms.length === 0 && !loading && (
                  <tr>
                    <td colSpan={6} className="py-8 text-center text-slate-500 text-xs">
                      No glossary terms found matching filter.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Add Term Modal */}
      {showModal && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <form
            onSubmit={handleCreate}
            className="bg-slate-900 border border-slate-700 rounded-xl max-w-md w-full p-5 shadow-2xl space-y-4"
          >
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <h3 className="text-sm font-semibold text-white">Add New Terminology Entry</h3>
              <button
                type="button"
                onClick={() => setShowModal(false)}
                className="text-slate-400 hover:text-white text-xs"
              >
                ✕
              </button>
            </div>

            <div className="space-y-3 text-xs">
              <div>
                <label className="text-slate-300 block mb-1">Source Term (Japanese / English) *</label>
                <input
                  type="text"
                  required
                  value={sourceTerm}
                  onChange={(e) => setSourceTerm(e.target.value)}
                  placeholder="e.g. 障害 or OAuth認証"
                  className="w-full bg-slate-850 border border-slate-700 rounded px-2.5 py-1.5 text-slate-100 focus:outline-none focus:border-emerald-500"
                />
              </div>

              <div>
                <label className="text-slate-300 block mb-1">Target Term (Vietnamese) *</label>
                <input
                  type="text"
                  required
                  value={targetTerm}
                  onChange={(e) => setTargetTerm(e.target.value)}
                  placeholder="e.g. sự cố or Xác thực OAuth"
                  className="w-full bg-slate-850 border border-slate-700 rounded px-2.5 py-1.5 text-slate-100 focus:outline-none focus:border-emerald-500"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-slate-300 block mb-1">Scope</label>
                  <select
                    value={scope}
                    onChange={(e) => setScope(e.target.value)}
                    className="w-full bg-slate-850 border border-slate-700 rounded px-2.5 py-1.5 text-slate-100 focus:outline-none focus:border-emerald-500"
                  >
                    <option value="project">Project Scope</option>
                    <option value="global">Global (All Projects)</option>
                    <option value="company">Company Wide</option>
                  </select>
                </div>

                <div>
                  <label className="text-slate-300 block mb-1">Category</label>
                  <input
                    type="text"
                    value={category}
                    onChange={(e) => setCategory(e.target.value)}
                    placeholder="IT, Security, etc."
                    className="w-full bg-slate-850 border border-slate-700 rounded px-2.5 py-1.5 text-slate-100 focus:outline-none focus:border-emerald-500"
                  />
                </div>
              </div>

              {scope === 'project' && (
                <div>
                  <label className="text-slate-300 block mb-1">Áp dụng cho Dự án *</label>
                  <select
                    value={modalProjectId}
                    onChange={(e) => setModalProjectId(e.target.value)}
                    required
                    className="w-full bg-slate-850 border border-slate-700 rounded px-2.5 py-1.5 text-slate-100 focus:outline-none focus:border-emerald-500"
                  >
                    {projects.map((p) => (
                      <option key={p.id} value={p.id}>
                        📁 {p.name}
                      </option>
                    ))}
                  </select>
                </div>
              )}

              <div>
                <label className="text-slate-300 block mb-1">Notes / Context of Usage</label>
                <textarea
                  value={notes}
                  onChange={(e) => setNotes(e.target.value)}
                  placeholder="When to apply this term..."
                  className="w-full h-16 bg-slate-850 border border-slate-700 rounded px-2.5 py-1.5 text-slate-100 focus:outline-none focus:border-emerald-500 resize-none"
                />
              </div>
            </div>

            <div className="flex items-center justify-end gap-2 pt-2 border-t border-slate-800">
              <button
                type="button"
                onClick={() => setShowModal(false)}
                className="px-3 py-1.5 rounded bg-slate-800 text-slate-300 text-xs hover:bg-slate-700"
              >
                Cancel
              </button>
              <button
                type="submit"
                className="px-4 py-1.5 rounded bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold"
              >
                Save Term
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
};
