import React, { useState, useEffect } from 'react';
import {
  Layers,
  Cloud,
  MessageSquare,
  Monitor,
  CheckCircle2,
  AlertTriangle,
  RefreshCw,
  Folder,
  FileText,
  FileSpreadsheet,
  Presentation,
  Send,
  Copy,
  Check,
  ExternalLink,
  Shield,
  Trash2,
  Search,
  Sparkles,
  ChevronRight,
  Clock,
  Settings,
  HelpCircle,
  Hash,
  Lock,
  ArrowRight,
  Play,
  Pause,
  RotateCcw,
  XCircle,
  Eye
} from 'lucide-react';
import { apiClient } from '../api/client';
import { FileFormatIcon } from '../components/common/FileFormatIcon';
import {
  Project,
  IntegrationHealth,
  GoogleFileItem,
  SlackChannel,
  SlackMessage,
  SlackReplyOption,
  ChannelMapping,
  ProviderInfo
} from '../types';
import { useToast } from '../context/ToastContext';
import { useConfirm } from '../context/ConfirmDialogContext';
import { GoogleTranslateConfigModal } from '../components/integrations/GoogleTranslateConfigModal';
import { GoogleSegmentReviewModal } from '../components/integrations/GoogleSegmentReviewModal';
import { GoogleSetupGuideModal } from '../components/integrations/GoogleSetupGuideModal';
import { GoogleCredentialsDropzone } from '../components/integrations/GoogleCredentialsDropzone';
import { GoogleDriveExplorer } from '../components/integrations/GoogleDriveExplorer';
import { GoogleAccountSwitcher } from '../components/integrations/GoogleAccountSwitcher';
import { GoogleAccountItem } from '../types';
import { Card } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { Badge } from '../components/ui/Badge';
import { Input } from '../components/ui/Input';
import { EmptyState } from '../components/ui/EmptyState';
import { Select } from '../components/ui/Select';

interface IntegrationsPageProps {
  activeProject: Project | null;
  projects: Project[];
  onOpenQuickTranslate?: () => void;
}

export const IntegrationsPage: React.FC<IntegrationsPageProps> = ({
  activeProject,
  projects,
  onOpenQuickTranslate
}) => {
  const toast = useToast();
  const confirm = useConfirm();
  const [health, setHealth] = useState<IntegrationHealth | null>(null);
  const [activeTab, setActiveTab] = useState<'google' | 'slack' | 'desktop' | 'mappings'>('google');
  const [isLoading, setIsLoading] = useState(false);

  // Google Drive state
  const [googleAccounts, setGoogleAccounts] = useState<GoogleAccountItem[]>([]);
  const [selectedAccountId, setSelectedAccountId] = useState<string | null>(null);
  const [driveFiles, setDriveFiles] = useState<GoogleFileItem[]>([]);
  const [selectedFolder, setSelectedFolder] = useState<string | null>(null);
  const [selectedFolderName, setSelectedFolderName] = useState<string | null>('My Drive');
  const [driveViewMode, setDriveViewMode] = useState<'my_drive' | 'shared_with_me' | 'recent'>('my_drive');
  const [driveSearch, setDriveSearch] = useState('');
  const [selectedFile, setSelectedFile] = useState<GoogleFileItem | null>(null);
  const [isTranslatingDoc, setIsTranslatingDoc] = useState(false);
  const [translateSuccess, setTranslateSuccess] = useState<string | null>(null);

  // Google Workspace translation & modals state
  const [providers, setProviders] = useState<ProviderInfo[]>([]);
  const [configGoogleFile, setConfigGoogleFile] = useState<GoogleFileItem | null>(null);
  const [reviewGoogleJob, setReviewGoogleJob] = useState<{
    jobId: string;
    fileTitle: string;
    fileType: string;
    outputUrl?: string;
  } | null>(null);
  const [activeGoogleJobId, setActiveGoogleJobId] = useState<string | null>(null);
  const [googleJobProgress, setGoogleJobProgress] = useState<any | null>(null);
  const [showGoogleGuideModal, setShowGoogleGuideModal] = useState<boolean>(false);

  // Slack state
  const [slackChannels, setSlackChannels] = useState<SlackChannel[]>([]);
  const [selectedChannel, setSelectedChannel] = useState<string>('');
  const [channelMessages, setChannelMessages] = useState<SlackMessage[]>([]);
  const [activeMessage, setActiveMessage] = useState<SlackMessage | null>(null);
  const [messageTranslation, setMessageTranslation] = useState<any | null>(null);
  const [replyOptions, setReplyOptions] = useState<SlackReplyOption[]>([]);
  const [isTranslatingSlack, setIsTranslatingSlack] = useState(false);
  const [isGeneratingReplies, setIsGeneratingReplies] = useState(false);
  const [copiedReplyIndex, setCopiedReplyIndex] = useState<number | null>(null);

  // Channel Mappings state
  const [mappings, setMappings] = useState<ChannelMapping[]>([]);
  const [newChannelId, setNewChannelId] = useState('');
  const [newChannelName, setNewChannelName] = useState('');
  const [newProjectId, setNewProjectId] = useState('');

  // Desktop Agent state
  const [activeWindow, setActiveWindow] = useState<any | null>(null);

  useEffect(() => {
    loadHealth();
    loadProviders();
    loadGoogleAccounts().then((activeId) => {
      if (activeId) {
        loadDriveFiles(undefined, 'My Drive', activeId);
      }
    });

    // Check OAuth return callback parameters
    const params = new URLSearchParams(window.location.search);
    if (params.get('google_connected') === 'true') {
      toast.success('Đã kết nối tài khoản Google Drive thành công!');
      loadHealth();
      loadGoogleAccounts().then((activeId) => {
        loadDriveFiles(undefined, 'My Drive', activeId || undefined);
      });
      window.history.replaceState({}, document.title, window.location.pathname);
    } else if (params.get('google_error')) {
      toast.error(`Kết nối Google thất bại: ${params.get('google_error')}`);
      window.history.replaceState({}, document.title, window.location.pathname);
    }
  }, []);

  const loadProviders = async () => {
    try {
      const p = await apiClient.getProviders();
      setProviders(p);
    } catch (err) {
      console.warn('Failed to load AI providers:', err);
    }
  };

  useEffect(() => {
    if (!activeGoogleJobId) return;

    const interval = setInterval(async () => {
      try {
        const prog = await apiClient.getGoogleJobProgress(activeGoogleJobId);
        setGoogleJobProgress(prog);

        if (['completed', 'partially_completed', 'failed', 'cancelled'].includes(prog.status)) {
          clearInterval(interval);
          loadDriveFiles(selectedFolder || undefined);
        }
      } catch (err) {
        console.warn('Failed to poll Google job progress:', err);
      }
    }, 1500);

    return () => clearInterval(interval);
  }, [activeGoogleJobId, selectedFolder]);

  useEffect(() => {
    if (activeTab === 'google' && health?.google.connected) {
      loadGoogleAccounts().then((activeId) => {
        loadDriveFiles(undefined, undefined, activeId || undefined);
      });
    } else if (activeTab === 'slack' && health?.slack.connected) {
      loadSlackChannels();
    } else if (activeTab === 'desktop') {
      loadActiveWindow();
    } else if (activeTab === 'mappings') {
      loadMappings();
    }
  }, [activeTab, health]);

  useEffect(() => {
    if (selectedChannel) {
      loadChannelMessages(selectedChannel);
    }
  }, [selectedChannel]);

  const loadHealth = async () => {
    try {
      const data = await apiClient.getIntegrationHealth();
      setHealth(data);
    } catch (e) {
      console.error('Failed to load integration health:', e);
    }
  };

  const loadGoogleAccounts = async (): Promise<string | null> => {
    try {
      const accs = await apiClient.getGoogleAccounts();
      setGoogleAccounts(accs || []);

      // Check if any account has placeholder email, trigger background sync
      if (accs && accs.some((a: any) => !a.email || a.email.startsWith('connected.'))) {
        apiClient.syncGoogleProfile().then((res) => {
          if (res?.updated_count > 0) {
            apiClient.getGoogleAccounts().then(setGoogleAccounts);
            loadHealth();
          }
        }).catch(() => {});
      }

      if (accs && accs.length > 0) {
        const active = accs.find((a: any) => a.is_active) || accs[0];
        setSelectedAccountId((prev) => {
          if (prev && accs.some((a: any) => a.id === prev)) return prev;
          return active.id;
        });
        return active.id;
      } else {
        setSelectedAccountId(null);
        return null;
      }
    } catch (err) {
      console.warn('Failed to load Google accounts:', err);
      return null;
    }
  };

  const loadDriveFiles = async (
    folderId?: string,
    folderName?: string,
    targetAccountId?: string,
    modeOverride?: 'my_drive' | 'shared_with_me' | 'recent'
  ) => {
    setIsLoading(true);
    const accId = targetAccountId !== undefined ? targetAccountId : (selectedAccountId || undefined);
    const mode = modeOverride !== undefined ? modeOverride : driveViewMode;
    try {
      const res = await apiClient.listGoogleDrive(folderId, driveSearch, accId, mode);
      setDriveFiles(res.files || []);
      setSelectedFolder(folderId || null);
      if (folderName !== undefined) {
        setSelectedFolderName(folderName);
      } else if (!folderId) {
        setSelectedFolderName(
          mode === 'shared_with_me' ? 'Được chia sẻ với tôi' : mode === 'recent' ? 'Gần đây' : 'My Drive'
        );
      }
      if (res.account_id && !selectedAccountId) {
        setSelectedAccountId(res.account_id);
      }
    } catch (e) {
      console.error('Failed to load drive files:', e);
    } finally {
      setIsLoading(false);
    }
  };

  const handleSelectGoogleAccount = async (accId: string) => {
    setSelectedAccountId(accId);
    try {
      await apiClient.activateGoogleAccount(accId);
      await loadGoogleAccounts();
      await loadHealth();
      loadDriveFiles(undefined, undefined, accId, driveViewMode);
    } catch (err) {
      console.warn('Failed to activate account:', err);
      loadDriveFiles(undefined, undefined, accId, driveViewMode);
    }
  };

  const loadSlackChannels = async () => {
    try {
      const res = await apiClient.listSlackChannels();
      setSlackChannels(res.channels || []);
      if (res.channels.length > 0 && !selectedChannel) {
        setSelectedChannel(res.channels[0].id);
      }
    } catch (e) {
      console.error('Failed to load slack channels:', e);
    }
  };

  const loadChannelMessages = async (channelId: string) => {
    setIsLoading(true);
    try {
      const res = await apiClient.getSlackMessages(channelId);
      setChannelMessages(res.messages || []);
      setActiveMessage(null);
      setMessageTranslation(null);
      setReplyOptions([]);
    } catch (e) {
      console.error('Failed to load messages:', e);
    } finally {
      setIsLoading(false);
    }
  };

  const loadMappings = async () => {
    try {
      const res = await apiClient.getChannelMappings();
      setMappings(res.mappings || []);
    } catch (e) {
      console.error('Failed to load mappings:', e);
    }
  };

  const loadActiveWindow = async () => {
    try {
      const res = await apiClient.getActiveWindow();
      setActiveWindow(res);
    } catch (e) {
      console.error('Failed to load active window:', e);
    }
  };


  const handleDisconnectGoogle = async () => {
    const ok = await confirm({
      title: 'Ngắt kết nối Google Workspace',
      message: 'Bạn có chắc muốn ngắt kết nối tài khoản Google Workspace hiện tại? File cache tạm thời sẽ được giữ lại theo chính sách lưu trữ.',
      isDestructive: true,
      confirmText: 'Ngắt kết nối'
    });
    if (!ok) return;

    await apiClient.disconnectGoogle();
    await loadHealth();
    setDriveFiles([]);
    toast.info('Đã ngắt kết nối Google Workspace');
  };

  const handleConnectSlack = async (isMock: boolean = true) => {
    try {
      await apiClient.connectSlack({ is_mock: isMock });
      await loadHealth();
      loadSlackChannels();
      toast.success('Đã kết nối Slack Workspace thành công');
    } catch (e) {
      toast.error('Failed to connect Slack');
    }
  };

  const handleDisconnectSlack = async () => {
    const ok = await confirm({
      title: 'Ngắt kết nối Slack',
      message: 'Bạn có chắc muốn ngắt kết nối Slack Workspace?',
      isDestructive: true,
      confirmText: 'Ngắt kết nối'
    });
    if (!ok) return;

    await apiClient.disconnectSlack();
    await loadHealth();
    setSlackChannels([]);
    setChannelMessages([]);
    toast.info('Đã ngắt kết nối Slack');
  };

  const handlePauseGoogleJob = async () => {
    if (!activeGoogleJobId) return;
    await apiClient.pauseGoogleJob(activeGoogleJobId);
    const prog = await apiClient.getGoogleJobProgress(activeGoogleJobId);
    setGoogleJobProgress(prog);
  };

  const handleResumeGoogleJob = async () => {
    if (!activeGoogleJobId) return;
    await apiClient.resumeGoogleJob(activeGoogleJobId);
    const prog = await apiClient.getGoogleJobProgress(activeGoogleJobId);
    setGoogleJobProgress(prog);
  };

  const handleCancelGoogleJob = async () => {
    if (!activeGoogleJobId) return;
    const ok = await confirm({
      title: 'Hủy tác vụ dịch',
      message: 'Bạn có chắc muốn hủy tác vụ dịch Google Workspace này?',
      isDestructive: true,
      confirmText: 'Hủy tác vụ'
    });
    if (!ok) return;

    await apiClient.cancelGoogleJob(activeGoogleJobId);
    const prog = await apiClient.getGoogleJobProgress(activeGoogleJobId);
    setGoogleJobProgress(prog);
    toast.info('Đã hủy tác vụ dịch');
  };

  const handleRetryGoogleJob = async () => {
    if (!activeGoogleJobId) return;
    await apiClient.retryGoogleJob(activeGoogleJobId);
    const prog = await apiClient.getGoogleJobProgress(activeGoogleJobId);
    setGoogleJobProgress(prog);
    toast.info('Đã bắt đầu thử lại tác vụ');
  };

  const handleTranslateGoogleDoc = async (file: GoogleFileItem) => {
    setConfigGoogleFile(file);
  };

  const handleTranslateSlackMessage = async (msg: SlackMessage) => {
    setIsTranslatingSlack(true);
    setActiveMessage(msg);
    setMessageTranslation(null);
    try {
      const res = await apiClient.translateSlackMessage({
        channel_id: selectedChannel,
        channel_name: slackChannels.find(c => c.id === selectedChannel)?.name || '',
        message_ts: msg.ts,
        message_text: msg.text,
        thread_ts: msg.thread_ts || msg.ts,
        project_id: activeProject?.id || null,
        target_language: 'vi'
      });
      setMessageTranslation(res);
      toast.success('Đã dịch tin nhắn Slack');
    } catch (err: any) {
      toast.error(err.response?.data?.detail || 'Failed to translate Slack message');
    } finally {
      setIsTranslatingSlack(false);
    }
  };

  const handleGenerateSlackReplies = async (msg: SlackMessage) => {
    setIsGeneratingReplies(true);
    setActiveMessage(msg);
    try {
      const res = await apiClient.generateSlackReply({
        message_text: msg.text,
        thread_ts: msg.thread_ts || msg.ts,
        channel_id: selectedChannel,
        project_id: activeProject?.id || null
      });
      setReplyOptions(res.reply_options || []);
      toast.success('Đã tạo 4 phương án phản hồi');
    } catch (err: any) {
      toast.error(err.response?.data?.detail || 'Failed to generate replies');
    } finally {
      setIsGeneratingReplies(false);
    }
  };

  const copyReplyToClipboard = (text: string, index: number) => {
    navigator.clipboard.writeText(text);
    setCopiedReplyIndex(index);
    toast.success('Đã sao chép phản hồi vào clipboard');
    setTimeout(() => setCopiedReplyIndex(null), 2000);
  };

  const handleAddMapping = async () => {
    if (!newChannelId || !newChannelName) return;
    try {
      await apiClient.createChannelMapping({
        channel_id: newChannelId,
        channel_name: newChannelName,
        project_id: newProjectId || null,
        auto_translate: false,
        min_priority_score: 60
      });
      await loadMappings();
      setNewChannelId('');
      setNewChannelName('');
      toast.success('Đã lưu cấu hình mapping kênh Slack');
    } catch (err) {
      toast.error('Failed to save mapping');
    }
  };

  const handleCleanCache = async (all: boolean = false) => {
    try {
      const res = await apiClient.cleanIntegrationCache(all);
      toast.success(res.message || 'Đã dọn dẹp cache thành công');
      loadHealth();
    } catch (err) {
      toast.error('Failed to clean cache');
    }
  };

  const getPriorityBadge = (score: number) => {
    if (score >= 85) {
      return <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-rose-500/10 text-rose-700 dark:text-rose-400 border border-rose-500/20">P1 · High ({score})</span>;
    } else if (score >= 60) {
      return <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-amber-500/10 text-amber-700 dark:text-amber-400 border border-amber-500/20">P2 · Medium ({score})</span>;
    }
    return <span className="px-2 py-0.5 rounded text-[10px] font-medium bg-surface-subtle text-text-secondary border border-border-subtle">P3 · Low ({score})</span>;
  };

  const getCategoryBadge = (cat: string) => {
    switch (cat) {
      case 'BUG':
        return <span className="px-1.5 py-0.5 rounded text-[9px] font-bold uppercase bg-rose-500/10 text-rose-700 dark:text-rose-400 border border-rose-500/20">Bug</span>;
      case 'QUESTION':
        return <span className="px-1.5 py-0.5 rounded text-[9px] font-bold uppercase bg-sky-500/10 text-sky-700 dark:text-sky-400 border border-sky-500/20">Question</span>;
      case 'ACTION_REQUIRED':
        return <span className="px-1.5 py-0.5 rounded text-[9px] font-bold uppercase bg-amber-500/10 text-amber-700 dark:text-amber-400 border border-amber-500/20">Action Required</span>;
      case 'TECHNICAL':
        return <span className="px-1.5 py-0.5 rounded text-[9px] font-bold uppercase bg-indigo-500/10 text-indigo-700 dark:text-indigo-400 border border-indigo-500/20">Technical</span>;
      default:
        return <span className="px-1.5 py-0.5 rounded text-[9px] font-bold uppercase bg-surface-subtle text-text-secondary border border-border-subtle">FYI</span>;
    }
  };

  return (
    <div className="flex-1 flex flex-col h-screen overflow-hidden bg-canvas text-text-primary">
      {/* Top Header */}
      <header className="px-6 py-4 border-b border-border-subtle bg-surface flex items-center justify-between">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-base font-bold tracking-tight text-text-primary flex items-center gap-2">
              <Cloud className="w-5 h-5 text-primary" />
              Tích hợp & Kết nối
            </h1>
          </div>
        </div>

        <div className="flex items-center gap-3">
          {onOpenQuickTranslate && (
            <Button
              variant="secondary"
              size="sm"
              onClick={onOpenQuickTranslate}
              title="Mở cửa sổ dịch nhanh (Ctrl+Shift+T)"
            >
              <Sparkles className="w-4 h-4 mr-1.5 text-primary" />
              <span>Dịch nhanh (Ctrl+Shift+T)</span>
            </Button>
          )}

          <Button
            variant="ghost"
            size="sm"
            onClick={() => handleCleanCache(false)}
            title="Dọn bộ nhớ đệm kết nối"
          >
            <Clock className="w-3.5 h-3.5 mr-1.5 text-text-muted" />
            <span>Dọn cache</span>
          </Button>
        </div>
      </header>

      {/* Main Content Area */}
      <div className="flex-1 overflow-y-auto p-6 space-y-6">
        {/* Status Overview Grid */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {/* Google Card */}
          <Card className="p-5 bg-surface border border-border-subtle flex flex-col justify-between shadow-xs">
            <div className="flex items-start justify-between">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-lg bg-primary/10 border border-primary/20 flex items-center justify-center text-primary">
                  <Cloud className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="text-sm font-semibold text-text-primary">Google Workspace</h3>
                  <p className="text-xs text-text-muted">Drive · Docs · Sheets · Slides</p>
                </div>
              </div>
              {health?.google.connected ? (
                <Badge variant="success" size="sm" className="flex items-center gap-1">
                  <CheckCircle2 className="w-3 h-3" /> Connected
                </Badge>
              ) : (
                <Badge variant="neutral" size="sm">
                  Disconnected
                </Badge>
              )}
            </div>

            <div className="mt-4 pt-3 border-t border-border-subtle flex items-center justify-between text-xs">
              <span className="text-text-muted truncate max-w-[140px]" title={health?.google.email || ''}>
                {health?.google.connected ? (
                  health.google.total_accounts && health.google.total_accounts > 1
                    ? `${health.google.total_accounts} tài khoản Google`
                    : health.google.email
                ) : 'No account'}
              </span>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => setShowGoogleGuideModal(true)}
                  className="text-primary hover:underline text-[11px] flex items-center gap-1 font-medium"
                  title="Xem hướng dẫn kết nối OAuth & mẹo dùng 2 tài khoản"
                >
                  <HelpCircle className="w-3.5 h-3.5" />
                  <span>Hướng dẫn</span>
                </button>
                {health?.google.connected ? (
                  <button
                    onClick={handleDisconnectGoogle}
                    className="text-danger hover:underline text-[11px] font-medium"
                  >
                    Disconnect All
                  </button>
                ) : (
                  <button
                    onClick={() => setActiveTab('google')}
                    className="px-2.5 py-1 rounded bg-primary hover:bg-primary/90 text-white text-[11px] font-medium transition-colors"
                  >
                    Cấu hình & Kết nối
                  </button>
                )}
              </div>
            </div>
          </Card>

          {/* Slack Card */}
          <Card className="p-5 bg-surface border border-border-subtle flex flex-col justify-between shadow-xs">
            <div className="flex items-start justify-between">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-lg bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center text-emerald-500">
                  <MessageSquare className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="text-sm font-semibold text-text-primary">Slack Communication</h3>
                  <p className="text-xs text-text-muted">Channels · Threads · Reply AI</p>
                </div>
              </div>
              {health?.slack.connected ? (
                <Badge variant="success" size="sm" className="flex items-center gap-1">
                  <CheckCircle2 className="w-3 h-3" /> Connected
                </Badge>
              ) : (
                <Badge variant="neutral" size="sm">
                  Disconnected
                </Badge>
              )}
            </div>

            <div className="mt-4 pt-3 border-t border-border-subtle flex items-center justify-between text-xs">
              <span className="text-text-muted truncate max-w-[140px]">
                {health?.slack.connected ? health.slack.workspace_name : 'No workspace'}
              </span>
              {health?.slack.connected ? (
                <button
                  onClick={handleDisconnectSlack}
                  className="text-danger hover:underline text-[11px] font-medium"
                >
                  Disconnect
                </button>
              ) : (
                <button
                  onClick={() => handleConnectSlack(true)}
                  className="px-2.5 py-1 rounded bg-emerald-600 hover:bg-emerald-500 text-white text-[11px] font-medium transition-colors"
                >
                  Connect
                </button>
              )}
            </div>
          </Card>

          {/* Windows Desktop Agent Card */}
          <Card className="p-5 bg-surface border border-border-subtle flex flex-col justify-between shadow-xs">
            <div className="flex items-start justify-between">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-lg bg-amber-500/10 border border-amber-500/20 flex items-center justify-center text-amber-500">
                  <Monitor className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="text-sm font-semibold text-text-primary">Windows Agent</h3>
                  <p className="text-xs text-text-muted">Global Hotkeys · Clipboard</p>
                </div>
              </div>
              <Badge variant="success" size="sm" className="flex items-center gap-1">
                <CheckCircle2 className="w-3 h-3" /> Active
              </Badge>
            </div>

            <div className="mt-4 pt-3 border-t border-border-subtle flex items-center justify-between text-xs">
              <span className="text-text-muted font-mono text-[11px]">
                {health?.desktop.shortcuts.quick_translate || 'Ctrl+Shift+T'}
              </span>
              <button
                onClick={() => setActiveTab('desktop')}
                className="text-primary hover:underline text-[11px] font-medium"
              >
                Inspect App
              </button>
            </div>
          </Card>
        </div>

        {/* Tab Navigation */}
        <div className="flex items-center gap-1 border-b border-border-subtle">
          <button
            onClick={() => setActiveTab('google')}
            className={`px-4 py-2.5 text-xs font-semibold border-b-2 transition-all flex items-center gap-2 ${
              activeTab === 'google'
                ? 'border-primary text-primary'
                : 'border-transparent text-text-muted hover:text-text-primary'
            }`}
          >
            <Cloud className="w-4 h-4" />
            <span>Google Drive Explorer</span>
          </button>

          <button
            onClick={() => setActiveTab('slack')}
            className={`px-4 py-2.5 text-xs font-semibold border-b-2 transition-all flex items-center gap-2 ${
              activeTab === 'slack'
                ? 'border-emerald-500 text-emerald-500'
                : 'border-transparent text-text-muted hover:text-text-primary'
            }`}
          >
            <MessageSquare className="w-4 h-4" />
            <span>Slack Companion</span>
          </button>

          <button
            onClick={() => setActiveTab('mappings')}
            className={`px-4 py-2.5 text-xs font-semibold border-b-2 transition-all flex items-center gap-2 ${
              activeTab === 'mappings'
                ? 'border-primary text-primary'
                : 'border-transparent text-text-muted hover:text-text-primary'
            }`}
          >
            <Hash className="w-4 h-4" />
            <span>Channel Mappings</span>
          </button>

          <button
            onClick={() => setActiveTab('desktop')}
            className={`px-4 py-2.5 text-xs font-semibold border-b-2 transition-all flex items-center gap-2 ${
              activeTab === 'desktop'
                ? 'border-amber-500 text-amber-500'
                : 'border-transparent text-text-muted hover:text-text-primary'
            }`}
          >
            <Monitor className="w-4 h-4" />
            <span>Desktop Agent & Profiles</span>
          </button>
        </div>

        {/* TAB 1: Google Drive Browser */}
        {activeTab === 'google' && (
          <div className="space-y-4">
            {translateSuccess && (
              <div className="p-3 rounded-lg bg-emerald-500/15 border border-emerald-500/30 text-emerald-300 text-xs flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                  <span>{translateSuccess}</span>
                </div>
                <button onClick={() => setTranslateSuccess(null)} className="text-emerald-400 hover:text-emerald-200">✕</button>
              </div>
            )}

            {/* Live Progress Card */}
            {googleJobProgress && (
              <Card className="p-4 bg-surface border border-border-subtle shadow-md space-y-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3 min-w-0">
                    <div className="w-9 h-9 rounded-lg bg-surface-elevated border border-border-subtle flex items-center justify-center flex-shrink-0">
                      <FileFormatIcon type={googleJobProgress.file_type} name={googleJobProgress.filename} size="sm" />
                    </div>
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <h4 className="text-sm font-semibold text-text-primary truncate max-w-md">
                          {googleJobProgress.filename}
                        </h4>
                        <span className={`text-[10px] uppercase font-semibold px-2 py-0.5 rounded border ${
                          googleJobProgress.status === 'completed'
                            ? 'bg-emerald-500/20 text-emerald-500 border-emerald-500/30'
                            : googleJobProgress.status === 'failed'
                            ? 'bg-danger/20 text-danger border-danger/30'
                            : googleJobProgress.status === 'paused'
                            ? 'bg-amber-500/20 text-amber-500 border-amber-500/30'
                            : 'bg-primary/20 text-primary border-primary/30 animate-pulse'
                        }`}>
                          {googleJobProgress.status}
                        </span>
                      </div>
                      <p className="text-xs text-text-muted mt-0.5">
                        {googleJobProgress.current_stage || 'Đang xử lý...'}
                      </p>
                    </div>
                  </div>

                  {/* Controls */}
                  <div className="flex items-center gap-2">
                    {googleJobProgress.status === 'translating' && (
                      <Button
                        variant="secondary"
                        size="sm"
                        onClick={handlePauseGoogleJob}
                        title="Tạm dừng"
                      >
                        <Pause className="w-3.5 h-3.5 mr-1" />
                        <span>Tạm dừng</span>
                      </Button>
                    )}

                    {googleJobProgress.status === 'paused' && (
                      <Button
                        variant="primary"
                        size="sm"
                        onClick={handleResumeGoogleJob}
                        title="Tiếp tục"
                      >
                        <Play className="w-3.5 h-3.5 mr-1" />
                        <span>Tiếp tục</span>
                      </Button>
                    )}

                    {['queued', 'analyzing', 'segmenting', 'translating', 'rendering'].includes(googleJobProgress.status) && (
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={handleCancelGoogleJob}
                        className="text-text-muted hover:text-danger"
                        title="Hủy tác vụ"
                      >
                        <XCircle className="w-3.5 h-3.5 mr-1" />
                        <span>Hủy</span>
                      </Button>
                    )}

                    {['failed', 'partially_completed'].includes(googleJobProgress.status) && (
                      <Button
                        variant="secondary"
                        size="sm"
                        onClick={handleRetryGoogleJob}
                        title="Thử lại các đoạn lỗi"
                      >
                        <RotateCcw className="w-3.5 h-3.5 mr-1 text-amber-500" />
                        <span>Thử lại</span>
                      </Button>
                    )}

                    {/* Review Segments button */}
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={() => setReviewGoogleJob({
                        jobId: googleJobProgress.job_id,
                        fileTitle: googleJobProgress.filename,
                        fileType: googleJobProgress.file_type || 'gdoc',
                        outputUrl: googleJobProgress.output_path
                      })}
                    >
                      <Eye className="w-3.5 h-3.5 mr-1 text-primary" />
                      <span>Xem lại phân đoạn</span>
                    </Button>

                    {/* Open Safe Copy on Drive */}
                    {['completed', 'partially_completed'].includes(googleJobProgress.status) && googleJobProgress.output_path && (
                      <a
                        href={googleJobProgress.output_path}
                        target="_blank"
                        rel="noreferrer"
                        className="px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-medium flex items-center gap-1.5 transition-colors shadow-xs"
                      >
                        <ExternalLink className="w-3.5 h-3.5" />
                        <span>Mở bản sao Drive</span>
                      </a>
                    )}
                  </div>
                </div>

                {/* Progress Bar */}
                <div className="space-y-1.5">
                  <div className="flex items-center justify-between text-[11px] text-text-muted font-medium">
                    <span>Tiến độ dịch thuật</span>
                    <span>{googleJobProgress.progress_percent}% ({googleJobProgress.completed_segments}/{googleJobProgress.total_segments} phân đoạn)</span>
                  </div>
                  <div className="w-full bg-surface-elevated rounded-full h-2 overflow-hidden border border-border-subtle">
                    <div
                      className="bg-primary h-full transition-all duration-300 rounded-full"
                      style={{ width: `${Math.min(100, Math.max(0, googleJobProgress.progress_percent || 0))}%` }}
                    />
                  </div>
                </div>
              </Card>
            )}

            {/* Google Account Switcher Bar */}
            {googleAccounts.length > 0 && (
              <GoogleAccountSwitcher
                accounts={googleAccounts}
                selectedAccountId={selectedAccountId}
                onSelectAccount={handleSelectGoogleAccount}
                onRefreshAccounts={async () => {
                  await loadHealth();
                  const actId = await loadGoogleAccounts();
                  loadDriveFiles(undefined, undefined, actId || undefined, driveViewMode);
                }}
              />
            )}

            {!health?.google.connected && googleAccounts.length === 0 ? (
              <GoogleCredentialsDropzone
                onOpenGuide={() => setShowGoogleGuideModal(true)}
                onConnected={async () => {
                  await loadHealth();
                  const actId = await loadGoogleAccounts();
                  loadDriveFiles(undefined, undefined, actId || undefined, driveViewMode);
                }}
              />
            ) : (
              <GoogleDriveExplorer
                files={driveFiles}
                isLoading={isLoading}
                selectedFolder={selectedFolder}
                folderName={selectedFolderName}
                searchQuery={driveSearch}
                viewMode={driveViewMode}
                onViewModeChange={(mode) => {
                  setDriveViewMode(mode);
                  loadDriveFiles(undefined, undefined, selectedAccountId || undefined, mode);
                }}
                onSearchChange={(q) => {
                  setDriveSearch(q);
                  loadDriveFiles(selectedFolder || undefined, undefined, selectedAccountId || undefined);
                }}
                onOpenFolder={(fId, fName) => loadDriveFiles(fId || undefined, fName, selectedAccountId || undefined)}
                onTranslateFile={(file) => setConfigGoogleFile(file)}
                onRefresh={() => loadDriveFiles(selectedFolder || undefined, undefined, selectedAccountId || undefined)}
              />
            )}
          </div>
        )}

        {/* TAB 2: Slack Companion */}
        {activeTab === 'slack' && (
          <div className="space-y-4">
            {!health?.slack.connected ? (
              <Card className="p-12 text-center bg-surface border border-border-subtle">
                <EmptyState
                  icon={<MessageSquare className="w-10 h-10" />}
                  title="Slack Not Connected"
                  description="Connect your Slack workspace to inspect channels, analyze message priorities, and generate instant replies."
                  action={
                    <Button variant="primary" onClick={() => handleConnectSlack(true)}>
                      Enable Sandbox Connection
                    </Button>
                  }
                />
              </Card>
            ) : (
              <div className="grid grid-cols-12 gap-6">
                {/* Channel List & Messages */}
                <div className="col-span-12 lg:col-span-7 space-y-4">
                  {/* Channel Switcher */}
                  <Card className="p-3 bg-surface border border-border-subtle flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <Hash className="w-4 h-4 text-emerald-500 shrink-0" />
                      <span className="text-xs font-semibold text-text-muted shrink-0">Channel:</span>
                      <Select
                        value={selectedChannel}
                        onChange={(val) => setSelectedChannel(val)}
                        size="sm"
                        triggerClassName="min-w-[170px]"
                        options={slackChannels.map(c => ({
                          value: c.id,
                          label: `#${c.name}`,
                          sublabel: c.is_private ? 'Private' : undefined
                        }))}
                      />
                    </div>

                    <span className="text-xs text-text-muted font-mono">
                      {channelMessages.length} messages
                    </span>
                  </Card>

                  {/* Messages Feed */}
                  <Card className="p-0 bg-surface border border-border-subtle overflow-hidden divide-y divide-border-subtle max-h-[600px] overflow-y-auto">
                    {channelMessages.map(msg => (
                      <div
                        key={msg.ts}
                        className={`p-4 hover:bg-surface-elevated/40 transition-colors space-y-2 ${
                          activeMessage?.ts === msg.ts ? 'bg-surface-elevated/60 border-l-2 border-primary' : ''
                        }`}
                      >
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-2">
                            <div className="w-6 h-6 rounded-full bg-emerald-500/15 text-emerald-500 font-bold text-[10px] flex items-center justify-center">
                              {msg.username?.charAt(0) || 'U'}
                            </div>
                            <span className="text-xs font-semibold text-text-primary">
                              {msg.username || msg.user}
                            </span>
                          </div>

                          <div className="flex items-center gap-2">
                            {msg.analysis && getCategoryBadge(msg.analysis.category)}
                            {msg.analysis && getPriorityBadge(msg.analysis.priority_score)}
                          </div>
                        </div>

                        <p className="text-xs text-text-secondary leading-relaxed font-sans">
                          {msg.text}
                        </p>

                        <div className="flex items-center justify-between pt-1 text-[11px]">
                          <span className="text-text-muted font-mono">
                            {msg.thread_ts && `Thread (${msg.reply_count || 1} replies)`}
                          </span>

                          <div className="flex items-center gap-2">
                            <Button
                              variant="secondary"
                              size="sm"
                              onClick={() => handleTranslateSlackMessage(msg)}
                              disabled={isTranslatingSlack}
                            >
                              Translate Thread
                            </Button>
                            <Button
                              variant="secondary"
                              size="sm"
                              onClick={() => handleGenerateSlackReplies(msg)}
                              disabled={isGeneratingReplies}
                              className="text-emerald-500 hover:text-emerald-600"
                            >
                              Suggest Replies
                            </Button>
                          </div>
                        </div>
                      </div>
                    ))}
                  </Card>
                </div>

                {/* Companion Side Panel: Translation & Replies */}
                <div className="col-span-12 lg:col-span-5 space-y-4">
                  {/* Translation Drawer */}
                  {messageTranslation && (
                    <Card className="p-4 bg-surface border border-primary/30 space-y-3 shadow-md">
                      <div className="flex items-center justify-between border-b border-border-subtle pb-2">
                        <h4 className="text-xs font-bold uppercase text-primary flex items-center gap-1.5">
                          <FileText className="w-3.5 h-3.5" />
                          Thread Context Translation
                        </h4>
                        <span className="text-[10px] text-text-muted font-mono">JA → VI</span>
                      </div>

                      <div className="p-3 bg-surface-elevated rounded-lg border border-border-subtle text-xs text-emerald-500 leading-relaxed">
                        {messageTranslation.translation}
                      </div>

                      {messageTranslation.used_glossary?.length > 0 && (
                        <div className="text-[11px] text-text-muted">
                          <span className="text-text-secondary font-semibold">Glossary Used: </span>
                          {messageTranslation.used_glossary.map((g: any, i: number) => (
                            <span key={i} className="px-1.5 py-0.5 bg-surface-elevated border border-border-subtle text-primary rounded mr-1">
                              {g.source_term} → {g.target_term}
                            </span>
                          ))}
                        </div>
                      )}
                    </Card>
                  )}

                  {/* Japanese Reply Generator */}
                  {replyOptions.length > 0 && (
                    <Card className="p-4 bg-surface border border-border-subtle space-y-3 shadow-md">
                      <div className="flex items-center justify-between border-b border-border-subtle pb-2">
                        <div className="flex items-center gap-1.5">
                          <Sparkles className="w-3.5 h-3.5 text-primary" />
                          <h4 className="text-xs font-bold uppercase text-text-primary">4 Reply Variations</h4>
                        </div>
                        <Badge variant="warning" size="sm">
                          Never auto-sends
                        </Badge>
                      </div>

                      <div className="space-y-2">
                        {replyOptions.map((opt, i) => (
                          <div key={i} className="p-3 bg-surface-elevated rounded-lg border border-border-subtle space-y-1.5">
                            <div className="flex items-center justify-between">
                              <span className="text-[10px] font-bold uppercase px-1.5 py-0.5 rounded bg-surface text-emerald-500 font-mono border border-border-subtle">
                                {opt.style}
                              </span>
                              <span className="text-[10px] text-text-muted">{opt.description}</span>
                            </div>
                            <p className="text-xs text-text-primary font-sans leading-relaxed">{opt.text}</p>
                            <div className="flex justify-end pt-1">
                              <Button
                                variant="secondary"
                                size="sm"
                                onClick={() => copyReplyToClipboard(opt.text, i)}
                              >
                                {copiedReplyIndex === i ? (
                                  <>
                                    <Check className="w-3 h-3 text-emerald-500 mr-1" />
                                    <span className="text-emerald-500">Copied</span>
                                  </>
                                ) : (
                                  <>
                                    <Copy className="w-3 h-3 mr-1" />
                                    <span>Copy Reply</span>
                                  </>
                                )}
                              </Button>
                            </div>
                          </div>
                        ))}
                      </div>
                    </Card>
                  )}

                  {!messageTranslation && replyOptions.length === 0 && (
                    <Card className="p-8 text-center bg-surface border border-border-subtle">
                      <EmptyState
                        icon={<MessageSquare className="w-8 h-8" />}
                        title="No active message selected"
                        description="Select a message to translate with thread context or generate Japanese reply variations."
                      />
                    </Card>
                  )}
                </div>
              </div>
            )}
          </div>
        )}

        {/* TAB 3: Channel Mappings */}
        {activeTab === 'mappings' && (
          <div className="space-y-4">
            <Card className="p-4 bg-surface border border-border-subtle space-y-3">
              <h3 className="text-xs font-bold uppercase text-text-muted">Map Channel to Project Workspace</h3>
              <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
                <Input
                  value={newChannelId}
                  onChange={(e) => setNewChannelId(e.target.value)}
                  placeholder="Channel ID (e.g. C01ABC)"
                />
                <Input
                  value={newChannelName}
                  onChange={(e) => setNewChannelName(e.target.value)}
                  placeholder="Channel Name (e.g. project-abc)"
                />
                <Select
                  value={newProjectId}
                  onChange={(val) => setNewProjectId(val)}
                  size="md"
                  placeholder="-- Select Project --"
                  className="w-full"
                  options={[
                    { value: '', label: '-- Select Project --' },
                    ...projects.map((p) => ({
                      value: p.id,
                      label: p.name,
                      sublabel: p.code
                    }))
                  ]}
                />
                <Button
                  variant="primary"
                  onClick={handleAddMapping}
                >
                  Save Mapping
                </Button>
              </div>
            </Card>

            <Card className="p-0 bg-surface border border-border-subtle overflow-hidden">
              <div className="p-4 border-b border-border-subtle text-xs font-bold uppercase text-text-muted">
                Active Mappings ({mappings.length})
              </div>
              <div className="divide-y divide-border-subtle text-xs">
                {mappings.length === 0 ? (
                  <div className="p-8 text-center text-text-muted">
                    No channel mappings configured yet.
                  </div>
                ) : (
                  mappings.map(m => (
                    <div key={m.id} className="p-4 flex items-center justify-between">
                      <div className="flex items-center gap-3">
                        <Hash className="w-4 h-4 text-emerald-500" />
                        <div>
                          <span className="font-semibold text-text-primary">#{m.channel_name}</span>
                          <span className="text-text-muted text-[11px] ml-2 font-mono">({m.channel_id})</span>
                        </div>
                      </div>
                      <div className="flex items-center gap-4">
                        <span className="text-primary font-medium">
                          → {projects.find(p => p.id === m.project_id)?.name || 'Default Global'}
                        </span>
                        <Badge variant="neutral" size="sm">
                          Min Score: {m.min_priority_score}
                        </Badge>
                      </div>
                    </div>
                  ))
                )}
              </div>
            </Card>
          </div>
        )}

        {/* TAB 4: Desktop Agent & Profiles */}
        {activeTab === 'desktop' && (
          <div className="space-y-4">
            <Card className="p-5 bg-surface border border-border-subtle space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-sm font-semibold text-text-primary flex items-center gap-2">
                    <Monitor className="w-4 h-4 text-amber-500" />
                    Active Windows Desktop Context
                  </h3>
                  <p className="text-xs text-text-muted mt-0.5">
                    Auto-detects active foreground application to adapt translation tone & load matching projects.
                  </p>
                </div>
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={loadActiveWindow}
                >
                  <RefreshCw className="w-3.5 h-3.5 mr-1" />
                  <span>Refresh Active Window</span>
                </Button>
              </div>

              {activeWindow && (
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4 pt-3 border-t border-border-subtle text-xs">
                  <div className="p-3 bg-surface-elevated rounded-lg border border-border-subtle">
                    <span className="text-text-muted block text-[10px] uppercase font-semibold">Foreground Process</span>
                    <span className="text-text-primary font-mono font-medium">{activeWindow.process_name || 'N/A'}</span>
                  </div>
                  <div className="p-3 bg-surface-elevated rounded-lg border border-border-subtle">
                    <span className="text-text-muted block text-[10px] uppercase font-semibold">Application Profile Mode</span>
                    <span className="text-amber-500 font-medium capitalize">{activeWindow.profile?.mode || 'Generic'} ({activeWindow.profile?.style || 'Auto'})</span>
                  </div>
                  <div className="p-3 bg-surface-elevated rounded-lg border border-border-subtle">
                    <span className="text-text-muted block text-[10px] uppercase font-semibold">Window Title</span>
                    <span className="text-text-secondary truncate block" title={activeWindow.title}>{activeWindow.title || 'N/A'}</span>
                  </div>
                </div>
              )}
            </Card>
          </div>
        )}

        {/* Google Workspace Translation Config Modal */}
        {configGoogleFile && (
          <GoogleTranslateConfigModal
            file={configGoogleFile}
            projects={projects}
            activeProject={activeProject}
            providers={providers}
            accountId={selectedAccountId}
            onClose={() => setConfigGoogleFile(null)}
            onStartJob={(jobData) => {
              setActiveGoogleJobId(jobData.job_id);
              apiClient.getGoogleJobProgress(jobData.job_id).then(setGoogleJobProgress);
            }}
          />
        )}

        {/* Google Workspace Segment Review Modal */}
        {reviewGoogleJob && (
          <GoogleSegmentReviewModal
            jobId={reviewGoogleJob.jobId}
            fileTitle={reviewGoogleJob.fileTitle}
            fileType={reviewGoogleJob.fileType}
            outputUrl={reviewGoogleJob.outputUrl}
            onClose={() => setReviewGoogleJob(null)}
          />
        )}

        {/* Google Setup & Multi-Account Guide Modal */}
        {showGoogleGuideModal && (
          <GoogleSetupGuideModal
            onClose={() => setShowGoogleGuideModal(false)}
          />
        )}
      </div>
    </div>
  );
};
