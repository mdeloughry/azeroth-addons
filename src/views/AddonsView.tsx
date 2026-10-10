import { ButtonItem, PanelSection, PanelSectionRow } from "@decky/ui";
import { FC } from "react";

import { AddonList } from "../components/AddonRow";
import { OperationStatus } from "../components/OperationStatus";
import { usePlugin } from "../state";
import { InstallationSelector } from "./InstallationSelector";

const COUNT: React.CSSProperties = {
  display: "flex",
  gap: "10px",
  alignItems: "baseline",
  fontVariantNumeric: "tabular-nums",
};

export const AddonsView: FC = () => {
  const plugin = usePlugin();
  const installation = plugin.selected;
  const installed = plugin.installed;
  const busy = plugin.busy !== null;

  if (!installation) {
    return (
      <PanelSection title="Installed addons">
        <PanelSectionRow>
          <div style={{ opacity: 0.75, fontSize: "12px" }}>
            Add a World of Warcraft installation to manage its addons.
          </div>
        </PanelSectionRow>
      </PanelSection>
    );
  }

  const updateCount = Math.max(plugin.updates.length, installed?.counts.updates ?? 0);
  const blocked = !installation.available;
  const running = Boolean(installed?.running);

  return (
    <>
      <InstallationSelector />

      <PanelSection title={`${installation.displayName}`}>
        <PanelSectionRow>
          <div style={COUNT}>
            <span style={{ fontSize: "20px", fontWeight: 600 }}>{installed?.counts.installed ?? 0}</span>
            <span style={{ opacity: 0.7 }}>installed</span>
            <span style={{ fontSize: "20px", fontWeight: 600, color: updateCount ? "#f0ad4e" : undefined }}>
              {updateCount}
            </span>
            <span style={{ opacity: 0.7 }}>updates</span>
          </div>
        </PanelSectionRow>

        {!installation.available ? (
          <PanelSectionRow>
            <div style={{ fontSize: "12px", opacity: 0.85 }}>
              This installation is not available right now. Reconnect its drive, then rescan.
            </div>
          </PanelSectionRow>
        ) : null}

        {running ? (
          <PanelSectionRow>
            <div style={{ fontSize: "12px", opacity: 0.85 }}>
              {installation.flavourLabel} is running. Close the game before changing its addons.
            </div>
          </PanelSectionRow>
        ) : null}

        <PanelSectionRow>
          <ButtonItem
            layout="below"
            disabled={busy || blocked || updateCount === 0}
            onClick={() => void plugin.updateAll()}
          >
            {updateCount > 0 ? `Update All (${updateCount})` : "Update All"}
          </ButtonItem>
        </PanelSectionRow>
        <PanelSectionRow>
          <ButtonItem
            layout="below"
            disabled={busy || blocked || plugin.checkingUpdates}
            onClick={() => void plugin.checkUpdates()}
          >
            {plugin.checkingUpdates ? "Checking…" : "Check for updates"}
          </ButtonItem>
        </PanelSectionRow>
        <PanelSectionRow>
          <ButtonItem
            layout="below"
            disabled={busy || blocked}
            onClick={() => void plugin.loadInstalled({ refresh: true })}
          >
            {plugin.loadingInstalled ? "Refreshing…" : "Refresh"}
          </ButtonItem>
        </PanelSectionRow>
      </PanelSection>

      <OperationStatus />

      {plugin.updates.length > 0 ? (
        <AddonList
          title="Updates"
          addons={plugin.updates}
          actions={{ showUpdate: true }}
          emptyMessage="Everything is up to date."
        />
      ) : null}

      <AddonList
        title="Installed addons"
        addons={installed?.addons ?? []}
        spinner={plugin.loadingInstalled}
        actions={{ showUpdate: true, showRemove: true, showRollback: true }}
        emptyMessage="No addons are managed for this installation yet. Use Find Addons to install one."
      />

      {installed && installed.unmanaged.length > 0 ? (
        <AddonList
          title={`Not managed by Azeroth Addons (${installed.unmanaged.length})`}
          addons={installed.unmanaged}
          emptyMessage=""
        />
      ) : null}
    </>
  );
};
