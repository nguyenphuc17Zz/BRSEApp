import React from 'react';

export type FileTypeCategory = 'doc' | 'sheet' | 'slide' | 'pdf' | 'folder' | 'image' | 'archive' | 'file';

interface FileFormatIconProps {
  type?: string;
  name?: string;
  mimeType?: string;
  size?: 'xs' | 'sm' | 'md' | 'lg' | 'xl';
  className?: string;
}

export function resolveFileType(type?: string, name?: string, mimeType?: string): FileTypeCategory {
  const t = (type || '').toLowerCase();
  const m = (mimeType || '').toLowerCase();
  const ext = (name || '').split('.').pop()?.toLowerCase() || '';

  if (t === 'folder' || m.includes('folder')) {
    return 'folder';
  }

  if (
    t === 'pdf' ||
    ext === 'pdf' ||
    m.includes('pdf')
  ) {
    return 'pdf';
  }

  if (
    t === 'doc' ||
    t === 'docx' ||
    ['doc', 'docx', 'rtf', 'odt'].includes(ext) ||
    m.includes('word') ||
    (m.includes('document') && !m.includes('spreadsheet') && !m.includes('presentation'))
  ) {
    return 'doc';
  }

  if (
    t === 'sheet' ||
    t === 'xlsx' ||
    ['xls', 'xlsx', 'csv', 'tsv', 'ods'].includes(ext) ||
    m.includes('excel') ||
    m.includes('spreadsheet') ||
    m.includes('csv')
  ) {
    return 'sheet';
  }

  if (
    t === 'slide' ||
    t === 'pptx' ||
    ['ppt', 'pptx', 'odp'].includes(ext) ||
    m.includes('presentation') ||
    m.includes('powerpoint')
  ) {
    return 'slide';
  }

  if (
    ['png', 'jpg', 'jpeg', 'webp', 'gif', 'svg', 'bmp', 'tiff'].includes(ext) ||
    m.startsWith('image/')
  ) {
    return 'image';
  }

  if (
    ['zip', 'rar', '7z', 'tar', 'gz', 'bz2'].includes(ext) ||
    m.includes('zip') ||
    m.includes('compressed') ||
    m.includes('archive')
  ) {
    return 'archive';
  }

  return 'file';
}

const sizeMap = {
  xs: 'w-4 h-4',
  sm: 'w-5 h-5',
  md: 'w-6 h-6',
  lg: 'w-8 h-8',
  xl: 'w-10 h-10',
};

export const FileFormatIcon: React.FC<FileFormatIconProps> = ({
  type,
  name,
  mimeType,
  size = 'md',
  className = '',
}) => {
  const category = resolveFileType(type, name, mimeType);
  const sizeClass = sizeMap[size] || sizeMap.md;

  switch (category) {
    case 'pdf':
      return (
        <svg
          viewBox="0 0 32 32"
          fill="none"
          xmlns="http://www.w3.org/2000/svg"
          className={`${sizeClass} ${className} flex-shrink-0 drop-shadow-sm select-none`}
        >
          <defs>
            <linearGradient id="pdfBg" x1="4" y1="2" x2="28" y2="30" gradientUnits="userSpaceOnUse">
              <stop stopColor="#F43F5E" />
              <stop offset="1" stopColor="#BE123C" />
            </linearGradient>
            <linearGradient id="pdfFold" x1="20" y1="2" x2="28" y2="10" gradientUnits="userSpaceOnUse">
              <stop stopColor="#FECDD3" stopOpacity="0.8" />
              <stop offset="1" stopColor="#FB7185" stopOpacity="0.3" />
            </linearGradient>
          </defs>
          {/* Main Paper */}
          <path
            d="M6 3C6 2.44772 6.44772 2 7 2H20L28 10V29C28 29.5523 27.5523 30 27 30H7C6.44772 30 6 29.5523 6 29V3Z"
            fill="url(#pdfBg)"
          />
          {/* Top-right folded corner */}
          <path d="M20 2V9C20 9.55228 20.4477 10 21 10H28L20 2Z" fill="url(#pdfFold)" />
          {/* PDF Ribbon Curve Graphic */}
          <path
            d="M10 13C12 11 15 12 16 15C17 18 19 17 22 14"
            stroke="white"
            strokeWidth="1.75"
            strokeLinecap="round"
            strokeOpacity="0.85"
          />
          {/* PDF Badge */}
          <rect x="3" y="18" width="18" height="10" rx="2.5" fill="#9F1239" stroke="#FECDD3" strokeWidth="1" />
          <text
            x="12"
            y="25.5"
            textAnchor="middle"
            fill="white"
            fontSize="7"
            fontWeight="900"
            fontFamily="system-ui, -apple-system, sans-serif"
            letterSpacing="0.5"
          >
            PDF
          </text>
        </svg>
      );

    case 'doc':
      return (
        <svg
          viewBox="0 0 32 32"
          fill="none"
          xmlns="http://www.w3.org/2000/svg"
          className={`${sizeClass} ${className} flex-shrink-0 drop-shadow-sm select-none`}
        >
          <defs>
            <linearGradient id="docBg" x1="4" y1="2" x2="28" y2="30" gradientUnits="userSpaceOnUse">
              <stop stopColor="#3B82F6" />
              <stop offset="1" stopColor="#1D4ED8" />
            </linearGradient>
            <linearGradient id="docFold" x1="20" y1="2" x2="28" y2="10" gradientUnits="userSpaceOnUse">
              <stop stopColor="#BFDBFE" stopOpacity="0.8" />
              <stop offset="1" stopColor="#60A5FA" stopOpacity="0.3" />
            </linearGradient>
          </defs>
          {/* Main Paper */}
          <path
            d="M6 3C6 2.44772 6.44772 2 7 2H20L28 10V29C28 29.5523 27.5523 30 27 30H7C6.44772 30 6 29.5523 6 29V3Z"
            fill="url(#docBg)"
          />
          {/* Folded corner */}
          <path d="M20 2V9C20 9.55228 20.4477 10 21 10H28L20 2Z" fill="url(#docFold)" />
          {/* Text paragraph lines */}
          <rect x="10" y="12" width="12" height="2" rx="1" fill="white" fillOpacity="0.85" />
          <rect x="10" y="16" width="9" height="2" rx="1" fill="white" fillOpacity="0.65" />
          {/* DOC Badge */}
          <rect x="3" y="18" width="18" height="10" rx="2.5" fill="#1E40AF" stroke="#93C5FD" strokeWidth="1" />
          <text
            x="12"
            y="25.5"
            textAnchor="middle"
            fill="white"
            fontSize="6.5"
            fontWeight="900"
            fontFamily="system-ui, -apple-system, sans-serif"
            letterSpacing="0.3"
          >
            DOC
          </text>
        </svg>
      );

    case 'sheet':
      return (
        <svg
          viewBox="0 0 32 32"
          fill="none"
          xmlns="http://www.w3.org/2000/svg"
          className={`${sizeClass} ${className} flex-shrink-0 drop-shadow-sm select-none`}
        >
          <defs>
            <linearGradient id="sheetBg" x1="4" y1="2" x2="28" y2="30" gradientUnits="userSpaceOnUse">
              <stop stopColor="#10B981" />
              <stop offset="1" stopColor="#047857" />
            </linearGradient>
            <linearGradient id="sheetFold" x1="20" y1="2" x2="28" y2="10" gradientUnits="userSpaceOnUse">
              <stop stopColor="#A7F3D0" stopOpacity="0.8" />
              <stop offset="1" stopColor="#34D399" stopOpacity="0.3" />
            </linearGradient>
          </defs>
          {/* Main Paper */}
          <path
            d="M6 3C6 2.44772 6.44772 2 7 2H20L28 10V29C28 29.5523 27.5523 30 27 30H7C6.44772 30 6 29.5523 6 29V3Z"
            fill="url(#sheetBg)"
          />
          {/* Folded corner */}
          <path d="M20 2V9C20 9.55228 20.4477 10 21 10H28L20 2Z" fill="url(#sheetFold)" />
          {/* Spreadsheet grid cells */}
          <g stroke="white" strokeOpacity="0.8" strokeWidth="1.2">
            {/* Header row */}
            <line x1="9" y1="12" x2="23" y2="12" />
            <line x1="9" y1="16" x2="23" y2="16" />
            <line x1="16" y1="9" x2="16" y2="17" />
          </g>
          {/* XLS Badge */}
          <rect x="3" y="18" width="18" height="10" rx="2.5" fill="#064E3B" stroke="#6EE7B7" strokeWidth="1" />
          <text
            x="12"
            y="25.5"
            textAnchor="middle"
            fill="white"
            fontSize="6.5"
            fontWeight="900"
            fontFamily="system-ui, -apple-system, sans-serif"
            letterSpacing="0.3"
          >
            XLS
          </text>
        </svg>
      );

    case 'slide':
      return (
        <svg
          viewBox="0 0 32 32"
          fill="none"
          xmlns="http://www.w3.org/2000/svg"
          className={`${sizeClass} ${className} flex-shrink-0 drop-shadow-sm select-none`}
        >
          <defs>
            <linearGradient id="slideBg" x1="4" y1="2" x2="28" y2="30" gradientUnits="userSpaceOnUse">
              <stop stopColor="#F59E0B" />
              <stop offset="1" stopColor="#D97706" />
            </linearGradient>
            <linearGradient id="slideFold" x1="20" y1="2" x2="28" y2="10" gradientUnits="userSpaceOnUse">
              <stop stopColor="#FDE68A" stopOpacity="0.8" />
              <stop offset="1" stopColor="#F59E0B" stopOpacity="0.3" />
            </linearGradient>
          </defs>
          {/* Main Paper */}
          <path
            d="M6 3C6 2.44772 6.44772 2 7 2H20L28 10V29C28 29.5523 27.5523 30 27 30H7C6.44772 30 6 29.5523 6 29V3Z"
            fill="url(#slideBg)"
          />
          {/* Folded corner */}
          <path d="M20 2V9C20 9.55228 20.4477 10 21 10H28L20 2Z" fill="url(#slideFold)" />
          {/* Slide Presentation Pie/Chart Graphic */}
          <circle cx="15" cy="14" r="3.5" stroke="white" strokeOpacity="0.8" strokeWidth="1.5" />
          <path d="M15 10.5V14H18.5" stroke="white" strokeOpacity="0.9" strokeWidth="1.5" strokeLinecap="round" />
          {/* PPT Badge */}
          <rect x="3" y="18" width="18" height="10" rx="2.5" fill="#78350F" stroke="#FCD34D" strokeWidth="1" />
          <text
            x="12"
            y="25.5"
            textAnchor="middle"
            fill="white"
            fontSize="6.5"
            fontWeight="900"
            fontFamily="system-ui, -apple-system, sans-serif"
            letterSpacing="0.3"
          >
            PPT
          </text>
        </svg>
      );

    case 'folder':
      return (
        <svg
          viewBox="0 0 32 32"
          fill="none"
          xmlns="http://www.w3.org/2000/svg"
          className={`${sizeClass} ${className} flex-shrink-0 drop-shadow-sm select-none`}
        >
          <defs>
            <linearGradient id="folderBack" x1="2" y1="4" x2="30" y2="28" gradientUnits="userSpaceOnUse">
              <stop stopColor="#0284C7" />
              <stop offset="1" stopColor="#0369A1" />
            </linearGradient>
            <linearGradient id="folderFront" x1="2" y1="12" x2="30" y2="28" gradientUnits="userSpaceOnUse">
              <stop stopColor="#38BDF8" />
              <stop offset="1" stopColor="#0284C7" />
            </linearGradient>
          </defs>
          {/* Back folder body */}
          <path
            d="M3 7C3 5.89543 3.89543 5 5 5H12L15 8H27C28.1046 8 29 8.89543 29 10V25C29 26.1046 28.1046 27 27 27H5C3.89543 27 3 26.1046 3 25V7Z"
            fill="url(#folderBack)"
          />
          {/* Front pocket with stylish angle */}
          <path
            d="M2 13C2 11.8954 2.89543 11 4 11H28C29.1046 11 30 11.8954 30 13L29 25.5C29 26.6046 28.1046 27.5 27 27.5H5C3.89543 27.5 3 26.6046 3 25.5L2 13Z"
            fill="url(#folderFront)"
            stroke="#7DD3FC"
            strokeWidth="0.75"
          />
        </svg>
      );

    case 'image':
      return (
        <svg
          viewBox="0 0 32 32"
          fill="none"
          xmlns="http://www.w3.org/2000/svg"
          className={`${sizeClass} ${className} flex-shrink-0 drop-shadow-sm select-none`}
        >
          <defs>
            <linearGradient id="imgBg" x1="4" y1="2" x2="28" y2="30" gradientUnits="userSpaceOnUse">
              <stop stopColor="#8B5CF6" />
              <stop offset="1" stopColor="#6D28D9" />
            </linearGradient>
            <linearGradient id="imgFold" x1="20" y1="2" x2="28" y2="10" gradientUnits="userSpaceOnUse">
              <stop stopColor="#DDD6FE" stopOpacity="0.8" />
              <stop offset="1" stopColor="#A78BFA" stopOpacity="0.3" />
            </linearGradient>
          </defs>
          <path
            d="M6 3C6 2.44772 6.44772 2 7 2H20L28 10V29C28 29.5523 27.5523 30 27 30H7C6.44772 30 6 29.5523 6 29V3Z"
            fill="url(#imgBg)"
          />
          <path d="M20 2V9C20 9.55228 20.4477 10 21 10H28L20 2Z" fill="url(#imgFold)" />
          {/* Mountains & Sun */}
          <circle cx="12" cy="13" r="2" fill="#FDE047" />
          <path d="M9 21L14 15L17 18L20 14L24 21H9Z" fill="white" fillOpacity="0.8" />
          {/* IMG Badge */}
          <rect x="3" y="18" width="18" height="10" rx="2.5" fill="#4C1D95" stroke="#C4B5FD" strokeWidth="1" />
          <text
            x="12"
            y="25.5"
            textAnchor="middle"
            fill="white"
            fontSize="6"
            fontWeight="900"
            fontFamily="system-ui, -apple-system, sans-serif"
            letterSpacing="0.3"
          >
            IMG
          </text>
        </svg>
      );

    case 'archive':
      return (
        <svg
          viewBox="0 0 32 32"
          fill="none"
          xmlns="http://www.w3.org/2000/svg"
          className={`${sizeClass} ${className} flex-shrink-0 drop-shadow-sm select-none`}
        >
          <defs>
            <linearGradient id="zipBg" x1="4" y1="2" x2="28" y2="30" gradientUnits="userSpaceOnUse">
              <stop stopColor="#F59E0B" />
              <stop offset="1" stopColor="#B45309" />
            </linearGradient>
            <linearGradient id="zipFold" x1="20" y1="2" x2="28" y2="10" gradientUnits="userSpaceOnUse">
              <stop stopColor="#FEF3C7" stopOpacity="0.8" />
              <stop offset="1" stopColor="#FBBF24" stopOpacity="0.3" />
            </linearGradient>
          </defs>
          <path
            d="M6 3C6 2.44772 6.44772 2 7 2H20L28 10V29C28 29.5523 27.5523 30 27 30H7C6.44772 30 6 29.5523 6 29V3Z"
            fill="url(#zipBg)"
          />
          <path d="M20 2V9C20 9.55228 20.4477 10 21 10H28L20 2Z" fill="url(#zipFold)" />
          {/* Zipper Teeth */}
          <g fill="white" fillOpacity="0.9">
            <rect x="15" y="6" width="3" height="1.5" rx="0.5" />
            <rect x="13.5" y="8" width="3" height="1.5" rx="0.5" />
            <rect x="15" y="10" width="3" height="1.5" rx="0.5" />
            <rect x="13.5" y="12" width="3" height="1.5" rx="0.5" />
            <rect x="15" y="14" width="3" height="1.5" rx="0.5" />
          </g>
          {/* ZIP Badge */}
          <rect x="3" y="18" width="18" height="10" rx="2.5" fill="#78350F" stroke="#FDE68A" strokeWidth="1" />
          <text
            x="12"
            y="25.5"
            textAnchor="middle"
            fill="white"
            fontSize="6.5"
            fontWeight="900"
            fontFamily="system-ui, -apple-system, sans-serif"
            letterSpacing="0.3"
          >
            ZIP
          </text>
        </svg>
      );

    case 'file':
    default:
      return (
        <svg
          viewBox="0 0 32 32"
          fill="none"
          xmlns="http://www.w3.org/2000/svg"
          className={`${sizeClass} ${className} flex-shrink-0 drop-shadow-sm select-none`}
        >
          <defs>
            <linearGradient id="fileBg" x1="4" y1="2" x2="28" y2="30" gradientUnits="userSpaceOnUse">
              <stop stopColor="#64748B" />
              <stop offset="1" stopColor="#334155" />
            </linearGradient>
            <linearGradient id="fileFold" x1="20" y1="2" x2="28" y2="10" gradientUnits="userSpaceOnUse">
              <stop stopColor="#CBD5E1" stopOpacity="0.8" />
              <stop offset="1" stopColor="#94A3B8" stopOpacity="0.3" />
            </linearGradient>
          </defs>
          <path
            d="M6 3C6 2.44772 6.44772 2 7 2H20L28 10V29C28 29.5523 27.5523 30 27 30H7C6.44772 30 6 29.5523 6 29V3Z"
            fill="url(#fileBg)"
          />
          <path d="M20 2V9C20 9.55228 20.4477 10 21 10H28L20 2Z" fill="url(#fileFold)" />
          {/* Subtle document lines */}
          <rect x="10" y="14" width="12" height="2" rx="1" fill="white" fillOpacity="0.6" />
          <rect x="10" y="18" width="12" height="2" rx="1" fill="white" fillOpacity="0.6" />
          <rect x="10" y="22" width="7" height="2" rx="1" fill="white" fillOpacity="0.4" />
        </svg>
      );
  }
};

export default FileFormatIcon;
