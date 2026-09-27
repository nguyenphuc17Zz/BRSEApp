import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ShieldCheck, FileSearch, HelpCircle, ListChecks, FlaskConical, AlertTriangle, PlayCircle, Bug as BugIcon, Sparkles, Zap, Monitor, GitBranch, ClipboardList, Table2 } from 'lucide-react';
import { apiClient } from '../../api/client';
import { Project } from '../../types';
import { QAOverview } from '../../types/qa';
import { useToast } from '../../context/ToastContext';
import { PageHeader } from '../../components/ui/PageHeader';
import { Card, CardContent } from '../../components/ui/Card';
import { Button } from '../../components/ui/Button';

import { QuickQACopilotModal } from '../../components/modals/QuickQACopilotModal';

interface Props {
  activeProject: Project | null;
}

export const QAOverviewPage: React.FC<Props> = ({ activeProject }) => {
  const [overview, setOverview] = useState<QAOverview | null>(null);
  const [uiExtra, setUiExtra] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [isQuickQAOpen, setIsQuickQAOpen] = useState(false);
  const toast = useToast();
  const navigate = useNavigate();

  const load = async () => {
    if (!activeProject) {
      setLoading(false);
      return;
    }
    setLoading(true);
    try {
      const [data, ui, dq] = await Promise.all([
        apiClient.qaGetOverview(activeProject.id),
        apiClient.qaUiOverview(activeProject.id).catch(() => null),
        apiClient.qaDataOverview(activeProject.id).catch(() => null),
      ]);
      setOverview({
        ...data,
        ...(ui || {}),
        data_jobs: dq?.jobs || 0,
        data_records: dq?.records_compared || 0,
        data_differences: dq?.differences || 0,
        data_violations: dq?.rule_violations || 0,
        data_missing: dq?.missing_records || 0,
        data_failures: dq?.failures || 0,
      });
      setUiExtra(ui);
    } catch (e: any) {
      toast.error('Không tải được QA overview');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeProject?.id]);

  const stats: Array<{ label: string; value: number | string; icon: React.ReactNode; action?: string; danger?: boolean }> = overview
    ? [
        { label: 'Tổng requirement', value: overview.total_requirements, icon: <FileSearch className="w-4 h-4" />, action: '/qa/requirements' },
        { label: 'Đã review', value: overview.reviewed_requirements, icon: <ShieldCheck className="w-4 h-4" />, action: '/qa/coverage' },
        { label: 'Cần clarification', value: overview.needs_clarification, icon: <AlertTriangle className="w-4 h-4" />, action: '/qa/coverage', danger: overview.needs_clarification > 0 },
        { label: 'Open questions', value: overview.open_questions, icon: <HelpCircle className="w-4 h-4" />, action: '/qa/requirements' },
        { label: 'AC chưa approve', value: overview.unapproved_ac, icon: <ListChecks className="w-4 h-4" />, action: '/qa/requirements' },
        { label: 'Đã cover', value: overview.covered_requirements, icon: <ShieldCheck className="w-4 h-4" />, action: '/qa/coverage' },
        { label: 'Chưa cover', value: overview.uncovered_requirements, icon: <FileSearch className="w-4 h-4" />, action: '/qa/coverage', danger: overview.uncovered_requirements > 0 },
        { label: 'Testcase draft', value: overview.testcase_draft, icon: <FlaskConical className="w-4 h-4" />, action: '/qa/test-cases' },
        { label: 'Testcase approved', value: overview.testcase_approved, icon: <FlaskConical className="w-4 h-4" />, action: '/qa/test-cases' },
        { label: 'Active test runs', value: overview.active_runs || 0, icon: <PlayCircle className="w-4 h-4" />, action: '/qa/test-runs' },
        { label: 'Exec PASS', value: overview.exec_pass || 0, icon: <PlayCircle className="w-4 h-4" />, action: '/qa/test-runs' },
        { label: 'Exec FAIL', value: overview.exec_fail || 0, icon: <AlertTriangle className="w-4 h-4" />, action: '/qa/test-runs', danger: (overview.exec_fail || 0) > 0 },
        { label: 'Exec BLOCKED', value: overview.exec_blocked || 0, icon: <AlertTriangle className="w-4 h-4" />, action: '/qa/test-runs', danger: (overview.exec_blocked || 0) > 0 },
        { label: 'NOT RUN', value: overview.exec_not_run || 0, icon: <PlayCircle className="w-4 h-4" />, action: '/qa/test-runs' },
        { label: 'Open bugs', value: overview.open_bugs || 0, icon: <BugIcon className="w-4 h-4" />, action: '/qa/bugs', danger: (overview.open_bugs || 0) > 0 },
        { label: 'Retest pending', value: overview.retest_pending || 0, icon: <Sparkles className="w-4 h-4" />, action: '/qa/bugs' },
        { label: 'API tests', value: overview.api_tests || 0, icon: <Zap className="w-4 h-4" />, action: '/qa/api-tests' },
        { label: 'API PASS', value: overview.api_pass || 0, icon: <Zap className="w-4 h-4" />, action: '/qa/api-tests' },
        { label: 'API FAIL', value: overview.api_fail || 0, icon: <AlertTriangle className="w-4 h-4" />, action: '/qa/api-tests', danger: (overview.api_fail || 0) > 0 },
        { label: 'Endpoints covered', value: `${overview.api_endpoints_covered || 0}/${overview.api_endpoints || 0}`, icon: <Zap className="w-4 h-4" />, action: '/qa/coverage' },
        { label: 'Automated UI', value: overview.ui_automated || 0, icon: <Monitor className="w-4 h-4" />, action: '/qa/ui-tests' },
        { label: 'UI PASS', value: overview.ui_pass || 0, icon: <Monitor className="w-4 h-4" />, action: '/qa/ui-tests' },
        { label: 'UI FAIL', value: overview.ui_fail || 0, icon: <AlertTriangle className="w-4 h-4" />, action: '/qa/ui-tests', danger: (overview.ui_fail || 0) > 0 },
        { label: 'Changes pending', value: overview.changes_pending || 0, icon: <GitBranch className="w-4 h-4" />, action: '/qa/changes', danger: (overview.changes_pending || 0) > 0 },
        { label: 'Regression required', value: overview.regression_required || 0, icon: <ClipboardList className="w-4 h-4" />, action: '/qa/regression', danger: (overview.regression_required || 0) > 0 },
        { label: 'Regression in progress', value: overview.regression_in_progress || 0, icon: <ClipboardList className="w-4 h-4" />, action: '/qa/regression' },
        { label: 'High-risk changes', value: overview.high_risk_changes || 0, icon: <AlertTriangle className="w-4 h-4" />, action: '/qa/changes', danger: (overview.high_risk_changes || 0) > 0 },
        { label: 'Tests needing update', value: overview.tests_needing_update || 0, icon: <FileSearch className="w-4 h-4" />, action: '/qa/coverage', danger: (overview.tests_needing_update || 0) > 0 },
        { label: 'Data QA jobs', value: overview.data_jobs || 0, icon: <Table2 className="w-4 h-4" />, action: '/qa/data' },
        { label: 'Records compared', value: overview.data_records || 0, icon: <Table2 className="w-4 h-4" />, action: '/qa/data' },
        { label: 'Data differences', value: overview.data_differences || 0, icon: <AlertTriangle className="w-4 h-4" />, action: '/qa/data', danger: (overview.data_differences || 0) > 0 },
        { label: 'Rule violations', value: overview.data_violations || 0, icon: <AlertTriangle className="w-4 h-4" />, action: '/qa/data', danger: (overview.data_violations || 0) > 0 },
        { label: 'Missing records', value: overview.data_missing || 0, icon: <FileSearch className="w-4 h-4" />, action: '/qa/data', danger: (overview.data_missing || 0) > 0 },
      ]
    : [];

  const latestBuild = overview?.latest_build
    ? `Latest build: ${overview.latest_build} (${overview.latest_build_status || '—'})`
    : null;

  return (
    <div className="flex-1 overflow-y-auto p-4 sm:p-6 space-y-4">
      <PageHeader
        title="QA Overview"
        description="Những việc cần action: review requirement, chạy test, fix bug, approve report."
        icon={<ShieldCheck className="w-5 h-5" />}
        badge={latestBuild ? <span className="text-xs text-text-secondary">{latestBuild}</span> : undefined}
        actions={
          <div className="flex items-center gap-2">
            <Button
              size="sm"
              onClick={() => setIsQuickQAOpen(true)}
              leftIcon={<Sparkles className="w-3.5 h-3.5 text-white" />}
              className="bg-purple-600 hover:bg-purple-700 text-white font-semibold shadow-xs"
            >
              Quick QA Studio
            </Button>
            <Button variant="subtle" size="sm" onClick={load}>Refresh</Button>
          </div>
        }
      />
      {!activeProject && (
        <Card><CardContent><p className="text-sm text-text-secondary">Chọn một project để xem QA overview.</p></CardContent></Card>
      )}
      {activeProject && (
        <>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
            {stats.map((s) => (
              <Card key={s.label}>
                <CardContent className="flex items-center gap-3">
                  <div className="p-2 rounded-lg bg-primary/10 text-primary">{s.icon}</div>
                  <div className="min-w-0">
                    <div className={`text-xl font-bold ${s.danger ? 'text-rose-500' : 'text-text-primary'}`}>{loading ? '—' : s.value}</div>
                    <div className="text-xs text-text-secondary truncate">{s.label}</div>
                    {s.action && (
                      <button className="text-[11px] text-primary hover:underline" onClick={() => navigate(s.action!)}>
                        Xem →
                      </button>
                    )}
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
          {overview && overview.needs_clarification > 0 && (
            <Card>
              <CardContent>
                <p className="text-sm text-text-primary">
                  <strong>{overview.needs_clarification}</strong> requirement đang <strong>Blocked by Clarification</strong> — cần confirm với khách trước khi viết AC/testcase.
                </p>
                <div className="mt-2">
                  <Button size="sm" onClick={() => navigate('/qa/coverage')}>Mở Coverage</Button>
                </div>
              </CardContent>
            </Card>
          )}
          {uiExtra && ((uiExtra.needs_update || 0) > 0 || (uiExtra.flaky || 0) > 0 || (uiExtra.review_required || 0) > 0) && (
            <Card>
              <CardContent>
                <p className="text-sm text-text-primary">
                  UI automation cần chú ý: <strong>{uiExtra.needs_update || 0}</strong> needs update ·{' '}
                  <strong>{uiExtra.flaky || 0}</strong> flaky · <strong>{uiExtra.review_required || 0}</strong> chờ review.
                </p>
                <div className="mt-2">
                  <Button size="sm" onClick={() => navigate('/qa/ui-tests')}>Mở UI Tests</Button>
                </div>
              </CardContent>
            </Card>
          )}
          {uiExtra && (uiExtra.recent_failures?.length || 0) > 0 && (
            <Card>
              <CardContent>
                <div className="text-sm font-semibold mb-1">Recent UI Failures</div>
                {uiExtra.recent_failures.map((f: any) => (
                  <div key={f.execution_id} className="text-xs text-text-secondary py-0.5">
                    <span className="font-mono text-primary">{f.tc_code}</span> {f.title}
                  </div>
                ))}
              </CardContent>
            </Card>
          )}
        </>
      )}

      {/* Quick QA Copilot Modal */}
      <QuickQACopilotModal
        isOpen={isQuickQAOpen}
        onClose={() => setIsQuickQAOpen(false)}
        activeProject={activeProject}
      />
    </div>
  );
};
