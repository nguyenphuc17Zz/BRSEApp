import React, { useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { ClipboardList, PlayCircle, Plus, Trash2, Check } from 'lucide-react';
import { apiClient } from '../../api/client';
import { Project } from '../../types';
import { RegressionPlan, RegressionPlanItem } from '../../types/qa';
import { useToast } from '../../context/ToastContext';
import { useConfirm } from '../../context/ConfirmDialogContext';
import { PageHeader } from '../../components/ui/PageHeader';
import { Card, CardContent } from '../../components/ui/Card';
import { Badge } from '../../components/ui/Badge';
import { Button } from '../../components/ui/Button';
import { Input } from '../../components/ui/Input';
import { Select } from '../../components/ui/Select';
import { EmptyState } from '../../components/ui/EmptyState';
import { statusVariant } from './qaHelpers';

interface Props {
  activeProject: Project | null;
}

const TIER_STYLE: Record<string, 'danger' | 'warning' | 'info' | 'neutral'> = {
  MUST_RUN: 'danger', RECOMMENDED: 'warning', OPTIONAL: 'info', EXCLUDED: 'neutral',
};

export const RegressionPlannerPage: React.FC<Props> = ({ activeProject }) => {
  const [plans, setPlans] = useState<RegressionPlan[]>([]);
  const [plan, setPlan] = useState<any>(null);
  const [summary, setSummary] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [changeIds, setChangeIds] = useState('');
  const [releaseTag, setReleaseTag] = useState('');
  const [budget, setBudget] = useState('');
  const [addTc, setAddTc] = useState('');
  const [addTier, setAddTier] = useState('RECOMMENDED');
  const [runForm, setRunForm] = useState({ version_build: '', environment: 'STG' });
  const [searchParams] = useSearchParams();
  const toast = useToast();
  const confirm = useConfirm();
  const navigate = useNavigate();

  const loadPlans = async () => {
    if (!activeProject) { setLoading(false); return; }
    setLoading(true);
    try {
      setPlans(await apiClient.qaListPlans(activeProject.id));
    } catch {
      toast.error('Không tải được plans');
    } finally {
      setLoading(false);
    }
  };

  const loadPlan = async (pid: string) => {
    try {
      const [detail, sum] = await Promise.all([
        apiClient.qaGetPlan(pid),
        apiClient.qaPlanSummary(pid).catch(() => null),
      ]);
      setPlan(detail);
      setSummary(sum);
    } catch {
      toast.error('Không tải được plan');
    }
  };

  useEffect(() => {
    loadPlans();
    const ch = searchParams.get('change');
    if (ch) setChangeIds(ch);
    const pl = searchParams.get('plan');
    if (pl) loadPlan(pl);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeProject?.id]);

  const createPlan = async () => {
    if (!activeProject) return;
    const ids = changeIds.split(',').map((s) => s.trim()).filter(Boolean);
    if (!ids.length) { toast.error('Nhập ít nhất 1 change ID'); return; }
    setBusy(true);
    try {
      const p = await apiClient.qaCreatePlan(activeProject.id, {
        change_ids: ids,
        release_tag: releaseTag || undefined,
        time_budget_min: budget ? Number(budget) : undefined,
      });
      toast.success(`Đã tạo ${p.plan_code} (DRAFT)`);
      setChangeIds('');
      await loadPlans();
      await loadPlan(p.id);
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || 'Tạo plan thất bại');
    } finally {
      setBusy(false);
    }
  };

  const setStatus = async (status: string) => {
    if (!plan) return;
    if (status === 'APPROVED') {
      const ok = await confirm({ title: 'Approve regression plan?', message: 'Duyệt scope regression này?', confirmText: 'Approve' });
      if (!ok) return;
    }
    try {
      const p = await apiClient.qaUpdatePlan(plan.id, { status });
      toast.success(`Plan → ${status}`);
      await loadPlans();
      await loadPlan(p.id);
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || 'Đổi status thất bại');
    }
  };

  const addItem = async () => {
    if (!plan || !addTc.trim()) return;
    try {
      await apiClient.qaAddPlanItem(plan.id, { test_case_id: addTc.trim(), tier: addTier, reason: 'Added by user' });
      toast.success('Đã thêm testcase');
      setAddTc('');
      await loadPlan(plan.id);
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || 'Thêm thất bại');
    }
  };

  const removeItem = async (itemId: string) => {
    if (!plan) return;
    if (!(await confirm({ title: 'Xóa khỏi plan?', message: 'Xóa testcase này khỏi scope?', confirmText: 'Xóa', isDestructive: true }))) return;
    try {
      await apiClient.qaRemovePlanItem(itemId);
      toast.success('Đã xóa');
      await loadPlan(plan.id);
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || 'Xóa thất bại');
    }
  };

  const runRegression = async () => {
    if (!plan) return;
    setBusy(true);
    try {
      const out = await apiClient.qaRunPlan(plan.id, { ...runForm });
      toast.success(`Đã tạo Test Run REGRESSION (${out.added} cases)`);
      await loadPlan(plan.id);
      navigate(`/qa/test-runs/${out.test_run_id}`);
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || 'Tạo run thất bại');
    } finally {
      setBusy(false);
    }
  };

  const tiers: Record<string, RegressionPlanItem[]> = { MUST_RUN: [], RECOMMENDED: [], OPTIONAL: [], EXCLUDED: [] };
  (plan?.items || []).forEach((it: RegressionPlanItem) => {
    (tiers[it.tier] || tiers.OPTIONAL).push(it);
  });

  return (
    <div className="flex-1 overflow-y-auto p-4 sm:p-6 space-y-4">
      <PageHeader
        title="Regression Planner"
        description="AI đề xuất Must / Recommended / Optional kèm lý do — bạn review, chỉnh, approve rồi chạy."
        icon={<ClipboardList className="w-5 h-5" />}
      />
      {!activeProject && (
        <Card><CardContent><p className="text-sm text-text-secondary">Chọn một project để bắt đầu.</p></CardContent></Card>
      )}
      {activeProject && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <div className="space-y-4">
            <Card>
              <CardContent className="space-y-2">
                <div className="text-sm font-semibold">Tạo plan từ changes</div>
                <Input value={changeIds} onChange={(e) => setChangeIds(e.target.value)}
                  placeholder="Change IDs, cách nhau dấu phẩy" />
                <div className="grid grid-cols-2 gap-2">
                  <Input value={releaseTag} onChange={(e) => setReleaseTag(e.target.value)} placeholder="Release 2.5 (optional)" />
                  <Input value={budget} onChange={(e) => setBudget(e.target.value)} placeholder="Budget phút, VD 120" />
                </div>
                <Button size="sm" disabled={busy} onClick={createPlan}>Tạo Regression Plan</Button>
                <p className="text-[11px] text-text-muted">Budget trống = full scope. Có budget → cắt theo risk, hiện excluded + residual risk.</p>
              </CardContent>
            </Card>
            <Card>
              <CardContent>
                <div className="text-sm font-semibold mb-2">Plans ({plans.length})</div>
                {loading && <p className="text-xs text-text-muted">Đang tải...</p>}
                {plans.map((p) => (
                  <button key={p.id} onClick={() => loadPlan(p.id)}
                    className={`w-full text-left py-2 px-1 rounded-lg hover:bg-surface-hover ${plan?.id === p.id ? 'bg-primary/10' : ''}`}>
                    <div className="flex items-center gap-1.5">
                      <span className="font-mono text-xs text-primary font-semibold">{p.plan_code}</span>
                      <Badge variant={statusVariant(p.status)}>{p.status}</Badge>
                      {p.release_tag && <span className="text-[11px] text-text-muted">{p.release_tag}</span>}
                    </div>
                    <div className="text-[11px] text-text-muted">{p.change_codes.join(', ')} · {p.item_count} cases ({p.must_count} must)</div>
                  </button>
                ))}
                {plans.length === 0 && !loading && <EmptyState title="Chưa có plan" description="Tạo plan từ change IDs." />}
              </CardContent>
            </Card>
          </div>

          <div className="lg:col-span-2 space-y-4">
            {!plan && <Card><CardContent><p className="text-sm text-text-muted">Chọn một plan để review.</p></CardContent></Card>}
            {plan && (
              <>
                <Card>
                  <CardContent className="space-y-2">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-mono font-semibold text-primary">{plan.plan_code}</span>
                      <Badge variant={statusVariant(plan.status)}>{plan.status}</Badge>
                      {plan.time_budget_min && <Badge variant="info">{plan.time_budget_min} min budget</Badge>}
                      {plan.test_run_id && (
                        <button className="text-xs text-primary hover:underline" onClick={() => navigate(`/qa/test-runs/${plan.test_run_id}`)}>
                          Mở Test Run →
                        </button>
                      )}
                    </div>
                    <div className="text-xs text-text-muted">Changes: {(plan.change_codes || []).join(', ')}</div>
                    <div className="flex gap-1.5 flex-wrap">
                      {plan.status === 'DRAFT' && <Button size="sm" variant="subtle" onClick={() => setStatus('REVIEWED')}>Mark Reviewed</Button>}
                      {(plan.status === 'DRAFT' || plan.status === 'REVIEWED') && (
                        <Button size="sm" leftIcon={<Check className="w-3.5 h-3.5" />} onClick={() => setStatus('APPROVED')}>Approve Plan</Button>
                      )}
                    </div>
                    <div className="flex gap-2 flex-wrap items-end pt-1 border-t border-border-subtle">
                      <div className="w-32"><Input value={runForm.version_build} onChange={(e) => setRunForm({ ...runForm, version_build: e.target.value })} placeholder="Build" /></div>
                      <div className="w-32"><Input value={runForm.environment} onChange={(e) => setRunForm({ ...runForm, environment: e.target.value })} placeholder="STG" /></div>
                      <Button size="sm" disabled={busy} leftIcon={<PlayCircle className="w-3.5 h-3.5" />} onClick={runRegression}>
                        Approve + Create REGRESSION Run
                      </Button>
                    </div>
                  </CardContent>
                </Card>

                {(Object.keys(tiers) as Array<keyof typeof tiers>).map((tier) => (
                  tiers[tier].length > 0 && (
                    <Card key={tier}>
                      <CardContent>
                        <div className="text-sm font-semibold mb-1">
                          {tier === 'MUST_RUN' ? 'Must Run — impacted trực tiếp / critical' : tier === 'RECOMMENDED' ? 'Recommended — indirect risk' : tier === 'OPTIONAL' ? 'Optional — lower risk' : 'Excluded — ngoài budget'}
                          <span className="ml-2 text-xs font-normal text-text-muted">({tiers[tier].length})</span>
                        </div>
                        {tiers[tier].map((it) => (
                          <div key={it.id} className="py-1.5 border-b border-border-subtle last:border-0">
                            <div className="flex items-center gap-1.5 flex-wrap">
                              <span className="font-mono text-xs text-primary">{it.tc_code}</span>
                              <Badge variant={TIER_STYLE[it.tier] || 'neutral'}>{it.tier}</Badge>
                              <Badge variant={it.risk === 'CRITICAL' || it.risk === 'HIGH' ? 'danger' : 'neutral'}>{it.risk}</Badge>
                              <span className="text-[11px] text-text-muted">confidence: {it.impact_confidence} · #{it.priority_rank} · {it.added_by}</span>
                              <span className="flex-1" />
                              {plan.status !== 'APPROVED' && (
                                <button className="text-text-muted hover:text-rose-500" onClick={() => removeItem(it.id)}>
                                  <Trash2 className="w-3.5 h-3.5" />
                                </button>
                              )}
                            </div>
                            <div className="text-xs font-medium mt-0.5">{it.title}</div>
                            <div className="text-[11px] text-text-secondary">Why: {it.reason}</div>
                          </div>
                        ))}
                      </CardContent>
                    </Card>
                  )
                ))}

                {plan.status !== 'APPROVED' && (
                  <Card>
                    <CardContent>
                      <div className="text-sm font-semibold mb-2">Thêm testcase thủ công</div>
                      <div className="flex gap-2">
                        <div className="flex-1"><Input value={addTc} onChange={(e) => setAddTc(e.target.value)} placeholder="Test case UUID" /></div>
                        <div className="w-40">
                          <Select value={addTier} onChange={(v) => setAddTier(v as string)}
                            options={['MUST_RUN', 'RECOMMENDED', 'OPTIONAL'].map((t) => ({ value: t, label: t }))} />
                        </div>
                        <Button size="sm" variant="subtle" leftIcon={<Plus className="w-3 h-3" />} onClick={addItem}>Thêm</Button>
                      </div>
                    </CardContent>
                  </Card>
                )}

                {summary && (
                  <Card>
                    <CardContent className="text-xs space-y-1">
                      <div className="text-sm font-semibold">Execution Summary (evidence, không kết luận release)</div>
                      <div>Recommended: {summary.recommended} · Executed: {summary.executed} · PASS {summary.passed} · FAIL {summary.failed} · BLOCKED {summary.blocked} · NOT RUN {summary.not_run}</div>
                      {(summary.critical_failures || []).map((f: any, i: number) => (
                        <div key={i} className="text-rose-500">Critical failure: {f.tc_code} {f.title}</div>
                      ))}
                      {(summary.excluded || []).map((e: any, i: number) => (
                        <div key={`e${i}`} className="text-text-muted">Excluded: {e.reason}</div>
                      ))}
                    </CardContent>
                  </Card>
                )}
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

export default RegressionPlannerPage;
