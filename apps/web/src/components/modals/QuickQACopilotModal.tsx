import React, { useState, useEffect } from 'react';
import {
  Sparkles,
  ShieldCheck,
  CheckCircle2,
  AlertTriangle,
  Copy,
  Check,
  Download,
  Upload,
  RefreshCw,
  Trash2,
  Eye,
  Send,
  MessageSquare,
  FileSpreadsheet,
  FileText,
  Mail,
  HelpCircle,
  X,
  Bug,
  ListCheck,
  Compass,
  Database,
  ArrowRight,
  BookmarkPlus
} from 'lucide-react';
import { Project, ProviderInfo } from '../../types';
import { apiClient } from '../../api/client';
import { useToast } from '../../context/ToastContext';
import { ProviderModelSelector } from '../ProviderModelSelector';
import { Button } from '../ui/Button';
import { Badge } from '../ui/Badge';

interface QuickQACopilotModalProps {
  isOpen: boolean;
  onClose: () => void;
  activeProject: Project | null;
  projects?: Project[];
  initialMode?: string;
}

export const QuickQACopilotModal: React.FC<QuickQACopilotModalProps> = ({
  isOpen,
  onClose,
  activeProject,
  projects = [],
  initialMode = 'test_case_polish'
}) => {
  const toast = useToast();

  // Mode Selection
  const [mode, setMode] = useState<string>(initialMode);
  const [inputText, setInputText] = useState<string>('');
  const [customInstruction, setCustomInstruction] = useState<string>('');
  const [isAutoHarvest, setIsAutoHarvest] = useState<boolean>(false);

  // AI Provider & Model
  const [providers, setProviders] = useState<ProviderInfo[]>([]);
  const [selectedProvider, setSelectedProvider] = useState<string>('auto');
  const [selectedModel, setSelectedModel] = useState<string>('');
  const [analyzing, setAnalyzing] = useState<boolean>(false);

  // Analysis Result
  const [result, setResult] = useState<any | null>(null);
  const [copied, setCopied] = useState<boolean>(false);
  const [saving, setSaving] = useState<boolean>(false);
  const [savedSuccess, setSavedSuccess] = useState<boolean>(false);

  useEffect(() => {
    if (isOpen) {
      loadProviders();
      setSavedSuccess(false);
    }
  }, [isOpen]);

  const loadProviders = async () => {
    try {
      const provs = await apiClient.getProviders();
      setProviders(provs);
    } catch (e) {
      console.error('Failed to load providers', e);
    }
  };

  const MODES = [
    {
      id: 'test_case_polish',
      label: '✍️ Chuốt Test Case',
      desc: 'Biến ý tưởng thô thành test case chuẩn + gợi ý góc khuất',
      badgeColor: 'border-blue-500 text-blue-500 bg-blue-500/10',
      placeholder: 'Ví dụ ý tưởng thô:\n- Test thử trường hợp user ấn nút thanh toán 2 lần liên tiếp thật nhanh xem có bị trừ tiền 2 lần ko\n- Hoặc: Thử nhập email có dấu cách ở đầu và cuối xem hệ thống có tự trim ko'
    },
    {
      id: 'bug_draft',
      label: '🐞 Báo cáo Bug & RCA',
      desc: 'Từ câu báo lỗi/log ➔ Báo cáo 5 phần + Thư trả lời khách',
      badgeColor: 'border-rose-500 text-rose-500 bg-rose-500/10',
      placeholder: 'Ví dụ câu chat báo lỗi hoặc log:\n- Khách báo bản prod bị văng lỗi khi import file CSV to. Log có dòng: OutOfMemoryError: Java heap space\n- Hoặc: Màn hình login ấn Quên mật khẩu nó đơ quay vòng vòng, console báo 500'
    },
    {
      id: 'dev_inquiry',
      label: '💬 Dev hỏi ➔ Q&A 5W1H',
      desc: 'Biến thắc mắc của Dev thành phiếu Q&A có đề xuất A/B',
      badgeColor: 'border-amber-500 text-amber-500 bg-amber-500/10',
      placeholder: 'Ví dụ câu hỏi thô của dev:\n- Dev hỏi: Nút Hủy đơn hàng, nếu đã giao bên vận chuyển thì có cho hủy ko anh? Bấm hủy thì hoàn tiền ngay hay chờ admin duyệt? Spec không thấy ghi gì.'
    },
    {
      id: 'spec_ambiguity',
      label: '🔍 Săn bẫy Spec',
      desc: 'Bắt các từ ngầm hiểu nguy hiểm: 適宜, よしなに, 等...',
      badgeColor: 'border-purple-500 text-purple-500 bg-purple-500/10',
      placeholder: 'Dán đoạn đặc tả tiếng Nhật của khách chứa các từ như:\n- エラー時は適宜メッセージを表示し、速やかに前画面に戻る。\n- CSVインポート対象項目は氏名、住所、電話番号等とする。'
    },
    {
      id: 'japan_test_data',
      label: '🗾 Dữ liệu Test Nhật',
      desc: 'Tạo dữ liệu mẫu: Kanji, Furigana, Mã bưu điện, Zenkaku/Hankaku',
      badgeColor: 'border-emerald-500 text-emerald-500 bg-emerald-500/10',
      placeholder: 'Nhập ngữ cảnh form cần test (hoặc để trống để lấy dữ liệu Nhật chuẩn chung):\n- Form đăng ký thông tin cá nhân và địa chỉ giao hàng tại Nhật Bản'
    },
    {
      id: 'quick_checklist',
      label: '✅ Checklist Nhanh',
      desc: 'Bảng kiểm tra 5-8 bước test nhanh trước khi release',
      badgeColor: 'border-indigo-500 text-indigo-500 bg-indigo-500/10',
      placeholder: 'Mô tả thay đổi nhỏ hoặc tính năng ngắn:\n- Thêm nút Xuất file CSV báo cáo tháng và hiển thị ngày xác nhận trên danh sách đơn hàng'
    }
  ];

  const currentModeInfo = MODES.find((m) => m.id === mode) || MODES[0];

  const handleAnalyze = async () => {
    if (!inputText.trim() && mode !== 'japan_test_data') {
      toast.warning('Chưa có nội dung', 'Vui lòng nhập ý tưởng, đoạn chat hoặc spec cần phân tích.');
      return;
    }

    setAnalyzing(true);
    setResult(null);
    setSavedSuccess(false);

    try {
      const res = await apiClient.quickQAAnalyze({
        project_id: activeProject?.id || '',
        spec_text: inputText.trim() || 'General Japanese profile and address form',
        mode: mode,
        custom_instruction: customInstruction.trim(),
        is_auto_harvest: isAutoHarvest,
        preferred_provider: selectedProvider,
        model: selectedModel || undefined
      });
      setResult(res);
      toast.success('Phân tích thành công!', 'Kết quả đã được chuẩn hóa theo chuẩn QA Nhật Bản.');
    } catch (err: any) {
      toast.error('Lỗi phân tích', err?.message || 'Không thể xử lý yêu cầu. Vui lòng thử lại.');
    } finally {
      setAnalyzing(false);
    }
  };

  const handleCopyResult = async () => {
    if (!result) return;
    const textToCopy =
      result.formatted_markdown ||
      result.bilingual_markdown ||
      JSON.stringify(result, null, 2);

    try {
      await navigator.clipboard.writeText(textToCopy);
      setCopied(true);
      toast.success('Đã sao chép kết quả!', 'Sẵn sàng dán vào Slack, Chatwork hoặc Excel.');
      setTimeout(() => setCopied(false), 2500);
    } catch (e) {
      toast.error('Lỗi sao chép', 'Không thể ghi vào clipboard.');
    }
  };

  const handleSaveToWorkspace = async () => {
    if (!activeProject || !result) return;
    setSaving(true);
    try {
      let itemType: 'test_case' | 'bug' | 'question' = 'test_case';
      let title = '';
      let desc = '';
      let steps: any[] = [];

      if (mode === 'test_case_polish') {
        itemType = 'test_case';
        title = result.title_ja || result.title_vi || 'Polished Test Case';
        desc = result.purpose_ja || result.purpose_vi || '';
        steps = result.steps || [];
      } else if (mode === 'bug_draft') {
        itemType = 'bug';
        title = result.bug_title_ja || result.bug_title_vi || 'Defect Report';
        desc = `【発生事象】: ${result.actual_behavior}\n【期待結果】: ${result.expected_behavior}\n【一次原因】: ${result.preliminary_cause}`;
      } else {
        itemType = 'question';
        title = result.inquiry_title_vi || result.inquiry_title_ja || 'Q&A Confirmation';
        desc = result.confirmation_question || result.issue_point || '';
      }

      await apiClient.quickQASave({
        project_id: activeProject.id,
        item_type: itemType,
        title: title,
        description: desc,
        steps: steps,
        priority: 'MEDIUM'
      });

      setSavedSuccess(true);
      toast.success('Đã lưu vào QA Workspace!', 'Bản ghi đã được đưa vào hệ thống QA chính thức của dự án.');
    } catch (err: any) {
      toast.error('Lỗi khi lưu', err?.message || 'Không thể lưu vào QA Workspace.');
    } finally {
      setSaving(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-6 overflow-y-auto bg-black/60 backdrop-blur-sm animate-in fade-in duration-200">
      <div
        className="relative flex flex-col w-full max-w-5xl max-h-[92vh] bg-surface border border-border rounded-2xl shadow-2xl overflow-hidden text-primary"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-border bg-subtle/50">
          <div className="flex items-center gap-3">
            <div className="p-2.5 rounded-xl bg-purple-500/10 text-purple-500 border border-purple-500/20">
              <Sparkles className="w-6 h-6" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-xl font-bold tracking-tight">Quick QA Studio (Kiểm Thử & Soi Spec Nhanh)</h2>
                {activeProject && (
                  <Badge variant="outline" className="text-xs font-semibold px-2.5 py-0.5 border-purple-500/30 text-purple-500 bg-purple-500/5">
                    {activeProject.name}
                  </Badge>
                )}
              </div>
              <p className="text-xs text-muted-foreground mt-0.5">
                Biến ý tưởng thô sơ, câu chat cộc lốc hoặc log lỗi thành tài liệu QA chuẩn mực Nhật Bản
              </p>
            </div>
          </div>

          <button
            onClick={onClose}
            className="p-2 text-muted-foreground hover:text-primary hover:bg-subtle rounded-xl transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* 6 Modes Presets Bar */}
        <div className="px-6 py-3 border-b border-border bg-canvas overflow-x-auto">
          <div className="flex items-center gap-2 min-w-max">
            {MODES.map((m) => (
              <button
                key={m.id}
                type="button"
                onClick={() => {
                  setMode(m.id);
                  setResult(null);
                }}
                className={`px-3 py-2 text-xs font-semibold rounded-xl border transition-all flex items-center gap-1.5 ${
                  mode === m.id
                    ? `${m.badgeColor} shadow-xs ring-1 ring-purple-500/30`
                    : 'border-border bg-surface text-muted-foreground hover:border-border-hover hover:text-primary'
                }`}
              >
                <span>{m.label}</span>
              </button>
            ))}
          </div>
        </div>

        {/* Body Content */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
            {/* LEFT: Input Area (6 cols) */}
            <div className="lg:col-span-6 space-y-4">
              <div className="p-4 rounded-xl bg-canvas border border-border space-y-3">
                <div className="flex items-center justify-between">
                  <label className="text-xs font-bold text-primary flex items-center gap-1.5">
                    <span>{currentModeInfo.label}</span>
                  </label>
                  <span className="text-[11px] text-muted-foreground italic">{currentModeInfo.desc}</span>
                </div>

                <textarea
                  rows={8}
                  value={inputText}
                  onChange={(e) => setInputText(e.target.value)}
                  placeholder={currentModeInfo.placeholder}
                  className="w-full p-3 text-xs rounded-xl border border-border bg-surface text-primary focus:outline-none focus:ring-1 focus:ring-purple-500 font-mono leading-relaxed resize-y"
                />

                {/* Custom Instruction Box */}
                <div>
                  <label className="text-[11px] font-semibold text-muted-foreground block mb-1">
                    💡 Ý muốn của bạn (Prompt chỉ đạo riêng):
                  </label>
                  <input
                    type="text"
                    value={customInstruction}
                    onChange={(e) => setCustomInstruction(e.target.value)}
                    placeholder="Ví dụ: Tập trung vào bảo mật và phân quyền admin, viết thật ngắn gọn..."
                    className="w-full px-3 py-2 text-xs rounded-lg border border-border bg-surface text-primary focus:outline-none focus:ring-1 focus:ring-purple-500"
                  />
                </div>

                {/* Auto-Harvest Toggle */}
                <div className="flex items-center justify-between pt-2 border-t border-border/60">
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-semibold text-primary">Tra cứu ngữ cảnh dự án (Auto-Harvest)</span>
                    {isAutoHarvest ? (
                      <Badge variant="outline" className="text-[10px] px-2 py-0.5 border-emerald-500/30 text-emerald-500 bg-emerald-500/10">
                        BẬT (Đối chiếu Spec/Decisions)
                      </Badge>
                    ) : (
                      <Badge variant="outline" className="text-[10px] px-2 py-0.5 border-muted text-muted-foreground bg-muted/10">
                        TẮT (Tập trung ý bạn)
                      </Badge>
                    )}
                  </div>

                  <button
                    type="button"
                    onClick={() => setIsAutoHarvest(!isAutoHarvest)}
                    className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors focus:outline-none ${
                      isAutoHarvest ? 'bg-purple-600' : 'bg-muted'
                    }`}
                  >
                    <span
                      className={`inline-block h-3.5 w-3.5 transform rounded-full bg-white transition-transform ${
                        isAutoHarvest ? 'translate-x-4' : 'translate-x-1'
                      }`}
                    />
                  </button>
                </div>
              </div>

              {/* Provider & Action */}
              <div className="p-4 rounded-xl bg-canvas border border-border flex flex-col sm:flex-row items-center justify-between gap-3">
                <div className="w-full sm:w-auto">
                  <ProviderModelSelector
                    providers={providers}
                    selectedProvider={selectedProvider}
                    selectedModel={selectedModel}
                    onChangeProvider={setSelectedProvider}
                    onChangeModel={setSelectedModel}
                  />
                </div>

                <Button
                  type="button"
                  onClick={handleAnalyze}
                  disabled={analyzing}
                  className="w-full sm:w-auto px-5 py-2.5 bg-purple-600 hover:bg-purple-700 text-white font-semibold text-xs shadow-md shadow-purple-500/20 flex items-center justify-center gap-2"
                >
                  {analyzing ? (
                    <>
                      <RefreshCw className="w-4 h-4 animate-spin" />
                      Đang phân tích & chuốt...
                    </>
                  ) : (
                    <>
                      <Sparkles className="w-4 h-4" />
                      Phân Tích & Chuẩn Hóa
                    </>
                  )}
                </Button>
              </div>
            </div>

            {/* RIGHT: Results Area (6 cols) */}
            <div className="lg:col-span-6 flex flex-col h-full space-y-4">
              {result ? (
                <div className="flex-1 flex flex-col rounded-xl border border-border bg-canvas overflow-hidden">
                  {/* Results Action Bar */}
                  <div className="flex items-center justify-between px-4 py-2.5 border-b border-border bg-subtle/50">
                    <span className="text-xs font-bold text-primary flex items-center gap-1.5">
                      <CheckCircle2 className="w-4 h-4 text-emerald-500" />
                      Kết quả đã chuẩn hóa
                    </span>

                    <div className="flex items-center gap-2">
                      <button
                        type="button"
                        onClick={handleCopyResult}
                        className="px-2.5 py-1 text-xs font-semibold rounded-lg bg-purple-500/10 text-purple-500 hover:bg-purple-500/20 border border-purple-500/20 flex items-center gap-1 transition-all"
                      >
                        {copied ? <Check className="w-3.5 h-3.5" /> : <Copy className="w-3.5 h-3.5" />}
                        Copy
                      </button>

                      {activeProject && (
                        <button
                          type="button"
                          onClick={handleSaveToWorkspace}
                          disabled={saving || savedSuccess}
                          className={`px-2.5 py-1 text-xs font-semibold rounded-lg border flex items-center gap-1 transition-all ${
                            savedSuccess
                              ? 'bg-emerald-500/10 text-emerald-500 border-emerald-500/30'
                              : 'bg-subtle text-primary hover:bg-subtle/80 border-border'
                          }`}
                        >
                          <BookmarkPlus className="w-3.5 h-3.5" />
                          {savedSuccess ? 'Đã Lưu' : saving ? 'Đang lưu...' : 'Lưu vào QA'}
                        </button>
                      )}
                    </div>
                  </div>

                  {/* Render Custom Views based on Mode */}
                  <div className="flex-1 p-4 overflow-y-auto max-h-[480px] space-y-3.5 text-xs font-sans leading-relaxed bg-surface/50">
                    {/* MODE 1: Test Case Polish Result */}
                    {mode === 'test_case_polish' && (
                      <div className="space-y-3">
                        <div className="p-3 rounded-xl bg-canvas border border-border space-y-2">
                          <div className="flex items-center justify-between">
                            <span className="font-bold text-sm text-primary">{result.title_ja}</span>
                            <Badge variant="outline" className="text-[10px] text-blue-500 border-blue-500/30">
                              {result.case_type}
                            </Badge>
                          </div>
                          <p className="text-xs text-muted-foreground">{result.title_vi}</p>

                          <div className="pt-2 border-t border-border/50">
                            <span className="text-[11px] font-bold text-blue-600 dark:text-blue-400 block mb-1">
                              🎯 Mục đích kiểm thử (テスト目的):
                            </span>
                            <p className="text-xs text-primary">{result.purpose_ja}</p>
                            <p className="text-[11px] text-muted-foreground mt-0.5">{result.purpose_vi}</p>
                          </div>

                          <div className="pt-2 border-t border-border/50">
                            <span className="text-[11px] font-bold text-muted-foreground block mb-1">
                              📌 Tiền điều kiện (前提条件):
                            </span>
                            <ul className="list-disc pl-4 space-y-0.5 text-xs text-muted-foreground">
                              {(result.preconditions_ja || []).map((p: string, i: number) => (
                                <li key={i}>{p}</li>
                              ))}
                            </ul>
                          </div>

                          <div className="pt-2 border-t border-border/50">
                            <span className="text-[11px] font-bold text-muted-foreground block mb-1.5">
                              📋 Các bước thao tác (手順) & Kết quả kỳ vọng (期待値):
                            </span>
                            <div className="space-y-2">
                              {(result.steps || []).map((st: any, i: number) => (
                                <div key={i} className="p-2 rounded-lg bg-surface border border-border/60">
                                  <div className="font-semibold text-primary">
                                    Bước {st.step_order}: {st.action_ja}
                                  </div>
                                  <div className="text-[11px] text-muted-foreground mt-0.5">{st.action_vi}</div>
                                  <div className="mt-1 text-emerald-600 dark:text-emerald-400 font-medium">
                                    ➔ Kỳ vọng: {st.expected_ja}
                                  </div>
                                </div>
                              ))}
                            </div>
                          </div>
                        </div>

                        {/* Edge Cases Card */}
                        {result.edge_case_tips?.length > 0 && (
                          <div className="p-3.5 rounded-xl bg-amber-500/5 border border-amber-500/20 text-xs space-y-1.5">
                            <span className="font-bold text-amber-600 dark:text-amber-400 flex items-center gap-1.5">
                              <AlertTriangle className="w-4 h-4" />
                              Gợi ý góc khuất / Trường hợp biên (Edge Cases):
                            </span>
                            <ul className="list-disc pl-4 space-y-1 text-muted-foreground">
                              {result.edge_case_tips.map((tip: string, i: number) => (
                                <li key={i}>{tip}</li>
                              ))}
                            </ul>
                          </div>
                        )}
                      </div>
                    )}

                    {/* MODE 2: Bug Draft Result */}
                    {mode === 'bug_draft' && (
                      <div className="space-y-3">
                        {/* Client Reply Box */}
                        {result.client_reply_keigo && (
                          <div className="p-3 rounded-xl bg-blue-500/5 border border-blue-500/20 space-y-1">
                            <span className="font-bold text-[11px] text-blue-600 dark:text-blue-400 flex items-center gap-1">
                              <Mail className="w-3.5 h-3.5" /> Thư trả lời khách tức thì (Business Keigo):
                            </span>
                            <p className="text-xs text-primary leading-relaxed font-mono bg-canvas p-2.5 rounded-lg border border-border">
                              {result.client_reply_keigo}
                            </p>
                          </div>
                        )}

                        {/* Bug Specs Card */}
                        <div className="p-3.5 rounded-xl bg-canvas border border-border space-y-2">
                          <div className="flex items-center justify-between">
                            <span className="font-bold text-sm text-rose-500">{result.bug_title_ja}</span>
                            <Badge variant="outline" className="text-[10px] text-rose-500 border-rose-500/30">
                              {result.severity || 'HIGH'}
                            </Badge>
                          </div>

                          <div className="space-y-1 text-xs">
                            <p>
                              <strong className="text-primary">【発生事象】:</strong> {result.actual_behavior}
                            </p>
                            <p>
                              <strong className="text-emerald-500">【期待結果】:</strong> {result.expected_behavior}
                            </p>
                            <p>
                              <strong className="text-amber-500">【一次原因】:</strong> {result.preliminary_cause}
                            </p>
                          </div>

                          {result.suggested_fix && (
                            <div className="pt-2 border-t border-border/50 text-[11px] space-y-1">
                              <p>
                                <strong className="text-primary">暫定対応:</strong> {result.suggested_fix.workaround}
                              </p>
                              <p>
                                <strong className="text-primary">恒久対応:</strong> {result.suggested_fix.permanent}
                              </p>
                            </div>
                          )}
                        </div>
                      </div>
                    )}

                    {/* MODE 3: Dev Inquiry Result */}
                    {mode === 'dev_inquiry' && (
                      <div className="space-y-3">
                        <div className="p-3 rounded-xl bg-canvas border border-border space-y-2">
                          <h4 className="font-bold text-sm text-primary">{result.inquiry_title_ja}</h4>
                          <p className="text-xs text-muted-foreground">
                            <strong>対象機能:</strong> {result.target_function}
                          </p>
                          <p className="text-xs text-muted-foreground">{result.current_situation}</p>
                          <p className="text-xs text-amber-500">{result.issue_point}</p>
                        </div>

                        {/* Proposals A vs B */}
                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
                          {result.proposal_a && (
                            <div className="p-3 rounded-xl bg-emerald-500/5 border border-emerald-500/20 text-xs space-y-1">
                              <strong className="text-emerald-500 block">{result.proposal_a.title}</strong>
                              <p className="text-primary">{result.proposal_a.description}</p>
                              <p className="text-[11px] text-muted-foreground">
                                <strong>Ưu:</strong> {result.proposal_a.pros}
                              </p>
                            </div>
                          )}

                          {result.proposal_b && (
                            <div className="p-3 rounded-xl bg-subtle border border-border text-xs space-y-1">
                              <strong className="text-primary block">{result.proposal_b.title}</strong>
                              <p className="text-primary">{result.proposal_b.description}</p>
                              <p className="text-[11px] text-muted-foreground">
                                <strong>Ưu:</strong> {result.proposal_b.pros}
                              </p>
                            </div>
                          )}
                        </div>

                        {result.confirmation_question && (
                          <div className="p-3 rounded-xl bg-blue-500/5 border border-blue-500/20 text-xs">
                            <span className="font-bold text-blue-500 block mb-1">【ご確認事項】 (Gửi khách Nhật):</span>
                            <p className="text-primary font-mono">{result.confirmation_question}</p>
                          </div>
                        )}
                      </div>
                    )}

                    {/* Other modes: Markdown representation */}
                    {(mode === 'spec_ambiguity' || mode === 'japan_test_data' || mode === 'quick_checklist') && (
                      <div className="p-3.5 rounded-xl bg-canvas border border-border font-mono text-xs whitespace-pre-wrap">
                        {result.formatted_markdown || JSON.stringify(result, null, 2)}
                      </div>
                    )}
                  </div>
                </div>
              ) : (
                <div className="flex-1 flex flex-col items-center justify-center p-8 rounded-xl border border-dashed border-border bg-canvas/50 text-center">
                  <div className="p-4 rounded-2xl bg-purple-500/5 text-purple-500 mb-3 border border-purple-500/10">
                    <Sparkles className="w-8 h-8" />
                  </div>
                  <h3 className="text-sm font-bold text-primary mb-1">Kết quả sẽ xuất hiện tại đây</h3>
                  <p className="text-xs text-muted-foreground max-w-xs leading-relaxed">
                    Paste ý tưởng thô hoặc câu hỏi ở cột bên trái và bấm <strong>"Phân Tích & Chuẩn Hóa"</strong> để AI chuyển đổi sang chuẩn QA chuyên nghiệp.
                  </p>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
