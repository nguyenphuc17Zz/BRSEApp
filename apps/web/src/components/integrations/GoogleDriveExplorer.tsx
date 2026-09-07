import React, { useState, useRef, useEffect } from 'react';
import {
  Folder,
  Search,
  Sparkles,
  ChevronRight,
  FolderPlus,
  Upload,
  Edit2,
  Trash2,
  Download,
  ExternalLink,
  RefreshCw,
  Home,
  Check,
  CheckSquare,
  X,
  Link2,
  Users,
  Clock,
  ArrowUp,
  ArrowDown,
  ArrowUpDown,
  ListFilter
} from 'lucide-react';
import { GoogleFileItem } from '../../types';
import { apiClient } from '../../api/client';
import { useToast } from '../../context/ToastContext';
import { useConfirm } from '../../context/ConfirmDialogContext';
import { FileFormatIcon, resolveFileType, FileTypeCategory } from '../common/FileFormatIcon';

export type SortField = 'name' | 'modifiedTime' | 'size';
export type SortDirection = 'asc' | 'desc';

const formatFileSize = (bytesStr?: string, isFolder?: boolean): string => {
  if (isFolder) return '—';
  if (!bytesStr) return '—';
  const bytes = Number(bytesStr);
  if (isNaN(bytes) || bytes <= 0) return '—';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
};

const formatModifiedDate = (dateStr?: string): string => {
  if (!dateStr) return '—';
  try {
    const d = new Date(dateStr);
    if (isNaN(d.getTime())) return dateStr.slice(0, 10);
    const now = new Date();
    const isToday = d.toDateString() === now.toDateString();
    if (isToday) {
      return `Hôm nay, ${d.toLocaleTimeString('vi-VN', { hour: '2-digit', minute: '2-digit' })}`;
    }
    const yesterday = new Date(now);
    yesterday.setDate(yesterday.getDate() - 1);
    if (d.toDateString() === yesterday.toDateString()) {
      return `Hôm qua, ${d.toLocaleTimeString('vi-VN', { hour: '2-digit', minute: '2-digit' })}`;
    }
    const currentYear = now.getFullYear();
    if (d.getFullYear() === currentYear) {
      return d.toLocaleDateString('vi-VN', { day: '2-digit', month: '2-digit' });
    }
    return d.toLocaleDateString('vi-VN', { day: '2-digit', month: '2-digit', year: 'numeric' });
  } catch {
    return dateStr.slice(0, 10);
  }
};

const getOwnerDisplayName = (file: GoogleFileItem): string => {
  if (file.sharingUser?.displayName) {
    return file.sharingUser.displayName;
  }
  if (file.sharingUser?.emailAddress) {
    return file.sharingUser.emailAddress.split('@')[0];
  }
  if (file.owners && file.owners.length > 0 && file.owners[0].displayName) {
    return file.owners[0].displayName;
  }
  return 'tôi';
};

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

  // Format Filter state
  type FormatFilterType = 'all' | 'folder' | 'doc' | 'sheet' | 'slide' | 'pdf' | 'image';
  const [selectedFormatFilter, setSelectedFormatFilter] = useState<FormatFilterType>('all');

  const getFileCategory = (f: GoogleFileItem): FileTypeCategory => {
    return resolveFileType(f.type, f.name, f.mimeType);
  };

  const formatCounts = {
    all: files.length,
    folder: files.filter(f => getFileCategory(f) === 'folder').length,
    doc: files.filter(f => getFileCategory(f) === 'doc').length,
    sheet: files.filter(f => getFileCategory(f) === 'sheet').length,
    slide: files.filter(f => getFileCategory(f) === 'slide').length,
    pdf: files.filter(f => getFileCategory(f) === 'pdf').length,
    image: files.filter(f => getFileCategory(f) === 'image').length,
  };

  const filteredFiles = files.filter(file => {
    const cat = getFileCategory(file);
    if (selectedFormatFilter !== 'all') {
      if (cat !== selectedFormatFilter) {
        return false;
      }
    }
    if (searchQuery.trim()) {
      const q = searchQuery.trim().toLowerCase();
      if (!file.name.toLowerCase().includes(q)) {
        return false;
      }
    }
    return true;
  });

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

  // Batch selection state
  const [isSelectMode, setIsSelectMode] = useState(false);
  const [selectedFileIds, setSelectedFileIds] = useState<Set<string>>(new Set());
  const [isBatchDeleting, setIsBatchDeleting] = useState(false);

  // Download states
  const [downloadingFileId, setDownloadingFileId] = useState<string | null>(null);
  const [isBatchDownloading, setIsBatchDownloading] = useState(false);

  // Sorting state (Standard Google Drive Sort)
  const [sortField, setSortField] = useState<SortField>('name');
  const [sortDirection, setSortDirection] = useState<SortDirection>('asc');
  const [showSortDropdown, setShowSortDropdown] = useState(false);
  const sortDropdownRef = useRef<HTMLDivElement>(null);

  // Close sort dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (sortDropdownRef.current && !sortDropdownRef.current.contains(event.target as Node)) {
        setShowSortDropdown(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handleHeaderSort = (field: SortField) => {
    if (sortField === field) {
      setSortDirection(prev => (prev === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortField(field);
      setSortDirection(field === 'modifiedTime' ? 'desc' : 'asc');
    }
  };

  const handleSelectSort = (field: SortField, direction: SortDirection) => {
    setSortField(field);
    setSortDirection(direction);
    setShowSortDropdown(false);
  };

  const sortedFiles = [...filteredFiles].sort((a, b) => {
    const aIsFolder = a.type === 'folder';
    const bIsFolder = b.type === 'folder';
    if (aIsFolder && !bIsFolder) return -1;
    if (!aIsFolder && bIsFolder) return 1;

    let comp = 0;
    if (sortField === 'name') {
      comp = a.name.localeCompare(b.name, 'vi', { sensitivity: 'base', numeric: true });
    } else if (sortField === 'modifiedTime') {
      const aTime = a.modifiedTime ? new Date(a.modifiedTime).getTime() : 0;
      const bTime = b.modifiedTime ? new Date(b.modifiedTime).getTime() : 0;
      comp = aTime - bTime;
    } else if (sortField === 'size') {
      const aSize = Number(a.size || 0);
      const bSize = Number(b.size || 0);
      comp = aSize - bSize;
    }

    return sortDirection === 'asc' ? comp : -comp;
  });

  // Clear selection when navigating folders or switching views
  useEffect(() => {
    setIsSelectMode(false);
    setSelectedFileIds(new Set());
  }, [selectedFolder, viewMode]);

  const toggleSelectMode = () => {
    if (isSelectMode) {
      setIsSelectMode(false);
      setSelectedFileIds(new Set());
    } else {
      setIsSelectMode(true);
    }
  };

  const allFilteredSelected = sortedFiles.length > 0 && sortedFiles.every(f => selectedFileIds.has(f.id));
  const someFilteredSelected = sortedFiles.some(f => selectedFileIds.has(f.id));

  const handleToggleSelectFile = (fileId: string, e?: React.MouseEvent) => {
    if (e) e.stopPropagation();
    setSelectedFileIds(prev => {
      const next = new Set(prev);
      if (next.has(fileId)) {
        next.delete(fileId);
      } else {
        next.add(fileId);
      }
      return next;
    });
  };

  const handleToggleSelectAll = () => {
    if (allFilteredSelected) {
      setSelectedFileIds(prev => {
        const next = new Set(prev);
        sortedFiles.forEach(f => next.delete(f.id));
        return next;
      });
    } else {
      setSelectedFileIds(prev => {
        const next = new Set(prev);
        sortedFiles.forEach(f => next.add(f.id));
        return next;
      });
    }
  };

  const handleClearSelection = () => {
    setSelectedFileIds(new Set());
  };

  const handleBatchDelete = async () => {
    if (selectedFileIds.size === 0) return;
    const selectedItems = files.filter(f => selectedFileIds.has(f.id));
    const folderCount = selectedItems.filter(f => f.type === 'folder').length;
    const fileCount = selectedItems.length - folderCount;

    let itemsDesc = '';
    if (folderCount > 0 && fileCount > 0) {
      itemsDesc = `${fileCount} tập tin và ${folderCount} thư mục`;
    } else if (folderCount > 0) {
      itemsDesc = `${folderCount} thư mục`;
    } else {
      itemsDesc = `${fileCount} tập tin`;
    }

    const ok = await confirm({
      title: `Xóa vĩnh viễn ${selectedFileIds.size} mục trên Google Drive`,
      message: `Bạn có chắc chắn muốn xóa vĩnh viễn ${itemsDesc} đã chọn khỏi Google Drive? Thao tác này sẽ gỡ bỏ các mục này khỏi tài khoản của bạn và không thể hoàn tác.`,
      isDestructive: true,
      confirmText: `Xóa vĩnh viễn (${selectedFileIds.size})`,
      cancelText: 'Hủy bỏ'
    });

    if (!ok) return;

    setIsBatchDeleting(true);
    try {
      const res = await apiClient.batchDeleteDriveFiles(Array.from(selectedFileIds));
      if (res.failed_count > 0) {
        toast.warning(`Đã xóa ${res.deleted_count}/${res.deleted_count + res.failed_count} mục. Một số mục không thể xóa.`);
      } else {
        toast.success(`Đã xóa thành công ${res.deleted_count} mục khỏi Google Drive`);
      }
      setSelectedFileIds(new Set());
      onRefresh();
    } catch (e: any) {
      toast.error(e.response?.data?.detail || 'Không thể xóa các mục đã chọn');
    } finally {
      setIsBatchDeleting(false);
    }
  };

  const handleDownloadSingle = async (file: GoogleFileItem) => {
    if (file.type === 'folder') return;
    setDownloadingFileId(file.id);
    try {
      const dlName = await apiClient.downloadDriveFile(file.id, file.name);
      toast.success(`Đã tải xuống "${dlName}"`);
    } catch (err: any) {
      toast.error(err.response?.data?.detail || 'Không thể tải xuống tệp tin');
    } finally {
      setDownloadingFileId(null);
    }
  };

  const handleBatchDownload = async () => {
    const selectedFiles = files.filter(f => selectedFileIds.has(f.id) && f.type !== 'folder');
    if (selectedFiles.length === 0) {
      toast.warning('Vui lòng chọn ít nhất 1 tệp tin để tải xuống (không thể tải trực tiếp thư mục).');
      return;
    }

    setIsBatchDownloading(true);
    try {
      const zipName = await apiClient.downloadDriveFilesBatch(selectedFiles.map(f => f.id));
      toast.success(`Đã tải xuống thành công ${selectedFiles.length} tệp tin (${zipName})`);
    } catch (err: any) {
      toast.error(err.response?.data?.detail || 'Không thể tải xuống các tệp tin đã chọn');
    } finally {
      setIsBatchDownloading(false);
    }
  };

  const selectedFilesCount = files.filter(f => selectedFileIds.has(f.id) && f.type !== 'folder').length;

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
      setSelectedFileIds(prev => {
        if (prev.has(file.id)) {
          const next = new Set(prev);
          next.delete(file.id);
          return next;
        }
        return prev;
      });
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

          {/* Select Mode / Batch Delete Buttons */}
          {!isSelectMode ? (
            <button
              type="button"
              onClick={toggleSelectMode}
              className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white text-xs font-medium flex items-center gap-1.5 border border-slate-700 transition-colors"
              title="Bật chế độ chọn nhiều file để thao tác"
            >
              <CheckSquare className="w-3.5 h-3.5 text-sky-400" />
              <span className="hidden sm:inline">Chọn</span>
            </button>
          ) : (
            <div className="flex items-center gap-1.5">
              {selectedFilesCount > 0 && (
                <button
                  type="button"
                  onClick={handleBatchDownload}
                  disabled={isBatchDownloading}
                  className="px-3 py-1.5 rounded-lg bg-sky-600 hover:bg-sky-500 disabled:opacity-50 text-white text-xs font-semibold flex items-center gap-1.5 shadow-md shadow-sky-900/30 transition-all hover:scale-[1.02] active:scale-[0.98]"
                  title="Tải tất cả tệp tin đã chọn dưới dạng file .ZIP"
                >
                  {isBatchDownloading ? (
                    <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                  ) : (
                    <Download className="w-3.5 h-3.5" />
                  )}
                  <span>Tải xuống ({selectedFilesCount})</span>
                </button>
              )}
              {selectedFileIds.size > 0 && (
                <button
                  type="button"
                  onClick={handleBatchDelete}
                  disabled={isBatchDeleting}
                  className="px-3 py-1.5 rounded-lg bg-red-600 hover:bg-red-500 disabled:opacity-50 text-white text-xs font-semibold flex items-center gap-1.5 shadow-md shadow-red-900/30 transition-all hover:scale-[1.02] active:scale-[0.98]"
                  title="Xóa vĩnh viễn các mục đã chọn khỏi Google Drive"
                >
                  {isBatchDeleting ? (
                    <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                  ) : (
                    <Trash2 className="w-3.5 h-3.5" />
                  )}
                  <span>Xóa tất ({selectedFileIds.size})</span>
                </button>
              )}
              <button
                type="button"
                onClick={toggleSelectMode}
                className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white border border-slate-700 text-xs font-medium flex items-center gap-1.5 transition-colors"
                title="Thoát chế độ chọn"
              >
                <X className="w-3.5 h-3.5 text-slate-400" />
                <span className="hidden sm:inline">Hủy chọn</span>
              </button>
            </div>
          )}

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

      {/* Format Filter Bar */}
      <div className="px-5 py-2.5 bg-slate-900/90 border-b border-slate-800/80 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-1.5 overflow-x-auto py-0.5 scrollbar-none">
          {([
            { key: 'all' as const, label: 'Tất cả', icon: null },
            { key: 'folder' as const, label: 'Thư mục', icon: <Folder className="w-3 h-3 text-amber-400" /> },
            { key: 'doc' as const, label: 'Tài liệu', icon: <FileFormatIcon type="doc" size="xs" /> },
            { key: 'sheet' as const, label: 'Bảng tính', icon: <FileFormatIcon type="sheet" size="xs" /> },
            { key: 'slide' as const, label: 'Trình chiếu', icon: <FileFormatIcon type="slide" size="xs" /> },
            { key: 'pdf' as const, label: 'PDF', icon: <FileFormatIcon type="pdf" size="xs" /> },
            { key: 'image' as const, label: 'Hình ảnh', icon: <FileFormatIcon type="image" size="xs" /> },
          ]).map((tab) => {
            const count = formatCounts[tab.key];
            const isActive = selectedFormatFilter === tab.key;
            return (
              <button
                key={tab.key}
                type="button"
                onClick={() => setSelectedFormatFilter(tab.key)}
                className={`px-2.5 py-1 rounded-lg text-xs font-medium flex items-center gap-1.5 transition-all ${
                  isActive
                    ? 'bg-sky-500/20 text-sky-300 border border-sky-500/40 shadow-sm shadow-sky-950'
                    : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60 border border-transparent'
                }`}
              >
                {tab.icon}
                <span>{tab.label}</span>
                <span className={`text-[10px] px-1.5 py-0.2 rounded-full font-mono ${
                  isActive ? 'bg-sky-500/30 text-sky-200' : 'bg-slate-800 text-slate-400'
                }`}>
                  {count}
                </span>
              </button>
            );
          })}
        </div>

        <div className="flex items-center gap-3">
          {isSelectMode && filteredFiles.length > 0 && (
            <label className="flex items-center gap-2 cursor-pointer select-none text-xs text-slate-300 hover:text-white px-2.5 py-1 rounded-lg bg-slate-800/80 border border-slate-700 hover:bg-slate-800 transition-colors">
              <input
                type="checkbox"
                checked={allFilteredSelected}
                ref={(el) => {
                  if (el) el.indeterminate = someFilteredSelected && !allFilteredSelected;
                }}
                onChange={handleToggleSelectAll}
                className="w-3.5 h-3.5 rounded border-slate-600 bg-slate-900 text-sky-500 focus:ring-sky-500/20 focus:ring-offset-0 cursor-pointer accent-sky-500"
              />
              <span className="font-medium text-[11px]">
                {allFilteredSelected ? 'Bỏ chọn tất cả' : 'Chọn tất cả'}
                <span className="text-slate-400 ml-1">({filteredFiles.length})</span>
              </span>
            </label>
          )}

          {selectedFormatFilter !== 'all' && (
            <div className="flex items-center gap-2">
              <span className="text-[11px] text-slate-400">
                Đang lọc: {filteredFiles.length} / {files.length} mục
              </span>
              <button
                type="button"
                onClick={() => setSelectedFormatFilter('all')}
                className="text-[10px] text-sky-400 hover:text-sky-300 font-medium px-2 py-0.5 rounded bg-sky-500/10 border border-sky-500/20 hover:bg-sky-500/20 transition-colors"
              >
                Xem tất cả
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Files List Table Header (Standard Google Drive Sort Bar) */}
      <div className="px-5 py-2.5 bg-slate-900/90 border-b border-slate-800 text-[11px] font-medium text-slate-400 select-none flex items-center justify-between gap-4">
        {/* Cột 1: Tên (kèm icon sắp xếp) */}
        <div className="flex items-center gap-3 min-w-0 flex-1">
          {isSelectMode && <div className="w-5 flex-shrink-0" />}
          <button
            type="button"
            onClick={() => handleHeaderSort('name')}
            className={`group inline-flex items-center gap-1.5 hover:text-white transition-colors cursor-pointer ${
              sortField === 'name' ? 'text-sky-400 font-semibold' : ''
            }`}
            title="Sắp xếp theo tên"
          >
            <span>Tên</span>
            <span className={`w-4 h-4 rounded-full flex items-center justify-center transition-all ${
              sortField === 'name'
                ? 'bg-sky-500/20 text-sky-400'
                : 'text-slate-500 opacity-0 group-hover:opacity-100 hover:bg-slate-800'
            }`}>
              {sortField === 'name' && sortDirection === 'desc' ? (
                <ArrowDown className="w-3 h-3" />
              ) : (
                <ArrowUp className="w-3 h-3" />
              )}
            </span>
          </button>
        </div>

        {/* Cột 2: Chủ sở hữu */}
        <div className="w-32 lg:w-40 flex-shrink-0 hidden md:flex items-center text-slate-400">
          <span>Chủ sở hữu</span>
        </div>

        {/* Cột 3: Ngày sửa đổi */}
        <div className="w-32 lg:w-36 flex-shrink-0 hidden sm:flex items-center">
          <button
            type="button"
            onClick={() => handleHeaderSort('modifiedTime')}
            className={`group inline-flex items-center gap-1.5 hover:text-white transition-colors cursor-pointer ${
              sortField === 'modifiedTime' ? 'text-sky-400 font-semibold' : ''
            }`}
            title="Sắp xếp theo ngày sửa đổi"
          >
            <span>Ngày sửa đổi</span>
            <span className={`w-4 h-4 rounded-full flex items-center justify-center transition-all ${
              sortField === 'modifiedTime'
                ? 'bg-sky-500/20 text-sky-400'
                : 'text-slate-500 opacity-0 group-hover:opacity-100 hover:bg-slate-800'
            }`}>
              {sortField === 'modifiedTime' && sortDirection === 'desc' ? (
                <ArrowDown className="w-3 h-3" />
              ) : (
                <ArrowUp className="w-3 h-3" />
              )}
            </span>
          </button>
        </div>

        {/* Cột 4: Kích cỡ tệp */}
        <div className="w-24 lg:w-28 flex-shrink-0 hidden sm:flex items-center">
          <button
            type="button"
            onClick={() => handleHeaderSort('size')}
            className={`group inline-flex items-center gap-1.5 hover:text-white transition-colors cursor-pointer ${
              sortField === 'size' ? 'text-sky-400 font-semibold' : ''
            }`}
            title="Sắp xếp theo kích cỡ"
          >
            <span>Kích cỡ tệp</span>
            <span className={`w-4 h-4 rounded-full flex items-center justify-center transition-all ${
              sortField === 'size'
                ? 'bg-sky-500/20 text-sky-400'
                : 'text-slate-500 opacity-0 group-hover:opacity-100 hover:bg-slate-800'
            }`}>
              {sortField === 'size' && sortDirection === 'desc' ? (
                <ArrowDown className="w-3 h-3" />
              ) : (
                <ArrowUp className="w-3 h-3" />
              )}
            </span>
          </button>
        </div>

        {/* Cột 5: Menu Sắp xếp */}
        <div className="w-52 lg:w-56 flex-shrink-0 flex items-center justify-end relative" ref={sortDropdownRef}>
          <button
            type="button"
            onClick={() => setShowSortDropdown(prev => !prev)}
            className={`flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-medium transition-colors border ${
              showSortDropdown
                ? 'bg-slate-800 text-white border-slate-700'
                : 'text-slate-400 hover:text-white hover:bg-slate-800/80 border-transparent hover:border-slate-700'
            }`}
            title="Tùy chọn sắp xếp nhanh"
          >
            <ListFilter className="w-3.5 h-3.5" />
            <span>Sắp xếp</span>
          </button>

          {/* Sort Dropdown Menu */}
          {showSortDropdown && (
            <div className="absolute right-0 top-full mt-1.5 w-52 bg-slate-900 border border-slate-700/80 rounded-xl shadow-2xl py-1.5 z-50 text-xs text-slate-300 animate-in fade-in zoom-in-95 duration-150">
              <div className="px-3 py-1 text-[10px] uppercase font-semibold text-slate-500 tracking-wider">
                Sắp xếp theo
              </div>
              <button
                type="button"
                onClick={() => handleSelectSort('name', 'asc')}
                className={`w-full px-3 py-1.5 text-left flex items-center justify-between hover:bg-slate-800 transition-colors ${
                  sortField === 'name' && sortDirection === 'asc' ? 'text-sky-400 font-medium bg-sky-500/10' : ''
                }`}
              >
                <span>Tên (A đến Z)</span>
                {sortField === 'name' && sortDirection === 'asc' && <Check className="w-3.5 h-3.5 text-sky-400" />}
              </button>
              <button
                type="button"
                onClick={() => handleSelectSort('name', 'desc')}
                className={`w-full px-3 py-1.5 text-left flex items-center justify-between hover:bg-slate-800 transition-colors ${
                  sortField === 'name' && sortDirection === 'desc' ? 'text-sky-400 font-medium bg-sky-500/10' : ''
                }`}
              >
                <span>Tên (Z đến A)</span>
                {sortField === 'name' && sortDirection === 'desc' && <Check className="w-3.5 h-3.5 text-sky-400" />}
              </button>

              <div className="my-1 border-t border-slate-800" />

              <button
                type="button"
                onClick={() => handleSelectSort('modifiedTime', 'desc')}
                className={`w-full px-3 py-1.5 text-left flex items-center justify-between hover:bg-slate-800 transition-colors ${
                  sortField === 'modifiedTime' && sortDirection === 'desc' ? 'text-sky-400 font-medium bg-sky-500/10' : ''
                }`}
              >
                <span>Sửa đổi gần đây nhất</span>
                {sortField === 'modifiedTime' && sortDirection === 'desc' && <Check className="w-3.5 h-3.5 text-sky-400" />}
              </button>
              <button
                type="button"
                onClick={() => handleSelectSort('modifiedTime', 'asc')}
                className={`w-full px-3 py-1.5 text-left flex items-center justify-between hover:bg-slate-800 transition-colors ${
                  sortField === 'modifiedTime' && sortDirection === 'asc' ? 'text-sky-400 font-medium bg-sky-500/10' : ''
                }`}
              >
                <span>Sửa đổi cũ nhất</span>
                {sortField === 'modifiedTime' && sortDirection === 'asc' && <Check className="w-3.5 h-3.5 text-sky-400" />}
              </button>

              <div className="my-1 border-t border-slate-800" />

              <button
                type="button"
                onClick={() => handleSelectSort('size', 'desc')}
                className={`w-full px-3 py-1.5 text-left flex items-center justify-between hover:bg-slate-800 transition-colors ${
                  sortField === 'size' && sortDirection === 'desc' ? 'text-sky-400 font-medium bg-sky-500/10' : ''
                }`}
              >
                <span>Kích cỡ (Lớn nhất trước)</span>
                {sortField === 'size' && sortDirection === 'desc' && <Check className="w-3.5 h-3.5 text-sky-400" />}
              </button>
              <button
                type="button"
                onClick={() => handleSelectSort('size', 'asc')}
                className={`w-full px-3 py-1.5 text-left flex items-center justify-between hover:bg-slate-800 transition-colors ${
                  sortField === 'size' && sortDirection === 'asc' ? 'text-sky-400 font-medium bg-sky-500/10' : ''
                }`}
              >
                <span>Kích cỡ (Nhỏ nhất trước)</span>
                {sortField === 'size' && sortDirection === 'asc' && <Check className="w-3.5 h-3.5 text-sky-400" />}
              </button>
            </div>
          )}
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
        ) : sortedFiles.length === 0 ? (
          <div className="p-10 text-center space-y-2.5">
            <Search className="w-8 h-8 text-slate-600 mx-auto" />
            <p className="text-slate-300 text-xs font-medium">
              Không tìm thấy mục nào phù hợp với bộ lọc hiện tại.
            </p>
            <p className="text-slate-500 text-[11px]">
              Thư mục này hiện có {files.length} mục, nhưng không có mục nào khớp với định dạng hoặc từ khóa đang chọn.
            </p>
            <button
              type="button"
              onClick={() => {
                setSelectedFormatFilter('all');
                onSearchChange('');
              }}
              className="px-3 py-1.5 rounded-md bg-slate-800 hover:bg-slate-700 text-sky-400 text-xs font-medium border border-slate-700 transition-colors"
            >
              Đặt lại bộ lọc & Tìm kiếm
            </button>
          </div>
        ) : (
          sortedFiles.map((file) => {
            const isSelected = selectedFileIds.has(file.id);
            const isFolder = file.type === 'folder';
            return (
              <div
                key={file.id}
                className={`px-5 py-2.5 transition-colors flex items-center justify-between gap-4 group ${
                  isSelectMode && isSelected
                    ? 'bg-sky-950/35 border-l-2 border-l-sky-500 hover:bg-sky-950/45'
                    : 'hover:bg-slate-850/50'
                }`}
              >
                {/* Column 1: Checkbox + Icon + Tên */}
                <div className="flex items-center gap-3 min-w-0 flex-1">
                  {/* Selection Checkbox (Only visible in Select Mode) */}
                  {isSelectMode && (
                    <div
                      className="flex items-center justify-center p-1 rounded hover:bg-slate-700/50 cursor-pointer flex-shrink-0"
                      onClick={(e) => handleToggleSelectFile(file.id, e)}
                      title={isSelected ? 'Bỏ chọn mục này' : 'Chọn mục này'}
                    >
                      <input
                        type="checkbox"
                        checked={isSelected}
                        onChange={() => {}}
                        className="w-4 h-4 rounded border-slate-600 bg-slate-800 text-sky-500 focus:ring-sky-500/20 cursor-pointer accent-sky-500 pointer-events-none"
                      />
                    </div>
                  )}

                  <div
                    className={`w-9 h-9 rounded-xl bg-slate-800/90 border border-slate-700/60 flex items-center justify-center flex-shrink-0 shadow-inner ${
                      isFolder ? 'cursor-pointer hover:border-sky-500/50 hover:bg-slate-800 transition-colors' : ''
                    }`}
                    onClick={() => {
                      if (isFolder) {
                        onOpenFolder(file.id, file.name);
                      }
                    }}
                  >
                    <FileFormatIcon type={file.type} name={file.name} mimeType={file.mimeType} size="md" />
                  </div>

                  <div className="min-w-0 pr-2">
                    <div className="flex items-center gap-2">
                      <h4
                        onClick={() => {
                          if (isFolder) {
                            onOpenFolder(file.id, file.name);
                          }
                        }}
                        className={`text-sm font-semibold truncate ${
                          isFolder
                            ? 'text-sky-300 hover:underline cursor-pointer'
                            : 'text-white'
                        }`}
                        title={file.name}
                      >
                        {file.name}
                      </h4>
                    </div>
                    {/* Mobile-only summary line for small screens */}
                    <div className="flex sm:hidden items-center gap-1.5 text-[11px] text-slate-400 mt-0.5 flex-wrap">
                      <span className="uppercase text-[9px] font-mono px-1 py-0.2 rounded bg-slate-800 text-slate-300 border border-slate-700/60">
                        {file.type}
                      </span>
                      <span>·</span>
                      <span className="truncate max-w-[120px]">{getOwnerDisplayName(file)}</span>
                      <span>·</span>
                      <span>{formatModifiedDate(file.modifiedTime)}</span>
                      <span>·</span>
                      <span>{formatFileSize(file.size, isFolder)}</span>
                    </div>
                  </div>
                </div>

                {/* Column 2: Chủ sở hữu */}
                <div className="w-32 lg:w-40 flex-shrink-0 hidden md:flex items-center text-xs text-slate-400 truncate">
                  <span className="truncate" title={getOwnerDisplayName(file)}>
                    {getOwnerDisplayName(file)}
                  </span>
                </div>

                {/* Column 3: Ngày sửa đổi */}
                <div className="w-32 lg:w-36 flex-shrink-0 hidden sm:flex items-center text-xs text-slate-400">
                  <span title={file.modifiedTime || undefined}>
                    {formatModifiedDate(file.modifiedTime)}
                  </span>
                </div>

                {/* Column 4: Kích cỡ tệp */}
                <div className="w-24 lg:w-28 flex-shrink-0 hidden sm:flex items-center text-xs text-slate-400 font-mono">
                  <span>{formatFileSize(file.size, isFolder)}</span>
                </div>

                {/* Column 5: Action Buttons */}
                <div className="w-52 lg:w-56 flex items-center justify-end gap-1.5 flex-shrink-0">
                  {/* Download Button (Only for files) */}
                  {!isFolder && (
                    <button
                      onClick={() => handleDownloadSingle(file)}
                      disabled={downloadingFileId === file.id}
                      className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition-colors"
                      title="Tải file về máy"
                    >
                      {downloadingFileId === file.id ? (
                        <RefreshCw className="w-4 h-4 animate-spin text-sky-400" />
                      ) : (
                        <Download className="w-4 h-4" />
                      )}
                    </button>
                  )}

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
                  {isFolder ? (
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
            );
          })
        )}
      </div>

      {/* Floating Action Bar for Batch Deletion */}
      {isSelectMode && selectedFileIds.size > 0 && (
        <div className="sticky bottom-4 z-40 px-4 self-center w-full max-w-xl animate-in fade-in slide-in-from-bottom-3 duration-200 mt-auto my-3">
          <div className="bg-slate-900/95 backdrop-blur-md border border-sky-500/40 rounded-xl px-4 py-2.5 shadow-2xl shadow-black/80 flex items-center justify-between gap-3 text-sm">
            <div className="flex items-center gap-2.5">
              <span className="flex items-center justify-center w-6 h-6 rounded-full bg-sky-500 text-slate-950 font-bold text-xs">
                {selectedFileIds.size}
              </span>
              <span className="text-white font-medium text-xs sm:text-sm">
                Đã chọn {selectedFileIds.size} mục
              </span>
              <button
                type="button"
                onClick={handleClearSelection}
                className="text-xs text-slate-400 hover:text-white underline decoration-slate-600 hover:decoration-white transition-colors ml-1"
              >
                Bỏ chọn
              </button>
            </div>

            <div className="flex items-center gap-2">
              {selectedFilesCount > 0 && (
                <button
                  type="button"
                  onClick={handleBatchDownload}
                  disabled={isBatchDownloading}
                  className="px-3.5 py-1.5 rounded-lg bg-sky-600 hover:bg-sky-500 disabled:opacity-50 text-white text-xs font-semibold flex items-center gap-1.5 shadow-md shadow-sky-900/30 transition-all hover:scale-[1.02] active:scale-[0.98]"
                  title="Tải tất cả tệp tin đã chọn dưới dạng file .ZIP"
                >
                  {isBatchDownloading ? (
                    <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                  ) : (
                    <Download className="w-3.5 h-3.5" />
                  )}
                  <span>Tải xuống ({selectedFilesCount})</span>
                </button>
              )}

              <button
                type="button"
                onClick={handleBatchDelete}
                disabled={isBatchDeleting}
                className="px-3.5 py-1.5 rounded-lg bg-red-600 hover:bg-red-500 disabled:opacity-50 text-white text-xs font-semibold flex items-center gap-1.5 shadow-md shadow-red-900/30 transition-all hover:scale-[1.02] active:scale-[0.98]"
                title="Xóa vĩnh viễn các mục đã chọn khỏi Google Drive"
              >
                {isBatchDeleting ? (
                  <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                ) : (
                  <Trash2 className="w-3.5 h-3.5" />
                )}
                <span>Xóa {selectedFileIds.size} mục đã chọn</span>
              </button>
            </div>
          </div>
        </div>
      )}

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
