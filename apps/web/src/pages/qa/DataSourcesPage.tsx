import React, { useEffect, useState } from 'react';
import { FileUp, Trash2 } from 'lucide-react';
import { apiClient } from '../../api/client';
import { Project } from '../../types';
import { DataSource } from '../../types/qa';
import { useToast } from '../../context/ToastContext';
import { useConfirm } from '../../context/ConfirmDialogContext';
import { PageHeader } from '../../components/ui/PageHeader';
import { Card, CardContent } from '../../components/ui/Card';
import { Badge } from '../../components/ui/Badge';
import { Button } from '../../components/ui/Button';
import { EmptyState } from '../../components/ui/EmptyState';

interface Props {
  activeProject: Project | null;
}

export const DataSourcesPage: React.FC<Props> = ({ activeProject }) => {
  const [sources, setSources] = useState<DataSource[]>([]);
  const [preview, setPreview] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const toast = useToast();
  const confirm = useConfirm();

  const load = async () => {
    if (!activeProject) { setLoading(false); return; }
    setLoading(true);
    try {
      setSources(await apiClient.qaListDataSources(activeProject.id));
    } catch {
      toast.error('Không tải được sources');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); /* eslint-disable-next-line */ }, [activeProject?.id]);

  const openPreview = async (id: string) => {
    try {
      setPreview(await apiClient.qaGetDataSource(id));
    } catch {
      toast.error('Không xem được preview');
    }
  };

  return (
    <div className="flex-1 overflow-y-auto p-4 sm:p-6 space-y-4">
      <PageHeader
        title="Data Sources"
        description="File CSV/Excel/JSON chỉ đọc — upload ở trang Data QA Jobs."
        icon={<FileUp className="w-5 h-5" />}
        actions={<Button size="sm" variant="subtle" onClick={load}>Refresh</Button>}
      />
      {!activeProject && (
        <Card><CardContent><p className="text-sm text-text-secondary">Chọn một project để bắt đầu.</p></CardContent></Card>
      )}
      {activeProject && (
        <Card>
          <CardContent className="space-y-2">
            {loading && <p className="text-xs text-text-muted">Đang tải...</p>}
            {!loading && sources.length === 0 && (
              <EmptyState title="Chưa có source" description="Upload file ở Data QA Jobs." />
            )}
            {sources.map((s) => (
              <div key={s.id} className="flex items-center gap-2 text-xs border border-border-subtle rounded-lg px-2.5 py-2">
                <Badge variant="info">{s.kind}</Badge>
                <span className="font-medium flex-1 truncate">{s.name}</span>
                <span className="text-text-muted">{(s.schema_fields || []).length} cột</span>
                <Button size="sm" variant="ghost" onClick={() => openPreview(s.id)}>Preview</Button>
                <Button size="sm" variant="ghost" onClick={async () => {
                  if (await confirm({ title: 'Xóa source?', message: s.name, confirmText: 'Xóa', isDestructive: true })) {
                    await apiClient.qaDeleteDataSource(s.id);
                    toast.success('Đã xóa');
                    load();
                  }
                }}><Trash2 className="w-3 h-3" /></Button>
              </div>
            ))}
            {preview && (
              <div className="border border-border-subtle rounded-lg p-2.5 mt-2">
                <div className="text-xs font-semibold mb-1">{preview.name} — {(preview.schema_fields || []).join(', ')}</div>
                {(preview.preview_error) && <p className="text-xs text-rose-500">{preview.preview_error}</p>}
                <div className="overflow-x-auto max-h-64 overflow-y-auto">
                  <table className="w-full text-[11px]">
                    <thead>
                      <tr className="text-left text-text-muted border-b border-border-subtle">
                        {(preview.preview_fields || []).map((f: string) => <th key={f} className="py-1 pr-2 font-mono">{f}</th>)}
                      </tr>
                    </thead>
                    <tbody>
                      {(preview.preview_rows || []).map((r: any, i: number) => (
                        <tr key={i} className="border-b border-border-subtle">
                          {(preview.preview_fields || []).map((f: string) => (
                            <td key={f} className="py-1 pr-2 font-mono break-all max-w-[220px]">{String(r[f] ?? '')}</td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
};

export default DataSourcesPage;
