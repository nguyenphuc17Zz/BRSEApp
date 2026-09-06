import axios from 'axios';
import {
  TranslationRequest,
  TranslationResponse,
  Project,
  GlossaryTerm,
  TranslationMemoryItem,
  HistoryItem,
  ProviderInfo,
  DashboardData,
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

  // Dashboard
  getDashboardStats: async (project_id?: string): Promise<DashboardData> => {
    const res = await api.get('/dashboard/stats', { params: { project_id } });
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

  // Document Translation (Phase 2)
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

  // Phase 3: Workspace & Communication Integrations
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

  // Phase 4 — BrSE Brain & Smart Workflow APIs
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
  }
};

