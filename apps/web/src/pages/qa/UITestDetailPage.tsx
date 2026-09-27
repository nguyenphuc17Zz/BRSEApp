import React, { useEffect, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { Monitor, PlayCircle, Sparkles, Bug as BugIcon, Square } from 'lucide-react';
import { apiClient } from '../../api/client';
import { Project } from '../../types';
import { UIScript, APIEnvironment } from '../../types/qa';
import { useToast } from '../../context/ToastContext';
import { useConfirm } from '../../context/ConfirmDialogContext';
import { PageHeader } from '../../components/ui/PageHeader';
import { Card, CardContent } from '../../components/ui/Card';
import { Badge } from '../../components/ui/Badge';
import { Button } from '../../components/ui/Button';
import { Select } from '../../components/ui/Select';
import { statusVariant } from './qaHelpers';
import { BugUxBadge, EvidenceViewer } from './execComponents';

interface Props {
  activeProject: Project | null;
}

const ACTION_LABEL: Record<string, string> = {
  open: 'Open', navigate: 'Navigate', fill: 'Enter', click: 'Click',
  select: 'Select', check: 'Check', press: 'Press key', upload: 'Upload',
  verify_text: 'Verify text', verify_visible: 'Verify visible',
  verify_hidden: 'Verify hidden', verify_url: 'Verify URL',
  verify_enabled: 'Verify enabled', verify_disabled: 'Verify disabled',
  verify_value: 'Verify value', verify_count: 'Verify count',
};

export const UITestDetailPage: React.FC<Props> = ({ activeProject }) => {
  const { id } = useParams<{ id: string }>();
  const [script, setScript] = useState<UIScript | null>(null);
  const [envs, setEnvs] = useState<APIEnvironment[]>([]);
  const [envId, setEnvId] = useState('');
  const [confirmProd, setConfirmProd] = useState(false);
  const [tab, setTab] = useState<'flow' | 'code'>('flow');
  const [execId, setExecId] = useState<string | null>(null);
  const [progress, setProgress] = useState<any>(null);
  const [execDetail, setExecDetail] = useState<any>(null);
  const [analysis, setAnalysis] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const pollRef = useRef<any>(null);
  const toast = useToast();
  const confirm = useConfirm();
  const navigate = useNavigate();

  const load = async () => {
    if (!id) return;
    try {
      const d = await apiClient.qaGetUiScript(id);
      setScript(d);
      if (activeProject) {
        const envList = await apiClient.qaListEnvs(activeProject.id);
        setEnvs(envList);
        const def = envList.find((e: APIEnvironment) => e.is_default) || envList[0];
        if (def && !envId) setEnvId(def.id);
      }
    } catch {
      toast.error('Không tải được automation script');
    }
  };

  useEffect(() => {
    load();
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  const stopPoll = () => { if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; } };

  const poll = async (eid: string) => {
    stopPoll();
    const tick = async () => {
      try {
        const st = await apiClient.qaUiStatus(eid);
        setProgress(st.progress);
        if (['PASS', 'FAIL', 'BLOCKED', 'SKIPPED'].includes(st.status)) {
          stopPoll();
          const full = await apiClient.qaGetExecution(eid);
          setExecDetail(full);
          toast.success(`Automation ${st.status}`);
        }
      } catch {
        stopPoll();
      }
    };
    await tick();
    pollRef.current = setInterval(tick, 2000);
  };

  const runTest = async () => {
    if (!id || !envId) { toast.error('Chọn environment'); return; }
    const env = envs.find((e) => e.id === envId);
    if (env?.is_prod && !confirmProd) { toast.error('Tick xác nhận PROD trước'); return; }
    setBusy(true);
    setAnalysis(null);
    setExecDetail(null);
    try {
      const out = await apiClient.qaRunUiTest(id, { environment_id: envId, confirm_prod: confirmProd });
      setExecId(out.execution_id);
      toast.success('Automation đang chạy nền — theo dõi progress');
      poll(out.execution_id);
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || 'Chạy thất bại');
    } finally {
      setBusy(false);
    }
  };

  const approve = async () => {
    if (!id) return;
    const ok = await confirm({ title: 'Approve automation?', message: 'Đã review flow và cho chạy regression?', confirmText: 'Approve' });
    if (!ok) return;
    try {
      const d = await apiClient.qaUpdateUiScript(id, { status: 'APPROVED' });
      setScript({ ...script!, ...d });
      toast.success('Đã approve automation');
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || 'Approve thất bại');
    }
  };

  const regenerate = async () => {
    if (!id) return;
    try {
      const out = await apiClient.qaGenerateUiScript({ test_case_id: id });
      toast.success(`Đã regenerate v${out.version} (history giữ bản cũ)`);
      load();
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || 'Regenerate thất bại');
    }
  };

  const analyze = async () => {
    if (!execId) return;
    try {
      setAnalysis(await apiClient.qaAnalyzeUiFail(execId, {}));
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || 'Phân tích thất bại');
    }
  };

  const genBug = async () => {
    if (!execId) return;
    try {
      const draft = await apiClient.qaDraftUiBug(execId, {});
      const bug = await apiClient.qaCreateBug(execId, { ...draft, status: 'PROPOSED' });
      toast.success(`Đã tạo ${bug.bug_code} (DRAFT)`);
      navigate(`/qa/bugs/${bug.id}`);
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || 'Tạo bug thất bại');
    }
  };

  if (!script) return <div className="flex-1 p-6 text-sm text-text-muted">Đang tải automation...</div>;
  const env = envs.find((e) => e.id === envId);
  const lastStatus = execDetail?.execution?.status;

  return (
    <div className="flex-1 overflow-y-auto p-4 sm:p-6 space-y-4">
      <PageHeader
        title={<span><span className="font-mono text-primary mr-2">{script.tc_code}</span>UI Automation</span>}
        icon={<Monitor className="w-5 h-5" />}
        breadcrumbs={[{ label: 'UI Tests', onClick: () => navigate('/qa/ui-tests') }, { label: script.tc_code }]}
        badge={<div className="flex gap-1.5 flex-wrap">
          <Badge variant={statusVariant(script.status)}>{script.status}</Badge>
          {script.is_smoke && <Badge variant="primary">SMOKE</Badge>}
          {script.flaky_flag && <Badge variant="warning">Potentially Flaky</Badge>}
          {script.needs_mapping && <Badge variant="danger">Selector Required</Badge>}
          {script.manual_preferred && <Badge variant="warning">Manual Preferred</Badge>}
          <span className="text-[11px] text-text-muted">v{script.script_version} · {script.test_type}</span>
        </div>}
        actions={
          <div className="flex gap-1.5 flex-wrap items-center">
            <div className="w-44">
              <Select value={envId} onChange={(v) => setEnvId(v as string)}
                options={envs.map((e) => ({ value: e.id, label: `${e.name}${e.is_prod ? ' (PROD!)' : ''}` }))} />
            </div>
            {env?.is_prod && (
              <label className="text-xs text-rose-500 flex items-center gap-1">
                <input type="checkbox" checked={confirmProd} onChange={(e) => setConfirmProd(e.target.checked)} /> PROD
              </label>
            )}
            <Button size="sm" disabled={busy} leftIcon={<PlayCircle className="w-3.5 h-3.5" />} onClick={runTest}>
              {busy ? '...' : 'Run UI Test'}
            </Button>
            {script.status !== 'APPROVED' && <Button size="sm" variant="subtle" onClick={approve}>Approve</Button>}
            <Button size="sm" variant="subtle" leftIcon={<Sparkles className="w-3 h-3" />} onClick={regenerate}>Regenerate</Button>
          </div>
        }
      />

      {script.manual_preferred && (
        <Card><CardContent><p className="text-xs text-amber-600">
          Manual Preferred: {script.manual_preferred_reason || 'case này hợp test tay hơn.'} Chạy automation cần force ở API.
        </p></CardContent></Card>
      )}

      {/* Visual flow vs code */}
      <Card>
        <CardContent className="space-y-2">
          <div className="flex gap-1 border-b border-border-subtle pb-2">
            <button onClick={() => setTab('flow')}
              className={`text-xs px-3 py-1.5 rounded-lg ${tab === 'flow' ? 'bg-primary/10 text-primary font-semibold' : 'text-text-secondary'}`}>
              Visual Flow ({script.flow.length} steps)
            </button>
            <button onClick={() => setTab('code')}
              className={`text-xs px-3 py-1.5 rounded-lg ${tab === 'code' ? 'bg-primary/10 text-primary font-semibold' : 'text-text-secondary'}`}>
              Advanced: Playwright Python
            </button>
          </div>
          {tab === 'flow' ? (
            <div className="space-y-1">
              {script.flow.map((s, i) => (
                <div key={i} className="flex items-start gap-2 text-xs border border-border-subtle rounded-lg px-2.5 py-1.5">
                  <span className="font-mono text-primary font-semibold">Step {s.order}</span>
                  <div className="flex-1">
                    <span className="font-semibold">{ACTION_LABEL[s.action] || s.action}:</span> {s.label}
                    {s.value !== '' && s.value != null && <span className="font-mono text-text-secondary"> — {String(s.value).slice(0, 80)}</span>}
                    {s.selector_required && <div className="text-rose-500 font-semibold">Selector Required: {s.element_hint}</div>}
                    {s.assertion_source === 'ai_suggested' && <span className="ml-1"><Badge variant="purple">AI Suggested</Badge></span>}
                  </div>
                </div>
              ))}
              {script.flow.length === 0 && <p className="text-xs text-text-muted">Chưa có flow.</p>}
            </div>
          ) : (
            <pre className="font-mono text-[11px] bg-surface-subtle border border-border-subtle rounded-lg p-3 whitespace-pre overflow-x-auto max-h-96 overflow-y-auto">
              {script.script_text || '(chưa sinh code)'}
            </pre>
          )}
        </CardContent>
      </Card>

      {/* Live progress */}
      {(execId || progress) && (
        <Card>
          <CardContent className="space-y-2">
            <div className="text-sm font-semibold">Execution
              {progress && <span className="ml-2 text-xs text-text-secondary">
                Step {progress.current_step}/{progress.total_steps} · {progress.label} · {progress.browser} · {progress.environment}
              </span>}
            </div>
            {progress && progress.total_steps > 0 && (
              <div className="h-2 rounded-full bg-surface-hover overflow-hidden">
                <div className="h-full bg-primary transition-all"
                  style={{ width: `${(progress.current_step / progress.total_steps) * 100}%` }} />
              </div>
            )}
            <div className="flex gap-1.5">
              <Button size="sm" variant="ghost" leftIcon={<Square className="w-3 h-3" />}
                onClick={async () => { if (execId) { await apiClient.qaUiCancel(execId); stopPoll(); toast.success('Đã hủy'); } }}>
                Cancel
              </Button>
              {lastStatus === 'FAIL' && (
                <>
                  <Button size="sm" variant="subtle" leftIcon={<Sparkles className="w-3 h-3" />} onClick={analyze}>Phân tích FAIL</Button>
                  <Button size="sm" variant="subtle" leftIcon={<BugIcon className="w-3.5 h-3.5" />} onClick={genBug}>Generate Bug</Button>
                </>
              )}
            </div>
            {execDetail && (
              <div className="text-xs space-y-1.5">
                <div><Badge variant={lastStatus === 'PASS' ? 'success' : 'danger'}>{lastStatus}</Badge>{' '}
                  <span className="text-text-secondary">{execDetail.execution?.fail_reason || execDetail.execution?.actual_result}</span></div>
                <EvidenceViewer items={execDetail.evidence || []} />
                {execDetail.bug && <div className="flex items-center gap-2">
                  <BugUxBadge ux={execDetail.bug.ux_status} />
                  <button className="text-primary hover:underline" onClick={() => navigate(`/qa/bugs/${execDetail.bug.id}`)}>
                    {execDetail.bug.bug_code} →
                  </button>
                </div>}
              </div>
            )}
            {analysis && (
              <div className="text-xs border border-border-subtle rounded-lg p-2">
                <div className="font-semibold">{analysis.bucket}</div>
                <div className="text-text-secondary">{analysis.reasoning}</div>
                {(analysis.suggested_next_steps || []).map((s: string, i: number) => <div key={i}>→ {s}</div>)}
                <p className="text-[11px] text-text-muted mt-1">Phân loại sơ bộ — không phải kết luận root cause.</p>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* Version history */}
      {(script.history?.length || 0) > 0 && (
        <Card>
          <CardContent>
            <div className="text-sm font-semibold mb-1">Script Versions</div>
            {script.history!.map((h) => (
              <div key={h.id} className="text-xs text-text-secondary">
                v{h.version} · {h.changed_by} · {h.reason} · {h.created_at}
              </div>
            ))}
          </CardContent>
        </Card>
      )}
    </div>
  );
};

export default UITestDetailPage;
