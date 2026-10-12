import { PanelSection, PanelSectionRow, Spinner } from "@decky/ui";
import { FC } from "react";

import { usePlugin } from "../state";
import { ProgressBar } from "./ProgressBar";

const OPERATION_LABELS: Record<string, string> = {
  install: "Installing",
  update: "Updating",
  update_all: "Updating",
  remove: "Removing",
  rollback: "Rolling back",
};

/** Live progress for the operation currently running on this installation. */
export const OperationStatus: FC = () => {
  const { operation, selected, busy } = usePlugin();
  if (!operation || operation.installationId !== selected?.id) return null;

  const label = OPERATION_LABELS[operation.kind] ?? operation.kind;
  const counting = operation.total > 0;
  const detail = operation.addon?.name ?? operation.message ?? "";

  return (
    <PanelSection>
      <PanelSectionRow>
        <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "4px" }}>
          {busy && operation.phase !== "failed" && operation.phase !== "done" ? <Spinner style={{ width: "16px", height: "16px" }} /> : null}
          <span style={{ fontWeight: 500 }}>{label}</span>
          {counting ? (
            <span style={{ marginLeft: "auto", fontVariantNumeric: "tabular-nums", opacity: 0.8 }}>
              {operation.current} / {operation.total}
            </span>
          ) : null}
        </div>
      </PanelSectionRow>
      <PanelSectionRow>
        <ProgressBar current={operation.current} total={operation.total} />
      </PanelSectionRow>
      {detail ? (
        <PanelSectionRow>
          <div style={{ fontSize: "11px", opacity: 0.7 }}>{detail}</div>
        </PanelSectionRow>
      ) : null}
      {busy ? null : (
        <PanelSectionRow>
          <div style={{ fontSize: "11px", opacity: 0.6 }}>{operation.phase === "failed" ? "Failed." : "Finished."}</div>
        </PanelSectionRow>
      )}
    </PanelSection>
  );
};
