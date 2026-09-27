import React, { forwardRef } from 'react';

export interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
  helperText?: string;
  leftIcon?: React.ReactNode;
  rightIcon?: React.ReactNode;
}

export const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ label, error, helperText, leftIcon, rightIcon, className = '', id, ...props }, ref) => {
    const inputId = id || (label ? label.toLowerCase().replace(/\s+/g, '-') : undefined);

    return (
      <div className="w-full space-y-1">
        {label && (
          <label htmlFor={inputId} className="block text-xs font-medium text-text-secondary">
            {label}
          </label>
        )}
        <div className="relative flex items-center">
          {leftIcon && (
            <div className="absolute left-2.5 flex items-center pointer-events-none text-text-muted">
              {leftIcon}
            </div>
          )}
          <input
            ref={ref}
            id={inputId}
            className={`w-full bg-surface-subtle text-text-primary text-xs rounded-lg border transition-all duration-150 ease-[cubic-bezier(0.16,1,0.3,1)] px-3 py-2 placeholder:text-text-muted focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary disabled:opacity-50 disabled:cursor-not-allowed ${
              leftIcon ? 'pl-8' : ''
            } ${rightIcon ? 'pr-8' : ''} ${
              error ? 'border-rose-500 focus:ring-rose-500/20 focus:border-rose-500' : 'border-border-default hover:border-border-active'
            } ${className}`}
            {...props}
          />
          {rightIcon && (
            <div className="absolute right-2.5 flex items-center text-text-muted">
              {rightIcon}
            </div>
          )}
        </div>
        {error && <p className="text-[11px] text-rose-500">{error}</p>}
        {helperText && !error && <p className="text-[11px] text-text-muted">{helperText}</p>}
      </div>
    );
  }
);
Input.displayName = 'Input';

export interface TextareaProps extends React.TextareaHTMLAttributes<HTMLTextAreaElement> {
  label?: string;
  error?: string;
  helperText?: string;
}

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaProps>(
  ({ label, error, helperText, className = '', id, ...props }, ref) => {
    const textareaId = id || (label ? label.toLowerCase().replace(/\s+/g, '-') : undefined);

    return (
      <div className="w-full space-y-1">
        {label && (
          <label htmlFor={textareaId} className="block text-xs font-medium text-text-secondary">
            {label}
          </label>
        )}
        <textarea
          ref={ref}
          id={textareaId}
          className={`w-full bg-surface-subtle text-text-primary text-xs rounded-lg border transition-all duration-150 ease-[cubic-bezier(0.16,1,0.3,1)] p-3 placeholder:text-text-muted focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary disabled:opacity-50 disabled:cursor-not-allowed ${
            error ? 'border-rose-500 focus:ring-rose-500/20 focus:border-rose-500' : 'border-border-default hover:border-border-active'
          } ${className}`}
          {...props}
        />
        {error && <p className="text-[11px] text-rose-500">{error}</p>}
        {helperText && !error && <p className="text-[11px] text-text-muted">{helperText}</p>}
      </div>
    );
  }
);
Textarea.displayName = 'Textarea';

