import React, { useMemo } from 'react';
import { ProviderInfo } from '../types';
import { SearchableModelSelect } from './SearchableModelSelect';
import { Select, SelectOption } from './ui/Select';
import { Cpu, Zap } from 'lucide-react';
import { saveProviderPreference, saveModelPreference } from '../utils/aiPreferences';

export interface ProviderModelSelectorProps {
  providers: ProviderInfo[];
  selectedProvider: string; // 'auto' | provider name
  onChangeProvider?: (provider: string) => void;
  onProviderChange?: (provider: string) => void;
  selectedModel: string;
  onChangeModel?: (model: string) => void;
  onModelChange?: (model: string) => void;
  allowAutoRouter?: boolean;
  layout?: 'inline' | 'stacked';
  className?: string;
}

export const ProviderModelSelector: React.FC<ProviderModelSelectorProps> = ({
  providers = [],
  selectedProvider = 'auto',
  onChangeProvider,
  onProviderChange,
  selectedModel,
  onChangeModel,
  onModelChange,
  allowAutoRouter = true,
  layout = 'inline',
  className = ''
}) => {
  const triggerProviderChange = (provider: string) => {
    if (onChangeProvider) onChangeProvider(provider);
    else if (onProviderChange) onProviderChange(provider);
  };

  const triggerModelChange = (model: string) => {
    if (onChangeModel) onChangeModel(model);
    else if (onModelChange) onModelChange(model);
  };

  const activeProvider = providers.find((p) => p.name === selectedProvider);
  const availableModels = activeProvider?.available_models || [];
  const defaultModel = activeProvider?.default_model;

  const providerOptions: SelectOption<string>[] = useMemo(() => {
    const list: SelectOption<string>[] = [];
    if (allowAutoRouter) {
      list.push({
        value: 'auto',
        label: 'Auto Router',
        sublabel: '(Tự động chọn)',
        icon: <Zap className="w-3.5 h-3.5 text-amber-500" />
      });
    }
    providers.forEach((p) => {
      list.push({
        value: p.name,
        label: p.display_name,
        sublabel: `(${p.available_models.length} models)`,
        icon: <Cpu className="w-3.5 h-3.5 text-primary" />
      });
    });
    return list;
  }, [allowAutoRouter, providers]);

  const handleProviderSelect = (nextProvider: string) => {
    triggerProviderChange(nextProvider);
    saveProviderPreference(nextProvider);

    if (nextProvider === 'auto') {
      triggerModelChange('');
      saveModelPreference('');
    } else {
      const p = providers.find((prov) => prov.name === nextProvider);
      if (p && p.available_models.length > 0) {
        if (!p.available_models.includes(selectedModel)) {
          const nextModel = p.default_model || p.available_models[0];
          triggerModelChange(nextModel);
          saveModelPreference(nextModel);
        } else {
          saveModelPreference(selectedModel);
        }
      }
    }
  };

  const handleModelChange = (model: string) => {
    triggerModelChange(model);
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
          <label className="block text-text-secondary font-medium mb-1 text-xs flex items-center gap-1.5">
            <Cpu className="w-3.5 h-3.5 text-primary" />
            AI Provider
          </label>
          <Select
            options={providerOptions}
            value={selectedProvider}
            onChange={handleProviderSelect}
            className="w-full"
            triggerClassName="w-full h-[35px]"
          />
        </div>

        <div>
          <label className="block text-text-secondary font-medium mb-1 text-xs flex items-center gap-1.5">
            <Zap className="w-3.5 h-3.5 text-emerald-500" />
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
        <span className="text-xs font-medium text-text-secondary">Provider:</span>
        <Select
          options={providerOptions}
          value={selectedProvider}
          onChange={handleProviderSelect}
          size="sm"
          className="min-w-[150px] max-w-[220px]"
        />
      </div>

      {/* Searchable Model Combobox */}
      <div className="flex items-center gap-1.5">
        <span className="text-xs font-medium text-text-secondary">Model:</span>
        <SearchableModelSelect
          models={availableModels}
          selectedModel={selectedModel}
          onSelectModel={handleModelChange}
          defaultModel={defaultModel}
          disabled={isAuto}
          disabledPlaceholder="⚡ Auto (Adaptive Orchestration)"
          placeholder="Tìm và chọn model..."
          className="min-w-[180px] max-w-[280px]"
        />
      </div>
    </div>
  );
};

