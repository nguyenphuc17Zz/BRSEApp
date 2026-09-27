import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { GitCompare } from 'lucide-react';
import { apiClient } from '../../api/client';
import { Project } from '../../types';
import { RequirementCoverage } from '../../types/qa';
import { useToast } from '../../context/ToastContext';
import { PageHeader } from '../../components/ui/PageHeader';
import { Card, CardContent } from '../../components/ui/Card';
import { Button } from '../../components/ui/Button';
import { EmptyState } from '../../components/ui/EmptyState';
import { CoverageBadge, ExecBadge } from './qaHelpers';

interface Props {
  activeProject: Project | null;
}

export const CoveragePage: React.FC<Props> = ({ activeProject }) => {
  const [rows, setRows] = useState<RequirementCoverage[]>([]);
  const [execRows, setExecRows] = useState<any[]>([]);
  const [apiRows, setApiRows] = useState<any[]>([]);
  const [uiRows, setUiRows] = useState<any[]>([]);
  const [changeCov, setChangeCov] = useState<any[]>([]);
  const [dataRows, setDataRows] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const toast = useToast();
  const navigate = useNavigate();

  const load = async () => {
    if (!activeProject) {
      setLoading(false);
      return;
    }
    setLoading(true);
    try {
      const data = await apiClient.qaGetCoverage(activeProject.id);
      setRows(data);
      const exec = await apiClient.qaExecutionCoverage(activeProject.id);
      setExecRows(exec);
      const apiCov = await apiClient.qaApiCoverage(activeProject.id);
      setApiRows(apiCov);
      const uiCov = await apiClient.qaUiCoverage(activeProject.id);
      setUiRows(uiCov);
      const dataCov = await apiClient.qaDataCoverage(activeProject.id).catch(() => []);
      setDataRows(dataCov);
      const plans = await apiClient.qaListPlans(activeProject.id).catch(() => []);
      const covs = [];
      for (const p of (plans || []).slice(0, 5)) {
        try {
          const s = await apiClient.qaPlanSummary(p.id);
          covs.push({ plan_code: p.plan_code, plan_id: p.id, ...s });
        } catch { /* ignore */ }
      }
      setChangeCov(covs);
    } catch {
      toast.error('Không tải được coverage');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeProject?.id]);

  return (
    <div className="flex-1 overflow-y-auto p-4 sm:p-6 space-y-4">
      <PageHeader
        title="Coverage"
        description="Design: requirement có testcase chưa? Execution: đã thực sự test chưa (Passed/Failed/Blocked)?"
        icon={<GitCompare className="w-5 h-5" />}
        actions={<Button variant="subtle" size="sm" onClick={load}>Refresh</Button>}
      />
      {!activeProject && (
        <Card><CardContent><p className="text-sm text-text-secondary">Chọn một project để xem coverage.</p></CardContent></Card>
      )}
      {activeProject && (
        <Card>
          <CardContent>
            {loading && <p className="text-xs text-text-muted">Đang tải...</p>}
            {!loading && rows.length === 0 && <EmptyState title="Chưa có requirement" description="Thêm requirement để theo dõi coverage." />}
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="text-left text-text-muted border-b border-border-subtle">
                    <th className="py-2 pr-2">Requirement</th>
                    <th className="py-2 pr-2">Review</th>
                    <th className="py-2 pr-2">Findings</th>
                    <th className="py-2 pr-2">Questions</th>
                    <th className="py-2 pr-2">AC</th>
                    <th className="py-2 pr-2">Testcases</th>
                    <th className="py-2">Coverage</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r) => (
                    <tr key={r.requirement_id} className="border-b border-border-subtle hover:bg-surface-hover">
                      <td className="py-2 pr-2">
                        <button className="text-left text-text-primary font-medium hover:text-primary"
                          onClick={() => navigate(`/qa/requirements/${r.requirement_id}`)}>
                          <span className="font-mono text-primary mr-1">{r.req_code}</span>{r.requirement_title}
                        </button>
                      </td>
                      <td className="py-2 pr-2">{r.has_review ? '✓' : '—'}</td>
                      <td className="py-2 pr-2">{r.findings_open}</td>
                      <td className="py-2 pr-2">{r.questions_unanswered}</td>
                      <td className="py-2 pr-2">{r.ac_approved}/{r.ac_total}</td>
                      <td className="py-2 pr-2">{r.tc_total} ({r.tc_approved} ✓)</td>
                      <td className="py-2"><CoverageBadge value={r.status} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}
      {activeProject && execRows.length > 0 && (
        <Card>
          <CardContent>
            <div className="text-sm font-semibold text-text-primary mb-2">Execution Coverage — đã thực sự test chưa?</div>
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="text-left text-text-muted border-b border-border-subtle">
                    <th className="py-2 pr-2">Requirement</th>
                    <th className="py-2 pr-2">Design</th>
                    <th className="py-2 pr-2">Executed</th>
                    <th className="py-2 pr-2">P/F/B</th>
                    <th className="py-2 pr-2">Last result</th>
                    <th className="py-2 pr-2">Last build</th>
                    <th className="py-2">Exec status</th>
                  </tr>
                </thead>
                <tbody>
                  {execRows.map((r: any) => (
                    <tr key={r.requirement_id} className="border-b border-border-subtle hover:bg-surface-hover">
                      <td className="py-2 pr-2">
                        <button className="text-left text-text-primary font-medium hover:text-primary"
                          onClick={() => navigate(`/qa/requirements/${r.requirement_id}`)}>
                          <span className="font-mono text-primary mr-1">{r.req_code}</span>{r.title}
                        </button>
                      </td>
                      <td className="py-2 pr-2">{r.design_total} cases</td>
                      <td className="py-2 pr-2">{r.exec_executed}/{r.exec_total} ({r.execution_coverage_pct}%)</td>
                      <td className="py-2 pr-2">{r.exec_passed}/{r.exec_failed}/{r.exec_blocked}</td>
                      <td className="py-2 pr-2">{r.last_result || '—'}</td>
                      <td className="py-2 pr-2">{r.last_build || '—'}</td>
                      <td className="py-2"><ExecBadge value={r.exec_status} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}
      {activeProject && apiRows.length > 0 && (
        <Card>
          <CardContent>
            <div className="text-sm font-semibold text-text-primary mb-2">API Endpoint Coverage</div>
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="text-left text-text-muted border-b border-border-subtle">
                    <th className="py-2 pr-2">Endpoint</th>
                    <th className="py-2 pr-2">Tests</th>
                    <th className="py-2 pr-2">Last result</th>
                    <th className="py-2 pr-2">Last build</th>
                    <th className="py-2">Gaps</th>
                  </tr>
                </thead>
                <tbody>
                  {apiRows.map((r: any) => (
                    <tr key={r.id} className="border-b border-border-subtle hover:bg-surface-hover">
                      <td className="py-2 pr-2">
                        <span className="font-mono text-primary mr-1">{r.method}</span>
                        <span className="font-mono">{r.path}</span>
                        <div className="text-text-muted">{r.name}</div>
                      </td>
                      <td className="py-2 pr-2">{r.test_case_count}</td>
                      <td className="py-2 pr-2">{r.last_result ? <ExecBadge value={r.last_result} /> : '—'}</td>
                      <td className="py-2 pr-2">{r.last_build || '—'}</td>
                      <td className="py-2">
                        {(r.gaps || []).length === 0
                          ? <span className="text-emerald-600">OK</span>
                          : (r.gaps || []).map((g: string, i: number) => (
                            <span key={i} className="block text-amber-600">· {g}</span>
                          ))}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}
      {activeProject && uiRows.length > 0 && (
        <Card>
          <CardContent>
            <div className="text-sm font-semibold text-text-primary mb-2">Web Automation Coverage — Manual / API / Web UI</div>
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="text-left text-text-muted border-b border-border-subtle">
                    <th className="py-2 pr-2">Requirement</th>
                    <th className="py-2 pr-2">Design</th>
                    <th className="py-2 pr-2">Web Auto</th>
                    <th className="py-2 pr-2">Manual ✓</th>
                    <th className="py-2 pr-2">API ✓</th>
                    <th className="py-2 pr-2">Web ✓</th>
                    <th className="py-2">Last UI</th>
                  </tr>
                </thead>
                <tbody>
                  {uiRows.map((r: any) => (
                    <tr key={r.requirement_id} className="border-b border-border-subtle hover:bg-surface-hover">
                      <td className="py-2 pr-2">
                        <button className="text-left text-text-primary font-medium hover:text-primary"
                          onClick={() => navigate(`/qa/requirements/${r.requirement_id}`)}>
                          <span className="font-mono text-primary mr-1">{r.req_code}</span>{r.title}
                        </button>
                      </td>
                      <td className="py-2 pr-2">{r.design_total}</td>
                      <td className="py-2 pr-2">{r.web_automated}</td>
                      <td className="py-2 pr-2">{r.manual_pass}</td>
                      <td className="py-2 pr-2">{r.api_pass}</td>
                      <td className="py-2 pr-2">{r.web_pass}</td>
                      <td className="py-2">{r.last_ui_result ? <ExecBadge value={r.last_ui_result} /> : '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}
      {activeProject && changeCov.length > 0 && (
        <Card>
          <CardContent>
            <div className="text-sm font-semibold text-text-primary mb-2">Change Coverage — regression plans gần nhất</div>
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="text-left text-text-muted border-b border-border-subtle">
                    <th className="py-2 pr-2">Plan</th>
                    <th className="py-2 pr-2">Recommended</th>
                    <th className="py-2 pr-2">Executed</th>
                    <th className="py-2 pr-2">P/F/B</th>
                    <th className="py-2 pr-2">Not run</th>
                    <th className="py-2">Critical failures</th>
                  </tr>
                </thead>
                <tbody>
                  {changeCov.map((r: any) => (
                    <tr key={r.plan_id} className="border-b border-border-subtle hover:bg-surface-hover">
                      <td className="py-2 pr-2">
                        <button className="text-left text-text-primary font-medium hover:text-primary"
                          onClick={() => navigate(`/qa/regression?plan=${r.plan_id}`)}>
                          <span className="font-mono text-primary mr-1">{r.plan_code}</span>
                        </button>
                      </td>
                      <td className="py-2 pr-2">{r.recommended}</td>
                      <td className="py-2 pr-2">{r.executed}</td>
                      <td className="py-2 pr-2">{r.passed}/{r.failed}/{r.blocked}</td>
                      <td className="py-2 pr-2">{r.not_run}</td>
                      <td className="py-2">{(r.critical_failures || []).length}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}
      {activeProject && dataRows.length > 0 && (
        <Card>
          <CardContent>
            <div className="text-sm font-semibold text-text-primary mb-2">Data Coverage — tables/entities checked</div>
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="text-left text-text-muted border-b border-border-subtle">
                    <th className="py-2 pr-2">Job</th>
                    <th className="py-2 pr-2">Records</th>
                    <th className="py-2 pr-2">Rules</th>
                    <th className="py-2 pr-2">Differences</th>
                    <th className="py-2">Open issues</th>
                  </tr>
                </thead>
                <tbody>
                  {dataRows.map((r: any) => (
                    <tr key={r.job_id} className="border-b border-border-subtle hover:bg-surface-hover">
                      <td className="py-2 pr-2">
                        <button className="text-left text-text-primary font-medium hover:text-primary"
                          onClick={() => navigate(`/qa/data/${r.job_id}`)}>
                          <span className="font-mono text-primary mr-1">{r.job_code}</span>{r.name}
                        </button>
                      </td>
                      <td className="py-2 pr-2">{r.records_checked}</td>
                      <td className="py-2 pr-2">{r.rules_checked}</td>
                      <td className="py-2 pr-2">{Object.entries(r.differences || {}).map(([k, v]) => `${k}:${v}`).join(' · ') || '—'}</td>
                      <td className="py-2">{r.open_issues}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
};
