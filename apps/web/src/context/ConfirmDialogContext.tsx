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
            className="fixed inset-0 bg-black/50 dark:bg-black/75 backdrop-blur-sm transition-opacity duration-200 animate-in fade-in"
          />

          {/* Modal Dialog Card */}
          <div className="relative z-10 max-w-md w-full rounded-xl bg-surface-elevated border border-border-default shadow-modal p-5 text-text-primary transform transition-all duration-200 animate-in zoom-in-95 scale-100 space-y-4">
            <div className="flex items-start gap-3.5">
              <div
                className={`w-9 h-9 rounded-lg flex items-center justify-center flex-shrink-0 ${
                  options.isDestructive
                    ? 'bg-rose-500/10 text-rose-500 border border-rose-500/20'
                    : 'bg-primary/10 text-primary border border-primary/20'
                }`}
              >
                {options.isDestructive ? <Trash2 className="w-4 h-4" /> : <AlertCircle className="w-4 h-4" />}
              </div>

              <div className="flex-1 min-w-0">
                <h3 className="text-sm font-semibold text-text-primary tracking-tight">{options.title}</h3>
                <p className="text-xs text-text-secondary mt-1 leading-relaxed font-sans">{options.message}</p>
              </div>

              <button
                onClick={handleCancel}
                className="text-text-muted hover:text-text-primary p-1 rounded-md hover:bg-surface-hover transition -mr-1"
                title="Cancel"
                aria-label="Cancel"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* Action buttons */}
            <div className="flex items-center justify-end gap-2.5 pt-3 border-t border-border-subtle">
              <button
                type="button"
                onClick={handleCancel}
                className="px-3.5 py-1.5 rounded-lg bg-surface hover:bg-surface-hover border border-border-default text-text-secondary hover:text-text-primary text-xs font-medium transition-colors"
              >
                {options.cancelText || 'Cancel'}
              </button>
              <button
                type="button"
                onClick={handleConfirm}
                autoFocus
                className={`px-3.5 py-1.5 rounded-lg text-xs font-semibold text-white transition-all flex items-center gap-1.5 shadow-sm ${
                  options.isDestructive
                    ? 'bg-rose-600 hover:bg-rose-500 border border-rose-700/30'
                    : 'bg-primary hover:opacity-95 border border-primary/20'
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
