import React, { useState, useEffect } from 'react';
import {
  FileText,
  FileSpreadsheet,
  Presentation,
  ArrowRightLeft,
  ArrowRight,
  Languages,
  Sparkles,
  ShieldCheck,
  Layers,
  X,
  CheckCircle2,
  Image as ImageIcon,
  Edit3,
  RotateCcw
} from 'lucide-react';
import { apiClient } from '../../api/client';
import { Project, ProviderInfo, GoogleFileItem } from '../../types';
import { ProviderModelSelector } from '../ProviderModelSelector';
import { useToast } from '../../context/ToastContext';
import { FileFormatIcon } from '../common/FileFormatIcon';
import { resolveHealthyModel } from '../../utils/aiPreferences';

interface GoogleTranslateConfigModalProps {
  file: GoogleFileItem;
  projects: Project[];
  activeProject: Project | null;
  providers: ProviderInfo[];
  accountId?: string | null;
  onClose: () => void;
  onStartJob: (jobData: any) => void;
}

export const GoogleTranslateConfigModal: React.FC<GoogleTranslateConfigModalProps> = ({
  file,
  projects,
  activeProject,
  providers,
  accountId,
  onClose,
  onStartJob
}) => {
  const toast = useToast();
  const [sourceLang, setSourceLang] = useState<string>('ja');
  const [targetLang, setTargetLang] = useState<string>('vi');
  const [selectedProjectId, setSelectedProjectId] = useState<string>(activeProject?.id || '');
  const [style, setStyle] = useState<string>('Auto');

  const initialAI = resolveHealthyModel(providers);
  const [selectedProvider, setSelectedProvider] = useState<string>(initialAI.provider);
  const [selectedModel, setSelectedModel] = useState<string>(initialAI.model);

  // Sheets specific
  const [availableSheets, setAvailableSheets] = useState<string[]>([]);
  const [selectedSheets, setSelectedSheets] = useState<string[]>([]);
  const [isLoadingMeta, setIsLoadingMeta] = useState<boolean>(false);

  // Slides specific
  const [translateNotes, setTranslateNotes] = useState<boolean>(true);

  // Image OCR specific (Hybrid Export)
  const [translateImages, setTranslateImages] = useState<boolean>(true);
  const [ocrEngine, setOcrEngine] = useState<'paddleocr' | 'gemini_vision'>('paddleocr');
  const [convertToGoogleFormat, setConvertToGoogleFormat] = useState<boolean>(true);

  const computeDefaultFilename = (originalName: string, tgtLang: string, convertToGoogle: boolean) => {
    const isGoogleFormat = ['doc', 'sheet', 'slide'].includes(file.type) || convertToGoogle;
    const lastDot = originalName.lastIndexOf('.');
    let stem = originalName;
    let ext = '';
    if (lastDot > 0) {
      stem = originalName.substring(0, lastDot);
      ext = originalName.substring(lastDot);
    }
    if (isGoogleFormat) {
      return `${stem}_${tgtLang.toUpperCase()}`;
    }
    return `${stem}_${tgtLang.toUpperCase()}${ext}`;
  };

  const [targetFilename, setTargetFilename] = useState<string>(() =>
    computeDefaultFilename(file.name, targetLang, convertToGoogleFormat)
  );
  const [isFilenameEdited, setIsFilenameEdited] = useState<boolean>(false);

  const [isStarting, setIsStarting] = useState<boolean>(false);

  useEffect(() => {
    // Load file metadata
    const loadMeta = async () => {
      setIsLoadingMeta(true);
      try {
        const meta = await apiClient.getGoogleFileMeta(file.id, file.type, accountId || undefined);
        if (meta.sheet_names && meta.sheet_names.length > 0) {
          setAvailableSheets(meta.sheet_names);
        }
      } catch (err) {
        console.warn('Could not fetch Google file metadata:', err);
      } finally {
        setIsLoadingMeta(false);
      }
    };

    loadMeta();
    const resolved = resolveHealthyModel(providers);
    setSelectedProvider(resolved.provider);
    setSelectedModel(resolved.model);
    setTargetFilename(computeDefaultFilename(file.name, targetLang, convertToGoogleFormat));
    setIsFilenameEdited(false);
  }, [file]);

  const handleSelectTargetLang = (newTgt: string) => {
    setTargetLang(newTgt);
    if (!isFilenameEdited) {
      setTargetFilename(computeDefaultFilename(file.name, newTgt, convertToGoogleFormat));
    }
  };

  const handleSwapLanguages = () => {
    const prevSrc = sourceLang;
    setSourceLang(targetLang);
    setTargetLang(prevSrc);
    if (!isFilenameEdited) {
      setTargetFilename(computeDefaultFilename(file.name, prevSrc, convertToGoogleFormat));
    }
  };

  const toggleSheetSelection = (sheetName: string) => {
    if (selectedSheets.includes(sheetName)) {
      setSelectedSheets(selectedSheets.filter(s => s !== sheetName));
    } else {
      setSelectedSheets([...selectedSheets, sheetName]);
    }
  };

  const handleStart = async () => {
    if (sourceLang === targetLang) {
      toast.error('Ngôn ngữ nguồn và ngôn ngữ đích không được trùng nhau.');
      return;
    }

    setIsStarting(true);
    try {
      const res = await apiClient.startGoogleTranslation({
        file_id: file.id,
        file_type: file.type,
        title: file.name,
        target_filename: targetFilename.trim() || undefined,
        source_language: sourceLang,
        target_language: targetLang,
        project_id: selectedProjectId || null,
        style,
        provider: selectedProvider,
        model: selectedModel,
        selected_sheets: selectedSheets.length > 0 ? selectedSheets : null,
        translate_notes: translateNotes,
        translate_images: translateImages,
        ocr_mode: ocrEngine,
        convert_to_google_format: convertToGoogleFormat,
        parent_folder_id: file.parents?.[0] || null,
        account_id: accountId || null
      });

      toast.success(res.message || 'Đã khởi tạo tác vụ dịch Google Workspace');
      onStartJob(res);
      onClose();
    } catch (err: any) {
      toast.error(err.response?.data?.detail || 'Không thể bắt đầu dịch file Google.');
    } finally {
      setIsStarting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/75 backdrop-blur-sm flex items-center justify-center p-4">
      <div className="bg-slate-900 border border-slate-700/80 rounded-2xl w-full max-w-2xl overflow-hidden shadow-2xl flex flex-col max-h-[90vh]">
        {/* Header */}
        <div className="px-6 py-4 border-b border-slate-800 flex items-center justify-between bg-slate-850">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-slate-800/90 border border-slate-700/60 flex items-center justify-center shadow-inner flex-shrink-0">
              <FileFormatIcon type={file.type} name={file.name} mimeType={file.mimeType} size="md" />
            </div>
            <div>
              <h3 className="text-sm font-semibold text-white truncate max-w-md" title={file.name}>
                Cấu hình Dịch Google {file.type.toUpperCase()}: {file.name}
              </h3>
              <p className="text-xs text-slate-400">
                Thao tác trực tiếp qua Google REST API · Tạo bản sao an toàn trên Google Drive
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Modal Body */}
        <div className="p-6 overflow-y-auto space-y-5 text-xs">
          {/* Language Pair Selector */}
          <div className="p-3.5 bg-slate-850 rounded-xl border border-slate-700/80 space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-slate-300 font-semibold flex items-center gap-1.5 text-xs">
                <Languages className="w-4 h-4 text-sky-400" />
                Cặp ngôn ngữ dịch thuật (Language Pair)
              </span>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-[1fr,auto,1fr] gap-2 items-center">
              {/* Source Language */}
              <div>
                <label className="block text-[11px] text-slate-400 font-medium mb-1">
                  Ngôn ngữ nguồn (Source)
                </label>
                <div className="grid grid-cols-3 gap-1.5">
                  {[
                    { id: 'ja', label: '🇯🇵 Nhật' },
                    { id: 'vi', label: '🇻🇳 Việt' },
                    { id: 'en', label: '🇬🇧 Anh' }
                  ].map((lang) => {
                    const isSelected = sourceLang === lang.id;
                    return (
                      <button
                        key={lang.id}
                        type="button"
                        onClick={() => {
                          setSourceLang(lang.id);
                          if (targetLang === lang.id) {
                            setTargetLang(lang.id === 'vi' ? 'ja' : 'vi');
                          }
                        }}
                        className={`p-2 rounded-lg border text-center transition-all text-xs ${
                          isSelected
                            ? 'bg-sky-600/30 border-sky-500 text-white font-semibold shadow-sm'
                            : 'bg-slate-800/60 border-slate-700/80 text-slate-300 hover:bg-slate-800 hover:text-white'
                        }`}
                      >
                        {lang.label}
                      </button>
                    );
                  })}
                </div>
              </div>

              {/* Swap Button */}
              <div className="flex items-center justify-center pt-5">
                <button
                  type="button"
                  onClick={handleSwapLanguages}
                  title="Đảo ngược cặp ngôn ngữ"
                  className="p-2 rounded-lg bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-300 hover:text-sky-400 transition-all active:scale-95 shadow-sm"
                >
                  <ArrowRightLeft className="w-4 h-4" />
                </button>
              </div>

              {/* Target Language */}
              <div>
                <label className="block text-[11px] text-slate-400 font-medium mb-1">
                  Ngôn ngữ đích (Target)
                </label>
                <div className="grid grid-cols-3 gap-1.5">
                  {[
                    { id: 'vi', label: '🇻🇳 Việt' },
                    { id: 'ja', label: '🇯🇵 Nhật' },
                    { id: 'en', label: '🇬🇧 Anh' }
                  ].map((lang) => (
                    <button
                      key={lang.id}
                      type="button"
                      onClick={() => {
                        handleSelectTargetLang(lang.id);
                        if (sourceLang === lang.id) {
                          setSourceLang(lang.id === 'vi' ? 'ja' : 'vi');
                        }
                      }}
                      className={`p-2 rounded-lg border text-center transition-all text-xs ${
                        targetLang === lang.id
                          ? 'bg-emerald-600/30 border-emerald-500 text-white font-semibold shadow-sm'
                          : 'bg-slate-800/60 border-slate-700/80 text-slate-300 hover:bg-slate-800 hover:text-white'
                      }`}
                    >
                      {lang.label}
                    </button>
                  ))}
                </div>
              </div>
            </div>

            {/* Translation Direction Banner */}
            <div className="flex items-center justify-center gap-2 py-1.5 px-3 bg-slate-900/80 rounded-lg border border-slate-800 text-[11px] text-slate-300">
              <span className="font-semibold text-sky-400 uppercase font-mono">
                {sourceLang}
              </span>
              <ArrowRight className="w-3.5 h-3.5 text-slate-500" />
              <span className="font-semibold text-emerald-400 uppercase font-mono">
                {targetLang}
              </span>
              <span className="text-slate-400 text-[11px] ml-1">
                (Dịch từ {sourceLang === 'vi' ? 'Tiếng Việt' : sourceLang === 'ja' ? 'Tiếng Nhật' : 'English'} sang {targetLang === 'vi' ? 'Tiếng Việt' : targetLang === 'ja' ? 'Tiếng Nhật' : 'English'})
              </span>
            </div>
          </div>

          {/* Project Workspace (Glossary & Memory Injection) */}
          <div>
            <label className="block text-slate-300 font-medium mb-1.5">
              Dự án / Không gian làm việc (Project Workspace)
            </label>
            <select
              value={selectedProjectId}
              onChange={(e) => setSelectedProjectId(e.target.value)}
              className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-sky-500"
            >
              <option value="">-- Dịch chung (Không áp dụng quy tắc dự án) --</option>
              {projects.map((p) => (
                <option key={p.id} value={p.id}>
                  📁 {p.name} ({p.code})
                </option>
              ))}
            </select>
            <p className="text-[11px] text-slate-500 mt-1">
              Tự động áp dụng từ điển thuật ngữ bắt buộc (Glossary), bộ nhớ dịch (TM) và quy tắc dịch của khách hàng.
            </p>
          </div>

          {/* Tone & Communication Style */}
          <div>
            <label className="block text-slate-300 font-medium mb-1.5">
              Văn phong & Phong cách dịch (Tone / Style)
            </label>
            <div className="grid grid-cols-4 gap-2">
              {['Auto', 'Polite', 'Formal', 'Technical'].map((s) => (
                <button
                  key={s}
                  type="button"
                  onClick={() => setStyle(s)}
                  className={`py-2 rounded-lg border text-center transition-all ${
                    style === s
                      ? 'bg-sky-600/30 border-sky-500 text-white font-semibold shadow-sm'
                      : 'bg-slate-800/60 border-slate-700 text-slate-400 hover:text-slate-200 hover:bg-slate-800'
                  }`}
                >
                  {s}
                </button>
              ))}
            </div>
          </div>

          {/* AI Provider & Model Selector */}
          <div className="pt-1">
            <ProviderModelSelector
              providers={providers}
              selectedProvider={selectedProvider}
              onChangeProvider={setSelectedProvider}
              selectedModel={selectedModel}
              onChangeModel={setSelectedModel}
              allowAutoRouter={false}
              layout="stacked"
            />
          </div>

          {/* File-specific options: Google Sheets */}
          {file.type === 'sheet' && (
            <div className="p-4 bg-emerald-500/10 border border-emerald-500/25 rounded-xl space-y-3">
              <div className="flex items-center gap-2 text-emerald-300 font-semibold text-xs">
                <ShieldCheck className="w-4 h-4 text-emerald-400" />
                <span>Bảo vệ 100% công thức Google Sheets (=VLOOKUP, =SUM, =IF,...)</span>
              </div>
              <p className="text-[11px] text-emerald-400/80 leading-relaxed">
                Hệ thống tự động bỏ qua toàn bộ ô chứa công thức tính toán và số liệu thuần túy, chỉ dịch các ô văn bản và cập nhật trực tiếp vào bản sao mới.
              </p>

              {availableSheets.length > 0 && (
                <div className="pt-2 border-t border-emerald-500/20">
                  <span className="block text-slate-300 font-medium mb-1.5">
                    Chọn Sheet / Tab cần dịch (mặc định: dịch toàn bộ file):
                  </span>
                  <div className="flex flex-wrap gap-2">
                    {availableSheets.map((sh) => {
                      const isSelected = selectedSheets.includes(sh);
                      return (
                        <button
                          key={sh}
                          type="button"
                          onClick={() => toggleSheetSelection(sh)}
                          className={`px-3 py-1 rounded-lg border text-xs flex items-center gap-1.5 transition-all ${
                            isSelected
                              ? 'bg-emerald-600/30 border-emerald-500 text-white font-medium'
                              : 'bg-slate-800/80 border-slate-700 text-slate-400 hover:text-slate-200'
                          }`}
                        >
                          <Layers className="w-3 h-3" />
                          <span>{sh}</span>
                          {isSelected && <CheckCircle2 className="w-3 h-3 text-emerald-400" />}
                        </button>
                      );
                    })}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* File-specific options: Google Slides */}
          {file.type === 'slide' && (
            <div className="p-3.5 bg-amber-500/10 border border-amber-500/25 rounded-xl space-y-2">
              <label className="flex items-start gap-2.5 cursor-pointer">
                <input
                  type="checkbox"
                  checked={translateNotes}
                  onChange={(e) => setTranslateNotes(e.target.checked)}
                  className="mt-0.5 rounded border-slate-700 text-amber-500 focus:ring-amber-400"
                />
                <div>
                  <span className="text-amber-200 font-medium text-xs">
                    Dịch cả ghi chú diễn giả (Speaker Notes)
                  </span>
                  <p className="text-[11px] text-amber-300/70 mt-0.5">
                    Trích xuất và dịch toàn bộ nội dung trong phần Speaker Notes của từng slide.
                  </p>
                </div>
              </label>
            </div>
          )}

          {/* OCR Image Translation (Hybrid Export Option) */}
          <div className="p-3.5 bg-slate-850 rounded-xl border border-slate-700/80 space-y-2.5">
            <label className="flex items-start gap-2.5 cursor-pointer">
              <input
                type="checkbox"
                checked={translateImages}
                onChange={(e) => setTranslateImages(e.target.checked)}
                className="mt-0.5 rounded border-slate-700 text-sky-500 focus:ring-sky-400"
              />
              <div className="flex-1">
                <div className="flex items-center gap-2">
                  <span className="text-slate-200 font-semibold text-xs flex items-center gap-1.5">
                    <ImageIcon className="w-3.5 h-3.5 text-sky-400" />
                    <span>Dịch chữ trong hình ảnh (AI Vision & Local Inpainting)</span>
                  </span>
                  <span className="text-[10px] font-semibold px-1.5 py-0.2 rounded bg-sky-500/20 text-sky-300 border border-sky-500/30">
                    BETA
                  </span>
                </div>
                <p className="text-[11px] text-slate-400 mt-0.5 leading-relaxed">
                  Tự động trích xuất sơ đồ, screenshot, quét chữ bằng OCR, xóa chữ cũ và vẽ chữ dịch mới trực tiếp lên ảnh.
                </p>

                {translateImages && (
                  <div className="mt-3 pt-2.5 border-t border-slate-700/60 flex flex-col gap-2">
                    <span className="text-[10px] uppercase tracking-wider font-semibold text-slate-400">
                      Công nghệ OCR bóc tách chữ trong ảnh:
                    </span>
                    <div className="grid grid-cols-2 gap-2">
                      <button
                        type="button"
                        onClick={(e) => { e.preventDefault(); setOcrEngine('paddleocr'); }}
                        className={`p-2 rounded-lg text-left border transition-all ${
                          ocrEngine === 'paddleocr'
                            ? 'bg-sky-500/20 border-sky-500 text-white font-medium shadow-sm'
                            : 'bg-slate-800 border-slate-700 text-slate-400 hover:text-slate-200'
                        }`}
                      >
                        <div className="font-semibold text-sky-300 text-xs flex items-center gap-1">
                          <span>⚡ PaddleOCR (Local)</span>
                        </div>
                        <div className="text-[10px] text-slate-400 mt-0.5">Offline · Miễn phí · Chuẩn tiếng Nhật/Việt</div>
                      </button>

                      <button
                        type="button"
                        onClick={(e) => { e.preventDefault(); setOcrEngine('gemini_vision'); }}
                        className={`p-2 rounded-lg text-left border transition-all ${
                          ocrEngine === 'gemini_vision'
                            ? 'bg-sky-500/20 border-sky-500 text-white font-medium shadow-sm'
                            : 'bg-slate-800 border-slate-700 text-slate-400 hover:text-slate-200'
                        }`}
                      >
                        <div className="font-semibold text-slate-200 text-xs flex items-center gap-1">
                          <span>☁️ Gemini Vision</span>
                        </div>
                        <div className="text-[10px] text-slate-400 mt-0.5">Cloud Multi-modal API</div>
                      </button>
                    </div>

                    <div className="mt-1 pt-2 border-t border-slate-700/40">
                      <label className="flex items-center gap-2 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={convertToGoogleFormat}
                          onChange={(e) => {
                            const val = e.target.checked;
                            setConvertToGoogleFormat(val);
                            if (!isFilenameEdited) {
                              setTargetFilename(computeDefaultFilename(file.name, targetLang, val));
                            }
                          }}
                          className="rounded border-slate-700 text-sky-500 focus:ring-sky-400"
                        />
                        <span className="text-[11px] text-slate-300">
                          Tự động chuyển đổi bản sao đã dịch thành định dạng Google Docs/Slides nguyên bản
                        </span>
                      </label>
                    </div>
                  </div>
                )}
              </div>
            </label>
          </div>

          {/* Output Filename Card (Customizable) */}
          <div className="p-3.5 bg-slate-850 rounded-xl border border-slate-700/80 space-y-2.5">
            <div className="flex items-center justify-between">
              <label className="text-xs font-semibold text-slate-300 flex items-center gap-1.5">
                <Edit3 className="w-3.5 h-3.5 text-sky-400" />
                <span>Tên tệp bản sao trên Google Drive (Output Filename)</span>
              </label>
              {isFilenameEdited && (
                <button
                  type="button"
                  onClick={() => {
                    setTargetFilename(computeDefaultFilename(file.name, targetLang, convertToGoogleFormat));
                    setIsFilenameEdited(false);
                  }}
                  className="text-[10px] text-sky-400 hover:text-sky-300 hover:underline flex items-center gap-1 font-medium transition-colors"
                  title="Khôi phục lại tên gợi ý ban đầu"
                >
                  <RotateCcw className="w-3 h-3" />
                  <span>Đặt lại mặc định</span>
                </button>
              )}
            </div>
            <div className="relative">
              <input
                type="text"
                value={targetFilename}
                onChange={(e) => {
                  setTargetFilename(e.target.value);
                  setIsFilenameEdited(true);
                }}
                placeholder={`Gợi ý: ${computeDefaultFilename(file.name, targetLang, convertToGoogleFormat)}`}
                className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-sky-500 font-mono shadow-inner"
              />
            </div>
            <p className="text-[10px] text-slate-400">
              Mặc định sẽ gắn mã ngôn ngữ <code className="text-sky-300 bg-slate-800 px-1 py-0.5 rounded font-mono">_{targetLang.toUpperCase()}</code> vào tên tệp gốc để tạo bản sao an toàn, không ghi đè tệp gốc của bạn.
            </p>
          </div>
        </div>

        {/* Footer */}
        <div className="px-6 py-4 border-t border-slate-800 bg-slate-850 flex items-center justify-end gap-3">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-medium transition-colors"
          >
            Hủy
          </button>
          <button
            type="button"
            onClick={handleStart}
            disabled={isStarting}
            className="px-5 py-2 rounded-lg bg-sky-600 hover:bg-sky-500 text-white text-xs font-medium flex items-center gap-2 shadow-lg shadow-sky-600/20 transition-all disabled:opacity-50"
          >
            <Sparkles className="w-4 h-4" />
            <span>{isStarting ? 'Đang khởi tạo...' : 'Bắt đầu Dịch (REST API)'}</span>
          </button>
        </div>
      </div>
    </div>
  );
};
