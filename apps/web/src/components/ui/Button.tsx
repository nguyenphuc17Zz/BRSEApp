import React, { forwardRef } from 'react';
import { Loader2 } from 'lucide-react';

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'outline' | 'ghost' | 'danger' | 'subtle';
  size?: 'sm' | 'md' | 'lg' | 'icon';
  isLoading?: boolean;
  leftIcon?: React.ReactNode;
  rightIcon?: React.ReactNode;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  (
    {
      children,
      className = '',
      variant = 'secondary',
      size = 'md',
      isLoading = false,
      disabled = false,
      leftIcon,
      rightIcon,
      type = 'button',
      ...props
    },
    ref
  ) => {
    // Base styles with tactile spring feedback & strictly horizontal single-line alignment
    const base = 'inline-flex items-center justify-center font-medium rounded-lg whitespace-nowrap transition-all duration-150 ease-[cubic-bezier(0.16,1,0.3,1)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40 disabled:opacity-50 disabled:pointer-events-none select-none active:scale-[0.97] cursor-pointer will-change-transform flex-shrink-0';

    // Sizes
    const sizes = {
      sm: 'text-xs px-2.5 py-1.5 gap-1.5 min-h-[30px]',
      md: 'text-xs px-3.5 py-2 gap-2 min-h-[36px]',
      lg: 'text-sm px-4 py-2.5 gap-2.5 min-h-[40px]',
      icon: 'p-1.5 h-8 w-8 justify-center flex-shrink-0',
    };

    // Variants
    const variants = {
      primary:
        'bg-primary text-white hover:brightness-105 active:brightness-95 shadow-xs shadow-primary/20 border border-primary/30',
      secondary:
        'bg-surface-elevated hover:bg-surface-hover active:bg-surface-elevated text-text-primary border border-border-default shadow-xs',
      outline:
        'bg-transparent hover:bg-surface-hover active:bg-surface-elevated text-text-primary border border-border-default',
      ghost:
        'bg-transparent hover:bg-surface-hover active:bg-surface-elevated text-text-secondary hover:text-text-primary',
      subtle:
        'bg-primary/10 hover:bg-primary/15 active:bg-primary/20 text-primary border border-primary/20',
      danger:
        'bg-rose-600 hover:bg-rose-500 active:bg-rose-700 text-white shadow-xs shadow-rose-600/25 border border-rose-700/30',
    };

    return (
      <button
        ref={ref}
        type={type}
        disabled={disabled || isLoading}
        className={`${base} ${sizes[size]} ${variants[variant]} ${className}`}
        {...props}
      >
        {isLoading ? (
          <Loader2 className="w-3.5 h-3.5 animate-spin flex-shrink-0" />
        ) : (
          leftIcon && <span className="flex-shrink-0 inline-flex items-center">{leftIcon}</span>
        )}
        {children && <span className="inline-flex items-center gap-1.5 whitespace-nowrap leading-none">{children}</span>}
        {!isLoading && rightIcon && <span className="flex-shrink-0 inline-flex items-center">{rightIcon}</span>}
      </button>
    );
  }
);

Button.displayName = 'Button';
