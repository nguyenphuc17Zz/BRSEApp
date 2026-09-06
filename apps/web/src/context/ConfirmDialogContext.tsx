import React, { createContext, useContext, useState, useRef, useEffect } from 'react';
import { AlertTriangle, AlertCircle, Trash2, X, Check } from 'lucide-react';

export interface ConfirmOptions {
  title: string;
  message: string;
  confirmText?: string;
  cancelText?: string;
  isDestructive?: boolean;
}

interface ConfirmDialogContextType {
  confirm: (options: ConfirmOptions) => Promise<boolean>;
}

const ConfirmDialogContext = createContext<ConfirmDialogContextType | undefined>(undefined);

export const ConfirmDialogProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [isOpen, setIsOpen] = useState<boolean>(false);
  const [options, setOptions] = useState<ConfirmOptions>({
    title: 'Are you sure?',
    message: 'This action cannot be undone.',
    confirmText: 'Confirm',
    cancelText: 'Cancel',
    isDestructive: false,
  });

  const resolverRef = useRef<((value: boolean) => void) | null>(null);

  const confirm = (opts: ConfirmOptions): Promise<boolean> => {
    setOptions({
      confirmText: opts.isDestructive ? 'Delete' : 'Confirm',
      cancelText: 'Cancel',
      ...opts,
    });
    setIsOpen(true);
    return new Promise<boolean>((resolve) => {
      resolverRef.current = resolve;
    });
  };

  const handleConfirm = () => {
    setIsOpen(false);
    if (resolverRef.current) {
      resolverRef.current(true);
      resolverRef.current = null;
    }
  };

  const handleCancel = () => {
    setIsOpen(false);
    if (resolverRef.current) {
      resolverRef.current(false);
      resolverRef.current = null;
    }
  };

  // Keyboard navigation: Escape cancels, Enter confirms
  useEffect(() => {
    if (!isOpen) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        handleCancel();
      } else if (e.key === 'Enter') {
        e.preventDefault();
        handleConfirm();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen]);

  return (
    <ConfirmDialogContext.Provider value={{ confirm }}>
      {children}
      {isOpen && (
        <div className="fixed inset-0 z-[9999] flex items-center justify-center p-4">
          {/* Backdrop Blur */}
          <div
            onClick={handleCancel}
            className="fixed inset-0 bg-black/70 backdrop-blur-md transition-opacity duration-200 animate-in fade-in"
          />

          {/* Modal Dialog Card */}
          <div className="relative z-10 max-w-md w-full rounded-2xl backdrop-blur-2xl bg-slate-900/95 border border-slate-700/80 shadow-2xl p-6 text-slate-100 transform transition-all duration-200 animate-in zoom-in-95 scale-100 space-y-4">
            <div className="flex items-start gap-3.5">
              <div
                className={`w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0 ${
                  options.isDestructive
                    ? 'bg-rose-500/20 text-rose-400 border border-rose-500/30 shadow-lg shadow-rose-500/10'
                    : 'bg-sky-500/20 text-sky-400 border border-sky-500/30 shadow-lg shadow-sky-500/10'
                }`}
              >
                {options.isDestructive ? <Trash2 className="w-5 h-5" /> : <AlertCircle className="w-5 h-5" />}
              </div>

              <div className="flex-1 min-w-0">
                <h3 className="text-sm font-bold text-white tracking-tight">{options.title}</h3>
                <p className="text-xs text-slate-300 mt-1.5 leading-relaxed font-sans">{options.message}</p>
              </div>

              <button
                onClick={handleCancel}
                className="text-slate-400 hover:text-white p-1 rounded-lg hover:bg-slate-800 transition -mr-1"
                title="Cancel"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* Action buttons */}
            <div className="flex items-center justify-end gap-2.5 pt-2 border-t border-slate-800/80">
              <button
                onClick={handleCancel}
                className="px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-semibold transition hover:text-white"
              >
                {options.cancelText || 'Cancel'}
              </button>
              <button
                onClick={handleConfirm}
                autoFocus
                className={`px-4 py-2 rounded-xl text-xs font-semibold text-white transition flex items-center gap-1.5 shadow-lg ${
                  options.isDestructive
                    ? 'bg-rose-600 hover:bg-rose-500 shadow-rose-600/30'
                    : 'bg-sky-600 hover:bg-sky-500 shadow-sky-600/30'
                }`}
              >
                {options.isDestructive ? <Trash2 className="w-3.5 h-3.5" /> : <Check className="w-3.5 h-3.5" />}
                {options.confirmText || 'Confirm'}
              </button>
            </div>
          </div>
        </div>
      )}
    </ConfirmDialogContext.Provider>
  );
};

export const useConfirm = (): ((options: ConfirmOptions) => Promise<boolean>) => {
  const context = useContext(ConfirmDialogContext);
  if (!context) {
    throw new Error('useConfirm must be used within a ConfirmDialogProvider');
  }
  return context.confirm;
};
