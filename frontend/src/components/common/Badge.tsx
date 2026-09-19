import React from "react";

export interface BadgeProps {
  children: React.ReactNode;
  variant?: "default" | "primary" | "success" | "danger";
  style?: React.CSSProperties;
}

export const Badge: React.FC<BadgeProps> = ({ children, variant = "default", style }) => {
  return <span className={`badge badge-${variant}`} style={style}>{children}</span>;
};
