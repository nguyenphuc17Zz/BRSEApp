import { 
  Languages, 
  LayoutDashboard, 
  FolderKanban, 
  BookA, 
  Database, 
  History as HistoryIcon, 
  Cpu, 
  Settings as SettingsIcon,
  Sparkles,
  CheckCircle2,
  AlertCircle,
  FileText,
  Cloud,
  Brain,
  GitCompare,
  Users,
  MessageCircle
} from 'lucide-react';
import { Project } from '../types';

interface SidebarProps {
  currentTab: string;
  setCurrentTab: (tab: string) => void;
  projects: Project[];
  activeProject: Project | null;
  setActiveProject: (p: Project | null) => void;
  isBackendHealthy: boolean;
}

export const Sidebar: React.FC<SidebarProps> = ({
  currentTab,
  setCurrentTab,
  projects,
  activeProject,
  setActiveProject,
  isBackendHealthy
}) => {
  const navItems = [
    { id: 'brse-dashboard', label: 'BrSE Workspace', icon: Brain, badge: 'Phase 4' },
    { id: 'project-brain', label: 'Project Brain & RAG', icon: GitCompare },
    { id: 'translator', label: 'Translator', icon: Languages, badge: 'Phase 1' },
    { id: 'documents', label: 'Documents', icon: FileText, badge: 'Phase 2' },
    { id: 'integrations', label: 'Integrations', icon: Cloud, badge: 'Phase 3' },
    { id: 'meetings', label: 'Meeting Minutes', icon: Users },
    { id: 'line-chat', label: 'LINE Workspace', icon: MessageCircle },
    { id: 'dashboard', label: 'Dashboard', icon: LayoutDashboard },
    { id: 'projects', label: 'Projects', icon: FolderKanban, count: projects.length },
    { id: 'glossary', label: 'Glossary', icon: BookA },
    { id: 'memory', label: 'Translation Memory', icon: Database },
    { id: 'history', label: 'History & Logs', icon: HistoryIcon },
    { id: 'providers', label: 'AI Providers', icon: Cpu },
    { id: 'settings', label: 'Settings', icon: SettingsIcon },
  ];

  return (
    <aside className="w-64 bg-slate-900 border-r border-slate-800 flex flex-col h-screen select-none">
      {/* Brand Header */}
      <div className="p-4 border-b border-slate-800 flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-tr from-sky-600 to-indigo-500 flex items-center justify-center text-white shadow-lg shadow-sky-500/20">
            <Sparkles className="w-4 h-4" />
          </div>
          <div>
            <h1 className="font-semibold text-sm tracking-tight text-white flex items-center gap-1.5">
              Comtor Copilot
              <span className="text-[10px] uppercase font-bold tracking-wider px-1 py-0.2 rounded bg-sky-500/20 text-sky-400 border border-sky-500/30">
                Phase 3
              </span>
            </h1>
            <p className="text-[11px] text-slate-400">BrSE Translation Engine</p>
          </div>
        </div>
      </div>

      {/* Active Project Switcher */}
      <div className="px-3 py-3 border-b border-slate-800/80 bg-slate-950/40">
        <label className="text-[10px] font-semibold uppercase tracking-wider text-slate-400 px-1 mb-1 block">
          Active Project Workspace
        </label>
        <select
          value={activeProject?.id || ''}
          onChange={(e) => {
            const found = projects.find(p => p.id === e.target.value);
            setActiveProject(found || null);
          }}
          className="w-full bg-slate-850 text-xs font-medium text-slate-200 border border-slate-700/80 rounded-md px-2.5 py-1.5 focus:outline-none focus:border-sky-500 transition-colors"
        >
          <option value="">-- No Project (Global Context) --</option>
          {projects.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name} ({p.code})
            </option>
          ))}
        </select>
      </div>

      {/* Navigation Links */}
      <nav className="flex-1 px-2.5 py-3 space-y-1 overflow-y-auto">
        {navItems.map((item) => {
          const Icon = item.icon;
          const isActive = currentTab === item.id;
          return (
            <button
              key={item.id}
              onClick={() => setCurrentTab(item.id)}
              className={`w-full flex items-center justify-between px-3 py-2 rounded-md text-xs font-medium transition-all ${
                isActive
                  ? 'bg-sky-600 text-white shadow-md shadow-sky-600/25'
                  : 'text-slate-300 hover:bg-slate-800/80 hover:text-white'
              }`}
            >
              <div className="flex items-center gap-2.5">
                <Icon className={`w-4 h-4 ${isActive ? 'text-white' : 'text-slate-400'}`} />
                <span>{item.label}</span>
              </div>
              {item.badge && (
                <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded ${
                  isActive ? 'bg-sky-700 text-white' : 'bg-slate-800 text-sky-400'
                }`}>
                  {item.badge}
                </span>
              )}
              {item.count !== undefined && (
                <span className="text-[11px] text-slate-400 font-mono">
                  {item.count}
                </span>
              )}
            </button>
          );
        })}
      </nav>

      {/* Backend & Local Engine Status Footer */}
      <div className="p-3 border-t border-slate-800 bg-slate-950/60 flex items-center justify-between text-[11px]">
        <div className="flex items-center gap-2">
          {isBackendHealthy ? (
            <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
          ) : (
            <AlertCircle className="w-3.5 h-3.5 text-amber-400 animate-pulse" />
          )}
          <span className="text-slate-400">
            Service: {isBackendHealthy ? <span className="text-emerald-400 font-medium">127.0.0.1:8000</span> : <span className="text-amber-400 font-medium">Connecting...</span>}
          </span>
        </div>
        <span className="text-[10px] text-slate-500 font-mono">v1.0.0</span>
      </div>
    </aside>
  );
};
