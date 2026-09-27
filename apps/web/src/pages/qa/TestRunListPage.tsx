import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { PlayCircle, Plus } from 'lucide-react';
import { apiClient } from '../../api/client';
import { Project } from '../../types';
import { TestRun } from '../../types/qa';
import { useToast } from '../../context/ToastContext';
import { PageHeader } from '../../components/ui/PageHeader';
import { Card, CardContent } from '../../components/ui/Card';
import { Badge } from '../../components/ui/Badge';
import { Button } from '../../components/ui/Button';
import { Input } from '../../components/ui/Input';
import { Select } from '../../components/ui/Select';
import { Modal } from '../../components/ui/Modal';
import { EmptyState } from '../../components/ui/EmptyState';
import { ProgressBar } from './execComponents';
import { statusVariant } from './qaHelpers';

interface Props {
  activeProject: Project | null;
}

export const TestRunListPage: React.FC<Props> = ({ activeProject }) => {
  const [runs, setRuns] = useState<TestRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState({ name: '', version_build: '', environment: 'STG', tester: '', notes: '' });
  const toast = useToast();
  const navigate = useNavigate();

  const load = async () => {
    setLoading(true);
    try {
      const data = await apiClient.qaListTestRuns({
        project_id: activeProject?.id || undefined,
        status: statusFilter || undefined,
        search: search || undefined,
      });
      setRuns(data);
    } catch {
      toast.error('Không tải được test runs');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeProject?.id]);

  const create = async () => {
    if (!activeProject) {
      toast.error('Chọn project trước');
      return;
    }
    if (!form.name.trim()) {
      toast.error('Nhập tên test run');
      return;
    }
    try {
      const run = await apiClient.qaCreateTestRun(activeProject.id, form);
      toast.success(`Đã tạo ${run.run_code}`);
      setShowCreate(false);
      setForm({ name: '', version_build: '', environment: 'STG', tester: '', notes: '' });
      navigate(`/qa/test-runs/${run.id}`);
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || 'Tạo thất bại');
    }
  };

  return (
    <div className="flex-1 overflow-y-auto p-4 sm:p-6 space-y-4">
      <PageHeader
        title="Test Runs"
        description="Mỗi đợt test: chọn testcase → chạy → ghi PASS/FAIL → evidence → bug → report."
        icon={<PlayCircle className="w-5 h-5" />}
        actions={
          <Button size="sm" leftIcon={<Plus className="w-3.5 h-3.5" />} onClick={() => setShowCreate(true)}>
            Create Test Run
          </Button>
        }
      />
      <Card>
        <CardContent className="space-y-3">
          <div className="flex flex-col sm:flex-row gap-2">
            <div className="flex-1">
              <Input placeholder="Tìm run (tên, build, mã...)" value={search}
                onChange={(e) => setSearch(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter') load(); }} />
            </div>
            <div className="w-full sm:w-44">
              <Select value={statusFilter} onChange={(v) => setStatusFilter(v as string)}
                options={[{ value: '', label: 'Mọi status' }, 'DRAFT', 'READY', 'IN_PROGRESS', 'COMPLETED', 'CANCELLED'].map((s) => typeof s === 'string' ? { value: s === 'Mọi status' ? '' : s, label: s } : s)} />
            </div>
            <Button size="sm" onClick={load}>Lọc</Button>
          </div>
          {loading && <p className="text-xs text-text-muted">Đang tải...</p>}
          {!loading && runs.length === 0 && (
            <EmptyState title="Chưa có test run" description="Tạo đợt test đầu tiên cho build hiện tại." />
          )}
          <div className="divide-y divide-border-subtle">
            {runs.map((r) => (
              <button key={r.id} onClick={() => navigate(`/qa/test-runs/${r.id}`)}
                className="w-full text-left py-3 px-3.5 hover:bg-surface-hover rounded-lg space-y-1.5 transition-colors">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="font-mono text-xs text-primary font-semibold">{r.run_code}</span>
                  <Badge variant={statusVariant(r.status)}>{r.status}</Badge>
                  {r.version_build && <Badge variant="neutral">build {r.version_build}</Badge>}
                  {r.environment && <Badge variant="neutral">{r.environment}</Badge>}
                </div>
                <div className="text-sm font-medium text-text-primary">{r.name}</div>
                <ProgressBar progress={r.progress} />
              </button>
            ))}
          </div>
        </CardContent>
      </Card>

      <Modal isOpen={showCreate} onClose={() => setShowCreate(false)} title="Create Test Run" size="lg">
        <div className="space-y-2.5">
          <div>
            <label className="text-xs font-semibold text-text-secondary">Tên đợt test *</label>
            <Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })}
              placeholder="VD: Build 1.2.0 / UAT 2026/09/27 / Login Feature Test" />
          </div>
          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="text-xs font-semibold text-text-secondary">Version / Build</label>
              <Input value={form.version_build} onChange={(e) => setForm({ ...form, version_build: e.target.value })} placeholder="1.2.0" />
            </div>
            <div>
              <label className="text-xs font-semibold text-text-secondary">Environment</label>
              <Input value={form.environment} onChange={(e) => setForm({ ...form, environment: e.target.value })} placeholder="STG / UAT / PROD" />
            </div>
          </div>
          <div>
            <label className="text-xs font-semibold text-text-secondary">Tester</label>
            <Input value={form.tester} onChange={(e) => setForm({ ...form, tester: e.target.value })} />
          </div>
          <div>
            <label className="text-xs font-semibold text-text-secondary">Notes</label>
            <Input value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} />
          </div>
          <div className="flex justify-end gap-2 pt-1">
            <Button variant="ghost" size="sm" onClick={() => setShowCreate(false)}>Hủy</Button>
            <Button size="sm" onClick={create}>Tạo</Button>
          </div>
        </div>
      </Modal>
    </div>
  );
};
