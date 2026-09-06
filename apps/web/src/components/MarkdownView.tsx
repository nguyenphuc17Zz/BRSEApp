import React from 'react';

interface MarkdownViewProps {
  content: string;
  className?: string;
  accent?: 'emerald' | 'sky' | 'indigo';
}

/**
 * Parses inline Markdown tokens: **bold**, *italic*, `inline code`
 */
const renderInline = (text: string, accent: 'emerald' | 'sky' | 'indigo'): React.ReactNode => {
  const parts = text.split(/(\*\*.*?\*\*|\*.*?\*|`.*?`)/g);
  return parts.map((part, i) => {
    if (part.startsWith('**') && part.endsWith('**') && part.length >= 4) {
      const boldText = part.slice(2, -2);
      return (
        <strong
          key={i}
          className={`font-semibold text-slate-100 ${
            accent === 'emerald'
              ? 'bg-emerald-950/40 text-emerald-200/90 border border-emerald-800/30'
              : accent === 'sky'
              ? 'bg-sky-950/40 text-sky-200/90 border border-sky-800/30'
              : 'bg-slate-800/50 text-slate-100'
          } px-1.5 py-0.5 rounded text-[11.5px]`}
        >
          {boldText}
        </strong>
      );
    }
    if (part.startsWith('*') && part.endsWith('*') && part.length >= 2) {
      return (
        <em key={i} className="italic text-slate-300">
          {part.slice(1, -1)}
        </em>
      );
    }
    if (part.startsWith('`') && part.endsWith('`') && part.length >= 2) {
      return (
        <code
          key={i}
          className="px-1.5 py-0.5 rounded bg-slate-800 border border-slate-700 text-emerald-300 font-mono text-[11px]"
        >
          {part.slice(1, -1)}
        </code>
      );
    }
    return part;
  });
};

interface Block {
  type: 'h1' | 'h2' | 'h3' | 'h4' | 'bullet' | 'ordered' | 'quote' | 'hr' | 'paragraph';
  text?: string;
  items?: string[];
  orderNumber?: number;
}

export const MarkdownView: React.FC<MarkdownViewProps> = ({
  content,
  className = '',
  accent = 'emerald'
}) => {
  if (!content || !content.trim()) {
    return <div className="text-slate-500 italic text-xs">Chưa có nội dung tóm tắt.</div>;
  }

  // Parse markdown lines into structured blocks
  const lines = content.split('\n');
  const blocks: Block[] = [];
  let currentBulletGroup: string[] = [];
  let currentOrderedGroup: string[] = [];

  const flushLists = () => {
    if (currentBulletGroup.length > 0) {
      blocks.push({ type: 'bullet', items: [...currentBulletGroup] });
      currentBulletGroup = [];
    }
    if (currentOrderedGroup.length > 0) {
      blocks.push({ type: 'ordered', items: [...currentOrderedGroup] });
      currentOrderedGroup = [];
    }
  };

  for (let i = 0; i < lines.length; i++) {
    const rawLine = lines[i];
    const line = rawLine.trim();

    if (!line) {
      flushLists();
      continue;
    }

    // Horizontal Rule
    if (/^(?:---|\*\*\*|___)$/.test(line)) {
      flushLists();
      blocks.push({ type: 'hr' });
      continue;
    }

    // Headings
    if (line.startsWith('#### ')) {
      flushLists();
      blocks.push({ type: 'h4', text: line.replace(/^####\s+/, '') });
      continue;
    }
    if (line.startsWith('### ')) {
      flushLists();
      blocks.push({ type: 'h3', text: line.replace(/^###\s+/, '') });
      continue;
    }
    if (line.startsWith('## ')) {
      flushLists();
      blocks.push({ type: 'h2', text: line.replace(/^##\s+/, '') });
      continue;
    }
    if (line.startsWith('# ')) {
      flushLists();
      blocks.push({ type: 'h1', text: line.replace(/^#\s+/, '') });
      continue;
    }

    // Blockquote
    if (line.startsWith('>')) {
      flushLists();
      blocks.push({ type: 'quote', text: line.replace(/^>\s*/, '') });
      continue;
    }

    // Bullet list item (- or *)
    const bulletMatch = line.match(/^[-*]\s+(.*)$/);
    if (bulletMatch) {
      if (currentOrderedGroup.length > 0) flushLists();
      currentBulletGroup.push(bulletMatch[1]);
      continue;
    }

    // Ordered list item (e.g. 1. )
    const orderedMatch = line.match(/^(\d+)\.\s+(.*)$/);
    if (orderedMatch) {
      if (currentBulletGroup.length > 0) flushLists();
      currentOrderedGroup.push(orderedMatch[2]);
      continue;
    }

    // Regular paragraph or continuation
    flushLists();
    blocks.push({ type: 'paragraph', text: line });
  }

  flushLists();

  const bulletDotColor =
    accent === 'emerald'
      ? 'bg-emerald-400 shadow-[0_0_6px_rgba(52,211,153,0.4)]'
      : accent === 'sky'
      ? 'bg-sky-400 shadow-[0_0_6px_rgba(56,189,248,0.4)]'
      : 'bg-indigo-400 shadow-[0_0_6px_rgba(129,140,248,0.4)]';

  const headingBorderColor =
    accent === 'emerald' ? 'border-emerald-500/30' : accent === 'sky' ? 'border-sky-500/30' : 'border-slate-800';

  return (
    <div className={`space-y-2 text-xs leading-relaxed text-slate-200 font-sans ${className}`}>
      {blocks.map((block, idx) => {
        switch (block.type) {
          case 'h1':
            return (
              <h1
                key={idx}
                className="text-sm font-bold text-slate-100 mt-3.5 mb-1.5 pb-1 border-b border-slate-800 flex items-center gap-2"
              >
                <span className={`w-1.5 h-4 rounded-full ${accent === 'emerald' ? 'bg-emerald-500' : 'bg-sky-500'}`} />
                {renderInline(block.text || '', accent)}
              </h1>
            );
          case 'h2':
            return (
              <h2
                key={idx}
                className={`text-xs font-bold text-slate-100 mt-3 mb-1 pb-1 border-b ${headingBorderColor} flex items-center gap-1.5`}
              >
                <span className={`w-1 h-3 rounded-full ${accent === 'emerald' ? 'bg-emerald-400' : 'bg-sky-400'}`} />
                {renderInline(block.text || '', accent)}
              </h2>
            );
          case 'h3':
            return (
              <h3
                key={idx}
                className={`text-xs font-semibold ${
                  accent === 'emerald' ? 'text-emerald-300' : accent === 'sky' ? 'text-sky-300' : 'text-indigo-300'
                } mt-2.5 mb-1 flex items-center gap-1.5`}
              >
                <span className={`w-1.5 h-1.5 rounded-sm rotate-45 ${accent === 'emerald' ? 'bg-emerald-400' : 'bg-sky-400'}`} />
                {renderInline(block.text || '', accent)}
              </h3>
            );
          case 'h4':
            return (
              <h4 key={idx} className="text-[11.5px] font-semibold text-slate-300 mt-2 mb-0.5">
                {renderInline(block.text || '', accent)}
              </h4>
            );
          case 'bullet':
            return (
              <ul key={idx} className="space-y-1.5 my-1 pl-1">
                {block.items?.map((item, itemIdx) => (
                  <li key={itemIdx} className="flex items-start gap-2 text-slate-200">
                    <span className={`w-1.5 h-1.5 rounded-full ${bulletDotColor} mt-1.5 shrink-0`} />
                    <span className="flex-1 leading-relaxed text-xs">{renderInline(item, accent)}</span>
                  </li>
                ))}
              </ul>
            );
          case 'ordered':
            return (
              <ol key={idx} className="space-y-1.5 my-1 pl-1">
                {block.items?.map((item, itemIdx) => (
                  <li key={itemIdx} className="flex items-start gap-2 text-slate-200">
                    <span
                      className={`text-[10px] font-bold font-mono ${
                        accent === 'emerald' ? 'text-emerald-400' : 'text-sky-400'
                      } mt-0.5 w-4 shrink-0 text-right`}
                    >
                      {itemIdx + 1}.
                    </span>
                    <span className="flex-1 leading-relaxed text-xs">{renderInline(item, accent)}</span>
                  </li>
                ))}
              </ol>
            );
          case 'quote':
            return (
              <div
                key={idx}
                className={`border-l-2 ${
                  accent === 'emerald' ? 'border-emerald-500/70 bg-emerald-950/20' : 'border-sky-500/70 bg-sky-950/20'
                } pl-3 py-1.5 my-2 rounded-r text-slate-300 italic text-[11.5px] leading-relaxed`}
              >
                {renderInline(block.text || '', accent)}
              </div>
            );
          case 'hr':
            return <hr key={idx} className="border-slate-800/80 my-2.5" />;
          case 'paragraph':
          default:
            return (
              <p key={idx} className="text-slate-200 leading-relaxed my-1">
                {renderInline(block.text || '', accent)}
              </p>
            );
        }
      })}
    </div>
  );
};
export default MarkdownView;
