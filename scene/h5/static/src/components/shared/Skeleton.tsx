import React from 'react';
import './Skeleton.css';

interface SkeletonProps {
  count?: number;
  width?: string | number;
  height?: string | number;
  circle?: boolean;
  className?: string;
}

export function SkeletonLine({ width, height = 14, className = '' }: SkeletonProps) {
  return (
    <div
      className={`skeleton-line ${className}`}
      style={{
        width: typeof width === 'number' ? `${width}px` : width,
        height: typeof height === 'number' ? `${height}px` : height,
      }}
    />
  );
}

export function SkeletonCircle({ size = 32, className = '' }: { size?: number; className?: string }) {
  return (
    <div
      className={`skeleton-circle ${className}`}
      style={{ width: size, height: size }}
    />
  );
}

export function SkeletonCard({ className = '' }: { className?: string }) {
  return (
    <div className={`skeleton-card ${className}`}>
      <div className="skeleton-card-head">
        <SkeletonCircle size={28} />
        <div className="skeleton-card-meta">
          <SkeletonLine width="60%" height={14} />
          <SkeletonLine width="40%" height={10} />
        </div>
      </div>
      <SkeletonLine width="90%" height={12} />
      <SkeletonLine width="70%" height={12} />
    </div>
  );
}

export function SkeletonList({ count = 3 }: { count?: number }) {
  return (
    <div className="skeleton-list">
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className="skeleton-list-item">
          <SkeletonCircle size={28} />
          <div className="skeleton-list-text">
            <SkeletonLine width="40%" height={13} />
            <SkeletonLine width="25%" height={10} />
          </div>
        </div>
      ))}
    </div>
  );
}
