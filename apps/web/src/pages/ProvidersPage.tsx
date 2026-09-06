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
  Sparkles
} from 'lucide-react';
import { apiClient } from '../api/client';
import { ProviderInfo } from '../types';
import { useToast } from '../context/ToastContext';

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
    <div className="flex-1 flex flex-col h-screen overflow-y-auto bg-slate-950 p-6 space-y-6">
      {/* Header with Global Refresh Button */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold text-white flex items-center gap-2">
            <Cpu className="w-5 h-5 text-sky-400" />
            AI Providers & Live Model Discovery
          </h2>
          <p className="text-xs text-slate-400">
            Dynamically discover and configure 100% of models available from Google Gemini, Groq, and Ollama APIs.
          </p>
        </div>

        <button
          onClick={handleRefreshAll}
          disabled={isRefreshingAll}
          className="px-3.5 py-1.5 rounded-lg bg-sky-600 hover:bg-sky-500 text-white text-xs font-semibold flex items-center gap-1.5 shadow-md shadow-sky-600/20 disabled:opacity-50"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${isRefreshingAll ? 'animate-spin' : ''}`} />
          {isRefreshingAll ? 'Querying APIs...' : 'Scan All Live Models'}
        </button>
      </div>

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
            <div
              key={prov.id}
              className="rounded-xl border border-slate-800 bg-slate-900/60 shadow-lg p-5 flex flex-col justify-between space-y-4"
            >
              {/* Card Header */}
              <div>
                <div className="flex items-center justify-between mb-1.5">
                  <h3 className="text-sm font-bold text-white flex items-center gap-2">
                    {prov.display_name}
                  </h3>
                  <span className={`text-[10px] font-semibold px-2 py-0.5 rounded flex items-center gap-1 ${
                    prov.is_healthy
                      ? 'bg-emerald-950 text-emerald-300 border border-emerald-800/40'
                      : 'bg-slate-800 text-slate-400 border border-slate-700'
                  }`}>
                    {prov.is_healthy ? (
                      <>
                        <CheckCircle2 className="w-3 h-3 text-emerald-400" /> Connected
                      </>
                    ) : (
                      <>
                        <AlertCircle className="w-3 h-3 text-slate-400" /> Needs Refresh
                      </>
                    )}
                  </span>
                </div>

                <div className="text-[11px] text-slate-400 flex items-center justify-between">
                  <span>{prov.name === 'ollama' ? 'Local offline engine' : 'Cloud provider adapter'}</span>
                  <span className="font-mono text-sky-400 text-[10px] bg-sky-950/60 px-1.5 py-0.2 rounded border border-sky-800/40">
                    {modelsList.length} models fetched
                  </span>
                </div>
              </div>

              {/* Form Inputs */}
              <div className="space-y-3 text-xs">
                {/* API Key */}
                {prov.name !== 'ollama' && (
                  <div>
                    <label className="text-slate-300 font-medium block mb-1 flex items-center justify-between">
                      <span className="flex items-center gap-1">
                        <KeyRound className="w-3 h-3 text-slate-400" />
                        API Key:
                      </span>
                      <span className="font-mono text-slate-500 text-[10px]">
                        {prov.api_key_masked || 'None'}
                      </span>
                    </label>
                    <input
                      type="password"
                      value={form.api_key}
                      onChange={(e) => setEditForms(prev => ({
                        ...prev,
                        [prov.name]: { ...prev[prov.name], api_key: e.target.value }
                      }))}
                      placeholder="Paste new key to replace..."
                      className="w-full bg-slate-850 border border-slate-700 rounded px-2.5 py-1.5 text-slate-100 focus:outline-none focus:border-sky-500 font-mono text-[11px]"
                    />
                  </div>
                )}

                {/* Base URL (for Ollama) */}
                {prov.name === 'ollama' && (
                  <div>
                    <label className="text-slate-300 font-medium block mb-1">Base Endpoint:</label>
                    <input
                      type="text"
                      disabled
                      value={prov.base_url || 'http://127.0.0.1:11434'}
                      className="w-full bg-slate-850 border border-slate-800 rounded px-2.5 py-1.5 text-slate-400 font-mono text-[11px] cursor-not-allowed"
                    />
                  </div>
                )}

                {/* Default Model Dropdown (Dynamic from 100% of API Models) */}
                <div>
                  <div className="flex items-center justify-between mb-1">
                    <label className="text-slate-300 font-medium">Selected Model:</label>
                    <button
                      type="button"
                      onClick={() => handleRefreshModels(prov.name)}
                      disabled={isRefreshing}
                      className="text-[10px] text-sky-400 hover:text-sky-300 flex items-center gap-1 disabled:opacity-50"
                      title="Fetch live models directly from API"
                    >
                      <RefreshCw className={`w-2.5 h-2.5 ${isRefreshing ? 'animate-spin' : ''}`} />
                      {isRefreshing ? 'Fetching...' : 'Refresh Models'}
                    </button>
                  </div>

                  {modelsList.length > 0 ? (
                    <select
                      value={form.default_model}
                      onChange={(e) => setEditForms(prev => ({
                        ...prev,
                        [prov.name]: { ...prev[prov.name], default_model: e.target.value }
                      }))}
                      className="w-full bg-slate-850 border border-slate-700 rounded px-2.5 py-1.5 text-slate-100 font-mono text-[11px] focus:outline-none focus:border-sky-500"
                    >
                      {/* If current default_model is not in the list, keep it as an option */}
                      {!modelsList.includes(form.default_model) && (
                        <option value={form.default_model}>{form.default_model} (Custom)</option>
                      )}
                      {modelsList.map((m) => (
                        <option key={m} value={m}>
                          {m}
                        </option>
                      ))}
                    </select>
                  ) : (
                    <input
                      type="text"
                      value={form.default_model}
                      onChange={(e) => setEditForms(prev => ({
                        ...prev,
                        [prov.name]: { ...prev[prov.name], default_model: e.target.value }
                      }))}
                      placeholder="Click Refresh Models to fetch from API..."
                      className="w-full bg-slate-850 border border-slate-700 rounded px-2.5 py-1.5 text-slate-100 font-mono text-[11px] focus:outline-none focus:border-sky-500"
                    />
                  )}
                </div>

                {/* Priority */}
                <div>
                  <label className="text-slate-300 font-medium block mb-1">Router Priority (1 = Primary):</label>
                  <input
                    type="number"
                    min={1}
                    max={10}
                    value={form.priority}
                    onChange={(e) => setEditForms(prev => ({
                      ...prev,
                      [prov.name]: { ...prev[prov.name], priority: Number(e.target.value) }
                    }))}
                    className="w-20 bg-slate-850 border border-slate-700 rounded px-2.5 py-1 text-slate-100 font-mono text-[11px] focus:outline-none focus:border-sky-500"
                  />
                </div>

                {/* Collapsible Model List View */}
                {modelsList.length > 0 && (
                  <div className="pt-1">
                    <button
                      type="button"
                      onClick={() => setExpandedModels(prev => ({ ...prev, [prov.name]: !prev[prov.name] }))}
                      className="text-[11px] text-slate-400 hover:text-slate-200 flex items-center justify-between w-full py-1 border-t border-slate-800/80"
                    >
                      <span className="flex items-center gap-1">
                        <Layers className="w-3 h-3 text-sky-400" />
                        All Fetched Models ({modelsList.length})
                      </span>
                      {isExpanded ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
                    </button>

                    {isExpanded && (
                      <div className="mt-1 p-2 bg-slate-950/80 rounded border border-slate-800 max-h-36 overflow-y-auto space-y-1 font-mono text-[10px] text-slate-300">
                        {modelsList.map((m) => (
                          <div
                            key={m}
                            onClick={() => setEditForms(prev => ({
                              ...prev,
                              [prov.name]: { ...prev[prov.name], default_model: m }
                            }))}
                            className={`p-1 rounded cursor-pointer transition-colors ${
                              form.default_model === m
                                ? 'bg-sky-950 text-sky-300 font-bold border border-sky-800/50'
                                : 'hover:bg-slate-800 text-slate-400 hover:text-white'
                            }`}
                          >
                            {m} {form.default_model === m ? '✓ (Selected)' : ''}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}

                {/* Live Test Results Alert */}
                {test && (
                  <div className={`p-2.5 rounded text-[11px] font-mono ${
                    test.is_healthy
                      ? 'bg-emerald-950/60 border border-emerald-800/40 text-emerald-300'
                      : 'bg-rose-950/60 border border-rose-800/40 text-rose-300'
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
              <div className="flex items-center justify-between pt-3 border-t border-slate-800">
                <button
                  onClick={() => handleTestConnection(prov.name)}
                  disabled={isTesting}
                  className="px-3 py-1.5 rounded bg-slate-850 hover:bg-slate-800 text-slate-300 text-xs font-medium flex items-center gap-1.5 border border-slate-700 disabled:opacity-50"
                >
                  <RefreshCw className={`w-3.5 h-3.5 ${isTesting ? 'animate-spin text-sky-400' : ''}`} />
                  {isTesting ? 'Testing...' : 'Test Connection'}
                </button>

                <button
                  onClick={() => handleSave(prov.name)}
                  className="px-3 py-1.5 rounded bg-sky-600 hover:bg-sky-500 text-white text-xs font-medium flex items-center gap-1.5 shadow"
                >
                  {savedSuccess === prov.name ? (
                    <>
                      <CheckCircle2 className="w-3.5 h-3.5" /> Saved!
                    </>
                  ) : (
                    <>
                      <Save className="w-3.5 h-3.5" /> Save
                    </>
                  )}
                </button>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
