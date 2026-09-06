import React, { useEffect, useState } from 'react';
import { 
  FolderKanban, 
  BookA, 
  Database, 
  Languages, 
  Cpu, 
  Activity, 
  CheckCircle2, 
  AlertCircle,
  ExternalLink,
  Sparkles,
  ArrowRight
} from 'lucide-react';
import { apiClient } from '../api/client';
import { DashboardData, Project } from '../types';

interface DashboardPageProps {
  activeProject: Project | null;
  setCurrentTab: (tab: string) => void;
}

export const DashboardPage: React.FC<DashboardPageProps> = ({
  activeProject,
  setCurrentTab
}) => {
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadStats();
  }, [activeProject]);

  const loadStats = async () => {
    setLoading(true);
    try {
      const res = await apiClient.getDashboardStats(activeProject?.id);
      setData(res);
    } catch (e) {
      console.error('Failed to load stats:', e);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex-1 flex flex-col h-screen overflow-y-auto bg-slate-950 p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold tracking-tight text-white flex items-center gap-2">
            BrSE Copilot Dashboard
          </h2>
          <p className="text-xs text-slate-400 mt-0.5">
            Operational overview, AI provider routing, and project knowledge repository.
          </p>
        </div>

        <button
          onClick={() => setCurrentTab('translator')}
          className="px-3.5 py-1.5 rounded-lg bg-sky-600 hover:bg-sky-500 text-white text-xs font-semibold flex items-center gap-1.5 shadow-md shadow-sky-600/20"
        >
          <Languages className="w-3.5 h-3.5" />
          Open Translator
        </button>
      </div>

      {/* Metric Cards Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="p-4 rounded-xl border border-slate-800 bg-slate-900/60 shadow">
          <div className="flex items-center justify-between text-slate-400 mb-2">
            <span className="text-xs font-medium uppercase tracking-wider">Current Project</span>
            <FolderKanban className="w-4 h-4 text-sky-400" />
          </div>
          <div className="text-lg font-bold text-white truncate">
            {activeProject ? activeProject.name : 'Global Workspace'}
          </div>
          <div className="text-[11px] text-slate-500 mt-1 font-mono">
            {activeProject ? `${activeProject.code} • ${activeProject.default_style}` : 'All projects combined'}
          </div>
        </div>

        <div className="p-4 rounded-xl border border-slate-800 bg-slate-900/60 shadow">
          <div className="flex items-center justify-between text-slate-400 mb-2">
            <span className="text-xs font-medium uppercase tracking-wider">Glossary Terms</span>
            <BookA className="w-4 h-4 text-emerald-400" />
          </div>
          <div className="text-2xl font-bold text-white font-mono">
            {data?.total_glossary_terms || 0}
          </div>
          <div className="text-[11px] text-emerald-400/80 mt-1 flex items-center gap-1">
            <CheckCircle2 className="w-3 h-3" />
            Active IT terminology constraints
          </div>
        </div>

        <div className="p-4 rounded-xl border border-slate-800 bg-slate-900/60 shadow">
          <div className="flex items-center justify-between text-slate-400 mb-2">
            <span className="text-xs font-medium uppercase tracking-wider">Translation Memory</span>
            <Database className="w-4 h-4 text-indigo-400" />
          </div>
          <div className="text-2xl font-bold text-white font-mono">
            {data?.total_tm_entries || 0}
          </div>
          <div className="text-[11px] text-indigo-400/80 mt-1">
            Verified reference segments
          </div>
        </div>

        <div className="p-4 rounded-xl border border-slate-800 bg-slate-900/60 shadow">
          <div className="flex items-center justify-between text-slate-400 mb-2">
            <span className="text-xs font-medium uppercase tracking-wider">Translations Run</span>
            <Activity className="w-4 h-4 text-amber-400" />
          </div>
          <div className="text-2xl font-bold text-white font-mono">
            {data?.total_translations || 0}
          </div>
          <div className="text-[11px] text-slate-500 mt-1">
            Recorded in local SQLite
          </div>
        </div>
      </div>

      {/* AI Providers Live Status Grid */}
      <div className="p-4 rounded-xl border border-slate-800 bg-slate-900/40">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-xs font-bold uppercase tracking-wider text-slate-300 flex items-center gap-2">
            <Cpu className="w-4 h-4 text-sky-400" />
            AI Provider Infrastructure
          </h3>
          <button
            onClick={() => setCurrentTab('providers')}
            className="text-xs text-sky-400 hover:text-sky-300 flex items-center gap-1"
          >
            Manage Providers <ArrowRight className="w-3 h-3" />
          </button>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          {data?.providers_status.map((prov) => (
            <div
              key={prov.id}
              className="p-3 rounded-lg border border-slate-800 bg-slate-850/80 flex items-center justify-between"
            >
              <div>
                <div className="text-xs font-semibold text-white flex items-center gap-1.5">
                  {prov.display_name}
                  {prov.is_healthy ? (
                    <span className="w-2 h-2 rounded-full bg-emerald-400" />
                  ) : (
                    <span className="w-2 h-2 rounded-full bg-slate-500" />
                  )}
                </div>
                <div className="text-[11px] text-slate-400 font-mono mt-0.5">
                  Model: {prov.default_model}
                </div>
                <div className="text-[10px] text-slate-500">
                  Priority: {prov.priority} • Key: {prov.api_key_masked || 'Local'}
                </div>
              </div>

              <span className={`text-[10px] font-semibold px-2 py-0.5 rounded ${
                prov.is_healthy ? 'bg-emerald-950 text-emerald-300 border border-emerald-800/40' : 'bg-slate-800 text-slate-400'
              }`}>
                {prov.is_healthy ? 'Ready' : 'Configured'}
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* 2-Column: Recent Translations & Top Glossary */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Recent Translations Table */}
        <div className="p-4 rounded-xl border border-slate-800 bg-slate-900/50 flex flex-col">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-300">
              Recent Translations
            </h3>
            <button
              onClick={() => setCurrentTab('history')}
              className="text-xs text-sky-400 hover:text-sky-300"
            >
              View All
            </button>
          </div>

          <div className="space-y-2 flex-1 overflow-y-auto">
            {data?.recent_translations && data.recent_translations.length > 0 ? (
              data.recent_translations.map((t, idx) => (
                <div key={idx} className="p-2.5 rounded bg-slate-850 border border-slate-800/80 space-y-1">
                  <div className="flex items-center justify-between text-[11px] text-slate-400 font-mono">
                    <span className="text-sky-400">{t.provider}</span>
                    <span>{t.latency_ms}ms</span>
                  </div>
                  <div className="text-xs text-slate-200 font-medium truncate">
                    JA: {t.source_text}
                  </div>
                  <div className="text-xs text-slate-400 truncate">
                    VI: {t.selected_translation}
                  </div>
                </div>
              ))
            ) : (
              <div className="text-xs text-slate-500 text-center py-6">No translations recorded yet.</div>
            )}
          </div>
        </div>

        {/* Top Glossary Terms */}
        <div className="p-4 rounded-xl border border-slate-800 bg-slate-900/50 flex flex-col">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-300">
              Active IT Terminology
            </h3>
            <button
              onClick={() => setCurrentTab('glossary')}
              className="text-xs text-sky-400 hover:text-sky-300"
            >
              Manage Glossary
            </button>
          </div>

          <div className="space-y-2 flex-1 overflow-y-auto">
            {data?.top_glossary_terms && data.top_glossary_terms.length > 0 ? (
              data.top_glossary_terms.map((term) => (
                <div key={term.id} className="p-2.5 rounded bg-slate-850 border border-slate-800/80 flex items-center justify-between">
                  <div>
                    <div className="text-xs font-semibold text-white flex items-center gap-2">
                      <span>{term.source_term}</span>
                      <span className="text-slate-500 font-mono">→</span>
                      <span className="text-emerald-400">{term.target_term}</span>
                    </div>
                    {term.notes && (
                      <div className="text-[10px] text-slate-500 mt-0.5">{term.notes}</div>
                    )}
                  </div>
                  <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-slate-800 text-slate-400 border border-slate-700">
                    {term.category || 'IT'}
                  </span>
                </div>
              ))
            ) : (
              <div className="text-xs text-slate-500 text-center py-6">No terms added yet.</div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
