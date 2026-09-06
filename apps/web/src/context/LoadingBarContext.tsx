import React, { createContext, useContext, useState, useEffect, useCallback, ReactNode } from 'react';

interface LoadingBarContextType {
  startLoading: () => void;
  finishLoading: () => void;
  isLoading: boolean;
}

const LoadingBarContext = createContext<LoadingBarContextType | undefined>(undefined);

// Global event bus for non-React callers like axios interceptors
type LoadingListener = (activeCount: number) => void;
const listeners = new Set<LoadingListener>();
let globalActiveCount = 0;

export const notifyLoadingStart = () => {
  globalActiveCount++;
  listeners.forEach(fn => fn(globalActiveCount));
};

export const notifyLoadingFinish = () => {
  globalActiveCount = Math.max(0, globalActiveCount - 1);
  listeners.forEach(fn => fn(globalActiveCount));
};

export const LoadingBarProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const [activeCount, setActiveCount] = useState<number>(0);
  const [visible, setVisible] = useState<boolean>(false);

  useEffect(() => {
    const handleUpdate = (count: number) => {
      setActiveCount(count);
    };
    listeners.add(handleUpdate);
    return () => {
      listeners.delete(handleUpdate);
    };
  }, []);

  useEffect(() => {
    if (activeCount > 0) {
      setVisible(true);
    } else {
      // Graceful delay before hiding
      const timer = setTimeout(() => {
        setVisible(false);
      }, 300);
      return () => clearTimeout(timer);
    }
  }, [activeCount]);

  const startLoading = useCallback(() => {
    notifyLoadingStart();
  }, []);

  const finishLoading = useCallback(() => {
    notifyLoadingFinish();
  }, []);

  return (
    <LoadingBarContext.Provider value={{ startLoading, finishLoading, isLoading: activeCount > 0 }}>
      {visible && (
        <div className="fixed top-0 left-0 right-0 h-[2.5px] z-[10000] pointer-events-none overflow-hidden bg-slate-900/30">
          <div className="h-full w-full bg-gradient-to-r from-sky-400 via-indigo-500 to-emerald-400 shadow-[0_0_12px_rgba(56,189,248,0.8)] indeterminate-bar" />
        </div>
      )}
      {children}
    </LoadingBarContext.Provider>
  );
};

export const useLoadingBar = () => {
  const context = useContext(LoadingBarContext);
  if (!context) {
    throw new Error('useLoadingBar must be used within a LoadingBarProvider');
  }
  return context;
};
