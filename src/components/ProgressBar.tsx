import { FC } from "react";

const TRACK: React.CSSProperties = {
  height: "6px",
  borderRadius: "3px",
  background: "rgba(255,255,255,0.12)",
  overflow: "hidden",
};

const FILL: React.CSSProperties = {
  height: "100%",
  background: "#67a5eb",
  transition: "width 160ms linear",
};

/** A plain determinate bar. Indeterminate when there is no total. */
export const ProgressBar: FC<{ current: number; total: number }> = ({ current, total }) => {
  if (total <= 0) {
    return (
      <div style={TRACK} aria-label="Working">
        <div style={{ ...FILL, width: "35%" }} />
      </div>
    );
  }
  const percent = Math.max(0, Math.min(100, Math.round((current / total) * 100)));
  return (
    <div style={TRACK} aria-label={`${percent}% complete`}>
      <div style={{ ...FILL, width: `${percent}%` }} />
    </div>
  );
};
