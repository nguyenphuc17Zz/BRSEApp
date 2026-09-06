import React from 'react';
import { ProviderInfo } from '../types';
import { SearchableModelSelect } from './SearchableModelSelect';
import { Cpu, Zap } from 'lucide-react';
import { saveProviderPreference, saveModelPreference } from '../utils/aiPreferences';

export interface ProviderModelSelectorProps {
  providers: ProviderInfo[];
  selectedProvider: string; // 'auto' | provider name
  onChangeProvider: (provider: string) => void;
  selectedModel: string;
  onChangeModel: (model: string) => void;
  allowAutoRouter?: boolean;
  layout?: 'inline' | 'stacked';
  className?: string;
}

export const ProviderModelSelector: React.FC<ProviderModelSelectorProps> = ({
  providers = [],
  selectedProvider = 'auto',
  onChangeProvider,
  selectedModel,
  onChangeModel,
  allowAutoRouter = true,
  layout = 'inline',
  className = ''
}) => {
  const activeProvider = providers.find((p) => p.name === selectedProvider);
  const availableModels = activeProvider?.available_models || [];
  const defaultModel = activeProvider?.default_model;

  const handleProviderChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const nextProvider = e.target.value;
    onChangeProvider(nextProvider);
    saveProviderPreference(nextProvider);

    if (nextProvider === 'auto') {
      onChangeModel('');
      saveModelPreference('');
    } else {
      const p = providers.find((prov) => prov.name === nextProvider);
      if (p && p.available_models.length > 0) {
        if (!p.available_models.includes(selectedModel)) {
          const nextModel = p.default_model || p.available_models[0];
          onChangeModel(nextModel);
          saveModelPreference(nextModel);
        } else {
          saveModelPreference(selectedModel);
        }
      }
    }
  };

  const handleModelChange = (model: string) => {
    onChangeModel(model);
    saveModelPreference(model);
    if (selectedProvider && selectedProvider !== 'auto') {
      saveProviderPreference(selectedProvider);
    }
  };

  const isAuto = selectedProvider === 'auto';

  if (layout === 'stacked') {
    return (
      <div className={`grid grid-cols-1 sm:grid-cols-2 gap-3 ${className}`}>
        <div>
          <label className="block text-slate-400 font-semibold mb-1 text-xs flex items-center gap-1.5">
            <Cpu className="w-3.5 h-3.5 text-sky-400" />
            AI Provider
          </label>
          <select
            value={selectedProvider}
            onChange={handleProviderChange}
            className="w-full bg-slate-800 border border-slate-700 rounded-lg p-2 text-xs text-slate-200 focus:border-sky-500 focus:outline-none"
          >
            {allowAutoRouter && (
              <option value="auto">⚡ Auto Router (Tự động chọn)</option>
            )}
            {providers.map((p) => (
              <option key={p.name} value={p.name}>
                {p.display_name} ({p.available_models.length} models)
              </option>
            ))}
          </select>
        </div>

        <div>
          <label className="block text-slate-400 font-semibold mb-1 text-xs flex items-center gap-1.5">
            <Zap className="w-3.5 h-3.5 text-emerald-400" />
            Model (Searchable)
          </label>
          <SearchableModelSelect
            models={availableModels}
            selectedModel={selectedModel}
            onSelectModel={handleModelChange}
            defaultModel={defaultModel}
            disabled={isAuto}
            disabledPlaceholder="⚡ Auto (Tự động điều phối)"
            placeholder="Tìm và chọn model..."
            className="w-full"
            buttonClassName="w-full p-2 h-[35px]"
          />
        </div>
      </div>
    );
  }

  // Default: Inline layout for top navigation & action bars
  return (
    <div className={`flex items-center gap-2 flex-wrap ${className}`}>
      {/* Provider Selector */}
      <div className="flex items-center gap-1.5">
        <span className="text-xs font-semibold text-slate-300">Provider:</span>
        <select
          value={selectedProvider}
          onChange={handleProviderChange}
          className="bg-slate-800 border border-slate-700 text-slate-200 text-xs rounded-lg px-2.5 py-1.5 focus:outline-none focus:border-sky-500 font-sans"
        >
          {allowAutoRouter && (
            <option value="auto">⚡ Auto Router</option>
          )}
          {providers.map((p) => (
            <option key={p.name} value={p.name}>
              {p.display_name}
            </option>
          ))}
        </select>
      </div>

      {/* Searchable Model Combobox */}
      <div className="flex items-center gap-1.5">
        <span className="text-xs font-semibold text-slate-300">Model:</span>
        <SearchableModelSelect
          models={availableModels}
          selectedModel={selectedModel}
          onSelectModel={handleModelChange}
          defaultModel={defaultModel}
          disabled={isAuto}
          disabledPlaceholder="⚡ Auto (Adaptive Orchestration)"
          placeholder="Tìm và chọn model..."
          className="min-w-[200px] max-w-[300px]"
        />
      </div>
    </div>
  );
};
