import React, { useState, useRef, useEffect, ReactNode } from 'react';
import { ChevronDown, Check } from 'lucide-react';

export interface SelectOption<T = string> {
  value: T;
  label: string;
  sublabel?: string;
  icon?: ReactNode;
  disabled?: boolean;
}

export interface SelectProps<T = string> {
  options: SelectOption<T>[];
  value: T;
  onChange: (value: T) => void;
  placeholder?: string;
  disabled?: boolean;
  className?: string;
  triggerClassName?: string;
  dropdownClassName?: string;
  size?: 'sm' | 'md' | 'lg';
  label?: string;
  prefix?: ReactNode;
  align?: 'left' | 'right';
  name?: string;
  id?: string;
}

export function Select<T extends string | number>({
  options,
  value,
  onChange,
  placeholder = 'Select option...',
  disabled = false,
  className = '',
  triggerClassName = '',
  dropdownClassName = '',
  size = 'md',
  label,
  prefix,
  align = 'left'
}: SelectProps<T>) {
  const [isOpen, setIsOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  const selectedOption = options.find((o) => o.value === value);

  // Close when clicking outside
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    };
    if (isOpen) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [isOpen]);

  // Handle escape key
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isOpen) {
        setIsOpen(false);
      }
    };
    if (isOpen) {
      window.addEventListener('keydown', handleKeyDown);
    }
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [isOpen]);

  // Size styles
  const sizeStyles = {
    sm: 'text-xs h-8 px-2.5 gap-1.5',
    md: 'text-xs h-9 px-3 gap-2',
    lg: 'text-sm h-10 px-3.5 gap-2.5'
  };

  const handleSelect = (option: SelectOption<T>) => {
    if (option.disabled) return;
    onChange(option.value);
    setIsOpen(false);
  };

  return (
    <div ref={containerRef} className={`relative inline-block text-left ${className}`}>
      {label && (
        <label className="block text-xs font-medium text-text-secondary mb-1">
          {label}
        </label>
      )}

      {/* Trigger Button */}
      <button
        type="button"
        disabled={disabled}
        onClick={() => !disabled && setIsOpen((prev) => !prev)}
        aria-haspopup="listbox"
        aria-expanded={isOpen}
        className={`w-full bg-surface hover:bg-surface-hover active:bg-surface-elevated border border-border-default hover:border-border-active rounded-lg font-medium text-text-primary transition-all duration-150 ease-[cubic-bezier(0.16,1,0.3,1)] flex items-center justify-between shadow-2xs cursor-pointer select-none disabled:opacity-50 disabled:pointer-events-none ${
          sizeStyles[size]
        } ${
          isOpen ? 'ring-2 ring-primary/20 border-primary/60 bg-surface-elevated' : ''
        } ${triggerClassName}`}
      >
        <div className="flex items-center gap-1.5 min-w-0 truncate">
          {prefix && <span className="text-text-muted flex-shrink-0">{prefix}</span>}
          {selectedOption?.icon && (
            <span className="flex-shrink-0 flex items-center text-text-secondary">
              {selectedOption.icon}
            </span>
          )}
          <span className="truncate">
            {selectedOption ? selectedOption.label : placeholder}
          </span>
          {selectedOption?.sublabel && (
            <span className="text-[10px] text-text-muted truncate ml-1 font-normal hidden sm:inline">
              {selectedOption.sublabel}
            </span>
          )}
        </div>

        <ChevronDown
          className={`w-3.5 h-3.5 text-text-muted transition-transform duration-200 flex-shrink-0 ml-1.5 ${
            isOpen ? 'rotate-180 text-primary' : ''
          }`}
        />
      </button>

      {/* Floating Popover Menu */}
      {isOpen && (
        <div
          role="listbox"
          className={`absolute z-50 mt-1 min-w-full w-max max-w-[320px] bg-surface-elevated border border-border-default rounded-xl shadow-xl p-1.5 space-y-0.5 max-h-60 overflow-y-auto animate-in fade-in zoom-in-95 duration-100 ease-[cubic-bezier(0.16,1,0.3,1)] ${
            align === 'right' ? 'right-0' : 'left-0'
          } ${dropdownClassName}`}
        >
          {options.length === 0 ? (
            <div className="py-2 px-3 text-xs text-text-muted text-center italic">
              Không có lựa chọn nào
            </div>
          ) : (
            options.map((option) => {
              const isSelected = option.value === value;
              return (
                <button
                  key={String(option.value)}
                  type="button"
                  role="option"
                  aria-selected={isSelected}
                  disabled={option.disabled}
                  onClick={() => handleSelect(option)}
                  className={`w-full text-left px-2.5 py-1.5 rounded-lg text-xs flex items-center justify-between gap-2.5 transition-colors duration-100 select-none cursor-pointer disabled:opacity-40 disabled:pointer-events-none ${
                    isSelected
                      ? 'bg-primary/10 text-primary font-semibold'
                      : 'text-text-primary hover:bg-surface-hover'
                  }`}
                >
                  <div className="flex items-center gap-2 min-w-0 truncate">
                    {option.icon && (
                      <span className="flex-shrink-0 flex items-center text-text-muted">
                        {option.icon}
                      </span>
                    )}
                    <span className="truncate">{option.label}</span>
                    {option.sublabel && (
                      <span className="text-[10px] text-text-muted truncate font-normal">
                        {option.sublabel}
                      </span>
                    )}
                  </div>

                  {isSelected && (
                    <Check className="w-3.5 h-3.5 text-primary flex-shrink-0" />
                  )}
                </button>
              );
            })
          )}
        </div>
      )}
    </div>
  );
}

export default Select;
