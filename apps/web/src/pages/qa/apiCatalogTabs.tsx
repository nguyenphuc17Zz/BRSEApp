import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Upload, Plus, Trash2, Link as LinkIcon, Sparkles, PlayCircle } from 'lucide-react';
import { apiClient } from '../../api/client';
import { Project } from '../../types';
import { APIEndpoint, APIEnvironment, APIFlow } from '../../types/qa';
import { useToast } from '../../context/ToastContext';
import { useConfirm } from '../../context/ConfirmDialogContext';
import { Badge } from '../../components/ui/Badge';
import { Button } from '../../components/ui/Button';
import { Input } from '../../components/ui/Input';
import { Select } from '../../components/ui/Select';
import { Modal } from '../../components/ui/Modal';
import { EmptyState } from '../../components/ui/EmptyState';
import { statusVariant, useQAProviders } from './qaHelpers';

interface Props {
  activeProject: Project | null;
}

/* ---------------- Catalog tab ---------------- */
export const CatalogTab: React.FC<Props> = ({ activeProject }) => {
  const [endpoints, setEndpoints] = useState<APIEndpoint[]>([]);
  const [requirements, setRequirements] = useState<any[]>([]);
  const [search, setSearch] = useState('');
  const [showImport, setShowImport] = useState(false);
  const [specText, setSpecText] = useState('');
  const [importOut, setImportOut] = useState<any>(null);
  const [showManual, setShowManual] = useState(false);
  const [manual, setManual] = useState({ method: 'GET', path: '', name: '', requirement_id: '' });
  const [generating, setGenerating] = useState<string | null>(null);
  const toast = useToast();
  const confirm = useConfirm();
  const navigate = useNavigate();
  const { opts, picker } = useQAProviders();

  const load = async () => {
    if (!activeProject) return;
    try {
      const [eps, reqs] = await Promise.all([
        apiClient.qaListEndpoints(activeProject.id, search ? { search } : {}),
        apiClient.qaListRequirements(activeProject.id),
      ]);
      setEndpoints(eps);
      setRequirements(reqs);
    } catch {
      toast.error('Không tải được catalog');
    }
  };

  useEffect(() => { load(); /* eslint-disable-next-line */ }, [activeProject?.id]);

  const doImport = async () => {
    if (!activeProject || !specText.trim()) return;
    try {
      const out = await apiClient.qaImportOpenAPI(activeProject.id, specText);
      setImportOut(out);
      toast.success(`Import ${out.total} endpoints (${out.imported} mới, ${out.updated} cập nhật)`);
      if (out.flagged_outdated > 0) toast.error(`${out.flagged_outdated} testcase bị flag outdated`);
      load();
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || 'Import thất bại');
    }
  };

  const doManual = async () => {
    if (!activeProject || !manual.path.trim()) return;
    try {
      await apiClient.qaCreateEndpoint(activeProject.id, { ...manual, spec_source: 'manual' });
      toast.success('Đã thêm endpoint');
      setShowManual(false);
      setManual({ method: 'GET', path: '', name: '', requirement_id: '' });
      load();
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || 'Thêm thất bại');
    }
  };

  const linkReq = async (epId: string, reqId: string) => {
    try {
      await apiClient.qaUpdateEndpoint(epId, { requirement_id: reqId || null });
      toast.success('Đã liên kết requirement');
      load();
    } catch {
      toast.error('Liên kết thất bại');
    }
  };

  const generate = async (epId: string) => {
    setGenerating(epId);
    try {
      const cases = await apiClient.qaGenerateApiTests({ endpoint_id: epId, max_cases: 8, ...opts });
      toast.success(`Đã sinh ${cases.length} testcase (DRAFT) — nhớ review`);
      load();
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || 'Generate thất bại');
    } finally {
      setGenerating(null);
    }
  };

  return (
    <div className="space-y-3">
      <div className="flex gap-2 flex-wrap items-center">
        <div className="flex-1 min-w-[200px]">
          <Input placeholder="Tìm endpoint..." value={search}
            onChange={(e) => setSearch(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') load(); }} />
        </div>
        <Button size="sm" leftIcon={<Upload className="w-3.5 h-3.5" />} onClick={() => setShowImport(true)}>Import OpenAPI</Button>
        <Button size="sm" variant="subtle" leftIcon={<Plus className="w-3.5 h-3.5" />} onClick={() => setShowManual(true)}>Thêm tay</Button>
      </div>
      <div className="max-w-md">{picker}</div>
      {endpoints.length === 0 && <EmptyState title="Chưa có endpoint" description="Import OpenAPI JSON/YAML hoặc thêm thủ công." />}
      <div className="divide-y divide-border-subtle">
        {endpoints.map((ep) => (
          <div key={ep.id} className="py-2.5 px-1">
            <div className="flex items-center gap-1.5 flex-wrap">
              <Badge variant={['POST', 'PUT', 'PATCH', 'DELETE'].includes(ep.method) ? 'warning' : 'info'}>{ep.method}</Badge>
              <span className="font-mono text-xs text-text-primary">{ep.path}</span>
              {ep.last_result && <Badge variant={ep.last_result === 'PASS' ? 'success' : 'danger'}>{ep.last_result}</Badge>}
              <span className="text-[11px] text-text-muted">{ep.test_case_count} cases</span>
            </div>
            <div className="text-xs text-text-secondary mt-0.5">{ep.name} {ep.auth_type !== 'none' && `· auth: ${ep.auth_type}`}</div>
            <div className="flex gap-1.5 mt-1.5 flex-wrap items-center">
              <select className="text-xs bg-surface border border-border-subtle rounded-lg px-2 py-1 max-w-[240px]"
                value={ep.requirement_id || ''} onChange={(e) => linkReq(ep.id, e.target.value)}>
                <option value="">— Link requirement —</option>
                {requirements.map((r: any) => (
                  <option key={r.id} value={r.id}>{r.req_code} — {r.title?.slice(0, 40)}</option>
                ))}
              </select>
              {ep.req_code && <span className="font-mono text-[11px] text-primary">{ep.req_code}</span>}
              <Button size="sm" variant="subtle" disabled={generating === ep.id}
                leftIcon={<Sparkles className="w-3 h-3" />} onClick={() => generate(ep.id)}>
                {generating === ep.id ? 'Đang sinh...' : 'Generate Tests'}
              </Button>
              <Button size="sm" variant="ghost"
                onClick={async () => {
                  if (await confirm({ title: 'Xóa endpoint?', message: `${ep.method} ${ep.path}?`, confirmText: 'Xóa', isDestructive: true })) {
                    await apiClient.qaDeleteEndpoint(ep.id);
                    toast.success('Đã xóa');
                    load();
                  }
                }}><Trash2 className="w-3 h-3" /></Button>
            </div>
          </div>
        ))}
      </div>

      <Modal isOpen={showImport} onClose={() => { setShowImport(false); setImportOut(null); }} title="Import OpenAPI" size="2xl">
        <div className="space-y-2">
          <p className="text-xs text-text-muted">Dán OpenAPI JSON hoặc YAML (tối đa 5MB). Parse deterministic, không dùng AI.</p>
          <textarea value={specText} onChange={(e) => setSpecText(e.target.value)} rows={10}
            className="w-full font-mono text-xs bg-surface border border-border-subtle rounded-lg p-2 text-text-primary"
            placeholder='{"openapi": "3.0.0", ...}' />
          <div className="flex justify-end gap-2">
            <Button variant="ghost" size="sm" onClick={() => setShowImport(false)}>Đóng</Button>
            <Button size="sm" onClick={doImport}>Import</Button>
          </div>
          {importOut && (
            <div className="text-xs bg-surface-subtle border border-border-subtle rounded-lg p-2">
              <div>{importOut.title} v{importOut.version}: {importOut.total} endpoints</div>
              {importOut.changed?.length > 0 && <div className="text-amber-600">Changed: {importOut.changed.join(', ')}</div>}
              {importOut.added?.length > 0 && <div className="text-emerald-600">Added: {importOut.added.join(', ')}</div>}
            </div>
          )}
        </div>
      </Modal>

      <Modal isOpen={showManual} onClose={() => setShowManual(false)} title="Thêm endpoint thủ công" size="lg">
        <div className="space-y-2">
          <div className="flex gap-2">
            <div className="w-32">
              <Select value={manual.method} onChange={(v) => setManual({ ...manual, method: v as string })}
                options={['GET', 'POST', 'PUT', 'PATCH', 'DELETE'].map((m) => ({ value: m, label: m }))} />
            </div>
            <div className="flex-1">
              <Input value={manual.path} onChange={(e) => setManual({ ...manual, path: e.target.value })} placeholder="/api/users/{id}" />
            </div>
          </div>
          <Input value={manual.name} onChange={(e) => setManual({ ...manual, name: e.target.value })} placeholder="Tên gợi nhớ" />
          <div className="flex justify-end gap-2">
            <Button variant="ghost" size="sm" onClick={() => setShowManual(false)}>Hủy</Button>
            <Button size="sm" onClick={doManual}>Thêm</Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}

/* ---------------- Environments tab ---------------- */
export const EnvTab: React.FC<Props> = ({ activeProject }) => {
  const [envs, setEnvs] = useState<APIEnvironment[]>([]);
  const [form, setForm] = useState({ name: '', base_url: '', variables: '{}' });
  const [secretForm, setSecretForm] = useState<Record<string, { key: string; value: string }>>({});
  const toast = useToast();
  const navigate = useNavigate();

  const load = async () => {
    if (!activeProject) return;
    try {
      setEnvs(await apiClient.qaListEnvs(activeProject.id));
    } catch {
      toast.error('Không tải được environments');
    }
  };

  useEffect(() => { load(); /* eslint-disable-next-line */ }, [activeProject?.id]);

  const create = async () => {
    if (!activeProject || !form.name.trim()) return;
    let vars: any = {};
    try { vars = form.variables.trim() ? JSON.parse(form.variables) : {}; }
    catch { toast.error('Variables phải là JSON hợp lệ'); return; }
    try {
      await apiClient.qaCreateEnv(activeProject.id, { name: form.name, base_url: form.base_url, variables: vars });
      toast.success('Đã tạo environment');
      setForm({ name: '', base_url: '', variables: '{}' });
      load();
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || 'Tạo thất bại');
    }
  };

  const saveSecret = async (envId: string) => {
    const f = secretForm[envId];
    if (!f?.key || !f?.value) { toast.error('Nhập key + value'); return; }
    try {
      await apiClient.qaSetEnvSecret(envId, f.key, f.value);
      toast.success('Đã lưu secret (mã hóa)');
      setSecretForm((s) => ({ ...s, [envId]: { key: '', value: '' } }));
      load();
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || 'Lưu thất bại');
    }
  };

  return (
    <div className="space-y-3">
      <p className="text-xs text-text-muted">
        Dùng {'{{BASE_URL}}'}, {'{{USER_ID}}'}, {'{{AUTH_TOKEN}}'}... trong testcase. Secrets mã hóa, chỉ hiện *** khi đọc.
        Dữ liệu động: {'{{TEST_EMAIL}}'}, {'{{UUID}}'}, {'{{TIMESTAMP}}'}.
      </p>
      <div className="flex gap-2 flex-wrap">
        <div className="w-32"><Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="STG" /></div>
        <div className="flex-1 min-w-[200px]"><Input value={form.base_url} onChange={(e) => setForm({ ...form, base_url: e.target.value })} placeholder="https://stg.example.com" /></div>
        <div className="flex-1 min-w-[200px]"><Input value={form.variables} onChange={(e) => setForm({ ...form, variables: e.target.value })} placeholder='{"PROJECT_ID": "123"}' /></div>
        <Button size="sm" leftIcon={<Plus className="w-3.5 h-3.5" />} onClick={create}>Tạo env</Button>
      </div>
      {envs.map((env) => (
        <div key={env.id} className={`border rounded-lg p-3 ${env.is_prod ? 'border-rose-500/50' : 'border-border-subtle'}`}>
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-semibold text-sm">{env.name}</span>
            {env.is_default && <Badge variant="primary">default</Badge>}
            {env.is_prod && <Badge variant="danger">PROD — destructive API cần confirm</Badge>}
            <span className="font-mono text-xs text-text-muted">{env.base_url}</span>
          </div>
          <div className="text-xs text-text-muted mt-1">Variables: {Object.keys(env.variables || {}).join(', ') || '—'} · Secrets: {env.secret_keys.join(', ') || '—'}</div>
          <div className="flex gap-1.5 mt-2 flex-wrap">
            <div className="w-36"><Input value={secretForm[env.id]?.key || ''} placeholder="AUTH_TOKEN"
              onChange={(e) => setSecretForm((s) => ({ ...s, [env.id]: { key: e.target.value, value: s[env.id]?.value || '' } }))} /></div>
            <div className="w-48"><Input type="password" value={secretForm[env.id]?.value || ''} placeholder="secret value"
              onChange={(e) => setSecretForm((s) => ({ ...s, [env.id]: { key: s[env.id]?.key || '', value: e.target.value } }))} /></div>
            <Button size="sm" variant="subtle" onClick={() => saveSecret(env.id)}>Lưu secret</Button>
            {env.secret_keys.map((k) => (
              <button key={k} className="text-[11px] text-text-muted hover:text-rose-500"
                onClick={async () => { await apiClient.qaDeleteEnvSecret(env.id, k); toast.success(`Đã xóa ${k}`); load(); }}>
                ✕ {k}
              </button>
            ))}
            {!env.is_default && (
              <Button size="sm" variant="ghost" onClick={async () => { await apiClient.qaUpdateEnv(env.id, { is_default: true }); load(); }}>
                Đặt default
              </Button>
            )}
          </div>
        </div>
      ))}
      {envs.length === 0 && <p className="text-xs text-text-muted">Chưa có environment. Tạo DEV/STG/UAT trước khi Run.</p>}
    </div>
  );
}

/* ---------------- Flows tab (minimal) ---------------- */
export const FlowTab: React.FC<Props> = ({ activeProject }) => {
  const [flows, setFlows] = useState<APIFlow[]>([]);
  const [tests, setTests] = useState<any[]>([]);
  const [envs, setEnvs] = useState<APIEnvironment[]>([]);
  const [form, setForm] = useState({ name: '', step_case_ids: '', setup_case_id: '', cleanup_case_id: '' });
  const [runEnv, setRunEnv] = useState('');
  const [flowOut, setFlowOut] = useState<Record<string, any>>({});
  const toast = useToast();
  void useNavigate();

  const load = async () => {
    if (!activeProject) return;
    try {
      const [f, t, e] = await Promise.all([
        apiClient.qaListFlows(activeProject.id),
        apiClient.qaListApiTests(activeProject.id),
        apiClient.qaListEnvs(activeProject.id),
      ]);
      setFlows(f); setTests(t); setEnvs(e);
      const def = e.find((x: APIEnvironment) => x.is_default) || e[0];
      if (def && !runEnv) setRunEnv(def.id);
    } catch {
      toast.error('Không tải được flows');
    }
  };

  useEffect(() => { load(); /* eslint-disable-next-line */ }, [activeProject?.id]);

  const create = async () => {
    if (!activeProject || !form.name.trim()) return;
    try {
      await apiClient.qaCreateFlow({
        project_id: activeProject.id, name: form.name,
        step_case_ids: form.step_case_ids.split(',').map((s) => s.trim()).filter(Boolean),
        setup_case_id: form.setup_case_id || null,
        cleanup_case_id: form.cleanup_case_id || null,
      });
      toast.success('Đã tạo flow');
      setForm({ name: '', step_case_ids: '', setup_case_id: '', cleanup_case_id: '' });
      load();
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || 'Tạo thất bại');
    }
  };

  const runFlow = async (flowId: string) => {
    if (!runEnv) { toast.error('Chọn environment'); return; }
    try {
      const out = await apiClient.qaRunFlow(flowId, { environment_id: runEnv });
      setFlowOut((s) => ({ ...s, [flowId]: out }));
      toast.success(`Flow: ${out.pass} PASS / ${out.fail} FAIL`);
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || 'Chạy flow thất bại');
    }
  };

  const tcLabel = (id: string) => {
    const t = tests.find((x: any) => x.id === id);
    return t ? `${t.tc_code} — ${t.title.slice(0, 40)}` : id.slice(0, 8);
  };

  return (
    <div className="space-y-3">
      <p className="text-xs text-text-muted">Flow chạy tuần tự, chia sẻ biến extract (VD: POST /users → {'{{user_id}}'} → GET /users/{'{user_id}'}). Setup/Cleanup là case thường gắn cờ.</p>
      <div className="flex gap-2 flex-wrap">
        <div className="w-48"><Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="User CRUD flow" /></div>
        <div className="flex-1 min-w-[220px]"><Input value={form.step_case_ids} onChange={(e) => setForm({ ...form, step_case_ids: e.target.value })} placeholder="step case ids, cách nhau dấu phẩy" /></div>
        <Button size="sm" leftIcon={<Plus className="w-3.5 h-3.5" />} onClick={create}>Tạo flow</Button>
        <div className="w-44">
          <Select value={runEnv} onChange={(v) => setRunEnv(v as string)}
            options={envs.map((e) => ({ value: e.id, label: e.name }))} />
        </div>
      </div>
      {flows.map((f) => (
        <div key={f.id} className="border border-border-subtle rounded-lg p-3">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-semibold text-sm">{f.name}</span>
            <Button size="sm" variant="subtle" leftIcon={<PlayCircle className="w-3 h-3" />} onClick={() => runFlow(f.id)}>Run flow</Button>
            {flowOut[f.id] && (
              <span className="text-xs">PASS {flowOut[f.id].pass} · <span className="text-rose-500">FAIL {flowOut[f.id].fail}</span>
                {flowOut[f.id].cleanup && ` · cleanup: ${flowOut[f.id].cleanup.status}`}</span>
            )}
          </div>
          <div className="text-xs text-text-muted mt-1">
            Steps: {(f.step_case_ids || []).map(tcLabel).join(' → ') || '—'}
          </div>
          <div className="text-xs text-text-muted mt-1 flex items-center gap-1">
            <LinkIcon className="w-3 h-3" /> Extract vars được chia sẻ giữa các step (cấu hình trong từng test → extract_map).
          </div>
        </div>
      ))}
      {flows.length === 0 && <p className="text-xs text-text-muted">Chưa có flow. Dán case IDs theo thứ tự để tạo.</p>}
      {tests.length > 0 && (
        <details className="text-xs text-text-muted">
          <summary className="cursor-pointer">Xem case IDs</summary>
          {tests.map((t: any) => <div key={t.id} className="font-mono">{t.id} — {t.tc_code} {t.title.slice(0, 50)}</div>)}
        </details>
      )}
    </div>
  );
};
