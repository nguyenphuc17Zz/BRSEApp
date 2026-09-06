import React, { useState, useEffect, useRef } from 'react';
import { 
  Users, 
  Sparkles, 
  Calendar, 
  Clock, 
  CheckSquare, 
  HelpCircle, 
  FileText, 
  Check, 
  Copy, 
  RefreshCw,
  ShieldCheck,
  AlertCircle,
  History,
  Bot,
  Zap,
  Tag,
  ArrowRight,
  Upload,
  FileUp,
  X,
  Paperclip,
  Trash2,
  ArrowUp,
  ArrowDown,
  ArrowUpDown,
  Mail,
  Download,
  Search,
  Languages,
  ExternalLink,
  Globe,
  GripVertical,
  Code,
  Eye,
  Send,
  MessageSquare,
  RotateCcw
} from 'lucide-react';

import { apiClient } from '../api/client';
import { Project, MeetingItemRecord, ProviderInfo } from '../types';
import { useToast } from '../context/ToastContext';
import { useConfirm } from '../context/ConfirmDialogContext';
import { ProviderModelSelector } from '../components/ProviderModelSelector';
import { MarkdownView } from '../components/MarkdownView';
import { resolveHealthyModel } from '../utils/aiPreferences';


export function cleanSubtitleOrText(content: string, filename: string): string {
  const ext = filename.split('.').pop()?.toLowerCase() || '';
  if (ext === 'txt') {
    return content.trim();
  }

  // Cleaning .vtt and .srt subtitle files
  const lines = content.split(/\r?\n/);
  const cleaned: string[] = [];

  for (let line of lines) {
    line = line.trim();
    if (!line) continue;
    // Skip WEBVTT header & metadata
    if (
      line.startsWith('WEBVTT') || 
      line.startsWith('NOTE') || 
      line.startsWith('Kind:') || 
      line.startsWith('Language:')
    ) {
      continue;
    }
    // Skip numeric sequence IDs (SRT index counters)
    if (/^\d+$/.test(line)) {
      continue;
    }
    // Skip timestamp lines (e.g. 00:00:01.000 --> 00:00:04.000 or 00:01:23,456 --> 00:01:25,789)
    if (line.includes('-->')) {
      continue;
    }
    // Remove inline formatting tags like <v Tanaka>, <c.color>, etc.
    const cleanedLine = line.replace(/<[^>]+>/g, '').trim();
    if (cleanedLine) {
      cleaned.push(cleanedLine);
    }
  }

  return cleaned.join('\n');
}

export interface DetectedDateInfo {
  dateStr: string | null;
  timestamp: number;
  displayLabel: string;
  source: 'filename' | 'content' | 'sequence' | 'none';
}

const MONTH_NAMES_MAP: Record<string, number> = {
  jan: 1, january: 1,
  feb: 2, february: 2,
  mar: 3, march: 3,
  apr: 4, april: 4,
  may: 5,
  jun: 6, june: 6,
  jul: 7, july: 7,
  aug: 8, august: 8,
  sep: 9, september: 9, sept: 9,
  oct: 10, october: 10,
  nov: 11, november: 11,
  dec: 12, december: 12
};

function parseValidDateTuple(y: number, m: number, d: number): { dateStr: string; timestamp: number } | null {
  if (y >= 1990 && y <= 2100 && m >= 1 && m <= 12 && d >= 1 && d <= 31) {
    const dt = new Date(y, m - 1, d);
    if (dt.getFullYear() === y && dt.getMonth() === m - 1 && dt.getDate() === d) {
      const mStr = String(m).padStart(2, '0');
      const dStr = String(d).padStart(2, '0');
      const dateStr = `${y}-${mStr}-${dStr}`;
      const timestamp = dt.getTime();
      return { dateStr, timestamp };
    }
  }
  return null;
}

export function parseDateFromAnyString(str: string, fallbackYear?: number): { dateStr: string; timestamp: number; displayLabel: string } | null {
  if (!str) return null;
  const targetYear = fallbackYear && fallbackYear >= 2000 && fallbackYear <= 2100 ? fallbackYear : new Date().getFullYear();

  // 1. Japanese Reiwa era: 令和X年M月D日 or R6.8.15 or R06-08-15
  const reiwaMatch = str.match(/(?:令和|R)\s*(\d{1,2})[-_./年\s]+(\d{1,2})[-_./月\s]+(\d{1,2})日?/i);
  if (reiwaMatch) {
    const rYear = parseInt(reiwaMatch[1], 10);
    const m = parseInt(reiwaMatch[2], 10);
    const d = parseInt(reiwaMatch[3], 10);
    const y = 2018 + rYear; // Reiwa 1 = 2019
    const valid = parseValidDateTuple(y, m, d);
    if (valid) return { ...valid, displayLabel: `${valid.dateStr} (R${rYear})` };
  }

  // 2. Japanese Heisei era: 平成X年M月D日 or H30.8.15
  const heiseiMatch = str.match(/(?:平成|H)\s*(\d{1,2})[-_./年\s]+(\d{1,2})[-_./月\s]+(\d{1,2})日?/i);
  if (heiseiMatch) {
    const hYear = parseInt(heiseiMatch[1], 10);
    const m = parseInt(heiseiMatch[2], 10);
    const d = parseInt(heiseiMatch[3], 10);
    const y = 1988 + hYear; // Heisei 1 = 1989
    const valid = parseValidDateTuple(y, m, d);
    if (valid) return { ...valid, displayLabel: `${valid.dateStr} (H${hYear})` };
  }

  // 3. Vietnamese text: "Ngày DD tháng MM năm YYYY" or "Ngày DD/MM/YYYY"
  const vnTextMatch = str.match(/ngày\s*(\d{1,2})(?:\s*tháng\s*|\s*[-_./]\s*)(\d{1,2})(?:\s*năm\s*|\s*[-_./]\s*)(\d{4})/i);
  if (vnTextMatch) {
    const d = parseInt(vnTextMatch[1], 10);
    const m = parseInt(vnTextMatch[2], 10);
    const y = parseInt(vnTextMatch[3], 10);
    const valid = parseValidDateTuple(y, m, d);
    if (valid) return { ...valid, displayLabel: valid.dateStr };
  }

  // 4. Japanese standard: YYYY年M月D日 with optional weekday (月/火/水/木/金/土/日)
  const jaMatch = str.match(/(\d{4})年\s*(\d{1,2})月\s*(\d{1,2})日(?:\s*\([月火水木金土日]\))?/);
  if (jaMatch) {
    const y = parseInt(jaMatch[1], 10);
    const m = parseInt(jaMatch[2], 10);
    const d = parseInt(jaMatch[3], 10);
    const valid = parseValidDateTuple(y, m, d);
    if (valid) return { ...valid, displayLabel: valid.dateStr };
  }

  // 5. English Month Name formats: "Aug 15, 2026", "15 August 2026", "2026-Aug-15", "August 15th 2026"
  const enMonthMatch1 = str.match(/([A-Za-z]{3,9})\s+(\d{1,2})(?:st|nd|rd|th)?,\s*(\d{4})/i);
  if (enMonthMatch1) {
    const mKey = enMonthMatch1[1].toLowerCase();
    if (MONTH_NAMES_MAP[mKey]) {
      const m = MONTH_NAMES_MAP[mKey];
      const d = parseInt(enMonthMatch1[2], 10);
      const y = parseInt(enMonthMatch1[3], 10);
      const valid = parseValidDateTuple(y, m, d);
      if (valid) return { ...valid, displayLabel: valid.dateStr };
    }
  }

  const enMonthMatch2 = str.match(/(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]{3,9})\s+(\d{4})/i);
  if (enMonthMatch2) {
    const mKey = enMonthMatch2[2].toLowerCase();
    if (MONTH_NAMES_MAP[mKey]) {
      const d = parseInt(enMonthMatch2[1], 10);
      const m = MONTH_NAMES_MAP[mKey];
      const y = parseInt(enMonthMatch2[3], 10);
      const valid = parseValidDateTuple(y, m, d);
      if (valid) return { ...valid, displayLabel: valid.dateStr };
    }
  }

  const enMonthMatch3 = str.match(/(\d{4})[-_.]([A-Za-z]{3,9})[-_.](\d{1,2})/i);
  if (enMonthMatch3) {
    const mKey = enMonthMatch3[2].toLowerCase();
    if (MONTH_NAMES_MAP[mKey]) {
      const y = parseInt(enMonthMatch3[1], 10);
      const m = MONTH_NAMES_MAP[mKey];
      const d = parseInt(enMonthMatch3[3], 10);
      const valid = parseValidDateTuple(y, m, d);
      if (valid) return { ...valid, displayLabel: valid.dateStr };
    }
  }

  // 6. ISO Delimited: YYYY-MM-DD, YYYY/MM/DD, YYYY.MM.DD, YYYY_MM_DD
  const isoMatch = str.match(/(?:^|[^0-9])(\d{4})[-_. /](\d{1,2})[-_. /](\d{1,2})(?:\s*\([A-Za-z月火水木金土日]+\))?(?:$|[^0-9])/);
  if (isoMatch) {
    const y = parseInt(isoMatch[1], 10);
    const m = parseInt(isoMatch[2], 10);
    const d = parseInt(isoMatch[3], 10);
    const valid = parseValidDateTuple(y, m, d);
    if (valid) return { ...valid, displayLabel: valid.dateStr };
  }

  // 7. Compact 8-digit: 20260815
  const compactMatch = str.match(/(?:^|[^0-9])(20\d{2})(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])(?:$|[^0-9])/);
  if (compactMatch) {
    const y = parseInt(compactMatch[1], 10);
    const m = parseInt(compactMatch[2], 10);
    const d = parseInt(compactMatch[3], 10);
    const valid = parseValidDateTuple(y, m, d);
    if (valid) return { ...valid, displayLabel: valid.dateStr };
  }

  // 8. European/Vietnamese DD-MM-YYYY or DD/MM/YYYY or DD_MM_YYYY
  const euroMatch = str.match(/(?:^|[^0-9])(\d{1,2})[-_. /](\d{1,2})[-_. /](\d{4})(?:$|[^0-9])/);
  if (euroMatch) {
    const d = parseInt(euroMatch[1], 10);
    const m = parseInt(euroMatch[2], 10);
    const y = parseInt(euroMatch[3], 10);
    const valid = parseValidDateTuple(y, m, d);
    if (valid) return { ...valid, displayLabel: valid.dateStr };
  }

  // 9. Japanese M月D日 (year omitted -> default to targetYear)
  const jaShortMatch = str.match(/(\d{1,2})月\s*(\d{1,2})日(?:\s*\([月火水木金土日]\))?/);
  if (jaShortMatch) {
    const m = parseInt(jaShortMatch[1], 10);
    const d = parseInt(jaShortMatch[2], 10);
    const valid = parseValidDateTuple(targetYear, m, d);
    if (valid) return { ...valid, displayLabel: `${valid.dateStr} (${m}月${d}日)` };
  }

  // 10. 3-segment with 2-digit year: YY-MM-DD or DD-MM-YY (e.g., 26_07_15 or 15_07_26)
  const short3Match = str.match(/(?:^|[^0-9])(\d{2})[-_. /](\d{1,2})[-_. /](\d{1,2})(?:$|[^0-9])/);
  if (short3Match) {
    const p1 = parseInt(short3Match[1], 10);
    const p2 = parseInt(short3Match[2], 10);
    const p3 = parseInt(short3Match[3], 10);
    if (p1 >= 20 && p1 <= 35 && p2 >= 1 && p2 <= 12 && p3 >= 1 && p3 <= 31) {
      const valid = parseValidDateTuple(2000 + p1, p2, p3);
      if (valid) return { ...valid, displayLabel: valid.dateStr };
    }
    if (p3 >= 20 && p3 <= 35 && p2 >= 1 && p2 <= 12 && p1 >= 1 && p1 <= 31) {
      const valid = parseValidDateTuple(2000 + p3, p2, p1);
      if (valid) return { ...valid, displayLabel: valid.dateStr };
    }
  }

  // 11. Short 2-segment date with delimiter: DD_MM, D_M, DD-MM, DD/MM, DD.MM (e.g. 06_08, 25_6, 16_7, 30_7, 20_8)
  const short2Match = str.match(/(?:^|[^0-9])([0-3]?\d)[-_. /]([01]?\d)(?:$|[^0-9])/);
  if (short2Match) {
    const num1 = parseInt(short2Match[1], 10);
    const num2 = parseInt(short2Match[2], 10);

    let d: number | null = null;
    let m: number | null = null;

    if (num1 > 12 && num1 <= 31 && num2 >= 1 && num2 <= 12) {
      d = num1;
      m = num2;
    } else if (num2 > 12 && num2 <= 31 && num1 >= 1 && num1 <= 12) {
      d = num2;
      m = num1;
    } else if (num1 >= 1 && num1 <= 31 && num2 >= 1 && num2 <= 12) {
      // User decision: Day first, Month second
      d = num1;
      m = num2;
    }

    if (d && m) {
      const valid = parseValidDateTuple(targetYear, m, d);
      if (valid) {
        const dFmt = String(d).padStart(2, '0');
        const mFmt = String(m).padStart(2, '0');
        return { ...valid, displayLabel: `${valid.dateStr} (${dFmt}/${mFmt})` };
      }
    }
  }

  // 12. Compact 4-digit date without year: DDMM (e.g. meetingkhack0207 -> 0207, meetingkhach1007 -> 1007)
  const compact4Match = str.match(/(?:^|[^0-9])(0[1-9]|[12]\d|3[01])(0[1-9]|1[0-2])(?:$|[^0-9])/);
  if (compact4Match) {
    const d = parseInt(compact4Match[1], 10);
    const m = parseInt(compact4Match[2], 10);
    const raw4 = parseInt(compact4Match[1] + compact4Match[2], 10);
    if (raw4 < 2020 || raw4 > 2035) {
      const valid = parseValidDateTuple(targetYear, m, d);
      if (valid) {
        const dFmt = String(d).padStart(2, '0');
        const mFmt = String(m).padStart(2, '0');
        return { ...valid, displayLabel: `${valid.dateStr} (${dFmt}/${mFmt})` };
      }
    }
  }

  return null;
}

export function extractDateFromFilenameOrContent(
  filename: string, 
  content: string, 
  fallbackYear?: number
): DetectedDateInfo {
  // 1. Sanitize filename:
  // Strip file extension (.txt, .srt, .vtt)
  let cleanName = filename.replace(/\.(txt|vtt|srt)$/i, '');
  // Strip noise suffixes added by transcription software:
  // e.g. " (transcribed by Teams on 2026-09-01...)" or " (transcribed on...)" or " (transcript)"
  cleanName = cleanName.replace(/\s*\((?:transcribed|transcript|recorded|record|ghi âm|bản dịch).*?\)/gi, '');
  cleanName = cleanName.trim();

  // 2. Check filename first (highest priority)
  const fnResult = parseDateFromAnyString(cleanName, fallbackYear);
  if (fnResult) {
    return {
      dateStr: fnResult.dateStr,
      timestamp: fnResult.timestamp,
      displayLabel: fnResult.displayLabel,
      source: 'filename'
    };
  }

  // Also check original filename if cleanName didn't match (in case date was right at the end)
  if (cleanName !== filename) {
    const rawFnResult = parseDateFromAnyString(filename, fallbackYear);
    if (rawFnResult) {
      return {
        dateStr: rawFnResult.dateStr,
        timestamp: rawFnResult.timestamp,
        displayLabel: rawFnResult.displayLabel,
        source: 'filename'
      };
    }
  }

  // 3. Check first 35 lines of content ONLY IF filename had no date
  const sampleLines = content.split(/\r?\n/).slice(0, 35);
  for (const line of sampleLines) {
    const trimmed = line.trim();
    if (!trimmed) continue;
    const contentResult = parseDateFromAnyString(trimmed, fallbackYear);
    if (contentResult) {
      return {
        dateStr: contentResult.dateStr,
        timestamp: contentResult.timestamp,
        displayLabel: contentResult.displayLabel,
        source: 'content'
      };
    }
  }

  // 4. Fallback: Sprint / Week / Buổi / Session numbers
  const combinedText = `${cleanName}\n${sampleLines.slice(0, 10).join('\n')}`;

  const sprintMatch = combinedText.match(/(?:sprint|sprint_)[-_\s]*(\d+)/i);
  if (sprintMatch) {
    const num = parseInt(sprintMatch[1], 10);
    const baseEpoch = new Date(fallbackYear || 2026, 0, 1).getTime() + (num * 14 * 86400000);
    return {
      dateStr: null,
      timestamp: baseEpoch,
      displayLabel: `Sprint ${num}`,
      source: 'sequence'
    };
  }

  const weekMatch = combinedText.match(/(?:week|tuần|tuan|w)[-_\s]*(\d+)/i);
  if (weekMatch) {
    const num = parseInt(weekMatch[1], 10);
    const baseEpoch = new Date(fallbackYear || 2026, 0, 1).getTime() + (num * 7 * 86400000);
    return {
      dateStr: null,
      timestamp: baseEpoch,
      displayLabel: `Tuần ${num}`,
      source: 'sequence'
    };
  }

  const sessionMatch = combinedText.match(/(?:buổi|buoi|session|part|phần|phan|p)[-_\s]*(\d+)/i);
  if (sessionMatch) {
    const num = parseInt(sessionMatch[1], 10);
    const baseEpoch = new Date(fallbackYear || 2026, 0, 1).getTime() + (num * 86400000);
    return {
      dateStr: null,
      timestamp: baseEpoch,
      displayLabel: `Buổi ${num}`,
      source: 'sequence'
    };
  }

  // 5. Unknown
  return {
    dateStr: null,
    timestamp: Number.MAX_SAFE_INTEGER,
    displayLabel: 'Chưa rõ ngày',
    source: 'none'
  };
}

export interface UploadedMeetingFile {
  id: string;
  name: string;
  size: number;
  content: string;
  detectedDate: string | null;
  displayLabel?: string;
  source?: 'filename' | 'content' | 'sequence' | 'none';
  timestamp: number;
}

export interface BrainChatMessage {
  id: string;
  role: 'user' | 'assistant';
  text: string;
  citations?: Array<{ meeting_id?: string; title?: string; meeting_date?: string; quote_or_reason?: string }>;
  evolution_notes?: string[];
  timestamp: number;
}

interface MeetingsPageProps {
  activeProject: Project | null;
  projects?: Project[];
  setActiveProject?: (p: Project | null) => void;
}


export const MeetingsPage: React.FC<MeetingsPageProps> = ({ 
  activeProject, 
  projects = [], 
  setActiveProject 
}) => {
  const toast = useToast();
  const confirm = useConfirm();
  const [allProjects, setAllProjects] = useState<Project[]>(projects);
  const [selectedProjectId, setSelectedProjectId] = useState<string>(activeProject?.id || '');

  const [providers, setProviders] = useState<ProviderInfo[]>([]);
  const [selectedProvider, setSelectedProvider] = useState<string>('auto');
  const [selectedModel, setSelectedModel] = useState<string>('');

  const [meetings, setMeetings] = useState<MeetingItemRecord[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [generating, setGenerating] = useState<boolean>(false);

  const [title, setTitle] = useState<string>('');
  const [meetingDate, setMeetingDate] = useState<string>(new Date().toISOString().split('T')[0]);
  const [transcript, setTranscript] = useState<string>('');

  const [currentResult, setCurrentResult] = useState<any | null>(null);
  const [copiedSummary, setCopiedSummary] = useState<boolean>(false);
  const [copiedAll, setCopiedAll] = useState<boolean>(false);

  // Executive Meeting Intelligence Suite State
  const [languageView, setLanguageView] = useState<'vi' | 'ja' | 'bilingual'>('vi');
  const [isRawSummaryMode, setIsRawSummaryMode] = useState<boolean>(false);
  const [showEmailModal, setShowEmailModal] = useState<boolean>(false);

  const [emailContent, setEmailContent] = useState<string>('');
  const [copiedEmail, setCopiedEmail] = useState<boolean>(false);
  const [brainQuery, setBrainQuery] = useState<string>('');
  const [askingBrain, setAskingBrain] = useState<boolean>(false);
  const [brainChatMessages, setBrainChatMessages] = useState<BrainChatMessage[]>([]);
  const [copiedBrainMsgId, setCopiedBrainMsgId] = useState<string | null>(null);
  const brainChatEndRef = useRef<HTMLDivElement | null>(null);
  const [historySearchQuery, setHistorySearchQuery] = useState<string>('');

  const [batchProgress, setBatchProgress] = useState<{
    current: number;
    total: number;
    currentFileName: string;
    percent: number;
  } | null>(null);
  const cancelBatchRef = useRef<boolean>(false);

  // Sync projects from props or fetch from API
  useEffect(() => {
    if (projects.length > 0) {
      setAllProjects(projects);
    } else {
      apiClient.getProjects().then((list) => {
        setAllProjects(list);
      }).catch(console.error);
    }
  }, [projects]);

  // Sync selected project with activeProject
  useEffect(() => {
    if (activeProject?.id) {
      setSelectedProjectId(activeProject.id);
    } else if (allProjects.length > 0 && !selectedProjectId) {
      setSelectedProjectId(allProjects[0].id);
    }
  }, [activeProject?.id, allProjects]);

  useEffect(() => {
    apiClient.getProviders().then((provs) => {
      setProviders(provs);
      const healthy = resolveHealthyModel(provs, 'auto', '');
      setSelectedProvider(healthy.provider);
      setSelectedModel(healthy.model);
    }).catch(console.error);
  }, []);

  const loadMeetings = async () => {
    try {
      setLoading(true);
      const res = await apiClient.listMeetings(activeProject?.id);
      setMeetings(res);
    } catch (e) {
      console.error("Failed loading meetings", e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadMeetings();
  }, [activeProject]);

  useEffect(() => {
    if (brainChatMessages.length > 0) {
      brainChatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [brainChatMessages, askingBrain]);


  const [uploadedFiles, setUploadedFiles] = useState<UploadedMeetingFile[]>([]);
  const [isDragging, setIsDragging] = useState<boolean>(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Drag-and-Drop Reordering & Sort Direction State
  const [draggedFileIndex, setDraggedFileIndex] = useState<number | null>(null);
  const [dragOverFileIndex, setDragOverFileIndex] = useState<number | null>(null);
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('asc'); // asc: Cũ -> Mới, desc: Mới -> Cũ

  const formatFileSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  const buildMergedTranscript = (files: UploadedMeetingFile[]): string => {
    if (files.length === 0) return '';
    if (files.length === 1) return files[0].content;
    return files.map((file, idx) => {
      const label = file.displayLabel || (file.detectedDate ? `Ngày: ${file.detectedDate}` : '');
      const labelSuffix = label ? ` (Thời gian/Tiến trình: ${label})` : '';
      return `=== [Phần ${idx + 1}/${files.length}: ${file.name}${labelSuffix}] ===\n${file.content}`;
    }).join('\n\n');
  };

  // Drag & Drop Handlers
  const handleFileDragStart = (e: React.DragEvent, index: number) => {
    e.stopPropagation();
    setDraggedFileIndex(index);
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('text/plain', String(index));
  };

  const handleFileDragOver = (e: React.DragEvent, index: number) => {
    e.preventDefault();
    e.stopPropagation();
    if (draggedFileIndex === null || draggedFileIndex === index) return;
    setDragOverFileIndex(index);
  };

  const handleFileDragLeave = (e: React.DragEvent) => {
    e.stopPropagation();
  };

  const handleFileDrop = (e: React.DragEvent, targetIndex: number) => {
    e.preventDefault();
    e.stopPropagation();
    if (draggedFileIndex === null || draggedFileIndex === targetIndex) {
      setDraggedFileIndex(null);
      setDragOverFileIndex(null);
      return;
    }

    const updated = [...uploadedFiles];
    const [movedItem] = updated.splice(draggedFileIndex, 1);
    updated.splice(targetIndex, 0, movedItem);

    setUploadedFiles(updated);
    setTranscript(buildMergedTranscript(updated));
    setDraggedFileIndex(null);
    setDragOverFileIndex(null);
    toast.info(`Đã đổi vị trí: "${movedItem.name}" sang vị trí số #${targetIndex + 1}.`);
  };

  const handleFileDragEnd = () => {
    setDraggedFileIndex(null);
    setDragOverFileIndex(null);
  };

  const handleRemoveFile = (index: number) => {
    const updated = uploadedFiles.filter((_, i) => i !== index);
    setUploadedFiles(updated);
    setTranscript(buildMergedTranscript(updated));
    toast.info("Đã xóa file khỏi danh sách gộp.");
  };

  const handleToggleSortDirection = () => {
    const nextOrder = sortOrder === 'asc' ? 'desc' : 'asc';
    setSortOrder(nextOrder);
    const sorted = [...uploadedFiles].sort((a, b) => {
      return nextOrder === 'asc' ? a.timestamp - b.timestamp : b.timestamp - a.timestamp;
    });
    setUploadedFiles(sorted);
    setTranscript(buildMergedTranscript(sorted));
    toast.success(`Đã đổi thứ tự: ${nextOrder === 'asc' ? 'Từ Cũ ➔ Mới' : 'Từ Mới ➔ Cũ'}!`);
  };

  const handleFiles = async (files: FileList | File[]) => {
    if (!files || files.length === 0) return;
    const validFiles = Array.from(files).filter(f => {
      const ext = f.name.split('.').pop()?.toLowerCase() || '';
      return ['txt', 'vtt', 'srt'].includes(ext);
    });

    if (validFiles.length === 0) {
      toast.warning('Chỉ hỗ trợ các file định dạng .txt, .vtt hoặc .srt!');
      return;
    }

    try {
      const fileReadPromises = validFiles.map(file => {
        return new Promise<{ name: string; size: number; content: string }>((resolve, reject) => {
          const reader = new FileReader();
          reader.onload = (e) => {
            const raw = (e.target?.result as string) || '';
            const cleaned = cleanSubtitleOrText(raw, file.name);
            resolve({ name: file.name, size: file.size, content: cleaned });
          };
          reader.onerror = reject;
          reader.readAsText(file, 'utf-8');
        });
      });

      const results = await Promise.all(fileReadPromises);

      const fallbackYear = meetingDate ? new Date(meetingDate).getFullYear() : new Date().getFullYear();
      const newFiles: UploadedMeetingFile[] = results.map(r => {
        const detected = extractDateFromFilenameOrContent(r.name, r.content, fallbackYear);
        return {
          id: Math.random().toString(36).substring(2, 9),
          name: r.name,
          size: r.size,
          content: r.content,
          detectedDate: detected.dateStr,
          displayLabel: detected.displayLabel,
          source: detected.source,
          timestamp: detected.timestamp
        };
      });

      // Auto sort according to selected sortOrder (default: ascending older -> newer)
      const sorted = [...newFiles].sort((a, b) => 
        sortOrder === 'asc' ? a.timestamp - b.timestamp : b.timestamp - a.timestamp
      );
      setUploadedFiles(sorted);
      setTranscript(buildMergedTranscript(sorted));

      // Auto-suggest meeting title from first file if current title is empty
      if (!title.trim() && sorted.length > 0) {
        const cleanName = sorted[0].name
          .replace(/\.[^/.]+$/, '')
          .replace(/\s*\((?:transcribed|transcript|recorded|record|ghi âm|bản dịch).*?\)/gi, '')
          .replace(/[_-]/g, ' ')
          .trim();
        setTitle(cleanName.charAt(0).toUpperCase() + cleanName.slice(1));
      }

      // If the latest file has a detected date, set meetingDate to it
      const latestDated = [...sorted].reverse().find(f => f.detectedDate);
      if (latestDated?.detectedDate) {
        setMeetingDate(latestDated.detectedDate);
      }

      const totalSizeKb = Math.round(results.reduce((acc, curr) => acc + curr.size, 0) / 1024);
      toast.success(`Đã nạp & tự động nhận diện ngày tháng cho ${sorted.length} file (${totalSizeKb} KB)!`);
    } catch (err) {
      console.error('Lỗi đọc file:', err);
      toast.error('Có lỗi xảy ra khi đọc file transcript.');
    }
  };

  const handleClearFiles = () => {
    setUploadedFiles([]);
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const handleDeleteMeeting = async (e: React.MouseEvent, meetingId: string, meetingTitle?: string) => {
    e.stopPropagation();
    const ok = await confirm({
      title: "Xóa bản ghi cuộc họp",
      message: `Bạn có chắc chắn muốn xóa cuộc họp "${meetingTitle || 'này'}"? Hành động này sẽ xóa vĩnh viễn biên bản và các việc cần làm liên quan khỏi hệ thống.`,
      confirmText: "Xóa cuộc họp",
      cancelText: "Hủy bỏ",
      isDestructive: true
    });
    if (!ok) return;

    try {
      await apiClient.deleteMeeting(meetingId);
      toast.success("Đã xóa cuộc họp thành công!");
      if (currentResult?.id === meetingId) {
        setCurrentResult(null);
      }
      await loadMeetings();
    } catch (err) {
      console.error("Failed to delete meeting", err);
      toast.error("Không thể xóa cuộc họp.");
    }
  };

  const handleClearAllMeetings = async () => {
    if (meetings.length === 0) return;
    const ok = await confirm({
      title: "Xác nhận xóa toàn bộ cuộc họp",
      message: `Bạn có chắc chắn muốn xóa sạch toàn bộ ${meetings.length} cuộc họp đã lưu trong lịch sử? Toàn bộ biên bản ghi chép và các việc cần làm liên quan sẽ bị xóa vĩnh viễn khỏi cơ sở dữ liệu.`,
      confirmText: `Xóa tất cả (${meetings.length})`,
      cancelText: "Hủy bỏ",
      isDestructive: true
    });
    if (!ok) return;

    try {
      await apiClient.clearAllMeetings();
      toast.success("Đã xóa toàn bộ lịch sử cuộc họp thành công!");
      setCurrentResult(null);
      await loadMeetings();
    } catch (err) {
      console.error("Failed to clear all meetings", err);
      toast.error("Không thể xóa tất cả cuộc họp.");
    }
  };

  const handleGenerateMinutes = async () => {
    if (!transcript.trim()) {
      toast.warning("Vui lòng nhập nội dung transcript cuộc họp!");
      return;
    }
    const targetProjectId = selectedProjectId || activeProject?.id || (allProjects[0]?.id ?? '');

    // Case 1: Batch Processing when multiple meeting files are uploaded
    if (uploadedFiles.length > 1) {
      cancelBatchRef.current = false;
      setGenerating(true);
      let successCount = 0;
      let lastResult: any = null;

      try {
        toast.info(`Bắt đầu phân tích hàng loạt ${uploadedFiles.length} cuộc họp độc lập qua ${selectedProvider}...`);
        for (let i = 0; i < uploadedFiles.length; i++) {
          if (cancelBatchRef.current) {
            toast.info(`Đã dừng tiến trình tại cuộc họp [${i}/${uploadedFiles.length}].`);
            break;
          }

          const file = uploadedFiles[i];
          const pct = Math.round((i / uploadedFiles.length) * 100);
          setBatchProgress({
            current: i + 1,
            total: uploadedFiles.length,
            currentFileName: file.name,
            percent: pct
          });

          // Clean title and resolve date
          const cleanTitle = file.name
            .replace(/\.[^/.]+$/, "")
            .replace(/\(transcribed on[^)]*\)/i, "")
            .trim();
          const fileDate = file.detectedDate || meetingDate;

          try {
            const res = await apiClient.analyzeMeeting({
              project_id: targetProjectId,
              title: cleanTitle,
              meeting_date: fileDate,
              transcript_text: file.content,
              preferred_provider: selectedProvider,
              model: selectedModel || undefined
            });
            successCount++;
            lastResult = res;
            setCurrentResult(res);
            await loadMeetings();
          } catch (fileErr: any) {
            console.error(`Error analyzing file ${file.name}:`, fileErr);
            toast.error(`Lỗi phân tích file "${file.name}": ${fileErr.message || 'Lỗi server'}`);
          }

          // Gentle pacing delay between Groq calls to avoid rate limit spikes
          if (i + 1 < uploadedFiles.length && !cancelBatchRef.current) {
            await new Promise((resolve) => setTimeout(resolve, 2000));
          }
        }

        if (!cancelBatchRef.current && successCount > 0) {
          toast.success(`Hoàn tất! Đã phân tích và lưu thành công ${successCount}/${uploadedFiles.length} cuộc họp vào Lịch sử!`);
          if (lastResult) setCurrentResult(lastResult);
        }
      } catch (err: any) {
        console.error("Batch meeting processing failed", err);
        toast.error(`Tiến trình xử lý hàng loạt gặp sự cố: ${err.message || 'Lỗi xử lý'}`);
      } finally {
        setGenerating(false);
        setBatchProgress(null);
      }
      return;
    }

    // Case 2: Single meeting transcript direct analysis
    try {
      setGenerating(true);
      const res = await apiClient.analyzeMeeting({
        project_id: targetProjectId,
        title,
        meeting_date: meetingDate,
        transcript_text: transcript,
        preferred_provider: selectedProvider,
        model: selectedModel || undefined
      });
      setCurrentResult(res);
      toast.success(`Đã trích xuất biên bản! ${res.action_items?.length || 0} việc cần làm đã đồng bộ sang BrSE Dashboard.`);
      await loadMeetings();
    } catch (e: any) {
      console.error("Meeting analysis failed", e);
      toast.error(`Phân tích biên bản thất bại: ${e.response?.data?.detail || e.message || 'Lỗi xử lý'}`);
    } finally {
      setGenerating(false);
    }
  };

  const getActiveSummaryText = (res: any): string => {
    if (!res) return '';
    if (languageView === 'ja') return res.summary_ja || res.summary_markdown || '';
    if (languageView === 'vi') return res.summary_vi || res.summary_markdown || '';
    // bilingual
    let bi = '';
    if (res.summary_ja) bi += `### 🇯🇵 日本語サマリー\n${res.summary_ja}\n\n`;
    if (res.summary_vi) bi += `### 🇻🇳 Tóm tắt Tiếng Việt\n${res.summary_vi}\n`;
    return bi || res.summary_markdown || '';
  };

  const copySummary = (text?: string) => {
    const toCopy = text || getActiveSummaryText(currentResult);
    navigator.clipboard.writeText(toCopy);
    setCopiedSummary(true);
    toast.success("Đã copy Tóm tắt điều hành vào clipboard!");
    setTimeout(() => setCopiedSummary(false), 2000);
  };

  const copyFullReport = () => {
    if (!currentResult) return;
    const mTitle = currentResult.title || title || 'Meeting Minutes';
    const mDate = currentResult.meeting_date || meetingDate;
    let full = `# ${mTitle} (${mDate})\n\n`;

    if (languageView === 'ja') {
      full += `## 1. エグゼクティブサマリー\n${currentResult.summary_ja || currentResult.summary_markdown}\n\n`;
      if (currentResult.decisions?.length > 0) {
        full += `## 2. 決定事項（Decisions）\n`;
        currentResult.decisions.forEach((d: any, idx: number) => {
          full += `${idx + 1}. **${d.title_ja || d.title || d.title_vi}**: ${d.detail_ja || d.detail || d.detail_vi || ''}\n`;
          if (d.evidence) full += `   > Evidence: "${d.evidence}"\n`;
        });
        full += `\n`;
      }
      if (currentResult.action_items?.length > 0) {
        full += `## 3. アクションアイテム（Action Items）\n`;
        currentResult.action_items.forEach((a: any) => {
          full += `- [ ] [${a.priority || '通常'}] **${a.task_ja || a.task || a.task_vi}** (担当: ${a.assignee || '未定'} | 期日: ${a.due_date || '未定'})\n`;
        });
        full += `\n`;
      }
      if (currentResult.open_questions?.length > 0) {
        full += `## 4. 保留・確認事項（Open Questions）\n`;
        currentResult.open_questions.forEach((q: any) => {
          full += `- [${q.urgency || '通常'}] ${q.question_ja || q.question || q.question_vi} (確認者: ${q.owner || 'Client'})\n`;
        });
      }
    } else if (languageView === 'vi') {
      full += `## 1. Tóm tắt điều hành (Executive Summary)\n${currentResult.summary_vi || currentResult.summary_markdown}\n\n`;
      if (currentResult.decisions?.length > 0) {
        full += `## 2. Quyết định đã chốt (Key Decisions)\n`;
        currentResult.decisions.forEach((d: any, idx: number) => {
          full += `${idx + 1}. **${d.title_vi || d.title || d.title_ja}**: ${d.detail_vi || d.detail || d.detail_ja || ''}\n`;
          if (d.evidence) full += `   > Bằng chứng: "${d.evidence}"\n`;
        });
        full += `\n`;
      }
      if (currentResult.action_items?.length > 0) {
        full += `## 3. Việc cần làm (Action Items & Assignments)\n`;
        currentResult.action_items.forEach((a: any) => {
          full += `- [ ] [${a.priority || 'NORMAL'}] **${a.task_vi || a.task || a.task_ja}** (Phụ trách: ${a.assignee || 'Unassigned'} | Hạn: ${a.due_date || 'Chưa xác định'})\n`;
        });
        full += `\n`;
      }
      if (currentResult.open_questions?.length > 0) {
        full += `## 4. Vấn đề tồn đọng & Cần xác nhận (Open Questions)\n`;
        currentResult.open_questions.forEach((q: any) => {
          full += `- [${q.urgency || 'NORMAL'}] ${q.question_vi || q.question || q.question_ja} (Bên xác nhận: ${q.owner || 'Client'})\n`;
        });
      }
    } else {
      // Bilingual
      full += `## 1. Executive Summary (Song ngữ JA/VI)\n`;
      if (currentResult.summary_ja) full += `### 🇯🇵 日本語サマリー\n${currentResult.summary_ja}\n\n`;
      if (currentResult.summary_vi) full += `### 🇻🇳 Tóm tắt Tiếng Việt\n${currentResult.summary_vi}\n\n`;
      if (!currentResult.summary_ja && !currentResult.summary_vi) full += `${currentResult.summary_markdown}\n\n`;

      if (currentResult.decisions?.length > 0) {
        full += `## 2. Quyết định đã chốt (Key Decisions)\n`;
        currentResult.decisions.forEach((d: any, idx: number) => {
          const viTitle = d.title_vi || d.title || d.title_ja || '';
          const jaTitle = d.title_ja ? ` / 【${d.title_ja}】` : '';
          full += `${idx + 1}. **${viTitle}${jaTitle}**\n`;
          if (d.detail_vi || d.detail) full += `   - 🇻🇳 ${d.detail_vi || d.detail}\n`;
          if (d.detail_ja) full += `   - 🇯🇵 ${d.detail_ja}\n`;
          if (d.evidence) full += `   > Evidence: "${d.evidence}"\n`;
        });
        full += `\n`;
      }

      if (currentResult.action_items?.length > 0) {
        full += `## 3. Việc cần làm (Action Items)\n`;
        currentResult.action_items.forEach((a: any) => {
          const viTask = a.task_vi || a.task || a.task_ja || '';
          const jaTask = a.task_ja ? `\n     ↳ 🇯🇵 ${a.task_ja}` : '';
          full += `- [ ] [${a.priority || 'NORMAL'}] **${viTask}**${jaTask} (Assignee: ${a.assignee || 'Unassigned'} | Due: ${a.due_date || 'TBD'})\n`;
        });
        full += `\n`;
      }

      if (currentResult.open_questions?.length > 0) {
        full += `## 4. Vấn đề tồn đọng (Open Questions)\n`;
        currentResult.open_questions.forEach((q: any) => {
          const viQ = q.question_vi || q.question || q.question_ja || '';
          const jaQ = q.question_ja ? `\n     ↳ 🇯🇵 ${q.question_ja}` : '';
          full += `- [${q.urgency || 'NORMAL'}] ${viQ}${jaQ} (Owner: ${q.owner || 'Client'})\n`;
        });
      }
    }

    navigator.clipboard.writeText(full);
    setCopiedAll(true);
    toast.success("Đã copy toàn bộ biên bản cuộc họp vào clipboard!");
    setTimeout(() => setCopiedAll(false), 2000);
  };

  const generateJapaneseEmail = (res: any): string => {
    if (!res) return '';
    const mTitle = res.title || title || '打ち合わせ';
    const mDate = res.meeting_date || meetingDate;
    const proj = allProjects.find(p => p.id === (res.project_id || selectedProjectId)) || activeProject;
    const projName = proj ? `${proj.name} (${proj.code})` : 'プロジェクト';
    const participants = Array.isArray(res.participants) && res.participants.length > 0 
      ? res.participants.join('、') 
      : '関係者各位';

    let email = `件名：【議事録送付】${mTitle}（${mDate}）\n\n`;
    email += `関係者各位\n\n`;
    email += `お疲れ様です。${projName} 開発チームです。\n\n`;
    email += `${mDate}に実施いたしました「${mTitle}」の議事録を送付いたします。\n`;
    email += `内容をご確認いただき、修正点や認識の相違がございましたらご指摘いただけますと幸いです。\n\n`;
    email += `==================================================\n`;
    email += `■ 開催概要\n`;
    email += `・日時：${mDate}\n`;
    email += `・件名：${mTitle}\n`;
    email += `・参加者：${participants}\n\n`;

    const summaryJa = res.summary_ja || res.summary_markdown || '';
    if (summaryJa) {
      email += `■ エグゼクティブサマリー\n`;
      email += `${summaryJa.replace(/###\s*/g, '').trim()}\n\n`;
    }

    if (res.decisions && res.decisions.length > 0) {
      email += `■ 決定事項（Key Decisions）\n`;
      res.decisions.forEach((d: any, idx: number) => {
        const dTitle = d.title_ja || d.title || d.title_vi || '';
        const dDetail = d.detail_ja || d.detail || d.detail_vi || '';
        email += `${idx + 1}. 【${dTitle}】\n`;
        if (dDetail) email += `   詳細：${dDetail}\n`;
      });
      email += `\n`;
    }

    if (res.action_items && res.action_items.length > 0) {
      email += `■ 今後のアクションアイテム（Action Items）\n`;
      res.action_items.forEach((a: any) => {
        const task = a.task_ja || a.task || a.task_vi || '';
        const assignee = a.assignee || '担当未定';
        const due = a.due_date || '期日未定';
        email += `・[${a.priority || '通常'}] ${task}（担当：${assignee} / 期限：${due}）\n`;
      });
      email += `\n`;
    }

    if (res.open_questions && res.open_questions.length > 0) {
      email += `■ 保留・確認事項（Open Questions）\n`;
      res.open_questions.forEach((q: any) => {
        const qText = q.question_ja || q.question || q.question_vi || '';
        const owner = q.owner || '要確認';
        email += `・${qText}（担当確認：${owner}）\n`;
      });
      email += `\n`;
    }

    email += `==================================================\n`;
    email += `以上、ご確認のほどよろしくお願い申し上げます。\n`;
    return email;
  };

  const handleOpenEmailModal = () => {
    if (!currentResult) return;
    const content = generateJapaneseEmail(currentResult);
    setEmailContent(content);
    setShowEmailModal(true);
  };

  const handleCopyEmail = () => {
    navigator.clipboard.writeText(emailContent);
    setCopiedEmail(true);
    toast.success("Đã copy Email tiếng Nhật chuẩn Keigo vào clipboard!");
    setTimeout(() => setCopiedEmail(false), 2000);
  };

  const handleDownloadMarkdown = () => {
    if (!currentResult) return;
    const mTitle = currentResult.title || title || 'Meeting_Minutes';
    const mDate = currentResult.meeting_date || meetingDate || 'Undated';
    let md = `# 議事録 / BIÊN BẢN CUỘC HỌP: ${mTitle}\n\n`;
    md += `- **Ngày họp (Date):** ${mDate}\n`;
    if (currentResult.participants?.length > 0) {
      md += `- **Thành phần tham gia (Participants):** ${currentResult.participants.join(', ')}\n`;
    }
    md += `\n---\n\n`;

    md += `## 1. Tóm tắt điều hành (Executive Summary)\n\n`;
    if (currentResult.summary_ja) {
      md += `### 🇯🇵 日本語サマリー (Japanese Summary)\n\n${currentResult.summary_ja}\n\n`;
    }
    if (currentResult.summary_vi) {
      md += `### 🇻🇳 Tóm tắt Tiếng Việt (Vietnamese Summary)\n\n${currentResult.summary_vi}\n\n`;
    } else if (currentResult.summary_markdown && !currentResult.summary_ja) {
      md += `${currentResult.summary_markdown}\n\n`;
    }

    if (currentResult.decisions?.length > 0) {
      md += `## 2. Quyết định đã chốt (Key Decisions)\n\n`;
      currentResult.decisions.forEach((d: any, idx: number) => {
        const viTitle = d.title_vi || d.title || d.title_ja || '';
        const jaTitle = d.title_ja ? ` / 【${d.title_ja}】` : '';
        md += `### ${idx + 1}. ${viTitle}${jaTitle}\n`;
        if (d.detail_vi || d.detail) md += `- **Chi tiết (VI):** ${d.detail_vi || d.detail}\n`;
        if (d.detail_ja) md += `- **詳細 (JA):** ${d.detail_ja}\n`;
        if (d.evidence) md += `- **Bằng chứng trích dẫn (Evidence):** *"${d.evidence}"*\n`;
        md += `\n`;
      });
    }

    if (currentResult.action_items?.length > 0) {
      md += `## 3. Việc cần làm (Action Items)\n\n`;
      currentResult.action_items.forEach((a: any) => {
        const viTask = a.task_vi || a.task || a.task_ja || '';
        const jaTask = a.task_ja ? ` [JA: ${a.task_ja}]` : '';
        md += `- [ ] [${a.priority || 'NORMAL'}] **${viTask}**${jaTask} (Phụ trách: ${a.assignee || 'Unassigned'} | Hạn: ${a.due_date || 'TBD'})\n`;
      });
      md += `\n`;
    }

    if (currentResult.open_questions?.length > 0) {
      md += `## 4. Vấn đề tồn đọng & Cần xác nhận (Open Questions)\n\n`;
      currentResult.open_questions.forEach((q: any) => {
        const viQ = q.question_vi || q.question || q.question_ja || '';
        const jaQ = q.question_ja ? ` [JA: ${q.question_ja}]` : '';
        md += `- [${q.urgency || 'NORMAL'}] ${viQ}${jaQ} (Bên xác nhận: ${q.owner || 'Client'})\n`;
      });
    }

    const blob = new Blob([md], { type: 'text/markdown;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    const safeTitle = mTitle.replace(/[^a-zA-Z0-9_-]/g, '_');
    a.download = `Meeting_${mDate}_${safeTitle}.md`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    toast.success("Đã tải xuống file Markdown (.md) thành công!");
  };

  const handleAskBrain = async (overrideQuery?: string) => {
    const q = (overrideQuery || brainQuery).trim();
    if (!q) {
      toast.warning("Vui lòng nhập câu hỏi tra cứu lịch sử cuộc họp!");
      return;
    }

    const userMsgId = `user_${Date.now()}`;
    const userMsg: BrainChatMessage = {
      id: userMsgId,
      role: 'user',
      text: q,
      timestamp: Date.now()
    };

    const updatedMessages = [...brainChatMessages, userMsg];
    setBrainChatMessages(updatedMessages);
    setBrainQuery('');
    setAskingBrain(true);

    try {
      const targetProjectId = selectedProjectId || activeProject?.id || undefined;
      const historyPayload = brainChatMessages.map(m => ({
        role: m.role,
        content: m.text
      }));

      const res = await apiClient.askMeetings({
        project_id: targetProjectId,
        query: q,
        preferred_provider: selectedProvider,
        model: selectedModel || undefined,
        chat_history: historyPayload.length > 0 ? historyPayload : undefined
      });

      const assistantMsg: BrainChatMessage = {
        id: `ast_${Date.now()}`,
        role: 'assistant',
        text: res.answer || "Đã phân tích thông tin từ các cuộc họp.",
        citations: res.citations || [],
        evolution_notes: res.evolution_notes || [],
        timestamp: Date.now()
      };

      setBrainChatMessages([...updatedMessages, assistantMsg]);
      toast.success("Meeting Brain đã hoàn tất trả lời!");
    } catch (e: any) {
      console.error("Meeting Brain Q&A failed", e);
      toast.error(`Tra cứu thất bại: ${e.response?.data?.detail || e.message || 'Lỗi xử lý'}`);
    } finally {
      setAskingBrain(false);
    }
  };

  const handleClearBrainChat = () => {
    setBrainChatMessages([]);
    setBrainQuery('');
    toast.info("Đã làm mới phiên chat Meeting Brain.");
  };

  const handleCopyBrainAnswer = (msgId: string, text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedBrainMsgId(msgId);
    toast.success("Đã copy câu trả lời của Meeting Brain vào clipboard!");
    setTimeout(() => setCopiedBrainMsgId(null), 2000);
  };


  const getPriorityBadgeClass = (priority: string) => {
    const p = (priority || '').toUpperCase();
    if (p.includes('HIGH')) return 'bg-rose-500/20 text-rose-300 border-rose-500/30';
    if (p.includes('MED')) return 'bg-amber-500/20 text-amber-300 border-amber-500/30';
    return 'bg-blue-500/20 text-blue-300 border-blue-500/30';
  };

  return (
    <div className="flex-1 overflow-y-auto bg-slate-950 p-6 space-y-6">
      {/* Header */}
      <div className="border-b border-slate-800 pb-5 flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
          <div className="flex items-center gap-2.5">
            <span className="px-2 py-0.5 rounded text-[11px] font-bold uppercase tracking-wider bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 flex items-center gap-1">
              <Sparkles className="w-3 h-3" /> Meeting Intelligence
            </span>
            <h1 className="text-xl font-bold text-white tracking-tight">Executive Meeting Minutes & Action Items</h1>
          </div>
          <p className="text-xs text-slate-400 mt-1">
            Biến hội thoại họp tiếng Nhật thành Biên bản điều hành, trích xuất Quyết định kỹ thuật, Việc cần làm (Action Items) & Câu hỏi tồn đọng.
          </p>
        </div>

        {/* Active Project Dropdown in Header */}
        <div className="flex items-center gap-2 px-3 py-1.5 bg-slate-900 border border-slate-800 rounded-xl text-xs shadow-xs">
          <Tag className="w-3.5 h-3.5 text-emerald-400" />
          <span className="text-slate-400 font-semibold">Active Project:</span>
          <select
            value={activeProject?.id || ''}
            onChange={(e) => {
              const found = allProjects.find(p => p.id === e.target.value);
              setActiveProject?.(found || null);
              if (found) setSelectedProjectId(found.id);
            }}
            className="bg-slate-950 border border-slate-800 text-emerald-300 font-medium rounded px-2.5 py-1 text-xs focus:outline-none focus:border-emerald-500 cursor-pointer"
          >
            <option value="">Tất cả dự án (All Projects)</option>
            {allProjects.map(p => (
              <option key={p.id} value={p.id}>📁 {p.name} ({p.code})</option>
            ))}
          </select>
        </div>
      </div>

      {/* Batch Processing Progress Bar Banner */}
      {batchProgress && (
        <div className="p-4 rounded-xl bg-gradient-to-r from-slate-900 via-emerald-950/40 to-slate-900 border border-emerald-500/50 shadow-xl animate-fadeIn space-y-3">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div className="flex items-center gap-3">
              <div className="p-2.5 rounded-xl bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 shadow-xs">
                <RefreshCw className="w-5 h-5 animate-spin text-emerald-400" />
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <span className="text-xs font-bold text-white uppercase tracking-wider">
                    Đang phân tích hàng loạt: Cuộc họp [{batchProgress.current} / {batchProgress.total}]
                  </span>
                  <span className="text-[11px] px-2 py-0.5 rounded-full bg-emerald-500/20 text-emerald-300 font-mono font-bold border border-emerald-500/30">
                    {batchProgress.percent}%
                  </span>
                </div>
                <p className="text-[11px] text-slate-300 flex items-center gap-1.5 mt-0.5">
                  <FileText className="w-3.5 h-3.5 text-emerald-400" />
                  File hiện tại: <span className="font-semibold text-emerald-300 font-mono">{batchProgress.currentFileName}</span>
                </p>
              </div>
            </div>

            <button
              type="button"
              onClick={() => {
                cancelBatchRef.current = true;
                toast.info("Đang yêu cầu dừng tiến trình sau file hiện tại...");
              }}
              className="px-3.5 py-1.5 rounded-lg bg-rose-600/20 hover:bg-rose-600/30 text-rose-300 border border-rose-500/40 text-xs font-medium flex items-center justify-center gap-1.5 transition cursor-pointer shadow-xs whitespace-nowrap self-start sm:self-center"
            >
              <X className="w-4 h-4 text-rose-400" />
              <span>Hủy tiến trình</span>
            </button>
          </div>

          {/* Animated Progress Bar Track */}
          <div className="w-full bg-slate-950 rounded-full h-2.5 overflow-hidden border border-slate-800 p-0.5">
            <div
              className="bg-gradient-to-r from-emerald-500 via-teal-400 to-emerald-400 h-full rounded-full transition-all duration-500 shadow-sm"
              style={{ width: `${Math.max(5, batchProgress.percent)}%` }}
            />
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left Column: Input Form */}
        <div className="lg:col-span-5 bg-slate-900/70 border border-slate-800 rounded-xl p-4 space-y-4">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2.5 pb-2.5 border-b border-slate-800">
            <h2 className="text-sm font-semibold text-white flex items-center gap-2">
              <Users className="w-4 h-4 text-emerald-400" />
              Meeting Transcript & Context
            </h2>

            {/* Split AI Provider & Searchable Model Combobox */}
            <ProviderModelSelector
              providers={providers}
              selectedProvider={selectedProvider}
              onChangeProvider={setSelectedProvider}
              selectedModel={selectedModel}
              onChangeModel={setSelectedModel}
              allowAutoRouter={true}
              layout="inline"
            />
          </div>

          {/* File Upload & Input Toolbar */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <label className="text-[11px] font-medium text-slate-400 flex items-center gap-1.5">
                <FileText className="w-3.5 h-3.5 text-slate-400" />
                Nội dung hội thoại cuộc họp (Transcript):
              </label>

              {/* Upload Button */}
              <div>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".txt,.vtt,.srt,text/plain"
                  multiple
                  className="hidden"
                  onChange={(e) => {
                    if (e.target.files) handleFiles(e.target.files);
                  }}
                />
                <button
                  type="button"
                  onClick={() => fileInputRef.current?.click()}
                  className="px-3 py-1.5 text-xs rounded-lg bg-emerald-600/20 hover:bg-emerald-600/30 text-emerald-300 border border-emerald-500/40 hover:border-emerald-500 transition flex items-center gap-1.5 cursor-pointer font-medium shadow-xs"
                >
                  <FileUp className="w-3.5 h-3.5 text-emerald-400" />
                  Tải file (.txt, .vtt, .srt)
                </button>
              </div>
            </div>

            {/* Uploaded Files Badges & Order Manager with Drag & Drop */}
            {uploadedFiles.length > 0 && (
              <div className="p-3 rounded-xl bg-emerald-950/20 border border-emerald-500/30 space-y-2.5">
                {/* Header & Controls */}
                <div className="flex flex-wrap items-center justify-between gap-2 text-[11px]">
                  <span className="font-semibold text-emerald-400 flex items-center gap-1.5">
                    <Paperclip className="w-3.5 h-3.5" />
                    Đã nạp {uploadedFiles.length} file cuộc họp:
                  </span>
                  <div className="flex items-center gap-2">
                    {uploadedFiles.length > 1 && (
                      <button
                        type="button"
                        onClick={handleToggleSortDirection}
                        className="px-2.5 py-1 rounded bg-emerald-600/30 hover:bg-emerald-600/40 text-emerald-300 border border-emerald-500/30 transition flex items-center gap-1 text-[11px] cursor-pointer font-medium shadow-2xs"
                        title="Đổi chiều sắp xếp giữa Cũ ➔ Mới và Mới ➔ Cũ"
                      >
                        <ArrowUpDown className="w-3 h-3 text-amber-400" />
                        <span>{sortOrder === 'asc' ? '⚡ Xếp: Cũ ➔ Mới' : '⚡ Xếp: Mới ➔ Cũ'}</span>
                      </button>
                    )}
                    <button
                      type="button"
                      onClick={handleClearFiles}
                      className="text-slate-400 hover:text-rose-400 transition flex items-center gap-1 text-[11px] cursor-pointer"
                    >
                      <X className="w-3 h-3" /> Bỏ tất cả
                    </button>
                  </div>
                </div>

                {/* Reading Order & Detection Guidance Note */}
                <div className="p-2.5 rounded-lg bg-slate-900/90 border border-slate-800 text-[11px] space-y-1">
                  <div className="flex items-center justify-between text-emerald-300 font-semibold">
                    <span className="flex items-center gap-1.5">
                      <Zap className="w-3.5 h-3.5 text-amber-400" />
                      Thứ tự phân tích của AI: Đọc từ trên xuống dưới ({sortOrder === 'asc' ? 'Cũ ➔ Mới' : 'Mới ➔ Cũ'})
                    </span>
                    <span className="text-[10px] text-slate-400 font-normal flex items-center gap-1">
                      <GripVertical className="w-3 h-3 text-emerald-400" /> Kéo thả thẻ để đổi vị trí
                    </span>
                  </div>
                  <p className="text-slate-400 text-[10.5px] leading-relaxed">
                    📌 <em>Tiến trình quyết định:</em> Quyết định ở buổi họp phía dưới sẽ <strong>bổ sung hoặc cập nhật thay thế</strong> quyết định của buổi họp phía trên.
                    <br />
                    💡 <em>Nhận diện đa định dạng:</em> Quét Tên file ➔ 35 dòng đầu transcript ➔ Thứ tự Tuần / Sprint / Buổi họp (hỗ trợ tiếng Nhật Reiwa/Heisei, ISO, Việt Nam, Anh).
                  </p>
                </div>

                {/* Draggable File Cards List */}
                <div className="space-y-1.5 max-h-[220px] overflow-y-auto pr-0.5">
                  {uploadedFiles.map((f, idx) => (
                    <div
                      key={f.id}
                      draggable={true}
                      onDragStart={(e) => handleFileDragStart(e, idx)}
                      onDragOver={(e) => handleFileDragOver(e, idx)}
                      onDragLeave={handleFileDragLeave}
                      onDrop={(e) => handleFileDrop(e, idx)}
                      onDragEnd={handleFileDragEnd}
                      className={`flex items-center justify-between px-2.5 py-2 rounded-lg text-xs transition select-none cursor-grab active:cursor-grabbing ${
                        draggedFileIndex === idx
                          ? 'opacity-40 border-2 border-dashed border-emerald-500 bg-emerald-950/20'
                          : dragOverFileIndex === idx
                          ? 'border-2 border-emerald-400 bg-emerald-950/50 scale-[1.01] shadow-md ring-2 ring-emerald-500/20'
                          : 'bg-slate-900/90 border border-slate-700/80 hover:border-slate-600'
                      }`}
                      title="Kéo thả thẻ này để thay đổi thứ tự tiến trình cuộc họp"
                    >
                      <div className="flex items-center gap-2 min-w-0">
                        {/* Drag Handle Grip Icon */}
                        <div className="text-slate-500 hover:text-slate-300 p-0.5 cursor-grab">
                          <GripVertical className="w-3.5 h-3.5" />
                        </div>

                        {/* Position Index Badge */}
                        <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-slate-800 text-slate-300 font-mono flex-shrink-0">
                          #{idx + 1}
                        </span>

                        <FileText className="w-3.5 h-3.5 text-emerald-400 flex-shrink-0" />
                        
                        {/* Filename & Size */}
                        <span className="font-medium text-slate-200 truncate max-w-[140px] sm:max-w-[200px]" title={f.name}>
                          {f.name}
                        </span>
                        <span className="text-slate-500 text-[10px] flex-shrink-0">({formatFileSize(f.size)})</span>
                        
                        {/* Date / Sequence Badge */}
                        {f.displayLabel ? (
                          <span className={`px-1.5 py-0.5 rounded border text-[10px] font-mono flex items-center gap-1 flex-shrink-0 ${
                            f.source === 'sequence' 
                              ? 'bg-sky-500/15 border-sky-500/30 text-sky-300' 
                              : 'bg-amber-500/15 border-amber-500/30 text-amber-300'
                          }`}>
                            <Calendar className="w-2.5 h-2.5" />
                            <span>{f.displayLabel}</span>
                          </span>
                        ) : (
                          <span className="text-[10px] text-slate-500 italic flex-shrink-0">Chưa rõ ngày</span>
                        )}
                      </div>

                      {/* Remove Single File Button */}
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          handleRemoveFile(idx);
                        }}
                        className="text-slate-500 hover:text-rose-400 p-1 rounded hover:bg-slate-800 transition flex-shrink-0 ml-2"
                        title="Xóa file này khỏi danh sách gộp"
                      >
                        <X className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Project Selection for Meeting */}
          <div>
            <label className="text-[11px] text-slate-400 block mb-1 font-medium flex items-center gap-1.5">
              <Tag className="w-3 h-3 text-emerald-400" />
              Dự án áp dụng (Target Project)
            </label>
            <select
              value={selectedProjectId}
              onChange={(e) => {
                const newId = e.target.value;
                setSelectedProjectId(newId);
                const found = allProjects.find(p => p.id === newId);
                if (found) {
                  setActiveProject?.(found);
                }
              }}
              className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 focus:outline-none focus:border-emerald-500 cursor-pointer font-medium"
            >
              {allProjects.map(p => (
                <option key={p.id} value={p.id}>📁 {p.name} ({p.code})</option>
              ))}
              {allProjects.length === 0 && (
                <option value="">Mặc định (Default Project)</option>
              )}
            </select>
          </div>

          <div className="grid grid-cols-2 gap-3 text-xs">
            <div>
              <label className="text-[11px] text-slate-400 block mb-1">Tiêu đề cuộc họp</label>
              <input
                type="text"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="Ví dụ: Họp Sprint Architecture & Kế hoạch UAT..."
                className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-emerald-500"
              />
            </div>
            <div>
              <label className="text-[11px] text-slate-400 block mb-1">Ngày họp</label>
              <input
                type="date"
                value={meetingDate}
                onChange={(e) => setMeetingDate(e.target.value)}
                className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-emerald-500"
              />
            </div>
          </div>

          {/* Transcript Area with Drag & Drop */}
          <div
            className="relative"
            onDragOver={(e) => {
              e.preventDefault();
              setIsDragging(true);
            }}
            onDragLeave={() => setIsDragging(false)}
            onDrop={(e) => {
              e.preventDefault();
              setIsDragging(false);
              if (e.dataTransfer.files) handleFiles(e.dataTransfer.files);
            }}
          >
            <div className="flex items-center justify-between mb-1">
              <label className="text-[11px] text-slate-400">Nội dung trao đổi / Transcript</label>
              <span className="text-[10px] text-slate-500">Hỗ trợ dán hoặc kéo thả .txt, .vtt, .srt</span>
            </div>

            <div className="relative">
              <textarea
                value={transcript}
                onChange={(e) => setTranscript(e.target.value)}
                rows={11}
                placeholder="Dán nội dung chat hoặc kéo thả các file .txt, .vtt, .srt tại đây..."
                className={`w-full bg-slate-950 border rounded-lg p-3 text-xs text-slate-200 font-mono resize-none focus:outline-none transition leading-relaxed ${
                  isDragging 
                    ? 'border-emerald-400 ring-2 ring-emerald-500/20 bg-emerald-950/20' 
                    : 'border-slate-800 focus:border-emerald-500'
                }`}
              />

              {isDragging && (
                <div className="absolute inset-0 bg-emerald-950/90 backdrop-blur-xs border-2 border-dashed border-emerald-400 rounded-lg flex flex-col items-center justify-center pointer-events-none text-emerald-300 gap-2">
                  <Upload className="w-8 h-8 animate-bounce text-emerald-400" />
                  <div className="font-semibold text-xs">Thả các file .txt, .vtt, .srt vào đây</div>
                  <div className="text-[11px] text-emerald-400/80">Tự động làm sạch timestamp và gộp nội dung</div>
                </div>
              )}
            </div>
          </div>

          <button
            onClick={handleGenerateMinutes}
            disabled={generating || !transcript.trim()}
            className="flex items-center justify-center gap-2 w-full py-2.5 px-4 rounded-lg bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white text-xs font-semibold shadow-lg shadow-emerald-950/40 transition cursor-pointer"
          >
            {generating ? (
              <>
                <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                {uploadedFiles.length >= 2 
                  ? `Đang tổng hợp ${uploadedFiles.length} buổi họp qua Map-Reduce...` 
                  : 'Đang phân tích & trích xuất biên bản...'}
              </>
            ) : (
              <>
                <Sparkles className="w-3.5 h-3.5" />
                Generate Executive Minutes & Action Items
              </>
            )}
          </button>
        </div>

        {/* Right Column: Structured Output */}
        <div className="lg:col-span-7 bg-slate-900/70 border border-slate-800 rounded-xl p-4 space-y-4 flex flex-col">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-800 pb-3">
            <div className="flex items-center gap-2">
              <FileText className="w-4 h-4 text-emerald-400" />
              <h2 className="text-sm font-semibold text-white">Kết quả biên bản cuộc họp</h2>
            </div>
            
            {/* Language Switcher & Export Hub */}
            <div className="flex flex-wrap items-center gap-2">
              {/* Language Toggle */}
              <div className="flex items-center bg-slate-950 p-0.5 rounded-lg border border-slate-800 text-[11px]">
                <button
                  type="button"
                  onClick={() => setLanguageView('vi')}
                  className={`px-2 py-1 rounded transition cursor-pointer font-medium flex items-center gap-1 ${
                    languageView === 'vi' 
                      ? 'bg-emerald-600 text-white shadow-xs' 
                      : 'text-slate-400 hover:text-slate-200'
                  }`}
                  title="Xem biên bản bằng Tiếng Việt (Dành cho Dev & Quản lý)"
                >
                  <span>🇻🇳</span> VI
                </button>
                <button
                  type="button"
                  onClick={() => setLanguageView('ja')}
                  className={`px-2 py-1 rounded transition cursor-pointer font-medium flex items-center gap-1 ${
                    languageView === 'ja' 
                      ? 'bg-emerald-600 text-white shadow-xs' 
                      : 'text-slate-400 hover:text-slate-200'
                  }`}
                  title="Xem biên bản bằng Tiếng Nhật (Dành cho Khách hàng & Stakeholders)"
                >
                  <span>🇯🇵</span> JA
                </button>
                <button
                  type="button"
                  onClick={() => setLanguageView('bilingual')}
                  className={`px-2 py-1 rounded transition cursor-pointer font-medium flex items-center gap-1 ${
                    languageView === 'bilingual' 
                      ? 'bg-emerald-600 text-white shadow-xs' 
                      : 'text-slate-400 hover:text-slate-200'
                  }`}
                  title="Xem song ngữ song song cả Tiếng Nhật và Tiếng Việt"
                >
                  <span>🌐</span> Song ngữ
                </button>
              </div>

              {currentResult && (
                <div className="flex items-center gap-1.5">
                  <button
                    onClick={handleOpenEmailModal}
                    className="flex items-center gap-1 text-[11px] px-2.5 py-1 rounded bg-indigo-600/30 hover:bg-indigo-600/50 text-indigo-300 border border-indigo-500/40 transition cursor-pointer font-medium"
                    title="Mở mẫu email gửi biên bản bằng tiếng Nhật chuẩn Keigo"
                  >
                    <Mail className="w-3.5 h-3.5 text-indigo-400" />
                    <span>Email JA</span>
                  </button>
                  <button
                    onClick={handleDownloadMarkdown}
                    className="flex items-center gap-1 text-[11px] px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 transition cursor-pointer font-medium"
                    title="Tải biên bản về máy định dạng Markdown (.md)"
                  >
                    <Download className="w-3.5 h-3.5 text-slate-400" />
                    <span>Tải .md</span>
                  </button>
                  <button
                    onClick={() => copySummary()}
                    className="flex items-center gap-1 text-[11px] px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-200 transition cursor-pointer"
                    title="Copy phần tóm tắt điều hành"
                  >
                    {copiedSummary ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
                    <span>{copiedSummary ? 'Đã copy' : 'Tóm tắt'}</span>
                  </button>
                  <button
                    onClick={copyFullReport}
                    className="flex items-center gap-1 text-[11px] px-2.5 py-1 rounded bg-emerald-600/80 hover:bg-emerald-600 text-white font-medium transition shadow cursor-pointer"
                    title="Copy toàn bộ biên bản, quyết định và action items"
                  >
                    {copiedAll ? <Check className="w-3.5 h-3.5" /> : <Copy className="w-3.5 h-3.5" />}
                    <span>{copiedAll ? 'Đã copy' : 'Toàn bộ'}</span>
                  </button>
                </div>
              )}
            </div>
          </div>

          {currentResult ? (
            <div className="space-y-4 text-xs overflow-y-auto max-h-[640px] pr-1">
              {/* Executive Summary Section */}
              <div className="space-y-1.5">
                <div className="text-[11px] font-bold text-slate-300 uppercase tracking-wider flex items-center justify-between">
                  <span className="flex items-center gap-1.5">
                    <FileText className="w-3.5 h-3.5 text-emerald-400" />
                    {languageView === 'ja' ? 'エグゼクティブサマリー (Executive Summary)' : 
                     languageView === 'vi' ? 'Tóm tắt điều hành (Executive Summary)' : 
                     'Executive Summary (Song ngữ JA / VI)'}
                  </span>
                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => setIsRawSummaryMode(!isRawSummaryMode)}
                      className={`flex items-center gap-1 text-[10.5px] px-2 py-0.5 rounded border transition cursor-pointer font-normal normal-case ${
                        isRawSummaryMode
                          ? 'bg-amber-950/60 border-amber-700/50 text-amber-300 shadow-xs'
                          : 'bg-slate-800/80 border-slate-700/60 text-slate-300 hover:bg-slate-700 hover:text-white'
                      }`}
                      title={isRawSummaryMode ? "Chuyển sang chế độ xem trực quan Markdown" : "Xem mã nguồn Markdown gốc"}
                    >
                      {isRawSummaryMode ? <Eye className="w-3 h-3 text-amber-400" /> : <Code className="w-3 h-3 text-emerald-400" />}
                      <span>{isRawSummaryMode ? 'Xem trực quan' : 'Xem mã MD'}</span>
                    </button>
                    <span className="text-[10px] text-slate-500 font-normal lowercase">
                      {languageView === 'ja' ? '🇯🇵 日本語表示' : languageView === 'vi' ? '🇻🇳 Tiếng Việt' : '🌐 Song ngữ'}
                    </span>
                  </div>
                </div>

                {languageView === 'bilingual' ? (
                  <div className="space-y-2.5">
                    {currentResult.summary_ja && (
                      <div className="bg-slate-950/90 p-3.5 rounded-lg border border-slate-800 space-y-1.5 shadow-xs">
                        <div className="text-[10px] font-bold text-emerald-400 flex items-center justify-between pb-1 border-b border-slate-800/60">
                          <span className="flex items-center gap-1">
                            <span>🇯🇵</span> 日本語サマリー（顧客・ステークホルダー向け）
                          </span>
                          {isRawSummaryMode && (
                            <span className="text-[9.5px] font-mono text-amber-400/80 uppercase font-normal">Raw Markdown</span>
                          )}
                        </div>
                        {isRawSummaryMode ? (
                          <div className="whitespace-pre-wrap font-mono text-[11px] text-slate-300 bg-slate-900/60 p-2.5 rounded border border-slate-800/80 leading-relaxed">
                            {currentResult.summary_ja}
                          </div>
                        ) : (
                          <MarkdownView content={currentResult.summary_ja} accent="emerald" />
                        )}
                      </div>
                    )}
                    <div className="bg-slate-950/90 p-3.5 rounded-lg border border-slate-800 space-y-1.5 shadow-xs">
                      <div className="text-[10px] font-bold text-sky-400 flex items-center justify-between pb-1 border-b border-slate-800/60">
                        <span className="flex items-center gap-1">
                          <span>🇻🇳</span> Tóm tắt Tiếng Việt（Team Kỹ thuật & Quản lý）
                        </span>
                        {isRawSummaryMode && (
                          <span className="text-[9.5px] font-mono text-amber-400/80 uppercase font-normal">Raw Markdown</span>
                        )}
                      </div>
                      {isRawSummaryMode ? (
                        <div className="whitespace-pre-wrap font-mono text-[11px] text-slate-300 bg-slate-900/60 p-2.5 rounded border border-slate-800/80 leading-relaxed">
                          {currentResult.summary_vi || currentResult.summary_markdown}
                        </div>
                      ) : (
                        <MarkdownView content={currentResult.summary_vi || currentResult.summary_markdown || ''} accent="sky" />
                      )}
                    </div>
                  </div>
                ) : (
                  <div className="bg-slate-950/80 p-3.5 rounded-lg border border-slate-800/80 shadow-xs">
                    {isRawSummaryMode ? (
                      <div className="space-y-1.5">
                        <div className="text-[9.5px] font-mono text-amber-400/80 uppercase">Raw Markdown Source</div>
                        <div className="whitespace-pre-wrap font-mono text-[11px] text-slate-300 bg-slate-900/60 p-2.5 rounded border border-slate-800/80 leading-relaxed">
                          {languageView === 'ja'
                            ? (currentResult.summary_ja || currentResult.summary_markdown)
                            : (currentResult.summary_vi || currentResult.summary_markdown)}
                        </div>
                      </div>
                    ) : (
                      <MarkdownView
                        content={languageView === 'ja'
                          ? (currentResult.summary_ja || currentResult.summary_markdown || '')
                          : (currentResult.summary_vi || currentResult.summary_markdown || '')}
                        accent={languageView === 'ja' ? 'emerald' : 'sky'}
                      />
                    )}
                  </div>
                )}
              </div>


              {/* Action Items List */}
              {currentResult.action_items?.length > 0 && (
                <div className="space-y-2">
                  <div className="text-[11px] font-bold text-emerald-400 uppercase tracking-wider flex items-center justify-between">
                    <span className="flex items-center gap-1.5">
                      <CheckSquare className="w-3.5 h-3.5" /> 
                      {languageView === 'ja' ? 'アクションアイテム（Action Items）' : 'Action Items & Việc cần làm'} ({currentResult.action_items.length})
                    </span>
                    <span className="text-[10px] text-slate-400 lowercase font-normal">
                      Tự động đồng bộ sang BrSE Dashboard
                    </span>
                  </div>
                  <div className="space-y-2">
                    {currentResult.action_items.map((act: any, i: number) => {
                      const taskVi = act.task_vi || act.task || act.task_ja || '';
                      const taskJa = act.task_ja || act.task || act.task_vi || '';
                      return (
                        <div key={i} className="p-2.5 rounded-lg bg-slate-950/90 border border-slate-800 hover:border-slate-700 transition space-y-1.5">
                          <div className="flex items-start justify-between gap-2">
                            <div className="font-medium text-slate-200 leading-snug space-y-1">
                              {languageView === 'ja' ? (
                                <div>{taskJa}</div>
                              ) : languageView === 'vi' ? (
                                <div>{taskVi}</div>
                              ) : (
                                <>
                                  <div className="flex items-start gap-1.5">
                                    <span className="text-[10px] px-1 rounded bg-slate-800 text-slate-300 font-mono flex-shrink-0 mt-0.5">VI</span>
                                    <span>{taskVi}</span>
                                  </div>
                                  {act.task_ja && act.task_ja !== taskVi && (
                                    <div className="flex items-start gap-1.5 text-slate-400 text-[11px]">
                                      <span className="text-[10px] px-1 rounded bg-slate-800 text-emerald-400 font-mono flex-shrink-0 mt-0.5">JA</span>
                                      <span>{act.task_ja}</span>
                                    </div>
                                  )}
                                </>
                              )}
                            </div>
                            <span className={`text-[10px] font-bold px-2 py-0.5 rounded border uppercase flex-shrink-0 ${getPriorityBadgeClass(act.priority)}`}>
                              {act.priority || 'HIGH'}
                            </span>
                          </div>
                          <div className="flex items-center justify-between text-[11px] text-slate-400 pt-1 border-t border-slate-900">
                            <span className="flex items-center gap-1">
                              <Users className="w-3 h-3 text-slate-500" />
                              Phụ trách: <strong className="text-slate-300 font-semibold">{act.assignee || 'Unassigned'}</strong>
                            </span>
                            <span className="font-mono text-amber-400 flex items-center gap-1">
                              <Clock className="w-3 h-3" />
                              Hạn chót: {act.due_date || 'Chưa xác định'}
                            </span>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              {/* Decisions List */}
              {currentResult.decisions?.length > 0 && (
                <div className="space-y-2">
                  <div className="text-[11px] font-bold text-sky-400 uppercase tracking-wider flex items-center gap-1.5">
                    <ShieldCheck className="w-3.5 h-3.5" />
                    {languageView === 'ja' ? '決定事項（Key Decisions）' : 'Quyết định đã chốt (Key Decisions)'} ({currentResult.decisions.length})
                  </div>
                  <div className="space-y-2">
                    {currentResult.decisions.map((dec: any, i: number) => {
                      const titleVi = dec.title_vi || dec.title || dec.title_ja || '';
                      const titleJa = dec.title_ja || dec.title || dec.title_vi || '';
                      const detailVi = dec.detail_vi || dec.detail || dec.detail_ja || '';
                      const detailJa = dec.detail_ja || dec.detail || dec.detail_vi || '';

                      return (
                        <div key={i} className="p-2.5 rounded-lg bg-slate-950/90 border border-slate-800 space-y-1.5">
                          {languageView === 'ja' ? (
                            <>
                              <div className="font-semibold text-slate-200 flex items-center gap-1.5">
                                <span className="w-1.5 h-1.5 rounded-full bg-sky-400"></span>
                                {titleJa}
                              </div>
                              {detailJa && (
                                <div className="text-[11px] text-slate-300 pl-3 leading-relaxed">
                                  {detailJa}
                                </div>
                              )}
                            </>
                          ) : languageView === 'vi' ? (
                            <>
                              <div className="font-semibold text-slate-200 flex items-center gap-1.5">
                                <span className="w-1.5 h-1.5 rounded-full bg-sky-400"></span>
                                {titleVi}
                              </div>
                              {detailVi && (
                                <div className="text-[11px] text-slate-300 pl-3 leading-relaxed">
                                  {detailVi}
                                </div>
                              )}
                            </>
                          ) : (
                            <>
                              <div className="font-semibold text-slate-200 space-y-1">
                                <div className="flex items-center gap-1.5">
                                  <span className="w-1.5 h-1.5 rounded-full bg-sky-400"></span>
                                  <span>{titleVi}</span>
                                </div>
                                {dec.title_ja && dec.title_ja !== titleVi && (
                                  <div className="text-[11px] text-emerald-400 font-normal pl-3">
                                    【{dec.title_ja}】
                                  </div>
                                )}
                              </div>
                              {detailVi && (
                                <div className="text-[11px] text-slate-300 pl-3 leading-relaxed">
                                  {detailVi}
                                </div>
                              )}
                              {detailJa && detailJa !== detailVi && (
                                <div className="text-[11px] text-slate-400 pl-3 leading-relaxed italic border-l border-emerald-500/30 my-1 ml-3">
                                  {detailJa}
                                </div>
                              )}
                            </>
                          )}

                          {dec.evidence && (
                            <div className="text-[11px] text-slate-400 bg-slate-900/60 p-2 rounded border-l-2 border-sky-500/50 italic">
                              "{dec.evidence}"
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              {/* Open Questions List */}
              {currentResult.open_questions?.length > 0 && (
                <div className="space-y-2">
                  <div className="text-[11px] font-bold text-amber-400 uppercase tracking-wider flex items-center gap-1.5">
                    <HelpCircle className="w-3.5 h-3.5" /> 
                    {languageView === 'ja' ? '保留・確認事項（Open Questions）' : 'Vấn đề tồn đọng & Cần xác nhận (Open Questions)'} ({currentResult.open_questions.length})
                  </div>
                  <div className="space-y-2">
                    {currentResult.open_questions.map((q: any, i: number) => {
                      const qVi = q.question_vi || q.question || q.question_ja || '';
                      const qJa = q.question_ja || q.question || q.question_vi || '';
                      return (
                        <div key={i} className="p-2.5 rounded-lg bg-slate-950/90 border border-slate-800 flex items-start justify-between gap-3">
                          <div className="space-y-1 flex-1">
                            <div className="font-medium text-slate-200">
                              {languageView === 'ja' ? qJa : languageView === 'vi' ? qVi : (
                                <div className="space-y-1">
                                  <div>{qVi}</div>
                                  {q.question_ja && q.question_ja !== qVi && (
                                    <div className="text-[11px] text-slate-400">↳ 🇯🇵 {q.question_ja}</div>
                                  )}
                                </div>
                              )}
                            </div>
                            <div className="text-[11px] text-slate-400">
                              Bên phụ trách trả lời: <span className="text-amber-300 font-medium">{q.owner || 'Client'}</span>
                            </div>
                          </div>
                          <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-amber-500/10 text-amber-400 border border-amber-500/20 uppercase flex-shrink-0">
                            {q.urgency || 'HIGH'}
                          </span>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}
            </div>
          ) : (
            <div className="p-16 text-center text-slate-500 text-xs my-auto">
              <FileText className="w-10 h-10 mx-auto mb-3 text-slate-700" />
              <div className="text-slate-400 font-medium mb-1">Chưa có kết quả biên bản cuộc họp</div>
              <p className="max-w-xs mx-auto text-slate-500">
                Chọn mẫu hoặc dán biên bản/hội thoại cuộc họp ở cột bên trái và bấm <strong className="text-emerald-400">"Generate Executive Minutes"</strong> để xem phân tích.
              </p>
            </div>
          )}
        </div>
      </div>

      {/* Bottom Section: Meeting Brain Q&A + Past Meetings History */}
      <div className="space-y-4">
        {/* Pillar 4: Meeting Brain Cross-Meeting Q&A Chat */}
        <div className="p-4 rounded-xl bg-slate-900/80 border border-emerald-500/30 shadow-sm space-y-3">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-slate-800 pb-2.5">
            <div className="flex items-center gap-2">
              <div className="p-1.5 rounded-lg bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">
                <Bot className="w-4 h-4" />
              </div>
              <div>
                <h3 className="text-xs font-bold text-white uppercase tracking-wider flex items-center gap-1.5">
                  Meeting Brain Q&A
                  <span className="text-[10px] font-normal px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 lowercase flex items-center gap-1">
                    <MessageSquare className="w-2.5 h-2.5" /> hội thoại đa lượt
                  </span>
                </h3>
                <p className="text-[11px] text-slate-400">
                  Hỏi đáp trực tiếp và trò chuyện nối tiếp trên toàn bộ lịch sử các cuộc họp dự án.
                </p>
              </div>
            </div>

            {brainChatMessages.length > 0 && (
              <button
                onClick={handleClearBrainChat}
                className="flex items-center gap-1 text-[11px] text-slate-300 hover:text-white px-2.5 py-1 rounded bg-slate-800/80 hover:bg-slate-800 border border-slate-700/60 transition cursor-pointer self-start sm:self-auto"
                title="Xóa lịch sử và bắt đầu hội thoại mới"
              >
                <RotateCcw className="w-3 h-3 text-slate-400" />
                <span>Đoạn chat mới</span>
              </button>
            )}
          </div>

          {/* Quick Prompt Suggestion Chips (when no messages) */}
          {brainChatMessages.length === 0 && (
            <div className="space-y-1.5 py-1">
              <div className="text-[11px] text-slate-400 flex items-center gap-1">
                <Sparkles className="w-3 h-3 text-emerald-400" /> Gợi ý câu hỏi nhanh:
              </div>
              <div className="flex flex-wrap gap-1.5">
                {[
                  "Tiến trình chốt kiến trúc qua các tuần?",
                  "Các việc cần làm (Action Items) đang pending?",
                  "Những câu hỏi khách hàng chưa phản hồi (Open Questions)?",
                  "Tóm tắt các mốc làm việc quan trọng nhất?"
                ].map((chip, idx) => (
                  <button
                    key={idx}
                    type="button"
                    onClick={() => handleAskBrain(chip)}
                    disabled={askingBrain}
                    className="text-[11px] px-2.5 py-1 rounded-full bg-slate-950 border border-slate-800 hover:border-emerald-500/40 text-slate-300 hover:text-emerald-300 transition cursor-pointer flex items-center gap-1"
                  >
                    <span>💡</span>
                    <span>{chip}</span>
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Chat Messages Conversation Stream */}
          {brainChatMessages.length > 0 && (
            <div className="space-y-3 max-h-[460px] overflow-y-auto pr-1 py-1 rounded-lg">
              {brainChatMessages.map((msg) => (
                <div key={msg.id} className="space-y-1.5">
                  {msg.role === 'user' ? (
                    <div className="flex justify-end">
                      <div className="bg-emerald-950/50 border border-emerald-600/40 text-emerald-100 px-3.5 py-2 rounded-2xl rounded-tr-xs text-xs max-w-[85%] shadow-xs leading-relaxed">
                        {msg.text}
                      </div>
                    </div>
                  ) : (
                    <div className="flex items-start gap-2.5 max-w-[96%]">
                      <div className="w-6 h-6 rounded-full bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 flex items-center justify-center shrink-0 mt-0.5">
                        <Bot className="w-3.5 h-3.5" />
                      </div>
                      <div className="flex-1 bg-slate-950/90 border border-slate-800/90 p-3.5 rounded-2xl rounded-tl-xs space-y-2.5 shadow-xs">
                        <div className="flex items-center justify-between text-[11px] border-b border-slate-800/80 pb-1.5">
                          <span className="font-semibold text-emerald-400 flex items-center gap-1">
                            <Sparkles className="w-3 h-3" /> Meeting Brain
                          </span>
                          <button
                            onClick={() => handleCopyBrainAnswer(msg.id, msg.text)}
                            className="flex items-center gap-1 text-[10.5px] text-slate-400 hover:text-slate-200 px-1.5 py-0.5 rounded hover:bg-slate-800 transition cursor-pointer"
                            title="Copy câu trả lời này"
                          >
                            {copiedBrainMsgId === msg.id ? (
                              <>
                                <Check className="w-3 h-3 text-emerald-400" />
                                <span className="text-emerald-400">Đã copy</span>
                              </>
                            ) : (
                              <>
                                <Copy className="w-3 h-3" />
                                <span>Copy</span>
                              </>
                            )}
                          </button>
                        </div>

                        {/* Render Markdown Answer */}
                        <div className="text-xs">
                          <MarkdownView content={msg.text} accent="emerald" />
                        </div>

                        {/* Evolution Notes */}
                        {msg.evolution_notes && msg.evolution_notes.length > 0 && (
                          <div className="p-2.5 rounded bg-amber-500/10 border border-amber-500/30 text-xs space-y-1 text-amber-200">
                            <div className="font-bold text-[10.5px] text-amber-300 uppercase tracking-wider flex items-center gap-1">
                              <History className="w-3 h-3" /> Tiến trình thay đổi quyết định qua các tuần:
                            </div>
                            <ul className="list-disc list-inside space-y-0.5 text-[11px] pl-1">
                              {msg.evolution_notes.map((note: string, idx: number) => (
                                <li key={idx}>{note}</li>
                              ))}
                            </ul>
                          </div>
                        )}

                        {/* Citations Pills */}
                        {msg.citations && msg.citations.length > 0 && (
                          <div className="space-y-1 pt-1 border-t border-slate-900">
                            <div className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">
                              Căn cứ từ các cuộc họp (Bấm để mở):
                            </div>
                            <div className="flex flex-wrap gap-1.5">
                              {msg.citations.map((c: any, idx: number) => {
                                const matchedMeeting = meetings.find(m => m.id === c.meeting_id || m.title === c.title);
                                return (
                                  <button
                                    key={idx}
                                    type="button"
                                    onClick={() => {
                                      if (matchedMeeting) {
                                        setCurrentResult(matchedMeeting);
                                        toast.info(`Đã nạp biên bản "${matchedMeeting.title}" lên bảng xem.`);
                                      }
                                    }}
                                    className="px-2 py-0.5 rounded bg-slate-900 hover:bg-slate-800 text-emerald-300 border border-emerald-500/30 text-[10.5px] flex items-center gap-1 transition cursor-pointer"
                                    title={c.quote_or_reason || 'Bấm để mở cuộc họp này'}
                                  >
                                    <Calendar className="w-3 h-3 text-slate-400" />
                                    <span className="font-semibold">{c.title || 'Cuộc họp'}</span>
                                    <span className="text-[9.5px] text-slate-400">({c.meeting_date || 'Gần đây'})</span>
                                    <ExternalLink className="w-2.5 h-2.5 text-slate-500" />
                                  </button>
                                );
                              })}
                            </div>
                          </div>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              ))}

              {askingBrain && (
                <div className="flex items-center gap-2 text-xs text-emerald-400/90 pl-1 py-1 animate-pulse">
                  <RefreshCw className="w-3.5 h-3.5 animate-spin text-emerald-400" />
                  <span>Meeting Brain đang tổng hợp lịch sử các cuộc họp...</span>
                </div>
              )}
              <div ref={brainChatEndRef} />
            </div>
          )}

          {/* Input Bar */}
          <div className="flex flex-col sm:flex-row gap-2 pt-1">
            <div className="relative flex-1">
              <MessageSquare className="w-3.5 h-3.5 text-slate-500 absolute left-3 top-1/2 -translate-y-1/2" />
              <input
                type="text"
                value={brainQuery}
                onChange={(e) => setBrainQuery(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') handleAskBrain();
                }}
                placeholder={brainChatMessages.length > 0 ? "Hỏi tiếp nối hoặc nhập câu hỏi mới..." : "Ví dụ: 'Kiến trúc xác thực Auth chốt phương án nào?', 'Ai phụ trách fix bug hiệu năng?'..."}
                className="w-full bg-slate-950 border border-slate-800 rounded-lg pl-8 pr-3 py-2 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-emerald-500 transition"
              />
            </div>
            <button
              onClick={() => handleAskBrain()}
              disabled={askingBrain || !brainQuery.trim()}
              className="px-4 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white text-xs font-semibold flex items-center justify-center gap-1.5 transition cursor-pointer shadow-xs whitespace-nowrap"
            >
              {askingBrain ? (
                <>
                  <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                  <span>Đang tra cứu...</span>
                </>
              ) : (
                <>
                  <Send className="w-3.5 h-3.5" />
                  <span>Gửi câu hỏi</span>
                </>
              )}
            </button>
          </div>
        </div>


        {/* Past Meetings History Cards */}
        {meetings.length > 0 && (() => {
          const filteredMeetings = meetings.filter(m => {
            if (!historySearchQuery.trim()) return true;
            const q = historySearchQuery.toLowerCase();
            return (
              m.title?.toLowerCase().includes(q) ||
              m.meeting_date?.includes(q) ||
              (m.summary_vi && m.summary_vi.toLowerCase().includes(q)) ||
              (m.summary_ja && m.summary_ja.toLowerCase().includes(q)) ||
              (m.summary_markdown && m.summary_markdown.toLowerCase().includes(q))
            );
          });

          return (
            <div className="bg-slate-900/50 border border-slate-800 rounded-xl p-4 space-y-3">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-slate-800 pb-2.5">
                <div className="flex items-center gap-2">
                  <h3 className="text-xs font-bold text-slate-300 uppercase tracking-wider flex items-center gap-2">
                    <History className="w-4 h-4 text-emerald-400" /> Lịch sử các cuộc họp đã phân tích ({meetings.length})
                  </h3>
                  {historySearchQuery.trim() && (
                    <span className="text-[11px] px-2 py-0.5 rounded-full bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">
                      Khớp {filteredMeetings.length} / {meetings.length}
                    </span>
                  )}
                </div>

                <div className="flex items-center gap-2">
                  {/* Real-time Keyword Search Bar */}
                  <div className="relative">
                    <Search className="w-3.5 h-3.5 text-slate-400 absolute left-2.5 top-1/2 -translate-y-1/2" />
                    <input
                      type="text"
                      value={historySearchQuery}
                      onChange={(e) => setHistorySearchQuery(e.target.value)}
                      placeholder="Lọc theo từ khóa, ngày..."
                      className="w-48 sm:w-60 bg-slate-950 border border-slate-800 rounded-lg pl-8 pr-7 py-1 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-emerald-500 transition"
                    />
                    {historySearchQuery && (
                      <button
                        onClick={() => setHistorySearchQuery('')}
                        className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300 p-0.5"
                        title="Xóa tìm kiếm"
                      >
                        <X className="w-3 h-3" />
                      </button>
                    )}
                  </div>

                  <button
                    onClick={loadMeetings}
                    className="text-[11px] text-slate-400 hover:text-slate-200 flex items-center gap-1 transition cursor-pointer px-2 py-1 rounded hover:bg-slate-800"
                  >
                    <RefreshCw className="w-3 h-3" /> Làm mới
                  </button>

                  {meetings.length > 0 && (
                    <button
                      onClick={handleClearAllMeetings}
                      className="text-[11px] text-rose-400 hover:text-rose-300 bg-rose-500/10 hover:bg-rose-500/20 border border-rose-500/20 hover:border-rose-500/30 flex items-center gap-1 transition cursor-pointer px-2.5 py-1 rounded-lg shadow-xs"
                      title="Xóa toàn bộ lịch sử các cuộc họp"
                    >
                      <Trash2 className="w-3 h-3" /> Xóa tất cả
                    </button>
                  )}
                </div>
              </div>

              {filteredMeetings.length === 0 ? (
                <div className="p-6 text-center text-slate-400 text-xs bg-slate-950/40 rounded-lg border border-slate-800/50">
                  Không tìm thấy cuộc họp nào khớp với từ khóa "<span className="text-emerald-400 font-semibold">{historySearchQuery}</span>".
                </div>
              ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                  {filteredMeetings.slice(0, 12).map((m) => (
                    <div
                      key={m.id}
                      onClick={() => setCurrentResult(m)}
                      className="p-3 rounded-lg bg-slate-950/80 border border-slate-800/80 hover:border-emerald-500/40 cursor-pointer transition space-y-1.5 group relative shadow-xs"
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div className="font-semibold text-slate-200 text-xs group-hover:text-emerald-300 transition line-clamp-1 pr-6">
                          {m.title}
                        </div>
                        <div className="flex items-center gap-1.5 flex-shrink-0">
                          <button
                            onClick={(e) => handleDeleteMeeting(e, m.id, m.title)}
                            className="text-slate-600 hover:text-rose-400 p-1 rounded hover:bg-slate-900 transition"
                            title="Xóa biên bản này"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                          <ArrowRight className="w-3.5 h-3.5 text-slate-600 group-hover:text-emerald-400 transition" />
                        </div>
                      </div>
                      <div className="flex items-center justify-between text-[11px] text-slate-400">
                        <span className="flex items-center gap-1 font-mono text-slate-400">
                          <Calendar className="w-3 h-3 text-slate-500" /> {m.meeting_date}
                        </span>
                        <span className="text-emerald-400/90 font-medium">
                          {m.action_items?.length || 0} TODOs
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          );
        })()}
      </div>

      {/* Japanese Business Email Modal */}
      {showEmailModal && (
        <div className="fixed inset-0 z-50 bg-slate-950/80 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-700 rounded-xl shadow-2xl w-full max-w-2xl max-h-[85vh] flex flex-col overflow-hidden animate-fadeIn">
            {/* Modal Header */}
            <div className="p-4 border-b border-slate-800 flex items-center justify-between bg-slate-950/50">
              <div className="flex items-center gap-2">
                <div className="p-1 rounded bg-indigo-500/20 text-indigo-400 border border-indigo-500/30">
                  <Mail className="w-4 h-4" />
                </div>
                <div>
                  <h3 className="text-sm font-bold text-white">Mẫu Email gửi khách hàng tiếng Nhật (Keigo)</h3>
                  <p className="text-[11px] text-slate-400">Mẫu email thương mại chuẩn mực gửi khách hàng/đối tác Nhật Bản</p>
                </div>
              </div>
              <button
                onClick={() => setShowEmailModal(false)}
                className="text-slate-400 hover:text-white p-1 rounded hover:bg-slate-800 transition"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* Modal Body */}
            <div className="p-4 flex-1 overflow-y-auto space-y-3">
              <div className="text-[11px] text-slate-400 flex items-center justify-between">
                <span>Nội dung email xem trước (Có thể chỉnh sửa trực tiếp trước khi copy):</span>
                <span className="font-mono text-indigo-300">Format: 敬語 (Keigo)</span>
              </div>
              <textarea
                value={emailContent}
                onChange={(e) => setEmailContent(e.target.value)}
                rows={16}
                className="w-full bg-slate-950 border border-slate-800 rounded-lg p-3 text-xs text-slate-200 font-mono resize-none focus:outline-none focus:border-indigo-500 leading-relaxed"
              />
            </div>

            {/* Modal Footer */}
            <div className="p-3 border-t border-slate-800 flex items-center justify-between bg-slate-950/50">
              <span className="text-[11px] text-slate-400">
                1-click để copy và dán vào Outlook / Gmail
              </span>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => setShowEmailModal(false)}
                  className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs transition font-medium"
                >
                  Đóng
                </button>
                <button
                  type="button"
                  onClick={handleCopyEmail}
                  className="px-4 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold flex items-center gap-1.5 transition shadow cursor-pointer"
                >
                  {copiedEmail ? <Check className="w-3.5 h-3.5" /> : <Copy className="w-3.5 h-3.5" />}
                  <span>{copiedEmail ? 'Đã copy Email!' : 'Sao chép Email'}</span>
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
