import React, { useState } from 'react';
import {
  ExternalLink,
  CheckCircle2,
  Key,
  ShieldCheck,
  Users,
  Copy,
  Check,
  X,
  Share2,
  Sparkles,
  FolderOpen
} from 'lucide-react';
import { useToast } from '../../context/ToastContext';

interface GoogleSetupGuideModalProps {
  onClose: () => void;
}

export const GoogleSetupGuideModal: React.FC<GoogleSetupGuideModalProps> = ({ onClose }) => {
  const toast = useToast();
  const [activeTab, setActiveTab] = useState<'oauth' | 'multi_account'>('oauth');
  const [copiedText, setCopiedText] = useState<string | null>(null);

  const copyToClipboard = (text: string, label: string) => {
    navigator.clipboard.writeText(text);
    setCopiedText(label);
    toast.success(`Đã sao chép ${label}`);
    setTimeout(() => setCopiedText(null), 2000);
  };

  const REDIRECT_URI = 'http://127.0.0.1:8000/api/integrations/google/callback';

  return (
    <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4">
      <div className="bg-surface-elevated border border-border-default rounded-2xl w-full max-w-4xl h-[85vh] overflow-hidden flex flex-col shadow-2xl">
        {/* Header */}
        <div className="px-6 py-4 border-b border-border-subtle bg-surface-subtle flex items-center justify-between">
          <div className="flex items-center gap-3.5">
            <div className="w-11 h-11 rounded-xl bg-sky-500/10 border border-sky-500/20 flex items-center justify-center text-brand-primary">
              <Key className="w-5 h-5" />
            </div>
            <div>
              <h3 className="text-base font-semibold text-text-primary">
                Hướng Dẫn Kết Nối Google Drive & Quản Lý Nhiều Tài Khoản
              </h3>
              <p className="text-sm text-text-secondary mt-0.5">
                Thiết lập OAuth 2.0 Client ID (miễn phí) và mẹo xử lý khi bạn có 2 tài khoản Google Drive
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-2 rounded-lg text-text-muted hover:text-text-primary hover:bg-surface transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Tab Navigation */}
        <div className="px-6 py-3 border-b border-border-subtle bg-surface flex items-center gap-2.5 text-sm">
          <button
            onClick={() => setActiveTab('oauth')}
            className={`px-4 py-2 rounded-lg font-medium transition-colors ${
              activeTab === 'oauth'
                ? 'bg-primary text-white shadow-sm'
                : 'text-text-secondary hover:text-text-primary hover:bg-surface-subtle'
            }`}
          >
            1. Thiết lập OAuth (Live Account)
          </button>
          <button
            onClick={() => setActiveTab('multi_account')}
            className={`px-4 py-2 rounded-lg font-medium transition-colors ${
              activeTab === 'multi_account'
                ? 'bg-emerald-600 text-white shadow-sm'
                : 'text-text-secondary hover:text-text-primary hover:bg-surface-subtle'
            }`}
          >
            2. Mẹo Xử Lý 2 Tài Khoản Drive
          </button>
        </div>

        {/* Modal Content */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6 text-sm text-text-secondary leading-relaxed">
          {/* TAB 1: OAuth Steps */}
          {activeTab === 'oauth' && (
            <div className="space-y-4">
              <div className="p-4 rounded-xl bg-sky-500/10 border border-sky-500/20 text-sky-900 dark:text-sky-200 flex items-start gap-3">
                <ShieldCheck className="w-5 h-5 text-brand-primary flex-shrink-0 mt-0.5" />
                <p className="text-sm leading-relaxed">
                  Google yêu cầu OAuth 2.0 để bảo vệ quyền riêng tư của bạn. Bạn chỉ cần tạo Client ID cá nhân trên Google Cloud một lần duy nhất (hoàn toàn miễn phí) và có thể sử dụng vĩnh viễn.
                </p>
              </div>

              {/* Step 1 */}
              <div className="p-4 rounded-xl bg-surface border border-border-subtle space-y-2.5">
                <div className="flex items-center justify-between">
                  <span className="font-semibold text-text-primary text-sm flex items-center gap-2.5">
                    <span className="w-6 h-6 rounded-full bg-primary text-white flex items-center justify-center text-xs font-bold">1</span>
                    Truy cập Google Cloud Console & Tạo Project
                  </span>
                  <a
                    href="https://console.cloud.google.com/"
                    target="_blank"
                    rel="noreferrer"
                    className="text-brand-primary hover:underline flex items-center gap-1.5 text-sm"
                  >
                    <span>Mở Google Cloud Console</span>
                    <ExternalLink className="w-3.5 h-3.5" />
                  </a>
                </div>
                <p className="text-text-secondary text-sm">
                  Đăng nhập bằng tài khoản Google của bạn → Bấm chọn <strong>Select a project</strong> ở góc trên bên trái → Chọn <strong>New Project</strong> → Đặt tên dự án (ví dụ: <code className="text-brand-primary font-mono bg-surface-subtle px-1.5 py-0.5 rounded border border-border-subtle">AutomationTranslate-Copilot</code>) → Bấm <strong>Create</strong>.
                </p>
              </div>

              {/* Step 2 */}
              <div className="p-4 rounded-xl bg-surface border border-border-subtle space-y-2.5">
                <span className="font-semibold text-text-primary text-sm flex items-center gap-2.5">
                  <span className="w-6 h-6 rounded-full bg-primary text-white flex items-center justify-center text-xs font-bold">2</span>
                  Bật (Enable) các Google Workspace APIs
                </span>
                <p className="text-text-secondary text-sm">
                  Vào menu trái → <strong>APIs & Services</strong> → <strong>Library</strong> → Tìm kiếm và nhấn <strong>Enable</strong> cho 4 API sau:
                </p>
                <div className="grid grid-cols-2 gap-2.5 pt-1 font-mono text-xs">
                  <div className="p-2.5 rounded bg-surface-subtle border border-border-subtle text-brand-primary font-medium flex items-center gap-2">
                    <CheckCircle2 className="w-4 h-4 text-emerald-500" />
                    <span>Google Drive API</span>
                  </div>
                  <div className="p-2.5 rounded bg-surface-subtle border border-border-subtle text-brand-primary font-medium flex items-center gap-2">
                    <CheckCircle2 className="w-4 h-4 text-emerald-500" />
                    <span>Google Docs API</span>
                  </div>
                  <div className="p-2.5 rounded bg-surface-subtle border border-border-subtle text-brand-primary font-medium flex items-center gap-2">
                    <CheckCircle2 className="w-4 h-4 text-emerald-500" />
                    <span>Google Sheets API</span>
                  </div>
                  <div className="p-2.5 rounded bg-surface-subtle border border-border-subtle text-brand-primary font-medium flex items-center gap-2">
                    <CheckCircle2 className="w-4 h-4 text-emerald-500" />
                    <span>Google Slides API</span>
                  </div>
                </div>
              </div>

              {/* Step 3 */}
              <div className="p-4 rounded-xl bg-surface border border-border-subtle space-y-3">
                <span className="font-semibold text-text-primary text-sm flex items-center gap-2.5">
                  <span className="w-6 h-6 rounded-full bg-primary text-white flex items-center justify-center text-xs font-bold">3</span>
                  Cấu hình OAuth Consent Screen & Thêm Test Users
                </span>
                <p className="text-text-secondary text-sm">
                  Vào menu <strong>APIs & Services</strong> → <strong>OAuth consent screen</strong> (hoặc <strong>Google Auth Platform</strong>):
                </p>
                <div className="bg-surface-subtle border border-border-subtle rounded-lg p-3.5 space-y-2 text-sm">
                  <p className="text-text-secondary">
                    • Nhìn lên thanh tab phía trên (hoặc menu phụ bên trái), chọn tab: <code className="text-brand-primary font-bold bg-surface px-1.5 py-0.5 rounded border border-border-subtle">Audience (Đối tượng)</code>.
                  </p>
                  <p className="text-text-secondary">
                    • Hãy chắc chắn mục <em>User type</em> đang chọn là <strong>External</strong>.
                  </p>
                  <p className="text-text-secondary">
                    • Cuộn xuống phần <strong>Test users</strong> → Bấm nút <strong className="text-text-primary bg-surface px-2 py-0.5 rounded border border-border-subtle">+ Add users</strong> → Nhập email của bạn vào danh sách rồi bấm <strong>Save</strong>.
                  </p>
                </div>

                {/* Clarification Callout for Test Users */}
                <div className="p-3.5 rounded-xl bg-sky-500/5 dark:bg-sky-500/10 border border-sky-500/20 text-text-secondary text-sm space-y-2 shadow-inner">
                  <div className="flex items-center gap-2 font-semibold text-brand-primary">
                    <Users className="w-4 h-4 text-brand-primary flex-shrink-0" />
                    <span>Lưu ý quan trọng: "Add users" là nhập email nào?</span>
                  </div>
                  <p className="text-text-secondary leading-relaxed pl-6">
                    👉 <strong>Nhập chính địa chỉ Gmail cá nhân hoặc email Google của bạn</strong> (ví dụ: <code className="text-brand-primary font-mono bg-surface px-1.5 py-0.5 rounded border border-border-subtle">tenban@gmail.com</code>).
                  </p>
                  <p className="text-text-secondary leading-relaxed pl-6">
                    • Nếu bạn có <strong>2 tài khoản Google Drive</strong> (ví dụ 1 email cá nhân và 1 email công việc), hãy bấm thêm <strong>cả 2 email</strong> vào danh sách này để cả 2 tài khoản đều được cấp quyền đăng nhập!
                  </p>
                  <div className="mt-1 pt-1.5 border-t border-sky-500/20 text-xs text-amber-700 dark:text-amber-300 flex items-start gap-1.5 pl-6">
                    <span className="text-sm leading-none">⚠️</span>
                    <span>
                      <em>Bắt buộc phải thêm email của bạn vào đây. Nếu bỏ qua bước này, khi bấm Đăng nhập Google sẽ chặn lại và báo lỗi <strong>"Access blocked: App has not completed the Google verification process"</strong>.</em>
                    </span>
                  </div>
                </div>

                <div className="p-3 rounded-lg bg-amber-500/10 border border-amber-500/20 text-amber-700 dark:text-amber-300 text-xs flex items-start gap-2">
                  <span className="text-base leading-none">💡</span>
                  <span>
                    <em>Lưu ý dành cho Google Workspace doanh nghiệp: Nếu bạn dùng email công ty (@company.com) và chọn User type là <strong>Internal (Nội bộ)</strong> thì Google sẽ không hiển thị mục Test Users vì toàn bộ thành viên trong tổ chức mặc định đã được cấp quyền.</em>
                  </span>
                </div>
              </div>

              {/* Step 4 */}
              <div className="p-4 rounded-xl bg-surface border border-border-subtle space-y-2.5">
                <span className="font-semibold text-text-primary text-sm flex items-center gap-2.5">
                  <span className="w-6 h-6 rounded-full bg-primary text-white flex items-center justify-center text-xs font-bold">4</span>
                  Tạo OAuth Client ID & Lấy Keys
                </span>
                <p className="text-text-secondary text-sm">
                  Vào <strong>Credentials</strong> → <strong>Create Credentials</strong> → Chọn <strong>OAuth client ID</strong>:
                </p>
                <div className="space-y-2.5 pt-1">
                  <div className="text-sm">
                    <span className="text-text-primary font-medium">Application type:</span>{' '}
                    <span className="text-brand-primary font-mono">Web application</span>
                  </div>
                  <div className="text-sm">
                    <span className="text-text-primary font-medium">Authorized redirect URIs:</span>
                    <div className="flex items-center gap-2 mt-1.5">
                      <input
                        type="text"
                        readOnly
                        value={REDIRECT_URI}
                        className="w-full bg-surface-subtle border border-border-default rounded-lg px-3 py-2 font-mono text-sm text-brand-primary select-all"
                      />
                      <button
                        onClick={() => copyToClipboard(REDIRECT_URI, 'Redirect URI')}
                        className="px-3.5 py-2 rounded-lg bg-surface hover:bg-surface-subtle text-text-secondary hover:text-text-primary text-sm flex items-center gap-1.5 border border-border-subtle font-medium"
                      >
                        {copiedText === 'Redirect URI' ? <Check className="w-4 h-4 text-emerald-500" /> : <Copy className="w-4 h-4" />}
                        <span>Copy</span>
                      </button>
                    </div>
                  </div>
                </div>
                <div className="p-3 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-emerald-800 dark:text-emerald-200 text-sm space-y-1.5 mt-2">
                  <p className="font-semibold text-text-primary flex items-center gap-1.5">
                    <Sparkles className="w-4 h-4 text-emerald-500" />
                    <span>Mẹo Tự Động Hóa 1-Click: Tải file JSON về kéo thả vào ứng dụng!</span>
                  </p>
                  <p className="text-text-secondary text-xs leading-relaxed">
                    Sau khi nhấn <strong>Create</strong>, popup Google sẽ có nút <strong>DOWNLOAD JSON</strong>. Bạn chỉ cần tải file đó về (tên file dạng <code className="text-emerald-600 dark:text-emerald-400 font-mono font-medium">client_secret_xxx.json</code>) rồi <strong>kéo thả thẳng vào ứng dụng</strong>. Hệ thống sẽ tự động nạp Client ID & Secret, bạn không cần phải copy-paste thủ công!
                  </p>
                </div>
              </div>
            </div>
          )}

          {/* TAB 2: Multi-Account Tips */}
          {activeTab === 'multi_account' && (
            <div className="space-y-4">
              <div className="p-4 rounded-xl bg-emerald-500/10 border border-emerald-500/20 text-emerald-800 dark:text-emerald-200 flex items-start gap-3">
                <Share2 className="w-5 h-5 text-emerald-500 flex-shrink-0 mt-0.5" />
                <div>
                  <h4 className="font-semibold text-text-primary text-sm">Mẹo Tiện Lợi Nhất: Chia Sẻ Thư Mục (Folder Sharing)</h4>
                  <p className="text-emerald-700 dark:text-emerald-300 text-sm mt-1">
                    Nếu bạn có 2 tài khoản (ví dụ: 1 tài khoản công ty và 1 tài khoản cá nhân), bạn <strong>không cần phải đăng nhập 2 lần</strong>!
                  </p>
                </div>
              </div>

              <div className="p-4 rounded-xl bg-surface border border-border-subtle space-y-3">
                <h4 className="font-semibold text-text-primary text-sm flex items-center gap-2">
                  <FolderOpen className="w-4 h-4 text-brand-primary" />
                  <span>Cách làm cụ thể:</span>
                </h4>
                <div className="space-y-2.5 text-text-secondary text-sm pl-2">
                  <div className="flex items-start gap-2.5">
                    <span className="font-semibold text-brand-primary">1.</span>
                    <span>Kết nối <strong>Tài khoản chính (Account A)</strong> vào ứng dụng Comtor Copilot.</span>
                  </div>
                  <div className="flex items-start gap-2.5">
                    <span className="font-semibold text-brand-primary">2.</span>
                    <span>Trên trình duyệt của <strong>Tài khoản thứ hai (Account B)</strong>, mở thư mục chứa tài liệu cần dịch (ví dụ folder <code className="text-brand-primary font-mono">1eyQ-oZhGwNfU8_-wr5HoChIuWjgUe801</code>).</span>
                  </div>
                  <div className="flex items-start gap-2.5">
                    <span className="font-semibold text-brand-primary">3.</span>
                    <span>Nhấn nút <strong>Chia sẻ (Share)</strong> → Điền email của <strong>Account A</strong> → Chọn quyền <strong>Người chỉnh sửa (Editor)</strong> → Bấm Gửi.</span>
                  </div>
                  <div className="flex items-start gap-2.5">
                    <span className="font-semibold text-brand-primary">4.</span>
                    <span>Tại tab Google Workspace trong ứng dụng, thư mục này sẽ tự động xuất hiện trong mục <strong>Shared Drives (Được chia sẻ với tôi)</strong>. Bạn có thể mở ra và dịch như bình thường!</span>
                  </div>
                </div>
              </div>

              <div className="p-4 rounded-xl bg-surface border border-border-subtle space-y-2">
                <h4 className="font-semibold text-text-primary text-sm flex items-center gap-2">
                  <Users className="w-4 h-4 text-amber-500" />
                  <span>Đổi tài khoản linh hoạt khi cần:</span>
                </h4>
                <p className="text-text-secondary text-sm">
                  Tại giao diện Google Workspace, bạn có thể bấm <strong>Ngắt kết nối</strong> bất kỳ lúc nào để chuyển sang đăng nhập tài khoản Google khác. Toàn bộ bản dịch cũ và lịch sử tác vụ vẫn được lưu giữ an toàn trong database cục bộ.
                </p>
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-6 py-4 border-t border-border-subtle bg-surface-subtle flex items-center justify-between">
          <span className="text-xs text-text-muted">
            Dữ liệu token luôn được mã hóa chuẩn AES-256 an toàn trên máy của bạn.
          </span>
          <button
            onClick={onClose}
            className="px-6 py-2.5 rounded-lg bg-primary hover:bg-primary-hover text-white text-sm font-medium transition-colors"
          >
            Đã Hiểu
          </button>
        </div>
      </div>
    </div>
  );
};
