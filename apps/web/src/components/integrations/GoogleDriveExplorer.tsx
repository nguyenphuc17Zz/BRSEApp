import React, { useState, useRef } from 'react';
import {
  Folder,
  Search,
  Sparkles,
  ChevronRight,
  FolderPlus,
  Upload,
  Edit2,
  Trash2,
  ExternalLink,
  RefreshCw,
  Home,
  Check,
  X,
  Link2,
  Users,
  Clock
} from 'lucide-react';
import { GoogleFileItem } from '../../types';
import { apiClient } from '../../api/client';
import { useToast } from '../../context/ToastContext';
import { useConfirm } from '../../context/ConfirmDialogContext';
import { FileFormatIcon } from '../common/FileFormatIcon';

interface GoogleDriveExplorerProps {
  files: GoogleFileItem[];
  isLoading: boolean;
  selectedFolder: string | null;
  folderName?: string | null;
  searchQuery: string;
  viewMode?: 'my_drive' | 'shared_with_me' | 'recent';
  onViewModeChange?: (mode: 'my_drive' | 'shared_with_me' | 'recent') => void;
  onSearchChange: (q: string) => void;
  onOpenFolder: (folderId: string | null, folderName?: string) => void;
  onTranslateFile: (file: GoogleFileItem) => void;
  onRefresh: () => void;
}

export const GoogleDriveExplorer: React.FC<GoogleDriveExplorerProps> = ({
  files,
  isLoading,
  selectedFolder,
  folderName,
  searchQuery,
  viewMode = 'my_drive',
  onViewModeChange,
  onSearchChange,
  onOpenFolder,
  onTranslateFile,
  onRefresh
}) => {
  const toast = useToast();
  const confirm = useConfirm();
  const fileInputRef = useRef<HTMLInputElement>(null);

  // New Folder state
  const [showNewFolderModal, setShowNewFolderModal] = useState(false);
  const [newFolderName, setNewFolderName] = useState('');
  const [isCreatingFolder, setIsCreatingFolder] = useState(false);

  // Rename state
  const [renameTarget, setRenameTarget] = useState<GoogleFileItem | null>(null);
  const [renameNewName, setRenameNewName] = useState('');
  const [isRenaming, setIsRenaming] = useState(false);

  // Link / Folder ID modal state
  const [showLinkModal, setShowLinkModal] = useState(false);
  const [folderLinkInput, setFolderLinkInput] = useState('');
  const [isOpeningLink, setIsOpeningLink] = useState(false);

  // Uploading state
  const [isUploading, setIsUploading] = useState(false);

  const extractFolderId = (input: string): string | null => {
    const trimmed = input.trim();
    if (!trimmed) return null;
    const urlMatch = trimmed.match(/(?:folders\/|[?&]id=)([a-zA-Z0-9_-]{15,})/);
    if (urlMatch) return urlMatch[1];
    if (/^[a-zA-Z0-9_-]{15,}$/.test(trimmed)) return trimmed;
    return null;
  };

  const handleOpenLinkSubmit = async () => {
    const extractedId = extractFolderId(folderLinkInput);
    if (!extractedId) {
      toast.error('Định dạng Link hoặc Folder ID không hợp lệ. Vui lòng kiểm tra lại.');
      return;
    }

    setIsOpeningLink(true);
    try {
      let folderTitle: string | undefined = undefined;
      try {
        const info = await apiClient.getDriveFolderInfo(extractedId);
        if (info && info.name) folderTitle = info.name;
      } catch (err) {
        console.warn('Could not fetch specific folder title:', err);
      }

      onOpenFolder(extractedId, folderTitle);
      toast.success(`Đã mở thư mục: ${folderTitle || extractedId}`);
      setShowLinkModal(false);
      setFolderLinkInput('');
    } catch (err: any) {
      toast.error(err.response?.data?.detail || 'Không thể mở thư mục này.');
    } finally {
      setIsOpeningLink(false);
    }
  };

  const handleCreateFolder = async () => {
    if (!newFolderName.trim()) {
      toast.error('Vui lòng nhập tên thư mục');
      return;
    }
    setIsCreatingFolder(true);
    try {
      await apiClient.createDriveFolder(newFolderName.trim(), selectedFolder || undefined);
      toast.success(`Đã tạo thư mục "${newFolderName}" thành công`);
      setNewFolderName('');
      setShowNewFolderModal(false);
      onRefresh();
    } catch (e: any) {
      toast.error(e.response?.data?.detail || 'Không thể tạo thư mục');
    } finally {
      setIsCreatingFolder(false);
    }
  };

  const handleUploadFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!e.target.files || e.target.files.length === 0) return;
    const file = e.target.files[0];
    setIsUploading(true);
    try {
      await apiClient.uploadDriveFile(file, selectedFolder || undefined);
      toast.success(`Đã tải lên file "${file.name}" thành công`);
      onRefresh();
    } catch (e: any) {
      toast.error(e.response?.data?.detail || 'Không thể tải file lên Drive');
    } finally {
      setIsUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  const handleRenameSubmit = async () => {
    if (!renameTarget || !renameNewName.trim()) {
      toast.error('Vui lòng nhập tên mới');
      return;
    }
    setIsRenaming(true);
    try {
      await apiClient.renameDriveFile(renameTarget.id, renameNewName.trim());
      toast.success(`Đã đổi tên thành "${renameNewName}" thành công`);
      setRenameTarget(null);
      setRenameNewName('');
      onRefresh();
    } catch (e: any) {
      toast.error(e.response?.data?.detail || 'Không thể đổi tên');
    } finally {
      setIsRenaming(false);
    }
  };

  const handleDeleteItem = async (file: GoogleFileItem) => {
    const isFolder = file.type === 'folder';
    const ok = await confirm({
      title: `Xóa ${isFolder ? 'thư mục' : 'tập tin'} trên Google Drive`,
      message: `Bạn có chắc chắn muốn xóa "${file.name}" khỏi Google Drive? Thao tác này sẽ gỡ bỏ file khỏi tài khoản của bạn.`,
      isDestructive: true,
      confirmText: 'Xóa vĩnh viễn'
    });
    if (!ok) return;

    try {
      await apiClient.deleteDriveFile(file.id);
      toast.success(`Đã xóa "${file.name}"`);
      onRefresh();
    } catch (e: any) {
      toast.error(e.response?.data?.detail || 'Không thể xóa');
    }
  };

  const getDriveWebUrl = (fileId: string) => {
    return `https://drive.google.com/open?id=${fileId}`;
  };

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-2xl overflow-hidden shadow-xl flex flex-col">
      {/* Hidden File Input for Upload */}
      <input
        type="file"
        ref={fileInputRef}
        onChange={handleUploadFile}
        className="hidden"
      />

      {/* Top View Category Selector: My Drive | Shared with me | Recent */}
      <div className="px-5 py-2.5 bg-slate-900 border-b border-slate-800 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-1.5 p-1 bg-slate-950/70 rounded-xl border border-slate-800">
          <button
            type="button"
            onClick={() => {
              if (viewMode !== 'my_drive') {
                onViewModeChange?.('my_drive');
              } else if (selectedFolder) {
                onOpenFolder(null, 'My Drive');
              }
            }}
            className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
              viewMode === 'my_drive' || !viewMode
                ? 'bg-sky-600/25 border border-sky-500 text-white shadow-sm shadow-sky-600/15'
                : 'text-slate-400 hover:text-white hover:bg-slate-800/80 border border-transparent'
            }`}
          >
            <Folder className="w-3.5 h-3.5 text-sky-400" />
            <span>Drive của tôi</span>
          </button>

          <button
            type="button"
            onClick={() => {
              if (viewMode !== 'shared_with_me') {
                onViewModeChange?.('shared_with_me');
              } else if (selectedFolder) {
                onOpenFolder(null, 'Được chia sẻ với tôi');
              }
            }}
            className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
              viewMode === 'shared_with_me'
                ? 'bg-indigo-600/25 border border-indigo-500 text-white shadow-sm shadow-indigo-600/15'
                : 'text-slate-400 hover:text-white hover:bg-slate-800/80 border border-transparent'
            }`}
          >
            <Users className="w-3.5 h-3.5 text-indigo-400" />
            <span>Được chia sẻ với tôi</span>
          </button>

          <button
            type="button"
            onClick={() => {
              if (viewMode !== 'recent') {
                onViewModeChange?.('recent');
              } else if (selectedFolder) {
                onOpenFolder(null, 'Gần đây');
              }
            }}
            className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
              viewMode === 'recent'
                ? 'bg-amber-600/25 border border-amber-500 text-white shadow-sm shadow-amber-600/15'
                : 'text-slate-400 hover:text-white hover:bg-slate-800/80 border border-transparent'
            }`}
          >
            <Clock className="w-3.5 h-3.5 text-amber-400" />
            <span>Gần đây</span>
          </button>
        </div>

        <span className="text-[11px] text-slate-500 hidden sm:inline-block">
          {viewMode === 'shared_with_me'
            ? 'Các tài liệu người khác mời hoặc chia sẻ quyền xem/sửa với bạn'
            : viewMode === 'recent'
            ? 'Các tài liệu mở hoặc chỉnh sửa gần nhất'
            : 'Tài liệu và thư mục trong Drive của bạn'}
        </span>
      </div>

      {/* Toolbar: Breadcrumb & Search & Actions */}
      <div className="px-5 py-3.5 border-b border-slate-800 bg-slate-850 flex flex-wrap items-center justify-between gap-3">
        {/* Breadcrumb Path */}
        <div className="flex items-center gap-1.5 text-xs text-slate-400">
          <button
            onClick={() => onOpenFolder(null, viewMode === 'shared_with_me' ? 'Được chia sẻ với tôi' : viewMode === 'recent' ? 'Gần đây' : 'My Drive')}
            className={`flex items-center gap-1 hover:text-white px-2 py-1 rounded transition-colors ${
              !selectedFolder ? 'text-white font-medium bg-slate-800' : 'text-slate-400'
            }`}
          >
            {viewMode === 'shared_with_me' ? (
              <Users className="w-3.5 h-3.5 text-indigo-400" />
            ) : viewMode === 'recent' ? (
              <Clock className="w-3.5 h-3.5 text-amber-400" />
            ) : (
              <Home className="w-3.5 h-3.5 text-sky-400" />
            )}
            <span>
              {viewMode === 'shared_with_me'
                ? 'Được chia sẻ với tôi'
                : viewMode === 'recent'
                ? 'Gần đây'
                : 'My Drive'}
            </span>
          </button>

          {selectedFolder && (
            <>
              <ChevronRight className="w-3.5 h-3.5 text-slate-600" />
              <span className="flex items-center gap-1 px-2 py-1 rounded bg-slate-800 text-white font-medium max-w-[200px] truncate">
                <Folder className="w-3.5 h-3.5 text-amber-400" />
                <span className="truncate">{folderName || selectedFolder}</span>
              </span>
            </>
          )}
        </div>

        {/* Action Buttons: New Folder, Upload, Refresh, Search */}
        <div className="flex items-center gap-2 flex-1 justify-end">
          <div className="relative max-w-xs w-full">
            <Search className="w-3.5 h-3.5 absolute left-3 top-2.5 text-slate-500" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => onSearchChange(e.target.value)}
              placeholder="Tìm kiếm file trên Drive..."
              className="w-full bg-slate-900 border border-slate-700 rounded-lg pl-8 pr-3 py-1.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-sky-500 transition-colors"
            />
          </div>

          <button
            onClick={() => setShowLinkModal(true)}
            className="px-3 py-1.5 rounded-lg bg-sky-500/15 hover:bg-sky-500/25 text-sky-300 text-xs font-medium flex items-center gap-1.5 border border-sky-500/30 transition-colors"
            title="Dán link hoặc ID thư mục Google Drive để mở nhanh"
          >
            <Link2 className="w-3.5 h-3.5 text-sky-400" />
            <span className="hidden sm:inline">Mở theo Link/ID</span>
          </button>

          <button
            onClick={() => setShowNewFolderModal(true)}
            className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-medium flex items-center gap-1.5 border border-slate-700 transition-colors"
            title="Tạo thư mục mới"
          >
            <FolderPlus className="w-3.5 h-3.5 text-sky-400" />
            <span className="hidden sm:inline">+ Thư mục mới</span>
          </button>

          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={isUploading}
            className="px-3 py-1.5 rounded-lg bg-sky-600/20 hover:bg-sky-600/30 text-sky-300 border border-sky-500/30 text-xs font-medium flex items-center gap-1.5 transition-colors"
            title="Tải file lên Drive"
          >
            {isUploading ? (
              <RefreshCw className="w-3.5 h-3.5 animate-spin text-sky-400" />
            ) : (
              <Upload className="w-3.5 h-3.5 text-sky-400" />
            )}
            <span className="hidden sm:inline">Tải file lên</span>
          </button>

          <button
            onClick={onRefresh}
            disabled={isLoading}
            className="p-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-400 hover:text-white border border-slate-700 transition-colors"
            title="Làm mới danh sách"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {/* Files List Table */}
      <div className="divide-y divide-slate-800/80">
        {files.length === 0 ? (
          <div className="p-12 text-center text-slate-500 text-xs space-y-2">
            {viewMode === 'shared_with_me' ? (
              <Users className="w-10 h-10 mx-auto text-slate-700 stroke-1" />
            ) : viewMode === 'recent' ? (
              <Clock className="w-10 h-10 mx-auto text-slate-700 stroke-1" />
            ) : (
              <Folder className="w-10 h-10 mx-auto text-slate-700 stroke-1" />
            )}
            <p className="font-medium text-slate-400">
              {viewMode === 'shared_with_me'
                ? 'Chưa có tập tin nào được chia sẻ với bạn'
                : viewMode === 'recent'
                ? 'Chưa có tập tin nào mở hoặc chỉnh sửa gần đây'
                : 'Không có tập tin nào trong thư mục này'}
            </p>
            <p className="text-slate-500 text-[11px]">
              {viewMode === 'shared_with_me'
                ? 'Khi người khác chia sẻ file hoặc folder với tài khoản Google này, chúng sẽ xuất hiện ở đây.'
                : viewMode === 'recent'
                ? 'Các tệp được mở hoặc cập nhật gần đây sẽ tự động hiển thị tại đây.'
                : 'Bấm "+ Thư mục mới" hoặc "Tải file lên" để bắt đầu thao tác.'}
            </p>
          </div>
        ) : (
          files.map((file) => (
            <div
              key={file.id}
              className="px-5 py-3 hover:bg-slate-850/50 transition-colors flex items-center justify-between gap-4 group"
            >
              {/* Left Item Details */}
              <div className="flex items-center gap-3.5 min-w-0 flex-1">
                <div
                  className={`w-10 h-10 rounded-xl bg-slate-800/90 border border-slate-700/60 flex items-center justify-center flex-shrink-0 shadow-inner ${
                    file.type === 'folder' ? 'cursor-pointer hover:border-sky-500/50 hover:bg-slate-800 transition-colors' : ''
                  }`}
                  onClick={() => {
                    if (file.type === 'folder') {
                      onOpenFolder(file.id, file.name);
                    }
                  }}
                >
                  <FileFormatIcon type={file.type} name={file.name} mimeType={file.mimeType} size="md" />
                </div>

                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <h4
                      onClick={() => {
                        if (file.type === 'folder') {
                          onOpenFolder(file.id, file.name);
                        }
                      }}
                      className={`text-sm font-semibold truncate ${
                        file.type === 'folder'
                          ? 'text-sky-300 hover:underline cursor-pointer'
                          : 'text-white'
                      }`}
                      title={file.name}
                    >
                      {file.name}
                    </h4>
                  </div>
                  <div className="flex items-center gap-2 flex-wrap text-xs text-slate-400 mt-0.5">
                    <span className="uppercase text-[10px] font-mono px-1.5 py-0.2 rounded bg-slate-800 text-slate-300 border border-slate-700/60">
                      {file.type}
                    </span>
                    {file.sharingUser && (
                      <span className="inline-flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-full bg-indigo-500/15 text-indigo-300 border border-indigo-500/30 font-medium" title={file.sharingUser.emailAddress}>
                        <Users className="w-3 h-3 text-indigo-400" />
                        <span>Chia sẻ bởi: {file.sharingUser.displayName || file.sharingUser.emailAddress}</span>
                      </span>
                    )}
                    {file.sharedWithMeTime && (
                      <span className="text-indigo-400/90 text-[11px]">
                        · Chia sẻ: {file.sharedWithMeTime.slice(0, 10)}
                      </span>
                    )}
                    {file.sharedDrive && (
                      <span className="text-[11px] text-amber-400">· Shared Drive</span>
                    )}
                    {file.size && (
                      <span className="text-slate-500 text-[11px]">
                        · {(Number(file.size) / 1024).toFixed(1)} KB
                      </span>
                    )}
                    <span className="text-slate-500 text-[11px]">
                      · Sửa: {file.modifiedTime?.slice(0, 10) || 'Gần đây'}
                    </span>
                  </div>
                </div>
              </div>

              {/* Right Action Buttons */}
              <div className="flex items-center gap-1.5 flex-shrink-0">
                {/* External Link */}
                <a
                  href={getDriveWebUrl(file.id)}
                  target="_blank"
                  rel="noreferrer"
                  className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition-colors"
                  title="Mở trực tiếp trên Google Drive"
                >
                  <ExternalLink className="w-4 h-4" />
                </a>

                {/* Rename Button */}
                <button
                  onClick={() => {
                    setRenameTarget(file);
                    setRenameNewName(file.name);
                  }}
                  className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition-colors"
                  title="Đổi tên"
                >
                  <Edit2 className="w-4 h-4" />
                </button>

                {/* Delete Button */}
                <button
                  onClick={() => handleDeleteItem(file)}
                  className="p-1.5 rounded-lg text-slate-400 hover:text-red-400 hover:bg-red-500/10 transition-colors"
                  title="Xóa"
                >
                  <Trash2 className="w-4 h-4" />
                </button>

                {/* Open Folder / Translate CTA */}
                {file.type === 'folder' ? (
                  <button
                    onClick={() => onOpenFolder(file.id, file.name)}
                    className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-medium transition-colors ml-1"
                  >
                    Mở thư mục
                  </button>
                ) : (
                  <button
                    onClick={() => onTranslateFile(file)}
                    className="px-3.5 py-1.5 rounded-lg bg-sky-600/20 hover:bg-sky-600/30 text-sky-300 border border-sky-500/30 text-xs font-medium flex items-center gap-1.5 transition-colors ml-1"
                  >
                    <Sparkles className="w-3.5 h-3.5" />
                    <span>Cấu hình & Dịch</span>
                  </button>
                )}
              </div>
            </div>
          ))
        )}
      </div>

      {/* MODAL: New Folder */}
      {showNewFolderModal && (
        <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-700 rounded-xl p-5 max-w-sm w-full shadow-2xl space-y-4">
            <div className="flex items-center justify-between">
              <h4 className="text-sm font-semibold text-white flex items-center gap-2">
                <FolderPlus className="w-4 h-4 text-sky-400" />
                <span>Tạo Thư Mục Mới</span>
              </h4>
              <button
                onClick={() => setShowNewFolderModal(false)}
                className="p-1 rounded hover:bg-slate-800 text-slate-400 hover:text-white"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
            <p className="text-xs text-slate-400">
              Thư mục mới sẽ được tạo trong:{' '}
              <strong className="text-sky-300">{folderName || 'My Drive'}</strong>
            </p>
            <input
              type="text"
              value={newFolderName}
              onChange={(e) => setNewFolderName(e.target.value)}
              placeholder="Nhập tên thư mục..."
              autoFocus
              className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-sky-500"
              onKeyDown={(e) => {
                if (e.key === 'Enter') handleCreateFolder();
              }}
            />
            <div className="flex justify-end gap-2 pt-1">
              <button
                onClick={() => setShowNewFolderModal(false)}
                className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-medium"
              >
                Hủy
              </button>
              <button
                onClick={handleCreateFolder}
                disabled={isCreatingFolder || !newFolderName.trim()}
                className="px-4 py-1.5 rounded-lg bg-sky-600 hover:bg-sky-500 disabled:opacity-50 text-white text-xs font-medium flex items-center gap-1.5"
              >
                {isCreatingFolder && <RefreshCw className="w-3.5 h-3.5 animate-spin" />}
                <span>Tạo Thư Mục</span>
              </button>
            </div>
          </div>
        </div>
      )}

      {/* MODAL: Rename File / Folder */}
      {renameTarget && (
        <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-700 rounded-xl p-5 max-w-sm w-full shadow-2xl space-y-4">
            <div className="flex items-center justify-between">
              <h4 className="text-sm font-semibold text-white flex items-center gap-2">
                <Edit2 className="w-4 h-4 text-sky-400" />
                <span>Đổi Tên {renameTarget.type === 'folder' ? 'Thư Mục' : 'Tập Tin'}</span>
              </h4>
              <button
                onClick={() => setRenameTarget(null)}
                className="p-1 rounded hover:bg-slate-800 text-slate-400 hover:text-white"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
            <input
              type="text"
              value={renameNewName}
              onChange={(e) => setRenameNewName(e.target.value)}
              autoFocus
              className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-sky-500"
              onKeyDown={(e) => {
                if (e.key === 'Enter') handleRenameSubmit();
              }}
            />
            <div className="flex justify-end gap-2 pt-1">
              <button
                onClick={() => setRenameTarget(null)}
                className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-medium"
              >
                Hủy
              </button>
              <button
                onClick={handleRenameSubmit}
                disabled={isRenaming || !renameNewName.trim()}
                className="px-4 py-1.5 rounded-lg bg-sky-600 hover:bg-sky-500 disabled:opacity-50 text-white text-xs font-medium flex items-center gap-1.5"
              >
                {isRenaming && <RefreshCw className="w-3.5 h-3.5 animate-spin" />}
                <span>Lưu Thay Đổi</span>
              </button>
            </div>
          </div>
        </div>
      )}
      {/* MODAL: Open Folder by Link / ID */}
      {showLinkModal && (
        <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-700 rounded-xl p-5 max-w-lg w-full shadow-2xl space-y-4">
            <div className="flex items-center justify-between">
              <h4 className="text-sm font-semibold text-white flex items-center gap-2">
                <Link2 className="w-4 h-4 text-sky-400" />
                <span>Mở Thư Mục Bằng Link Hoặc Folder ID</span>
              </h4>
              <button
                onClick={() => setShowLinkModal(false)}
                className="p-1 rounded hover:bg-slate-800 text-slate-400 hover:text-white"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <p className="text-xs text-slate-400 leading-relaxed">
              Dán đường link Google Drive chia sẻ (ví dụ: <code className="text-sky-300">https://drive.google.com/drive/folders/...</code>) hoặc mã Folder ID để mở thẳng thư mục đó mà không cần tìm kiếm thủ công.
            </p>

            <div className="space-y-2">
              <input
                type="text"
                value={folderLinkInput}
                onChange={(e) => setFolderLinkInput(e.target.value)}
                placeholder="Dán link https://drive.google.com/drive/folders/... hoặc Folder ID"
                autoFocus
                className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-xs text-white focus:outline-none focus:border-sky-500 font-mono"
                onKeyDown={(e) => {
                  if (e.key === 'Enter') handleOpenLinkSubmit();
                }}
              />
              <div className="flex items-center gap-2 pt-1 text-[11px] text-slate-400">
                <span>Gợi ý:</span>
                <button
                  type="button"
                  onClick={() => setFolderLinkInput('https://drive.google.com/drive/folders/1eyQ-oZhGwNfU8_-wr5HoChIuWjgUe801?hl=vi')}
                  className="text-sky-400 hover:text-sky-300 underline font-mono truncate max-w-xs"
                  title="Điền link thư mục test mẫu của bạn"
                >
                  Thư mục Test mẫu (1eyQ-oZhGw...)
                </button>
              </div>
            </div>

            <div className="flex justify-end gap-2 pt-2 border-t border-slate-800">
              <button
                onClick={() => setShowLinkModal(false)}
                className="px-3.5 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-medium"
              >
                Hủy
              </button>
              <button
                onClick={handleOpenLinkSubmit}
                disabled={isOpeningLink || !folderLinkInput.trim()}
                className="px-4 py-1.5 rounded-lg bg-sky-600 hover:bg-sky-500 disabled:opacity-50 text-white text-xs font-medium flex items-center gap-1.5"
              >
                {isOpeningLink && <RefreshCw className="w-3.5 h-3.5 animate-spin" />}
                <span>Mở Thư Mục</span>
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
