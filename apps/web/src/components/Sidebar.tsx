import React, { useEffect, useState } from 'react';
import {
  Languages,
  FolderKanban,
  BookA,
  Database,
  History as HistoryIcon,
  Cpu,
  Settings as SettingsIcon,
  Sparkles,
  FileText,
  Cloud,
  Brain,
  GitCompare,
  Users,
  MessageCircle,
  ChevronLeft,
  ChevronRight,
  ChevronDown,
  PanelLeftOpen,
  PanelLeftClose,
  ShieldCheck,
  FileSearch,
  FlaskConical,
  PlayCircle,
  Bug as BugIcon,
  Zap,
  Monitor,
  MousePointer2,
  GitBranch,
  ClipboardList,
  Table2,
  FileSpreadsheet
} from 'lucide-react';
import { Project } from '../types';
import { Tooltip } from './ui/Tooltip';

interface SidebarProps {
  currentTab: string;
  setCurrentTab: (tab: string) => void;
  projects: Project[];
  activeProject: Project | null;
  setActiveProject: (p: Project | null) => void;
  isBackendHealthy: boolean;
  isCollapsed?: boolean;
  setIsCollapsed?: (collapsed: boolean | ((prev: boolean) => boolean)) => void;
  qaRoute?: string;
  onNavigateQA?: (path: string) => void;
}

interface NavSection {
  title: string;
  items: {
    id: string;
    label: string;
    icon: any;
    count?: number;
  }[];
}

export const Sidebar: React.FC<SidebarProps> = ({
  currentTab,
  setCurrentTab,
  projects,
  isBackendHealthy,
  isCollapsed = false,
  setIsCollapsed,
  qaRoute = '/qa/overview',
  onNavigateQA,
}) => {
  // Global Ctrl+B / Cmd+B keyboard shortcut to toggle sidebar collapse
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'b') {
        const tag = (e.target as HTMLElement)?.tagName?.toLowerCase();
        if (tag !== 'input' && tag !== 'textarea') {
          e.preventDefault();
          setIsCollapsed?.((prev) => !prev);
        }
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [setIsCollapsed]);

  // Section collapse state with localStorage persistence
  const [collapsedSections, setCollapsedSections] = useState<Record<string, boolean>>(() => {
    try {
      const saved = localStorage.getItem('sidebar_collapsed_sections');
      return saved ? JSON.parse(saved) : {};
    } catch {
      return {};
    }
  });

  const toggleSection = (title: string) => {
    setCollapsedSections((prev) => {
      const next = { ...prev, [title]: !prev[title] };
      try {
        localStorage.setItem('sidebar_collapsed_sections', JSON.stringify(next));
      } catch (err) {
        console.error('Failed to save sidebar_collapsed_sections', err);
      }
      return next;
    });
  };

  const navSections: NavSection[] = [
    {
      title: 'Workspace',
      items: [
        { id: 'brse-dashboard', label: 'BrSE Workspace', icon: Brain },
        { id: 'project-brain', label: 'Project Brain & RAG', icon: GitCompare },
        { id: 'meetings', label: 'Meeting Minutes', icon: Users },
        { id: 'reports', label: 'Báo cáo Tiến độ', icon: FileSpreadsheet },
        { id: 'line-chat', label: 'LINE Workspace', icon: MessageCircle },
      ],
    },
    {
      title: 'QA Workspace',
      items: [
        { id: 'qa:/qa/overview', label: 'QA Overview', icon: ShieldCheck },
        { id: 'qa:/qa/requirements', label: 'Requirement Review', icon: FileSearch },
        { id: 'qa:/qa/test-cases', label: 'Test Cases', icon: FlaskConical },
        { id: 'qa:/qa/test-runs', label: 'Test Runs', icon: PlayCircle },
        { id: 'qa:/qa/api-tests', label: 'API Tests', icon: Zap },
        { id: 'qa:/qa/ui-tests', label: 'UI Tests', icon: Monitor },
        { id: 'qa:/qa/ui-mappings', label: 'UI Mappings', icon: MousePointer2 },
        { id: 'qa:/qa/changes', label: 'Changes', icon: GitBranch },
        { id: 'qa:/qa/regression', label: 'Regression', icon: ClipboardList },
        { id: 'qa:/qa/data', label: 'Data QA', icon: Table2 },
        { id: 'qa:/qa/bugs', label: 'Bugs', icon: BugIcon },
        { id: 'qa:/qa/coverage', label: 'Coverage', icon: GitCompare },
      ],
    },
    {
      title: 'Translation',
      items: [
        { id: 'translator', label: 'Translator', icon: Languages },
        { id: 'documents', label: 'Documents', icon: FileText },
        { id: 'integrations', label: 'Integrations', icon: Cloud },
      ],
    },
    {
      title: 'Knowledge',
      items: [
        { id: 'projects', label: 'Projects & Rules', icon: FolderKanban, count: projects.length },
        { id: 'glossary', label: 'Glossary Terms', icon: BookA },
        { id: 'memory', label: 'Translation Memory', icon: Database },
      ],
    },
    {
      title: 'System',
      items: [
        { id: 'history', label: 'History & Logs', icon: HistoryIcon },
        { id: 'providers', label: 'AI Providers', icon: Cpu },
        { id: 'settings', label: 'Settings', icon: SettingsIcon },
      ],
    },
  ];

  return (
    <aside
      className={`h-screen flex flex-col bg-surface border-r border-border-subtle transition-all duration-200 ease-[cubic-bezier(0.16,1,0.3,1)] select-none z-30 flex-shrink-0 ${
        isCollapsed ? 'w-16' : 'w-60'
      }`}
    >
      {/* Brand Header */}
      <div
        className={`h-13 flex items-center border-b border-border-subtle flex-shrink-0 ${
          isCollapsed ? 'justify-center px-2' : 'justify-between px-3.5'
        }`}
      >
        {isCollapsed ? (
          // In Collapsed Mode: Prominent, clear Expand Button with high visual affordance
          setIsCollapsed && (
            <Tooltip content="Mở rộng thanh điều hướng (Ctrl+B)" side="right">
              <button
                type="button"
                onClick={() => setIsCollapsed(false)}
                className="w-10 h-10 rounded-xl bg-surface-subtle hover:bg-surface-hover hover:border-primary/40 border border-border-default text-text-secondary hover:text-text-primary flex items-center justify-center transition-all duration-150 active:scale-90 cursor-pointer shadow-xs group"
                aria-label="Expand sidebar"
                title="Mở rộng thanh điều hướng (Ctrl+B)"
              >
                <PanelLeftOpen className="w-4 h-4 text-primary group-hover:scale-110 transition-transform duration-150" />
              </button>
            </Tooltip>
          )
        ) : (
          // In Expanded Mode: App Brand Title + Collapse Button
          <>
            <div className="flex items-center gap-2.5 overflow-hidden">
              <div className="w-8 h-8 rounded-lg bg-gradient-to-tr from-sky-500 to-indigo-600 flex items-center justify-center text-white shadow-sm flex-shrink-0">
                <Sparkles className="w-4 h-4" />
              </div>
              <div className="min-w-0">
                <h1 className="font-bold text-xs tracking-tight text-text-primary truncate">
                  Comtor Copilot
                </h1>
                <p className="text-[10px] text-text-muted truncate font-mono">BrSE Intelligence</p>
              </div>
            </div>

            {setIsCollapsed && (
              <Tooltip content="Thu gọn thanh điều hướng (Ctrl+B)" side="bottom">
                <button
                  type="button"
                  onClick={() => setIsCollapsed(true)}
                  className="p-1.5 rounded-lg text-text-muted hover:text-text-primary hover:bg-surface-hover active:scale-90 transition-all duration-150 ease-[cubic-bezier(0.16,1,0.3,1)] cursor-pointer border border-transparent hover:border-border-subtle"
                  aria-label="Collapse sidebar"
                  title="Thu gọn (Ctrl+B)"
                >
                  <PanelLeftClose className="w-4 h-4" />
                </button>
              </Tooltip>
            )}
          </>
        )}
      </div>

      {/* Navigation Sections */}
      <div className="flex-1 px-2.5 py-3 overflow-y-auto space-y-3">
        {navSections.map((sec, secIdx) => {
          const isSectionCollapsed = !!collapsedSections[sec.title];
          const hasActiveItem = sec.items.some((item) => {
            const isQaItem = item.id.startsWith('qa:');
            const qaPath = isQaItem ? item.id.slice(3) : '';
            return isQaItem
              ? currentTab === 'qa' && (qaRoute === qaPath || (qaPath !== '/qa/overview' && qaRoute.startsWith(qaPath)))
              : currentTab === item.id;
          });

          return (
            <div key={secIdx} className="space-y-1">
              {!isCollapsed && (
                <button
                  type="button"
                  onClick={() => toggleSection(sec.title)}
                  className="w-full flex items-center justify-between px-2 py-1 rounded-md text-[10px] uppercase font-semibold text-text-muted hover:text-text-primary hover:bg-surface-hover/60 transition-all duration-150 cursor-pointer group select-none"
                  title={isSectionCollapsed ? `Mở rộng nhóm ${sec.title}` : `Thu gọn nhóm ${sec.title}`}
                >
                  <div className="flex items-center gap-1.5">
                    <span className="tracking-wider">{sec.title}</span>
                    {isSectionCollapsed && hasActiveItem && (
                      <span className="w-1.5 h-1.5 rounded-full bg-primary" title="Có mục đang mở trong nhóm này" />
                    )}
                  </div>
                  <ChevronDown
                    className={`w-3 h-3 text-text-muted group-hover:text-text-primary transition-transform duration-200 ${
                      isSectionCollapsed ? '-rotate-90' : 'rotate-0'
                    }`}
                  />
                </button>
              )}

              {/* Items List (Collapsible in expanded mode) */}
              {(!isSectionCollapsed || isCollapsed) && (
                <div className="space-y-0.5">
                  {sec.items.map((item) => {
                const Icon = item.icon;
                const isQaItem = item.id.startsWith('qa:');
                const qaPath = isQaItem ? item.id.slice(3) : '';
                const isActive = isQaItem
                  ? currentTab === 'qa' && (qaRoute === qaPath || (qaPath !== '/qa/overview' && qaRoute.startsWith(qaPath)))
                  : currentTab === item.id;

                const navButton = (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => {
                      if (isQaItem) {
                        onNavigateQA ? onNavigateQA(qaPath) : setCurrentTab('qa');
                      } else {
                        setCurrentTab(item.id);
                      }
                    }}
                    className={`w-full relative flex items-center ${
                      isCollapsed ? 'justify-center px-0 py-2.5' : 'justify-between px-2.5 py-1.5'
                    } rounded-lg text-xs font-medium transition-all duration-150 ease-[cubic-bezier(0.16,1,0.3,1)] active:scale-[0.98] cursor-pointer ${
                      isActive
                        ? 'bg-primary/10 text-primary font-semibold shadow-2xs before:content-[""] before:absolute before:left-0 before:top-1.5 before:bottom-1.5 before:w-1 before:rounded-r-full before:bg-primary'
                        : 'text-text-secondary hover:text-text-primary hover:bg-surface-hover'
                    }`}
                  >
                    <div className="flex items-center gap-2.5 min-w-0">
                      <Icon
                        className={`w-4 h-4 flex-shrink-0 transition-colors ${
                          isActive ? 'text-primary' : 'text-text-muted group-hover:text-text-primary'
                        }`}
                      />
                      {!isCollapsed && <span className="truncate">{item.label}</span>}
                    </div>
                    {!isCollapsed && item.count !== undefined && (
                      <span className="text-[10px] text-text-muted font-mono bg-surface-subtle px-1.5 py-0.5 rounded border border-border-subtle">
                        {item.count}
                      </span>
                    )}
                  </button>
                );

                if (isCollapsed) {
                  return (
                    <Tooltip key={item.id} content={item.label} side="right">
                      {navButton}
                    </Tooltip>
                  );
                }

                return navButton;
              })}
            </div>
          )}
        </div>
      );
    })}
  </div>

      {/* Footer Info & Expand Button */}
      <div className="p-3 border-t border-border-subtle bg-surface-subtle/50 flex items-center justify-between text-[11px] flex-shrink-0">
        {!isCollapsed ? (
          <>
            <div className="flex items-center gap-1.5 text-text-muted">
              <span
                className={`w-2 h-2 rounded-full ${
                  isBackendHealthy ? 'bg-emerald-500' : 'bg-amber-500 animate-pulse'
                }`}
              />
              <span className="font-mono text-[10px]">
                {isBackendHealthy ? '127.0.0.1:8000' : 'Offline'}
              </span>
            </div>
            <span className="text-[10px] text-text-muted font-mono">v1.2.0</span>
          </>
        ) : (
          <div className="w-full flex justify-center">
            {setIsCollapsed && (
              <Tooltip content="Mở rộng (Ctrl+B)" side="right">
                <button
                  type="button"
                  onClick={() => setIsCollapsed(false)}
                  className="p-1.5 rounded-lg text-text-muted hover:text-text-primary hover:bg-surface-hover active:scale-90 transition-colors cursor-pointer"
                  title="Expand sidebar (Ctrl+B)"
                  aria-label="Expand sidebar"
                >
                  <ChevronRight className="w-4 h-4" />
                </button>
              </Tooltip>
            )}
          </div>
        )}
      </div>
    </aside>
  );
};
