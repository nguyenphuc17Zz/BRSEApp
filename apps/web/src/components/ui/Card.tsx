import React from 'react';

export interface CardProps extends React.HTMLAttributes<HTMLDivElement> {
  elevated?: boolean;
  interactive?: boolean;
}

export const Card: React.FC<CardProps> = ({
  children,
  className = '',
  elevated = false,
  interactive = false,
  ...props
}) => {
  return (
    <div
      className={`rounded-xl border border-border-subtle transition-all duration-150 ease-[cubic-bezier(0.16,1,0.3,1)] ${
        elevated ? 'bg-surface-elevated shadow-elevated' : 'bg-surface shadow-subtle'
      } ${
        interactive
          ? 'hover:border-border-default hover:shadow-elevated active:scale-[0.99] cursor-pointer will-change-transform'
          : ''
      } ${className}`}
      {...props}
    >
      {children}
    </div>
  );
};

export const CardHeader: React.FC<React.HTMLAttributes<HTMLDivElement>> = ({
  children,
  className = '',
  ...props
}) => {
  return (
    <div
      className={`p-4 sm:p-5 flex items-center justify-between gap-4 border-b border-border-subtle ${className}`}
      {...props}
    >
      {children}
    </div>
  );
};

export const CardTitle: React.FC<React.HTMLAttributes<HTMLHeadingElement>> = ({
  children,
  className = '',
  ...props
}) => {
  return (
    <h3
      className={`text-sm font-semibold tracking-tight text-text-primary ${className}`}
      {...props}
    >
      {children}
    </h3>
  );
};

export const CardDescription: React.FC<React.HTMLAttributes<HTMLParagraphElement>> = ({
  children,
  className = '',
  ...props
}) => {
  return (
    <p
      className={`text-xs text-text-secondary mt-0.5 leading-normal ${className}`}
      {...props}
    >
      {children}
    </p>
  );
};

export const CardContent: React.FC<React.HTMLAttributes<HTMLDivElement>> = ({
  children,
  className = '',
  ...props
}) => {
  return (
    <div className={`p-4 sm:p-5 ${className}`} {...props}>
      {children}
    </div>
  );
};

export const CardFooter: React.FC<React.HTMLAttributes<HTMLDivElement>> = ({
  children,
  className = '',
  ...props
}) => {
  return (
    <div
      className={`p-3.5 sm:p-4 bg-surface-subtle/50 rounded-b-xl border-t border-border-subtle flex items-center justify-between gap-3 ${className}`}
      {...props}
    >
      {children}
    </div>
  );
};
