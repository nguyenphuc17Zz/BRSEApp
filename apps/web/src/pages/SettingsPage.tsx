import React from 'react';
import { 
  Settings as SettingsIcon, 
  Database, 
  ShieldCheck, 
  Keyboard, 
  HardDrive, 
  Layers, 
  HelpCircle 
} from 'lucide-react';

export const SettingsPage: React.FC = () => {
  return (
    <div className="flex-1 flex flex-col h-screen overflow-y-auto bg-slate-950 p-6 space-y-6">
      <div>
        <h2 className="text-xl font-bold text-white flex items-center gap-2">
          <SettingsIcon className="w-5 h-5 text-sky-400" />
          System Settings & Platform Architecture
        </h2>
        <p className="text-xs text-slate-400">
          Local data storage paths, keyboard shortcuts, and Phase 2 compatibility interfaces.
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Local-First Architecture & Storage */}
        <div className="p-5 rounded-xl border border-slate-800 bg-slate-900/50 space-y-4">
          <h3 className="text-sm font-bold text-white flex items-center gap-2">
            <HardDrive className="w-4 h-4 text-sky-400" />
            Local Data & Storage Security
          </h3>

          <div className="space-y-3 text-xs text-slate-300">
            <div>
              <span className="text-slate-400 block mb-1">Database Location (SQLite):</span>
              <code className="block bg-slate-850 p-2.5 rounded border border-slate-800 text-sky-400 font-mono text-[11px]">
                E:\AutomationTranslate\data\comtor_copilot.db
              </code>
            </div>

            <div>
              <span className="text-slate-400 block mb-1">Vector Embedding Engine:</span>
              <div className="p-2.5 rounded bg-slate-850 border border-slate-800 text-[11px]">
                Local Ollama <strong className="text-white">nomic-embed-text:latest</strong> with cosine similarity calculation for Translation Memory matching.
              </div>
            </div>

            <div>
              <span className="text-slate-400 block mb-1">Secret / Credential Encryption:</span>
              <div className="p-2.5 rounded bg-slate-850 border border-slate-800 text-[11px] text-emerald-400 flex items-center gap-1.5">
                <ShieldCheck className="w-4 h-4" />
                AES-256 Fernet encryption active. Provider API keys are never sent to browser source or unmasked logs.
              </div>
            </div>
          </div>
        </div>

        {/* Keyboard Shortcuts */}
        <div className="p-5 rounded-xl border border-slate-800 bg-slate-900/50 space-y-4">
          <h3 className="text-sm font-bold text-white flex items-center gap-2">
            <Keyboard className="w-4 h-4 text-indigo-400" />
            Keyboard Shortcuts
          </h3>

          <div className="space-y-2 text-xs">
            <div className="flex items-center justify-between p-2.5 rounded bg-slate-850 border border-slate-800 text-slate-300">
              <span>Execute Translation</span>
              <kbd className="px-2 py-1 rounded bg-slate-800 border border-slate-700 font-mono text-[10px] text-sky-400">
                Ctrl + Enter
              </kbd>
            </div>
            <div className="flex items-center justify-between p-2.5 rounded bg-slate-850 border border-slate-800 text-slate-300">
              <span>Quick Copy Selected Translation</span>
              <kbd className="px-2 py-1 rounded bg-slate-800 border border-slate-700 font-mono text-[10px] text-slate-300">
                Click Copy Icon
              </kbd>
            </div>
            <div className="flex items-center justify-between p-2.5 rounded bg-slate-850 border border-slate-800 text-slate-300">
              <span>Explain Nuance</span>
              <kbd className="px-2 py-1 rounded bg-slate-800 border border-slate-700 font-mono text-[10px] text-slate-300">
                Click ? Icon
              </kbd>
            </div>
          </div>
        </div>

        {/* Phase 2 Extension Interfaces */}
        <div className="lg:col-span-2 p-5 rounded-xl border border-slate-800 bg-slate-900/50 space-y-3">
          <h3 className="text-sm font-bold text-white flex items-center gap-2">
            <Layers className="w-4 h-4 text-emerald-400" />
            Phase 2–4 Extensibility Status
          </h3>
          <p className="text-xs text-slate-400">
            Phase 1 exposes stable abstractions for future integrations without modifying the core engine:
          </p>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-xs">
            <div className="p-3 rounded-lg bg-slate-850 border border-slate-800">
              <strong className="text-white block mb-1">Phase 2: File Processing</strong>
              <p className="text-slate-400 text-[11px]">
                Extension point: <code className="text-sky-400">DocumentSource</code> for DOCX, XLSX, PPTX, PDF, and OCR.
              </p>
            </div>

            <div className="p-3 rounded-lg bg-slate-850 border border-slate-800">
              <strong className="text-white block mb-1">Phase 3: Integrations</strong>
              <p className="text-slate-400 text-[11px]">
                Extension point: <code className="text-sky-400">MessageSource</code> & <code className="text-sky-400">ConversationContext</code> for Slack, Google Docs, Clipboard.
              </p>
            </div>

            <div className="p-3 rounded-lg bg-slate-850 border border-slate-800">
              <strong className="text-white block mb-1">Phase 4: BrSE Intelligence</strong>
              <p className="text-slate-400 text-[11px]">
                Extension point: Requirement extraction, Bug detection, Decision logs, and automated replies.
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
