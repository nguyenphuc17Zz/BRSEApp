import React from 'react';
import { 
  Sparkles, 
  PanelLeft,
  ChevronRight
} from 'lucide-react';
import { Project } from '../types';
import { ThemeToggle } from './ui/ThemeToggle';
import { Button } from './ui/Button';
import { Tooltip } from './ui/Tooltip';
import { ProjectSelectorDropdown } from './common/ProjectSelectorDropdown';

interface TopbarProps {
  currentTab: string;
  projects: Project[];
  activeProject: Project | null;
  setActiveProject: (p: Project | null) => void;
  isBackendHealthy: boolean;
  onOpenQuickTranslate: () => void;
  isSidebarCollapsed: boolean;
  setIsSidebarCollapsed: (collapsed: boolean | ((prev: boolean) => boolean)) => void;
}

const TAB_TITLES: Record<string, { group: string; title: string }> = {
  'qa': { group: 'QA Workspace', title: 'QA Workspace' },
  'brse-dashboard': { group: 'Workspace', title: 'BrSE Workspace' },
  'project-brain': { group: 'Workspace', title: 'Project Brain & RAG' },
  'meetings': { group: 'Workspace', title: 'Meeting Minutes' },
  'line-chat': { group: 'Workspace', title: 'LINE Workspace' },
  'translator': { group: 'Translation', title: 'Translator' },
  'documents': { group: 'Translation', title: 'Documents' },
  'projects': { group: 'Knowledge', title: 'Projects & Rules' },
  'glossary': { group: 'Knowledge', title: 'Terminology Glossary' },
  'memory': { group: 'Knowledge', title: 'Translation Memory' },
  'integrations': { group: 'Translation', title: 'Integrations' },
  'history': { group: 'System', title: 'History & Logs' },
  'providers': { group: 'System', title: 'AI Providers' },
  'settings': { group: 'System', title: 'Settings' },
};

export const Topbar: React.FC<TopbarProps> = ({
  currentTab,
  projects,
  activeProject,
  setActiveProject,
  isBackendHealthy,
  onOpenQuickTranslate,
  isSidebarCollapsed,
  setIsSidebarCollapsed,
}) => {
  const meta = TAB_TITLES[currentTab] || { group: 'Workspace', title: 'Workspace' };

  return (
    <header className="h-13 bg-surface/90 backdrop-blur-md border-b border-border-subtle px-4 sm:px-6 flex items-center justify-between gap-4 z-20 flex-shrink-0 transition-colors">
      {/* Left: Collapse toggle + Breadcrumbs */}
      <div className="flex items-center gap-3 min-w-0">
        <Tooltip
          content={isSidebarCollapsed ? 'Mở rộng sidebar (Ctrl+B)' : 'Thu gọn sidebar (Ctrl+B)'}
          side="bottom"
        >
          <button
            type="button"
            onClick={() => setIsSidebarCollapsed((prev) => !prev)}
            className="p-1.5 rounded-lg text-text-secondary hover:text-text-primary hover:bg-surface-hover border border-border-subtle active:scale-95 transition-all duration-150 cursor-pointer"
            title={isSidebarCollapsed ? 'Expand sidebar (Ctrl+B)' : 'Collapse sidebar (Ctrl+B)'}
            aria-label="Toggle sidebar"
          >
            <PanelLeft className="w-4 h-4" />
          </button>
        </Tooltip>

        <div className="flex items-center gap-1.5 text-xs text-text-muted truncate select-none">
          <span className="text-text-secondary font-medium hidden sm:inline">{meta.group}</span>
          <ChevronRight className="w-3.5 h-3.5 text-border-default hidden sm:inline" />
          <span className="font-semibold text-text-primary truncate">{meta.title}</span>
        </div>
      </div>

      {/* Right: Project Switcher Dropdown + Quick Translate + Health + Theme */}
      <div className="flex items-center gap-2.5 flex-shrink-0">
        {/* Floating Custom Project Selector */}
        <ProjectSelectorDropdown
          projects={projects}
          activeProject={activeProject}
          onSelectProject={setActiveProject}
        />

        {/* Quick Translate Button */}
        <Tooltip content="Dịch nhanh (Ctrl+Shift+T)" side="bottom">
          <Button
            variant="subtle"
            size="sm"
            onClick={onOpenQuickTranslate}
            leftIcon={<Sparkles className="w-3.5 h-3.5" />}
            className="hidden sm:inline-flex"
          >
            Quick Translate
          </Button>
        </Tooltip>

        {/* Backend status indicator */}
        <div
          className={`flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-[11px] font-medium border transition-colors select-none ${
            isBackendHealthy
              ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/20'
              : 'bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/20 animate-pulse'
          }`}
          title={isBackendHealthy ? 'Backend service connected (127.0.0.1:8000)' : 'Reconnecting to backend service...'}
        >
          <span
            className={`w-1.5 h-1.5 rounded-full ${
              isBackendHealthy ? 'bg-emerald-500' : 'bg-amber-500'
            }`}
          />
          <span className="hidden md:inline font-mono">
            {isBackendHealthy ? 'API Online' : 'Connecting'}
          </span>
        </div>

        {/* Theme Toggle */}
        <ThemeToggle compact />
      </div>
    </header>
  );
};
