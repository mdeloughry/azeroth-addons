import { FC, ReactNode } from "react";

import { AddonState } from "../types";

const BADGE_BASE: React.CSSProperties = {
  display: "inline-block",
  padding: "1px 6px",
  borderRadius: "3px",
  fontSize: "10px",
  fontWeight: 600,
  letterSpacing: "0.04em",
  textTransform: "uppercase",
  lineHeight: "15px",
  whiteSpace: "nowrap",
};

const TONES: Record<string, React.CSSProperties> = {
  ok: { background: "rgba(94, 190, 96, 0.22)", color: "#8ddb8f" },
  warn: { background: "rgba(240, 173, 78, 0.22)", color: "#f0ad4e" },
  error: { background: "rgba(214, 84, 84, 0.24)", color: "#ef8b8b" },
  info: { background: "rgba(103, 165, 235, 0.22)", color: "#92c1f0" },
  muted: { background: "rgba(255, 255, 255, 0.10)", color: "rgba(255,255,255,0.62)" },
};

export const Badge: FC<{ tone: keyof typeof TONES; children: ReactNode; title?: string }> = ({
  tone,
  children,
  title,
}) => (
  <span style={{ ...BADGE_BASE, ...TONES[tone] }} title={title}>
    {children}
  </span>
);

const STATE_TONES: Record<AddonState, keyof typeof TONES> = {
  current: "ok",
  "update-available": "warn",
  installing: "info",
  updating: "info",
  unmanaged: "muted",
  error: "error",
};

const STATE_LABELS: Record<AddonState, string> = {
  current: "Current",
  "update-available": "Update",
  installing: "Installing",
  updating: "Updating",
  unmanaged: "Unmanaged",
  error: "Error",
};

export const StateBadge: FC<{ state: AddonState }> = ({ state }) => (
  <Badge tone={STATE_TONES[state] ?? "muted"}>{STATE_LABELS[state] ?? state}</Badge>
);

export const ProviderBadge: FC<{ label: string }> = ({ label }) => <Badge tone="info">{label}</Badge>;

export const AvailabilityBadge: FC<{ available: boolean; running?: boolean }> = ({ available, running }) => {
  if (running) return <Badge tone="error">Running</Badge>;
  return available ? <Badge tone="ok">Ready</Badge> : <Badge tone="warn">Drive unavailable</Badge>;
};

const ENGINE_TONES: Record<string, keyof typeof TONES> = {
  ready: "ok",
  verifying: "info",
  warming: "info",
  unknown: "muted",
  missing: "warn",
  incompatible: "error",
  error: "error",
};

export const EngineStateBadge: FC<{ state: string; label?: string }> = ({ state, label }) => (
  <Badge tone={ENGINE_TONES[state] ?? "muted"}>{label ?? state}</Badge>
);

const PROVIDER_TONES: Record<string, keyof typeof TONES> = {
  available: "ok",
  "engine-backed": "info",
  degraded: "warn",
  "not-configured": "muted",
  unavailable: "muted",
};

/** Short, scannable labels - the raw states read badly on a 10px badge. */
const PROVIDER_LABELS: Record<string, string> = {
  available: "Ready",
  "engine-backed": "Via engine",
  degraded: "Problem",
  "not-configured": "Not set up",
  unavailable: "Unavailable",
};

export const ProviderStateBadge: FC<{ state: string }> = ({ state }) => (
  <Badge tone={PROVIDER_TONES[state] ?? "muted"}>{PROVIDER_LABELS[state] ?? state.replace("-", " ")}</Badge>
);
