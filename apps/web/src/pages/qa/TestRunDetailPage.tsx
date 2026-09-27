import React, { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { PlayCircle, Plus, FileText, Bug as BugIcon, Paperclip, Sparkles } from 'lucide-react';
import { apiClient } from '../../api/client';
import { Project } from '../../types';
import { TestExecution, TestEvidence, QAReport } from '../../types/qa';
import { useToast } from '../../context/ToastContext';
import { useConfirm } from '../../context/ConfirmDialogContext';
import { PageHeader } from '../../components/ui/PageHeader';
import { Card, CardContent } from '../../components/ui/Card';
import { Badge } from '../../components/ui/Badge';
import { Button } from '../../components/ui/Button';
import { Input } from '../../components/ui/Input';
import { Select } from '../../components/ui/Select';
import { Modal } from '../../components/ui/Modal';
import { ProgressBar, EvidenceViewer, ReportPreview, BugUxBadge } from './execComponents';
import { statusVariant, ExecBadge, useQAProviders } from './qaHelpers';

interface Props {
  activeProject: Project | null;
}

export const TestRunDetailPage: React.FC<Props> = ({ activeProject }) => {
  void activeProject;
  const { id } = useParams<{ id: string }>();
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [currentId, setCurrentId] = useState<string | null>(null);
  const [execDetail, setExecDetail] = useState<any>(null);
  const [actual, setActual] = useState('');
  const [busy, setBusy] = useState(false);
  const [showAddCases, setShowAddCases] = useState(false);
  const [scopeForm, setScopeForm] = useState({ priorities: '', case_types: '', approved_only: true });
  const [showReport, setShowReport] = useState(false);
  const [reportType, setReportType] = useState('summary');
  const [report, setReport] = useState<QAReport | null>(null);
  const [reports, setReports] = useState<QAReport[]>([]);
  const [evNote, setEvNote] = useState('');
  const toast = useToast();
  const confirm = useConfirm();
  const navigate = useNavigate();
  const { opts, picker } = useQAProviders();

  const load = async (keepCurrent = true) => {
    if (!id) return;
    try {
      const d = await apiClient.qaGetTestRun(id);
      setData(d);
      if (!keepCurrent || !currentId) {
        const first = (d.executions || []).find((e: TestExecution) => ['NOT_RUN', 'RUNNING'].includes(e.status));
        if (first) setCurrentId(first.id);
      }
    } catch {
      toast.error('Không tải được test run');
    } finally {
      setLoading(false);
    }
  };

  const loadExec = async (execId: string) => {
    try {
      const d = await apiClient.qaGetExecution(execId);
      setExecDetail(d);
      setActual(d.execution?.actual_result || '');
    } catch {
      toast.error('Không tải được execution');
    }
  };

  useEffect(() => {
    setLoading(true);
    load(false);
    if (id) apiClient.qaListReports(id).then(setReports).catch(() => undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  useEffect(() => {
    if (currentId) loadExec(currentId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentId]);

  const refresh = async (nextId?: string) => {
    await load(true);
    const target = nextId !== undefined ? nextId : currentId;
    if (target) await loadExec(target);
  };

  const goNext = async () => {
    if (!id) return;
    try {
      const r = await apiClient.qaNextExecution(id, currentId || undefined);
      if (r.execution) {
        setCurrentId(r.execution.id);
      } else {
        toast.success('Hết testcase chưa chạy trong run này');
        await load(true);
      }
    } catch {
      toast.error('Không lấy được testcase tiếp theo');
    }
  };

  const saveResult = async (status: 'PASS' | 'FAIL' | 'BLOCKED' | 'SKIPPED') => {
    if (!currentId) return;
    if ((status === 'FAIL' || status === 'BLOCKED') && !actual.trim()) {
      toast.error('FAIL/BLOCKED cần nhập Actual Result');
      return;
    }
    setBusy(true);
    try {
      await apiClient.qaSaveResult(currentId, { status, actual_result: actual || undefined });
      toast.success(`Đã ghi ${status}`);
      await refresh();
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || 'Ghi kết quả thất bại');
    } finally {
      setBusy(false);
    }
  };

  const addNoteEvidence = async () => {
    if (!currentId || !evNote.trim()) return;
    try {
      await apiClient.qaAddEvidence(currentId, { evidence_type: 'note', title: evNote.slice(0, 80), text_content: evNote });
      toast.success('Đã thêm evidence');
      setEvNote('');
      await refresh();
    } catch {
      toast.error('Thêm evidence thất bại');
    }
  };

  const uploadFile = async (f: File) => {
    if (!currentId) return;
    try {
      await apiClient.qaUploadEvidence(currentId, f, { evidence_type: 'screenshot' });
      toast.success('Đã upload evidence');
      await refresh();
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || 'Upload thất bại');
    }
  };

  const generateBug = async () => {
    if (!currentId) return;
    setBusy(true);
    try {
      const draft = await apiClient.qaDraftBug(currentId, opts);
      await apiClient.qaCreateBug(currentId, { ...draft, status: 'PROPOSED' });
      toast.success('Đã tạo Bug Report (DRAFT) — nhớ review');
      await refresh();
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || 'Tạo bug thất bại');
    } finally {
      setBusy(false);
    }
  };

  const doRetest = async () => {
    if (!currentId) return;
    try {
      const ne = await apiClient.qaRetest(currentId);
      toast.success(`Đã tạo retest attempt #${ne.attempt_no}`);
      setCurrentId(ne.id);
      await refresh(ne.id);
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || 'Tạo retest thất bại');
    }
  };

  const addCases = async () => {
    if (!id) return;
    const scope: any = { approved_only: scopeForm.approved_only };
    if (scopeForm.priorities.trim()) scope.priorities = scopeForm.priorities.split(',').map((s) => s.trim().toUpperCase());
    if (scopeForm.case_types.trim()) scope.case_types = scopeForm.case_types.split(',').map((s) => s.trim());
    try {
      const r = await apiClient.qaAddRunCases(id, scope);
      toast.success(`Đã thêm ${r.added}/${r.matched} testcase`);
      (r.warnings || []).forEach((w: string) => toast.error(w));
      setShowAddCases(false);
      await refresh();
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || 'Thêm thất bại');
    }
  };

  const setStatus = async (status: string) => {
    if (!id) return;
    if (status === 'COMPLETED') {
      const ok = await confirm({ title: 'Complete test run?', message: 'Xác nhận kết thúc đợt test? Các case NOT_RUN sẽ được liệt kê trong report.', confirmText: 'Complete' });
      if (!ok) return;
    }
    try {
      const r = await apiClient.qaUpdateTestRun(id, { status });
      (r.warnings || []).forEach((w: string) => toast.error(w));
      toast.success(`Run → ${status}`);
      await refresh();
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || 'Đổi status thất bại');
    }
  };

  const genReport = async () => {
    if (!id) return;
    setBusy(true);
    try {
      const r = await apiClient.qaGenerateReport(id, { report_type: reportType, ...opts });
      setReport(r);
      const list = await apiClient.qaListReports(id);
      setReports(list);
      toast.success('Đã tạo report (DRAFT)');
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || 'Tạo report thất bại');
    } finally {
      setBusy(false);
    }
  };

  if (loading) return <div className="flex-1 p-6 text-sm text-text-muted">Đang tải test run...</div>;
  if (!data) return <div className="flex-1 p-6 text-sm text-text-muted">Không tìm thấy test run.</div>;

  const run = data.run;
  const executions: TestExecution[] = data.executions || [];
  const current: TestExecution | undefined = executions.find((e) => e.id === currentId) || undefined;
  const detail = execDetail;
  const evItems: TestEvidence[] = detail?.evidence || [];

  return (
    <div className="flex-1 overflow-y-auto p-4 sm:p-6 space-y-4">
      <PageHeader
        title={<span><span className="font-mono text-primary mr-2">{run.run_code}</span>{run.name}</span>}
        description={`${run.version_build ? `Build ${run.version_build} · ` : ''}${run.environment || ''}${run.tester ? ` · Tester: ${run.tester}` : ''}`}
        icon={<PlayCircle className="w-5 h-5" />}
        breadcrumbs={[{ label: 'Test Runs', onClick: () => navigate('/qa/test-runs') }, { label: run.run_code }]}
        badge={<div className="flex gap-1.5 flex-wrap">
          <Badge variant={statusVariant(run.status)}>{run.status}</Badge>
          {(run.run_type && run.run_type !== 'MANUAL') && <Badge variant="purple">{run.run_type}</Badge>}
          {run.scope?.origin === 'regression_plan' && <Badge variant="info">Regression</Badge>}
        </div>}
        actions={
          <div className="flex gap-1.5 flex-wrap">
            {run.status === 'DRAFT' && <Button size="sm" onClick={() => setStatus('READY')}>Ready</Button>}
            {['READY', 'DRAFT'].includes(run.status) && <Button size="sm" onClick={() => setStatus('IN_PROGRESS')}>Start</Button>}
            {run.status === 'IN_PROGRESS' && <Button size="sm" variant="subtle" onClick={() => setStatus('COMPLETED')}>Complete</Button>}
            <Button size="sm" variant="subtle" leftIcon={<Plus className="w-3 h-3" />} onClick={() => setShowAddCases(true)}>Add Cases</Button>
            <Button size="sm" variant="subtle" leftIcon={<FileText className="w-3 h-3" />} onClick={() => setShowReport(true)}>QA Report</Button>
          </div>
        }
      />

      <Card>
        <CardContent>
          <ProgressBar progress={data.progress} />
          {data.risks?.length > 0 && (
            <div className="text-xs text-rose-500 mt-2">Risks chưa giải quyết: {data.risks.join(' · ')}</div>
          )}
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 lg:grid-cols-5 gap-4">
        {/* Case list */}
        <Card>
          <CardContent className="lg:col-span-1 p-2 max-h-[60vh] overflow-y-auto">
            <div className="text-xs font-semibold text-text-secondary px-2 py-1">TEST CASES ({executions.length})</div>
            {executions.map((e) => (
              <button key={e.id}
                onClick={() => setCurrentId(e.id)}
                className={`w-full text-left px-2 py-1.5 rounded-lg text-xs hover:bg-surface-hover ${e.id === currentId ? 'bg-primary/10' : ''}`}>
                <div className="flex items-center gap-1.5">
                  <span className="font-mono text-primary font-semibold">{e.tc_code}</span>
                  <Badge variant={statusVariant(e.status)}>{e.status}</Badge>
                  {e.attempt_no > 1 && <span className="text-[10px] text-text-muted">#{e.attempt_no}</span>}
                  {e.bug_code && <BugUxBadge ux="OPEN" />}
                </div>
                <div className="text-text-primary truncate mt-0.5">{e.tc_title}</div>
              </button>
            ))}
          </CardContent>
        </Card>

        {/* Fast execution panel */}
        <div className="lg:col-span-3 space-y-4">
          <Card>
            <CardContent className="space-y-3">
              {!current && <p className="text-sm text-text-muted">Run chưa có testcase. Nhấn Add Cases.</p>}
              {current && detail && (
                <>
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-mono text-sm text-primary font-bold">{detail.test_case?.tc_code}</span>
                    <span className="text-sm font-semibold text-text-primary">{detail.test_case?.title}</span>
                    <Badge variant={statusVariant(current.status)}>{current.status}</Badge>
                    {current.attempt_no > 1 && <Badge variant="neutral">attempt #{current.attempt_no}</Badge>}
                  </div>
                  {detail.requirement && (
                    <button className="text-xs text-primary hover:underline"
                      onClick={() => navigate(`/qa/requirements/${detail.requirement.id}`)}>
                      {detail.requirement.req_code} — {detail.requirement.title} →
                    </button>
                  )}
                  {detail.acceptance_criterion && (
                    <div className="text-xs bg-surface-subtle border border-border-subtle rounded-lg p-2">
                      <span className="font-mono text-primary">{detail.acceptance_criterion.ac_code}</span>{' '}
                      Given {detail.acceptance_criterion.given_text} · When {detail.acceptance_criterion.when_text} · Then {detail.acceptance_criterion.then_text}
                    </div>
                  )}
                  {detail.test_case?.preconditions && (
                    <div className="text-xs"><span className="font-semibold">Preconditions:</span> {detail.test_case.preconditions}</div>
                  )}
                  <div className="space-y-1">
                    {(detail.test_case?.steps || []).map((s: any, i: number) => (
                      <div key={i} className="text-xs bg-surface-subtle border border-border-subtle rounded p-1.5">
                        <span className="font-semibold">Step {s.step_order}:</span> {s.action}
                        {s.expected && <div className="text-text-secondary">→ {s.expected}</div>}
                      </div>
                    ))}
                  </div>
                  <div className="text-xs"><span className="font-semibold">Expected:</span> {detail.test_case?.expected_result}</div>

                  <div>
                    <label className="text-xs font-semibold text-text-secondary">Actual Result {(current.status === 'FAIL' || current.status === 'BLOCKED') ? '' : '(bắt buộc khi FAIL/BLOCKED)'}</label>
                    <textarea value={actual} onChange={(e) => setActual(e.target.value)} rows={3}
                      className="w-full text-xs bg-surface border border-border-subtle rounded-lg p-2 text-text-primary"
                      placeholder="Nhập kết quả thực tế quan sát được..." />
                  </div>

                  <div className="flex gap-1.5 flex-wrap">
                    <Button size="sm" disabled={busy} onClick={() => saveResult('PASS')}>PASS</Button>
                    <Button size="sm" variant="subtle" disabled={busy} onClick={() => saveResult('FAIL')}>FAIL</Button>
                    <Button size="sm" variant="subtle" disabled={busy} onClick={() => saveResult('BLOCKED')}>BLOCKED</Button>
                    <Button size="sm" variant="ghost" disabled={busy} onClick={() => saveResult('SKIPPED')}>SKIPPED</Button>
                    <Button size="sm" variant="ghost" onClick={goNext}>Next →</Button>
                  </div>

                  <div className="border-t border-border-subtle pt-2 space-y-2">
                    <div className="text-xs font-semibold">Evidence</div>
                    <EvidenceViewer items={evItems} />
                    <div className="flex gap-1.5">
                      <div className="flex-1">
                        <Input value={evNote} onChange={(e) => setEvNote(e.target.value)} placeholder="Ghi chú evidence..." />
                      </div>
                      <Button size="sm" variant="subtle" onClick={addNoteEvidence}>Thêm note</Button>
                      <label className="cursor-pointer">
                        <span className="inline-flex items-center gap-1 text-xs px-2.5 py-1.5 rounded-lg border border-border-subtle hover:bg-surface-hover">
                          <Paperclip className="w-3.5 h-3.5" /> File
                        </span>
                        <input type="file" className="hidden" accept=".png,.jpg,.jpeg,.gif,.webp,.log,.txt,.json,.pdf,.csv"
                          onChange={(e) => { const f = e.target.files?.[0]; if (f) uploadFile(f); e.target.value = ''; }} />
                      </label>
                    </div>
                  </div>

                  {current.status === 'FAIL' && (
                    <div className="border-t border-border-subtle pt-2 flex gap-1.5 flex-wrap items-center">
                      {current.bug_work_item_id ? (
                        <>
                          <BugUxBadge ux="OPEN" />
                          <button className="text-xs text-primary hover:underline font-mono"
                            onClick={() => navigate(`/qa/bugs/${current.bug_work_item_id}`)}>
                            {current.bug_code || 'Bug'} →
                          </button>
                          <Button size="sm" variant="subtle" leftIcon={<Sparkles className="w-3 h-3" />} onClick={doRetest}>
                            Create Retest
                          </Button>
                        </>
                      ) : (
                        <Button size="sm" variant="subtle" disabled={busy}
                          leftIcon={<BugIcon className="w-3.5 h-3.5" />} onClick={generateBug}>
                          Generate Bug
                        </Button>
                      )}
                    </div>
                  )}
                  {detail.bug && !current.bug_work_item_id && (
                    <div className="text-xs">Related bug: <BugUxBadge ux={detail.bug.ux_status} /></div>
                  )}
                  {(detail.attempts?.length || 0) > 1 && (
                    <div className="text-xs text-text-muted">
                      History: {detail.attempts.map((a: any) => `#${a.attempt_no} ${a.status}`).join(' → ')}
                    </div>
                  )}
                </>
              )}
            </CardContent>
          </Card>
        </div>

        {/* Side: failures + bugs */}
        <div className="lg:col-span-1 space-y-4">
          <Card>
            <CardContent>
              <div className="text-xs font-semibold text-text-secondary mb-2">FAILURES ({data.failures?.length || 0})</div>
              {(data.failures || []).map((f: any) => (
                <button key={f.id} onClick={() => setCurrentId(f.id)}
                  className="w-full text-left text-xs py-1 hover:text-primary">
                  <span className="font-mono text-primary">{f.tc_code}</span> {f.tc_title}
                  <div><Badge variant={statusVariant(f.status)}>{f.status}</Badge></div>
                </button>
              ))}
              {(data.failures?.length || 0) === 0 && <p className="text-xs text-text-muted">Không có failure.</p>}
            </CardContent>
          </Card>
          <Card>
            <CardContent>
              <div className="text-xs font-semibold text-text-secondary mb-2">BUGS ({data.bugs?.length || 0})</div>
              {(data.bugs || []).map((b: any) => (
                <button key={b.id} onClick={() => navigate(`/qa/bugs/${b.id}`)}
                  className="w-full text-left text-xs py-1 hover:text-primary">
                  <span className="font-mono text-primary">{b.bug_code}</span> {b.title}
                  <div className="mt-0.5"><BugUxBadge ux={b.ux_status} /></div>
                </button>
              ))}
              {(data.bugs?.length || 0) === 0 && <p className="text-xs text-text-muted">Chưa có bug.</p>}
            </CardContent>
          </Card>
        </div>
      </div>

      {/* Add cases modal */}
      <Modal isOpen={showAddCases} onClose={() => setShowAddCases(false)} title="Add Test Cases" size="lg">
        <div className="space-y-2.5">
          <p className="text-xs text-text-muted">Chỉ REVIEWED/APPROVED được thêm. REJECTED không bao giờ được đưa vào.</p>
          <div>
            <label className="text-xs font-semibold">Priorities (VD: HIGH, CRITICAL — trống = tất cả)</label>
            <Input value={scopeForm.priorities} onChange={(e) => setScopeForm({ ...scopeForm, priorities: e.target.value })} />
          </div>
          <div>
            <label className="text-xs font-semibold">Case types (VD: Happy, Boundary — trống = tất cả)</label>
            <Input value={scopeForm.case_types} onChange={(e) => setScopeForm({ ...scopeForm, case_types: e.target.value })} />
          </div>
          <label className="text-xs flex items-center gap-2">
            <input type="checkbox" checked={scopeForm.approved_only}
              onChange={(e) => setScopeForm({ ...scopeForm, approved_only: e.target.checked })} />
            Chỉ REVIEWED / APPROVED (khuyến nghị)
          </label>
          <div className="flex justify-end gap-2">
            <Button variant="ghost" size="sm" onClick={() => setShowAddCases(false)}>Hủy</Button>
            <Button size="sm" onClick={addCases}>Thêm vào run</Button>
          </div>
        </div>
      </Modal>

      {/* Report modal */}
      <Modal isOpen={showReport} onClose={() => { setShowReport(false); setReport(null); }} title="QA Report" size="2xl">
        <div className="space-y-3">
          <div className="flex gap-2 items-end flex-wrap">
            <div className="w-48">
              <Select value={reportType} onChange={(v) => setReportType(v as string)}
                options={[{ value: 'summary', label: 'QA Summary' }, { value: 'completion', label: 'Test Completion Report' }, { value: 'daily', label: 'Daily QA Status' }]} />
            </div>
            <Button size="sm" disabled={busy} onClick={genReport}>Generate (DRAFT)</Button>
          </div>
          <div className="max-w-md">{picker}</div>
          {report && <ReportPreview vi={report.markdown_vi} ja={report.markdown_ja} />}
          {report && report.status === 'DRAFT' && (
            <Button size="sm" onClick={async () => {
              const r = await apiClient.qaApproveReport(report.id);
              setReport(r);
              toast.success('Đã approve report');
            }}>Approve report</Button>
          )}
          {reports.length > 0 && (
            <div className="text-xs space-y-1">
              <div className="font-semibold">Reports của run:</div>
              {reports.map((r) => (
                <button key={r.id} className="block text-primary hover:underline"
                  onClick={() => setReport(r)}>
                  {r.report_type} · {r.scope_build} · {r.status} · {r.created_at}
                </button>
              ))}
            </div>
          )}
        </div>
      </Modal>
    </div>
  );
};

export default TestRunDetailPage;
