import React, { useState, useEffect, useMemo } from 'react';
import { 
  MessageSquare, 
  Send, 
  Sparkles, 
  ShieldAlert, 
  Check, 
  Copy, 
  RefreshCw, 
  AlertTriangle,
  User,
  Users,
  UserPlus,
  Clock,
  CheckCircle2,
  ArrowRight,
  ExternalLink,
  Zap,
  Trash2,
  Edit2,
  BookOpen,
  Search,
  Filter,
  FileText,
  RotateCw
} from 'lucide-react';
import { apiClient } from '../api/client';
import { 
  Project, 
  LineMessageItem, 
  SmartReplyOption, 
  ProjectStakeholder, 
  ProviderInfo 
} from '../types';
import { useToast } from '../context/ToastContext';
import { useConfirm } from '../context/ConfirmDialogContext';
import { ProviderModelSelector } from '../components/ProviderModelSelector';
import { resolveHealthyModel } from '../utils/aiPreferences';
import { StakeholderManagerModal } from '../components/modals/StakeholderManagerModal';

interface LineSmartPageProps {
  activeProject: Project | null;
  onNavigateToBrSE?: () => void;
}

const QUICK_SAMPLES = [
  {
    label: "Hỏi Deadline Gấp",
    text: "明日までにこの外注管理の修正対応は可能でしょうか？急ぎで本番反映したいです。"
  },
  {
    label: "Hỏi Đặc Tả CSV",
    text: "CSVインポート時のキー項目と、画面上で修正可能な項目について仕様を教えてください。"
  },
  {
    label: "Hỏi Tiến Độ & Trách Nhiệm",
    text: "戻り日と確認日のカラム追加について、オフショア側の進捗はいかがでしょうか？"
  }
];

export const LineSmartPage: React.FC<LineSmartPageProps> = ({ activeProject, onNavigateToBrSE }) => {
  const toast = useToast();
  const confirm = useConfirm();

  const [messages, setMessages] = useState<LineMessageItem[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [simText, setSimText] = useState<string>('明日までにこの外注管理の修正対応は可能でしょうか？');
  const [simSender, setSimSender] = useState<string>('');
  const [isCustomSender, setIsCustomSender] = useState<boolean>(false);
  const [simulating, setSimulating] = useState<boolean>(false);
  const [regeneratingId, setRegeneratingId] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState<string>('');

  // AI Provider & Model State
  const [providers, setProviders] = useState<ProviderInfo[]>([]);
  const [selectedProvider, setSelectedProvider] = useState<string>('auto');
  const [selectedModel, setSelectedModel] = useState<string>('');

  // Stakeholders State & Modal
  const [stakeholders, setStakeholders] = useState<ProjectStakeholder[]>([]);
  const [isStakeholderModalOpen, setIsStakeholderModalOpen] = useState<boolean>(false);
  const [editingStakeholderForModal, setEditingStakeholderForModal] = useState<ProjectStakeholder | null>(null);

  // Send confirmation modal
  const [confirmModalOpen, setConfirmModalOpen] = useState<boolean>(false);
  const [selectedToken, setSelectedToken] = useState<string>('');
  const [selectedReplyText, setSelectedReplyText] = useState<string>('');
  const [sending, setSending] = useState<boolean>(false);
  const [sendSuccess, setSendSuccess] = useState<string | null>(null);

  const loadMessages = async () => {
    try {
      setLoading(true);
      const res = await apiClient.getLineMessages(activeProject?.id);
      setMessages(res.messages || []);
    } catch (e) {
      console.error("Failed loading LINE messages", e);
    } finally {
      setLoading(false);
    }
  };

  const loadStakeholders = async () => {
    if (!activeProject?.id) return;
    try {
      const list = await apiClient.getStakeholders(activeProject.id);
      setStakeholders(list);
      if (list.length > 0) {
        // Auto-select preferred line stakeholder or first item
        const lineUser = list.find(s => s.platform === 'line') || list[0];
        const hasCurrent = list.some(s => s.name === simSender);
        if (!hasCurrent && !isCustomSender) {
          setSimSender(lineUser.name);
        }
      } else {
        if (!isCustomSender) setSimSender('');
      }
    } catch (e) {
      console.error("Failed to load stakeholders", e);
    }
  };

  useEffect(() => {
    loadMessages();
    loadStakeholders();
  }, [activeProject?.id]);

  useEffect(() => {
    apiClient.getProviders().then((provs) => {
      setProviders(provs);
      const healthy = resolveHealthyModel(provs, 'auto', '');
      setSelectedProvider(healthy.provider);
      setSelectedModel(healthy.model);
    }).catch(console.error);
  }, []);

  const currentStakeholder = useMemo(() => {
    if (isCustomSender || !simSender) return null;
    return stakeholders.find(s => s.name === simSender) || null;
  }, [stakeholders, simSender, isCustomSender]);

  const handleQuickEditCurrentStakeholder = () => {
    if (!currentStakeholder) return;
    setEditingStakeholderForModal(currentStakeholder);
    setIsStakeholderModalOpen(true);
  };

  const handleQuickDeleteCurrentStakeholder = async () => {
    if (!currentStakeholder) return;
    const ok = await confirm({
      title: 'Xóa Người nhắn / Stakeholder',
      message: `Bạn có chắc chắn muốn xóa "${currentStakeholder.name}" (${currentStakeholder.role} · ${currentStakeholder.organization}) khỏi dự án? Thao tác này không thể hoàn tác.`,
      isDestructive: true,
      confirmText: 'Xóa người này',
      cancelText: 'Hủy'
    });
    if (!ok) return;

    try {
      await apiClient.deleteStakeholder(currentStakeholder.id);
      toast.info(`Đã xóa ${currentStakeholder.name} khỏi danh sách.`, 'Đã xóa');
      const remaining = stakeholders.filter(s => s.id !== currentStakeholder.id);
      setStakeholders(remaining);
      if (remaining.length > 0) {
        setSimSender(remaining[0].name);
      } else {
        setSimSender('');
      }
    } catch (err: any) {
      console.error('Delete stakeholder failed:', err);
      toast.error('Không thể xóa người nhắn.', 'Lỗi');
    }
  };

  const handleSimulate = async () => {
    if (!simText.trim()) return;
    try {
      setSimulating(true);
      const res = await apiClient.simulateLineMessage({
        text: simText.trim(),
        sender: simSender || 'Client (LINE)',
        project_id: activeProject?.id,
        provider: selectedProvider,
        model: selectedModel
      });
      await loadMessages();
      setSimText('');
      const syncCount = res.sync_result?.work_items_count || 0;
      toast.success(
        `Tin nhắn đã được bóc tách & lưu CSDL! (${syncCount} mục đồng bộ sang BrSE Inbox)`,
        "LINE Ingested"
      );
    } catch (e: any) {
      console.error("Simulate failed", e);
      toast.error(e.response?.data?.detail || e.message || "Không thể mô phỏng tin nhắn.");
    } finally {
      setSimulating(false);
    }
  };

  const handleDeleteMessage = async (msg: LineMessageItem) => {
    const targetId = msg.id || msg.message_id;
    const ok = await confirm({
      title: 'Xóa Tin nhắn LINE',
      message: `Bạn có chắc chắn muốn xóa tin nhắn "${msg.text.slice(0, 50)}..." khỏi CSDL? Thao tác này giúp dọn sạch tài nguyên hệ thống.`,
      isDestructive: true,
      confirmText: 'Xóa tin nhắn',
      cancelText: 'Hủy'
    });
    if (!ok) return;

    try {
      await apiClient.deleteLineMessage(targetId);
      toast.info("Đã xóa tin nhắn LINE khỏi CSDL.", "Đã xóa");
      setMessages(prev => prev.filter(m => (m.id || m.message_id) !== targetId));
    } catch (e: any) {
      console.error("Delete failed", e);
      toast.error("Không thể xóa tin nhắn.");
    }
  };

  const handleClearAllMessages = async () => {
    const ok = await confirm({
      title: 'Dọn Sạch Hòm thư LINE',
      message: `Thao tác này sẽ xóa toàn bộ ${messages.length} tin nhắn LINE đã lưu của dự án "${activeProject?.name || 'hiện tại'}". Bạn có chắc muốn thực hiện?`,
      isDestructive: true,
      confirmText: 'Dọn sạch toàn bộ',
      cancelText: 'Hủy'
    });
    if (!ok) return;

    try {
      const res = await apiClient.clearLineMessages(activeProject?.id);
      toast.success(`Đã dọn sạch ${res.deleted_count} tin nhắn LINE.`, "Hoàn tất");
      setMessages([]);
    } catch (e: any) {
      console.error("Clear all failed", e);
      toast.error("Không thể dọn sạch hòm thư.");
    }
  };

  const handleRegenerateReply = async (msg: LineMessageItem) => {
    const targetId = msg.id || msg.message_id;
    try {
      setRegeneratingId(targetId);
      const res = await apiClient.regenerateLineReply(targetId, selectedProvider, selectedModel);
      setMessages(prev => prev.map(m => {
        if ((m.id || m.message_id) === targetId) {
          return {
            ...m,
            detected_intent: res.detected_intent,
            commitment_warning: res.commitment_warning,
            suggested_replies: res.suggested_replies,
            rag_sources: res.rag_sources
          };
        }
        return m;
      }));
      toast.success("Đã sinh lại câu trả lời với Model đã chọn!", "Smart Reply");
    } catch (e: any) {
      console.error("Regenerate failed", e);
      toast.error("Không thể sinh lại câu trả lời.");
    } finally {
      setRegeneratingId(null);
    }
  };

  const handleOpenSendConfirmation = (token: string, text: string) => {
    setSelectedToken(token);
    setSelectedReplyText(text);
    setConfirmModalOpen(true);
  };

  const handleConfirmSend = async () => {
    try {
      setSending(true);
      await apiClient.sendLineReply(selectedToken, selectedReplyText);
      setSendSuccess("Reply transmitted successfully to LINE!");
      toast.success("Phản hồi đã được truyền thành công tới LINE Bot API!", "Đã gửi");
      setConfirmModalOpen(false);
      setTimeout(() => setSendSuccess(null), 4000);
    } catch (e: any) {
      toast.error(`Gửi thất bại: ${e.message}`);
    } finally {
      setSending(false);
    }
  };

  const filteredMessages = useMemo(() => {
    if (!searchQuery.trim()) return messages;
    const q = searchQuery.toLowerCase();
    return messages.filter(m => 
      m.text.toLowerCase().includes(q) ||
      m.sender.toLowerCase().includes(q) ||
      (m.detected_intent && m.detected_intent.toLowerCase().includes(q))
    );
  }, [messages, searchQuery]);

  return (
    <div className="flex-1 overflow-y-auto bg-slate-950 p-6 space-y-6">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-slate-800 pb-5">
        <div className="space-y-1">
          <div className="flex items-center gap-2.5 flex-wrap">
            <span className="px-2 py-0.5 rounded text-[11px] font-bold uppercase tracking-wider bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">
              Official LINE Bot API
            </span>
            <span className="px-2 py-0.5 rounded text-[11px] font-medium bg-sky-500/10 text-sky-400 border border-sky-500/20 flex items-center gap-1.5">
              <span className="relative flex h-1.5 w-1.5">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-emerald-500"></span>
              </span>
              RAG & Zero-Waste CSDL: Active
            </span>
            <h1 className="text-xl font-bold text-white tracking-tight">LINE Smart Workspace & Reply Inbox</h1>
          </div>
          <p className="text-xs text-slate-400">
            Hòm thư thông minh LINE: Tự động tra cứu <span className="text-sky-300 font-medium">Project Document RAG</span> và quyết định dự án để sinh câu trả lời chuẩn Nhật, bảo vệ cam kết và đồng bộ sang BrSE Inbox.
          </p>
        </div>

        <div className="flex items-center gap-2.5 flex-wrap">
          {/* Provider & Model Selector */}
          <div className="bg-slate-900 border border-slate-800 rounded-xl px-2 py-1 flex items-center">
            <ProviderModelSelector
              providers={providers}
              selectedProvider={selectedProvider}
              onChangeProvider={setSelectedProvider}
              selectedModel={selectedModel}
              onChangeModel={setSelectedModel}
            />
          </div>

          {onNavigateToBrSE && (
            <button
              onClick={onNavigateToBrSE}
              className="flex items-center gap-2 px-3.5 py-2 rounded-xl bg-sky-600/20 text-sky-300 border border-sky-500/40 hover:bg-sky-600/30 text-xs font-semibold transition shadow-sm cursor-pointer"
            >
              <span>Xem Thẻ trong BrSE Inbox</span>
              <ArrowRight className="w-3.5 h-3.5" />
            </button>
          )}
        </div>
      </div>

      {sendSuccess && (
        <div className="bg-emerald-950/40 border border-emerald-500/40 rounded-xl p-3 text-xs text-emerald-300 flex items-center gap-2 animate-in fade-in">
          <CheckCircle2 className="w-4 h-4 text-emerald-400" />
          {sendSuccess}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left Column: Simulator / Webhook Receiver */}
        <div className="lg:col-span-5 bg-slate-900/70 border border-slate-800 rounded-xl p-4 space-y-4">
          <div className="flex items-center justify-between border-b border-slate-800 pb-2.5">
            <h2 className="text-sm font-semibold text-white flex items-center gap-2">
              <MessageSquare className="w-4 h-4 text-emerald-400" />
              Incoming Message Simulator
            </h2>
            <span className="text-[10px] px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 font-medium">
              Webhook Active
            </span>
          </div>

          <div className="space-y-3.5 text-xs">
            {/* Sender / Stakeholder Selection */}
            <div>
              <div className="flex items-center justify-between mb-1">
                <label className="text-[11px] text-slate-400 font-medium">Sender Name / Client Identity</label>
                <button
                  type="button"
                  onClick={() => {
                    setEditingStakeholderForModal(null);
                    setIsStakeholderModalOpen(true);
                  }}
                  className="text-[10.5px] text-sky-400 hover:text-sky-300 flex items-center gap-1 cursor-pointer transition font-medium"
                  title="Quản lý danh sách Người nhắn & Stakeholders"
                >
                  <Users className="w-3 h-3" />
                  <span>Quản lý ({stakeholders.length})</span>
                </button>
              </div>

              {isCustomSender ? (
                <div className="flex items-center gap-1.5">
                  <input
                    type="text"
                    value={simSender}
                    onChange={(e) => setSimSender(e.target.value)}
                    placeholder="Nhập tên người gửi..."
                    className="flex-1 bg-slate-950 border border-slate-800 rounded-lg px-3 py-1.5 text-slate-200 text-xs focus:ring-1 focus:ring-emerald-500 focus:outline-none"
                    autoFocus
                  />
                  <button
                    type="button"
                    onClick={() => {
                      setIsCustomSender(false);
                      if (stakeholders.length > 0) setSimSender(stakeholders[0].name);
                    }}
                    className="px-2.5 py-1.5 text-[10.5px] rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 transition shrink-0 cursor-pointer"
                  >
                    Chọn lại
                  </button>
                </div>
              ) : (
                <div className="flex items-center gap-1.5">
                  <select
                    value={simSender}
                    onChange={(e) => {
                      if (e.target.value === '__custom__') {
                        setIsCustomSender(true);
                        setSimSender('');
                      } else {
                        setSimSender(e.target.value);
                      }
                    }}
                    className="flex-1 min-w-0 bg-slate-950 border border-slate-800 rounded-lg px-3 py-1.5 text-slate-200 text-xs focus:ring-1 focus:ring-emerald-500 focus:outline-none cursor-pointer truncate"
                  >
                    {stakeholders.length === 0 && (
                      <option value="">Chưa có người nhắn nào</option>
                    )}
                    {stakeholders.map((s) => (
                      <option key={s.id} value={s.name}>
                        {s.name} ({s.role} · {s.organization})
                      </option>
                    ))}
                    <option value="__custom__">➕ Nhập tên tùy chỉnh...</option>
                  </select>

                  <div className="flex items-center gap-1 shrink-0">
                    <button
                      type="button"
                      onClick={() => {
                        setEditingStakeholderForModal(null);
                        setIsStakeholderModalOpen(true);
                      }}
                      className="p-1.5 rounded-lg text-slate-400 hover:text-emerald-400 hover:bg-slate-800 border border-slate-800/80 transition cursor-pointer"
                      title="Thêm người nhắn mới"
                    >
                      <UserPlus className="w-3.5 h-3.5" />
                    </button>
                    <button
                      type="button"
                      onClick={handleQuickEditCurrentStakeholder}
                      disabled={!currentStakeholder}
                      className="p-1.5 rounded-lg text-slate-400 hover:text-amber-300 hover:bg-slate-800 disabled:opacity-30 disabled:cursor-not-allowed border border-slate-800/80 transition cursor-pointer"
                      title={currentStakeholder ? `Sửa thông tin: ${currentStakeholder.name}` : 'Chọn một người để sửa'}
                    >
                      <Edit2 className="w-3.5 h-3.5" />
                    </button>
                    <button
                      type="button"
                      onClick={handleQuickDeleteCurrentStakeholder}
                      disabled={!currentStakeholder}
                      className="p-1.5 rounded-lg text-slate-400 hover:text-rose-400 hover:bg-slate-800 disabled:opacity-30 disabled:cursor-not-allowed border border-slate-800/80 transition cursor-pointer"
                      title={currentStakeholder ? `Xóa người này: ${currentStakeholder.name}` : 'Chọn một người để xóa'}
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>
              )}
            </div>

            {/* Japanese Message Input */}
            <div>
              <label className="text-[11px] text-slate-400 block mb-1 font-medium">Japanese Message Text</label>
              <textarea
                value={simText}
                onChange={(e) => setSimText(e.target.value)}
                rows={4}
                placeholder="e.g. 明日までにこの修正対応は可能でしょうか？"
                className="w-full bg-slate-950 border border-slate-800 rounded-lg p-2.5 text-slate-200 font-mono text-xs resize-none focus:outline-none focus:border-emerald-500"
              />

              {/* Quick Sample Chips */}
              <div className="flex items-center gap-1.5 flex-wrap mt-2">
                <span className="text-[10px] text-slate-500">Mẫu nhanh:</span>
                {QUICK_SAMPLES.map((qs, qIdx) => (
                  <button
                    key={qIdx}
                    type="button"
                    onClick={() => setSimText(qs.text)}
                    className="text-[10px] px-2 py-0.5 rounded-md bg-slate-800/80 hover:bg-slate-700 text-slate-300 border border-slate-700/60 transition cursor-pointer"
                    title={qs.text}
                  >
                    {qs.label}
                  </button>
                ))}
              </div>
            </div>

            <button
              onClick={handleSimulate}
              disabled={simulating || !simText.trim()}
              className="flex items-center justify-center gap-2 w-full py-2.5 px-4 rounded-xl bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white text-xs font-semibold transition shadow-md cursor-pointer"
            >
              {simulating ? (
                <>
                  <div className="w-3.5 h-3.5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                  <span>Tra cứu RAG & Sinh câu trả lời...</span>
                </>
              ) : (
                <>
                  <Sparkles className="w-3.5 h-3.5" />
                  <span>Mô phỏng Tin nhắn & Tra cứu RAG</span>
                </>
              )}
            </button>
          </div>

          <div className="border-t border-slate-800 pt-3 text-[11px] text-slate-400 space-y-1.5">
            <div className="font-semibold text-slate-300 flex items-center gap-1.5">
              <ShieldAlert className="w-3.5 h-3.5 text-emerald-400" />
              Chính sách Bảo vệ Cam kết (Safety Guardrails):
            </div>
            <div>• AI tra cứu tài liệu đặc tả thật từ Project Document RAG (FTS5 BM25).</div>
            <div>• Tuyệt đối không tự ý hứa hẹn deadline khi chưa có quyết định được duyệt (`確認保留`).</div>
            <div>• Tự động trích xuất Yêu cầu/Lỗi vào BrSE Inbox và lưu CSDL SQLite bền vững (Zero-Waste).</div>
          </div>
        </div>

        {/* Right Column: Messages & Smart Reply Drafts */}
        <div className="lg:col-span-7 bg-slate-900/70 border border-slate-800 rounded-xl p-4 space-y-4">
          <div className="flex items-center justify-between border-b border-slate-800 pb-3 gap-2 flex-wrap">
            <div className="flex items-center gap-2">
              <h2 className="text-sm font-semibold text-white">Captured Messages & Proposed Replies</h2>
              <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-slate-800 text-slate-300 border border-slate-700">
                {messages.length} tin nhắn
              </span>
            </div>

            <div className="flex items-center gap-2">
              {/* Search Bar */}
              <div className="relative w-40 sm:w-56">
                <Search className="w-3.5 h-3.5 text-slate-400 absolute left-2.5 top-1/2 -translate-y-1/2" />
                <input
                  type="text"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="Lọc tin nhắn..."
                  className="w-full bg-slate-950 border border-slate-800 rounded-lg pl-8 pr-2.5 py-1 text-xs text-slate-200 focus:outline-none focus:border-emerald-500"
                />
              </div>

              <button
                onClick={loadMessages}
                className="p-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 transition cursor-pointer"
                title="Tải lại danh sách tin nhắn"
              >
                <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
              </button>

              {messages.length > 0 && (
                <button
                  onClick={handleClearAllMessages}
                  className="px-2.5 py-1.5 rounded-lg bg-rose-500/10 hover:bg-rose-500/20 text-rose-300 border border-rose-500/20 text-xs font-medium flex items-center gap-1 transition cursor-pointer"
                  title="Xóa toàn bộ tin nhắn LINE đã lưu trong dự án"
                >
                  <Trash2 className="w-3.5 h-3.5 text-rose-400" />
                  <span>Dọn sạch ({messages.length})</span>
                </button>
              )}
            </div>
          </div>

          <div className="space-y-4 max-h-[600px] overflow-y-auto pr-1">
            {loading ? (
              <div className="p-12 text-center text-slate-500 text-xs">
                <div className="w-5 h-5 border-2 border-emerald-500/30 border-t-emerald-500 rounded-full animate-spin mx-auto mb-2" />
                Đang tải hòm thư tin nhắn LINE...
              </div>
            ) : filteredMessages.length === 0 ? (
              <div className="p-12 text-center text-slate-500 text-xs bg-slate-950/40 rounded-xl border border-slate-800/60">
                <MessageSquare className="w-8 h-8 mx-auto mb-2 text-slate-600" />
                {searchQuery ? (
                  <div>Không tìm thấy tin nhắn nào khớp với từ khóa "{searchQuery}".</div>
                ) : (
                  <div>Chưa có tin nhắn LINE nào được lưu trong CSDL. Hãy nhập tin nhắn ở cột bên trái để mô phỏng!</div>
                )}
              </div>
            ) : (
              filteredMessages.map((m, idx) => {
                const isRegenerating = regeneratingId === (m.id || m.message_id);
                const syncData = m.sync_result || {};
                const extractedCount = syncData.work_items_count || (
                  (syncData.requirements || 0) + (syncData.bugs || 0) + (syncData.deadlines || 0) + (syncData.decisions || 0)
                );

                return (
                  <div key={m.id || idx} className="bg-slate-950/70 border border-slate-800 rounded-xl p-4 space-y-3 relative hover:border-slate-700/80 transition">
                    {/* Message Header */}
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex items-center gap-2.5">
                        <div className="w-8 h-8 rounded-lg bg-emerald-500/20 border border-emerald-500/30 text-emerald-400 flex items-center justify-center font-bold text-xs">
                          {m.sender[0]?.toUpperCase() || 'U'}
                        </div>
                        <div>
                          <div className="text-xs font-bold text-white flex items-center gap-2">
                            {m.sender}
                            {m.detected_intent && (
                              <span className="px-2 py-0.5 rounded text-[9.5px] font-bold uppercase tracking-wider bg-slate-800 text-sky-400 border border-slate-700">
                                Intent: {m.detected_intent}
                              </span>
                            )}
                          </div>
                          <div className="text-[10px] text-slate-500 flex items-center gap-1 font-mono">
                            <Clock className="w-2.5 h-2.5" />
                            {m.timestamp ? new Date(m.timestamp).toLocaleString('vi-VN') : 'Vừa xong'}
                          </div>
                        </div>
                      </div>

                      <div className="flex items-center gap-1">
                        <button
                          type="button"
                          onClick={() => handleRegenerateReply(m)}
                          disabled={isRegenerating}
                          className="p-1.5 rounded-lg text-slate-400 hover:text-sky-300 hover:bg-slate-800 transition cursor-pointer"
                          title="Sinh lại gợi ý câu trả lời bằng Model hiện tại"
                        >
                          <RotateCw className={`w-3.5 h-3.5 ${isRegenerating ? 'animate-spin text-sky-400' : ''}`} />
                        </button>
                        <button
                          type="button"
                          onClick={() => handleDeleteMessage(m)}
                          className="p-1.5 rounded-lg text-slate-400 hover:text-rose-400 hover:bg-slate-800 transition cursor-pointer"
                          title="Xóa tin nhắn này khỏi CSDL (Dọn tài nguyên)"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    </div>

                    {/* Japanese Text */}
                    <div className="text-xs text-slate-200 bg-slate-900/90 p-3 rounded-lg border border-slate-800/80 font-mono leading-relaxed">
                      "{m.text}"
                    </div>

                    {/* RAG Spec Sources Grounding Badge */}
                    {m.rag_sources && m.rag_sources.length > 0 && (
                      <div className="bg-sky-950/20 border border-sky-500/20 rounded-lg p-2.5 text-[11px] space-y-1">
                        <div className="text-sky-300 font-semibold flex items-center gap-1.5 text-[10.5px]">
                          <BookOpen className="w-3 h-3 text-sky-400" />
                          <span>Tham chiếu Đặc tả Dự án (RAG Spec Grounding):</span>
                        </div>
                        <div className="flex items-center gap-1.5 flex-wrap">
                          {m.rag_sources.map((src, sIdx) => (
                            <span 
                              key={sIdx}
                              className="px-2 py-0.5 rounded bg-sky-500/10 text-sky-300 border border-sky-500/20 font-mono text-[10px]"
                              title={src.snippet}
                            >
                              📄 {src.file_name} #{src.chunk_index}
                            </span>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Extracted Items Chip (Sync with BrSE Work Inbox) */}
                    {extractedCount > 0 && (
                      <div className="flex items-center justify-between bg-emerald-950/20 border border-emerald-500/20 rounded-lg px-2.5 py-1.5 text-[11px]">
                        <span className="text-emerald-300 font-medium flex items-center gap-1.5">
                          <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
                          Đã trích xuất: {syncData.requirements ? `${syncData.requirements} Yêu cầu · ` : ''}
                          {syncData.bugs ? `${syncData.bugs} Lỗi · ` : ''}
                          {syncData.deadlines ? `${syncData.deadlines} Hạn chót · ` : ''}
                          {syncData.decisions ? `${syncData.decisions} Quyết định` : ''}
                        </span>
                        {onNavigateToBrSE && (
                          <button
                            type="button"
                            onClick={onNavigateToBrSE}
                            className="text-[10px] text-sky-400 hover:text-sky-300 underline font-medium cursor-pointer"
                          >
                            Xem trong Inbox ↗
                          </button>
                        )}
                      </div>
                    )}

                    {/* Commitment Warning Alert */}
                    {m.commitment_warning && (
                      <div className="bg-amber-950/30 border border-amber-500/40 rounded-lg p-2.5 text-[11px] text-amber-300 flex items-start gap-2">
                        <AlertTriangle className="w-3.5 h-3.5 text-amber-400 shrink-0 mt-0.5" />
                        <div>
                          <span className="font-semibold">Cảnh báo cam kết:</span> {m.commitment_warning}
                        </div>
                      </div>
                    )}

                    {/* Reply Proposals */}
                    {m.suggested_replies && m.suggested_replies.length > 0 && (
                      <div className="space-y-2 border-t border-slate-800 pt-3">
                        <div className="text-[11px] font-semibold text-slate-300 flex items-center justify-between">
                          <span className="flex items-center gap-1.5">
                            <Sparkles className="w-3 h-3 text-sky-400" />
                            Gợi ý Trả lời Thông minh (Fact & Commitment Protected)
                          </span>
                        </div>

                        <div className="space-y-2">
                          {m.suggested_replies.map((rep, rIdx) => (
                            <div key={rIdx} className="bg-slate-900/70 border border-slate-800 hover:border-slate-700/90 p-3 rounded-lg space-y-1.5 text-xs transition">
                              <div className="flex items-center justify-between text-[11px]">
                                <span className="font-semibold text-sky-400">{rep.style}</span>
                                <span className="text-slate-500 text-[10px] italic">{rep.rationale}</span>
                              </div>
                              <p className="text-slate-200 font-sans leading-relaxed">{rep.text}</p>
                              <div className="flex items-center justify-end gap-2 pt-1">
                                <button
                                  type="button"
                                  onClick={() => {
                                    navigator.clipboard.writeText(rep.text);
                                    toast.info("Đã sao chép nội dung vào Clipboard!");
                                  }}
                                  className="px-2.5 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 text-[11px] flex items-center gap-1 cursor-pointer transition"
                                >
                                  <Copy className="w-3 h-3" /> Copy
                                </button>
                                <button
                                  type="button"
                                  onClick={() => {
                                    if (!m.reply_token) {
                                      toast.error("Không tìm thấy Reply Token hợp lệ từ webhook của tin nhắn này");
                                      return;
                                    }
                                    handleOpenSendConfirmation(m.reply_token, rep.text);
                                  }}
                                  className="px-3 py-1 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-[11px] font-semibold flex items-center gap-1 transition cursor-pointer shadow-sm"
                                >
                                  <Send className="w-3 h-3" /> Review & Gửi
                                </button>
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                );
              })
            )}
          </div>
        </div>
      </div>

      {/* Explicit Human Confirmation Modal */}
      {confirmModalOpen && (
        <div className="fixed inset-0 bg-black/70 backdrop-blur-sm z-50 flex items-center justify-center p-4 animate-in fade-in">
          <div className="bg-slate-900 border border-slate-700 rounded-xl max-w-lg w-full p-5 space-y-4 shadow-2xl">
            <div className="flex items-center gap-2 text-amber-400 text-sm font-bold">
              <AlertTriangle className="w-5 h-5" />
              Human Confirmation Required (Guardrail Level 4)
            </div>

            <p className="text-xs text-slate-300">
              AI không bao giờ tự ý gửi tin nhắn ra ngoài. Vui lòng kiểm tra và chỉnh sửa nội dung phản hồi tiếng Nhật trước khi chính thức gửi tới khách hàng:
            </p>

            <div>
              <label className="text-[11px] text-slate-400 block mb-1 font-medium">Nội dung tin nhắn xem trước / chỉnh sửa</label>
              <textarea
                value={selectedReplyText}
                onChange={(e) => setSelectedReplyText(e.target.value)}
                rows={5}
                className="w-full bg-slate-950 border border-slate-800 rounded-lg p-2.5 text-xs text-slate-200 font-mono resize-none focus:outline-none focus:border-emerald-500"
              />
            </div>

            <div className="flex items-center justify-end gap-2.5 pt-2">
              <button
                type="button"
                onClick={() => setConfirmModalOpen(false)}
                className="px-3.5 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs transition cursor-pointer"
              >
                Hủy bỏ
              </button>
              <button
                type="button"
                onClick={handleConfirmSend}
                disabled={sending}
                className="px-4 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold flex items-center gap-1.5 transition cursor-pointer shadow-md"
              >
                {sending ? (
                  <>
                    <div className="w-3.5 h-3.5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                    <span>Đang gửi tới LINE...</span>
                  </>
                ) : (
                  <>
                    <Send className="w-3.5 h-3.5" />
                    <span>Xác nhận & Gửi tới LINE</span>
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Stakeholder CRUD Manager Modal */}
      {activeProject && (
        <StakeholderManagerModal
          isOpen={isStakeholderModalOpen}
          onClose={() => {
            setIsStakeholderModalOpen(false);
            setEditingStakeholderForModal(null);
          }}
          projectId={activeProject.id}
          projectName={activeProject.name}
          initialEditingStakeholder={editingStakeholderForModal}
          onStakeholderSelected={(s) => {
            setSimSender(s.name);
            setIsCustomSender(false);
          }}
          onStakeholdersChanged={() => {
            loadStakeholders();
          }}
        />
      )}
    </div>
  );
};
