import React, { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { Bug as BugIcon, Sparkles } from 'lucide-react';
import { apiClient } from '../../api/client';
import { Project } from '../../types';
import { BugDetail } from '../../types/qa';
import { useToast } from '../../context/ToastContext';
import { PageHeader } from '../../components/ui/PageHeader';
import { Card, CardContent } from '../../components/ui/Card';
import { Badge } from '../../components/ui/Badge';
import { Button } from '../../components/ui/Button';
import { Select } from '../../components/ui/Select';
import { BugUxBadge } from './execComponents';
import { severityVariant } from './qaHelpers';

interface Props {
  activeProject: Project | null;
}

const UX_FLOW = ['OPEN', 'CONFIRMED', 'IN_PROGRESS', 'FIXED', 'RETEST', 'CLOSED', 'REJECTED'];

export const BugDetailPage: React.FC<Props> = ({ activeProject }) => {
  void activeProject;
  const { id } = useParams<{ id: string }>();
  const [bug, setBug] = useState<BugDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [ux, setUx] = useState('');
  const toast = useToast();
  const navigate = useNavigate();

  const load = async () => {
    if (!id) return;
    setLoading(true);
    try {
      const d = await apiClient.qaGetBug(id);
      setBug(d);
      setUx(d.ux_status);
    } catch {
      toast.error('Không tải được bug');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  const changeUx = async () => {
    if (!id || !ux) return;
    try {
      const d = await apiClient.qaUpdateBug(id, { ux_status: ux });
      setBug(d);
      toast.success(`Bug → ${ux}`);
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || 'Đổi status thất bại');
    }
  };

  const retest = async () => {
    if (!bug?.execution_id) return;
    try {
      const ne = await apiClient.qaRetest(bug.execution_id);
      toast.success(`Đã tạo retest attempt #${ne.attempt_no}`);
      load();
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || 'Tạo retest thất bại');
    }
  };

  if (loading) return <div className="flex-1 p-6 text-sm text-text-muted">Đang tải bug...</div>;
  if (!bug) return <div className="flex-1 p-6 text-sm text-text-muted">Không tìm thấy bug.</div>;

  const d = bug.details || {};
  const steps: string[] = Array.isArray(d.steps) ? d.steps : [];

  return (
    <div className="flex-1 overflow-y-auto p-4 sm:p-6 space-y-4">
      <PageHeader
        title={<span><span className="font-mono text-primary mr-2">{bug.bug_code}</span>{bug.title}</span>}
        icon={<BugIcon className="w-5 h-5" />}
        breadcrumbs={[{ label: 'Bugs', onClick: () => navigate('/qa/bugs') }, { label: bug.bug_code || 'Bug' }]}
        badge={<div className="flex gap-1.5 flex-wrap"><BugUxBadge ux={bug.ux_status} /><Badge variant={severityVariant(bug.priority)}>{bug.priority}</Badge></div>}
        actions={
          <div className="flex gap-1.5 items-center">
            <div className="w-40">
              <Select value={ux} onChange={(v) => setUx(v as string)}
                options={UX_FLOW.map((s) => ({ value: s, label: s }))} />
            </div>
            <Button size="sm" onClick={changeUx}>Đổi status</Button>
          </div>
        }
      />

      {/* Traceability */}
      <Card>
        <CardContent>
          <div className="text-xs font-semibold text-text-secondary mb-2">TRACEABILITY</div>
          <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs">
            {bug.requirement_id && (
              <button className="text-primary hover:underline" onClick={() => navigate(`/qa/requirements/${bug.requirement_id}`)}>
                {bug.req_code} — {bug.requirement_title} (Requirement) →
              </button>
            )}
            {bug.test_case_id && (
              <span className="text-text-secondary">{bug.tc_code} — {bug.test_case_title} (Test Case)</span>
            )}
            {bug.test_run_id && (
              <button className="text-primary hover:underline" onClick={() => navigate(`/qa/test-runs/${bug.test_run_id}`)}>
                {bug.run_code} (Test Run) →
              </button>
            )}
            {bug.assignee && <span className="text-text-muted">Assignee: {bug.assignee}</span>}
          </div>
        </CardContent>
      </Card>

      {/* JA / VI report */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Card>
          <CardContent className="space-y-1.5 text-xs">
            <div className="font-semibold text-text-primary">🇻🇳 Vietnamese</div>
            {d.summary_vi && <div><span className="font-semibold">Tóm tắt:</span> {d.summary_vi}</div>}
            {d.preconditions && <div><span className="font-semibold">Tiền điều kiện:</span> {d.preconditions}</div>}
            {d.expected_result && <div><span className="font-semibold">Expected:</span> {d.expected_result}</div>}
            {d.actual_result && <div><span className="font-semibold">Actual:</span> {d.actual_result}</div>}
            {d.reproduction_rate && <div><span className="font-semibold">Tái hiện:</span> {d.reproduction_rate}</div>}
            {bug.description && <div className="text-text-muted whitespace-pre-wrap">{bug.description}</div>}
          </CardContent>
        </Card>
        <Card>
          <CardContent className="space-y-1.5 text-xs">
            <div className="font-semibold text-text-primary">🇯🇵 日本語</div>
            {d.summary_ja && <div><span className="font-semibold">【不具合概要】</span> {d.summary_ja}</div>}
            {d.environment && <div><span className="font-semibold">【環境】</span> {d.environment}</div>}
            {steps.length > 0 && (
              <div><span className="font-semibold">【再現手順】</span>
                <ol className="list-decimal ml-4">{steps.map((s, i) => <li key={i}>{s}</li>)}</ol>
              </div>
            )}
            {d.notes_ja && <div><span className="font-semibold">【備考】</span> {d.notes_ja}</div>}
          </CardContent>
        </Card>
      </div>

      {/* Evidence + retest */}
      <Card>
        <CardContent className="space-y-2">
          <div className="text-xs font-semibold text-text-secondary">EVIDENCE ({bug.evidence?.length || 0})</div>
          {(bug.evidence || []).map((e) => (
            <div key={e.id} className="text-xs border border-border-subtle rounded-lg p-2">
              <span className="font-mono text-primary">[{e.source_type}]</span> {e.quote_text}
            </div>
          ))}
          {(bug.evidence?.length || 0) === 0 && <p className="text-xs text-text-muted">Chưa có evidence.</p>}
          {(bug.retests?.length || 0) > 0 && (
            <div className="text-xs">Retest history: {bug.retests.map((r) => `#${r.attempt_no} ${r.status}`).join(' → ')}</div>
          )}
          {['FIXED', 'CONFIRMED', 'IN_PROGRESS'].includes(bug.ux_status) && bug.execution_id && (
            <Button size="sm" variant="subtle" leftIcon={<Sparkles className="w-3 h-3" />} onClick={retest}>
              Create Retest
            </Button>
          )}
        </CardContent>
      </Card>
    </div>
  );
};

export default BugDetailPage;
