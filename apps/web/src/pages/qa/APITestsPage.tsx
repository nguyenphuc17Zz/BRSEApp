import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { FlaskConical, PlayCircle } from 'lucide-react';
import { apiClient } from '../../api/client';
import { Project } from '../../types';
import { APITestCase, APIEnvironment } from '../../types/qa';
import { useToast } from '../../context/ToastContext';
import { PageHeader } from '../../components/ui/PageHeader';
import { Card, CardContent } from '../../components/ui/Card';
import { Badge } from '../../components/ui/Badge';
import { Button } from '../../components/ui/Button';
import { Input } from '../../components/ui/Input';
import { Select } from '../../components/ui/Select';
import { EmptyState } from '../../components/ui/EmptyState';
import { KnowledgeBadge, statusVariant } from './qaHelpers';
import { CatalogTab, EnvTab, FlowTab } from './apiCatalogTabs';

interface Props {
  activeProject: Project | null;
}

export const APITestListTab: React.FC<Props> = ({ activeProject }) => {
  const [items, setItems] = useState<APITestCase[]>([]);
  const [envs, setEnvs] = useState<APIEnvironment[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [methodFilter, setMethodFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [envId, setEnvId] = useState('');
  const [selected, setSelected] = useState<Record<string, boolean>>({});
  const [running, setRunning] = useState(false);
  const [suiteOut, setSuiteOut] = useState<any>(null);
  const toast = useToast();
  const navigate = useNavigate();

  const load = async () => {
    if (!activeProject) { setLoading(false); return; }
    setLoading(true);
    try {
      const [tests, envList] = await Promise.all([
        apiClient.qaListApiTests(activeProject.id, {
          method: methodFilter || undefined,
          status: statusFilter || undefined,
          search: search || undefined,
        }),
        apiClient.qaListEnvs(activeProject.id),
      ]);
      setItems(tests);
      setEnvs(envList);
      const def = envList.find((e: APIEnvironment) => e.is_default) || envList[0];
      if (def && !envId) setEnvId(def.id);
    } catch {
      toast.error('Không tải được API tests');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); /* eslint-disable-next-line */ }, [activeProject?.id]);

  const toggle = (id: string) => setSelected((s) => ({ ...s, [id]: !s[id] }));
  const chosen = items.filter((t) => selected[t.id]);

  const runSuite = async () => {
    if (!envId) { toast.error('Chọn environment trước'); return; }
    if (chosen.length === 0) { toast.error('Chọn ít nhất 1 testcase'); return; }
    const env = envs.find((e) => e.id === envId);
    if (env?.is_prod && !window.confirm('Environment là PROD. Tiếp tục chạy suite?')) return;
    setRunning(true);
    try {
      const out = await apiClient.qaRunApiSuite({
        test_case_ids: chosen.map((t) => t.id),
        environment_id: envId, changed_by: 'user',
      });
      setSuiteOut(out);
      toast.success(`Suite: ${out.pass} PASS / ${out.fail} FAIL / ${out.blocked} BLOCKED`);
      load();
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || 'Chạy suite thất bại');
    } finally {
      setRunning(false);
    }
  };

  return (
    <div className="space-y-3">
      <div className="flex flex-col sm:flex-row gap-2">
        <div className="flex-1">
          <Input placeholder="Tìm API test (mã, tiêu đề...)" value={search}
            onChange={(e) => setSearch(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') load(); }} />
        </div>
        <div className="w-full sm:w-32">
          <Select value={methodFilter} onChange={(v) => setMethodFilter(v as string)}
            options={[{ value: '', label: 'Mọi method' }, { value: 'GET', label: 'GET' }, { value: 'POST', label: 'POST' }, { value: 'PUT', label: 'PUT' }, { value: 'PATCH', label: 'PATCH' }, { value: 'DELETE', label: 'DELETE' }]} />
        </div>
        <div className="w-full sm:w-40">
          <Select value={statusFilter} onChange={(v) => setStatusFilter(v as string)}
            options={[{ value: '', label: 'Mọi status' }, { value: 'DRAFT', label: 'DRAFT' }, { value: 'REVIEWED', label: 'REVIEWED' }, { value: 'APPROVED', label: 'APPROVED' }, { value: 'REJECTED', label: 'REJECTED' }]} />
        </div>
        <Button size="sm" onClick={load}>Lọc</Button>
      </div>

      <div className="flex flex-col sm:flex-row gap-2 items-stretch sm:items-center bg-surface-subtle border border-border-subtle rounded-lg p-2">
        <div className="w-full sm:w-56">
          <Select value={envId} onChange={(v) => setEnvId(v as string)}
            options={envs.map((e) => ({ value: e.id, label: `${e.name}${e.is_prod ? ' (PROD!)' : ''}` }))} />
        </div>
        <Button size="sm" disabled={running || chosen.length === 0}
          leftIcon={<PlayCircle className="w-3.5 h-3.5" />} onClick={runSuite}>
          {running ? 'Đang chạy...' : `Run suite (${chosen.length})`}
        </Button>
        {suiteOut && (
          <span className="text-xs text-text-secondary">
            {suiteOut.pass} PASS · <span className="text-rose-500 font-semibold">{suiteOut.fail} FAIL</span> · {suiteOut.blocked} BLOCKED
            {suiteOut.test_run_id && ' · đã ghi vào Test Run'}
          </span>
        )}
      </div>

      {loading && <p className="text-xs text-text-muted">Đang tải...</p>}
      {!loading && items.length === 0 && (
        <EmptyState title="Chưa có API test" description="Import OpenAPI ở tab Catalog rồi Generate API Test Cases." />
      )}
      <div className="divide-y divide-border-subtle">
        {items.map((tc) => (
          <div key={tc.id} className="py-1 flex items-start gap-2">
            <input type="checkbox" className="mt-3 ml-2" checked={!!selected[tc.id]} onChange={() => toggle(tc.id)} />
            <button onClick={() => navigate(`/qa/api-tests/${tc.id}`)} className="flex-1 text-left hover:bg-surface-hover rounded-lg px-3 py-2 transition-colors">
              <div className="flex items-center gap-1.5 flex-wrap">
                <span className="font-mono text-xs text-primary font-semibold">{tc.api_config?.method} {tc.api_config?.url_template?.replace('{{BASE_URL}}', '') || tc.tc_code}</span>
                <Badge variant={statusVariant(tc.status)}>{tc.status}</Badge>
                <KnowledgeBadge value={tc.knowledge_class} />
                {tc.api_config?.outdated_flag && <Badge variant="danger">API Changed — Review</Badge>}
                {tc.last_result && <Badge variant={tc.last_result === 'PASS' ? 'success' : 'danger'}>{tc.last_result}</Badge>}
              </div>
              <div className="text-sm font-medium text-text-primary mt-0.5">{tc.tc_code} — {tc.title}</div>
              <div className="text-xs text-text-muted">{tc.case_type} · {tc.priority}</div>
            </button>
          </div>
        ))}
      </div>
    </div>
  );
};

export const APITestsPage: React.FC<Props> = ({ activeProject }) => {
  const [tab, setTab] = useState<'tests' | 'catalog' | 'env' | 'flows'>('tests');
  return (
    <div className="flex-1 overflow-y-auto p-4 sm:p-6 space-y-4">
      <PageHeader
        title="API Tests"
        description="Catalog → Generate → Review → Run tự động → PASS/FAIL → Bug."
        icon={<FlaskConical className="w-5 h-5" />}
      />
      {!activeProject && (
        <Card><CardContent><p className="text-sm text-text-secondary">Chọn một project để bắt đầu.</p></CardContent></Card>
      )}
      {activeProject && (
        <Card>
          <CardContent className="space-y-3">
            <div className="flex gap-1 border-b border-border-subtle pb-2 flex-wrap">
              {([['tests', 'Tests'], ['catalog', 'Catalog'], ['env', 'Environments'], ['flows', 'Flows']] as const).map(([k, label]) => (
                <button key={k} onClick={() => setTab(k)}
                  className={`text-xs px-3 py-1.5 rounded-lg ${tab === k ? 'bg-primary/10 text-primary font-semibold' : 'text-text-secondary hover:bg-surface-hover'}`}>
                  {label}
                </button>
              ))}
            </div>
            {tab === 'tests' && <APITestListTab activeProject={activeProject} />}
            {tab === 'catalog' && <CatalogTab activeProject={activeProject} />}
            {tab === 'env' && <EnvTab activeProject={activeProject} />}
            {tab === 'flows' && <FlowTab activeProject={activeProject} />}
          </CardContent>
        </Card>
      )}
    </div>
  );
};
