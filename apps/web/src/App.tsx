import React, { useState, useEffect } from 'react';
import { Sidebar } from './components/Sidebar';
import { TranslatorPage } from './pages/TranslatorPage';
import { DocumentsPage } from './pages/DocumentsPage';
import { IntegrationsPage } from './pages/IntegrationsPage';
import { QuickTranslateModal } from './pages/QuickTranslateModal';
import { BrSEDashboardPage } from './pages/BrSEDashboardPage';
import { ProjectBrainPage } from './pages/ProjectBrainPage';
import { MeetingsPage } from './pages/MeetingsPage';
import { LineSmartPage } from './pages/LineSmartPage';
import { DashboardPage } from './pages/DashboardPage';
import { ProjectsPage } from './pages/ProjectsPage';
import { GlossaryPage } from './pages/GlossaryPage';
import { MemoryPage } from './pages/MemoryPage';
import { HistoryPage } from './pages/HistoryPage';
import { ProvidersPage } from './pages/ProvidersPage';
import { SettingsPage } from './pages/SettingsPage';
import { apiClient } from './api/client';
import { Project } from './types';
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
        // Set first project (e.g. ABC Banking) as active by default if none saved
        setActiveProject(list[0]);
        saveActiveProjectId(list[0].id);
      }
    } catch (e) {
      console.error('Failed to load projects:', e);
    }
  };

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-slate-950 font-sans text-slate-100">
      <Sidebar
        currentTab={currentTab}
        setCurrentTab={setCurrentTab}
        projects={projects}
        activeProject={activeProject}
        setActiveProject={handleSetActiveProject}
        isBackendHealthy={isBackendHealthy}
      />

      <main className="flex-1 flex flex-col h-screen overflow-hidden">
        {currentTab === 'brse-dashboard' && (
          <BrSEDashboardPage
            activeProject={activeProject}
            projects={projects}
            setActiveProject={handleSetActiveProject}
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

        {currentTab === 'dashboard' && (
          <DashboardPage
            activeProject={activeProject}
            setCurrentTab={setCurrentTab}
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

        {currentTab === 'providers' && (
          <ProvidersPage />
        )}

        {currentTab === 'settings' && (
          <SettingsPage />
        )}
      </main>

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
    <LoadingBarProvider>
      <ToastProvider>
        <ConfirmDialogProvider>
          <AppContent />
        </ConfirmDialogProvider>
      </ToastProvider>
    </LoadingBarProvider>
  );
};

export default App;
