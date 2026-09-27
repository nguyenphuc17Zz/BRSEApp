import React, { useState, useEffect } from 'react';
import { 
  Users, 
  UserPlus, 
  X, 
  Search, 
  Edit2, 
  Trash2, 
  Check, 
  Briefcase, 
  Building, 
  MessageSquare, 
  Sparkles,
  AlertCircle,
  ShieldAlert
} from 'lucide-react';
import { ProjectStakeholder, StakeholderCreatePayload } from '../../types';
import { apiClient } from '../../api/client';
import { useToast } from '../../context/ToastContext';
import { useConfirm } from '../../context/ConfirmDialogContext';
import { Select } from '../ui/Select';

interface StakeholderManagerModalProps {
  isOpen: boolean;
  onClose: () => void;
  projectId: string;
  projectName?: string;
  initialEditingStakeholder?: ProjectStakeholder | null;
  onStakeholderSelected?: (stakeholder: ProjectStakeholder) => void;
  onStakeholdersChanged?: () => void;
}

const PRESET_ROLES = [
  'Client PM',
  'Tech Lead',
  'Product Owner',
  'BrSE',
  'QA Lead',
  'Developer',
  'Designer',
  'Customer / Stakeholder'
];

const PRESET_ORGS = [
  'Khách hàng Nhật',
  'Nội bộ Offshore',
  'Đối tác (Partner)'
];

const PRESET_PLATFORMS = [
  { value: 'all', label: 'Tất cả (All Platforms)' },
  { value: 'line', label: 'LINE' },
  { value: 'slack', label: 'Slack' },
  { value: 'email', label: 'Email' },
  { value: 'meeting', label: 'Cuộc họp' }
];

export const StakeholderManagerModal: React.FC<StakeholderManagerModalProps> = ({
  isOpen,
  onClose,
  projectId,
  projectName = 'Dự án',
  initialEditingStakeholder,
  onStakeholderSelected,
  onStakeholdersChanged
}) => {
  const toast = useToast();
  const confirm = useConfirm();

  const [stakeholders, setStakeholders] = useState<ProjectStakeholder[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const [searchQuery, setSearchQuery] = useState<string>('');

  // Form state
  const [isEditing, setIsEditing] = useState<boolean>(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [formName, setFormName] = useState<string>('');
  const [formRole, setFormRole] = useState<string>('Client PM');
  const [formOrg, setFormOrg] = useState<string>('Khách hàng Nhật');
  const [formPlatform, setFormPlatform] = useState<string>('all');
  const [formNotes, setFormNotes] = useState<string>('');
  const [submitting, setSubmitting] = useState<boolean>(false);

  const fetchStakeholders = async () => {
    if (!projectId) return;
    try {
      setLoading(true);
      const list = await apiClient.getStakeholders(projectId);
      setStakeholders(list);
    } catch (err: any) {
      console.error('Failed to load stakeholders:', err);
      toast.error('Không thể tải danh sách người nhắn.', 'Lỗi');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (isOpen && projectId) {
      fetchStakeholders();
      if (initialEditingStakeholder) {
        handleStartEdit(initialEditingStakeholder);
      } else {
        resetForm();
      }
    }
  }, [isOpen, projectId, initialEditingStakeholder]);

  const resetForm = () => {
    setIsEditing(false);
    setEditingId(null);
    setFormName('');
    setFormRole('Client PM');
    setFormOrg('Khách hàng Nhật');
    setFormPlatform('all');
    setFormNotes('');
  };

  const handleStartEdit = (s: ProjectStakeholder) => {
    setIsEditing(true);
    setEditingId(s.id);
    setFormName(s.name);
    setFormRole(s.role);
    setFormOrg(s.organization);
    setFormPlatform(s.platform || 'all');
    setFormNotes(s.notes || '');
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!formName.trim()) {
      toast.warning('Vui lòng nhập tên người nhắn.', 'Thiếu thông tin');
      return;
    }

    try {
      setSubmitting(true);
      if (isEditing && editingId) {
        const updated = await apiClient.updateStakeholder(editingId, {
          name: formName.trim(),
          role: formRole,
          organization: formOrg,
          platform: formPlatform,
          notes: formNotes.trim() || undefined
        });
        toast.success(`Đã cập nhật thông tin: ${updated.name}`, 'Thành công');
        if (onStakeholderSelected) {
          onStakeholderSelected(updated);
        }
      } else {
        const created = await apiClient.createStakeholder({
          project_id: projectId,
          name: formName.trim(),
          role: formRole,
          organization: formOrg,
          platform: formPlatform,
          notes: formNotes.trim() || undefined
        });
        toast.success(`Đã thêm người nhắn: ${created.name}`, 'Thành công');
        if (onStakeholderSelected) {
          onStakeholderSelected(created);
        }
      }

      resetForm();
      await fetchStakeholders();
      if (onStakeholdersChanged) {
        onStakeholdersChanged();
      }
    } catch (err: any) {
      console.error('Submit error:', err);
      const msg = err.response?.data?.detail || err.message || 'Không thể lưu người nhắn.';
      toast.error(msg, 'Lỗi');
    } finally {
      setSubmitting(false);
    }
  };

  const handleDelete = async (s: ProjectStakeholder) => {
    const ok = await confirm({
      title: 'Xóa Người nhắn / Stakeholder',
      message: `Bạn có chắc chắn muốn xóa "${s.name}" khỏi danh sách người nhắn của dự án? Thao tác này không thể hoàn tác.`,
      isDestructive: true,
      confirmText: 'Xóa người này',
      cancelText: 'Hủy'
    });

    if (!ok) return;

    try {
      await apiClient.deleteStakeholder(s.id);
      toast.info(`Đã xóa ${s.name} khỏi danh sách.`, 'Đã xóa');
      if (editingId === s.id) {
        resetForm();
      }
      await fetchStakeholders();
      if (onStakeholdersChanged) {
        onStakeholdersChanged();
      }
    } catch (err: any) {
      console.error('Delete error:', err);
      toast.error('Không thể xóa người nhắn.', 'Lỗi');
    }
  };

  const handleCleanMockData = async () => {
    const ok = await confirm({
      title: 'Dọn sạch dữ liệu mẫu (Mock Stakeholders)',
      message: 'Thao tác này sẽ xóa toàn bộ các Stakeholder mẫu (như Suzuki-san, Tanaka-san, Yamada-san, An (BrSE)...) khỏi dự án. Bạn có chắc muốn thực hiện?',
      isDestructive: true,
      confirmText: 'Dọn sạch dữ liệu mẫu',
      cancelText: 'Hủy'
    });

    if (!ok) return;

    try {
      setLoading(true);
      const res = await apiClient.cleanMockStakeholders(projectId);
      toast.success(`Đã dọn sạch ${res.deleted_count} stakeholder mẫu!`, 'Hoàn tất');
      resetForm();
      await fetchStakeholders();
      if (onStakeholdersChanged) {
        onStakeholdersChanged();
      }
    } catch (err: any) {
      console.error('Clean mock error:', err);
      toast.error('Không thể dọn dữ liệu mẫu.', 'Lỗi');
    } finally {
      setLoading(false);
    }
  };

  if (!isOpen) return null;

  const filteredList = stakeholders.filter((s) => {
    if (!searchQuery.trim()) return true;
    const q = searchQuery.toLowerCase();
    return (
      s.name.toLowerCase().includes(q) ||
      s.role.toLowerCase().includes(q) ||
      s.organization.toLowerCase().includes(q) ||
      (s.notes && s.notes.toLowerCase().includes(q))
    );
  });

  const getRoleBadgeStyle = (role: string) => {
    const r = role.toLowerCase();
    if (r.includes('pm') || r.includes('po') || r.includes('owner')) {
      return 'bg-amber-500/10 text-amber-700 dark:text-amber-300 border-amber-500/20';
    }
    if (r.includes('tech') || r.includes('lead') || r.includes('architect')) {
      return 'bg-indigo-500/10 text-indigo-700 dark:text-indigo-300 border-indigo-500/20';
    }
    if (r.includes('brse')) {
      return 'bg-sky-500/10 text-sky-700 dark:text-sky-300 border-sky-500/20';
    }
    if (r.includes('qa') || r.includes('test')) {
      return 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-300 border-emerald-500/20';
    }
    return 'bg-surface-subtle text-text-secondary border-border-subtle';
  };

  const getOrgBadgeStyle = (org: string) => {
    const o = org.toLowerCase();
    if (o.includes('khách') || o.includes('client') || o.includes('nhật')) {
      return 'bg-rose-500/10 text-rose-700 dark:text-rose-300 border-rose-500/20';
    }
    if (o.includes('nội bộ') || o.includes('offshore')) {
      return 'bg-teal-500/10 text-teal-700 dark:text-teal-300 border-teal-500/20';
    }
    return 'bg-surface-subtle text-text-secondary border-border-subtle';
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/60 dark:bg-black/75 backdrop-blur-sm flex items-center justify-center p-4">
      <div className="bg-surface-elevated border border-border-default rounded-2xl shadow-modal w-full max-w-4xl max-h-[90vh] flex flex-col overflow-hidden animate-in fade-in duration-200">
        
        {/* Header */}
        <div className="px-6 py-4 border-b border-border-subtle flex items-center justify-between bg-surface-subtle/50">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-xl bg-primary/10 text-primary border border-primary/20">
              <Users className="w-5 h-5" />
            </div>
            <div>
              <h3 className="text-base font-bold text-text-primary tracking-tight flex items-center gap-2">
                Quản lý Người nhắn & Stakeholders
                <span className="text-xs font-mono font-normal px-2 py-0.5 rounded-full bg-primary/10 text-primary border border-primary/20">
                  {stakeholders.length} thành viên
                </span>
              </h3>
              <p className="text-xs text-text-secondary">
                Dự án: <span className="text-primary font-medium">{projectName}</span> — Danh sách đối tác, khách hàng và người phát biểu phục vụ phân tích AI.
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="text-text-muted hover:text-text-primary p-1.5 rounded-lg hover:bg-surface-hover transition"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content Body: Two Columns */}
        <div className="flex-1 overflow-y-auto p-6 grid grid-cols-1 md:grid-cols-12 gap-6">
          
          {/* Left Column: Form Thêm mới / Sửa */}
          <div className="md:col-span-5 bg-surface-subtle/60 border border-border-subtle rounded-xl p-4 flex flex-col space-y-3.5">
            <div className="flex items-center justify-between border-b border-border-subtle pb-2">
              <span className="text-xs font-bold text-text-primary uppercase tracking-wider flex items-center gap-1.5">
                {isEditing ? <Edit2 className="w-3.5 h-3.5 text-amber-500" /> : <UserPlus className="w-3.5 h-3.5 text-primary" />}
                {isEditing ? 'Chỉnh sửa Người nhắn' : 'Thêm Người nhắn Mới'}
              </span>
              {isEditing && (
                <button
                  type="button"
                  onClick={resetForm}
                  className="text-[11px] text-text-muted hover:text-text-primary underline cursor-pointer"
                >
                  Hủy sửa
                </button>
              )}
            </div>

            <form onSubmit={handleSubmit} className="space-y-3 text-xs">
              <div>
                <label className="text-text-secondary text-[11px] block mb-1 font-medium">
                  Tên người nhắn / Stakeholder <span className="text-rose-500">*</span>
                </label>
                <input
                  type="text"
                  value={formName}
                  onChange={(e) => setFormName(e.target.value)}
                  placeholder="Ví dụ: Suzuki-san, Tanaka (Tech Lead)..."
                  className="w-full bg-surface border border-border-default rounded-lg px-3 py-2 text-text-primary focus:outline-none focus:border-primary transition"
                  required
                />
              </div>

              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="text-text-secondary text-[11px] block mb-1 font-medium">Vai trò / Chức danh</label>
                  <Select
                    value={formRole}
                    onChange={(val) => setFormRole(val)}
                    size="md"
                    className="w-full"
                    options={PRESET_ROLES.map((r) => ({ value: r, label: r }))}
                  />
                </div>

                <div>
                  <label className="text-text-secondary text-[11px] block mb-1 font-medium">Tổ chức / Phía</label>
                  <Select
                    value={formOrg}
                    onChange={(val) => setFormOrg(val)}
                    size="md"
                    className="w-full"
                    options={PRESET_ORGS.map((o) => ({ value: o, label: o }))}
                  />
                </div>
              </div>

              <div>
                <label className="text-text-secondary text-[11px] block mb-1 font-medium">Nền tảng thường nhắn</label>
                <Select
                  value={formPlatform}
                  onChange={(val) => setFormPlatform(val)}
                  size="md"
                  className="w-full"
                  options={PRESET_PLATFORMS.map((p) => ({ value: p.value, label: p.label }))}
                />
              </div>

              <div>
                <label className="text-text-secondary text-[11px] block mb-1 font-medium">Ghi chú phụ trợ</label>
                <textarea
                  value={formNotes}
                  onChange={(e) => setFormNotes(e.target.value)}
                  rows={2}
                  placeholder="Ghi chú về thẩm quyền chốt yêu cầu, timeline, v.v."
                  className="w-full bg-surface border border-border-default rounded-lg px-3 py-2 text-text-primary focus:outline-none focus:border-primary transition resize-none"
                />
              </div>

              <div className="pt-2">
                <button
                  type="submit"
                  disabled={submitting || !formName.trim()}
                  className={`w-full py-2.5 px-4 rounded-xl text-white font-semibold flex items-center justify-center gap-2 transition shadow-sm cursor-pointer ${
                    isEditing
                      ? 'bg-amber-600 hover:bg-amber-500'
                      : 'bg-primary hover:opacity-95'
                  } disabled:opacity-50`}
                >
                  {submitting ? (
                    <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                  ) : isEditing ? (
                    <>
                      <Check className="w-4 h-4" />
                      <span>Cập nhật Thông tin</span>
                    </>
                  ) : (
                    <>
                      <UserPlus className="w-4 h-4" />
                      <span>Lưu Người nhắn</span>
                    </>
                  )}
                </button>
              </div>
            </form>
          </div>

          {/* Right Column: Danh sách Stakeholders */}
          <div className="md:col-span-7 flex flex-col space-y-3">
            {/* Search Bar & Clean Mock action */}
            <div className="flex items-center gap-2">
              <div className="relative flex-1">
                <Search className="w-3.5 h-3.5 text-text-muted absolute left-3 top-1/2 -translate-y-1/2" />
                <input
                  type="text"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="Tìm theo tên, vai trò hoặc tổ chức..."
                  className="w-full bg-surface border border-border-default rounded-xl pl-9 pr-3 py-2 text-xs text-text-primary focus:outline-none focus:border-primary transition"
                />
              </div>
              {searchQuery && (
                <button
                  onClick={() => setSearchQuery('')}
                  className="text-xs text-text-muted hover:text-text-primary px-2 py-1"
                >
                  Xóa tìm
                </button>
              )}
              <button
                type="button"
                onClick={handleCleanMockData}
                className="px-2.5 py-2 rounded-xl text-xs bg-rose-500/10 hover:bg-rose-500/20 text-rose-600 dark:text-rose-400 border border-rose-500/20 flex items-center gap-1.5 transition cursor-pointer shrink-0 font-medium"
                title="Xóa toàn bộ các dữ liệu mẫu đã tạo tự động để dọn sạch hệ thống"
              >
                <Trash2 className="w-3.5 h-3.5 text-rose-500" />
                <span>Dọn mẫu</span>
              </button>
            </div>

            {/* List */}
            <div className="space-y-2 max-h-[460px] overflow-y-auto pr-1">
              {loading ? (
                <div className="p-12 text-center text-text-muted text-xs">
                  <div className="w-5 h-5 border-2 border-primary/30 border-t-primary rounded-full animate-spin mx-auto mb-2" />
                  Đang tải danh sách người nhắn...
                </div>
              ) : filteredList.length === 0 ? (
                <div className="p-10 text-center text-text-muted text-xs bg-surface-subtle/50 rounded-xl border border-border-subtle">
                  <Users className="w-8 h-8 mx-auto mb-2 text-text-muted/60" />
                  {searchQuery ? (
                    <div>Không tìm thấy người nhắn nào khớp với từ khóa "{searchQuery}".</div>
                  ) : (
                    <div>Chưa có người nhắn nào. Hãy tạo người nhắn mới ở form bên trái!</div>
                  )}
                </div>
              ) : (
                filteredList.map((s) => {
                  const isCurrentEditing = editingId === s.id;
                  return (
                    <div
                      key={s.id}
                      className={`p-3 rounded-xl border transition flex items-start justify-between gap-3 ${
                        isCurrentEditing
                          ? 'bg-amber-500/10 border-amber-500/50 ring-1 ring-amber-500/30'
                          : 'bg-surface border-border-subtle hover:border-border-default'
                      }`}
                    >
                      <div className="flex items-start gap-3 min-w-0">
                        {/* Avatar Initials */}
                        <div className="w-8 h-8 rounded-lg bg-primary/10 border border-primary/20 text-primary font-bold text-xs flex items-center justify-center shrink-0 mt-0.5">
                          {s.name.slice(0, 2).toUpperCase()}
                        </div>

                        <div className="space-y-1 min-w-0">
                          <div className="flex items-center gap-2 flex-wrap">
                            <span className="font-semibold text-text-primary text-xs truncate">
                              {s.name}
                            </span>
                            <span className={`text-[10px] font-medium px-2 py-0.5 rounded-full border ${getRoleBadgeStyle(s.role)}`}>
                              {s.role}
                            </span>
                            <span className={`text-[10px] font-medium px-2 py-0.5 rounded-full border ${getOrgBadgeStyle(s.organization)}`}>
                              {s.organization}
                            </span>
                          </div>

                          {s.notes && (
                            <p className="text-[11px] text-text-secondary line-clamp-1 italic">
                              "{s.notes}"
                            </p>
                          )}

                          <div className="text-[10px] text-text-muted flex items-center gap-2 font-mono">
                            <span>Kênh: {s.platform || 'all'}</span>
                          </div>
                        </div>
                      </div>

                      {/* Action buttons */}
                      <div className="flex items-center gap-1 shrink-0">
                        {onStakeholderSelected && (
                          <button
                            type="button"
                            onClick={() => {
                              onStakeholderSelected(s);
                              toast.info(`Đã chọn: ${s.name}`, 'Người nhắn');
                              onClose();
                            }}
                            className="px-2.5 py-1 text-[11px] rounded-lg bg-primary/10 text-primary hover:bg-primary/20 border border-primary/20 transition cursor-pointer font-medium"
                            title="Chọn người này vào Smart Message Analyzer"
                          >
                            Chọn
                          </button>
                        )}
                        <button
                          type="button"
                          onClick={() => handleStartEdit(s)}
                          className="p-1.5 rounded-lg text-text-muted hover:text-amber-500 hover:bg-surface-hover transition"
                          title="Sửa thông tin"
                        >
                          <Edit2 className="w-3.5 h-3.5" />
                        </button>
                        <button
                          type="button"
                          onClick={() => handleDelete(s)}
                          className="p-1.5 rounded-lg text-text-muted hover:text-rose-500 hover:bg-surface-hover transition"
                          title="Xóa người này"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="px-6 py-3 border-t border-border-subtle bg-surface-subtle/50 flex items-center justify-between text-xs text-text-secondary">
          <span>
            💡 Mẹo: Khi chọn Người nhắn, AI sẽ tự động liên kết các yêu cầu và quyết định trích xuất vào hồ sơ của họ.
          </span>
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-1.5 rounded-xl bg-surface hover:bg-surface-hover border border-border-default text-text-primary transition font-medium cursor-pointer"
          >
            Đóng
          </button>
        </div>

      </div>
    </div>
  );
};
