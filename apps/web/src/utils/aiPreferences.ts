import { ProviderInfo } from '../types';

export const AI_PROVIDER_KEY = 'at_selected_provider';
export const AI_MODEL_KEY = 'at_selected_model';
export const ACTIVE_PROJECT_KEY = 'at_active_project_id';

export const DEFAULT_PROVIDER = 'gemini';
export const DEFAULT_MODEL = 'gemini-3.7-flash';

/**
 * Retrieves the user's previously chosen active project ID from localStorage.
 */
export function getSavedProjectId(): string | null {
  try {
    const saved = localStorage.getItem(ACTIVE_PROJECT_KEY);
    return saved && saved.trim() ? saved.trim() : null;
  } catch {
    return null;
  }
}

/**
 * Persists the selected active project ID to localStorage.
 */
export function saveActiveProjectId(projectId: string | null | undefined): void {
  try {
    if (projectId && projectId.trim()) {
      localStorage.setItem(ACTIVE_PROJECT_KEY, projectId.trim());
    } else {
      localStorage.removeItem(ACTIVE_PROJECT_KEY);
    }
  } catch (err) {
    console.warn('Could not save active project preference:', err);
  }
}


/**
 * Retrieves the user's previously chosen AI provider from localStorage.
 */
export function getSavedProvider(fallback: string = DEFAULT_PROVIDER): string {
  try {
    const saved = localStorage.getItem(AI_PROVIDER_KEY);
    return saved && saved.trim() ? saved.trim() : fallback;
  } catch {
    return fallback;
  }
}

/**
 * Retrieves the user's previously chosen AI model from localStorage.
 */
export function getSavedModel(fallback: string = DEFAULT_MODEL): string {
  try {
    const saved = localStorage.getItem(AI_MODEL_KEY);
    return saved && saved.trim() ? saved.trim() : fallback;
  } catch {
    return fallback;
  }
}

/**
 * Persists the selected provider to localStorage.
 */
export function saveProviderPreference(provider: string): void {
  try {
    if (provider && provider.trim()) {
      localStorage.setItem(AI_PROVIDER_KEY, provider.trim());
    }
  } catch (err) {
    console.warn('Could not save provider preference:', err);
  }
}

/**
 * Persists the selected model to localStorage.
 */
export function saveModelPreference(model: string): void {
  try {
    if (model && model.trim()) {
      localStorage.setItem(AI_MODEL_KEY, model.trim());
    }
  } catch (err) {
    console.warn('Could not save model preference:', err);
  }
}

/**
 * Atomically saves both provider and model preferences.
 */
export function saveAIPreferences(provider: string, model: string): void {
  saveProviderPreference(provider);
  saveModelPreference(model);
}

/**
 * Validates a saved provider & model against available active providers,
 * returning a validated pair (falling back gracefully to defaults if the saved model/provider is disabled).
 */
export function resolveHealthyModel(
  providers: ProviderInfo[],
  fallbackProvider: string = DEFAULT_PROVIDER,
  fallbackModel: string = DEFAULT_MODEL
): { provider: string; model: string } {
  if (!providers || providers.length === 0) {
    return { provider: fallbackProvider, model: fallbackModel };
  }

  const savedP = getSavedProvider(fallbackProvider);
  const savedM = getSavedModel(fallbackModel);

  // If saved provider is 'auto'
  if (savedP === 'auto') {
    return { provider: 'auto', model: '' };
  }

  // Find saved provider in list
  const matchingProv = providers.find((p) => p.name === savedP && p.is_enabled && p.is_healthy);
  if (matchingProv) {
    const models = matchingProv.available_models || [];
    if (savedM && models.includes(savedM)) {
      return { provider: matchingProv.name, model: savedM };
    }
    const defaultM = matchingProv.default_model || models[0] || fallbackModel;
    return { provider: matchingProv.name, model: defaultM };
  }

  // Fallback to first healthy enabled provider
  const healthyProv = providers.find((p) => p.is_enabled && p.is_healthy) || providers[0];
  if (healthyProv) {
    const models = healthyProv.available_models || [];
    const defaultM = healthyProv.default_model || models[0] || fallbackModel;
    return { provider: healthyProv.name, model: defaultM };
  }

  return { provider: fallbackProvider, model: fallbackModel };
}
