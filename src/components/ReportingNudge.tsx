import { ButtonItem, PanelSection, PanelSectionRow } from "@decky/ui";
import { FC } from "react";

import { usePlugin } from "../state";

/**
 * Opt-in prompt shown after an error, until the user answers it.
 *
 * Rendering is driven by `plugin.reportingNudge`, which the provider sets from
 * the local journal (on boot) and from the backend `az:error` nudge event.
 */
export const ReportingNudge: FC = () => {
  const plugin = usePlugin();
  if (!plugin.reportingNudge) return null;

  return (
    <PanelSection title="Help fix this?">
      <PanelSectionRow>
        <div style={{ fontSize: "12px", opacity: 0.85 }}>
          A redacted error was recorded on this device - nothing has been sent. Send future redacted errors to the
          plugin developer? Diagnostics shows exactly what would be sent.
        </div>
      </PanelSectionRow>
      <PanelSectionRow>
        <ButtonItem
          layout="below"
          disabled={plugin.busy !== null}
          onClick={() => void plugin.answerReportingNudge(true)}
        >
          Send error reports
        </ButtonItem>
      </PanelSectionRow>
      <PanelSectionRow>
        <ButtonItem
          layout="below"
          disabled={plugin.busy !== null}
          onClick={() => void plugin.answerReportingNudge(false)}
        >
          Don't ask again
        </ButtonItem>
      </PanelSectionRow>
    </PanelSection>
  );
};
