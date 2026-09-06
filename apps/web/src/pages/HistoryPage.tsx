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
  AlertTriangle
} from 'lucide-react';
import { apiClient } from '../api/client';
import { HistoryItem, Project } from '../types';
import { useToast } from '../context/ToastContext';
import { useConfirm } from '../context/ConfirmDialogContext';
import { TableSkeleton } from '../components/skeletons/TableSkeleton';

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
    <div className="flex-1 flex flex-col h-screen overflow-hidden bg-slate-950 p-6 space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold text-white flex items-center gap-2">
            <HistoryIcon className="w-5 h-5 text-sky-400" />
            Translation History & Audit Logs
          </h2>
          <p className="text-xs text-slate-400">
            Search and review all historical translations, model routes, and quality signals.
          </p>
        </div>
      </div>

      {/* Search Filter */}
      <div className="p-3 rounded-xl border border-slate-800 bg-slate-900/50 flex items-center gap-3">
        <div className="flex-1 relative">
          <Search className="w-4 h-4 text-slate-400 absolute left-3 top-2.5" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search source or translated text in history..."
            className="w-full bg-slate-850 border border-slate-700 rounded-lg pl-9 pr-3 py-1.5 text-xs text-slate-100 focus:outline-none focus:border-sky-500"
          />
        </div>
        <span className="text-xs text-slate-400 font-mono">
          {history.length} records
        </span>
      </div>

      {/* History Table */}
      <div className="flex-1 rounded-xl border border-slate-800 bg-slate-900/50 overflow-hidden flex flex-col">
        {loading ? (
          <TableSkeleton rows={6} columns={6} />
        ) : (
          <div className="overflow-x-auto flex-1">
            <table className="w-full text-left text-xs text-slate-300">
              <thead className="bg-slate-850/90 text-slate-400 uppercase font-semibold text-[10px] tracking-wider border-b border-slate-800">
                <tr>
                  <th className="py-3 px-4 w-1/4">Source Text</th>
                  <th className="py-3 px-4 w-1/3">Selected Translation</th>
                  <th className="py-3 px-4">AI Route & Latency</th>
                  <th className="py-3 px-4">Signals</th>
                  <th className="py-3 px-4">Time</th>
                  <th className="py-3 px-4 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60 font-sans">
                {history.map((h) => (
                  <tr
                    key={h.id}
                    onClick={() => setSelectedItem(h)}
                    className="hover:bg-slate-800/40 transition-colors cursor-pointer"
                  >
                    <td className="py-3 px-4 text-white font-medium truncate max-w-xs">
                      {h.source_text}
                    </td>
                    <td className="py-3 px-4 text-slate-200 truncate max-w-sm">
                      {h.selected_translation}
                    </td>
                    <td className="py-3 px-4 font-mono text-[11px] text-slate-400">
                      <div className="text-sky-400">{h.provider}</div>
                      <div className="text-slate-500">{h.model} • {h.latency_ms}ms</div>
                    </td>
                    <td className="py-3 px-4">
                      <div className="flex items-center gap-1.5">
                        {h.ambiguity_detected && (
                          <span className="px-1.5 py-0.5 rounded bg-indigo-950 text-indigo-300 border border-indigo-800/40 text-[10px]">
                            Ambiguous
                          </span>
                        )}
                        {h.qa_warnings && h.qa_warnings.length > 0 && (
                          <span className="px-1.5 py-0.5 rounded bg-amber-950 text-amber-300 border border-amber-800/40 text-[10px]">
                            QA Warning
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="py-3 px-4 text-slate-500 text-[11px] font-mono whitespace-nowrap">
                      {new Date(h.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                    </td>
                    <td className="py-3 px-4 text-right">
                      <div className="flex items-center justify-end gap-1" onClick={(e) => e.stopPropagation()}>
                        <button
                          onClick={() => handleCopy(h.selected_translation, h.id)}
                          className="p-1 text-slate-400 hover:text-white"
                          title="Copy Translation"
                        >
                          {copiedId === h.id ? (
                            <Check className="w-3.5 h-3.5 text-emerald-400" />
                          ) : (
                            <Copy className="w-3.5 h-3.5" />
                          )}
                        </button>
                        <button
                          onClick={() => handleDelete(h.id)}
                          className="p-1 text-slate-500 hover:text-rose-400"
                          title="Delete record"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}

                {history.length === 0 && !loading && (
                  <tr>
                    <td colSpan={6} className="py-8 text-center text-slate-500 text-xs">
                      No translation history found.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Details Modal */}
      {selectedItem && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-700 rounded-xl max-w-xl w-full p-5 shadow-2xl space-y-4">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <h3 className="text-sm font-semibold text-white flex items-center gap-2">
                <HistoryIcon className="w-4 h-4 text-sky-400" />
                Translation Details
              </h3>
              <button
                onClick={() => setSelectedItem(null)}
                className="text-slate-400 hover:text-white text-xs"
              >
                ✕ Close
              </button>
            </div>

            <div className="space-y-3 text-xs">
              <div>
                <span className="text-slate-400 block mb-1">Source Text:</span>
                <div className="p-2.5 rounded bg-slate-850 border border-slate-800 text-slate-100 font-sans leading-relaxed">
                  {selectedItem.source_text}
                </div>
              </div>

              <div>
                <span className="text-slate-400 block mb-1">Selected Translation:</span>
                <div className="p-2.5 rounded bg-slate-850 border border-slate-800 text-emerald-300 font-sans leading-relaxed">
                  {selectedItem.selected_translation}
                </div>
              </div>

              {selectedItem.candidate_translations && selectedItem.candidate_translations.length > 1 && (
                <div>
                  <span className="text-slate-400 block mb-1">All Candidate Options:</span>
                  <div className="space-y-1.5">
                    {selectedItem.candidate_translations.map((c, i) => (
                      <div key={i} className="p-2 rounded bg-slate-850 border border-slate-800 text-slate-200">
                        <div className="text-[10px] text-slate-400 font-mono mb-0.5">
                          Option {i+1} ({c.style} • {Math.round(c.confidence * 100)}%)
                        </div>
                        <div>{c.text}</div>
                        {c.reason && <div className="text-[10px] text-slate-500 italic mt-0.5">{c.reason}</div>}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              <div className="p-2.5 rounded bg-slate-850 border border-slate-800 font-mono text-[11px] text-slate-400 grid grid-cols-2 gap-2">
                <div>Provider: <strong className="text-sky-400">{selectedItem.provider}</strong></div>
                <div>Model: <strong className="text-slate-200">{selectedItem.model}</strong></div>
                <div>Latency: <strong className="text-slate-200">{selectedItem.latency_ms}ms</strong></div>
                <div>Style: <strong className="text-slate-200">{selectedItem.style}</strong></div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
