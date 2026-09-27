import React, { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { GitBranch, PlayCircle, History } from 'lucide-react';
import { apiClient } from '../../api/client';
import { Project } from '../../types';
import { ChangeRecord } from '../../types/qa';
import { useToast } from '../../context/ToastContext';
import { PageHeader } from '../../components/ui/PageHeader';
import { Card, CardContent } from '../../components/ui/Card';
import { Badge } from '../../components/ui/Badge';
import { Button } from '../../components/ui/Button';
import { statusVariant } from './qaHelpers';

interface Props {
  activeProject: Project | null;
}

export const ChangeDetailPage: React.FC<Props> = ({ activeProject }) => {
  void activeProject;
  const { id } = useParams<{ id: string }>();
  const [change, setChange] = useState<ChangeRecord | null>(null);
  const [analysis, setAnalysis] = useState<any>(null);
  const [versions, setVersions] = useState<any[]>([]);
  const [busy, setBusy] = useState(false);
  const toast = useToast();
  const navigate = useNavigate();

  const load = async () => {
    if (!id) return;
    try {
      const d = await apiClient.qaGetChange(id);
      setChange(d);
      if (d.requirement_id) {
        apiClient.qaRequirementVersions(d.requirement_id).then(setVersions).catch(() => undefined);
      }
    } catch {
      toast.error('Không tải được change');
    }
  };

  useEffect(() => { load(); /* eslint-disable-next-line */ }, [id]);

  const analyze = async () => {
    if (!id) return;
    setBusy(true);
    try {
      const out = await apiClient.qaAnalyzeChange(id, {});
      setAnalysis(out);
      const d = await apiClient.qaGetChange(id);
      setChange(d);
      toast.success('Đã phân tích impact + risk');
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || 'Phân tích thất bại');
    } finally {
      setBusy(false);
    }
  };

  if (!change) return <div className="flex-1 p-6 text-sm text-text-muted">Đang tải change...</div>;
  const impact = analysis?.impact;
  const aspects = analysis?.before_after?.aspects || [];
  const diff = analysis?.before_after?.diff;

  return (
    <div className="flex-1 overflow-y-auto p-4 sm:p-6 space-y-4">
      <PageHeader
        title={<span><span className="font-mono text-primary mr-2">{change.change_code}</span>{change.source}</span>}
        description={change.business_summary || change.change_summary}
        icon={<GitBranch className="w-5 h-5" />}
        breadcrumbs={[{ label: 'Changes', onClick: () => navigate('/qa/changes') }, { label: change.change_code }]}
        badge={<div className="flex gap-1.5 flex-wrap">
          <Badge variant={change.risk_level === 'CRITICAL' || change.risk_level === 'HIGH' ? 'danger' : 'warning'}>{change.risk_level}</Badge>
          <Badge variant={statusVariant(change.status)}>{change.status}</Badge>
        </div>}
        actions={<Button size="sm" disabled={busy} onClick={analyze}>{busy ? 'Đang phân tích...' : 'Analyze Impact'}</Button>}
      />

      <Card>
        <CardContent className="space-y-1.5 text-xs">
          <div className="font-semibold text-sm text-text-primary">Change Summary</div>
          <div className="text-text-primary">{change.change_summary}</div>
          <div className="text-text-muted">Categories: {(change.categories || []).join(' · ') || '—'}</div>
          {(change.risk_reasons || []).length > 0 && (
            <div className="text-text-muted">Risk vì: {change.risk_reasons.join(' · ')}</div>
          )}
          {change.requirement_id && (
            <button className="text-primary hover:underline" onClick={() => navigate(`/qa/requirements/${change.requirement_id}`)}>
              Mở requirement liên quan →
            </button>
          )}
        </CardContent>
      </Card>

      {(diff || aspects.length > 0) && (
        <Card>
          <CardContent className="space-y-2 text-xs">
            <div className="font-semibold text-sm text-text-primary">Before / After — business-friendly</div>
            {aspects.map((a: any, i: number) => (
              <div key={i} className="flex gap-2">
                <Badge variant={a.changed ? 'warning' : 'neutral'}>{a.aspect}</Badge>
                <span className="text-text-secondary">{a.evidence}</span>
              </div>
            ))}
            {diff && ((diff.added || []).length > 0 || (diff.removed || []).length > 0 || (diff.modified || []).length > 0) && (
              <div className="space-y-1 pt-1">
                {(diff.added || []).map((x: any, i: number) => (
                  <div key={`a${i}`} className="text-emerald-600">+ {x.item || x.description}</div>
                ))}
                {(diff.removed || []).map((x: any, i: number) => (
                  <div key={`r${i}`} className="text-rose-500">− {x.item || x.description}</div>
                ))}
                {(diff.modified || []).map((x: any, i: number) => (
                  <div key={`m${i}`} className="text-amber-600">~ {x.item}: {x.before} → {x.after} [{x.significance}]</div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {impact && (
        <>
          <Card>
            <CardContent className="space-y-1.5 text-xs">
              <div className="font-semibold text-sm text-text-primary">
                Impact — {impact.cases?.length || 0} testcases, {impact.bugs?.length || 0} historical bugs
              </div>
              {(impact.cases || []).slice(0, 15).map((c: any) => (
                <div key={c.id} className="flex items-center gap-2 flex-wrap">
                  <Badge variant={c.level === 'Direct' ? 'danger' : c.level === 'Indirect' ? 'warning' : 'neutral'}>{c.level}</Badge>
                  <span className="font-mono text-primary">{c.code}</span>
                  <span className="flex-1">{c.title}</span>
                  <span className="text-text-muted">[{c.confidence}]</span>
                </div>
              ))}
              {(impact.cases || []).length > 15 && (
                <div className="text-text-muted">...và {(impact.cases || []).length - 15} cases nữa (xem trong Regression Planner)</div>
              )}
              {(impact.apis || []).map((a: any) => (
                <div key={a.id} className="text-text-secondary">API ảnh hưởng: <span className="font-mono">{a.code}</span> {a.title}</div>
              ))}
              {(impact.possible || []).map((p: any) => (
                <div key={p.id} className="text-text-muted">Possible (Needs Review): {p.code} {p.title}</div>
              ))}
            </CardContent>
          </Card>
          {(impact.bugs || []).length > 0 && (
            <Card>
              <CardContent>
                <div className="font-semibold text-sm text-text-primary mb-1">Historical Bug Regression</div>
                {(impact.bugs || []).map((b: any) => (
                  <div key={b.id} className="text-xs py-0.5">
                    <span className="font-mono text-primary">{b.code}</span> {b.title}
                  </div>
                ))}
              </CardContent>
            </Card>
          )}
        </>
      )}

      {analysis?.outdated_flags && (
        <Card>
          <CardContent>
            <div className="text-xs text-text-secondary">
              Flag outdated: {analysis.outdated_flags.confirmed_cases} confirmed cases ·
              API {analysis.outdated_flags.api_flagged} · UI {analysis.outdated_flags.ui_flagged}
            </div>
          </CardContent>
        </Card>
      )}

      {versions.length > 0 && (
        <Card>
          <CardContent>
            <div className="flex items-center gap-2 text-sm font-semibold text-text-primary mb-2">
              <History className="w-4 h-4" /> Requirement versions ({versions.length})
            </div>
            {versions.map((v: any) => (
              <div key={v.id} className="text-xs py-1 border-b border-border-subtle">
                <Badge variant="neutral">v{v.version_no}</Badge>{' '}
                <span className="font-medium">{v.title}</span>
                <span className="text-text-muted"> · {v.source} · {v.created_at}</span>
              </div>
            ))}
          </CardContent>
        </Card>
      )}

      <div className="flex gap-2">
        <Button size="sm" leftIcon={<PlayCircle className="w-3.5 h-3.5" />}
          onClick={() => navigate(`/qa/regression?change=${change.id}`)}>
          Mở Regression Planner
        </Button>
      </div>
    </div>
  );
};

export default ChangeDetailPage;
