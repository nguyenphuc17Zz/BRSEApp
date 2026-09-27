import React, { useState, useEffect } from 'react';
import { Sidebar } from './components/Sidebar';
import { Topbar } from './components/Topbar';
import { TranslatorPage } from './pages/TranslatorPage';
import { DocumentsPage } from './pages/DocumentsPage';
import { IntegrationsPage } from './pages/IntegrationsPage';
import { QuickTranslateModal } from './pages/QuickTranslateModal';
import { BrSEDashboardPage } from './pages/BrSEDashboardPage';
import { ProjectBrainPage } from './pages/ProjectBrainPage';
import { MeetingsPage } from './pages/MeetingsPage';
import { ReportsPage } from './pages/ReportsPage';
import { LineSmartPage } from './pages/LineSmartPage';
import { ProjectsPage } from './pages/ProjectsPage';
import { GlossaryPage } from './pages/GlossaryPage';
import { MemoryPage } from './pages/MemoryPage';
import { HistoryPage } from './pages/HistoryPage';
import { ProvidersPage } from './pages/ProvidersPage';
import { SettingsPage } from './pages/SettingsPage';
import { QAWorkspace } from './pages/qa/QAWorkspace';
import { apiClient } from './api/client';
import { Project } from './types';
import { ThemeProvider } from './context/ThemeContext';
import { ToastProvider } from './context/ToastContext';
import { ConfirmDialogProvider } from './context/ConfirmDialogContext';
import { LoadingBarProvider } from './context/LoadingBarContext';
import { getSavedProjectId, saveActiveProjectId } from './utils/aiPreferences';

export const AppContent: React.FC = () => {
  const [currentTab, setCurrentTab] = useState('brse-dashboard');
  const [projects, setProjects] = useState<Project[]>([]);
  const [activeProject, setActiveProject] = useState<Project | null>(null);
  const [isBackendHealthy, setIsBackendHealthy] = useState(false);
  const [isQuickTranslateOpen, setIsQuickTranslateOpen] = useState(false);
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false);
  const [qaRoute, setQaRoute] = useState<string>(() => {
    const h = window.location.hash.replace(/^#/, '');
    return h.startsWith('/qa') ? h : '/qa/overview';
  });

  // Deep-link: opening #/qa/... selects the QA Workspace tab
  useEffect(() => {
    const syncHash = () => {
      const h = window.location.hash.replace(/^#/, '');
      if (h.startsWith('/qa')) {
        setQaRoute(h);
        setCurrentTab('qa');
      }
    };
    syncHash();
    window.addEventListener('hashchange', syncHash);
    return () => window.removeEventListener('hashchange', syncHash);
  }, []);

  const handleNavigateQA = (path: string) => {
    setCurrentTab('qa');
    setQaRoute(path);
    if (window.location.hash !== `#${path}`) {
      window.location.hash = `#${path}`;
    }
  };

  const handleSetActiveProject = (p: Project | null) => {
    setActiveProject(p);
    saveActiveProjectId(p?.id || null);
  };

  useEffect(() => {
    loadProjects();
    checkHealth();
    const interval = setInterval(checkHealth, 15000);
    return () => clearInterval(interval);
  }, []);

  const checkHealth = async () => {
    try {
      await apiClient.checkHealth();
      setIsBackendHealthy(true);
    } catch {
      setIsBackendHealthy(false);
    }
  };

  const loadProjects = async () => {
    try {
      const list = await apiClient.getProjects();
      setProjects(list);
      const savedId = getSavedProjectId();
      const savedProject = list.find((p) => p.id === savedId);
      if (savedProject) {
        setActiveProject(savedProject);
      } else if (list.length > 0 && !activeProject) {
        setActiveProject(list[0]);
        saveActiveProjectId(list[0].id);
      }
    } catch (e) {
      console.error('Failed to load projects:', e);
    }
  };

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-canvas text-primary font-sans antialiased">
      <Sidebar
        currentTab={currentTab}
        setCurrentTab={setCurrentTab}
        projects={projects}
        activeProject={activeProject}
        setActiveProject={handleSetActiveProject}
        isBackendHealthy={isBackendHealthy}
        isCollapsed={isSidebarCollapsed}
        setIsCollapsed={setIsSidebarCollapsed}
        qaRoute={qaRoute}
        onNavigateQA={handleNavigateQA}
      />

      <div className="flex-1 flex flex-col h-screen overflow-hidden min-w-0">
        <Topbar
          currentTab={currentTab}
          projects={projects}
          activeProject={activeProject}
          setActiveProject={handleSetActiveProject}
          isBackendHealthy={isBackendHealthy}
          onOpenQuickTranslate={() => setIsQuickTranslateOpen(true)}
          isSidebarCollapsed={isSidebarCollapsed}
          setIsSidebarCollapsed={setIsSidebarCollapsed}
        />

        <main className="flex-1 flex flex-col overflow-hidden bg-canvas min-w-0">
          {currentTab === 'brse-dashboard' && (
            <BrSEDashboardPage
              activeProject={activeProject}
              projects={projects}
              setActiveProject={handleSetActiveProject}
              onNavigateTab={setCurrentTab}
            />
          )}

          {currentTab === 'project-brain' && (
            <ProjectBrainPage
              activeProject={activeProject}
              projects={projects}
              setActiveProject={handleSetActiveProject}
            />
          )}

          {currentTab === 'meetings' && (
            <MeetingsPage
              activeProject={activeProject}
              projects={projects}
              setActiveProject={handleSetActiveProject}
            />
          )}

          {currentTab === 'reports' && (
            <ReportsPage
              activeProject={activeProject}
              projects={projects}
              setActiveProject={handleSetActiveProject}
            />
          )}

          {currentTab === 'line-chat' && (
            <LineSmartPage
              activeProject={activeProject}
              onNavigateToBrSE={() => setCurrentTab('brse-dashboard')}
            />
          )}

          {currentTab === 'translator' && (
            <TranslatorPage
              activeProject={activeProject}
              projects={projects}
              setActiveProject={handleSetActiveProject}
            />
          )}

          {currentTab === 'documents' && (
            <DocumentsPage
              activeProject={activeProject}
              projects={projects}
            />
          )}

          {currentTab === 'integrations' && (
            <IntegrationsPage
              activeProject={activeProject}
              projects={projects}
              onOpenQuickTranslate={() => setIsQuickTranslateOpen(true)}
            />
          )}

          {currentTab === 'projects' && (
            <ProjectsPage
              projects={projects}
              activeProject={activeProject}
              setActiveProject={handleSetActiveProject}
              refreshProjects={loadProjects}
            />
          )}

          {currentTab === 'glossary' && (
            <GlossaryPage
              activeProject={activeProject}
              projects={projects}
            />
          )}

          {currentTab === 'memory' && (
            <MemoryPage
              activeProject={activeProject}
            />
          )}

          {currentTab === 'history' && (
            <HistoryPage
              activeProject={activeProject}
            />
          )}

          {currentTab === 'qa' && (
            <QAWorkspace
              activeProject={activeProject}
              projects={projects}
              setActiveProject={handleSetActiveProject}
            />
          )}

          {currentTab === 'providers' && (
            <ProvidersPage />
          )}

          {currentTab === 'settings' && (
            <SettingsPage />
          )}
        </main>
      </div>

      <QuickTranslateModal
        isOpen={isQuickTranslateOpen}
        onClose={() => setIsQuickTranslateOpen(false)}
        activeProject={activeProject}
        projects={projects}
      />
    </div>
  );
};

export const App: React.FC = () => {
  return (
    <ThemeProvider>
      <LoadingBarProvider>
        <ToastProvider>
          <ConfirmDialogProvider>
            <AppContent />
          </ConfirmDialogProvider>
        </ToastProvider>
      </LoadingBarProvider>
    </ThemeProvider>
  );
};

export default App;

