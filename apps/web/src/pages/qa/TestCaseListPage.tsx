import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { FlaskConical, Copy, Trash2 } from 'lucide-react';
import { apiClient } from '../../api/client';
import { Project } from '../../types';
import { QATestCase } from '../../types/qa';
import { useToast } from '../../context/ToastContext';
import { useConfirm } from '../../context/ConfirmDialogContext';
import { PageHeader } from '../../components/ui/PageHeader';
import { Card, CardContent } from '../../components/ui/Card';
import { Badge } from '../../components/ui/Badge';
import { Button } from '../../components/ui/Button';
import { Input } from '../../components/ui/Input';
import { Select } from '../../components/ui/Select';
import { EmptyState } from '../../components/ui/EmptyState';
import { Modal } from '../../components/ui/Modal';
import { KnowledgeBadge, statusVariant } from './qaHelpers';

interface Props {
  activeProject: Project | null;
}

export const TestCaseListPage: React.FC<Props> = ({ activeProject }) => {
  const [items, setItems] = useState<QATestCase[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [typeFilter, setTypeFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [selected, setSelected] = useState<QATestCase | null>(null);
  const toast = useToast();
  const confirm = useConfirm();
  const navigate = useNavigate();

  const load = async () => {
    setLoading(true);
    try {
      const data = await apiClient.qaListTestCases({
        project_id: activeProject?.id || undefined,
        case_type: typeFilter || undefined,
        status: statusFilter || undefined,
        search: search || undefined,
      });
      setItems(data);
    } catch {
      toast.error('Không tải được test cases');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeProject?.id]);

  const mutate = async (fn: () => Promise<any>, msg: string) => {
    try {
      const updated = await fn();
      toast.success(msg);
      setItems((prev) => prev.map((t) => (t.id === updated.id ? updated : t)));
      if (selected && selected.id === updated.id) setSelected(updated);
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || 'Thao tác thất bại');
    }
  };

  return (
    <div className="flex-1 overflow-y-auto p-4 sm:p-6 space-y-4">
      <PageHeader
        title="Test Cases"
        description="Tìm kiếm, lọc và review testcase. Click để xem steps chi tiết."
        icon={<FlaskConical className="w-5 h-5" />}
        actions={<Button variant="subtle" size="sm" onClick={load}>Refresh</Button>}
      />
      <Card>
        <CardContent className="space-y-3">
          <div className="flex flex-col sm:flex-row gap-2">
            <div className="flex-1">
              <Input placeholder="Tìm testcase (mã, tiêu đề...)" value={search} onChange={(e) => setSearch(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter') load(); }} />
            </div>
            <div className="w-full sm:w-44">
              <Select value={typeFilter} onChange={(v) => setTypeFilter(v as string)}
                options={[{ value: '', label: 'Mọi loại' }, 'Happy', 'Negative', 'Validation', 'Boundary', 'Permission', 'DataIntegrity', 'ErrorHandling', 'StateTransition', 'RegressionCandidate'].map((t) => typeof t === 'string' ? { value: t === 'Mọi loại' ? '' : t, label: t } : t)} />
            </div>
            <div className="w-full sm:w-40">
              <Select value={statusFilter} onChange={(v) => setStatusFilter(v as string)}
                options={[{ value: '', label: 'Mọi status' }, { value: 'DRAFT', label: 'DRAFT' }, { value: 'REVIEWED', label: 'REVIEWED' }, { value: 'APPROVED', label: 'APPROVED' }, { value: 'REJECTED', label: 'REJECTED' }]} />
            </div>
            <Button size="sm" onClick={load}>Lọc</Button>
          </div>
          {loading && <p className="text-xs text-text-muted">Đang tải...</p>}
          {!loading && items.length === 0 && <EmptyState title="Chưa có testcase" description="Sinh testcase từ Requirement Detail." />}
          <div className="divide-y divide-border-subtle">
            {items.map((tc) => (
              <div key={tc.id} className="py-1 flex items-start gap-2">
                <button onClick={() => setSelected(tc)} className="flex-1 text-left hover:bg-surface-hover rounded-lg px-3 py-2 transition-colors">
                  <div className="flex items-center gap-1.5 flex-wrap">
                    <span className="font-mono text-xs text-primary font-semibold">{tc.tc_code}</span>
                    <Badge variant="info">{tc.case_type}</Badge>
                    <Badge variant={statusVariant(tc.status)}>{tc.status}</Badge>
                    <KnowledgeBadge value={tc.knowledge_class} />
                  </div>
                  <div className="text-sm font-medium text-text-primary mt-0.5">{tc.title}</div>
                  <div className="text-xs text-text-muted">{tc.steps?.length || 0} steps · {tc.priority}</div>
                </button>
                <div className="flex gap-1 flex-shrink-0">
                  <Button size="sm" variant="ghost" leftIcon={<Copy className="w-3 h-3" />}
                    onClick={() => mutate(() => apiClient.qaDuplicateTestCase(tc.id), 'Đã duplicate')}> </Button>
                  <Button size="sm" variant="ghost" leftIcon={<Trash2 className="w-3 h-3" />}
                    onClick={async () => {
                      if (await confirm({ title: 'Xóa testcase?', message: `Xóa ${tc.tc_code}?`, confirmText: 'Xóa', isDestructive: true })) {
                        try {
                          await apiClient.qaDeleteTestCase(tc.id);
                          toast.success('Đã xóa');
                          setItems((prev) => prev.filter((t) => t.id !== tc.id));
                        } catch { toast.error('Xóa thất bại'); }
                      }
                    }}> </Button>
                </div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      <Modal isOpen={!!selected} onClose={() => setSelected(null)} title={selected ? `${selected.tc_code} — ${selected.title}` : ''} size="2xl"
        footer={selected ? (
          <div className="flex gap-2 justify-end flex-wrap">
            <Button variant="ghost" size="sm" onClick={() => setSelected(null)}>Đóng</Button>
            <Button variant="subtle" size="sm" onClick={() => selected && mutate(() => apiClient.qaUpdateTestCase(selected.id, { status: 'REVIEWED' }), 'Đã review')}>Reviewed</Button>
            <Button size="sm" onClick={() => selected && mutate(() => apiClient.qaUpdateTestCase(selected.id, { status: 'APPROVED' }), 'Đã approve')}>Approve</Button>
            <Button variant="ghost" size="sm" onClick={() => selected && mutate(() => apiClient.qaUpdateTestCase(selected.id, { status: 'REJECTED' }), 'Đã reject')}>Reject</Button>
          </div>
        ) : undefined}>
        {selected && (
          <div className="space-y-2">
            <div className="flex gap-1.5 flex-wrap">
              <Badge variant="info">{selected.case_type}</Badge>
              <Badge variant={statusVariant(selected.status)}>{selected.status}</Badge>
              <KnowledgeBadge value={selected.knowledge_class} />
              <Badge variant="neutral">{selected.priority}</Badge>
            </div>
            {selected.purpose && <p className="text-xs text-text-secondary">{selected.purpose}</p>}
            {selected.preconditions && <p className="text-xs"><span className="font-semibold">Preconditions:</span> {selected.preconditions}</p>}
            {(selected.steps || []).map((s) => (
              <div key={s.id} className="text-xs bg-surface-subtle border border-border-subtle rounded p-2">
                <div><span className="font-semibold">Step {s.step_order}:</span> {s.action}</div>
                {s.expected && <div className="text-text-secondary">→ Expected: {s.expected}</div>}
              </div>
            ))}
            <p className="text-xs"><span className="font-semibold">Expected result:</span> {selected.expected_result}</p>
            <p className="text-xs text-text-muted italic">Evidence: “{selected.evidence_quote}”</p>
            <button className="text-xs text-primary hover:underline" onClick={() => { setSelected(null); navigate(`/qa/requirements/${selected.requirement_id}`); }}>
              Mở requirement liên quan →
            </button>
          </div>
        )}
      </Modal>
    </div>
  );
};
