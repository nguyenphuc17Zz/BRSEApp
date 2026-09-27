import React, { useState, useEffect } from 'react';
import { 
  Cpu, 
  CheckCircle2, 
  AlertCircle, 
  KeyRound, 
  Radio, 
  Activity, 
  RefreshCw,
  Lock,
  Save,
  ChevronDown,
  ChevronUp,
  Layers,
  Sparkles,
  Server
} from 'lucide-react';
import { apiClient } from '../api/client';
import { ProviderInfo } from '../types';
import { useToast } from '../context/ToastContext';
import { PageHeader } from '../components/ui/PageHeader';
import { Card } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { Badge } from '../components/ui/Badge';
import { Input } from '../components/ui/Input';
import { Select } from '../components/ui/Select';

export const ProvidersPage: React.FC = () => {
  const toast = useToast();
  const [providers, setProviders] = useState<ProviderInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [testingName, setTestingName] = useState<string | null>(null);
  const [refreshingName, setRefreshingName] = useState<string | null>(null);
  const [isRefreshingAll, setIsRefreshingAll] = useState(false);
  const [testResults, setTestResults] = useState<Record<string, any>>({});
  const [editForms, setEditForms] = useState<Record<string, { api_key: string; default_model: string; priority: number }>>({});
  const [savedSuccess, setSavedSuccess] = useState<string | null>(null);
  const [expandedModels, setExpandedModels] = useState<Record<string, boolean>>({});

  useEffect(() => {
    loadProviders();
  }, []);

  const loadProviders = async () => {
    setLoading(true);
    try {
      const list = await apiClient.getProviders();
      setProviders(list);
      const initialForms: Record<string, any> = {};
      list.forEach(p => {
        initialForms[p.name] = {
          api_key: '',
          default_model: p.default_model,
          priority: p.priority
        };
      });
      setEditForms(initialForms);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  const handleTestConnection = async (name: string) => {
    setTestingName(name);
    try {
      const res = await apiClient.testProvider(name);
      setTestResults(prev => ({ ...prev, [name]: res }));
      loadProviders();
    } catch (e: any) {
      setTestResults(prev => ({
        ...prev,
        [name]: { is_healthy: false, message: e?.response?.data?.detail || e.message }
      }));
    } finally {
      setTestingName(null);
    }
  };

  const handleRefreshModels = async (name: string) => {
    setRefreshingName(name);
    try {
      const res = await apiClient.refreshModels(name);
      await loadProviders();
      setTestResults(prev => ({
        ...prev,
        [name]: { is_healthy: true, message: `Loaded ${res.models_count} models live from ${name} API.` }
      }));
      toast.success(`Đã tải ${res.models_count} model trực tiếp từ API ${name}`);
    } catch (e: any) {
      toast.error(`Lỗi cập nhật model cho ${name}: ` + (e?.response?.data?.detail || e.message));
    } finally {
      setRefreshingName(null);
    }
  };

  const handleRefreshAll = async () => {
    setIsRefreshingAll(true);
    try {
      await apiClient.refreshAllModels();
      await loadProviders();
      toast.success('Toàn bộ catalog model đã được đồng bộ từ provider API!');
    } catch (e: any) {
      toast.error('Failed to refresh models: ' + (e?.response?.data?.detail || e.message));
    } finally {
      setIsRefreshingAll(false);
    }
  };

  const handleSave = async (name: string) => {
    const form = editForms[name];
    if (!form) return;

    try {
      await apiClient.updateProvider(name, {
        api_key: form.api_key.trim() || undefined,
        default_model: form.default_model,
        priority: Number(form.priority)
      });
      setSavedSuccess(name);
      setTimeout(() => setSavedSuccess(null), 2500);
      loadProviders();
      toast.success(`Đã lưu cấu hình provider ${name} thành công`);
    } catch (e: any) {
      toast.error('Failed to update provider: ' + (e?.response?.data?.detail || e.message));
    }
  };

  return (
    <div className="flex-1 flex flex-col h-screen overflow-y-auto bg-canvas p-6 space-y-6">
      {/* Header with Global Refresh Button */}
      <PageHeader
        title="Mô hình AI"
        actions={
          <Button
            variant="primary"
            onClick={handleRefreshAll}
            disabled={isRefreshingAll}
            leftIcon={<RefreshCw className={`w-3.5 h-3.5 ${isRefreshingAll ? 'animate-spin' : ''}`} />}
          >
            {isRefreshingAll ? 'Đang quét...' : 'Quét mô hình'}
          </Button>
        }
      />

      {/* Provider Cards */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {providers.map((prov) => {
          const form = editForms[prov.name] || { api_key: '', default_model: prov.default_model, priority: prov.priority };
          const test = testResults[prov.name];
          const isTesting = testingName === prov.name;
          const isRefreshing = refreshingName === prov.name;
          const isExpanded = !!expandedModels[prov.name];
          const modelsList = prov.available_models || [];

          return (
            <Card
              key={prov.id}
              className="p-5 flex flex-col justify-between space-y-4 border border-border-subtle bg-surface shadow-sm"
            >
              {/* Card Header */}
              <div>
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <div className="w-8 h-8 rounded-lg bg-primary/10 text-primary flex items-center justify-center font-bold">
                      <Cpu className="w-4 h-4" />
                    </div>
                    <h3 className="text-sm font-bold text-text-primary">
                      {prov.display_name}
                    </h3>
                  </div>
                  {prov.is_healthy ? (
                    <Badge variant="success" size="sm" className="flex items-center gap-1">
                      <CheckCircle2 className="w-3 h-3" /> Connected
                    </Badge>
                  ) : (
                    <Badge variant="neutral" size="sm" className="flex items-center gap-1">
                      <AlertCircle className="w-3 h-3 text-text-muted" /> Needs Refresh
                    </Badge>
                  )}
                </div>

                <div className="text-[11px] text-text-muted flex items-center justify-between pt-1">
                  <span>{prov.name === 'ollama' ? 'Local offline engine' : 'Cloud provider adapter'}</span>
                  <Badge variant="info" size="sm" className="font-mono text-[10px]">
                    {modelsList.length} models fetched
                  </Badge>
                </div>
              </div>

              {/* Form Inputs */}
              <div className="space-y-3.5 text-xs">
                {/* API Key */}
                {prov.name !== 'ollama' && (
                  <div>
                    <label className="text-text-secondary font-medium block mb-1 flex items-center justify-between">
                      <span className="flex items-center gap-1">
                        <KeyRound className="w-3 h-3 text-text-muted" />
                        API Key:
                      </span>
                      <span className="font-mono text-text-muted text-[10px]">
                        {prov.api_key_masked || 'None'}
                      </span>
                    </label>
                    <Input
                      type="password"
                      value={form.api_key}
                      onChange={(e) => setEditForms(prev => ({
                        ...prev,
                        [prov.name]: { ...prev[prov.name], api_key: e.target.value }
                      }))}
                      placeholder="Paste new key to replace..."
                      className="font-mono text-[11px]"
                    />
                  </div>
                )}

                {/* Base URL (for Ollama) */}
                {prov.name === 'ollama' && (
                  <div>
                    <label className="text-text-secondary font-medium block mb-1">Base Endpoint:</label>
                    <Input
                      type="text"
                      disabled
                      value={prov.base_url || 'http://127.0.0.1:11434'}
                      className="font-mono text-[11px] opacity-75 cursor-not-allowed"
                    />
                  </div>
                )}

                {/* Default Model Dropdown */}
                <div>
                  <div className="flex items-center justify-between mb-1">
                    <label className="text-text-secondary font-medium">Selected Model:</label>
                    <button
                      type="button"
                      onClick={() => handleRefreshModels(prov.name)}
                      disabled={isRefreshing}
                      className="text-[10px] text-primary hover:underline flex items-center gap-1 disabled:opacity-50 font-medium"
                      title="Fetch live models directly from API"
                    >
                      <RefreshCw className={`w-2.5 h-2.5 ${isRefreshing ? 'animate-spin' : ''}`} />
                      {isRefreshing ? 'Fetching...' : 'Refresh Models'}
                    </button>
                  </div>

                  {modelsList.length > 0 ? (
                    <Select
                      value={form.default_model}
                      onChange={(val) => setEditForms(prev => ({
                        ...prev,
                        [prov.name]: { ...prev[prov.name], default_model: val }
                      }))}
                      size="sm"
                      className="w-full"
                      triggerClassName="font-mono text-[11px]"
                      options={[
                        ...(!modelsList.includes(form.default_model) && form.default_model ? [{ value: form.default_model, label: `${form.default_model} (Custom)` }] : []),
                        ...modelsList.map((m) => ({ value: m, label: m }))
                      ]}
                    />
                  ) : (
                    <Input
                      type="text"
                      value={form.default_model}
                      onChange={(e) => setEditForms(prev => ({
                        ...prev,
                        [prov.name]: { ...prev[prov.name], default_model: e.target.value }
                      }))}
                      placeholder="Nhấp Làm mới để tải danh sách mô hình..."
                      className="font-mono text-[11px]"
                    />
                  )}
                </div>

                {/* Priority */}
                <div>
                  <label className="text-text-secondary font-medium block mb-1">Độ ưu tiên Router (1 = Cao nhất):</label>
                  <Input
                    type="number"
                    min={1}
                    max={10}
                    value={form.priority}
                    onChange={(e) => setEditForms(prev => ({
                      ...prev,
                      [prov.name]: { ...prev[prov.name], priority: Number(e.target.value) }
                    }))}
                    className="w-24 font-mono text-[11px]"
                  />
                </div>

                {/* Collapsible Model List View */}
                {modelsList.length > 0 && (
                  <div className="pt-1">
                    <button
                      type="button"
                      onClick={() => setExpandedModels(prev => ({ ...prev, [prov.name]: !prev[prov.name] }))}
                      className="text-[11px] text-text-muted hover:text-text-primary flex items-center justify-between w-full py-1.5 border-t border-border-subtle transition"
                    >
                      <span className="flex items-center gap-1.5 font-medium">
                        <Layers className="w-3.5 h-3.5 text-primary" />
                        Danh sách mô hình ({modelsList.length})
                      </span>
                      {isExpanded ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
                    </button>

                    {isExpanded && (
                      <div className="mt-1 p-2 bg-surface-elevated/70 rounded-lg border border-border-subtle max-h-36 overflow-y-auto space-y-1 font-mono text-[10px] text-text-secondary">
                        {modelsList.map((m) => (
                          <div
                            key={m}
                            onClick={() => setEditForms(prev => ({
                              ...prev,
                              [prov.name]: { ...prev[prov.name], default_model: m }
                            }))}
                            className={`p-1.5 rounded cursor-pointer transition-colors ${
                              form.default_model === m
                                ? 'bg-primary/10 text-primary font-bold border border-primary/30'
                                : 'hover:bg-surface-elevated text-text-muted hover:text-text-primary'
                            }`}
                          >
                            {m} {form.default_model === m ? '✓ (Đang chọn)' : ''}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}

                {/* Live Test Results Alert */}
                {test && (
                  <div className={`p-2.5 rounded-lg text-[11px] font-mono border ${
                    test.is_healthy
                      ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-500'
                      : 'bg-danger/10 border-danger/30 text-danger'
                  }`}>
                    {test.is_healthy ? (
                      <div>✓ {test.message}</div>
                    ) : (
                      <div>✕ {test.message}</div>
                    )}
                  </div>
                )}
              </div>

              {/* Action Buttons */}
              <div className="flex items-center justify-between pt-3 border-t border-border-subtle gap-2">
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => handleTestConnection(prov.name)}
                  disabled={isTesting}
                  leftIcon={<RefreshCw className={`w-3.5 h-3.5 ${isTesting ? 'animate-spin text-primary' : ''}`} />}
                >
                  {isTesting ? 'Đang thử...' : 'Kiểm tra ping'}
                </Button>

                <Button
                  variant="primary"
                  size="sm"
                  onClick={() => handleSave(prov.name)}
                  leftIcon={savedSuccess === prov.name ? <CheckCircle2 className="w-3.5 h-3.5" /> : <Save className="w-3.5 h-3.5" />}
                >
                  {savedSuccess === prov.name ? 'Đã lưu' : 'Lưu cấu hình'}
                </Button>
              </div>
            </Card>
          );
        })}
      </div>
    </div>
  );
};
