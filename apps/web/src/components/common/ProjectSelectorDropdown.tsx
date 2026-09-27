import React, { useState, useRef, useEffect, useMemo } from 'react';
import { 
  FolderKanban, 
  ChevronDown, 
  Check, 
  Search, 
  Globe, 
  X
} from 'lucide-react';
import { Project } from '../../types';

export interface ProjectSelectorDropdownProps {
  projects: Project[];
  activeProject: Project | null;
  onSelectProject: (p: Project | null) => void;
  className?: string;
}

export const ProjectSelectorDropdown: React.FC<ProjectSelectorDropdownProps> = ({
  projects,
  activeProject,
  onSelectProject,
  className = '',
}) => {
  const [isOpen, setIsOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const containerRef = useRef<HTMLDivElement>(null);
  const searchInputRef = useRef<HTMLInputElement>(null);

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
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen]);

  // Focus search input when popover opens
  useEffect(() => {
    if (isOpen) {
      setTimeout(() => {
        searchInputRef.current?.focus();
      }, 50);
    } else {
      setSearchQuery('');
    }
  }, [isOpen]);

  // Filter projects by name or code
  const filteredProjects = useMemo(() => {
    if (!searchQuery.trim()) return projects;
    const q = searchQuery.toLowerCase().trim();
    return projects.filter(
      (p) =>
        p.name.toLowerCase().includes(q) ||
        (p.code && p.code.toLowerCase().includes(q)) ||
        (p.description && p.description.toLowerCase().includes(q))
    );
  }, [projects, searchQuery]);

  return (
    <div ref={containerRef} className={`relative inline-block text-left ${className}`}>
      {/* Trigger Button */}
      <button
        type="button"
        onClick={() => setIsOpen((prev) => !prev)}
        aria-haspopup="listbox"
        aria-expanded={isOpen}
        className={`h-9 px-3 rounded-lg border transition-all duration-150 ease-[cubic-bezier(0.16,1,0.3,1)] active:scale-[0.98] flex items-center gap-2 cursor-pointer text-xs font-medium select-none shadow-2xs ${
          isOpen
            ? 'bg-surface-elevated border-primary/50 text-text-primary ring-2 ring-primary/15'
            : 'bg-surface-subtle hover:bg-surface-hover border-border-default/80 text-text-secondary hover:text-text-primary'
        }`}
        title="Chọn dự án làm việc"
      >
        <FolderKanban className="w-3.5 h-3.5 text-primary flex-shrink-0" />
        
        <span className="max-w-[130px] sm:max-w-[180px] truncate text-text-primary font-medium">
          {activeProject ? activeProject.name : 'Global (All Projects)'}
        </span>

        {activeProject?.code && (
          <span className="hidden sm:inline-block px-2 py-0.5 rounded text-[10px] font-mono font-semibold bg-primary/10 text-primary border border-primary/20">
            {activeProject.code}
          </span>
        )}

        <ChevronDown
          className={`w-3.5 h-3.5 text-text-muted transition-transform duration-200 ease-[cubic-bezier(0.16,1,0.3,1)] flex-shrink-0 ${
            isOpen ? 'rotate-180 text-primary' : ''
          }`}
        />
      </button>

      {/* Floating Popover */}
      {isOpen && (
        <div
          role="listbox"
          className="absolute right-0 top-full mt-1.5 w-72 sm:w-80 bg-surface-elevated border border-border-default rounded-xl shadow-2xl z-50 p-2 animate-modal-in backdrop-blur-xl"
        >
          {/* Header & Search */}
          <div className="px-1.5 pb-2 mb-1.5 border-b border-border-subtle">
            <div className="flex items-center justify-between pb-1.5">
              <span className="text-[11px] font-semibold text-text-muted uppercase tracking-wider">
                Không gian làm việc
              </span>
              <span className="text-[10px] text-text-muted font-mono">
                {projects.length} dự án
              </span>
            </div>

            {/* Quick Filter Input */}
            <div className="relative flex items-center">
              <Search className="w-3.5 h-3.5 absolute left-2.5 text-text-muted pointer-events-none" />
              <input
                ref={searchInputRef}
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Tìm theo tên hoặc mã dự án..."
                className="w-full bg-surface-subtle border border-border-subtle focus:border-primary rounded-lg pl-8 pr-7 py-1.5 text-xs text-text-primary placeholder:text-text-muted focus:outline-none focus:ring-1 focus:ring-primary/30 transition-colors"
              />
              {searchQuery && (
                <button
                  type="button"
                  onClick={() => setSearchQuery('')}
                  className="absolute right-2 p-0.5 rounded text-text-muted hover:text-text-primary hover:bg-surface-hover"
                >
                  <X className="w-3 h-3" />
                </button>
              )}
            </div>
          </div>

          {/* Project List */}
          <div className="max-h-60 overflow-y-auto space-y-0.5 pr-0.5">
            {/* Global Option (always available unless searching and doesn't match) */}
            {(!searchQuery || 'global all projects tất cả'.includes(searchQuery.toLowerCase())) && (
              <button
                type="button"
                onClick={() => {
                  onSelectProject(null);
                  setIsOpen(false);
                }}
                className={`w-full flex items-center justify-between px-2.5 py-2 rounded-lg text-xs transition-all duration-150 cursor-pointer ${
                  activeProject === null
                    ? 'bg-primary/10 text-primary font-semibold'
                    : 'text-text-secondary hover:text-text-primary hover:bg-surface-hover'
                }`}
              >
                <div className="flex items-center gap-2.5 min-w-0">
                  <div
                    className={`w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0 ${
                      activeProject === null
                        ? 'bg-primary text-white'
                        : 'bg-surface-subtle text-text-muted border border-border-subtle'
                    }`}
                  >
                    <Globe className="w-3.5 h-3.5" />
                  </div>
                  <div className="text-left min-w-0">
                    <div className="font-medium text-text-primary truncate">
                      Global (All Projects)
                    </div>
                    <div className="text-[10px] text-text-muted truncate">
                      Tất cả quy tắc & kho từ vựng chung
                    </div>
                  </div>
                </div>
                {activeProject === null && (
                  <Check className="w-4 h-4 text-primary flex-shrink-0 ml-2" />
                )}
              </button>
            )}

            {filteredProjects.length > 0 && (
              <div className="h-px bg-border-subtle my-1" />
            )}

            {/* Filtered Project Items */}
            {filteredProjects.map((p) => {
              const isSelected = activeProject?.id === p.id;
              const ruleCount = p.instructions_count || 0;

              return (
                <button
                  key={p.id}
                  type="button"
                  onClick={() => {
                    onSelectProject(p);
                    setIsOpen(false);
                  }}
                  className={`w-full flex items-center justify-between px-2.5 py-2 rounded-lg text-xs transition-all duration-150 cursor-pointer group ${
                    isSelected
                      ? 'bg-primary/10 text-primary font-semibold'
                      : 'text-text-secondary hover:text-text-primary hover:bg-surface-hover'
                  }`}
                >
                  <div className="flex items-center gap-2.5 min-w-0">
                    <div
                      className={`w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0 ${
                        isSelected
                          ? 'bg-primary text-white shadow-xs'
                          : 'bg-surface-subtle text-text-muted group-hover:text-primary border border-border-subtle transition-colors'
                      }`}
                    >
                      <FolderKanban className="w-3.5 h-3.5" />
                    </div>
                    <div className="text-left min-w-0">
                      <div className="flex items-center gap-1.5">
                        <span className="font-medium text-text-primary truncate">
                          {p.name}
                        </span>
                        {p.code && (
                          <span className="px-2 py-0.5 rounded text-[9px] font-mono font-semibold bg-surface-subtle border border-border-subtle text-text-muted group-hover:text-text-secondary">
                            {p.code}
                          </span>
                        )}
                      </div>
                      <div className="text-[10px] text-text-muted truncate">
                        {p.description || (p.client_name ? `Khách hàng: ${p.client_name}` : ruleCount > 0 ? `${ruleCount} chỉ dẫn dịch` : 'Dự án đang hoạt động')}
                      </div>
                    </div>
                  </div>

                  {isSelected && (
                    <Check className="w-4 h-4 text-primary flex-shrink-0 ml-2" />
                  )}
                </button>
              );
            })}

            {filteredProjects.length === 0 && searchQuery && (
              <div className="py-6 text-center text-text-muted text-xs">
                Không tìm thấy dự án "{searchQuery}"
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
