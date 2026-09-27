import React, { useEffect, useRef } from 'react';
import { X } from 'lucide-react';

export interface ModalProps {
  isOpen: boolean;
  onClose: () => void;
  title?: React.ReactNode;
  description?: React.ReactNode;
  children: React.ReactNode;
  footer?: React.ReactNode;
  size?: 'sm' | 'md' | 'lg' | 'xl' | '2xl' | '5xl';
  showCloseButton?: boolean;
}

export const Modal: React.FC<ModalProps> = ({
  isOpen,
  onClose,
  title,
  description,
  children,
  footer,
  size = 'md',
  showCloseButton = true,
}) => {
  const contentRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!isOpen) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const sizeClasses = {
    sm: 'max-w-sm',
    md: 'max-w-md',
    lg: 'max-w-lg',
    xl: 'max-w-xl',
    '2xl': 'max-w-2xl',
    '5xl': 'max-w-5xl',
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 overflow-y-auto">
      {/* Backdrop with smooth fade */}
      <div
        onClick={onClose}
        className="fixed inset-0 bg-black/60 dark:bg-black/75 backdrop-blur-xs animate-backdrop-in"
      />

      {/* Modal Dialog Content with spring pop-in */}
      <div
        ref={contentRef}
        className={`relative z-10 w-full ${sizeClasses[size]} bg-surface-elevated border border-border-default rounded-xl shadow-2xl text-text-primary animate-modal-in overflow-hidden flex flex-col my-8 max-h-[90vh]`}
      >
        {/* Header */}
        {(title || showCloseButton) && (
          <div className="p-4 sm:p-5 border-b border-border-subtle flex items-start justify-between gap-4">
            <div>
              {title && (
                <h3 className="text-sm font-semibold tracking-tight text-text-primary">
                  {title}
                </h3>
              )}
              {description && (
                <p className="text-xs text-text-secondary mt-1 leading-normal">
                  {description}
                </p>
              )}
            </div>
            {showCloseButton && (
              <button
                type="button"
                onClick={onClose}
                className="p-1 rounded-lg text-text-muted hover:text-text-primary hover:bg-surface-hover transition-all duration-150 ease-[cubic-bezier(0.16,1,0.3,1)] active:scale-90 -mr-1 cursor-pointer"
                aria-label="Close modal"
              >
                <X className="w-4 h-4" />
              </button>
            )}
          </div>
        )}

        {/* Body */}
        <div className="p-4 sm:p-5 overflow-y-auto flex-1">{children}</div>

        {/* Footer */}
        {footer && (
          <div className="p-3.5 sm:p-4 bg-surface-subtle/40 border-t border-border-subtle flex items-center justify-end gap-2.5">
            {footer}
          </div>
        )}
      </div>
    </div>
  );
};
