import React, { useState, useEffect } from 'react';
import { 
  Database, 
  Plus, 
  Search, 
  Trash2, 
  Layers, 
  CheckCircle2, 
  Sparkles,
  Bot
} from 'lucide-react';
import { apiClient } from '../api/client';
import { TranslationMemoryItem, Project } from '../types';
import { useToast } from '../context/ToastContext';
import { useConfirm } from '../context/ConfirmDialogContext';
import { TableSkeleton } from '../components/skeletons/TableSkeleton';

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

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
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
    <div className="flex-1 flex flex-col h-screen overflow-hidden bg-slate-950 p-6 space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold text-white flex items-center gap-2">
            <Database className="w-5 h-5 text-indigo-400" />
            Translation Memory (TM)
          </h2>
          <p className="text-xs text-slate-400">
            Intelligent repository of verified past translations used for hybrid semantic reference.
          </p>
        </div>

        <button
          onClick={() => setShowModal(true)}
          className="px-3.5 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold flex items-center gap-1.5 shadow-md shadow-indigo-600/20"
        >
          <Plus className="w-3.5 h-3.5" />
          Add Memory Segment
        </button>
      </div>

      {/* Search Bar */}
      <div className="p-3 rounded-xl border border-slate-800 bg-slate-900/50 flex items-center gap-3">
        <div className="flex-1 relative">
          <Search className="w-4 h-4 text-slate-400 absolute left-3 top-2.5" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search past translated segments..."
            className="w-full bg-slate-850 border border-slate-700 rounded-lg pl-9 pr-3 py-1.5 text-xs text-slate-100 focus:outline-none focus:border-indigo-500"
          />
        </div>
        <span className="text-xs text-slate-400 font-mono">
          {memories.length} segments loaded
        </span>
      </div>

      {/* TM Table */}
      <div className="flex-1 rounded-xl border border-slate-800 bg-slate-900/50 overflow-hidden flex flex-col">
        {loading ? (
          <TableSkeleton rows={6} columns={5} />
        ) : (
          <div className="overflow-x-auto flex-1">
            <table className="w-full text-left text-xs text-slate-300">
              <thead className="bg-slate-850/90 text-slate-400 uppercase font-semibold text-[10px] tracking-wider border-b border-slate-800">
                <tr>
                  <th className="py-3 px-4 w-1/3">Source Segment</th>
                  <th className="py-3 px-4 w-1/3">Target Segment</th>
                  <th className="py-3 px-4">Metadata</th>
                  <th className="py-3 px-4">Quality</th>
                  <th className="py-3 px-4 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60 font-sans">
                {memories.map((m) => (
                  <tr key={m.id} className="hover:bg-slate-800/40 transition-colors">
                    <td className="py-3 px-4 text-white font-medium">
                      {m.source_text}
                    </td>
                    <td className="py-3 px-4 text-slate-200">
                      {m.target_text}
                    </td>
                    <td className="py-3 px-4 text-[11px] text-slate-400 font-mono">
                      <div>Style: {m.style || 'business'}</div>
                      <div className="text-slate-500">Provider: {m.provider || 'human'}</div>
                    </td>
                    <td className="py-3 px-4">
                      {m.user_edited ? (
                        <span className="px-2 py-0.5 rounded bg-emerald-950 text-emerald-300 border border-emerald-800/40 text-[10px] font-semibold flex items-center gap-1 w-fit">
                          <CheckCircle2 className="w-3 h-3" /> User Verified
                        </span>
                      ) : (
                        <span className="px-2 py-0.5 rounded bg-slate-850 text-slate-400 border border-slate-700 text-[10px] flex items-center gap-1 w-fit">
                          <Bot className="w-3 h-3" /> AI Generated
                        </span>
                      )}
                    </td>
                    <td className="py-3 px-4 text-right">
                      <button
                        onClick={() => handleDelete(m.id)}
                        className="p-1 text-slate-500 hover:text-rose-400 transition-colors"
                        title="Delete TM Entry"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </td>
                  </tr>
                ))}

                {memories.length === 0 && !loading && (
                  <tr>
                    <td colSpan={5} className="py-8 text-center text-slate-500 text-xs">
                      No translation memory segments found.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Add Memory Modal */}
      {showModal && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <form
            onSubmit={handleCreate}
            className="bg-slate-900 border border-slate-700 rounded-xl max-w-md w-full p-5 shadow-2xl space-y-4"
          >
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <h3 className="text-sm font-semibold text-white">Add Translation Memory Entry</h3>
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
                <label className="text-slate-300 block mb-1">Source Segment (Japanese) *</label>
                <textarea
                  required
                  value={sourceText}
                  onChange={(e) => setSourceText(e.target.value)}
                  placeholder="e.g. 本番環境にて障害が発生いたしました。"
                  className="w-full h-16 bg-slate-850 border border-slate-700 rounded p-2.5 text-slate-100 focus:outline-none focus:border-indigo-500 resize-none"
                />
              </div>

              <div>
                <label className="text-slate-300 block mb-1">Target Segment (Vietnamese) *</label>
                <textarea
                  required
                  value={targetText}
                  onChange={(e) => setTargetText(e.target.value)}
                  placeholder="e.g. Đã xảy ra sự cố tại môi trường Production."
                  className="w-full h-16 bg-slate-850 border border-slate-700 rounded p-2.5 text-slate-100 focus:outline-none focus:border-indigo-500 resize-none"
                />
              </div>

              <div>
                <label className="text-slate-300 block mb-1">Style Preset</label>
                <select
                  value={style}
                  onChange={(e) => setStyle(e.target.value)}
                  className="w-full bg-slate-850 border border-slate-700 rounded px-2.5 py-1.5 text-slate-100 focus:outline-none focus:border-indigo-500"
                >
                  <option value="business">Business</option>
                  <option value="technical">Technical</option>
                  <option value="very_polite">Very Polite</option>
                  <option value="natural">Natural</option>
                  <option value="concise">Concise</option>
                </select>
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
                className="px-4 py-1.5 rounded bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold"
              >
                Save Memory
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
};
