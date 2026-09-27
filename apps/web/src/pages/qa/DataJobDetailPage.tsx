import React, { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { Database, PlayCircle, Sparkles, Bug as BugIcon, Copy } from 'lucide-react';
import { apiClient } from '../../api/client';
import { Project } from '../../types';
import { DataDifference, DataRule, FieldMapping } from '../../types/qa';
import { useToast } from '../../context/ToastContext';
import { useConfirm } from '../../context/ConfirmDialogContext';
import { PageHeader } from '../../components/ui/PageHeader';
import { Card, CardContent } from '../../components/ui/Card';
import { Badge } from '../../components/ui/Badge';
import { Button } from '../../components/ui/Button';
import { Input } from '../../components/ui/Input';
import { Select } from '../../components/ui/Select';
import { Modal } from '../../components/ui/Modal';
import { EmptyState } from '../../components/ui/EmptyState';
import { statusVariant, severityVariant } from './qaHelpers';

interface Props {
  activeProject: Project | null;
}

const RULE_TYPES = ['required', 'unique', 'range', 'format', 'ref_integrity',
  'cross_field', 'calculation', 'consistency', 'mapping', 'custom_sql'];

export const DataJobDetailPage: React.FC<Props> = ({ activeProject }) => {
  void activeProject;
  const { id } = useParams<{ id: string }>();
  const [job, setJob] = useState<any>(null);
  const [mappings, setMappings] = useState<FieldMapping[]>([]);
  const [rules, setRules] = useState<DataRule[]>([]);
  const [diffs, setDiffs] = useState<DataDifference[]>([]);
  const [diffFilter, setDiffFilter] = useState('');
  const [summary, setSummary] = useState<any>(null);
  const [executionId, setExecutionId] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const [showRule, setShowRule] = useState(false);
  const [ruleForm, setRuleForm] = useState({ rule_type: 'required', definition: '{}' });
  const [showReport, setShowReport] = useState(false);
  const [report, setReport] = useState<any>(null);
  const [copied, setCopied] = useState(false);
  const toast = useToast();
  const confirm = useConfirm();
  const navigate = useNavigate();

  const load = async () => {
    if (!id) return;
    try {
      const [j, m, r, d] = await Promise.all([
        apiClient.qaGetDataJob(id),
        apiClient.qaListMappings(id),
        apiClient.qaListDataRules(job?.project_id || '', { job_id: id }).catch(() => [] as DataRule[]),
        apiClient.qaListDifferences(id, { limit: 200 }).catch(() => [] as DataDifference[]),
      ]);
      setJob(j);
      setMappings(m);
      setRules(r);
      setDiffs(d);
    } catch {
      toast.error('Không tải được job');
    }
  };

  useEffect(() => { load(); /* eslint-disable-next-line */ }, [id]);

  const suggestMappings = async () => {
    if (!id) return;
    try {
      const out = await apiClient.qaSuggestMappings(id);
      toast.success(`AI đề xuất ${out.length} mappings (DRAFT) — hãy review`);
      load();
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || 'Suggest thất bại');
    }
  };

  const approveMapping = async (m: FieldMapping) => {
    try {
      await apiClient.qaUpdateMapping(m.id, { status: 'APPROVED' });
      toast.success('Đã approve mapping');
      load();
    } catch {
      toast.error('Approve thất bại');
    }
  };

  const generateRules = async () => {
    if (!id || !job?.requirement_id) { toast.error('Job chưa link requirement'); return; }
    try {
      const out = await apiClient.qaGenerateDataRules(job.project_id, {
        requirement_id: job.requirement_id, job_id: id,
      });
      toast.success(`AI đề xuất ${out.length} rules (DRAFT)`);
      load();
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || 'Generate thất bại');
    }
  };

  const createRule = async () => {
    if (!id || !job) return;
    let definition: any = {};
    try {
      definition = ruleForm.definition.trim() ? JSON.parse(ruleForm.definition) : {};
    } catch {
      toast.error('Definition phải là JSON hợp lệ');
      return;
    }
    try {
      await apiClient.qaCreateDataRule(job.project_id, {
        job_id: id, requirement_id: job.requirement_id,
        rule_type: ruleForm.rule_type, definition,
      });
      toast.success('Đã tạo rule (DRAFT)');
      setShowRule(false);
      setRuleForm({ rule_type: 'required', definition: '{}' });
      load();
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || 'Tạo thất bại');
    }
  };

  const approveRule = async (r: DataRule) => {
    try {
      await apiClient.qaUpdateDataRule(r.id, { status: 'APPROVED' });
      toast.success('Đã approve rule');
      load();
    } catch {
      toast.error('Approve thất bại');
    }
  };

  const runJob = async () => {
    if (!id) return;
    setRunning(true);
    try {
      const out = await apiClient.qaRunDataJob(id, {});
      setSummary(out.summary);
      setExecutionId(out.execution_id);
      toast.success(out.status === 'PASS' ? 'PASS — không có difference' : `FAIL — ${out.summary.total_differences} differences`);
      load();
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || 'Run thất bại');
    } finally {
      setRunning(false);
    }
  };

  const genBug = async () => {
    if (!executionId) { toast.error('Chạy job trước'); return; }
    try {
      const draft = await apiClient.qaDraftDataBug(executionId, {});
      const bug = await apiClient.qaCreateBug(executionId, { ...draft, status: 'PROPOSED' });
      toast.success('Đã tạo bug (DRAFT) — nhớ review');
      for (const did of (draft.diff_ids || []).slice(0, 20)) {
        await apiClient.qaUpdateDifference(did, { status: 'BUG_FILED' }).catch(() => undefined);
      }
      load();
      navigate(`/qa/bugs/${bug.id}`);
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || 'Tạo bug thất bại');
    }
  };

  const openReport = async () => {
    if (!id) return;
    try {
      const rep = await apiClient.qaDataJobReport(id, executionId || undefined);
      setReport(rep);
      setShowReport(true);
    } catch {
      toast.error('Tạo report thất bại');
    }
  };

  if (!job) return <div className="flex-1 p-6 text-sm text-text-muted">Đang tải job...</div>;

  const filteredDiffs = diffFilter ? diffs.filter((d) => d.diff_type === diffFilter) : diffs;
  const byType: Record<string, number> = {};
  diffs.forEach((d) => { byType[d.diff_type] = (byType[d.diff_type] || 0) + 1; });

  return (
    <div className="flex-1 overflow-y-auto p-4 sm:p-6 space-y-4">
      <PageHeader
        title={<span><span className="font-mono text-primary mr-2">{job.job_code}</span>{job.name}</span>}
        description={job.purpose}
        icon={<Database className="w-5 h-5" />}
        breadcrumbs={[{ label: 'Data QA', onClick: () => navigate('/qa/data') }, { label: job.job_code }]}
        badge={<div className="flex gap-1.5 flex-wrap">
          <Badge variant={statusVariant(job.status)}>{job.status}</Badge>
          {job.build && <Badge variant="neutral">{job.build}</Badge>}
        </div>}
        actions={
          <div className="flex gap-1.5">
            <Button size="sm" variant="subtle" onClick={openReport}>Report</Button>
            <Button size="sm" disabled={running} leftIcon={<PlayCircle className="w-3.5 h-3.5" />} onClick={runJob}>
              {running ? 'Đang chạy...' : 'Run Comparison'}
            </Button>
          </div>
        }
      />

      {job.requirement_id && (
        <button className="text-xs text-primary hover:underline" onClick={() => navigate(`/qa/requirements/${job.requirement_id}`)}>
          Requirement liên quan →
        </button>
      )}

      {summary && (
        <Card>
          <CardContent>
            <div className="text-sm font-semibold mb-1">
              Summary — Compared {summary.compared} records · Matched {summary.matched}
            </div>
            <div className="flex gap-2 flex-wrap text-xs">
              <Badge variant={summary.missing > 0 ? 'danger' : 'success'}>Missing {summary.missing}</Badge>
              <Badge variant={summary.extra > 0 ? 'warning' : 'success'}>Extra {summary.extra}</Badge>
              <Badge variant={summary.mismatch > 0 ? 'danger' : 'success'}>Mismatch {summary.mismatch}</Badge>
              <Badge variant={summary.rule_violations > 0 ? 'danger' : 'success'}>Rule violations {summary.rule_violations}</Badge>
              <Badge variant={summary.duplicates > 0 ? 'warning' : 'neutral'}>Duplicates {summary.duplicates}</Badge>
              <Badge variant={summary.encoding > 0 ? 'warning' : 'neutral'}>Encoding {summary.encoding}</Badge>
            </div>
            {(summary.warnings || []).length > 0 && (
              <div className="text-[11px] text-amber-600 mt-1">{summary.warnings.join(' · ')}</div>
            )}
            <div className="mt-2">
              <Button size="sm" variant="subtle" leftIcon={<BugIcon className="w-3.5 h-3.5" />} onClick={genBug}>
                Generate Bug từ differences
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Card>
          <CardContent className="space-y-2">
            <div className="flex items-center justify-between">
              <div className="text-sm font-semibold">Field Mappings ({mappings.length})</div>
              <Button size="sm" variant="subtle" leftIcon={<Sparkles className="w-3 h-3" />} onClick={suggestMappings}>
                AI Suggest
              </Button>
            </div>
            {mappings.length === 0 && <p className="text-xs text-text-muted">Chưa có mapping. Bấm AI Suggest hoặc tự thêm ở API.</p>}
            {mappings.map((m) => (
              <div key={m.id} className="flex items-center gap-1.5 text-xs border border-border-subtle rounded-lg px-2 py-1.5 flex-wrap">
                <span className="font-mono">{m.source_field}</span>
                <span className="text-text-muted">→</span>
                <span className="font-mono">{m.dest_field}</span>
                {m.transform && <Badge variant="info">transform</Badge>}
                {m.ignored && <Badge variant="neutral">ignored</Badge>}
                {m.ai_suggested && <Badge variant="purple">AI</Badge>}
                <Badge variant={m.status === 'APPROVED' ? 'success' : 'warning'}>{m.status}</Badge>
                {m.status !== 'APPROVED' && (
                  <button className="text-primary hover:underline ml-auto" onClick={() => approveMapping(m)}>Approve</button>
                )}
              </div>
            ))}
          </CardContent>
        </Card>

        <Card>
          <CardContent className="space-y-2">
            <div className="flex items-center justify-between">
              <div className="text-sm font-semibold">Data Quality Rules ({rules.length})</div>
              <div className="flex gap-1.5">
                <Button size="sm" variant="subtle" leftIcon={<Sparkles className="w-3 h-3" />} onClick={generateRules}>
                  AI Generate
                </Button>
                <Button size="sm" variant="ghost" onClick={() => setShowRule(true)}>+ Rule</Button>
              </div>
            </div>
            {rules.length === 0 && <p className="text-xs text-text-muted">Chưa có rule.</p>}
            {rules.map((r) => (
              <div key={r.id} className="flex items-center gap-1.5 text-xs border border-border-subtle rounded-lg px-2 py-1.5 flex-wrap">
                <Badge variant="info">{r.rule_type}</Badge>
                <span className="font-mono flex-1 truncate">{JSON.stringify(r.definition)}</span>
                {r.ai_generated && <Badge variant="purple">AI Suggested</Badge>}
                <Badge variant={r.status === 'APPROVED' ? 'success' : r.status === 'DRAFT' ? 'warning' : 'neutral'}>{r.status}</Badge>
                {r.status === 'DRAFT' && (
                  <button className="text-primary hover:underline" onClick={() => approveRule(r)}>Approve</button>
                )}
              </div>
            ))}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardContent className="space-y-2">
          <div className="flex items-center gap-2 flex-wrap">
            <div className="text-sm font-semibold">Differences ({diffs.length})</div>
            <div className="w-44">
              <Select value={diffFilter} onChange={(v) => setDiffFilter(v as string)}
                options={[{ value: '', label: 'Mọi loại' }, { value: 'missing', label: 'Missing' }, { value: 'extra', label: 'Extra' }, { value: 'mismatch', label: 'Mismatch' }, { value: 'rule_violation', label: 'Rule violation' }, { value: 'duplicate', label: 'Duplicate' }, { value: 'encoding', label: 'Encoding' }]} />
            </div>
          </div>
          {filteredDiffs.length === 0 && <EmptyState title="Chưa có difference" description="Chạy comparison để phát hiện lệch." />}
          {filteredDiffs.slice(0, 100).map((d) => (
            <div key={d.id} className="border border-border-subtle rounded-lg p-2 text-xs space-y-0.5">
              <div className="flex items-center gap-1.5 flex-wrap">
                <Badge variant={d.diff_type === 'missing' || d.diff_type === 'mismatch' ? 'danger' : 'warning'}>{d.diff_type}</Badge>
                <span className="font-mono text-primary">{d.biz_key}</span>
                {d.field && <span className="font-mono">{d.field}</span>}
                <Badge variant={severityVariant(d.severity)}>{d.severity}</Badge>
                <Badge variant={d.status === 'OPEN' ? 'warning' : 'success'}>{d.status}</Badge>
              </div>
              {(d.expected != null || d.actual != null) && (
                <div className="grid grid-cols-2 gap-2">
                  <div><span className="text-text-muted">Source: </span><span className="font-mono break-all">{d.expected}</span></div>
                  <div><span className="text-text-muted">Dest: </span><span className="font-mono break-all">{d.actual}</span></div>
                </div>
              )}
              {d.severity_reason && <div className="text-text-muted">{d.severity_reason}</div>}
            </div>
          ))}
          {filteredDiffs.length > 100 && (
            <p className="text-[11px] text-text-muted">Hiển thị 100/{filteredDiffs.length} — dùng filter để drill-down.</p>
          )}
        </CardContent>
      </Card>

      <Modal isOpen={showRule} onClose={() => setShowRule(false)} title="New Data Quality Rule" size="lg">
        <div className="space-y-2.5">
          <Select value={ruleForm.rule_type} onChange={(v) => setRuleForm({ ...ruleForm, rule_type: v as string })}
            options={RULE_TYPES.map((t) => ({ value: t, label: t }))} />
          <textarea value={ruleForm.definition} onChange={(e) => setRuleForm({ ...ruleForm, definition: e.target.value })} rows={6}
            className="w-full font-mono text-xs bg-surface border border-border-subtle rounded-lg p-2"
            placeholder='{"field": "status", ...} hoặc {"sql": "SELECT ..."} (SELECT-only)' />
          <p className="text-[11px] text-text-muted">
            VD cross_field: {"{"}"if": {"{"}"field":"status","condition":"eq","value":"COMPLETE"{"}"}, "then": {"{"}"field":"completed_at","condition":"not_empty"{"}"}{"}"}.
            Custom SQL: chỉ SELECT đơn, chạy trên snapshot (không đụng DB live).
          </p>
          <div className="flex justify-end gap-2">
            <Button variant="ghost" size="sm" onClick={() => setShowRule(false)}>Hủy</Button>
            <Button size="sm" onClick={createRule}>Tạo (DRAFT)</Button>
          </div>
        </div>
      </Modal>

      <Modal isOpen={showReport} onClose={() => setShowReport(false)} title="Data QA Report" size="2xl">
        {report && (
          <div className="space-y-2">
            <div className="flex gap-2">
              <Button size="sm" variant="subtle" leftIcon={<Copy className="w-3 h-3" />} onClick={() => {
                navigator.clipboard.writeText(report.markdown_vi + '\n\n' + report.markdown_ja);
                setCopied(true);
                setTimeout(() => setCopied(false), 1500);
              }}>{copied ? 'Đã copy!' : 'Copy VI+JA'}</Button>
            </div>
            <pre className="text-xs bg-surface-subtle border border-border-subtle rounded-lg p-3 whitespace-pre-wrap max-h-96 overflow-y-auto">
              {report.markdown_vi}{'\n\n---\n\n'}{report.markdown_ja}
            </pre>
          </div>
        )}
      </Modal>
    </div>
  );
};

export default DataJobDetailPage;
