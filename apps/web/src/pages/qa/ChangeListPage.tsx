import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { GitBranch, Plus, Sparkles } from 'lucide-react';
import { apiClient } from '../../api/client';
import { Project } from '../../types';
import { ChangeRecord } from '../../types/qa';
import { useToast } from '../../context/ToastContext';
import { PageHeader } from '../../components/ui/PageHeader';
import { Card, CardContent } from '../../components/ui/Card';
import { Badge } from '../../components/ui/Badge';
import { Button } from '../../components/ui/Button';
import { Input } from '../../components/ui/Input';
import { Select } from '../../components/ui/Select';
import { Modal } from '../../components/ui/Modal';
import { EmptyState } from '../../components/ui/EmptyState';
import { statusVariant } from './qaHelpers';

interface Props {
  activeProject: Project | null;
}

const SOURCES = ['', 'requirement_update', 'spec', 'decision', 'meeting', 'ac_change',
  'api_spec', 'ui_change', 'bug_fix', 'change_request', 'document'];

export const ChangeListPage: React.FC<Props> = ({ activeProject }) => {
  const [changes, setChanges] = useState<ChangeRecord[]>([]);
  const [suggests, setSuggests] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [sourceFilter, setSourceFilter] = useState('');
  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState({
    source: 'requirement_update', requirement_id: '', decision_id: '',
    bug_id: '', change_summary: '', hint: '',
  });
  const toast = useToast();
  const navigate = useNavigate();

  const load = async () => {
    if (!activeProject) { setLoading(false); return; }
    setLoading(true);
    try {
      const [list, sug] = await Promise.all([
        apiClient.qaListChanges(activeProject.id, {
          source: sourceFilter || undefined,
          search: search || undefined,
        }),
        apiClient.qaSuggestChanges(activeProject.id).catch(() => []),
      ]);
      setChanges(list);
      setSuggests(sug);
    } catch {
      toast.error('Không tải được changes');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); /* eslint-disable-next-line */ }, [activeProject?.id]);

  const create = async (preset?: any) => {
    if (!activeProject) return;
    const payload = preset ? {
      source: preset.suggested_source,
      requirement_id: preset.item_type === 'REQUIREMENT' ? preset.work_item_id : undefined,
      decision_id: preset.item_type === 'DECISION' ? preset.work_item_id : undefined,
      bug_id: preset.item_type === 'BUG' ? preset.work_item_id : undefined,
      change_summary: preset.title,
    } : {
      ...form,
      requirement_id: form.requirement_id || undefined,
      decision_id: form.decision_id || undefined,
      bug_id: form.bug_id || undefined,
    };
    try {
      const c = await apiClient.qaCreateChange(activeProject.id, payload);
      toast.success(`Đã tạo ${c.change_code}`);
      setShowCreate(false);
      setForm({ source: 'requirement_update', requirement_id: '', decision_id: '', bug_id: '', change_summary: '', hint: '' });
      navigate(`/qa/changes/${c.id}`);
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || 'Tạo thất bại');
    }
  };

  return (
    <div className="flex-1 overflow-y-auto p-4 sm:p-6 space-y-4">
      <PageHeader
        title="Changes"
        description="Mỗi thay đổi (requirement, spec, decision, bug fix...) được record để phân tích impact."
        icon={<GitBranch className="w-5 h-5" />}
        actions={
          <Button size="sm" leftIcon={<Plus className="w-3.5 h-3.5" />} onClick={() => setShowCreate(true)}>
            Record Change
          </Button>
        }
      />
      {!activeProject && (
        <Card><CardContent><p className="text-sm text-text-secondary">Chọn một project để bắt đầu.</p></CardContent></Card>
      )}
      {activeProject && suggests.length > 0 && (
        <Card>
          <CardContent>
            <div className="flex items-center gap-2 text-sm font-semibold text-text-primary mb-2">
              <Sparkles className="w-4 h-4 text-primary" /> Gợi ý change chưa record
            </div>
            {suggests.slice(0, 6).map((s: any) => (
              <div key={s.work_item_id} className="flex items-center gap-2 text-xs py-1">
                <Badge variant="neutral">{s.item_type}</Badge>
                <span className="flex-1 truncate">{s.title}</span>
                <Button size="sm" variant="subtle" onClick={() => create(s)}>Record</Button>
              </div>
            ))}
          </CardContent>
        </Card>
      )}
      {activeProject && (
        <Card>
          <CardContent className="space-y-3">
            <div className="flex flex-col sm:flex-row gap-2">
              <div className="flex-1">
                <Input placeholder="Tìm change (mã, nội dung...)" value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  onKeyDown={(e) => { if (e.key === 'Enter') load(); }} />
              </div>
              <div className="w-full sm:w-48">
                <Select value={sourceFilter} onChange={(v) => setSourceFilter(v as string)}
                  options={SOURCES.map((s) => ({ value: s, label: s === '' ? 'Mọi nguồn' : s }))} />
              </div>
              <Button size="sm" onClick={load}>Lọc</Button>
            </div>
            {loading && <p className="text-xs text-text-muted">Đang tải...</p>}
            {!loading && changes.length === 0 && (
              <EmptyState title="Chưa có change" description="Record change đầu tiên từ requirement, bug fix hoặc decision." />
            )}
            <div className="divide-y divide-border-subtle">
              {changes.map((c) => (
                <button key={c.id} onClick={() => navigate(`/qa/changes/${c.id}`)}
                  className="w-full text-left py-2.5 px-1 hover:bg-surface-hover rounded-lg">
                  <div className="flex items-center gap-1.5 flex-wrap">
                    <span className="font-mono text-xs text-primary font-semibold">{c.change_code}</span>
                    <Badge variant="info">{c.source}</Badge>
                    <Badge variant={c.risk_level === 'CRITICAL' || c.risk_level === 'HIGH' ? 'danger' : c.risk_level === 'MEDIUM' ? 'warning' : 'neutral'}>
                      {c.risk_level}
                    </Badge>
                    <Badge variant={statusVariant(c.status)}>{c.status}</Badge>
                  </div>
                  <div className="text-sm text-text-primary mt-0.5 line-clamp-2">{c.change_summary}</div>
                  <div className="text-[11px] text-text-muted">{(c.categories || []).join(' · ')}</div>
                </button>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
      <Modal isOpen={showCreate} onClose={() => setShowCreate(false)} title="Record Change" size="lg">
        <div className="space-y-2.5">
          <div>
            <label className="text-xs font-semibold text-text-secondary">Nguồn change</label>
            <Select value={form.source} onChange={(v) => setForm({ ...form, source: v as string })}
              options={SOURCES.filter(Boolean).map((s) => ({ value: s, label: s }))} />
          </div>
          <div>
            <label className="text-xs font-semibold text-text-secondary">Requirement ID (nếu có)</label>
            <Input value={form.requirement_id} onChange={(e) => setForm({ ...form, requirement_id: e.target.value })} placeholder="Work item UUID" />
          </div>
          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="text-xs font-semibold text-text-secondary">Decision ID</label>
              <Input value={form.decision_id} onChange={(e) => setForm({ ...form, decision_id: e.target.value })} />
            </div>
            <div>
              <label className="text-xs font-semibold text-text-secondary">Bug ID</label>
              <Input value={form.bug_id} onChange={(e) => setForm({ ...form, bug_id: e.target.value })} />
            </div>
          </div>
          <div>
            <label className="text-xs font-semibold text-text-secondary">Tóm tắt thay đổi</label>
            <Input value={form.change_summary} onChange={(e) => setForm({ ...form, change_summary: e.target.value })}
              placeholder="VD: Search chuyển từ exact sang partial match" />
          </div>
          <div>
            <label className="text-xs font-semibold text-text-secondary">Gợi ý thêm cho AI (optional)</label>
            <Input value={form.hint} onChange={(e) => setForm({ ...form, hint: e.target.value })} />
          </div>
          <div className="flex justify-end gap-2 pt-1">
            <Button variant="ghost" size="sm" onClick={() => setShowCreate(false)}>Hủy</Button>
            <Button size="sm" onClick={() => create()}>Tạo + phân loại AI</Button>
          </div>
        </div>
      </Modal>
    </div>
  );
};
