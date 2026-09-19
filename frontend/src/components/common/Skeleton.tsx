import React from "react";

export interface SkeletonProps {
  width?: string | number;
  height?: string | number;
  borderRadius?: string | number;
  style?: React.CSSProperties;
  className?: string;
}

export const Skeleton: React.FC<SkeletonProps> = ({
  width = "100%",
  height = "1rem",
  borderRadius = "var(--radius-sm)",
  style,
  className = "",
}) => {
  return (
    <div
      className={`skeleton-shimmer ${className}`}
      style={{
        width,
        height,
        borderRadius,
        ...style,
      }}
    />
  );
};

export const ProductCardSkeleton: React.FC = () => {
  return (
    <div
      className="card"
      style={{
        padding: "1.25rem",
        display: "flex",
        flexDirection: "column",
        gap: "0.875rem",
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between" }}>
        <Skeleton width="40%" height="1.25rem" borderRadius="var(--radius-full)" />
      </div>
      <Skeleton height="140px" borderRadius="var(--radius-md)" style={{ margin: "0.5rem 0" }} />
      <Skeleton width="30%" height="0.875rem" />
      <Skeleton width="85%" height="1.25rem" />
      <div style={{ marginTop: "auto", paddingTop: "0.75rem", borderTop: "1px solid var(--color-border)" }}>
        <Skeleton width="45%" height="0.875rem" style={{ marginBottom: "0.35rem" }} />
        <Skeleton width="60%" height="1.5rem" />
      </div>
    </div>
  );
};
