import axios from 'axios';
import {
  TranslationRequest,
  TranslationResponse,
  Project,
  GlossaryTerm,
  TranslationMemoryItem,
  HistoryItem,
  ProviderInfo,
  ProjectStakeholder,
  StakeholderCreatePayload,
  LineMessageItem
} from '../types';

import { notifyLoadingStart, notifyLoadingFinish } from '../context/LoadingBarContext';

const API_BASE_URL = 'http://127.0.0.1:8000/api';

export const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

api.interceptors.request.use(
  (config) => {
    notifyLoadingStart();
    return config;
  },
  (error) => {
    notifyLoadingFinish();
    return Promise.reject(error);
  }
);

api.interceptors.response.use(
  (response) => {
    notifyLoadingFinish();
    return response;
  },
  (error) => {
    notifyLoadingFinish();
    return Promise.reject(error);
  }
);

export const apiClient = {
  // Translate & AI Ops
  translate: async (req: TranslationRequest): Promise<TranslationResponse> => {
    const res = await api.post('/translate', req);
    return res.data;
  },

  explain: async (source_text: string, translation_text: string, project_id?: string, preferred_provider?: string, force_model?: string) => {
    const res = await api.post('/explain', { 
      source_text, 
      translation_text, 
      project_id,
      preferred_provider,
      force_model
    });
    return res.data;
  },

  reply: async (
    source_message: string, 
    history?: string[], 
    project_id?: string, 
    preferred_provider?: string, 
    force_model?: string,
    user_intent?: string
  ) => {
    const res = await api.post('/reply', { 
      source_message, 
      conversation_history: history, 
      project_id,
      preferred_provider,
      force_model,
      user_intent
    });
    return res.data;
  },

  rewrite: async (text: string, tone: string, project_id?: string, preferred_provider?: string, force_model?: string) => {
    const res = await api.post('/rewrite', { 
      text, 
      tone,
      project_id,
      preferred_provider,
      force_model
    });
    return res.data;
  },

  // Projects
  getProjects: async (): Promise<Project[]> => {
    const res = await api.get('/projects');
    return res.data;
  },

  createProject: async (data: { name: string; code: string; client_name?: string; description?: string; instructions?: string[] }): Promise<Project> => {
    const res = await api.post('/projects', data);
    return res.data;
  },

  deleteProject: async (id: string) => {
    const res = await api.delete(`/projects/${id}`);
    return res.data;
  },

  getProjectInstructions: async (projectId: string) => {
    const res = await api.get(`/projects/${projectId}/instructions`);
    return res.data;
  },

  addProjectInstruction: async (projectId: string, rule_text: string) => {
    const res = await api.post(`/projects/${projectId}/instructions`, { rule_text });
    return res.data;
  },

  deleteProjectInstruction: async (projectId: string, instructionId: string) => {
    const res = await api.delete(`/projects/${projectId}/instructions/${instructionId}`);
    return res.data;
  },

  // Glossary
  getGlossary: async (params?: { project_id?: string; search?: string; category?: string; scope?: string }): Promise<GlossaryTerm[]> => {
    const res = await api.get('/glossary', { params });
    return res.data;
  },

  createGlossaryTerm: async (term: Partial<GlossaryTerm>): Promise<GlossaryTerm> => {
    const res = await api.post('/glossary', term);
    return res.data;
  },

  updateGlossaryTerm: async (id: string, term: Partial<GlossaryTerm>): Promise<GlossaryTerm> => {
    const res = await api.patch(`/glossary/${id}`, term);
    return res.data;
  },

  deleteGlossaryTerm: async (id: string) => {
    const res = await api.delete(`/glossary/${id}`);
    return res.data;
  },

  deleteProjectGlossary: async (projectId: string): Promise<{ message: string; deleted_count: number }> => {
    const res = await api.delete(`/glossary/project/${projectId}`);
    return res.data;
  },

  // Translation Memory
  getTranslationMemory: async (params?: { project_id?: string; search?: string }): Promise<TranslationMemoryItem[]> => {
    const res = await api.get('/memory', { params });
    return res.data;
  },

  createTranslationMemory: async (item: Partial<TranslationMemoryItem>): Promise<TranslationMemoryItem> => {
    const res = await api.post('/memory', item);
    return res.data;
  },

  deleteTranslationMemory: async (id: string) => {
    const res = await api.delete(`/memory/${id}`);
    return res.data;
  },

  // History & Corrections
  getHistory: async (params?: { project_id?: string; search?: string }): Promise<HistoryItem[]> => {
    const res = await api.get('/history', { params });
    return res.data;
  },

  deleteHistoryItem: async (id: string) => {
    const res = await api.delete(`/history/${id}`);
    return res.data;
  },

  recordCorrection: async (data: {
    project_id?: string | null;
    source_text: string;
    original_translation: string;
    corrected_translation: string;
    apply_scope: string;
    context_note?: string;
    save_to_tm?: boolean;
  }) => {
    const res = await api.post('/history/corrections', data);
    return res.data;
  },

  // Providers
  getProviders: async (): Promise<ProviderInfo[]> => {
    const res = await api.get('/providers');
    return res.data;
  },

  updateProvider: async (name: string, data: Partial<ProviderInfo> & { api_key?: string }) => {
    const res = await api.patch(`/providers/${name}`, data);
    return res.data;
  },

  testProvider: async (name: string) => {
    const res = await api.post(`/providers/${name}/test`);
    return res.data;
  },

  refreshModels: async (name: string) => {
    const res = await api.post(`/providers/${name}/models/refresh`);
    return res.data;
  },

  refreshAllModels: async () => {
    const res = await api.post('/providers/models/refresh-all');
    return res.data;
  },

  // Health
  checkHealth: async () => {
    const res = await api.get('/health');
    return res.data;
  },

  // Document Translation
  uploadDocument: async (file: File, projectId?: string): Promise<any> => {
    const formData = new FormData();
    formData.append('file', file);
    if (projectId) {
      formData.append('project_id', projectId);
    }
    const res = await api.post('/documents/upload', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
    return res.data;
  },

  getDocuments: async (projectId?: string): Promise<any[]> => {
    const res = await api.get('/documents', { params: { project_id: projectId } });
    return res.data;
  },

  getDocument: async (id: string): Promise<any> => {
    const res = await api.get(`/documents/${id}`);
    return res.data;
  },

  deleteDocument: async (id: string): Promise<any> => {
    const res = await api.delete(`/documents/${id}`);
    return res.data;
  },

  deleteAllDocuments: async (projectId?: string, fileType?: string, docIds?: string[]): Promise<any> => {
    const payload: { project_id?: string; file_type?: string; doc_ids?: string[] } = {};
    if (projectId) payload.project_id = projectId;
    if (fileType && fileType !== 'all') payload.file_type = fileType;
    if (docIds && docIds.length > 0) payload.doc_ids = docIds;
    const res = await api.post('/documents/bulk-delete', payload);
    return res.data;
  },

  analyzeDocument: async (id: string): Promise<any> => {
    const res = await api.post(`/documents/${id}/analyze`);
    return res.data;
  },

  startDocumentTranslation: async (id: string, config: any): Promise<any> => {
    const res = await api.post(`/documents/${id}/translate`, config);
    return res.data;
  },

  getJob: async (jobId: string): Promise<any> => {
    const res = await api.get(`/documents/jobs/${jobId}`);
    return res.data;
  },

  pauseJob: async (jobId: string): Promise<any> => {
    const res = await api.post(`/documents/jobs/${jobId}/pause`);
    return res.data;
  },

  resumeJob: async (jobId: string): Promise<any> => {
    const res = await api.post(`/documents/jobs/${jobId}/resume`);
    return res.data;
  },

  cancelJob: async (jobId: string): Promise<any> => {
    const res = await api.post(`/documents/jobs/${jobId}/cancel`);
    return res.data;
  },

  retryJob: async (jobId: string): Promise<any> => {
    const res = await api.post(`/documents/jobs/${jobId}/retry`);
    return res.data;
  },

  getJobProgress: async (jobId: string): Promise<any> => {
    const res = await api.get(`/documents/jobs/${jobId}/progress`);
    return res.data;
  },

  openJobFolder: async (jobId: string): Promise<any> => {
    const res = await api.post(`/documents/jobs/${jobId}/open-folder`);
    return res.data;
  },

  browseDirectory: async (initialDir?: string): Promise<{ success: boolean; path: string; canceled: boolean; error?: string }> => {
    const res = await api.post('/documents/browse-directory', { initial_dir: initialDir });
    return res.data;
  },

  getCommonPaths: async (): Promise<{
    desktop: string;
    downloads: string;
    documents: string;
    default_output: string;
  }> => {
    const res = await api.get('/documents/common-paths');
    return res.data;
  },

  getJobIssues: async (jobId: string): Promise<any[]> => {
    const res = await api.get(`/documents/jobs/${jobId}/issues`);
    return res.data;
  },

  getJobSegments: async (jobId: string, limit: number = 100, offset: number = 0): Promise<{ total: number; segments: any[] }> => {
    const res = await api.get(`/documents/jobs/${jobId}/segments`, { params: { limit, offset } });
    return res.data;
  },

  updateSegment: async (jobId: string, segmentId: string, targetText: string): Promise<any> => {
    const res = await api.patch(`/documents/jobs/${jobId}/segments/${segmentId}`, { target_text: targetText });
    return res.data;
  },

  regenerateSegment: async (jobId: string, segmentId: string): Promise<any> => {
    const res = await api.post(`/documents/jobs/${jobId}/segments/${segmentId}/regenerate`);
    return res.data;
  },

  getDocumentDownloadUrl: (jobId: string): string => {
    return `${API_BASE_URL}/documents/jobs/${jobId}/output`;
  },

  // Workspace & Communication Integrations
  getIntegrationHealth: async (): Promise<any> => {
    const res = await api.get('/integrations/health');
    return res.data;
  },

  cleanIntegrationCache: async (allEntries: boolean = false): Promise<any> => {
    const res = await api.post('/integrations/cache/clean', null, { params: { all_entries: allEntries } });
    return res.data;
  },

  // Google Workspace
  getGoogleConfig: async (): Promise<{ is_configured: boolean; client_id_masked: string; project_id: string; redirect_uri: string }> => {
    const res = await api.get('/integrations/google/config');
    return res.data;
  },

  uploadGoogleCredentials: async (payload: any): Promise<any> => {
    const res = await api.post('/integrations/google/config/upload-credentials', payload);
    return res.data;
  },

  getGoogleLoginUrl: async (): Promise<{ auth_url: string }> => {
    const res = await api.get('/integrations/google/login-url');
    return res.data;
  },

  getGoogleAccounts: async (): Promise<any[]> => {
    const res = await api.get('/integrations/google/accounts');
    return res.data;
  },

  activateGoogleAccount: async (accountId: string): Promise<any> => {
    const res = await api.post(`/integrations/google/accounts/${accountId}/activate`);
    return res.data;
  },

  disconnectGoogleAccount: async (accountId: string): Promise<any> => {
    const res = await api.delete(`/integrations/google/accounts/${accountId}`);
    return res.data;
  },

  syncGoogleProfile: async (accountId?: string): Promise<any> => {
    const res = await api.post('/integrations/google/accounts/sync-profile', null, {
      params: { account_id: accountId }
    });
    return res.data;
  },

  connectGoogle: async (data: { client_id?: string; client_secret?: string; auth_code?: string; is_mock?: boolean }): Promise<any> => {
    const res = await api.post('/integrations/google/connect', data);
    return res.data;
  },

  disconnectGoogle: async (accountId?: string): Promise<any> => {
    const res = await api.post('/integrations/google/disconnect', null, { params: { account_id: accountId } });
    return res.data;
  },

  listGoogleDrive: async (
    folderId?: string,
    query?: string,
    accountId?: string,
    viewMode: string = 'my_drive'
  ): Promise<{ files: any[]; current_folder?: { id: string; name: string } | null; account_id?: string; account_email?: string; view_mode?: string }> => {
    const res = await api.get('/integrations/google/drive', {
      params: { folder_id: folderId, query, account_id: accountId, view_mode: viewMode }
    });
    return res.data;
  },

  getDriveFolderInfo: async (folderId: string, accountId?: string): Promise<{ id: string; name: string }> => {
    const res = await api.get(`/integrations/google/drive/folders/${folderId}`, { params: { account_id: accountId } });
    return res.data;
  },

  findExistingGoogleTranslation: async (fileId: string, targetLang: string = 'vi', accountId?: string): Promise<any> => {
    const params: any = { target_language: targetLang };
    if (accountId) params.account_id = accountId;
    const res = await api.get(`/integrations/google/drive/files/${fileId}/existing-translation`, { params });
    return res.data;
  },

  createDriveFolder: async (name: string, parentFolderId?: string, accountId?: string): Promise<any> => {
    const res = await api.post('/integrations/google/drive/folders', {
      name,
      parent_folder_id: parentFolderId,
      account_id: accountId
    });
    return res.data;
  },

  uploadDriveFile: async (file: File, parentFolderId?: string, accountId?: string): Promise<any> => {
    const formData = new FormData();
    formData.append('file', file);
    if (parentFolderId) {
      formData.append('parent_folder_id', parentFolderId);
    }
    if (accountId) {
      formData.append('account_id', accountId);
    }
    const res = await api.post('/integrations/google/drive/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    });
    return res.data;
  },

  renameDriveFile: async (fileId: string, newName: string, accountId?: string): Promise<any> => {
    const res = await api.patch(`/integrations/google/drive/files/${fileId}`, {
      new_name: newName,
      account_id: accountId
    });
    return res.data;
  },

  deleteDriveFile: async (fileId: string, accountId?: string): Promise<any> => {
    const res = await api.delete(`/integrations/google/drive/files/${fileId}`, {
      params: { account_id: accountId }
    });
    return res.data;
  },

  batchDeleteDriveFiles: async (fileIds: string[], accountId?: string): Promise<{ status: string, deleted_count: number, failed_count: number, failed_ids: string[] }> => {
    const res = await api.post('/integrations/google/drive/files/batch-delete', {
      file_ids: fileIds,
      account_id: accountId
    });
    return res.data;
  },

  downloadDriveFile: async (fileId: string, fallbackName?: string, accountId?: string): Promise<string> => {
    const res = await api.get(`/integrations/google/drive/files/${fileId}/download`, {
      params: { account_id: accountId },
      responseType: 'blob'
    });

    let filename = fallbackName || `drive_file_${fileId}`;
    const disposition = res.headers['content-disposition'] || res.headers['Content-Disposition'];
    if (disposition) {
      const matchUtf8 = disposition.match(/filename\*=UTF-8''([^;]+)/i);
      const matchStandard = disposition.match(/filename="?([^";]+)"?/i);
      if (matchUtf8 && matchUtf8[1]) {
        filename = decodeURIComponent(matchUtf8[1]);
      } else if (matchStandard && matchStandard[1]) {
        filename = decodeURIComponent(matchStandard[1]);
      }
    }

    const blob = new Blob([res.data]);
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    window.URL.revokeObjectURL(url);
    return filename;
  },

  downloadDriveFilesBatch: async (fileIds: string[], accountId?: string): Promise<string> => {
    const res = await api.post('/integrations/google/drive/files/batch-download', {
      file_ids: fileIds,
      account_id: accountId
    }, {
      responseType: 'blob'
    });

    let filename = `drive_download_${new Date().toISOString().slice(0, 10)}.zip`;
    const disposition = res.headers['content-disposition'] || res.headers['Content-Disposition'];
    if (disposition) {
      const matchUtf8 = disposition.match(/filename\*=UTF-8''([^;]+)/i);
      const matchStandard = disposition.match(/filename="?([^";]+)"?/i);
      if (matchUtf8 && matchUtf8[1]) {
        filename = decodeURIComponent(matchUtf8[1]);
      } else if (matchStandard && matchStandard[1]) {
        filename = decodeURIComponent(matchStandard[1]);
      }
    }

    const blob = new Blob([res.data]);
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    window.URL.revokeObjectURL(url);
    return filename;
  },

  translateGoogleDoc: async (fileId: string, config: any): Promise<any> => {
    const res = await api.post(`/integrations/google/docs/${fileId}/translate`, config);
    return res.data;
  },

  translateGoogleSheet: async (fileId: string, config: any): Promise<any> => {
    const res = await api.post(`/integrations/google/sheets/${fileId}/translate`, config);
    return res.data;
  },

  translateGoogleSlide: async (fileId: string, config: any): Promise<any> => {
    const res = await api.post(`/integrations/google/slides/${fileId}/translate`, config);
    return res.data;
  },

  getGoogleFileMeta: async (fileId: string, fileType: string, accountId?: string): Promise<any> => {
    const res = await api.get(`/integrations/google/files/${fileId}/meta`, { params: { file_type: fileType, account_id: accountId } });
    return res.data;
  },

  startGoogleTranslation: async (payload: any): Promise<any> => {
    const res = await api.post('/integrations/google/translate', payload);
    return res.data;
  },

  getGoogleJobProgress: async (jobId: string): Promise<any> => {
    const res = await api.get(`/integrations/google/jobs/${jobId}/progress`);
    return res.data;
  },

  pauseGoogleJob: async (jobId: string): Promise<any> => {
    const res = await api.post(`/integrations/google/jobs/${jobId}/pause`);
    return res.data;
  },

  resumeGoogleJob: async (jobId: string): Promise<any> => {
    const res = await api.post(`/integrations/google/jobs/${jobId}/resume`);
    return res.data;
  },

  cancelGoogleJob: async (jobId: string): Promise<any> => {
    const res = await api.post(`/integrations/google/jobs/${jobId}/cancel`);
    return res.data;
  },

  retryGoogleJob: async (jobId: string, data?: any): Promise<any> => {
    const res = await api.post(`/integrations/google/jobs/${jobId}/retry`, data || {});
    return res.data;
  },

  getGoogleJobSegments: async (jobId: string, limit: number = 100, offset: number = 0): Promise<any> => {
    const res = await api.get(`/integrations/google/jobs/${jobId}/segments`, { params: { limit, offset } });
    return res.data;
  },

  updateGoogleJobSegment: async (jobId: string, segmentId: string, data: any): Promise<any> => {
    const res = await api.patch(`/integrations/google/jobs/${jobId}/segments/${segmentId}`, data);
    return res.data;
  },

  regenerateGoogleJobSegment: async (jobId: string, segmentId: string): Promise<any> => {
    const res = await api.post(`/integrations/google/jobs/${jobId}/segments/${segmentId}/regenerate`);
    return res.data;
  },

  getGoogleJobIssues: async (jobId: string): Promise<any> => {
    const res = await api.get(`/integrations/google/jobs/${jobId}/issues`);
    return res.data;
  },

  // Slack
  connectSlack: async (data: { client_id?: string; client_secret?: string; auth_code?: string; bot_token?: string; is_mock?: boolean }): Promise<any> => {
    const res = await api.post('/integrations/slack/connect', data);
    return res.data;
  },

  disconnectSlack: async (): Promise<any> => {
    const res = await api.post('/integrations/slack/disconnect');
    return res.data;
  },

  listSlackChannels: async (): Promise<{ channels: any[] }> => {
    const res = await api.get('/integrations/slack/channels');
    return res.data;
  },

  getSlackMessages: async (channelId?: string): Promise<{ messages: any[] }> => {
    if (channelId) {
      const res = await api.get(`/integrations/slack/channels/${channelId}/messages`);
      return res.data;
    }
    const res = await api.get('/slack/messages');
    return res.data;
  },

  translateSlackMessage: async (payload: any): Promise<any> => {
    const res = await api.post('/integrations/slack/messages/translate', payload);
    return res.data;
  },

  generateSlackReply: async (payload: any): Promise<any> => {
    const res = await api.post('/integrations/slack/messages/reply', payload);
    return res.data;
  },

  getChannelMappings: async (): Promise<{ mappings: any[] }> => {
    const res = await api.get('/integrations/slack/mappings');
    return res.data;
  },

  createChannelMapping: async (data: any): Promise<any> => {
    const res = await api.post('/integrations/slack/mappings', data);
    return res.data;
  },

  // Windows Desktop Agent
  getDesktopStatus: async (): Promise<any> => {
    const res = await api.get('/integrations/desktop/status');
    return res.data;
  },

  getActiveWindow: async (): Promise<any> => {
    const res = await api.get('/integrations/desktop/active-window');
    return res.data;
  },

  quickTranslate: async (payload: { text?: string; target_language?: string; project_id?: string; style?: string; provider?: string; model?: string }): Promise<any> => {
    const res = await api.post('/integrations/desktop/quick-translate', payload);
    return res.data;
  },

  quickReply: async (payload: { text?: string; provider?: string; model?: string }): Promise<any> => {
    const res = await api.post('/integrations/desktop/quick-reply', payload);
    return res.data;
  },

  // BrSE Brain & Smart Workflow APIs
  getBrSEMetrics: async (project_id?: string): Promise<any> => {
    const res = await api.get('/brse-dashboard/metrics', { params: { project_id } });
    return res.data;
  },

  getWorkInbox: async (project_id?: string): Promise<any> => {
    const res = await api.get('/brse-dashboard/inbox', { params: { project_id } });
    return res.data;
  },

  generateDailySummary: async (
    project_id?: string, 
    summary_type: string = 'morning',
    preferred_provider?: string,
    model?: string,
    language?: string
  ): Promise<any> => {
    const res = await api.post('/brse-dashboard/generate-summary', { 
      project_id, 
      summary_type,
      preferred_provider,
      model,
      language
    });
    return res.data;
  },

  listWorkItems: async (params?: any): Promise<any> => {
    const res = await api.get('/work-items', { params });
    return res.data;
  },

  confirmWorkItem: async (itemId: string): Promise<any> => {
    const res = await api.post(`/work-items/${itemId}/confirm`);
    return res.data;
  },

  rejectWorkItem: async (itemId: string): Promise<any> => {
    const res = await api.post(`/work-items/${itemId}/reject`);
    return res.data;
  },

  resetWorkItem: async (itemId: string): Promise<any> => {
    const res = await api.post(`/work-items/${itemId}/reset`);
    return res.data;
  },

  updateWorkItem: async (itemId: string, data: any): Promise<any> => {
    const res = await api.patch(`/work-items/${itemId}`, data);
    return res.data;
  },

  createWorkItem: async (data: any): Promise<any> => {
    const res = await api.post('/work-items', data);
    return res.data;
  },

  analyzeConversation: async (payload: { text: string; project_id: string; source_type?: string; author?: string; save_drafts?: boolean }): Promise<any> => {
    const res = await api.post('/intelligence/analyze', payload);
    return res.data;
  },

  askProjectBrain: async (
    project_id: string,
    query: string,
    chat_history?: Array<{ role: string; content: string }>,
    scope?: string,
    preferred_provider?: string,
    model?: string
  ): Promise<any> => {
    const res = await api.post(`/intelligence/projects/${project_id}/ask`, {
      query,
      chat_history,
      scope: scope || 'all',
      preferred_provider,
      model
    });
    return res.data;
  },

  getProjectBrainStats: async (project_id: string): Promise<any> => {
    const res = await api.get(`/intelligence/projects/${project_id}/brain-stats`);
    return res.data;
  },

  diffDocuments: async (project_id: string, old_text: string, new_text: string, title?: string): Promise<any> => {
    const res = await api.post(`/intelligence/projects/${project_id}/diff`, { old_text, new_text, title });
    return res.data;
  },

  analyzeImpact: async (project_id: string, change_description: string, affected_component?: string): Promise<any> => {
    const res = await api.post(`/intelligence/projects/${project_id}/impact`, { change_description, affected_component });
    return res.data;
  },

  generateSmartReply: async (current_message: string, conversation_context?: string[], project_id?: string): Promise<any> => {
    const res = await api.post('/intelligence/reply/generate', { current_message, conversation_context, project_id });
    return res.data;
  },

  analyzeMeeting: async (payload: { project_id: string; title: string; meeting_date: string; transcript_text: string; participants?: string[]; preferred_provider?: string; model?: string }): Promise<any> => {
    const res = await api.post('/intelligence/meetings/analyze', payload);
    return res.data;
  },

  listMeetings: async (project_id?: string): Promise<any> => {
    const res = await api.get('/intelligence/meetings', { params: project_id ? { project_id } : {} });
    return res.data;
  },

  askMeetings: async (payload: { project_id?: string; query: string; preferred_provider?: string; model?: string; chat_history?: Array<{ role: string; content: string }> }): Promise<any> => {
    const res = await api.post('/intelligence/meetings/ask', payload);
    return res.data;
  },


  deleteMeeting: async (meeting_id: string): Promise<any> => {
    const res = await api.delete(`/intelligence/meetings/${meeting_id}`);
    return res.data;
  },

  clearAllMeetings: async (): Promise<any> => {
    const res = await api.delete('/intelligence/meetings/clear-all');
    return res.data;
  },

  getLineMessages: async (projectId?: string): Promise<{ messages: LineMessageItem[] }> => {
    const res = await api.get('/line/messages', {
      params: projectId ? { project_id: projectId } : undefined
    });
    return res.data;
  },

  simulateLineMessage: async (payload: {
    text: string;
    sender?: string;
    project_id?: string;
    provider?: string;
    model?: string;
  }): Promise<LineMessageItem> => {
    const res = await api.post('/line/simulate', payload);
    return res.data;
  },

  deleteLineMessage: async (messageId: string): Promise<{ success: boolean; id: string; message: string }> => {
    const res = await api.delete(`/line/messages/${messageId}`);
    return res.data;
  },

  clearLineMessages: async (projectId?: string): Promise<{ success: boolean; deleted_count: number; message: string }> => {
    const res = await api.delete('/line/messages/clear-all', {
      params: projectId ? { project_id: projectId } : undefined
    });
    return res.data;
  },

  regenerateLineReply: async (messageId: string, provider?: string, model?: string): Promise<any> => {
    const res = await api.post(`/line/messages/${messageId}/regenerate`, { provider, model });
    return res.data;
  },

  sendLineReply: async (reply_token: string, message_text: string): Promise<any> => {
    const res = await api.post('/line/reply', { reply_token, message_text });
    return res.data;
  },

  simulateSlackMessage: async (text: string, sender?: string, channel?: string, project_id?: string): Promise<any> => {
    const res = await api.post('/slack/simulate', { text, sender, channel, project_id });
    return res.data;
  },

  sendSlackReply: async (channel: string, message_text: string, thread_ts?: string, project_id?: string): Promise<any> => {
    const res = await api.post('/slack/reply', { channel, message_text, thread_ts, project_id });
    return res.data;
  },

  getAutomationRules: async (project_id?: string): Promise<any> => {
    const res = await api.get('/automation/rules', { params: { project_id } });
    return res.data;
  },

  getAutomationLogs: async (limit: number = 50): Promise<any> => {
    const res = await api.get('/automation/logs', { params: { limit } });
    return res.data;
  },

  getStakeholders: async (projectId?: string, includeInactive: boolean = false): Promise<ProjectStakeholder[]> => {
    const res = await api.get('/intelligence/stakeholders', {
      params: { project_id: projectId, include_inactive: includeInactive }
    });
    return res.data;
  },

  createStakeholder: async (payload: StakeholderCreatePayload): Promise<ProjectStakeholder> => {
    const res = await api.post('/intelligence/stakeholders', payload);
    return res.data;
  },

  updateStakeholder: async (id: string, payload: Partial<StakeholderCreatePayload & { is_active?: boolean }>): Promise<ProjectStakeholder> => {
    const res = await api.put(`/intelligence/stakeholders/${id}`, payload);
    return res.data;
  },

  deleteStakeholder: async (id: string): Promise<{ success: boolean; id: string; message: string }> => {
    const res = await api.delete(`/intelligence/stakeholders/${id}`);
    return res.data;
  },

  cleanMockStakeholders: async (projectId?: string): Promise<{ message: string; deleted_count: number }> => {
    const res = await api.post('/intelligence/stakeholders/clean-mock', null, {
      params: projectId ? { project_id: projectId } : undefined
    });
    return res.data;
  },

  // QA Workspace Phase 1
  qaReviewRequirement: async (requirementId: string, opts?: { preferred_provider?: string; model?: string; force?: boolean }): Promise<any[]> => {
    const res = await api.post(`/qa/requirements/${requirementId}/review`, {
      preferred_provider: opts?.preferred_provider,
      model: opts?.model,
      force: opts?.force ?? false,
    });
    return res.data;
  },

  qaGetDetail: async (requirementId: string): Promise<any> => {
    const res = await api.get(`/qa/requirements/${requirementId}/detail`);
    return res.data;
  },

  qaListRequirements: async (projectId: string, params?: { status?: string; coverage?: string }): Promise<any[]> => {
    const res = await api.get(`/qa/projects/${projectId}/requirements`, { params });
    return res.data;
  },

  qaUpdateFinding: async (findingId: string, status: string): Promise<any> => {
    const res = await api.patch(`/qa/findings/${findingId}`, { status });
    return res.data;
  },

  qaGenerateQuestions: async (requirementId: string, opts?: { finding_ids?: string[]; preferred_provider?: string; model?: string }): Promise<any[]> => {
    const res = await api.post(`/qa/requirements/${requirementId}/questions:generate`, {
      finding_ids: opts?.finding_ids,
      preferred_provider: opts?.preferred_provider,
      model: opts?.model,
    });
    return res.data;
  },

  qaUpdateQuestion: async (questionId: string, data: any): Promise<any> => {
    const res = await api.patch(`/qa/questions/${questionId}`, data);
    return res.data;
  },

  qaGenerateAC: async (requirementId: string, opts?: { preferred_provider?: string; model?: string }): Promise<any[]> => {
    const res = await api.post(`/qa/requirements/${requirementId}/acceptance-criteria:generate`, {
      preferred_provider: opts?.preferred_provider,
      model: opts?.model,
    });
    return res.data;
  },

  qaCreateAC: async (requirementId: string, data: { given_text: string; when_text: string; then_text: string; evidence_quote?: string }): Promise<any> => {
    const res = await api.post(`/qa/requirements/${requirementId}/acceptance-criteria`, data);
    return res.data;
  },

  qaUpdateAC: async (acId: string, data: any): Promise<any> => {
    const res = await api.patch(`/qa/acceptance-criteria/${acId}`, data);
    return res.data;
  },

  qaDeleteAC: async (acId: string): Promise<any> => {
    const res = await api.delete(`/qa/acceptance-criteria/${acId}`);
    return res.data;
  },

  qaGenerateTestCases: async (requirementId: string, opts?: { acceptance_criterion_ids?: string[]; checklist_mode?: boolean; preferred_provider?: string; model?: string }): Promise<any[]> => {
    const res = await api.post(`/qa/requirements/${requirementId}/test-cases:generate`, {
      acceptance_criterion_ids: opts?.acceptance_criterion_ids,
      checklist_mode: opts?.checklist_mode ?? false,
      preferred_provider: opts?.preferred_provider,
      model: opts?.model,
    });
    return res.data;
  },

  qaCreateTestCase: async (requirementId: string, data: any): Promise<any> => {
    const res = await api.post(`/qa/requirements/${requirementId}/test-cases`, data);
    return res.data;
  },

  qaListTestCases: async (params?: any): Promise<any[]> => {
    const res = await api.get('/qa/test-cases', { params });
    return res.data;
  },

  qaGetTestCase: async (caseId: string): Promise<any> => {
    const res = await api.get(`/qa/test-cases/${caseId}`);
    return res.data;
  },

  qaUpdateTestCase: async (caseId: string, data: any): Promise<any> => {
    const res = await api.patch(`/qa/test-cases/${caseId}`, data);
    return res.data;
  },

  qaDuplicateTestCase: async (caseId: string): Promise<any> => {
    const res = await api.post(`/qa/test-cases/${caseId}/duplicate`);
    return res.data;
  },

  qaDeleteTestCase: async (caseId: string): Promise<any> => {
    const res = await api.delete(`/qa/test-cases/${caseId}`);
    return res.data;
  },

  qaGetCoverage: async (projectId: string): Promise<any[]> => {
    const res = await api.get(`/qa/projects/${projectId}/coverage`);
    return res.data;
  },

  qaGetOverview: async (projectId: string): Promise<any> => {
    const res = await api.get(`/qa/projects/${projectId}/overview`);
    return res.data;
  },

  // QA Workspace Phase 2 — Test Runs & Execution
  qaCreateTestRun: async (projectId: string, data: any): Promise<any> => {
    const res = await api.post('/qa/test-runs', data, { params: { project_id: projectId } });
    return res.data;
  },

  qaListTestRuns: async (params?: any): Promise<any[]> => {
    const res = await api.get('/qa/test-runs', { params });
    return res.data;
  },

  qaGetTestRun: async (runId: string): Promise<any> => {
    const res = await api.get(`/qa/test-runs/${runId}`);
    return res.data;
  },

  qaUpdateTestRun: async (runId: string, data: any): Promise<any> => {
    const res = await api.patch(`/qa/test-runs/${runId}`, data);
    return res.data;
  },

  qaAddRunCases: async (runId: string, scope: any): Promise<any> => {
    const res = await api.post(`/qa/test-runs/${runId}/cases`, { scope });
    return res.data;
  },

  qaNextExecution: async (runId: string, after?: string): Promise<any> => {
    const res = await api.get(`/qa/test-runs/${runId}/next`, { params: after ? { after } : {} });
    return res.data;
  },

  qaGetExecution: async (executionId: string): Promise<any> => {
    const res = await api.get(`/qa/executions/${executionId}`);
    return res.data;
  },

  qaStartExecution: async (executionId: string, tester?: string): Promise<any> => {
    const res = await api.post(`/qa/executions/${executionId}/start`, null, { params: tester ? { tester } : {} });
    return res.data;
  },

  qaSaveResult: async (executionId: string, data: any): Promise<any> => {
    const res = await api.post(`/qa/executions/${executionId}/result`, data);
    return res.data;
  },

  qaRewriteActual: async (executionId: string, data: any): Promise<{ rewritten: string }> => {
    const res = await api.post(`/qa/executions/${executionId}/rewrite-actual`, data);
    return res.data;
  },

  qaAddEvidence: async (executionId: string, data: any): Promise<any> => {
    const res = await api.post(`/qa/executions/${executionId}/evidence`, data);
    return res.data;
  },

  qaUploadEvidence: async (executionId: string, file: File, opts?: { title?: string; evidence_type?: string; changed_by?: string }): Promise<any> => {
    const form = new FormData();
    form.append('file', file);
    if (opts?.title) form.append('title', opts.title);
    form.append('evidence_type', opts?.evidence_type || 'screenshot');
    form.append('changed_by', opts?.changed_by || 'user');
    const res = await api.post(`/qa/executions/${executionId}/evidence/upload`, form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return res.data;
  },

  qaEvidenceFileUrl: (evidenceId: string): string => {
    return `http://127.0.0.1:8000/api/qa/evidence/${evidenceId}/file`;
  },

  qaDraftBug: async (executionId: string, opts?: any): Promise<any> => {
    const res = await api.post(`/qa/executions/${executionId}/bug:draft`, opts || {});
    return res.data;
  },

  qaCreateBug: async (executionId: string, data: any): Promise<any> => {
    const res = await api.post(`/qa/executions/${executionId}/bug`, data);
    return res.data;
  },

  qaRetest: async (executionId: string): Promise<any> => {
    const res = await api.post(`/qa/executions/${executionId}/retest`, {});
    return res.data;
  },

  qaListBugs: async (params?: any): Promise<any[]> => {
    const res = await api.get('/qa/bugs', { params });
    return res.data;
  },

  qaGetBug: async (bugId: string): Promise<any> => {
    const res = await api.get(`/qa/bugs/${bugId}`);
    return res.data;
  },

  qaUpdateBug: async (bugId: string, data: any): Promise<any> => {
    const res = await api.patch(`/qa/bugs/${bugId}`, data);
    return res.data;
  },

  qaGenerateReport: async (runId: string, data: any): Promise<any> => {
    const res = await api.post(`/qa/test-runs/${runId}/reports`, data);
    return res.data;
  },

  qaListReports: async (runId: string): Promise<any[]> => {
    const res = await api.get(`/qa/test-runs/${runId}/reports`);
    return res.data;
  },

  qaApproveReport: async (reportId: string): Promise<any> => {
    const res = await api.patch(`/qa/reports/${reportId}`, { status: 'APPROVED' });
    return res.data;
  },

  qaExecutionCoverage: async (projectId: string): Promise<any[]> => {
    const res = await api.get('/qa/execution-coverage', { params: { project_id: projectId } });
    return res.data;
  },

  // QA Phase 3: API testing
  qaImportOpenAPI: async (projectId: string, content: string): Promise<any> => {
    const res = await api.post('/qa/openapi:import', { project_id: projectId, content });
    return res.data;
  },

  qaListEndpoints: async (projectId: string, params?: any): Promise<any[]> => {
    const res = await api.get('/qa/endpoints', { params: { project_id: projectId, ...(params || {}) } });
    return res.data;
  },

  qaCreateEndpoint: async (projectId: string, data: any): Promise<any> => {
    const res = await api.post('/qa/endpoints', data, { params: { project_id: projectId } });
    return res.data;
  },

  qaUpdateEndpoint: async (endpointId: string, data: any): Promise<any> => {
    const res = await api.patch(`/qa/endpoints/${endpointId}`, data);
    return res.data;
  },

  qaDeleteEndpoint: async (endpointId: string): Promise<any> => {
    const res = await api.delete(`/qa/endpoints/${endpointId}`);
    return res.data;
  },

  qaListEnvs: async (projectId: string): Promise<any[]> => {
    const res = await api.get('/qa/environments', { params: { project_id: projectId } });
    return res.data;
  },

  qaCreateEnv: async (projectId: string, data: any): Promise<any> => {
    const res = await api.post('/qa/environments', data, { params: { project_id: projectId } });
    return res.data;
  },

  qaUpdateEnv: async (envId: string, data: any): Promise<any> => {
    const res = await api.patch(`/qa/environments/${envId}`, data);
    return res.data;
  },

  qaDeleteEnv: async (envId: string): Promise<any> => {
    const res = await api.delete(`/qa/environments/${envId}`);
    return res.data;
  },

  qaSetEnvSecret: async (envId: string, key: string, value: string): Promise<any> => {
    const res = await api.post(`/qa/environments/${envId}/secrets`, { key, value });
    return res.data;
  },

  qaDeleteEnvSecret: async (envId: string, key: string): Promise<any> => {
    const res = await api.delete(`/qa/environments/${envId}/secrets/${key}`);
    return res.data;
  },

  qaGenerateApiTests: async (data: any): Promise<any[]> => {
    const res = await api.post('/qa/api-tests:generate', data);
    return res.data;
  },

  qaListApiTests: async (projectId: string, params?: any): Promise<any[]> => {
    const res = await api.get('/qa/api-tests', { params: { project_id: projectId, ...(params || {}) } });
    return res.data;
  },

  qaGetApiTest: async (caseId: string): Promise<any> => {
    const res = await api.get(`/qa/api-tests/${caseId}`);
    return res.data;
  },

  qaUpdateApiConfig: async (caseId: string, data: any): Promise<any> => {
    const res = await api.patch(`/qa/api-tests/${caseId}/config`, data);
    return res.data;
  },

  qaCreateAssertion: async (caseId: string, data: any): Promise<any> => {
    const res = await api.post(`/qa/api-tests/${caseId}/assertions`, data);
    return res.data;
  },

  qaUpdateAssertion: async (assertionId: string, data: any): Promise<any> => {
    const res = await api.patch(`/qa/assertions/${assertionId}`, data);
    return res.data;
  },

  qaDeleteAssertion: async (assertionId: string): Promise<any> => {
    const res = await api.delete(`/qa/assertions/${assertionId}`);
    return res.data;
  },

  qaSuggestAssertions: async (caseId: string, data?: any): Promise<any[]> => {
    const res = await api.post(`/qa/api-tests/${caseId}/assertions:suggest`, data || {});
    return res.data;
  },

  qaRunApiTest: async (caseId: string, data: any): Promise<any> => {
    const res = await api.post(`/qa/api-tests/${caseId}/run`, data);
    return res.data;
  },

  qaRunApiSuite: async (data: any): Promise<any> => {
    const res = await api.post('/qa/api-suites:run', data);
    return res.data;
  },

  qaAnalyzeFail: async (executionId: string, data?: any): Promise<any> => {
    const res = await api.post(`/qa/executions/${executionId}/analyze-fail`, data || {});
    return res.data;
  },

  qaDraftApiBug: async (executionId: string, data?: any): Promise<any> => {
    const res = await api.post(`/qa/executions/${executionId}/api-bug:draft`, data || {});
    return res.data;
  },

  qaListFlows: async (projectId: string): Promise<any[]> => {
    const res = await api.get('/qa/flows', { params: { project_id: projectId } });
    return res.data;
  },

  qaCreateFlow: async (data: any): Promise<any> => {
    const res = await api.post('/qa/flows', data);
    return res.data;
  },

  qaRunFlow: async (flowId: string, data: any): Promise<any> => {
    const res = await api.post(`/qa/flows/${flowId}/run`, data);
    return res.data;
  },

  qaApiCoverage: async (projectId: string): Promise<any[]> => {
    const res = await api.get('/qa/coverage/api', { params: { project_id: projectId } });
    return res.data;
  },

  qaPreviewTestData: async (kind: string): Promise<any> => {
    const res = await api.get('/qa/test-data:preview', { params: { kind } });
    return res.data;
  },

  // QA Phase 4: UI automation
  qaGenerateUiScript: async (data: any): Promise<any> => {
    const res = await api.post('/qa/ui-scripts:generate', data);
    return res.data;
  },

  qaListUiScripts: async (projectId: string, params?: any): Promise<any[]> => {
    const res = await api.get('/qa/ui-scripts', { params: { project_id: projectId, ...(params || {}) } });
    return res.data;
  },

  qaGetUiScript: async (caseId: string): Promise<any> => {
    const res = await api.get(`/qa/ui-scripts/${caseId}`);
    return res.data;
  },

  qaUpdateUiScript: async (caseId: string, data: any): Promise<any> => {
    const res = await api.patch(`/qa/ui-scripts/${caseId}`, data);
    return res.data;
  },

  qaListUiMappings: async (projectId: string, params?: any): Promise<any[]> => {
    const res = await api.get('/qa/ui-mappings', { params: { project_id: projectId, ...(params || {}) } });
    return res.data;
  },

  qaCreateUiMapping: async (projectId: string, data: any): Promise<any> => {
    const res = await api.post('/qa/ui-mappings', data, { params: { project_id: projectId } });
    return res.data;
  },

  qaUpdateUiMapping: async (mappingId: string, data: any): Promise<any> => {
    const res = await api.patch(`/qa/ui-mappings/${mappingId}`, data);
    return res.data;
  },

  qaDeleteUiMapping: async (mappingId: string): Promise<any> => {
    const res = await api.delete(`/qa/ui-mappings/${mappingId}`);
    return res.data;
  },

  qaListUiPages: async (projectId: string): Promise<any[]> => {
    const res = await api.get('/qa/ui-pages', { params: { project_id: projectId } });
    return res.data;
  },

  qaCreateUiPage: async (projectId: string, data: any): Promise<any> => {
    const res = await api.post('/qa/ui-pages', data, { params: { project_id: projectId } });
    return res.data;
  },

  qaUpdateUiPage: async (pageId: string, data: any): Promise<any> => {
    const res = await api.patch(`/qa/ui-pages/${pageId}`, data);
    return res.data;
  },

  qaDeleteUiPage: async (pageId: string): Promise<any> => {
    const res = await api.delete(`/qa/ui-pages/${pageId}`);
    return res.data;
  },

  qaRunUiTest: async (caseId: string, data: any): Promise<any> => {
    const res = await api.post(`/qa/ui-tests/${caseId}/run`, data);
    return res.data;
  },

  qaUiStatus: async (executionId: string): Promise<any> => {
    const res = await api.get(`/qa/executions/${executionId}/ui-status`);
    return res.data;
  },

  qaUiCancel: async (executionId: string): Promise<any> => {
    const res = await api.post(`/qa/executions/${executionId}/ui-cancel`);
    return res.data;
  },

  qaRunUiSuite: async (data: any): Promise<any> => {
    const res = await api.post('/qa/ui-suites:run', data);
    return res.data;
  },

  qaAnalyzeUiFail: async (executionId: string, data?: any): Promise<any> => {
    const res = await api.post(`/qa/executions/${executionId}/analyze-ui-fail`, data || {});
    return res.data;
  },

  qaDraftUiBug: async (executionId: string, data?: any): Promise<any> => {
    const res = await api.post(`/qa/executions/${executionId}/ui-bug:draft`, data || {});
    return res.data;
  },

  qaUiCoverage: async (projectId: string): Promise<any[]> => {
    const res = await api.get('/qa/coverage/ui', { params: { project_id: projectId } });
    return res.data;
  },

  qaUiCandidates: async (projectId: string): Promise<any[]> => {
    const res = await api.get('/qa/ui-candidates', { params: { project_id: projectId } });
    return res.data;
  },

  qaUiOverview: async (projectId: string): Promise<any> => {
    const res = await api.get('/qa/overview/ui', { params: { project_id: projectId } });
    return res.data;
  },

  // QA Phase 5: Regression Intelligence
  qaCreateChange: async (projectId: string, data: any): Promise<any> => {
    const res = await api.post('/qa/changes', data, { params: { project_id: projectId } });
    return res.data;
  },

  qaListChanges: async (projectId: string, params?: any): Promise<any[]> => {
    const res = await api.get('/qa/changes', { params: { project_id: projectId, ...(params || {}) } });
    return res.data;
  },

  qaSuggestChanges: async (projectId: string): Promise<any[]> => {
    const res = await api.get('/qa/changes/suggest', { params: { project_id: projectId } });
    return res.data;
  },

  qaGetChange: async (changeId: string): Promise<any> => {
    const res = await api.get(`/qa/changes/${changeId}`);
    return res.data;
  },

  qaAnalyzeChange: async (changeId: string, data?: any): Promise<any> => {
    const res = await api.post(`/qa/changes/${changeId}/analyze`, data || {});
    return res.data;
  },

  qaRequirementVersions: async (requirementId: string): Promise<any[]> => {
    const res = await api.get(`/qa/requirements/${requirementId}/versions`);
    return res.data;
  },

  qaSpecDiff: async (data: any): Promise<any> => {
    const res = await api.post('/qa/specs:diff', data);
    return res.data;
  },

  qaCreatePlan: async (projectId: string, data: any): Promise<any> => {
    const res = await api.post('/qa/plans', data, { params: { project_id: projectId } });
    return res.data;
  },

  qaListPlans: async (projectId: string, params?: any): Promise<any[]> => {
    const res = await api.get('/qa/plans', { params: { project_id: projectId, ...(params || {}) } });
    return res.data;
  },

  qaGetPlan: async (planId: string): Promise<any> => {
    const res = await api.get(`/qa/plans/${planId}`);
    return res.data;
  },

  qaUpdatePlan: async (planId: string, data: any): Promise<any> => {
    const res = await api.patch(`/qa/plans/${planId}`, data);
    return res.data;
  },

  qaAddPlanItem: async (planId: string, data: any): Promise<any> => {
    const res = await api.post(`/qa/plans/${planId}/items`, data);
    return res.data;
  },

  qaRemovePlanItem: async (itemId: string): Promise<any> => {
    const res = await api.delete(`/qa/plans/items/${itemId}`);
    return res.data;
  },

  qaRunPlan: async (planId: string, data: any): Promise<any> => {
    const res = await api.post(`/qa/plans/${planId}/run`, data);
    return res.data;
  },

  qaPlanSummary: async (planId: string): Promise<any> => {
    const res = await api.get(`/qa/plans/${planId}/summary`);
    return res.data;
  },

  qaChangeCoverage: async (params: any): Promise<any> => {
    const res = await api.get('/qa/change-coverage', { params });
    return res.data;
  },

  // QA Phase 6: Data QA
  qaUploadDataSource: async (projectId: string, file: File, opts?: { name?: string; sheet?: string; kind?: string }): Promise<any> => {
    const form = new FormData();
    form.append('file', file);
    if (opts?.name) form.append('name', opts.name);
    if (opts?.sheet) form.append('sheet', opts.sheet);
    form.append('kind', opts?.kind || 'file_csv');
    const res = await api.post('/qa/data-sources/upload', form, {
      params: { project_id: projectId },
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return res.data;
  },

  qaCreateDataSource: async (projectId: string, data: any): Promise<any> => {
    const res = await api.post('/qa/data-sources', data, { params: { project_id: projectId } });
    return res.data;
  },

  qaListDataSources: async (projectId: string): Promise<any[]> => {
    const res = await api.get('/qa/data-sources', { params: { project_id: projectId } });
    return res.data;
  },

  qaGetDataSource: async (sourceId: string): Promise<any> => {
    const res = await api.get(`/qa/data-sources/${sourceId}`);
    return res.data;
  },

  qaDeleteDataSource: async (sourceId: string): Promise<any> => {
    const res = await api.delete(`/qa/data-sources/${sourceId}`);
    return res.data;
  },

  qaCreateDataJob: async (projectId: string, data: any): Promise<any> => {
    const res = await api.post('/qa/data-jobs', data, { params: { project_id: projectId } });
    return res.data;
  },

  qaListDataJobs: async (projectId: string, params?: any): Promise<any[]> => {
    const res = await api.get('/qa/data-jobs', { params: { project_id: projectId, ...(params || {}) } });
    return res.data;
  },

  qaGetDataJob: async (jobId: string): Promise<any> => {
    const res = await api.get(`/qa/data-jobs/${jobId}`);
    return res.data;
  },

  qaUpdateDataJob: async (jobId: string, data: any): Promise<any> => {
    const res = await api.patch(`/qa/data-jobs/${jobId}`, data);
    return res.data;
  },

  qaDeleteDataJob: async (jobId: string): Promise<any> => {
    const res = await api.delete(`/qa/data-jobs/${jobId}`);
    return res.data;
  },

  qaListMappings: async (jobId: string): Promise<any[]> => {
    const res = await api.get(`/qa/data-jobs/${jobId}/mappings`);
    return res.data;
  },

  qaCreateMappings: async (jobId: string, mappings: any[]): Promise<any[]> => {
    const res = await api.post(`/qa/data-jobs/${jobId}/mappings`, { mappings });
    return res.data;
  },

  qaSuggestMappings: async (jobId: string): Promise<any[]> => {
    const res = await api.post(`/qa/data-jobs/${jobId}/mappings:suggest`, {});
    return res.data;
  },

  qaUpdateMapping: async (mappingId: string, data: any): Promise<any> => {
    const res = await api.patch(`/qa/data-mappings/${mappingId}`, data);
    return res.data;
  },

  qaDeleteMapping: async (mappingId: string): Promise<any> => {
    const res = await api.delete(`/qa/data-mappings/${mappingId}`);
    return res.data;
  },

  qaCreateDataRule: async (projectId: string, data: any): Promise<any> => {
    const res = await api.post('/qa/data-rules', data, { params: { project_id: projectId } });
    return res.data;
  },

  qaListDataRules: async (projectId: string, params?: any): Promise<any[]> => {
    const res = await api.get('/qa/data-rules', { params: { project_id: projectId, ...(params || {}) } });
    return res.data;
  },

  qaGenerateDataRules: async (projectId: string, data: any): Promise<any[]> => {
    const res = await api.post('/qa/data-rules:generate', data, { params: { project_id: projectId } });
    return res.data;
  },

  qaUpdateDataRule: async (ruleId: string, data: any): Promise<any> => {
    const res = await api.patch(`/qa/data-rules/${ruleId}`, data);
    return res.data;
  },

  qaDeleteDataRule: async (ruleId: string): Promise<any> => {
    const res = await api.delete(`/qa/data-rules/${ruleId}`);
    return res.data;
  },

  qaRunDataJob: async (jobId: string, data?: any): Promise<any> => {
    const res = await api.post(`/qa/data-jobs/${jobId}/run`, data || {});
    return res.data;
  },

  qaListDifferences: async (jobId: string, params?: any): Promise<any[]> => {
    const res = await api.get(`/qa/data-jobs/${jobId}/differences`, { params });
    return res.data;
  },

  qaUpdateDifference: async (diffId: string, data: any): Promise<any> => {
    const res = await api.patch(`/qa/data-differences/${diffId}`, data);
    return res.data;
  },

  qaDraftDataBug: async (executionId: string, data?: any): Promise<any> => {
    const res = await api.post(`/qa/executions/${executionId}/data-bug:draft`, data || {});
    return res.data;
  },

  qaDataJobReport: async (jobId: string, executionId?: string): Promise<any> => {
    const res = await api.get(`/qa/data-jobs/${jobId}/report`, { params: executionId ? { execution_id: executionId } : {} });
    return res.data;
  },

  qaDataCoverage: async (projectId: string): Promise<any[]> => {
    const res = await api.get('/qa/data-coverage', { params: { project_id: projectId } });
    return res.data;
  },

  qaDataOverview: async (projectId: string): Promise<any> => {
    const res = await api.get('/qa/data-overview', { params: { project_id: projectId } });
    return res.data;
  },

  // Reports Intelligence Suite
  harvestReportData: async (projectId: string, reportType = 'client_nippo', date?: string): Promise<any> => {
    const res = await api.get('/intelligence/reports/harvest', {
      params: { project_id: projectId, report_type: reportType, date }
    });
    return res.data;
  },

  uploadReportTemplate: async (file: File): Promise<any> => {
    const formData = new FormData();
    formData.append('file', file);
    const res = await api.post('/intelligence/reports/upload-template', formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    });
    return res.data;
  },

  generateReport: async (payload: {
    project_id: string;
    report_type: string;
    is_auto_harvest: boolean;
    manual_input_raw?: string;
    target_language: string;
    sender_name: string;
    recipient_name: string;
    selected_item_ids?: string[];
    additional_notes?: string;
    report_date?: string;
    template_file_path?: string;
    custom_text_template?: string;
    provider?: string;
    model?: string;
  }): Promise<any> => {
    const res = await api.post('/intelligence/reports/generate', payload);
    return res.data;
  },

  getReportHistory: async (projectId: string, limit = 20): Promise<any[]> => {
    const res = await api.get('/intelligence/reports/history', {
      params: { project_id: projectId, limit }
    });
    return res.data;
  },

  getSingleReport: async (reportId: string): Promise<any> => {
    const res = await api.get(`/intelligence/reports/${reportId}`);
    return res.data;
  },

  deleteReport: async (reportId: string): Promise<any> => {
    const res = await api.delete(`/intelligence/reports/${reportId}`);
    return res.data;
  },

  getReportExportUrl: (reportId: string, format: 'pptx' | 'docx' | 'xlsx'): string => {
    return `${API_BASE_URL}/intelligence/reports/${reportId}/export-${format}`;
  },

  // Quick QA Copilot Studio
  quickQAAnalyze: async (payload: {
    project_id?: string;
    spec_text: string;
    mode: string;
    custom_instruction?: string;
    is_auto_harvest?: boolean;
    target_language?: string;
    preferred_provider?: string;
    model?: string;
  }): Promise<any> => {
    const res = await api.post('/qa/quick-analyze', payload);
    return res.data;
  },

  quickQASave: async (payload: {
    project_id: string;
    item_type: 'test_case' | 'bug' | 'question';
    title: string;
    description: string;
    steps?: any[];
    priority?: string;
  }): Promise<any> => {
    const res = await api.post('/qa/quick-save', payload);
    return res.data;
  }
};

