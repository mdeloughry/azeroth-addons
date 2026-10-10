import { ButtonItem, Navigation, PanelSection, PanelSectionRow, Spinner } from "@decky/ui";
import { FC } from "react";

import { AddonList } from "../components/AddonRow";
import { AvailabilityBadge, EngineStateBadge } from "../components/Badges";
import { OperationStatus } from "../components/OperationStatus";
import { ROUTE } from "../routes";
import { usePlugin } from "../state";

const HEADER: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: "8px",
  padding: "8px 0",
};

const COUNTS: React.CSSProperties = {
  display: "flex",
  gap: "12px",
  fontSize: "12px",
  opacity: 0.85,
};

/** The compact Quick Access Menu panel: status, counts, Update All, entry points. */
export const MainPanel: FC = () => {
  const plugin = usePlugin();
  const engine = plugin.status?.engine ?? plugin.engines[0] ?? null;
  const installation = plugin.selected;
  const counts = plugin.installed?.counts;
  const updateCount = Math.max(plugin.updates.length, counts?.updates ?? 0);
  const topUpdates = plugin.updates.slice(0, 5);

  const open = () => {
    Navigation.Navigate(ROUTE);
    Navigation.CloseSideMenus();
  };

  if (plugin.booting && !plugin.status) {
    return (
      <PanelSection>
        <PanelSectionRow>
          <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
            <Spinner style={{ width: "16px", height: "16px" }} />
            <span>Starting Azeroth Addons…</span>
          </div>
        </PanelSectionRow>
      </PanelSection>
    );
  }

  return (
    <>
      <PanelSection>
        <PanelSectionRow>
          <div style={HEADER}>
            <span style={{ fontWeight: 700, letterSpacing: "0.08em", fontSize: "13px" }}>AZEROTH ADDONS</span>
            {engine ? <EngineStateBadge state={engine.state} label={engine.version ?? undefined} /> : null}
          </div>
        </PanelSectionRow>

        {installation ? (
          <PanelSectionRow>
            <div>
              <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                <span style={{ fontWeight: 500 }}>{installation.displayName}</span>
                <AvailabilityBadge available={installation.available} running={plugin.installed?.running} />
              </div>
              <div style={{ ...COUNTS, marginTop: "4px" }}>
                <span>{counts?.installed ?? 0} installed</span>
                <span style={{ color: updateCount > 0 ? "#f0ad4e" : undefined }}>{updateCount} updates</span>
              </div>
            </div>
          </PanelSectionRow>
        ) : (
          <PanelSectionRow>
            <div style={{ opacity: 0.75, fontSize: "12px" }}>
              No World of Warcraft installation registered yet.
            </div>
          </PanelSectionRow>
        )}
      </PanelSection>

      <OperationStatus />

      {installation ? (
        <PanelSection>
          <PanelSectionRow>
            <ButtonItem
              layout="below"
              disabled={plugin.busy !== null || !installation.available || updateCount === 0}
              onClick={() => void plugin.updateAll()}
            >
              {updateCount > 0 ? `Update All (${updateCount})` : "Update All"}
            </ButtonItem>
          </PanelSectionRow>
          <PanelSectionRow>
            <ButtonItem layout="below" onClick={open}>
              Find Addons
            </ButtonItem>
          </PanelSectionRow>
          <PanelSectionRow>
            <ButtonItem layout="below" onClick={open}>
              Manage Installations
            </ButtonItem>
          </PanelSectionRow>
        </PanelSection>
      ) : (
        <PanelSection>
          <PanelSectionRow>
            <ButtonItem layout="below" disabled={plugin.busy !== null} onClick={() => void plugin.rescan()}>
              Find World of Warcraft
            </ButtonItem>
          </PanelSectionRow>
          <PanelSectionRow>
            <ButtonItem layout="below" onClick={open}>
              Open Azeroth Addons
            </ButtonItem>
          </PanelSectionRow>
        </PanelSection>
      )}

      {topUpdates.length > 0 ? (
        <AddonList title="Updates available" addons={topUpdates} actions={{ showUpdate: true }} />
      ) : null}

      {updateCount > topUpdates.length ? (
        <PanelSection>
          <PanelSectionRow>
            <div style={{ fontSize: "11px", opacity: 0.65 }}>
              +{updateCount - topUpdates.length} more inside Azeroth Addons.
            </div>
          </PanelSectionRow>
        </PanelSection>
      ) : null}
    </>
  );
};
