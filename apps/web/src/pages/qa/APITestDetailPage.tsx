import React, { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { FlaskConical, PlayCircle, Plus, Sparkles, Bug as BugIcon, Trash2 } from 'lucide-react';
import { apiClient } from '../../api/client';
import { Project } from '../../types';
import { APITestCase, APIEnvironment, APIAssertion } from '../../types/qa';
import { useToast } from '../../context/ToastContext';
import { useConfirm } from '../../context/ConfirmDialogContext';
import { PageHeader } from '../../components/ui/PageHeader';
import { Card, CardContent } from '../../components/ui/Card';
import { Badge } from '../../components/ui/Badge';
import { Button } from '../../components/ui/Button';
import { Input } from '../../components/ui/Input';
import { Select } from '../../components/ui/Select';
import { KnowledgeBadge, statusVariant } from './qaHelpers';
import { BugUxBadge } from './execComponents';

interface Props {
  activeProject: Project | null;
}

const FIELD_OPS: Record<string, string[]> = {
  status: ['eq', 'ne'],
  json: ['eq', 'ne', 'exists', 'not_exists', 'type', 'contains', 'gt', 'gte', 'lt', 'lte', 'empty', 'not_empty'],
  header: ['eq', 'exists', 'not_exists', 'contains'],
  time: ['lt', 'lte', 'gt', 'gte', 'eq'],
  empty: ['empty', 'not_empty'],
};

export const APITestDetailPage: React.FC<Props> = ({ activeProject }) => {
  const { id } = useParams<{ id: string }>();
  const [tc, setTc] = useState<APITestCase | null>(null);
  const [envs, setEnvs] = useState<APIEnvironment[]>([]);
  const [envId, setEnvId] = useState('');
  const [confirmProd, setConfirmProd] = useState(false);
  const [running, setRunning] = useState(false);
  const [runOut, setRunOut] = useState<any>(null);
  const [analysis, setAnalysis] = useState<any>(null);
  const [editCfg, setEditCfg] = useState<any>(null);
  const [newAssert, setNewAssert] = useState({ field: 'json', target: 'data.id', operator: 'exists', expected_value: '' });
  const toast = useToast();
  const confirm = useConfirm();
  const navigate = useNavigate();

  const load = async () => {
    if (!id) return;
    try {
      const d = await apiClient.qaGetApiTest(id);
      setTc(d);
      if (!editCfg && d.api_config) {
        setEditCfg({
          method: d.api_config.method,
          url_template: d.api_config.url_template,
          expected_status: d.api_config.expected_status,
          timeout_s: d.api_config.timeout_s,
          retry_network: d.api_config.retry_network,
          headers: JSON.stringify(d.api_config.headers, null, 2),
          query: JSON.stringify(d.api_config.query, null, 2),
          path_params: JSON.stringify(d.api_config.path_params, null, 2),
          body_text: d.api_config.body_text || '',
          auth: d.api_config.auth || { type: 'none' },
          extract_map: JSON.stringify(d.api_config.extract_map, null, 2),
        });
      }
      if (activeProject) {
        const envList = await apiClient.qaListEnvs(activeProject.id);
        setEnvs(envList);
        const def = envList.find((e: APIEnvironment) => e.is_default) || envList[0];
        if (def && !envId) setEnvId(def.id);
      }
    } catch {
      toast.error('Không tải được API test');
    }
  };

  useEffect(() => { load(); /* eslint-disable-next-line */ }, [id]);

  const parseJSON = (s: string, label: string) => {
    if (!s.trim()) return {};
    try { return JSON.parse(s); }
    catch { throw new Error(`${label} phải là JSON hợp lệ`); }
  };

  const saveConfig = async () => {
    if (!id || !editCfg) return;
    try {
      await apiClient.qaUpdateApiConfig(id, {
        method: editCfg.method,
        url_template: editCfg.url_template,
        expected_status: Number(editCfg.expected_status) || 200,
        timeout_s: Number(editCfg.timeout_s) || 30,
        retry_network: !!editCfg.retry_network,
        headers: parseJSON(editCfg.headers, 'Headers'),
        query: parseJSON(editCfg.query, 'Query'),
        path_params: parseJSON(editCfg.path_params, 'Path params'),
        body_text: editCfg.body_text,
        auth: editCfg.auth,
        extract_map: parseJSON(editCfg.extract_map, 'Extract map'),
      });
      toast.success('Đã lưu request config');
      setEditCfg(null);
      load();
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || e.message || 'Lưu thất bại');
    }
  };

  const runTest = async () => {
    if (!id || !envId) { toast.error('Chọn environment'); return; }
    const env = envs.find((e) => e.id === envId);
    if (env?.is_prod && !confirmProd && (editCfg?.method || tc?.api_config?.method) !== 'GET') {
      toast.error('PROD + destructive method: tick xác nhận PROD trước');
      return;
    }
    setRunning(true);
    setAnalysis(null);
    try {
      const out = await apiClient.qaRunApiTest(id, { environment_id: envId, confirm_prod: confirmProd });
      setRunOut(out);
      toast.success(`Kết quả: ${out.status}`, );
      load();
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || 'Chạy thất bại');
    } finally {
      setRunning(false);
    }
  };

  const addAssertion = async (draft?: Partial<APIAssertion>) => {
    if (!id) return;
    const a = draft || newAssert;
    try {
      await apiClient.qaCreateAssertion(id, {
        field: a.field, target: a.target, operator: a.operator,
        expected_value: a.expected_value || null,
      });
      toast.success('Đã thêm assertion (APPROVED)');
      load();
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || 'Thêm thất bại');
    }
  };

  const suggest = async () => {
    if (!id) return;
    try {
      const rows = await apiClient.qaSuggestAssertions(id, {});
      toast.success(`AI đề xuất ${rows.length} assertions (DRAFT) — hãy review`);
      load();
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || 'Suggest thất bại');
    }
  };

  const approveAllDrafts = async () => {
    if (!tc?.api_config) return;
    const drafts = tc.api_config.assertions.filter((a) => a.status === 'DRAFT');
    for (const d of drafts) {
      await apiClient.qaUpdateAssertion(d.id, { status: 'APPROVED' });
    }
    toast.success(`Đã approve ${drafts.length} assertions`);
    load();
  };

  const analyze = async () => {
    if (!runOut?.execution_id) return;
    try {
      setAnalysis(await apiClient.qaAnalyzeFail(runOut.execution_id, {}));
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || 'Phân tích thất bại');
    }
  };

  const genBug = async () => {
    if (!runOut?.execution_id) return;
    try {
      const draft = await apiClient.qaDraftApiBug(runOut.execution_id, {});
      const bug = await apiClient.qaCreateBug(runOut.execution_id, { ...draft, status: 'PROPOSED' });
      toast.success(`Đã tạo ${bug.bug_code} (DRAFT) — nhớ review`);
      navigate(`/qa/bugs/${bug.id}`);
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || 'Tạo bug thất bại');
    }
  };

  if (!tc) return <div className="flex-1 p-6 text-sm text-text-muted">Đang tải API test...</div>;
  const cfg = tc.api_config;
  const env = envs.find((e) => e.id === envId);

  return (
    <div className="flex-1 overflow-y-auto p-4 sm:p-6 space-y-4">
      <PageHeader
        title={<span><span className="font-mono text-primary mr-2">{tc.tc_code}</span>{tc.title}</span>}
        description={tc.purpose}
        icon={<FlaskConical className="w-5 h-5" />}
        breadcrumbs={[{ label: 'API Tests', onClick: () => navigate('/qa/api-tests') }, { label: tc.tc_code }]}
        badge={<div className="flex gap-1.5 flex-wrap">
          <Badge variant={statusVariant(tc.status)}>{tc.status}</Badge>
          <KnowledgeBadge value={tc.knowledge_class} />
          {cfg?.outdated_flag && <Badge variant="danger">API Definition Changed — Review Required</Badge>}
          {tc.last_result && <Badge variant={tc.last_result === 'PASS' ? 'success' : 'danger'}>{tc.last_result}</Badge>}
        </div>}
      />

      {tc.requirement && (
        <button className="text-xs text-primary hover:underline"
          onClick={() => navigate(`/qa/requirements/${tc.requirement!.id}`)}>
          {tc.requirement.req_code} — {tc.requirement.title} →
        </button>
      )}

      {/* Request builder */}
      <Card>
        <CardContent className="space-y-2.5">
          <div className="text-sm font-semibold">Request Builder</div>
          {editCfg && (
            <>
              <div className="flex gap-2 flex-wrap">
                <div className="w-32">
                  <Select value={editCfg.method} onChange={(v) => setEditCfg({ ...editCfg, method: v as string })}
                    options={['GET', 'POST', 'PUT', 'PATCH', 'DELETE'].map((m) => ({ value: m, label: m }))} />
                </div>
                <div className="flex-1 min-w-[240px]">
                  <Input value={editCfg.url_template} onChange={(e) => setEditCfg({ ...editCfg, url_template: e.target.value })}
                    placeholder="{{BASE_URL}}/api/users" />
                </div>
                <div className="w-28"><Input type="number" value={editCfg.expected_status} onChange={(e) => setEditCfg({ ...editCfg, expected_status: e.target.value })} /></div>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                <div>
                  <label className="text-xs font-semibold">Headers (JSON)</label>
                  <textarea value={editCfg.headers} onChange={(e) => setEditCfg({ ...editCfg, headers: e.target.value })} rows={4}
                    className="w-full font-mono text-xs bg-surface border border-border-subtle rounded-lg p-2" />
                </div>
                <div>
                  <label className="text-xs font-semibold">Query params (JSON)</label>
                  <textarea value={editCfg.query} onChange={(e) => setEditCfg({ ...editCfg, query: e.target.value })} rows={4}
                    className="w-full font-mono text-xs bg-surface border border-border-subtle rounded-lg p-2" />
                </div>
                <div>
                  <label className="text-xs font-semibold">Path params (JSON, VD {`{"id": "{{user_id}}"}`})</label>
                  <textarea value={editCfg.path_params} onChange={(e) => setEditCfg({ ...editCfg, path_params: e.target.value })} rows={3}
                    className="w-full font-mono text-xs bg-surface border border-border-subtle rounded-lg p-2" />
                </div>
                <div>
                  <label className="text-xs font-semibold">Body (JSON, hỗ trợ {'{{TEST_EMAIL}}'})</label>
                  <textarea value={editCfg.body_text} onChange={(e) => setEditCfg({ ...editCfg, body_text: e.target.value })} rows={3}
                    className="w-full font-mono text-xs bg-surface border border-border-subtle rounded-lg p-2" />
                </div>
              </div>
              <div className="flex gap-2 flex-wrap items-end">
                <div className="w-36">
                  <label className="text-xs font-semibold">Auth</label>
                  <Select value={editCfg.auth?.type || 'none'}
                    onChange={(v) => setEditCfg({ ...editCfg, auth: { ...(editCfg.auth || {}), type: v as string } })}
                    options={[{ value: 'none', label: 'No Auth' }, { value: 'bearer', label: 'Bearer Token' }, { value: 'api_key', label: 'API Key' }, { value: 'basic', label: 'Basic Auth' }]} />
                </div>
                {(editCfg.auth?.type === 'bearer' || editCfg.auth?.type === 'api_key' || editCfg.auth?.type === 'basic') && (
                  <div className="w-48">
                    <label className="text-xs font-semibold">Secret key (VD AUTH_TOKEN)</label>
                    <Input value={editCfg.auth?.secret_key || ''}
                      onChange={(e) => setEditCfg({ ...editCfg, auth: { ...(editCfg.auth || {}), secret_key: e.target.value } })} />
                  </div>
                )}
                {editCfg.auth?.type === 'api_key' && (
                  <div className="w-40">
                    <label className="text-xs font-semibold">Header name</label>
                    <Input value={editCfg.auth?.header || 'X-API-Key'}
                      onChange={(e) => setEditCfg({ ...editCfg, auth: { ...(editCfg.auth || {}), header: e.target.value } })} />
                  </div>
                )}
                <div className="flex-1 min-w-[200px]">
                  <label className="text-xs font-semibold">Extract map (VD {`{"user_id": "data.id"}`})</label>
                  <Input value={editCfg.extract_map} onChange={(e) => setEditCfg({ ...editCfg, extract_map: e.target.value })} />
                </div>
                <label className="text-xs flex items-center gap-1">
                  <input type="checkbox" checked={!!editCfg.retry_network}
                    onChange={(e) => setEditCfg({ ...editCfg, retry_network: e.target.checked })} /> retry network
                </label>
                <Button size="sm" onClick={saveConfig}>Lưu config</Button>
              </div>
            </>
          )}
        </CardContent>
      </Card>

      {/* Assertions */}
      <Card>
        <CardContent className="space-y-2">
          <div className="flex items-center justify-between flex-wrap gap-2">
            <div className="text-sm font-semibold">Assertions (chỉ APPROVED được tính PASS/FAIL)</div>
            <div className="flex gap-1.5">
              <Button size="sm" variant="subtle" leftIcon={<Sparkles className="w-3 h-3" />} onClick={suggest}>Generate Assertions</Button>
              <Button size="sm" variant="ghost" onClick={approveAllDrafts}>Approve all DRAFT</Button>
            </div>
          </div>
          {(cfg?.assertions || []).map((a) => (
            <div key={a.id} className="flex items-center gap-2 text-xs flex-wrap border border-border-subtle rounded-lg px-2 py-1.5">
              <Badge variant="neutral">{a.field}</Badge>
              <span className="font-mono">{a.target || '(status)'}</span>
              <span className="text-text-muted">{a.operator}</span>
              <span className="font-mono">{a.expected_value ?? ''}</span>
              <Badge variant={a.status === 'APPROVED' ? 'success' : a.status === 'DRAFT' ? 'warning' : 'neutral'}>{a.status}</Badge>
              {a.ai_generated && <Badge variant="purple">AI</Badge>}
              <span className="flex-1" />
              {a.status === 'DRAFT' && (
                <button className="text-primary hover:underline" onClick={async () => { await apiClient.qaUpdateAssertion(a.id, { status: 'APPROVED' }); load(); }}>Approve</button>
              )}
              <button className="text-text-muted hover:text-rose-500"
                onClick={async () => {
                  if (await confirm({ title: 'Xóa assertion?', message: 'Xóa assertion này?', confirmText: 'Xóa', isDestructive: true })) {
                    await apiClient.qaDeleteAssertion(a.id); load();
                  }
                }}><Trash2 className="w-3 h-3" /></button>
            </div>
          ))}
          {(cfg?.assertions || []).length === 0 && <p className="text-xs text-text-muted">Chưa có assertion. Thêm thủ công hoặc Generate.</p>}
          <div className="flex gap-1.5 flex-wrap items-end pt-1">
            <div className="w-28">
              <Select value={newAssert.field} onChange={(v) => {
                const f = v as string;
                setNewAssert({ field: f, target: f === 'status' ? '' : newAssert.target, operator: FIELD_OPS[f][0], expected_value: '' });
              }} options={Object.keys(FIELD_OPS).map((f) => ({ value: f, label: f }))} />
            </div>
            <div className="w-44"><Input value={newAssert.target} onChange={(e) => setNewAssert({ ...newAssert, target: e.target.value })} placeholder="data.status" /></div>
            <div className="w-32">
              <Select value={newAssert.operator} onChange={(v) => setNewAssert({ ...newAssert, operator: v as string })}
                options={FIELD_OPS[newAssert.field].map((o) => ({ value: o, label: o }))} />
            </div>
            <div className="w-40"><Input value={newAssert.expected_value} onChange={(e) => setNewAssert({ ...newAssert, expected_value: e.target.value })} placeholder="ACTIVE" /></div>
            <Button size="sm" variant="subtle" leftIcon={<Plus className="w-3 h-3" />} onClick={() => addAssertion()}>Thêm</Button>
          </div>
        </CardContent>
      </Card>

      {/* Run */}
      <Card>
        <CardContent className="space-y-2.5">
          <div className="text-sm font-semibold">Run API Test</div>
          <div className="flex gap-2 flex-wrap items-end">
            <div className="w-52">
              <Select value={envId} onChange={(v) => setEnvId(v as string)}
                options={envs.map((e) => ({ value: e.id, label: `${e.name}${e.is_prod ? ' (PROD!)' : ''}` }))} />
            </div>
            {env?.is_prod && (
              <label className="text-xs text-rose-500 flex items-center gap-1">
                <input type="checkbox" checked={confirmProd} onChange={(e) => setConfirmProd(e.target.checked)} />
                Tôi xác nhận chạy trên PROD
              </label>
            )}
            <Button size="sm" disabled={running} leftIcon={<PlayCircle className="w-3.5 h-3.5" />} onClick={runTest}>
              {running ? 'Đang chạy...' : 'Run API Test'}
            </Button>
          </div>
          {runOut && (
            <div className="space-y-2 text-xs">
              <div className="flex gap-2 items-center flex-wrap">
                <Badge variant={runOut.status === 'PASS' ? 'success' : 'danger'}>{runOut.status}</Badge>
                <span className="text-text-muted">{runOut.latency_ms}ms</span>
                {runOut.fail_reason && <span className="text-rose-500">{runOut.fail_reason}</span>}
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                <div>
                  <div className="font-semibold mb-1">Expected</div>
                  <pre className="bg-surface-subtle border border-border-subtle rounded-lg p-2 whitespace-pre-wrap">
                    Status {cfg?.expected_status}{'\n'}{(cfg?.assertions || []).filter((a) => a.status === 'APPROVED').map((a) => `${a.field}:${a.target} ${a.operator} ${a.expected_value ?? ''}`).join('\n')}
                  </pre>
                </div>
                <div>
                  <div className="font-semibold mb-1">Actual</div>
                  <pre className="bg-surface-subtle border border-border-subtle rounded-lg p-2 whitespace-pre-wrap max-h-64 overflow-y-auto">
                    {JSON.stringify({ status_code: runOut.response?.status_code, body: runOut.response?.body }, null, 2)}
                  </pre>
                </div>
              </div>
              {(runOut.assertions?.results || []).filter((r: any) => !r.passed).length > 0 && (
                <div>
                  <div className="font-semibold text-rose-500 mb-1">Failed assertions</div>
                  {(runOut.assertions.results as any[]).filter((r) => !r.passed).map((r, i) => (
                    <div key={i} className="font-mono bg-rose-500/10 border border-rose-500/20 rounded p-1.5 mb-1">{r.message} (actual: {JSON.stringify(r.actual)})</div>
                  ))}
                </div>
              )}
              <details>
                <summary className="cursor-pointer text-primary">Request / Response đầy đủ (đã redact secrets)</summary>
                <pre className="bg-surface-subtle border border-border-subtle rounded-lg p-2 whitespace-pre-wrap max-h-64 overflow-y-auto mt-1">
                  {JSON.stringify({ request: runOut.request, response: runOut.response }, null, 2)}
                </pre>
              </details>
              {runOut.status === 'FAIL' && (
                <div className="flex gap-1.5 flex-wrap">
                  <Button size="sm" variant="subtle" leftIcon={<Sparkles className="w-3 h-3" />} onClick={analyze}>Phân tích FAIL</Button>
                  <Button size="sm" variant="subtle" leftIcon={<BugIcon className="w-3.5 h-3.5" />} onClick={genBug}>Generate Bug</Button>
                </div>
              )}
              {analysis && (
                <div className="border border-border-subtle rounded-lg p-2">
                  <div className="font-semibold">{analysis.bucket}</div>
                  <div className="text-text-secondary">{analysis.reasoning}</div>
                  {(analysis.diff_highlights || []).map((h: string, i: number) => (
                    <div key={i} className="font-mono text-[11px]">{h}</div>
                  ))}
                  {(analysis.suggested_next_steps || []).map((s: string, i: number) => (
                    <div key={i}>→ {s}</div>
                  ))}
                  <p className="text-[11px] text-text-muted mt-1">Phân loại sơ bộ — không phải kết luận root cause.</p>
                </div>
              )}
            </div>
          )}
        </CardContent>
      </Card>

      {/* History */}
      {(tc.history?.length || 0) > 0 && (
        <Card>
          <CardContent>
            <div className="text-sm font-semibold mb-1">Execution History</div>
            {tc.history!.map((h, i) => (
              <div key={i} className="text-xs text-text-secondary">
                Build {h.build} ({h.run_code}) → {h.status} #{h.attempt_no}
              </div>
            ))}
          </CardContent>
        </Card>
      )}
    </div>
  );
};

export default APITestDetailPage;
