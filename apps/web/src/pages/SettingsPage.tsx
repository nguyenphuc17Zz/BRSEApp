import React from 'react';
import { 
  Settings as SettingsIcon, 
  Database, 
  ShieldCheck, 
  Keyboard, 
  HardDrive,
  Sun,
  Moon,
  Laptop,
  Check,
  Cpu,
  Layers,
  Sparkles
} from 'lucide-react';
import { PageHeader } from '../components/ui/PageHeader';
import { Card } from '../components/ui/Card';
import { Badge } from '../components/ui/Badge';
import { useTheme } from '../context/ThemeContext';

export const SettingsPage: React.FC = () => {
  const { theme, setTheme } = useTheme();

  const themeOptions: Array<{ id: 'light' | 'dark' | 'system'; label: string; desc: string; icon: React.ReactNode }> = [
    {
      id: 'light',
      label: 'Light Mode',
      desc: 'Crisp high-contrast theme optimized for bright daytime office environments.',
      icon: <Sun className="w-5 h-5 text-amber-500" />
    },
    {
      id: 'dark',
      label: 'Dark Mode',
      desc: 'Premium neutral graphite dark palette designed to eliminate eye strain during long Comtor sessions.',
      icon: <Moon className="w-5 h-5 text-indigo-400" />
    },
    {
      id: 'system',
      label: 'System Preference',
      desc: 'Automatically synchronizes with your Windows/macOS operating system preference.',
      icon: <Laptop className="w-5 h-5 text-sky-400" />
    }
  ];

  return (
    <div className="flex-1 flex flex-col h-screen overflow-y-auto bg-canvas p-6 space-y-6">
      <PageHeader
        title="System Settings & Platform Architecture"
        description="Local-first offline architecture, theme appearance preferences, storage security, and comtor keyboard bindings."
      />

      {/* Theme Appearance Preference Card */}
      <Card className="p-5 border border-border-subtle bg-surface space-y-4">
        <div>
          <h3 className="text-sm font-bold text-text-primary flex items-center gap-2">
            <Sparkles className="w-4 h-4 text-primary" />
            Appearance & Interface Theme
          </h3>
          <p className="text-xs text-text-muted mt-1">
            Choose your preferred workspace aesthetic. Theme preference is automatically persisted to local client storage.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 pt-1">
          {themeOptions.map((opt) => {
            const isSelected = theme === opt.id;
            return (
              <div
                key={opt.id}
                onClick={() => setTheme(opt.id)}
                className={`p-4 rounded-xl border cursor-pointer transition-all flex flex-col justify-between space-y-3 ${
                  isSelected
                    ? 'border-primary/80 bg-surface-elevated ring-1 ring-primary/20 shadow-sm'
                    : 'border-border-subtle bg-surface-elevated/30 hover:border-border hover:bg-surface-elevated/60'
                }`}
              >
                <div className="flex items-center justify-between">
                  <div className="p-2 rounded-lg bg-surface border border-border-subtle">
                    {opt.icon}
                  </div>
                  {isSelected && (
                    <Badge variant="success" size="sm" className="flex items-center gap-1">
                      <Check className="w-3 h-3" /> Active
                    </Badge>
                  )}
                </div>

                <div>
                  <h4 className="text-xs font-semibold text-text-primary mb-1">{opt.label}</h4>
                  <p className="text-[11px] text-text-muted leading-relaxed">{opt.desc}</p>
                </div>
              </div>
            );
          })}
        </div>
      </Card>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Local-First Architecture & Storage */}
        <Card className="p-5 border border-border-subtle bg-surface space-y-4">
          <h3 className="text-sm font-bold text-text-primary flex items-center gap-2">
            <HardDrive className="w-4 h-4 text-primary" />
            Local Data & Storage Security
          </h3>

          <div className="space-y-3.5 text-xs text-text-secondary">
            <div>
              <span className="text-text-muted block mb-1">Local Database Engine:</span>
              <code className="block bg-surface-elevated p-2.5 rounded-lg border border-border-subtle text-primary font-mono text-[11px]">
                SQLite embedded storage (E:\AutomationTranslate\data\comtor_copilot.db)
              </code>
            </div>

            <div>
              <span className="text-text-muted block mb-1">Vector Embedding Engine:</span>
              <div className="p-2.5 rounded-lg bg-surface-elevated border border-border-subtle text-[11px] text-text-secondary">
                Local Ollama <strong className="text-text-primary">nomic-embed-text:latest</strong> with cosine similarity calculation for Translation Memory semantic matching.
              </div>
            </div>

            <div>
              <span className="text-text-muted block mb-1">Secret / Credential Encryption:</span>
              <div className="p-2.5 rounded-lg bg-surface-elevated border border-border-subtle text-[11px] text-emerald-500 flex items-center gap-1.5 font-medium">
                <ShieldCheck className="w-4 h-4 shrink-0" />
                AES-256 Fernet encryption active. Provider API keys are never exposed in plaintext logs.
              </div>
            </div>
          </div>
        </Card>

        {/* Keyboard Shortcuts */}
        <Card className="p-5 border border-border-subtle bg-surface space-y-4">
          <h3 className="text-sm font-bold text-text-primary flex items-center gap-2">
            <Keyboard className="w-4 h-4 text-primary" />
            Keyboard Shortcuts & Ergonomics
          </h3>

          <div className="space-y-2.5 text-xs">
            <div className="flex items-center justify-between p-2.5 rounded-lg bg-surface-elevated border border-border-subtle text-text-primary">
              <span className="text-text-secondary">Execute Translation in Workspace</span>
              <kbd className="px-2 py-1 rounded bg-surface border border-border font-mono text-[10px] text-primary font-semibold shadow-xs">
                Ctrl + Enter
              </kbd>
            </div>
            <div className="flex items-center justify-between p-2.5 rounded-lg bg-surface-elevated border border-border-subtle text-text-primary">
              <span className="text-text-secondary">Quick Translation Popup Hotkey</span>
              <kbd className="px-2 py-1 rounded bg-surface border border-border font-mono text-[10px] text-primary font-semibold shadow-xs">
                Ctrl + Shift + T
              </kbd>
            </div>
            <div className="flex items-center justify-between p-2.5 rounded-lg bg-surface-elevated border border-border-subtle text-text-primary">
              <span className="text-text-secondary">Quick Copy Active Translation</span>
              <kbd className="px-2 py-1 rounded bg-surface border border-border font-mono text-[10px] text-text-muted shadow-xs">
                Ctrl + C
              </kbd>
            </div>
            <div className="flex items-center justify-between p-2.5 rounded-lg bg-surface-elevated border border-border-subtle text-text-primary">
              <span className="text-text-secondary">Dismiss Modal / Dialog</span>
              <kbd className="px-2 py-1 rounded bg-surface border border-border font-mono text-[10px] text-text-muted shadow-xs">
                Escape
              </kbd>
            </div>
          </div>
        </Card>
      </div>
    </div>
  );
};
