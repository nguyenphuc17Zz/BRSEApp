import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Bug as BugIcon } from 'lucide-react';
import { apiClient } from '../../api/client';
import { Project } from '../../types';
import { useToast } from '../../context/ToastContext';
import { PageHeader } from '../../components/ui/PageHeader';
import { Card, CardContent } from '../../components/ui/Card';
import { Badge } from '../../components/ui/Badge';
import { Button } from '../../components/ui/Button';
import { Input } from '../../components/ui/Input';
import { Select } from '../../components/ui/Select';
import { EmptyState } from '../../components/ui/EmptyState';
import { BugUxBadge } from './execComponents';
import { severityVariant } from './qaHelpers';

interface Props {
  activeProject: Project | null;
}

const UX_OPTIONS = ['', 'OPEN', 'CONFIRMED', 'IN_PROGRESS', 'FIXED', 'RETEST', 'CLOSED', 'REJECTED'];

export const BugListPage: React.FC<Props> = ({ activeProject }) => {
  const [bugs, setBugs] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [status, setStatus] = useState('');
  const [priority, setPriority] = useState('');
  const toast = useToast();
  const navigate = useNavigate();

  const load = async () => {
    setLoading(true);
    try {
      const data = await apiClient.qaListBugs({
        project_id: activeProject?.id || undefined,
        status: status || undefined,
        priority: priority || undefined,
        search: search || undefined,
      });
      setBugs(data);
    } catch {
      toast.error('Không tải được bugs');
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
        title="Bugs"
        description="Bug từ test execution — trace tới requirement, testcase, test run."
        icon={<BugIcon className="w-5 h-5" />}
      />
      <Card>
        <CardContent className="space-y-3">
          <div className="flex flex-col sm:flex-row gap-2">
            <div className="flex-1">
              <Input placeholder="Tìm bug (mã, tiêu đề...)" value={search}
                onChange={(e) => setSearch(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter') load(); }} />
            </div>
            <div className="w-full sm:w-44">
              <Select value={status} onChange={(v) => setStatus(v as string)}
                options={UX_OPTIONS.map((s) => ({ value: s, label: s === '' ? 'Mọi status' : s }))} />
            </div>
            <div className="w-full sm:w-40">
              <Select value={priority} onChange={(v) => setPriority(v as string)}
                options={[{ value: '', label: 'Mọi severity' }, { value: 'CRITICAL', label: 'CRITICAL' }, { value: 'HIGH', label: 'HIGH' }, { value: 'MEDIUM', label: 'MEDIUM' }, { value: 'LOW', label: 'LOW' }]} />
            </div>
            <Button size="sm" onClick={load}>Lọc</Button>
          </div>
          {loading && <p className="text-xs text-text-muted">Đang tải...</p>}
          {!loading && bugs.length === 0 && <EmptyState title="Chưa có bug" description="Bug được tạo từ FAIL execution." />}
          <div className="divide-y divide-border-subtle">
            {bugs.map((b) => (
              <button key={b.id} onClick={() => navigate(`/qa/bugs/${b.id}`)}
                className="w-full text-left py-2.5 px-3.5 hover:bg-surface-hover rounded-lg transition-colors">
                <div className="flex items-center gap-1.5 flex-wrap">
                  <span className="font-mono text-xs text-primary font-semibold">{b.bug_code}</span>
                  <BugUxBadge ux={b.ux_status} />
                  <Badge variant={severityVariant(b.priority)}>{b.priority}</Badge>
                  {b.assignee && <span className="text-[11px] text-text-muted">{b.assignee}</span>}
                </div>
                <div className="text-sm text-text-primary mt-0.5">{b.title}</div>
              </button>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );
};
