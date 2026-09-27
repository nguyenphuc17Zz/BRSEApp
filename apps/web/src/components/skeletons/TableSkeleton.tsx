import React from 'react';
import { Skeleton } from './Skeleton';

interface TableSkeletonProps {
  rows?: number;
  columns?: number;
}

export const TableSkeleton: React.FC<TableSkeletonProps> = ({ rows = 5, columns = 4 }) => {
  return (
    <div className="space-y-3 p-4">
      {/* Header bar placeholder */}
      <div className="flex items-center gap-4 pb-3 border-b border-border-subtle">
        {Array.from({ length: columns }).map((_, cIdx) => (
          <Skeleton key={cIdx} className={`h-3 ${cIdx === 0 ? 'w-28' : 'flex-1'} rounded`} />
        ))}
      </div>

      {/* Row items */}
      <div className="space-y-2.5">
        {Array.from({ length: rows }).map((_, rIdx) => (
          <div
            key={rIdx}
            className="flex items-center gap-4 p-3 rounded-lg bg-surface-subtle border border-border-subtle"
          >
            <Skeleton className="w-6 h-6 rounded flex-shrink-0" />
            <Skeleton className="h-4 w-1/4 rounded" />
            <Skeleton className="h-4 flex-1 rounded" />
            <Skeleton className="h-4 w-20 rounded" />
            <Skeleton className="h-6 w-16 rounded-md flex-shrink-0" />
          </div>
        ))}
      </div>
    </div>
  );
};
