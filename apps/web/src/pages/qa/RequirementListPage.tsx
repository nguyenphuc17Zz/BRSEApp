import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { FileSearch } from 'lucide-react';
import { apiClient } from '../../api/client';
import { Project } from '../../types';
import { QARequirement } from '../../types/qa';
import { useToast } from '../../context/ToastContext';
import { PageHeader } from '../../components/ui/PageHeader';
import { Card, CardContent } from '../../components/ui/Card';
import { Badge } from '../../components/ui/Badge';
import { Button } from '../../components/ui/Button';
import { Input } from '../../components/ui/Input';
import { Select } from '../../components/ui/Select';
import { EmptyState } from '../../components/ui/EmptyState';
import { CoverageBadge, statusVariant } from './qaHelpers';

interface Props {
  activeProject: Project | null;
}

export const RequirementListPage: React.FC<Props> = ({ activeProject }) => {
  const [items, setItems] = useState<QARequirement[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [coverageFilter, setCoverageFilter] = useState('');
  const toast = useToast();
  const navigate = useNavigate();

  const load = async () => {
    if (!activeProject) {
      setLoading(false);
      return;
    }
    setLoading(true);
    try {
      const data = await apiClient.qaListRequirements(activeProject.id);
      setItems(data);
    } catch {
      toast.error('Không tải được danh sách requirement');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeProject?.id]);

  const filtered = items.filter((it) => {
    if (coverageFilter && it.coverage !== coverageFilter) return false;
    if (search) {
      const s = search.toLowerCase();
      return (
        it.title.toLowerCase().includes(s) ||
        (it.req_code || '').toLowerCase().includes(s) ||
        (it.description || '').toLowerCase().includes(s)
      );
    }
    return true;
  });

  return (
    <div className="flex-1 overflow-y-auto p-4 sm:p-6 space-y-4">
      <PageHeader
        title="Requirement Review"
        description="Chọn một requirement để Review → xem Findings → tạo câu hỏi confirm → sinh AC và testcase."
        icon={<FileSearch className="w-5 h-5" />}
        actions={<Button variant="subtle" size="sm" onClick={load}>Refresh</Button>}
      />
      {!activeProject && (
        <Card><CardContent><p className="text-sm text-text-secondary">Chọn một project để bắt đầu.</p></CardContent></Card>
      )}
      {activeProject && (
        <Card>
          <CardContent className="space-y-3">
            <div className="flex flex-col sm:flex-row gap-2">
              <div className="flex-1">
                <Input placeholder="Tìm requirement (mã, tiêu đề...)" value={search} onChange={(e) => setSearch(e.target.value)} />
              </div>
              <div className="w-full sm:w-56">
                <Select
                  value={coverageFilter}
                  onChange={(v) => setCoverageFilter(v as string)}
                  options={[
                    { value: '', label: 'Mọi coverage' },
                    { value: 'NotReviewed', label: 'Not Reviewed' },
                    { value: 'NotCovered', label: 'Not Covered' },
                    { value: 'PartiallyCovered', label: 'Partially Covered' },
                    { value: 'BlockedByClarification', label: 'Blocked by Clarification' },
                    { value: 'Covered', label: 'Covered' },
                  ]}
                />
              </div>
            </div>
            {loading && <p className="text-xs text-text-muted">Đang tải...</p>}
            {!loading && filtered.length === 0 && (
              <EmptyState
                title="Chưa có requirement"
                description="Requirement từ WorkItem, Meeting hoặc nhập trực tiếp sẽ hiện ở đây."
              />
            )}
            <div className="divide-y divide-border-subtle">
              {filtered.map((it) => (
                <button
                  key={it.id}
                  onClick={() => navigate(`/qa/requirements/${it.id}`)}
                  className="w-full text-left py-3 px-3.5 hover:bg-surface-hover rounded-lg transition-colors"
                >
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-mono text-xs text-primary font-semibold">{it.req_code || it.id.slice(0, 6)}</span>
                    <CoverageBadge value={it.coverage} />
                    <Badge variant={statusVariant(it.status)}>{it.status}</Badge>
                    {it.findings_open > 0 && <Badge variant="danger">{it.findings_open} findings</Badge>}
                    {it.questions_unanswered > 0 && <Badge variant="warning">{it.questions_unanswered} questions</Badge>}
                  </div>
                  <div className="text-sm font-medium text-text-primary mt-1">{it.title}</div>
                  <div className="text-xs text-text-muted mt-0.5">
                    AC: {it.ac_total} · Testcases: {it.tc_total} · Evidence: {it.evidence_count}
                  </div>
                </button>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
};
