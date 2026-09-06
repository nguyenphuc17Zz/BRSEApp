import React, { useState } from 'react';
import {
  Cloud,
  Plus,
  CheckCircle2,
  X,
  ExternalLink,
  ShieldCheck,
  UserCheck
} from 'lucide-react';
import { GoogleAccountItem } from '../../types';
import { apiClient } from '../../api/client';
import { useToast } from '../../context/ToastContext';
import { useConfirm } from '../../context/ConfirmDialogContext';

interface GoogleAccountSwitcherProps {
  accounts: GoogleAccountItem[];
  selectedAccountId: string | null;
  onSelectAccount: (accountId: string) => void;
  onRefreshAccounts: () => void;
}

export const GoogleAccountSwitcher: React.FC<GoogleAccountSwitcherProps> = ({
  accounts,
  selectedAccountId,
  onSelectAccount,
  onRefreshAccounts
}) => {
  const toast = useToast();
  const confirm = useConfirm();
  const [isAdding, setIsAdding] = useState(false);
  const [removingId, setRemovingId] = useState<string | null>(null);

  const handleAddAccount = async () => {
    setIsAdding(true);
    try {
      const res = await apiClient.getGoogleLoginUrl();
      if (!res.auth_url) {
        toast.error('Không tạo được đường dẫn đăng nhập Google OAuth.');
        return;
      }

      // Open Google OAuth window in popup
      const width = 600;
      const height = 700;
      const left = window.screen.width / 2 - width / 2;
      const top = window.screen.height / 2 - height / 2;

      const popup = window.open(
        res.auth_url,
        'GoogleAccountLogin',
        `toolbar=no, location=no, directories=no, status=no, menubar=no, scrollbars=yes, resizable=yes, copyhistory=no, width=${width}, height=${height}, top=${top}, left=${left}`
      );

      if (!popup) {
        // Fallback to normal navigation if popup is blocked
        window.location.href = res.auth_url;
        return;
      }

      // Check when popup closes
      const timer = setInterval(() => {
        if (popup.closed) {
          clearInterval(timer);
          setIsAdding(false);
          onRefreshAccounts();
        }
      }, 1000);
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Lỗi khi khởi tạo đăng nhập Google.');
      setIsAdding(false);
    }
  };

  const handleDisconnect = async (e: React.MouseEvent, acc: GoogleAccountItem) => {
    e.stopPropagation();
    const confirmed = await confirm({
      title: 'Ngắt kết nối tài khoản Google?',
      message: `Bạn có chắc muốn ngắt kết nối tài khoản ${acc.email}? Dữ liệu và bản dịch của tài khoản này trên Google Drive sẽ không bị ảnh hưởng.`,
      confirmText: 'Ngắt kết nối',
      cancelText: 'Hủy',
      isDestructive: true
    });

    if (!confirmed) return;

    setRemovingId(acc.id);
    try {
      await apiClient.disconnectGoogleAccount(acc.id);
      toast.success(`Đã ngắt kết nối tài khoản ${acc.email}`);
      onRefreshAccounts();
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Lỗi khi ngắt kết nối tài khoản.');
    } finally {
      setRemovingId(null);
    }
  };

  if (!accounts || accounts.length === 0) return null;

  return (
    <div className="p-3 bg-slate-900/90 rounded-xl border border-slate-800 shadow-md flex flex-col md:flex-row md:items-center justify-between gap-3">
      {/* Account Tabs */}
      <div className="flex items-center gap-2 flex-wrap min-w-0">
        <div className="flex items-center gap-1.5 text-xs text-slate-400 font-medium mr-1.5">
          <Cloud className="w-4 h-4 text-sky-400" />
          <span>Google Drive ({accounts.length}):</span>
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          {accounts.map((acc) => {
            const isSelected = acc.id === selectedAccountId;
            const isRemoving = removingId === acc.id;

            return (
              <div
                key={acc.id}
                onClick={() => onSelectAccount(acc.id)}
                className={`group flex items-center gap-2 px-3 py-1.5 rounded-lg border text-xs font-medium cursor-pointer transition-all ${
                  isSelected
                    ? 'bg-sky-600/20 border-sky-500 text-white shadow-sm shadow-sky-600/10'
                    : 'bg-slate-800/80 border-slate-700/80 text-slate-300 hover:bg-slate-800 hover:text-white hover:border-slate-600'
                } ${isRemoving ? 'opacity-50 pointer-events-none' : ''}`}
              >
                <div className="flex items-center gap-1.5">
                  <div
                    className={`w-2 h-2 rounded-full ${
                      isSelected ? 'bg-emerald-400 shadow-sm shadow-emerald-400/50' : 'bg-slate-500'
                    }`}
                  />
                  <span className="truncate max-w-[180px]" title={acc.email}>
                    {acc.email}
                  </span>
                </div>

                {isSelected && (
                  <span className="text-[10px] px-1.5 py-0.2 rounded bg-sky-500/20 text-sky-300 font-semibold border border-sky-500/30">
                    Đang xem
                  </span>
                )}

                <button
                  type="button"
                  onClick={(e) => handleDisconnect(e, acc)}
                  title={`Ngắt kết nối ${acc.email}`}
                  className="text-slate-400 hover:text-rose-400 p-0.5 rounded transition-colors opacity-60 group-hover:opacity-100 hover:bg-rose-500/10"
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              </div>
            );
          })}
        </div>
      </div>

      {/* Add another Google account button */}
      <button
        type="button"
        onClick={handleAddAccount}
        disabled={isAdding}
        className="flex-shrink-0 px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 border border-slate-700/90 text-sky-400 hover:text-sky-300 text-xs font-medium flex items-center gap-1.5 transition-all shadow-sm active:scale-95 disabled:opacity-50"
      >
        <Plus className="w-3.5 h-3.5" />
        <span>{isAdding ? 'Đang mở OAuth...' : '+ Thêm tài khoản Google'}</span>
      </button>
    </div>
  );
};
