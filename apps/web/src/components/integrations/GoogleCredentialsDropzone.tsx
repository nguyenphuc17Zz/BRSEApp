import React, { useState, useEffect, useRef } from 'react';
import {
  UploadCloud,
  CheckCircle2,
  FileJson,
  Key,
  ExternalLink,
  ShieldCheck,
  AlertCircle,
  HelpCircle,
  RefreshCw,
  LogIn,
  Eye,
  EyeOff,
  Check,
  Copy,
  Sparkles
} from 'lucide-react';
import { apiClient } from '../../api/client';
import { useToast } from '../../context/ToastContext';

interface GoogleCredentialsDropzoneProps {
  onOpenGuide: () => void;
  onConnected?: () => void;
}

export const GoogleCredentialsDropzone: React.FC<GoogleCredentialsDropzoneProps> = ({
  onOpenGuide,
  onConnected
}) => {
  const toast = useToast();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [inputMode, setInputMode] = useState<'manual' | 'dropzone'>('manual');
  const [isDragging, setIsDragging] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [isSavingManual, setIsSavingManual] = useState(false);

  // Manual inputs - prefilled with client_id from user's Google Cloud screen
  const [manualClientId, setManualClientId] = useState(
    '673906047017-1dqq9geb9n1ldq5p5l15k4ferwv9bb2fg.apps.googleusercontent.com'
  );
  const [manualClientSecret, setManualClientSecret] = useState('');
  const [manualProjectId, setManualProjectId] = useState('AutomationTranslate');
  const [showSecret, setShowSecret] = useState(false);

  const [config, setConfig] = useState<{
    is_configured: boolean;
    client_id_masked: string;
    project_id: string;
    redirect_uri: string;
  } | null>(null);
  const [redirectWarning, setRedirectWarning] = useState<string | null>(null);

  useEffect(() => {
    loadConfig();
  }, []);

  const loadConfig = async () => {
    try {
      const data = await apiClient.getGoogleConfig();
      setConfig(data);
      if (data.is_configured) {
        setInputMode('manual');
      }
    } catch (err) {
      console.warn('Failed to load Google OAuth config:', err);
    }
  };

  const handleProcessFile = async (file: File) => {
    if (!file.name.endsWith('.json')) {
      toast.error('Vui lòng chọn file định dạng .json (ví dụ: credentials.json hoặc client_secret_*.json)');
      return;
    }

    setIsUploading(true);
    try {
      const text = await file.text();
      const json = JSON.parse(text);

      const res = await apiClient.uploadGoogleCredentials(json);
      toast.success(res.message || 'Đã nạp file credentials.json thành công!');
      if (res.redirect_warning) {
        setRedirectWarning(res.redirect_warning);
      } else {
        setRedirectWarning(null);
      }
      await loadConfig();
    } catch (err: any) {
      console.error('Failed to parse or upload credentials:', err);
      toast.error(err.response?.data?.detail || err.message || 'Không thể nạp file JSON này. Vui lòng kiểm tra lại cấu trúc.');
    } finally {
      setIsUploading(false);
    }
  };

  const handleSaveManual = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!manualClientId.trim()) {
      toast.error('Vui lòng điền Client ID.');
      return;
    }
    if (!manualClientSecret.trim()) {
      toast.error('Vui lòng điền Client Secret (bấm + Add secret trên Google Cloud để lấy).');
      return;
    }

    setIsSavingManual(true);
    try {
      const payload = {
        client_id: manualClientId.trim(),
        client_secret: manualClientSecret.trim(),
        project_id: manualProjectId.trim() || 'AutomationTranslate',
        redirect_uris: ['http://127.0.0.1:8000/api/integrations/google/callback']
      };

      const res = await apiClient.uploadGoogleCredentials(payload);
      toast.success(res.message || 'Đã lưu cấu hình Google OAuth thành công!');
      if (res.redirect_warning) {
        setRedirectWarning(res.redirect_warning);
      } else {
        setRedirectWarning(null);
      }
      await loadConfig();
    } catch (err: any) {
      console.error('Failed to save manual credentials:', err);
      toast.error(err.response?.data?.detail || err.message || 'Lưu cấu hình thất bại. Vui lòng kiểm tra lại.');
    } finally {
      setIsSavingManual(false);
    }
  };

  const onDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const onDragLeave = () => {
    setIsDragging(false);
  };

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      handleProcessFile(e.dataTransfer.files[0]);
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      handleProcessFile(e.target.files[0]);
    }
  };

  const handleStartGoogleOAuth = async () => {
    try {
      const res = await apiClient.getGoogleLoginUrl();
      if (res.auth_url) {
        window.location.href = res.auth_url;
      }
    } catch (err: any) {
      toast.error(err.response?.data?.detail || 'Không thể tạo URL đăng nhập Google.');
    }
  };

  return (
    <div className="p-8 bg-slate-900/90 border border-slate-800 rounded-2xl shadow-xl space-y-6 max-w-3xl mx-auto">
      {/* Header Info */}
      <div className="flex items-start justify-between">
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <h3 className="text-base font-semibold text-white">
              Kết Nối Google Workspace (Docs, Sheets, Slides)
            </h3>
            <span className="px-2 py-0.5 rounded-full text-[11px] font-medium bg-sky-500/10 border border-sky-500/30 text-sky-400">
              OAuth 2.0
            </span>
          </div>
          <p className="text-sm text-slate-400">
            Dán Client ID & Secret hoặc kéo thả file JSON từ Google Cloud Console.
          </p>
        </div>

        <button
          onClick={onOpenGuide}
          className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs flex items-center gap-1.5 border border-slate-700 transition-colors"
        >
          <HelpCircle className="w-4 h-4 text-sky-400" />
          <span>Hướng dẫn thiết lập</span>
        </button>
      </div>

      {/* Mode Switcher Tabs */}
      {!config?.is_configured && (
        <div className="flex items-center p-1 rounded-xl bg-slate-950/80 border border-slate-800">
          <button
            type="button"
            onClick={() => setInputMode('manual')}
            className={`flex-1 py-2 px-3 rounded-lg text-xs font-semibold flex items-center justify-center gap-2 transition-all ${
              inputMode === 'manual'
                ? 'bg-sky-600 text-white shadow-md shadow-sky-900/40'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            <Key className="w-3.5 h-3.5" />
            <span>Nhập tay Client ID & Secret (Khuyên dùng)</span>
          </button>
          <button
            type="button"
            onClick={() => setInputMode('dropzone')}
            className={`flex-1 py-2 px-3 rounded-lg text-xs font-semibold flex items-center justify-center gap-2 transition-all ${
              inputMode === 'dropzone'
                ? 'bg-sky-600 text-white shadow-md shadow-sky-900/40'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            <FileJson className="w-3.5 h-3.5" />
            <span>Kéo thả file JSON</span>
          </button>
        </div>
      )}

      {/* TAB 1: MANUAL INPUT FORM */}
      {!config?.is_configured && inputMode === 'manual' && (
        <form onSubmit={handleSaveManual} className="space-y-4">
          {/* Quick instructions for user's screen */}
          <div className="p-3.5 rounded-xl bg-sky-500/10 border border-sky-500/25 text-sky-200 text-xs space-y-2">
            <div className="flex items-center gap-2 font-semibold text-sky-300">
              <Sparkles className="w-4 h-4 text-sky-400 flex-shrink-0" />
              <span>Cách lấy Client Secret trong 30 giây:</span>
            </div>
            <ol className="list-decimal list-inside space-y-1 text-slate-300 pl-1 leading-relaxed">
              <li>
                Trên tab Google Cloud (màn hình bạn vừa chụp), bấm nút{' '}
                <strong className="text-white bg-slate-800 px-1.5 py-0.5 rounded border border-slate-700">
                  + Add secret
                </strong>
                .
              </li>
              <li>
                Google sẽ hiện popup chứa <strong>Client secret</strong> mới $\rightarrow$ Bấm icon Copy bên cạnh secret đó.
              </li>
              <li>Dán mã secret vừa copy vào ô bên dưới rồi bấm <strong>Lưu & Kích Hoạt</strong>.</li>
            </ol>
          </div>

          <div className="space-y-3.5">
            <div>
              <label className="block text-xs font-medium text-slate-300 mb-1.5">
                Client ID (đã tự động điền từ Google Cloud của bạn)
              </label>
              <input
                type="text"
                value={manualClientId}
                onChange={(e) => setManualClientId(e.target.value)}
                placeholder="673906047017-xxxx.apps.googleusercontent.com"
                className="w-full bg-slate-950 border border-slate-700 focus:border-sky-500 focus:ring-1 focus:ring-sky-500 rounded-xl px-3.5 py-2.5 text-xs text-sky-300 font-mono transition-colors"
                required
              />
            </div>

            <div>
              <label className="block text-xs font-medium text-slate-300 mb-1.5">
                Client Secret <span className="text-rose-400">*</span>
              </label>
              <div className="relative">
                <input
                  type={showSecret ? 'text' : 'password'}
                  value={manualClientSecret}
                  onChange={(e) => setManualClientSecret(e.target.value)}
                  placeholder="Dán mã secret vừa tạo tại đây (ví dụ: GOCSPX-...)"
                  className="w-full bg-slate-950 border border-slate-700 focus:border-sky-500 focus:ring-1 focus:ring-sky-500 rounded-xl px-3.5 py-2.5 text-xs text-white font-mono pr-10 transition-colors"
                  required
                />
                <button
                  type="button"
                  onClick={() => setShowSecret(!showSecret)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-200"
                >
                  {showSecret ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
            </div>

            <div>
              <label className="block text-xs font-medium text-slate-400 mb-1.5">
                Project ID
              </label>
              <input
                type="text"
                value={manualProjectId}
                onChange={(e) => setManualProjectId(e.target.value)}
                placeholder="AutomationTranslate"
                className="w-full bg-slate-950/60 border border-slate-800 focus:border-sky-500 rounded-xl px-3.5 py-2 text-xs text-slate-300 font-mono transition-colors"
              />
            </div>
          </div>

          <button
            type="submit"
            disabled={isSavingManual}
            className="w-full py-2.5 rounded-xl bg-sky-600 hover:bg-sky-500 disabled:opacity-50 text-white text-xs font-semibold transition-all flex items-center justify-center gap-2 shadow-lg shadow-sky-600/25"
          >
            {isSavingManual ? (
              <>
                <RefreshCw className="w-4 h-4 animate-spin" />
                <span>Đang lưu cấu hình...</span>
              </>
            ) : (
              <>
                <Check className="w-4 h-4" />
                <span>Lưu & Kích Hoạt Cấu Hình</span>
              </>
            )}
          </button>
        </form>
      )}

      {/* TAB 2: DROPZONE FILE JSON */}
      {(!config?.is_configured && inputMode === 'dropzone') || config?.is_configured ? (
        <>
          <input
            type="file"
            ref={fileInputRef}
            onChange={handleFileChange}
            accept=".json,application/json"
            className="hidden"
          />

          <div
            onDragOver={onDragOver}
            onDragLeave={onDragLeave}
            onDrop={onDrop}
            onClick={() => fileInputRef.current?.click()}
            className={`border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-all duration-200 ${
              isDragging
                ? 'border-sky-400 bg-sky-950/20 scale-[1.01]'
                : config?.is_configured
                ? 'border-emerald-500/40 bg-emerald-950/10 hover:border-emerald-500/60'
                : 'border-slate-700 hover:border-sky-500/60 bg-slate-850/50'
            }`}
          >
            <div className="flex flex-col items-center justify-center gap-3">
              <div
                className={`w-14 h-14 rounded-2xl flex items-center justify-center transition-colors ${
                  config?.is_configured
                    ? 'bg-emerald-500/15 text-emerald-400 border border-emerald-500/30'
                    : 'bg-sky-500/15 text-sky-400 border border-sky-500/30'
                }`}
              >
                {isUploading ? (
                  <RefreshCw className="w-7 h-7 animate-spin" />
                ) : config?.is_configured ? (
                  <CheckCircle2 className="w-7 h-7" />
                ) : (
                  <UploadCloud className="w-7 h-7" />
                )}
              </div>

              <div>
                <p className="text-sm font-semibold text-white">
                  {config?.is_configured ? (
                    <span className="text-emerald-300">Đã cấu hình Google OAuth thành công!</span>
                  ) : (
                    'Kéo thả file credentials.json vào đây'
                  )}
                </p>
                <p className="text-xs text-slate-400 mt-1">
                  {config?.is_configured ? (
                    <span>Bấm vào đây nếu bạn muốn thay đổi hoặc tải lên file JSON khác</span>
                  ) : (
                    <span>hoặc bấm để chọn file từ máy tính (hỗ trợ file client_secret_*.json)</span>
                  )}
                </p>
              </div>
            </div>
          </div>
        </>
      ) : null}

      {/* Config Details if Configured */}
      {config?.is_configured && (
        <div className="p-4 rounded-xl bg-slate-850 border border-slate-800 space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2 text-xs font-semibold text-white">
              <ShieldCheck className="w-4 h-4 text-emerald-400" />
              <span>Thông tin OAuth Client đang kích hoạt:</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="px-2 py-0.5 rounded text-[11px] bg-emerald-500/10 text-emerald-400 border border-emerald-500/30">
                Active
              </span>
              <button
                onClick={() => {
                  setConfig((prev) => (prev ? { ...prev, is_configured: false } : null));
                  setInputMode('manual');
                }}
                className="text-[11px] text-slate-400 hover:text-sky-300 underline transition-colors"
              >
                Chỉnh sửa
              </button>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3 text-xs">
            <div className="p-2.5 rounded-lg bg-slate-900 border border-slate-800 space-y-1">
              <span className="text-slate-400">Project ID:</span>
              <p className="font-mono text-white font-medium truncate">
                {config.project_id || 'AutomationTranslate'}
              </p>
            </div>
            <div className="p-2.5 rounded-lg bg-slate-900 border border-slate-800 space-y-1">
              <span className="text-slate-400">Client ID:</span>
              <p className="font-mono text-sky-300 truncate" title={config.client_id_masked}>
                {config.client_id_masked}
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Redirect Warning Alert if applicable */}
      {redirectWarning && (
        <div className="p-3.5 rounded-xl bg-amber-500/10 border border-amber-500/30 text-amber-200 text-xs flex items-start gap-2.5">
          <AlertCircle className="w-4 h-4 text-amber-400 flex-shrink-0 mt-0.5" />
          <p className="leading-relaxed">{redirectWarning}</p>
        </div>
      )}

      {/* Action Buttons */}
      <div className="pt-2 flex flex-col sm:flex-row items-center justify-between gap-3 border-t border-slate-800">
        <div className="text-xs text-slate-400">
          {config?.is_configured
            ? '✅ File cấu hình hợp lệ. Bấm nút bên phải để kết nối tài khoản Google thật.'
            : '💡 Sau khi lưu Client ID & Secret, nút đăng nhập sẽ xuất hiện tại đây.'}
        </div>

        <div className="flex items-center gap-2.5 w-full sm:w-auto">
          {config?.is_configured ? (
            <button
              onClick={handleStartGoogleOAuth}
              className="flex-1 sm:flex-none px-5 py-2.5 rounded-xl bg-sky-600 hover:bg-sky-500 text-white text-xs font-semibold shadow-lg shadow-sky-600/20 transition-all flex items-center justify-center gap-2"
            >
              <LogIn className="w-4 h-4" />
              <span>Đăng Nhập Google (Tài Khoản Thật)</span>
            </button>
          ) : (
            <button
              onClick={onOpenGuide}
              className="flex-1 sm:flex-none px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-medium transition-colors flex items-center justify-center gap-1.5 border border-slate-700"
            >
              <HelpCircle className="w-4 h-4 text-sky-400" />
              <span>Xem hướng dẫn chi tiết</span>
            </button>
          )}
        </div>
      </div>
    </div>
  );
};
