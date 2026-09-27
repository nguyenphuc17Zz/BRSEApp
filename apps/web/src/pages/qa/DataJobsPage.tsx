import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Database, Plus, Upload } from 'lucide-react';
import { apiClient } from '../../api/client';
import { Project } from '../../types';
import { DataJob } from '../../types/qa';
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
import { statusVariant } from './qaHelpers';

interface Props {
  activeProject: Project | null;
}

export const DataJobsPage: React.FC<Props> = ({ activeProject }) => {
  const [jobs, setJobs] = useState<DataJob[]>([]);
  const [sources, setSources] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [showCreate, setShowCreate] = useState(false);
  const [showUpload, setShowUpload] = useState(false);
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploadName, setUploadName] = useState('');
  const [form, setForm] = useState({
    name: '', purpose: '', source_id: '', dest_id: '',
    requirement_id: '', build: '', environment: 'STG', key_fields: 'order_no',
  });
  const toast = useToast();
  const confirm = useConfirm();
  const navigate = useNavigate();

  const load = async () => {
    if (!activeProject) { setLoading(false); return; }
    setLoading(true);
    try {
      const [list, srcs] = await Promise.all([
        apiClient.qaListDataJobs(activeProject.id, {
          status: statusFilter || undefined,
          search: search || undefined,
        }),
        apiClient.qaListDataSources(activeProject.id),
      ]);
      setJobs(list);
      setSources(srcs);
    } catch {
      toast.error('Không tải được data jobs');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); /* eslint-disable-next-line */ }, [activeProject?.id]);

  const create = async () => {
    if (!activeProject || !form.name.trim()) { toast.error('Nhập tên job'); return; }
    try {
      const job = await apiClient.qaCreateDataJob(activeProject.id, {
        ...form,
        source_id: form.source_id || undefined,
        dest_id: form.dest_id || undefined,
        requirement_id: form.requirement_id || undefined,
        key_fields: form.key_fields.split(',').map((s) => s.trim()).filter(Boolean),
      });
      toast.success(`Đã tạo ${job.job_code}`);
      setShowCreate(false);
      setForm({ name: '', purpose: '', source_id: '', dest_id: '', requirement_id: '', build: '', environment: 'STG', key_fields: 'order_no' });
      navigate(`/qa/data/${job.id}`);
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || 'Tạo thất bại');
    }
  };

  const upload = async () => {
    if (!activeProject || !uploadFile) { toast.error('Chọn file CSV/Excel/JSON'); return; }
    const ext = uploadFile.name.split('.').pop()?.toLowerCase();
    const kind = ext === 'xlsx' || ext === 'xls' ? 'file_excel' : ext === 'json' ? 'file_json' : 'file_csv';
    try {
      const src = await apiClient.qaUploadDataSource(activeProject.id, uploadFile, {
        name: uploadName || uploadFile.name, kind,
      });
      toast.success(`Đã upload: ${src.schema_fields?.length || 0} cột`);
      setShowUpload(false);
      setUploadFile(null);
      setUploadName('');
      load();
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || 'Upload thất bại');
    }
  };

  return (
    <div className="flex-1 overflow-y-auto p-4 sm:p-6 space-y-4">
      <PageHeader
        title="Data QA Jobs"
        description="So sánh 2 nguồn dữ liệu: count → key → field → rule. Không sửa dữ liệu nguồn."
        icon={<Database className="w-5 h-5" />}
        actions={
          <div className="flex gap-1.5">
            <Button size="sm" variant="subtle" leftIcon={<Upload className="w-3.5 h-3.5" />} onClick={() => setShowUpload(true)}>
              Upload File
            </Button>
            <Button size="sm" leftIcon={<Plus className="w-3.5 h-3.5" />} onClick={() => setShowCreate(true)}>
              New Data Job
            </Button>
          </div>
        }
      />
      {!activeProject && (
        <Card><CardContent><p className="text-sm text-text-secondary">Chọn một project để bắt đầu.</p></CardContent></Card>
      )}
      {activeProject && (
        <Card>
          <CardContent className="space-y-3">
            <div className="flex flex-col sm:flex-row gap-2">
              <div className="flex-1">
                <Input placeholder="Tìm job..." value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  onKeyDown={(e) => { if (e.key === 'Enter') load(); }} />
              </div>
              <div className="w-full sm:w-44">
                <Select value={statusFilter} onChange={(v) => setStatusFilter(v as string)}
                  options={[{ value: '', label: 'Mọi status' }, { value: 'DRAFT', label: 'DRAFT' }, { value: 'READY', label: 'READY' }, { value: 'COMPLETED', label: 'COMPLETED' }, { value: 'FAILED', label: 'FAILED' }]} />
              </div>
              <Button size="sm" onClick={load}>Lọc</Button>
            </div>
            {loading && <p className="text-xs text-text-muted">Đang tải...</p>}
            {!loading && jobs.length === 0 && (
              <EmptyState title="Chưa có data job" description="Upload file nguồn rồi tạo job so sánh đầu tiên." />
            )}
            <div className="divide-y divide-border-subtle">
              {jobs.map((j) => (
                <button key={j.id} onClick={() => navigate(`/qa/data/${j.id}`)}
                  className="w-full text-left py-2.5 px-1 hover:bg-surface-hover rounded-lg">
                  <div className="flex items-center gap-1.5 flex-wrap">
                    <span className="font-mono text-xs text-primary font-semibold">{j.job_code}</span>
                    <Badge variant={statusVariant(j.status)}>{j.status}</Badge>
                    {j.build && <Badge variant="neutral">{j.build}</Badge>}
                  </div>
                  <div className="text-sm text-text-primary mt-0.5">{j.name}</div>
                  <div className="text-[11px] text-text-muted">key: {(j.key_fields || []).join(', ') || '—'}</div>
                </button>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
      <Modal isOpen={showCreate} onClose={() => setShowCreate(false)} title="New Data QA Job" size="lg">
        <div className="space-y-2.5">
          <Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })}
            placeholder="VD: Access vs Web Data Check" />
          <Input value={form.purpose} onChange={(e) => setForm({ ...form, purpose: e.target.value })}
            placeholder="Mục đích (optional)" />
          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="text-xs font-semibold text-text-secondary">Source</label>
              <Select value={form.source_id} onChange={(v) => setForm({ ...form, source_id: v as string })}
                options={[{ value: '', label: '— Chọn —' }, ...sources.map((s: any) => ({ value: s.id, label: `${s.name} (${s.kind})` }))]} />
            </div>
            <div>
              <label className="text-xs font-semibold text-text-secondary">Destination</label>
              <Select value={form.dest_id} onChange={(v) => setForm({ ...form, dest_id: v as string })}
                options={[{ value: '', label: '— Chọn —' }, ...sources.map((s: any) => ({ value: s.id, label: `${s.name} (${s.kind})` }))]} />
            </div>
          </div>
          <div>
            <label className="text-xs font-semibold text-text-secondary">Business key (cách nhau dấu phẩy, VD: order_no,detail_no)</label>
            <Input value={form.key_fields} onChange={(e) => setForm({ ...form, key_fields: e.target.value })} />
          </div>
          <div className="grid grid-cols-2 gap-2">
            <Input value={form.build} onChange={(e) => setForm({ ...form, build: e.target.value })} placeholder="Build" />
            <Input value={form.environment} onChange={(e) => setForm({ ...form, environment: e.target.value })} placeholder="STG" />
          </div>
          <div className="flex justify-end gap-2 pt-1">
            <Button variant="ghost" size="sm" onClick={() => setShowCreate(false)}>Hủy</Button>
            <Button size="sm" onClick={create}>Tạo job</Button>
          </div>
        </div>
      </Modal>
      <Modal isOpen={showUpload} onClose={() => setShowUpload(false)} title="Upload Data File" size="lg">
        <div className="space-y-2.5">
          <p className="text-xs text-text-muted">CSV / Excel / JSON, tối đa 50MB. File chỉ đọc, không bao giờ bị sửa.</p>
          <input type="file" accept=".csv,.xlsx,.xls,.json,.txt,.log"
            onChange={(e) => setUploadFile(e.target.files?.[0] || null)}
            className="text-xs" />
          <Input value={uploadName} onChange={(e) => setUploadName(e.target.value)}
            placeholder="Tên nguồn (optional)" />
          <div className="flex justify-end gap-2">
            <Button variant="ghost" size="sm" onClick={() => setShowUpload(false)}>Hủy</Button>
            <Button size="sm" onClick={upload}>Upload</Button>
          </div>
        </div>
      </Modal>
    </div>
  );
};

export default DataJobsPage;
