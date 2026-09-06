import React, { useState, useEffect } from 'react';
import { Sparkles, Cpu, Bot } from 'lucide-react';
import { Skeleton } from './Skeleton';

interface AiThinkingLoaderProps {
  title?: string;
  mode?: 'translate' | 'analyze' | 'rag';
  className?: string;
}

const DEFAULT_MESSAGES = {
  translate: [
    'Đang nạp ngữ cảnh dự án & lọc thuật ngữ Glossary...',
    'Đối soát Translation Memory & kiểm tra sắc thái văn phong...',
    'Mô hình AI đang suy luận bản dịch & bảo vệ công thức...',
    'Đang trau chuốt bản dịch tự nhiên & kiểm định chất lượng (QA)...'
  ],
  analyze: [
    'Đang phân tích hội thoại & phát hiện câu hỏi/yêu cầu...',
    'Trích xuất Requirement, Bug, Decision & TODOs...',
    'Đối chiếu xung đột yêu cầu & chuẩn hóa Deadline tuyệt đối...',
    'Tổng hợp dữ liệu trí tuệ BrSE hoàn tất...'
  ],
  rag: [
    'Truy vấn Project Brain & tìm kiếm bằng chứng xác thực...',
    'Phân tích ngữ nghĩa từ các quyết định đã xác nhận...',
    'Kiểm tra Known Unknowns & tổng hợp câu trả lời...'
  ]
};

export const AiThinkingLoader: React.FC<AiThinkingLoaderProps> = ({
  title,
  mode = 'translate',
  className = ''
}) => {
  const messages = DEFAULT_MESSAGES[mode] || DEFAULT_MESSAGES.translate;
  const [msgIndex, setMsgIndex] = useState(0);

  useEffect(() => {
    const interval = setInterval(() => {
      setMsgIndex((prev) => (prev + 1) % messages.length);
    }, 2400);
    return () => clearInterval(interval);
  }, [messages.length]);

  return (
    <div
      className={`ai-glow-card rounded-xl p-5 bg-slate-900/90 border border-sky-500/40 backdrop-blur-xl relative overflow-hidden space-y-4 shadow-xl shadow-sky-950/30 ${className}`}
    >
      {/* Ambient background light sweep */}
      <div className="absolute inset-0 pointer-events-none opacity-20 bg-gradient-to-r from-transparent via-sky-500/20 to-indigo-500/20 animate-pulse" />

      {/* Header with animated neon badge & pulsing status */}
      <div className="flex items-center justify-between border-b border-slate-800/80 pb-3">
        <div className="flex items-center gap-2.5">
          <div className="relative flex items-center justify-center w-8 h-8 rounded-lg bg-gradient-to-tr from-sky-500/20 to-indigo-500/30 border border-sky-400/40 text-sky-400 shadow-md shadow-sky-500/20">
            <Sparkles className="w-4 h-4 animate-spin [animation-duration:4s]" />
            <span className="absolute -top-1 -right-1 flex h-2.5 w-2.5">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-sky-400 opacity-75" />
              <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-sky-500" />
            </span>
          </div>
          <div>
            <div className="text-xs font-bold uppercase tracking-wider text-transparent bg-clip-text bg-gradient-to-r from-sky-400 via-indigo-300 to-emerald-400 flex items-center gap-1.5">
              {title || (mode === 'translate' ? 'AI Translation Reasoning' : 'BrSE Intelligence Engine')}
            </div>
            <p className="text-[11px] text-slate-400 font-mono transition-opacity duration-300">
              {messages[msgIndex]}
            </p>
          </div>
        </div>

        <div className="hidden sm:flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-slate-800/80 border border-slate-700/60 text-[10px] text-slate-300 font-mono">
          <Cpu className="w-3 h-3 text-sky-400 animate-pulse" />
          <span>Neural Engine Active</span>
        </div>
      </div>

      {/* Shimmering Skeleton Lines */}
      <div className="space-y-2.5 pt-1">
        <Skeleton className="h-4 w-[92%]" />
        <Skeleton className="h-4 w-[78%]" />
        <Skeleton className="h-4 w-[85%]" />
        <div className="pt-2 flex items-center gap-2">
          <Skeleton className="h-6 w-24 rounded-full" />
          <Skeleton className="h-6 w-32 rounded-full" />
        </div>
      </div>
    </div>
  );
};
