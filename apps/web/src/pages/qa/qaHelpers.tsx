import React, { useEffect, useState } from 'react';
import { Badge } from '../../components/ui/Badge';
import { ProviderModelSelector } from '../../components/ProviderModelSelector';
import { apiClient } from '../../api/client';
import { ProviderInfo } from '../../types';

export const knowledgeVariant = (k: string): 'success' | 'warning' | 'purple' => {
  if (k === 'Confirmed') return 'success';
  if (k === 'Inferred') return 'warning';
  return 'purple';
};

export const knowledgeLabel = (k: string): string => {
  if (k === 'Confirmed') return 'Confirmed';
  if (k === 'Inferred') return 'Inferred';
  return 'AI Suggested';
};

export const KnowledgeBadge: React.FC<{ value: string }> = ({ value }) => (
  <Badge variant={knowledgeVariant(value)} title="Nguồn gốc thông tin: Confirmed = có evidence, Inferred = suy luận, AI Suggested = gợi ý theo QA best practice">
    {knowledgeLabel(value)}
  </Badge>
);

export const coverageVariant = (s: string): 'success' | 'warning' | 'danger' | 'info' | 'neutral' => {
  if (s === 'Covered') return 'success';
  if (s === 'PartiallyCovered') return 'warning';
  if (s === 'BlockedByClarification') return 'danger';
  if (s === 'NotCovered') return 'info';
  return 'neutral';
};

export const coverageLabel = (s: string): string => {
  const map: Record<string, string> = {
    Covered: 'Covered',
    PartiallyCovered: 'Partially Covered',
    NotCovered: 'Not Covered',
    BlockedByClarification: 'Blocked by Clarification',
    NotReviewed: 'Not Reviewed',
  };
  return map[s] || s;
};

export const CoverageBadge: React.FC<{ value: string }> = ({ value }) => (
  <Badge variant={coverageVariant(value)} dot>{coverageLabel(value)}</Badge>
);

export const severityVariant = (s: string): 'danger' | 'warning' | 'info' | 'neutral' => {
  if (s === 'CRITICAL' || s === 'HIGH') return 'danger';
  if (s === 'MEDIUM') return 'warning';
  return 'neutral';
};

export const statusVariant = (s: string): 'success' | 'warning' | 'danger' | 'info' | 'neutral' | 'primary' | 'purple' => {
  const u = (s || '').toUpperCase();
  if (['APPROVED', 'CONFIRMED', 'RESOLVED', 'ANSWERED', 'COVERED', 'PASS', 'COMPLETED', 'CLOSED', 'FIXED'].includes(u)) return 'success';
  if (['DRAFT', 'PROPOSED', 'OPEN', 'REVIEWED', 'NEEDS_CONFIRMATION', 'NOT_RUN', 'READY', 'RUNNING', 'RETEST'].includes(u)) return 'warning';
  if (['REJECTED', 'IGNORED', 'CONFLICT', 'BLOCKED', 'FAIL', 'CANCELLED'].includes(u)) return 'danger';
  if (['IN_PROGRESS', 'SKIPPED'].includes(u)) return 'info';
  if (['DONE'].includes(u)) return 'primary';
  return 'neutral';
};

export const execVariant = (s: string): 'success' | 'warning' | 'danger' | 'info' | 'neutral' => {
  if (s === 'Passed' || s === 'PASS') return 'success';
  if (s === 'Failed' || s === 'FAIL') return 'danger';
  if (s === 'Blocked' || s === 'BLOCKED') return 'danger';
  if (s === 'NotExecuted' || s === 'NOT_RUN' || s === 'RUNNING') return 'warning';
  if (s === 'SKIPPED') return 'info';
  return 'neutral';
};

export const ExecBadge: React.FC<{ value: string }> = ({ value }) => (
  <Badge variant={execVariant(value)} dot>{value}</Badge>
);

/** Shared AI provider picker for QA generation actions (user-selected provider per human decision). */
export const useQAProviders = () => {
  const [providers, setProviders] = useState<ProviderInfo[]>([]);
  const [selectedProvider, setSelectedProvider] = useState<string>('auto');
  const [selectedModel, setSelectedModel] = useState<string>('');
  useEffect(() => {
    apiClient.getProviders().then(setProviders).catch(() => undefined);
  }, []);
  const opts =
    selectedProvider && selectedProvider !== 'auto'
      ? { preferred_provider: selectedProvider, model: selectedModel || undefined }
      : {};
  const picker = (
    <ProviderModelSelector
      providers={providers}
      selectedProvider={selectedProvider}
      onChangeProvider={setSelectedProvider}
      selectedModel={selectedModel}
      onChangeModel={setSelectedModel}
      layout="inline"
    />
  );
  return { providers, selectedProvider, selectedModel, opts, picker };
};
