import React, { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import {
  FileSearch, Sparkles, HelpCircle, ListChecks, FlaskConical,
  Check, X, Copy, Trash2, Plus, ClipboardList,
} from 'lucide-react';
import { apiClient } from '../../api/client';
import { Project } from '../../types';
import { RequirementDetail, QAOpenQuestion, QATestCase } from '../../types/qa';
import { useToast } from '../../context/ToastContext';
import { useConfirm } from '../../context/ConfirmDialogContext';
import { PageHeader } from '../../components/ui/PageHeader';
import { Card, CardContent } from '../../components/ui/Card';
import { Badge } from '../../components/ui/Badge';
import { Button } from '../../components/ui/Button';
import { Modal } from '../../components/ui/Modal';
import { Input } from '../../components/ui/Input';
import { CoverageBadge, KnowledgeBadge, severityVariant, statusVariant, useQAProviders, ExecBadge } from './qaHelpers';
import { BugUxBadge } from './execComponents';

interface Props {
  activeProject: Project | null;
}

const SectionTitle: React.FC<{ icon: React.ReactNode; title: string; count?: number; right?: React.ReactNode }> = ({ icon, title, count, right }) => (
  <div className="flex items-center justify-between gap-2 mb-2">
    <div className="flex items-center gap-2 text-sm font-semibold text-text-primary">
      <span className="text-primary">{icon}</span>
      <span>{title}</span>
      {count !== undefined && <Badge variant="neutral">{count}</Badge>}
    </div>
    {right}
  </div>
);

export const RequirementDetailPage: React.FC<Props> = ({ activeProject }) => {
  const { id } = useParams<{ id: string }>();
  const [detail, setDetail] = useState<RequirementDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [editingQ, setEditingQ] = useState<QAOpenQuestion | null>(null);
  const [answerText, setAnswerText] = useState('');
  const [showACModal, setShowACModal] = useState(false);
  const [acForm, setAcForm] = useState({ given_text: '', when_text: '', then_text: '' });
  const [expandedTC, setExpandedTC] = useState<string | null>(null);
  const [autoMap, setAutoMap] = useState<Record<string, { type: string; script_status?: string; last_result?: string }>>({});
  const toast = useToast();
  const confirm = useConfirm();
  const navigate = useNavigate();
  const { opts, picker } = useQAProviders();

  const load = async () => {
    if (!id) return;
    setLoading(true);
    try {
      const data = await apiClient.qaGetDetail(id);
      setDetail(data);
      if (activeProject && (data.test_cases?.length || 0) > 0) {
        try {
          const [uiScripts, apiTests] = await Promise.all([
            apiClient.qaListUiScripts(activeProject.id),
            apiClient.qaListApiTests(activeProject.id, { requirement_id: id }),
          ]);
          const m: Record<string, { type: string; script_status?: string; last_result?: string }> = {};
          (data.test_cases || []).forEach((tc: any) => { m[tc.id] = { type: 'MANUAL' }; });
          (apiTests || []).forEach((t: any) => {
            if (m[t.id]) m[t.id] = { type: 'API', last_result: t.last_result };
          });
          (uiScripts || []).forEach((s: any) => {
            if (m[s.test_case_id]) {
              m[s.test_case_id] = { type: 'WEB_UI', script_status: s.status, last_result: s.last_result };
            }
          });
          setAutoMap(m);
        } catch { /* automation badges optional */ }
      }
    } catch {
      toast.error('Không tải được requirement');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  const run = async (key: string, fn: () => Promise<any>, okMsg: string) => {
    setBusy(key);
    try {
      await fn();
      toast.success(okMsg);
      await load();
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || 'Thao tác thất bại');
    } finally {
      setBusy(null);
    }
  };

  if (loading) return <div className="flex-1 overflow-y-auto p-6 text-sm text-text-muted">Đang tải requirement...</div>;
  if (!detail) return <div className="flex-1 overflow-y-auto p-6 text-sm text-text-muted">Không tìm thấy requirement.</div>;

  const blocked = detail.coverage?.status === 'BlockedByClarification';

  return (
    <div className="flex-1 overflow-y-auto p-4 sm:p-6 space-y-4">
      <PageHeader
        title={<span><span className="font-mono text-primary mr-2">{detail.req_code}</span>{detail.title}</span>}
        description={detail.description}
        icon={<FileSearch className="w-5 h-5" />}
        breadcrumbs={[
          { label: 'Requirement Review', onClick: () => navigate('/qa/requirements') },
          { label: detail.req_code || 'Detail' },
        ]}
        badge={<div className="flex gap-1 flex-wrap"><Badge variant={statusVariant(detail.status)}>{detail.status}</Badge>{detail.coverage && <CoverageBadge value={detail.coverage.status} />}</div>}
      />

      {/* Primary actions */}
      <Card>
        <CardContent className="flex flex-col gap-2">
          <div className="flex flex-wrap gap-2">
            <Button size="sm" isLoading={busy === 'review'} leftIcon={<Sparkles className="w-3.5 h-3.5" />}
              onClick={() => run('review', () => apiClient.qaReviewRequirement(detail.id, { ...opts, force: true }), 'Đã review requirement')}>
              Review Requirement
            </Button>
            <Button size="sm" variant="subtle" isLoading={busy === 'questions'} leftIcon={<HelpCircle className="w-3.5 h-3.5" />}
              onClick={() => run('questions', () => apiClient.qaGenerateQuestions(detail.id, opts), 'Đã tạo câu hỏi confirm')}>
              Generate Questions
            </Button>
            <Button size="sm" variant="subtle" isLoading={busy === 'ac'} leftIcon={<ListChecks className="w-3.5 h-3.5" />}
              onClick={() => run('ac', () => apiClient.qaGenerateAC(detail.id, opts), 'Đã tạo Acceptance Criteria')}>
              Generate Acceptance Criteria
            </Button>
            <Button size="sm" variant="subtle" isLoading={busy === 'tc'} leftIcon={<FlaskConical className="w-3.5 h-3.5" />}
              onClick={() => run('tc', () => apiClient.qaGenerateTestCases(detail.id, opts), 'Đã tạo Test Cases')}>
              Generate Test Cases
            </Button>
            <Button size="sm" variant="ghost" isLoading={busy === 'checklist'} leftIcon={<ClipboardList className="w-3.5 h-3.5" />}
              onClick={() => run('checklist', () => apiClient.qaGenerateTestCases(detail.id, { ...opts, checklist_mode: true }), 'Đã tạo Quick QA Checklist')}>
              Quick Checklist
            </Button>
          </div>
          <div className="max-w-md">{picker}</div>
          {blocked && (
            <p className="text-xs text-rose-500">Requirement đang Blocked by Clarification — nên trả lời câu hỏi confirm trước khi approve AC/testcase.</p>
          )}
        </CardContent>
      </Card>

      {/* Evidence */}
      <Card>
        <CardContent>
          <SectionTitle icon={<FileSearch className="w-4 h-4" />} title="Evidence" count={detail.evidence_items.length} />
          {detail.evidence_items.length === 0 && <p className="text-xs text-text-muted">Nội dung requirement gốc là nguồn duy nhất.</p>}
          {detail.evidence_items.map((e) => (
            <div key={e.id} className="text-xs bg-surface-subtle border border-border-subtle rounded-lg p-2 mb-1.5">
              <span className="font-mono text-primary">[{e.source_type}]</span> “{e.quote_text}”
              {e.author && <span className="text-text-muted"> — {e.author}</span>}
            </div>
          ))}
        </CardContent>
      </Card>

      {/* Findings */}
      <Card>
        <CardContent>
          <SectionTitle icon={<Sparkles className="w-4 h-4" />} title="QA Findings" count={detail.findings.length} />
          {detail.findings.length === 0 && <p className="text-xs text-text-muted">Chưa có finding. Nhấn “Review Requirement”.</p>}
          {detail.findings.map((f) => (
            <div key={f.id} className="border border-border-subtle rounded-lg p-3 mb-2">
              <div className="flex items-center gap-1.5 flex-wrap">
                <Badge variant={severityVariant(f.severity)}>{f.severity}</Badge>
                <Badge variant="info">{f.finding_type}</Badge>
                <KnowledgeBadge value={f.knowledge_class} />
                <Badge variant={statusVariant(f.status)}>{f.status}</Badge>
                <span className="text-[11px] text-text-muted ml-auto">conf {Math.round(f.confidence * 100)}%</span>
              </div>
              <div className="text-sm font-medium text-text-primary mt-1.5">{f.title}</div>
              <div className="text-xs text-text-secondary mt-0.5">{f.description}</div>
              <div className="text-xs text-text-muted mt-1 italic">Evidence: “{f.evidence_quote}”</div>
              {f.suggested_action && <div className="text-xs mt-1"><span className="font-semibold">Gợi ý:</span> {f.suggested_action}</div>}
              {f.status === 'OPEN' && (
                <div className="flex gap-1.5 mt-2">
                  <Button size="sm" variant="subtle" leftIcon={<Check className="w-3 h-3" />}
                    onClick={() => run(`f-${f.id}`, () => apiClient.qaUpdateFinding(f.id, 'RESOLVED'), 'Đã resolve finding')}>
                    Resolve
                  </Button>
                  <Button size="sm" variant="ghost" leftIcon={<X className="w-3 h-3" />}
                    onClick={() => run(`f-${f.id}`, () => apiClient.qaUpdateFinding(f.id, 'IGNORED'), 'Đã ignore finding')}>
                    Ignore
                  </Button>
                </div>
              )}
            </div>
          ))}
        </CardContent>
      </Card>

      {/* Open Questions */}
      <Card>
        <CardContent>
          <SectionTitle icon={<HelpCircle className="w-4 h-4" />} title="Open Questions — Need Confirmation" count={detail.questions.length} />
          {detail.questions.length === 0 && <p className="text-xs text-text-muted">Chưa có câu hỏi. Nhấn “Generate Questions”.</p>}
          {detail.questions.map((q) => (
            <div key={q.id} className="border border-border-subtle rounded-lg p-3 mb-2">
              <div className="flex items-center gap-1.5 flex-wrap">
                <Badge variant={statusVariant(q.status)}>{q.status}</Badge>
                {q.ai_generated && <Badge variant="purple">AI</Badge>}
              </div>
              <div className="text-sm text-text-primary mt-1.5">🇯🇵 {q.question_ja || q.question_vi}</div>
              <div className="text-xs text-text-secondary mt-0.5">🇻🇳 {q.question_vi}</div>
              {q.reason && <div className="text-xs text-text-muted mt-1">Lý do: {q.reason}</div>}
              {q.risk_if_unanswered && <div className="text-xs text-amber-600 mt-0.5">Rủi ro nếu chưa trả lời: {q.risk_if_unanswered}</div>}
              {q.answer_text && <div className="text-xs mt-1 bg-emerald-500/10 border border-emerald-500/20 rounded p-1.5">Trả lời: {q.answer_text}</div>}
              <div className="flex gap-1.5 mt-2 flex-wrap">
                <Button size="sm" variant="subtle" onClick={() => { setEditingQ(q); setAnswerText(q.answer_text || ''); }}>Edit / Answer</Button>
                {q.status === 'DRAFT' && (
                  <Button size="sm" variant="ghost" onClick={() => run(`q-${q.id}`, () => apiClient.qaUpdateQuestion(q.id, { status: 'APPROVED' }), 'Đã approve câu hỏi')}>Approve</Button>
                )}
                {(q.status === 'DRAFT' || q.status === 'APPROVED') && (
                  <Button size="sm" variant="ghost" onClick={() => run(`q-${q.id}`, () => apiClient.qaUpdateQuestion(q.id, { status: 'REJECTED' }), 'Đã reject câu hỏi')}>Reject</Button>
                )}
              </div>
            </div>
          ))}
        </CardContent>
      </Card>

      {/* Acceptance Criteria */}
      <Card>
        <CardContent>
          <SectionTitle icon={<ListChecks className="w-4 h-4" />} title="Acceptance Criteria" count={detail.acceptance_criteria.length}
            right={<Button size="sm" variant="subtle" leftIcon={<Plus className="w-3 h-3" />} onClick={() => setShowACModal(true)}>Thêm tay</Button>} />
          {detail.acceptance_criteria.length === 0 && <p className="text-xs text-text-muted">Chưa có AC. Nhấn “Generate Acceptance Criteria”.</p>}
          {detail.acceptance_criteria.map((a) => (
            <div key={a.id} className="border border-border-subtle rounded-lg p-3 mb-2">
              <div className="flex items-center gap-1.5 flex-wrap">
                <span className="font-mono text-xs text-primary font-semibold">{a.ac_code}</span>
                <Badge variant={statusVariant(a.status)}>{a.status}</Badge>
                <KnowledgeBadge value={a.knowledge_class} />
                {a.ai_generated && <Badge variant="purple">AI · DRAFT</Badge>}
              </div>
              <div className="text-xs mt-1.5 space-y-0.5">
                <div><span className="font-semibold text-emerald-600">Given:</span> <span className="text-text-primary">{a.given_text}</span></div>
                <div><span className="font-semibold text-sky-600">When:</span> <span className="text-text-primary">{a.when_text}</span></div>
                <div><span className="font-semibold text-amber-600">Then:</span> <span className="text-text-primary">{a.then_text}</span></div>
              </div>
              <div className="flex gap-1.5 mt-2 flex-wrap">
                {a.status === 'DRAFT' && (
                  <Button size="sm" variant="subtle" leftIcon={<Check className="w-3 h-3" />}
                    onClick={() => run(`a-${a.id}`, () => apiClient.qaUpdateAC(a.id, { status: 'APPROVED' }), `Đã approve ${a.ac_code}`)}>Approve</Button>
                )}
                {a.status !== 'REJECTED' && (
                  <Button size="sm" variant="ghost" leftIcon={<X className="w-3 h-3" />}
                    onClick={() => run(`a-${a.id}`, () => apiClient.qaUpdateAC(a.id, { status: 'REJECTED' }), `Đã reject ${a.ac_code}`)}>Reject</Button>
                )}
                <Button size="sm" variant="ghost" leftIcon={<Trash2 className="w-3 h-3" />}
                  onClick={async () => {
                    if (await confirm({ title: 'Xóa AC?', message: `Xóa ${a.ac_code}?`, confirmText: 'Xóa', isDestructive: true })) {
                      run(`a-${a.id}`, () => apiClient.qaDeleteAC(a.id), 'Đã xóa AC');
                    }
                  }}>Xóa</Button>
              </div>
            </div>
          ))}
        </CardContent>
      </Card>

      {/* Test Cases */}
      <Card>
        <CardContent>
          <SectionTitle icon={<FlaskConical className="w-4 h-4" />} title="Test Cases" count={detail.test_cases.length} />
          {detail.test_cases.length === 0 && <p className="text-xs text-text-muted">Chưa có testcase. Nhấn “Generate Test Cases” hoặc “Quick Checklist”.</p>}
          {detail.test_cases.map((tc) => (
            <TestCaseRow key={tc.id} tc={tc} run={run} busy={busy} expanded={expandedTC === tc.id}
              auto={autoMap[tc.id]} navigate={navigate}
              onToggle={() => setExpandedTC(expandedTC === tc.id ? null : tc.id)} confirm={confirm} />
          ))}
        </CardContent>
      </Card>

      {/* Coverage */}
      {detail.coverage && (
        <Card>
          <CardContent>
            <SectionTitle icon={<FileSearch className="w-4 h-4" />} title="Coverage" right={<CoverageBadge value={detail.coverage.status} />} />
            <div className="text-xs text-text-secondary space-y-1">
              <div>Đã review: {detail.coverage.has_review ? 'Có' : 'Chưa'} · Findings mở: {detail.coverage.findings_open} · Câu hỏi chưa trả lời: {detail.coverage.questions_unanswered}</div>
              <div>AC: {detail.coverage.ac_approved}/{detail.coverage.ac_total} approved · Testcase: {detail.coverage.tc_total} ({detail.coverage.tc_approved} approved)</div>
              {detail.exec_summary && (
                <div>Execution: {detail.exec_summary.exec_executed}/{detail.exec_summary.exec_total} đã chạy
                  {' '}(PASS {detail.exec_summary.exec_passed} · FAIL {detail.exec_summary.exec_failed} · BLOCKED {detail.exec_summary.exec_blocked}) ·{' '}
                  <ExecBadge value={detail.exec_summary.exec_status} />
                  {detail.exec_summary.last_build && <span> · Last build: {detail.exec_summary.last_build} ({detail.exec_summary.last_result})</span>}
                </div>
              )}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Test history + related bugs (Phase 2) */}
      {((detail.case_history?.length || 0) > 0 || (detail.related_bugs?.length || 0) > 0) && (
        <Card>
          <CardContent>
            <SectionTitle icon={<FileSearch className="w-4 h-4" />} title="Test History & Related Bugs" />
            {(detail.case_history || []).map((h, i) => (
              <div key={i} className="text-xs text-text-secondary py-0.5">
                <span className="font-mono text-primary">{h.tc_code}</span> → {h.status}
                {h.build && <span> (build {h.build}, {h.run_code})</span>}
                {h.bug_code && (
                  <button className="text-primary hover:underline ml-1" onClick={() => {
                    const b = (detail.related_bugs || []).find((x) => x.bug_code === h.bug_code);
                    if (b) navigate(`/qa/bugs/${b.id}`);
                  }}>· Bug {h.bug_code} →</button>
                )}
              </div>
            ))}
            {(detail.related_bugs || []).map((b) => (
              <div key={b.id} className="text-xs py-0.5">
                <button className="text-primary hover:underline" onClick={() => navigate(`/qa/bugs/${b.id}`)}>
                  <span className="font-mono">{b.bug_code}</span> {b.title} →
                </button>{' '}
                <BugUxBadge ux={b.ux_status} />
              </div>
            ))}
          </CardContent>
        </Card>
      )}

      {/* Version history (Phase 5) */}
      <VersionHistoryBlock requirementId={detail.id} />

      {/* Data rules traceability (Phase 6) */}
      <DataRulesBlock requirementId={detail.id} projectId={activeProject?.id} />

      {/* Question edit modal */}
      <Modal isOpen={!!editingQ} onClose={() => setEditingQ(null)} title="Edit / Answer question" size="lg"
        footer={
          <div className="flex gap-2 justify-end">
            <Button variant="ghost" size="sm" onClick={() => setEditingQ(null)}>Đóng</Button>
            <Button size="sm" onClick={() => editingQ && run(`q-${editingQ.id}`,
              () => apiClient.qaUpdateQuestion(editingQ.id, { question_vi: editingQ.question_vi, question_ja: editingQ.question_ja, answer_text: answerText, status: answerText ? 'ANSWERED' : editingQ.status }),
              'Đã lưu câu hỏi')}>Lưu</Button>
          </div>
        }>
        {editingQ && (
          <div className="space-y-2">
            <label className="text-xs font-semibold">Tiếng Việt</label>
            <Input value={editingQ.question_vi} onChange={(e) => setEditingQ({ ...editingQ, question_vi: e.target.value })} />
            <label className="text-xs font-semibold">日本語 (keigo)</label>
            <Input value={editingQ.question_ja} onChange={(e) => setEditingQ({ ...editingQ, question_ja: e.target.value })} />
            <label className="text-xs font-semibold">Câu trả lời của khách</label>
            <Input value={answerText} onChange={(e) => setAnswerText(e.target.value)} placeholder="Nhập câu trả lời → status thành ANSWERED" />
          </div>
        )}
      </Modal>

      {/* Manual AC modal */}
      <Modal isOpen={showACModal} onClose={() => setShowACModal(false)} title="Thêm Acceptance Criteria" size="lg"
        footer={
          <div className="flex gap-2 justify-end">
            <Button variant="ghost" size="sm" onClick={() => setShowACModal(false)}>Đóng</Button>
            <Button size="sm" onClick={() => {
              setShowACModal(false);
              run('ac-manual', () => apiClient.qaCreateAC(detail.id, acForm), 'Đã thêm AC');
              setAcForm({ given_text: '', when_text: '', then_text: '' });
            }}>Thêm</Button>
          </div>
        }>
        <div className="space-y-2">
          <label className="text-xs font-semibold text-emerald-600">Given</label>
          <Input value={acForm.given_text} onChange={(e) => setAcForm({ ...acForm, given_text: e.target.value })} />
          <label className="text-xs font-semibold text-sky-600">When</label>
          <Input value={acForm.when_text} onChange={(e) => setAcForm({ ...acForm, when_text: e.target.value })} />
          <label className="text-xs font-semibold text-amber-600">Then</label>
          <Input value={acForm.then_text} onChange={(e) => setAcForm({ ...acForm, then_text: e.target.value })} />
        </div>
      </Modal>
    </div>
  );
};

const TestCaseRow: React.FC<{
  tc: QATestCase; run: any; busy: string | null; expanded: boolean;
  onToggle: () => void; confirm: any;
  auto?: { type: string; script_status?: string; last_result?: string };
  navigate?: (p: string) => void;
}> = ({ tc, run, busy, expanded, onToggle, confirm, auto, navigate }) => (
  <div className="border border-border-subtle rounded-lg p-3 mb-2">
    <button onClick={onToggle} className="w-full text-left">
      <div className="flex items-center gap-1.5 flex-wrap">
        <span className="font-mono text-xs text-primary font-semibold">{tc.tc_code}</span>
        <Badge variant="info">{tc.case_type}</Badge>
        <Badge variant={tc.priority === 'HIGH' || tc.priority === 'CRITICAL' ? 'danger' : 'neutral'}>{tc.priority}</Badge>
        <Badge variant={statusVariant(tc.status)}>{tc.status}</Badge>
        <KnowledgeBadge value={tc.knowledge_class} />
        {auto && auto.type !== 'MANUAL' && (
          <Badge variant="purple">{auto.type}{auto.script_status ? ` · ${auto.script_status}` : ''}</Badge>
        )}
        {auto?.last_result && (
          <Badge variant={auto.last_result === 'PASS' ? 'success' : 'danger'}>{auto.last_result}</Badge>
        )}
      </div>
      <div className="text-sm font-medium text-text-primary mt-1">{tc.title}</div>
      {tc.purpose && <div className="text-xs text-text-muted">{tc.purpose}</div>}
    </button>
    {expanded && (
      <div className="mt-2 space-y-1.5">
        {tc.preconditions && <div className="text-xs"><span className="font-semibold">Preconditions:</span> {tc.preconditions}</div>}
        {tc.steps.map((s) => (
          <div key={s.id} className="text-xs bg-surface-subtle border border-border-subtle rounded p-1.5">
            <div><span className="font-semibold">Step {s.step_order}:</span> {s.action}</div>
            {s.expected && <div className="text-text-secondary">→ Expected: {s.expected}</div>}
          </div>
        ))}
        <div className="text-xs"><span className="font-semibold">Expected result:</span> {tc.expected_result}</div>
        <div className="text-xs text-text-muted italic">Evidence: “{tc.evidence_quote}”</div>
        <div className="flex gap-1.5 flex-wrap pt-1">
          <Button size="sm" variant="subtle" onClick={() => run(`tc-${tc.id}`, () => apiClient.qaUpdateTestCase(tc.id, { status: 'REVIEWED' }), 'Đã review')}>Reviewed</Button>
          <Button size="sm" variant="subtle" leftIcon={<Check className="w-3 h-3" />} onClick={() => run(`tc-${tc.id}`, () => apiClient.qaUpdateTestCase(tc.id, { status: 'APPROVED' }), 'Đã approve')}>Approve</Button>
          <Button size="sm" variant="ghost" onClick={() => run(`tc-${tc.id}`, () => apiClient.qaUpdateTestCase(tc.id, { status: 'REJECTED' }), 'Đã reject')}>Reject</Button>
          <Button size="sm" variant="ghost" leftIcon={<Copy className="w-3 h-3" />} onClick={() => run(`tc-${tc.id}`, () => apiClient.qaDuplicateTestCase(tc.id), 'Đã duplicate')}>Duplicate</Button>
          <Button size="sm" variant="ghost" leftIcon={<Trash2 className="w-3 h-3" />} onClick={async () => {
            if (await confirm({ title: 'Xóa testcase?', message: `Xóa ${tc.tc_code}?`, confirmText: 'Xóa', isDestructive: true })) {
              run(`tc-${tc.id}`, () => apiClient.qaDeleteTestCase(tc.id), 'Đã xóa testcase');
            }
          }}>Xóa</Button>
          {auto?.type === 'WEB_UI' && navigate && (
            <Button size="sm" variant="subtle" onClick={() => navigate(`/qa/ui-tests/${tc.id}`)}>Mở UI Automation →</Button>
          )}
        </div>
      </div>
    )}
  </div>
);

const VersionHistoryBlock: React.FC<{ requirementId: string }> = ({ requirementId }) => {  const [versions, setVersions] = useState<any[]>([]);
  useEffect(() => {
    apiClient.qaRequirementVersions(requirementId).then(setVersions).catch(() => undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [requirementId]);
  if (!versions.length) return null;
  return (
    <Card>
      <CardContent>
        <SectionTitle icon={<FileSearch className="w-4 h-4" />} title="Version History" count={versions.length} />
        {versions.map((v: any) => (
          <div key={v.id} className="text-xs py-1 border-b border-border-subtle last:border-0">
            <Badge variant="neutral">v{v.version_no}</Badge>{' '}
            <span className="font-medium">{v.title}</span>
            <span className="text-text-muted"> · {v.source} · {v.created_at}</span>
          </div>
        ))}
      </CardContent>
    </Card>
  );
};

const DataRulesBlock: React.FC<{ requirementId: string; projectId?: string }> = ({ requirementId, projectId }) => {
  const [rules, setRules] = useState<any[]>([]);
  useEffect(() => {
    if (projectId) {
      apiClient.qaListDataRules(projectId).then((all: any[]) =>
        setRules(all.filter((r) => r.requirement_id === requirementId))).catch(() => undefined);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [requirementId, projectId]);
  if (!rules.length) return null;
  return (
    <Card>
      <CardContent>
        <SectionTitle icon={<FileSearch className="w-4 h-4" />} title="Data Quality Rules" count={rules.length} />
        {rules.map((r: any) => (
          <div key={r.id} className="text-xs py-1 border-b border-border-subtle last:border-0 flex items-center gap-1.5 flex-wrap">
            <Badge variant="info">{r.rule_type}</Badge>
            <span className="font-mono flex-1 truncate">{JSON.stringify(r.definition)}</span>
            {r.ai_generated && <Badge variant="purple">AI Suggested</Badge>}
            <Badge variant={r.status === 'APPROVED' ? 'success' : 'warning'}>{r.status}</Badge>
          </div>
        ))}
      </CardContent>
    </Card>
  );
};

export default RequirementDetailPage;
