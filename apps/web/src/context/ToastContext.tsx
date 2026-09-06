import React, { createContext, useContext, useState, useCallback, useRef, useEffect } from 'react';
import { CheckCircle2, AlertCircle, AlertTriangle, Info, X } from 'lucide-react';

export type ToastType = 'success' | 'error' | 'warning' | 'info';

export interface ToastItem {
  id: string;
  type: ToastType;
  title?: string;
  message: string;
  duration?: number;
}

interface ToastContextType {
  toast: {
    success: (message: string, title?: string, duration?: number) => void;
    error: (message: string, title?: string, duration?: number) => void;
    warning: (message: string, title?: string, duration?: number) => void;
    info: (message: string, title?: string, duration?: number) => void;
  };
  removeToast: (id: string) => void;
}

const ToastContext = createContext<ToastContextType | undefined>(undefined);

export const ToastProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [toasts, setToasts] = useState<ToastItem[]>([]);

  const removeToast = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const addToast = useCallback((type: ToastType, message: string, title?: string, duration = 4000) => {
    const id = `${Date.now()}-${Math.random().toString(36).substring(2, 9)}`;
    setToasts((prev) => [...prev, { id, type, title, message, duration }]);
  }, []);

  const toast = {
    success: (message: string, title?: string, duration = 4000) => addToast('success', message, title, duration),
    error: (message: string, title?: string, duration = 5000) => addToast('error', message, title, duration),
    warning: (message: string, title?: string, duration = 4000) => addToast('warning', message, title, duration),
    info: (message: string, title?: string, duration = 4000) => addToast('info', message, title, duration),
  };

  return (
    <ToastContext.Provider value={{ toast, removeToast }}>
      {children}
      {/* Toast Floating Container at Top-Right */}
      <div className="fixed top-4 right-4 z-[9999] flex flex-col gap-2.5 max-w-sm w-full pointer-events-none">
        {toasts.map((t) => (
          <ToastCard key={t.id} toast={t} onClose={() => removeToast(t.id)} />
        ))}
      </div>
    </ToastContext.Provider>
  );
};

export const useToast = (): ToastContextType['toast'] => {
  const context = useContext(ToastContext);
  if (!context) {
    throw new Error('useToast must be used within a ToastProvider');
  }
  return context.toast;
};

// Individual Toast Card with Glassmorphism and Countdown Progress Bar
const ToastCard: React.FC<{ toast: ToastItem; onClose: () => void }> = ({ toast, onClose }) => {
  const duration = toast.duration || 4000;
  const [progress, setProgress] = useState(100);
  const [isPaused, setIsPaused] = useState(false);
  const startTimeRef = useRef<number>(Date.now());
  const remainingTimeRef = useRef<number>(duration);

  useEffect(() => {
    if (isPaused) return;

    startTimeRef.current = Date.now();
    const interval = setInterval(() => {
      const elapsed = Date.now() - startTimeRef.current;
      const newRemaining = Math.max(0, remainingTimeRef.current - elapsed);
      setProgress((newRemaining / duration) * 100);

      if (newRemaining <= 0) {
        clearInterval(interval);
        onClose();
      }
    }, 50);

    return () => clearInterval(interval);
  }, [isPaused, duration, onClose]);

  const handleMouseEnter = () => {
    setIsPaused(true);
    const elapsed = Date.now() - startTimeRef.current;
    remainingTimeRef.current = Math.max(0, remainingTimeRef.current - elapsed);
  };

  const handleMouseLeave = () => {
    setIsPaused(false);
  };

  const getStyle = () => {
    switch (toast.type) {
      case 'success':
        return {
          border: 'border-emerald-500/40',
          glow: 'shadow-emerald-500/20',
          iconBg: 'bg-emerald-500/20 text-emerald-400',
          progressBar: 'bg-gradient-to-r from-emerald-500 to-teal-400',
          defaultTitle: 'Success',
          Icon: CheckCircle2,
        };
      case 'error':
        return {
          border: 'border-rose-500/40',
          glow: 'shadow-rose-500/20',
          iconBg: 'bg-rose-500/20 text-rose-400',
          progressBar: 'bg-gradient-to-r from-rose-500 to-pink-500',
          defaultTitle: 'Error',
          Icon: AlertCircle,
        };
      case 'warning':
        return {
          border: 'border-amber-500/40',
          glow: 'shadow-amber-500/20',
          iconBg: 'bg-amber-500/20 text-amber-400',
          progressBar: 'bg-gradient-to-r from-amber-500 to-orange-400',
          defaultTitle: 'Notice',
          Icon: AlertTriangle,
        };
      case 'info':
      default:
        return {
          border: 'border-sky-500/40',
          glow: 'shadow-sky-500/20',
          iconBg: 'bg-sky-500/20 text-sky-400',
          progressBar: 'bg-gradient-to-r from-sky-500 to-indigo-500',
          defaultTitle: 'Info',
          Icon: Info,
        };
    }
  };

  const s = getStyle();
  const { Icon } = s;

  return (
    <div
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
      className={`pointer-events-auto relative overflow-hidden rounded-xl backdrop-blur-xl bg-slate-900/95 border ${s.border} shadow-xl ${s.glow} p-3.5 text-slate-100 transition-all duration-300 transform translate-y-0 opacity-100 animate-in slide-in-from-top-3`}
    >
      <div className="flex items-start gap-3">
        <div className={`w-8 h-8 rounded-lg ${s.iconBg} flex items-center justify-center flex-shrink-0 mt-0.5`}>
          <Icon className="w-4 h-4" />
        </div>

        <div className="flex-1 min-w-0 pr-1">
          <div className="text-xs font-semibold text-white tracking-tight">
            {toast.title || s.defaultTitle}
          </div>
          <p className="text-xs text-slate-300 mt-0.5 leading-relaxed break-words font-sans">
            {toast.message}
          </p>
        </div>

        <button
          onClick={onClose}
          className="text-slate-400 hover:text-white p-1 rounded-lg hover:bg-slate-800 transition flex-shrink-0"
          title="Close notification"
        >
          <X className="w-3.5 h-3.5" />
        </button>
      </div>

      {/* Animated countdown progress bar */}
      <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-slate-800/80">
        <div
          className={`h-full ${s.progressBar} transition-all duration-75`}
          style={{ width: `${progress}%` }}
        />
      </div>
    </div>
  );
};
