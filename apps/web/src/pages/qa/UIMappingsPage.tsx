import React, { useEffect, useState } from 'react';
import { MousePointer2, Plus, Trash2 } from 'lucide-react';
import { apiClient } from '../../api/client';
import { Project } from '../../types';
import { UIElementMapping, UIPage } from '../../types/qa';
import { useToast } from '../../context/ToastContext';
import { useConfirm } from '../../context/ConfirmDialogContext';
import { PageHeader } from '../../components/ui/PageHeader';
import { Card, CardContent } from '../../components/ui/Card';
import { Badge } from '../../components/ui/Badge';
import { Button } from '../../components/ui/Button';
import { Input } from '../../components/ui/Input';
import { Select } from '../../components/ui/Select';
import { Modal } from '../../components/ui/Modal';

interface Props {
  activeProject: Project | null;
}

const STRATEGIES = ['role', 'label', 'placeholder', 'text', 'testid', 'css'];

export const UIMappingsPage: React.FC<Props> = ({ activeProject }) => {
  const [pages, setPages] = useState<UIPage[]>([]);
  const [mappings, setMappings] = useState<UIElementMapping[]>([]);
  const [pageFilter, setPageFilter] = useState('');
  const [showPage, setShowPage] = useState(false);
  const [showMap, setShowMap] = useState(false);
  const [pageForm, setPageForm] = useState({ page_name: '', url_path: '', description: '' });
  const [mapForm, setMapForm] = useState({ page_name: '', element_name: '', strategy: 'role', value: '', name: '' });
  const toast = useToast();
  const confirm = useConfirm();

  const load = async () => {
    if (!activeProject) return;
    try {
      const [p, m] = await Promise.all([
        apiClient.qaListUiPages(activeProject.id),
        apiClient.qaListUiMappings(activeProject.id, pageFilter ? { page_name: pageFilter } : {}),
      ]);
      setPages(p);
      setMappings(m);
    } catch {
      toast.error('Không tải được mappings');
    }
  };

  useEffect(() => { load(); /* eslint-disable-next-line */ }, [activeProject?.id]);

  const createPage = async () => {
    if (!activeProject || !pageForm.page_name.trim()) return;
    try {
      await apiClient.qaCreateUiPage(activeProject.id, { ...pageForm, common_actions: [] });
      toast.success('Đã tạo page');
      setShowPage(false);
      setPageForm({ page_name: '', url_path: '', description: '' });
      load();
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || 'Tạo thất bại');
    }
  };

  const createMapping = async () => {
    if (!activeProject || !mapForm.page_name.trim() || !mapForm.element_name.trim() || !mapForm.value.trim()) {
      toast.error('Nhập đủ page / element / locator value');
      return;
    }
    const locator: any = { strategy: mapForm.strategy, value: mapForm.value };
    if (mapForm.strategy === 'role' && mapForm.name.trim()) locator.options = { name: mapForm.name.trim() };
    try {
      await apiClient.qaCreateUiMapping(activeProject.id, {
        page_name: mapForm.page_name, element_name: mapForm.element_name, locator,
      });
      toast.success('Đã thêm mapping (ACTIVE)');
      setShowMap(false);
      setMapForm({ page_name: '', element_name: '', strategy: 'role', value: '', name: '' });
      load();
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || 'Thêm thất bại (kiểm tra locator policy)');
    }
  };

  return (
    <div className="flex-1 overflow-y-auto p-4 sm:p-6 space-y-4">
      <PageHeader
        title="UI Element Mappings"
        description="Mapping được duyệt dùng chung cho mọi testcase. Ưu tiên: role → label → placeholder → text → testid → CSS ổn định."
        icon={<MousePointer2 className="w-5 h-5" />}
        actions={
          <div className="flex gap-1.5">
            <Button size="sm" variant="subtle" leftIcon={<Plus className="w-3 h-3" />} onClick={() => setShowPage(true)}>Thêm Page</Button>
            <Button size="sm" leftIcon={<Plus className="w-3 h-3" />} onClick={() => setShowMap(true)}>Thêm Mapping</Button>
          </div>
        }
      />
      {!activeProject && (
        <Card><CardContent><p className="text-sm text-text-secondary">Chọn một project để bắt đầu.</p></CardContent></Card>
      )}
      {activeProject && (
        <Card>
          <CardContent className="space-y-3">
            <div className="w-full sm:w-64">
              <Select value={pageFilter} onChange={(v) => { setPageFilter(v as string); }}
                options={[{ value: '', label: 'Mọi page' }, ...pages.map((p) => ({ value: p.page_name, label: `${p.page_name} (${p.element_count})` }))]} />
            </div>
            <div className="flex gap-1.5">
              <Button size="sm" variant="ghost" onClick={load}>Lọc</Button>
            </div>
            <div className="divide-y divide-border-subtle">
              {mappings.map((m) => (
                <div key={m.id} className="py-2 px-1 flex items-start gap-2">
                  <div className="flex-1">
                    <div className="flex items-center gap-1.5 flex-wrap">
                      <span className="text-xs font-semibold">{m.page_name} / {m.element_name}</span>
                      <Badge variant={m.status === 'ACTIVE' ? 'success' : 'warning'}>{m.status}</Badge>
                      <span className="text-[11px] text-text-muted">dùng {m.used_count} lần</span>
                    </div>
                    <div className="font-mono text-xs text-text-secondary mt-0.5">
                      {m.locator.strategy}: {m.locator.value}
                      {m.locator.options?.name && ` (name: ${m.locator.options.name})`}
                    </div>
                  </div>
                  <div className="flex gap-1">
                    {m.status !== 'ACTIVE' && (
                      <Button size="sm" variant="subtle" onClick={async () => {
                        await apiClient.qaUpdateUiMapping(m.id, { status: 'ACTIVE' });
                        toast.success('Đã duyệt mapping');
                        load();
                      }}>Duyệt</Button>
                    )}
                    <Button size="sm" variant="ghost" onClick={async () => {
                      if (await confirm({ title: 'Xóa mapping?', message: `${m.element_name}?`, confirmText: 'Xóa', isDestructive: true })) {
                        await apiClient.qaDeleteUiMapping(m.id);
                        toast.success('Đã xóa');
                        load();
                      }
                    }}><Trash2 className="w-3 h-3" /></Button>
                  </div>
                </div>
              ))}
              {mappings.length === 0 && <p className="text-xs text-text-muted py-2">Chưa có mapping. Thêm mapping trước khi generate automation.</p>}
            </div>
            {pages.length > 0 && (
              <div className="pt-2 border-t border-border-subtle">
                <div className="text-xs font-semibold mb-1">Pages ({pages.length})</div>
                {pages.map((p) => (
                  <div key={p.id} className="text-xs text-text-secondary py-0.5">
                    <span className="font-semibold text-text-primary">{p.page_name}</span>
                    <span className="font-mono"> {p.url_path}</span> · {p.element_count} elements
                    {p.description && ` · ${p.description}`}
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      )}
      <Modal isOpen={showPage} onClose={() => setShowPage(false)} title="Thêm Page Knowledge" size="lg">
        <div className="space-y-2">
          <Input value={pageForm.page_name} onChange={(e) => setPageForm({ ...pageForm, page_name: e.target.value })} placeholder="Login Page" />
          <Input value={pageForm.url_path} onChange={(e) => setPageForm({ ...pageForm, url_path: e.target.value })} placeholder="/login" />
          <Input value={pageForm.description} onChange={(e) => setPageForm({ ...pageForm, description: e.target.value })} placeholder="Mô tả ngắn" />
          <div className="flex justify-end gap-2">
            <Button variant="ghost" size="sm" onClick={() => setShowPage(false)}>Hủy</Button>
            <Button size="sm" onClick={createPage}>Tạo</Button>
          </div>
        </div>
      </Modal>
      <Modal isOpen={showMap} onClose={() => setShowMap(false)} title="Thêm Element Mapping" size="lg">
        <div className="space-y-2">
          <Input value={mapForm.page_name} onChange={(e) => setMapForm({ ...mapForm, page_name: e.target.value })} placeholder="Login Page" />
          <Input value={mapForm.element_name} onChange={(e) => setMapForm({ ...mapForm, element_name: e.target.value })} placeholder="Login Button" />
          <div className="flex gap-2">
            <div className="w-36">
              <Select value={mapForm.strategy} onChange={(v) => setMapForm({ ...mapForm, strategy: v as string })}
                options={STRATEGIES.map((s) => ({ value: s, label: s }))} />
            </div>
            <div className="flex-1">
              <Input value={mapForm.value} onChange={(e) => setMapForm({ ...mapForm, value: e.target.value })} placeholder='button / Email / "Login"' />
            </div>
          </div>
          {mapForm.strategy === 'role' && (
            <Input value={mapForm.name} onChange={(e) => setMapForm({ ...mapForm, name: e.target.value })} placeholder="Accessible name (VD Login)" />
          )}
          <p className="text-[11px] text-text-muted">Cấm nth-child, XPath tuyệt đối, sleep cứng — hệ thống tự kiểm tra.</p>
          <div className="flex justify-end gap-2">
            <Button variant="ghost" size="sm" onClick={() => setShowMap(false)}>Hủy</Button>
            <Button size="sm" onClick={createMapping}>Thêm (ACTIVE)</Button>
          </div>
        </div>
      </Modal>
    </div>
  );
};
