import React, { useState, useRef, useEffect, useMemo } from 'react';
import { Search, ChevronDown, Check, Sparkles, X } from 'lucide-react';

export interface SearchableModelSelectProps {
  models: string[];
  selectedModel: string;
  onSelectModel: (model: string) => void;
  defaultModel?: string;
  disabled?: boolean;
  disabledPlaceholder?: string;
  placeholder?: string;
  className?: string;
  buttonClassName?: string;
}

export const SearchableModelSelect: React.FC<SearchableModelSelectProps> = ({
  models = [],
  selectedModel,
  onSelectModel,
  defaultModel,
  disabled = false,
  disabledPlaceholder = '⚡ Auto (Tự động điều phối)',
  placeholder = 'Chọn model...',
  className = '',
  buttonClassName = ''
}) => {
  const [isOpen, setIsOpen] = useState<boolean>(false);
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [highlightedIndex, setHighlightedIndex] = useState<number>(0);
  const containerRef = useRef<HTMLDivElement>(null);
  const searchInputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  // Filter models based on search query
  const filteredModels = useMemo(() => {
    if (!searchQuery.trim()) return models;
    const query = searchQuery.toLowerCase().trim();
    return models.filter((m) => m.toLowerCase().includes(query));
  }, [models, searchQuery]);

  // Click outside listener
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

  // Autofocus input when opened
  useEffect(() => {
    if (isOpen) {
      setSearchQuery('');
      setHighlightedIndex(0);
      setTimeout(() => {
        searchInputRef.current?.focus();
      }, 50);
    }
  }, [isOpen]);

  // Keyboard navigation
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (!isOpen) {
      if (e.key === 'Enter' || e.key === ' ' || e.key === 'ArrowDown') {
        e.preventDefault();
        setIsOpen(true);
      }
      return;
    }

    if (e.key === 'Escape') {
      e.preventDefault();
      setIsOpen(false);
    } else if (e.key === 'ArrowDown') {
      e.preventDefault();
      setHighlightedIndex((prev) => (prev + 1) % Math.max(1, filteredModels.length));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setHighlightedIndex((prev) => (prev - 1 + filteredModels.length) % Math.max(1, filteredModels.length));
    } else if (e.key === 'Enter') {
      e.preventDefault();
      if (filteredModels.length > 0 && highlightedIndex >= 0 && highlightedIndex < filteredModels.length) {
        onSelectModel(filteredModels[highlightedIndex]);
        setIsOpen(false);
      }
    }
  };

  // Scroll highlighted item into view
  useEffect(() => {
    if (isOpen && listRef.current) {
      const activeElement = listRef.current.children[highlightedIndex] as HTMLElement;
      if (activeElement) {
        activeElement.scrollIntoView({ block: 'nearest' });
      }
    }
  }, [highlightedIndex, isOpen]);

  // Substring highlight helper
  const renderHighlightedText = (text: string, query: string) => {
    if (!query.trim()) return text;
    const regex = new RegExp(`(${query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'gi');
    const parts = text.split(regex);
    return parts.map((part, i) =>
      regex.test(part) ? (
        <span key={i} className="bg-sky-500/30 text-sky-200 font-semibold px-0.5 rounded">
          {part}
        </span>
      ) : (
        part
      )
    );
  };

  return (
    <div className={`relative ${className}`} ref={containerRef} onKeyDown={handleKeyDown}>
      {/* Trigger Button */}
      <button
        type="button"
        disabled={disabled}
        onClick={() => setIsOpen(!isOpen)}
        className={`flex items-center justify-between gap-2 px-3 py-1.5 rounded-lg border text-xs font-mono transition-all outline-none ${
          disabled
            ? 'bg-slate-900/60 border-slate-800/80 text-slate-500 cursor-not-allowed'
            : isOpen
            ? 'bg-slate-800 border-sky-500 shadow-md shadow-sky-500/20 text-white'
            : 'bg-slate-850 hover:bg-slate-800 border-slate-700 text-slate-200 hover:border-slate-600'
        } ${buttonClassName}`}
      >
        <div className="flex items-center gap-1.5 truncate">
          {disabled ? (
            <span className="truncate italic text-slate-400">{disabledPlaceholder}</span>
          ) : selectedModel ? (
            <>
              <span className="truncate">{selectedModel}</span>
              {defaultModel && selectedModel === defaultModel && (
                <span className="hidden sm:inline-flex px-1.5 py-0.2 rounded text-[9px] font-sans font-semibold bg-sky-500/20 text-sky-300 border border-sky-500/30">
                  Default
                </span>
              )}
            </>
          ) : (
            <span className="text-slate-500">{placeholder}</span>
          )}
        </div>

        <ChevronDown
          className={`w-3.5 h-3.5 text-slate-400 flex-shrink-0 transition-transform duration-200 ${
            isOpen ? 'rotate-180 text-sky-400' : ''
          }`}
        />
      </button>

      {/* Glassmorphic Combobox Popover */}
      {isOpen && !disabled && (
        <div className="absolute z-[100] mt-1.5 w-full min-w-[280px] max-w-[360px] rounded-xl border border-slate-700/80 bg-slate-900/95 backdrop-blur-xl shadow-2xl shadow-black/80 overflow-hidden flex flex-col animate-in fade-in zoom-in-95 duration-150">
          {/* Search Header */}
          <div className="p-2 border-b border-slate-800 bg-slate-950/70 flex items-center gap-2">
            <div className="relative flex-1">
              <Search className="w-3.5 h-3.5 text-slate-400 absolute left-2.5 top-2.5" />
              <input
                ref={searchInputRef}
                type="text"
                value={searchQuery}
                onChange={(e) => {
                  setSearchQuery(e.target.value);
                  setHighlightedIndex(0);
                }}
                placeholder="Gõ để tìm model (e.g. flash, 70b, qwen)..."
                className="w-full bg-slate-900 border border-slate-700/80 rounded-lg pl-8 pr-7 py-1.5 text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:border-sky-500 font-sans"
              />
              {searchQuery && (
                <button
                  onClick={() => {
                    setSearchQuery('');
                    searchInputRef.current?.focus();
                  }}
                  className="absolute right-2 top-2 text-slate-400 hover:text-white p-0.5 rounded"
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              )}
            </div>
          </div>

          {/* Result Count Indicator */}
          <div className="px-3 py-1 bg-slate-950/40 border-b border-slate-800/60 flex items-center justify-between text-[10px] text-slate-400 font-mono">
            <span>
              Tìm thấy: <strong className="text-sky-300">{filteredModels.length}</strong> / {models.length} models
            </span>
            {searchQuery && (
              <span className="text-slate-500">Lọc theo: "{searchQuery}"</span>
            )}
          </div>

          {/* Scrollable Model List */}
          <div ref={listRef} className="max-h-60 overflow-y-auto p-1.5 space-y-0.5 font-mono text-xs">
            {filteredModels.length === 0 ? (
              <div className="p-6 text-center text-slate-500 text-xs font-sans">
                <Search className="w-6 h-6 mx-auto mb-2 text-slate-600" />
                <p>Không tìm thấy model nào khớp với "{searchQuery}"</p>
              </div>
            ) : (
              filteredModels.map((model, idx) => {
                const isSelected = model === selectedModel;
                const isHighlighted = idx === highlightedIndex;
                const isDefault = defaultModel && model === defaultModel;

                return (
                  <button
                    key={model}
                    type="button"
                    onClick={() => {
                      onSelectModel(model);
                      setIsOpen(false);
                    }}
                    onMouseEnter={() => setHighlightedIndex(idx)}
                    className={`w-full text-left px-3 py-2 rounded-lg flex items-center justify-between gap-2 transition-colors ${
                      isSelected
                        ? 'bg-sky-600/20 text-sky-200 border border-sky-500/30'
                        : isHighlighted
                        ? 'bg-slate-800/90 text-white'
                        : 'text-slate-300 hover:bg-slate-800/50'
                    }`}
                  >
                    <div className="flex items-center gap-2 truncate flex-1">
                      <span className="truncate">{renderHighlightedText(model, searchQuery)}</span>
                      {isDefault && (
                        <span className="px-1.5 py-0.2 rounded text-[9px] font-sans font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 flex-shrink-0">
                          Default
                        </span>
                      )}
                    </div>

                    {isSelected && (
                      <Check className="w-3.5 h-3.5 text-sky-400 flex-shrink-0" />
                    )}
                  </button>
                );
              })
            )}
          </div>
        </div>
      )}
    </div>
  );
};
