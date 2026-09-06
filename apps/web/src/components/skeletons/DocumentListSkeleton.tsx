import React from 'react';
import { Skeleton } from './Skeleton';

interface DocumentListSkeletonProps {
  count?: number;
}

export const DocumentListSkeleton: React.FC<DocumentListSkeletonProps> = ({ count = 4 }) => {
  return (
    <div className="divide-y divide-slate-800/80">
      {Array.from({ length: count }).map((_, idx) => (
        <div
          key={idx}
          className="p-4 flex items-center justify-between gap-4 animate-pulse"
        >
          <div className="flex items-center gap-3.5 min-w-0 flex-1">
            {/* Format Icon Box */}
            <Skeleton className="w-10 h-10 rounded-lg flex-shrink-0" />

            {/* Document Info */}
            <div className="space-y-2 flex-1 max-w-md">
              <Skeleton className="h-4 w-3/4 rounded" />
              <div className="flex items-center gap-2">
                <Skeleton className="h-3 w-16 rounded" />
                <Skeleton className="h-3 w-24 rounded" />
                <Skeleton className="h-3 w-20 rounded" />
              </div>
            </div>
          </div>

          {/* Action Buttons */}
          <div className="flex items-center gap-2 flex-shrink-0">
            <Skeleton className="w-24 h-7 rounded-md" />
            <Skeleton className="w-20 h-7 rounded-md" />
          </div>
        </div>
      ))}
    </div>
  );
};
