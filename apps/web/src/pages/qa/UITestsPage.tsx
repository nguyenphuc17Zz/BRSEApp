import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Monitor, Sparkles, PlayCircle } from 'lucide-react';
import { apiClient } from '../../api/client';
import { Project } from '../../types';
import { UIScript, APIEnvironment } from '../../types/qa';
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

const SCRIPT_STATUS = ['', 'REVIEW_REQUIRED', 'APPROVED', 'NEEDS_UPDATE', 'DISABLED', 'NOT_GENERATED'];

export const UITestsPage: React.FC<Props> = ({ activeProject }) => {
  const [items, setItems] = useState<UIScript[]>([]);
  const [candidates, setCandidates] = useState<any[]>([]);
  const [envs, setEnvs] = useState<APIEnvironment[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [smokeOnly, setSmokeOnly] = useState(false);
  const [generating, setGenerating] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const [envId, setEnvId] = useState('');
  const [showGen, setShowGen] = useState(false);
  const [genCaseId, setGenCaseId] = useState('');
  const toast = useToast();
  const navigate = useNavigate();

  const load = async () => {
    if (!activeProject) { setLoading(false); return; }
    setLoading(true);
    try {
      const [scripts, cands, envList] = await Promise.all([
        apiClient.qaListUiScripts(activeProject.id, {
          status: statusFilter || undefined,
          smoke: smokeOnly || undefined,
          search: search || undefined,
        }),
        apiClient.qaUiCandidates(activeProject.id),
        apiClient.qaListEnvs(activeProject.id),
      ]);
      setItems(scripts);
      setCandidates(cands);
      setEnvs(envList);
      const def = envList.find((e: APIEnvironment) => e.is_default) || envList[0];
      if (def && !envId) setEnvId(def.id);
    } catch {
      toast.error('Không tải được UI tests');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); /* eslint-disable-next-line */ }, [activeProject?.id]);

  const generate = async () => {
    if (!genCaseId.trim()) { toast.error('Nhập test case ID (UUID)'); return; }
    setGenerating(genCaseId);
    try {
      const out = await apiClient.qaGenerateUiScript({ test_case_id: genCaseId.trim() });
      toast.success(`Đã generate v${out.version} (REVIEW_REQUIRED)${out.needs_mapping ? ' — cần mapping' : ''}`);
      setShowGen(false);
      setGenCaseId('');
      load();
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || 'Generate thất bại');
    } finally {
      setGenerating(null);
    }
  };

  const runSmoke = async () => {
    if (!activeProject || !envId) { toast.error('Chọn environment'); return; }
    setRunning(true);
    try {
      const out = await apiClient.qaRunUiSuite({
        project_id: activeProject.id, smoke_only: true,
        environment_id: envId, changed_by: 'user',
      });
      toast.success(`Smoke: ${out.started.length} started, ${out.skipped.length} skipped`);
      if (out.test_run_id) navigate(`/qa/test-runs/${out.test_run_id}`);
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || 'Chạy smoke thất bại');
    } finally {
      setRunning(false);
    }
  };

  return (
    <div className="flex-1 overflow-y-auto p-4 sm:p-6 space-y-4">
      <PageHeader
        title="UI Tests"
        description="Generate Playwright automation → review → approve → chạy nền trên Chromium."
        icon={<Monitor className="w-5 h-5" />}
        actions={
          <div className="flex gap-1.5">
            <Button size="sm" variant="subtle" leftIcon={<Sparkles className="w-3.5 h-3.5" />} onClick={() => setShowGen(true)}>
              Generate Automation
            </Button>
            <Button size="sm" disabled={running} leftIcon={<PlayCircle className="w-3.5 h-3.5" />} onClick={runSmoke}>
              {running ? 'Đang chạy...' : 'Run Smoke Tests'}
            </Button>
          </div>
        }
      />
      {!activeProject && (
        <Card><CardContent><p className="text-sm text-text-secondary">Chọn một project để bắt đầu.</p></CardContent></Card>
      )}
      {activeProject && (
        <>
          <Card>
            <CardContent className="space-y-3">
              <div className="flex flex-col sm:flex-row gap-2">
                <div className="flex-1">
                  <Input placeholder="Tìm UI test..." value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    onKeyDown={(e) => { if (e.key === 'Enter') load(); }} />
                </div>
                <div className="w-full sm:w-44">
                  <Select value={statusFilter} onChange={(v) => setStatusFilter(v as string)}
                    options={SCRIPT_STATUS.map((s) => ({ value: s, label: s === '' ? 'Mọi status' : s }))} />
                </div>
                <label className="text-xs flex items-center gap-1.5">
                  <input type="checkbox" checked={smokeOnly} onChange={(e) => setSmokeOnly(e.target.checked)} /> Smoke
                </label>
                <div className="w-full sm:w-44">
                  <Select value={envId} onChange={(v) => setEnvId(v as string)}
                    options={envs.map((e) => ({ value: e.id, label: e.name }))} />
                </div>
                <Button size="sm" onClick={load}>Lọc</Button>
              </div>
              {loading && <p className="text-xs text-text-muted">Đang tải...</p>}
              {!loading && items.length === 0 && (
                <EmptyState title="Chưa có automation" description="Generate từ test case, hoặc xem gợi ý bên dưới." />
              )}
              <div className="divide-y divide-border-subtle">
                {items.map((s) => (
                  <button key={s.test_case_id} onClick={() => navigate(`/qa/ui-tests/${s.test_case_id}`)}
                    className="w-full text-left py-2.5 px-1 hover:bg-surface-hover rounded-lg">
                    <div className="flex items-center gap-1.5 flex-wrap">
                      <span className="font-mono text-xs text-primary font-semibold">{s.tc_code}</span>
                      <Badge variant={statusVariant(s.status)}>{s.status}</Badge>
                      {s.is_smoke && <Badge variant="primary">SMOKE</Badge>}
                      {s.flaky_flag && <Badge variant="warning">Potentially Flaky</Badge>}
                      {s.needs_mapping && <Badge variant="danger">Selector Required</Badge>}
                      {s.last_result && <Badge variant={s.last_result === 'PASS' ? 'success' : 'danger'}>{s.last_result}</Badge>}
                      <span className="text-[11px] text-text-muted">v{s.script_version}</span>
                    </div>
                    <div className="text-sm text-text-primary mt-0.5">{s.title}</div>
                  </button>
                ))}
              </div>
            </CardContent>
          </Card>
          {candidates.length > 0 && (
            <Card>
              <CardContent>
                <div className="text-sm font-semibold text-text-primary mb-2">Gợi ý automate (recommendation — bạn quyết định)</div>
                {candidates.slice(0, 8).map((c: any) => (
                  <div key={c.test_case_id} className="text-xs py-1 flex items-center gap-2 flex-wrap">
                    <span className="font-mono text-primary">{c.tc_code}</span>
                    <span className="flex-1">{c.title}</span>
                    <span className="text-text-muted">{(c.reasons || []).join(' · ')}</span>
                  </div>
                ))}
              </CardContent>
            </Card>
          )}
        </>
      )}
      <Modal isOpen={showGen} onClose={() => setShowGen(false)} title="Generate Automation" size="lg">
        <div className="space-y-2">
          <p className="text-xs text-text-muted">
            Nhập Test Case ID (mở Test Cases → copy ID, hoặc lấy từ requirement detail).
            AI chỉ dùng mapping ACTIVE đã duyệt; thiếu element sẽ flag Selector Required.
          </p>
          <Input value={genCaseId} onChange={(e) => setGenCaseId(e.target.value)} placeholder="Test case UUID" />
          <div className="flex justify-end gap-2">
            <Button variant="ghost" size="sm" onClick={() => setShowGen(false)}>Hủy</Button>
            <Button size="sm" disabled={!!generating} onClick={generate}>
              {generating ? 'Đang sinh...' : 'Generate (REVIEW_REQUIRED)'}
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
};
