import React, { useState } from 'react';
import { FileText, Image as ImageIcon, Link as LinkIcon, Terminal, Database, Globe } from 'lucide-react';
import { Badge } from '../../components/ui/Badge';
import { Modal } from '../../components/ui/Modal';
import { Button } from '../../components/ui/Button';
import { apiClient } from '../../api/client';
import { RunProgress, TestEvidence } from '../../types/qa';
import { statusVariant } from './qaHelpers';

export const ProgressBar: React.FC<{ progress: RunProgress }> = ({ progress }) => {
  const total = progress.total || 1;
  const segs = [
    { v: progress.pass, cls: 'bg-emerald-500' },
    { v: progress.fail, cls: 'bg-rose-500' },
    { v: progress.blocked, cls: 'bg-amber-500' },
    { v: progress.skipped, cls: 'bg-sky-500' },
  ];
  return (
    <div>
      <div className="flex h-2.5 rounded-full overflow-hidden bg-surface-hover">
        {segs.map((s, i) => (
          s.v > 0 ? <div key={i} className={s.cls} style={{ width: `${(s.v / total) * 100}%` }} /> : null
        ))}
      </div>
      <div className="text-[11px] text-text-muted mt-1">
        {progress.total} tests · <span className="text-emerald-600 font-semibold">{progress.pass} PASS</span> ·{' '}
        <span className="text-rose-500 font-semibold">{progress.fail} FAIL</span> ·{' '}
        <span className="text-amber-600 font-semibold">{progress.blocked} BLOCKED</span> · {progress.not_run} NOT RUN
      </div>
    </div>
  );
};

export const BugUxBadge: React.FC<{ ux: string }> = ({ ux }) => (
  <Badge variant={statusVariant(ux)}>{ux}</Badge>
);

const evidenceIcon = (t: string) => {
  if (t === 'screenshot') return <ImageIcon className="w-3.5 h-3.5" />;
  if (t === 'url') return <LinkIcon className="w-3.5 h-3.5" />;
  if (t === 'log' || t === 'console_error') return <Terminal className="w-3.5 h-3.5" />;
  if (t === 'db_result') return <Database className="w-3.5 h-3.5" />;
  if (t === 'api_request' || t === 'api_response') return <Globe className="w-3.5 h-3.5" />;
  return <FileText className="w-3.5 h-3.5" />;
};

const isImage = (e: TestEvidence) =>
  e.evidence_type === 'screenshot' ||
  (e.mime_type || '').startsWith('image/') ||
  /\.(png|jpe?g|gif|webp|bmp)$/i.test(e.file_path || '');

/** Reusable evidence viewer: inline preview for images/text, download-free basic view. */
export const EvidenceViewer: React.FC<{ items: TestEvidence[] }> = ({ items }) => {
  const [preview, setPreview] = useState<TestEvidence | null>(null);
  if (!items || items.length === 0) {
    return <p className="text-xs text-text-muted">Chưa có evidence. Hãy đính kèm trước khi tạo Bug.</p>;
  }
  return (
    <div className="space-y-1.5">
      {items.map((e) => (
        <button
          key={e.id}
          onClick={() => setPreview(e)}
          className="w-full flex items-center gap-2 text-left text-xs border border-border-subtle rounded-lg px-2.5 py-1.5 hover:bg-surface-hover"
        >
          <span className="text-primary">{evidenceIcon(e.evidence_type)}</span>
          <span className="font-mono text-[10px] text-text-muted uppercase">{e.evidence_type}</span>
          <span className="text-text-primary truncate flex-1">{e.title || '(no title)'}</span>
          {e.file_path && <span className="text-[10px] text-text-muted">file</span>}
        </button>
      ))}
      <Modal isOpen={!!preview} onClose={() => setPreview(null)} title={preview?.title || 'Evidence'} size="2xl">
        {preview && (
          <div className="space-y-2">
            <div className="flex gap-2 text-xs text-text-muted">
              <span className="font-mono uppercase">{preview.evidence_type}</span>
              {preview.created_by && <span>by {preview.created_by}</span>}
            </div>
            {isImage(preview) && preview.file_path && (
              <img src={apiClient.qaEvidenceFileUrl(preview.id)} alt={preview.title}
                className="max-w-full rounded-lg border border-border-subtle" />
            )}
            {preview.text_content && (
              <pre className="text-xs bg-surface-subtle border border-border-subtle rounded-lg p-3 whitespace-pre-wrap max-h-96 overflow-y-auto">
                {preview.text_content}
              </pre>
            )}
            {preview.file_path && !isImage(preview) && (
              <a className="text-xs text-primary hover:underline" href={apiClient.qaEvidenceFileUrl(preview.id)} target="_blank" rel="noreferrer">
                Mở file đính kèm →
              </a>
            )}
            {preview.evidence_type === 'url' && preview.text_content && (
              <a className="text-xs text-primary hover:underline break-all" href={preview.text_content} target="_blank" rel="noreferrer">
                {preview.text_content}
              </a>
            )}
          </div>
        )}
      </Modal>
    </div>
  );
};

export const ReportPreview: React.FC<{ vi: string; ja: string }> = ({ vi, ja }) => {
  const [tab, setTab] = useState<'vi' | 'ja'>('vi');
  const [copied, setCopied] = useState(false);
  const text = tab === 'vi' ? vi : ja;
  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2">
        <div className="flex rounded-lg border border-border-subtle overflow-hidden text-xs">
          <button onClick={() => setTab('vi')} className={`px-3 py-1 ${tab === 'vi' ? 'bg-primary/10 text-primary font-semibold' : 'text-text-secondary'}`}>Tiếng Việt</button>
          <button onClick={() => setTab('ja')} className={`px-3 py-1 ${tab === 'ja' ? 'bg-primary/10 text-primary font-semibold' : 'text-text-secondary'}`}>日本語</button>
        </div>
        <Button size="sm" variant="subtle" onClick={() => {
          navigator.clipboard.writeText(text).then(() => {
            setCopied(true);
            setTimeout(() => setCopied(false), 1500);
          });
        }}>{copied ? 'Đã copy!' : 'Copy gửi PM/khách'}</Button>
      </div>
      <pre className="text-xs bg-surface-subtle border border-border-subtle rounded-lg p-3 whitespace-pre-wrap max-h-96 overflow-y-auto">{text}</pre>
    </div>
  );
};
