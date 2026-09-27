import React from 'react';
import { HashRouter, Routes, Route, Navigate } from 'react-router-dom';
import { Project } from '../../types';
import { QAOverviewPage } from './QAOverviewPage';
import { RequirementListPage } from './RequirementListPage';
import { RequirementDetailPage } from './RequirementDetailPage';
import { TestCaseListPage } from './TestCaseListPage';
import { TestRunListPage } from './TestRunListPage';
import { TestRunDetailPage } from './TestRunDetailPage';
import { BugListPage } from './BugListPage';
import { BugDetailPage } from './BugDetailPage';
import { APITestsPage } from './APITestsPage';
import { APITestDetailPage } from './APITestDetailPage';
import { UITestsPage } from './UITestsPage';
import { UITestDetailPage } from './UITestDetailPage';
import { UIMappingsPage } from './UIMappingsPage';
import { ChangeListPage } from './ChangeListPage';
import { ChangeDetailPage } from './ChangeDetailPage';
import { RegressionPlannerPage } from './RegressionPlannerPage';
import { DataJobsPage } from './DataJobsPage';
import { DataJobDetailPage } from './DataJobDetailPage';
import { DataSourcesPage } from './DataSourcesPage';
import { CoveragePage } from './CoveragePage';

interface Props {
  activeProject: Project | null;
  projects: Project[];
  setActiveProject: (p: Project | null) => void;
}

/**
 * QA Workspace shell. Uses HashRouter so requirement detail pages are
 * deep-linkable (#/qa/requirements/:id) without touching the tab-state
 * navigation used by the rest of the app.
 */
export const QAWorkspace: React.FC<Props> = ({ activeProject, projects, setActiveProject }) => {
  void projects;
  void setActiveProject;
  return (
    <HashRouter>
      <Routes>
        <Route path="/qa/overview" element={<QAOverviewPage activeProject={activeProject} />} />
        <Route path="/qa/requirements" element={<RequirementListPage activeProject={activeProject} />} />
        <Route path="/qa/requirements/:id" element={<RequirementDetailPage activeProject={activeProject} />} />
        <Route path="/qa/test-cases" element={<TestCaseListPage activeProject={activeProject} />} />
        <Route path="/qa/test-runs" element={<TestRunListPage activeProject={activeProject} />} />
        <Route path="/qa/test-runs/:id" element={<TestRunDetailPage activeProject={activeProject} />} />
        <Route path="/qa/bugs" element={<BugListPage activeProject={activeProject} />} />
        <Route path="/qa/bugs/:id" element={<BugDetailPage activeProject={activeProject} />} />
        <Route path="/qa/api-tests" element={<APITestsPage activeProject={activeProject} />} />
        <Route path="/qa/api-tests/:id" element={<APITestDetailPage activeProject={activeProject} />} />
        <Route path="/qa/ui-tests" element={<UITestsPage activeProject={activeProject} />} />
        <Route path="/qa/ui-tests/:id" element={<UITestDetailPage activeProject={activeProject} />} />
        <Route path="/qa/ui-mappings" element={<UIMappingsPage activeProject={activeProject} />} />
        <Route path="/qa/changes" element={<ChangeListPage activeProject={activeProject} />} />
        <Route path="/qa/changes/:id" element={<ChangeDetailPage activeProject={activeProject} />} />
        <Route path="/qa/regression" element={<RegressionPlannerPage activeProject={activeProject} />} />
        <Route path="/qa/data" element={<DataJobsPage activeProject={activeProject} />} />
        <Route path="/qa/data/:id" element={<DataJobDetailPage activeProject={activeProject} />} />
        <Route path="/qa/data-sources" element={<DataSourcesPage activeProject={activeProject} />} />
        <Route path="/qa/coverage" element={<CoveragePage activeProject={activeProject} />} />
        <Route path="*" element={<Navigate to="/qa/overview" replace />} />
      </Routes>
    </HashRouter>
  );
};
