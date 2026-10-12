import { ButtonItem, DialogButton, Focusable, Navigation, PanelSection, PanelSectionRow, Spinner } from "@decky/ui";
import { FC, useMemo } from "react";
import { FaCog, FaSearch } from "react-icons/fa";

import { AddonList } from "../components/AddonRow";
import { ReportingNudge } from "../components/ReportingNudge";
import { PageTab, TAB_ROUTES } from "../routes";
import { usePlugin } from "../state";
import { InstallationSelector } from "./InstallationSelector";

const ICON: React.CSSProperties = {
  display: "inline-flex", alignItems: "center", justifyContent: "center",
  width: "36px", minWidth: "36px", height: "36px", padding: 0, margin: 0, flex: "0 0 36px",
};

/** Quick Access Menu: installed addons first, secondary navigation last. */
export const MainPanel: FC = () => {
  const plugin = usePlugin();
  const installation = plugin.selected;
  const engine = plugin.status?.engine ?? plugin.engines[0] ?? null;
  const busy = plugin.busy !== null;
  const blocked = busy || !installation?.available || Boolean(plugin.installed?.running);
  const addons = useMemo(() => {
    const updates = new Map(plugin.updates.map((addon) => [addon.id.toLowerCase(), addon]));
    return (plugin.installed?.addons ?? [])
      .map((addon) => updates.has(addon.id.toLowerCase()) ? { ...addon, ...updates.get(addon.id.toLowerCase()) } : addon)
      .sort((a, b) => Number(b.state === "update-available") - Number(a.state === "update-available") || a.name.localeCompare(b.name));
  }, [plugin.installed, plugin.updates]);
  const updateCount = addons.filter((addon) => addon.state === "update-available").length;

  const open = (tab: PageTab) => {
    Navigation.Navigate(TAB_ROUTES[tab]);
    Navigation.CloseSideMenus();
  };

  if (plugin.booting && !plugin.status) {
    return (
      <PanelSection><PanelSectionRow>
        <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
          <Spinner style={{ width: "16px", height: "16px" }} />
          <span>Loading addons…</span>
        </div>
      </PanelSectionRow></PanelSection>
    );
  }

  return (
    <>
      <PanelSection>
        <PanelSectionRow>
          <Focusable style={{ display: "flex", alignItems: "center", gap: "8px", paddingBlock: "6px" }} flow-children="row">
            <div style={{ flex: "1 1 auto", minWidth: 0 }}>
              <div style={{ fontWeight: 600, overflowWrap: "anywhere" }}>{installation?.displayName ?? "Your addons"}</div>
              {installation ? <div style={{ fontSize: "12px", opacity: 0.7, marginTop: "4px" }}>{addons.length} installed · {updateCount} {updateCount === 1 ? "update" : "updates"}</div> : null}
            </div>
            <DialogButton style={ICON} aria-label="Find addons" onOKActionDescription="Find addons" onClick={() => open("find")}>
              <FaSearch aria-hidden="true" />
            </DialogButton>
            <DialogButton style={ICON} aria-label="Settings" onOKActionDescription="Settings" onClick={() => open("settings")}>
              <FaCog aria-hidden="true" />
            </DialogButton>
          </Focusable>
        </PanelSectionRow>
        {engine && engine.state !== "ready" ? <PanelSectionRow><div style={{ fontSize: "12px", opacity: 0.75 }}>{engine.message ?? `Addon engine: ${engine.state}`}</div></PanelSectionRow> : null}
        {installation && (!installation.available || plugin.installed?.running) ? <PanelSectionRow><div style={{ fontSize: "12px", opacity: 0.75 }}>{!installation.available ? "Reconnect this installation’s drive to manage addons." : "Close World of Warcraft to change addons."}</div></PanelSectionRow> : null}
      </PanelSection>

      {plugin.installations.length > 1 ? <InstallationSelector /> : null}

      {installation ? (
        <>
          <PanelSection><PanelSectionRow>
            <ButtonItem layout="below" disabled={blocked || updateCount === 0} onClick={() => void plugin.updateAll()}>
              {updateCount > 0 ? `Update All (${updateCount})` : "Update All"}
            </ButtonItem>
          </PanelSectionRow></PanelSection>

          <AddonList title="Installed addons" addons={addons} compact spinner={plugin.loadingInstalled}
            actions={{ showUpdate: true, showRemove: true }}
            emptyMessage="No managed addons yet. Use the search icon to find one." />
        </>
      ) : (
        <PanelSection><PanelSectionRow>
          <div style={{ fontSize: "12px", opacity: 0.75 }}>Find or add a World of Warcraft installation first.</div>
        </PanelSectionRow></PanelSection>
      )}

      <PanelSection title="More">
        {installation ? <>
          <PanelSectionRow><ButtonItem layout="below" disabled={blocked || plugin.checkingUpdates} onClick={() => void plugin.checkUpdates()}>
            {plugin.checkingUpdates ? "Checking…" : "Check for updates"}
          </ButtonItem></PanelSectionRow>
          <PanelSectionRow><ButtonItem layout="below" disabled={busy || plugin.loadingInstalled || !installation.available} onClick={() => void plugin.loadInstalled({ refresh: true })}>
            {plugin.loadingInstalled ? "Refreshing…" : "Refresh list"}
          </ButtonItem></PanelSectionRow>
          <PanelSectionRow><ButtonItem layout="below" onClick={() => open("addons")}>Open addon manager</ButtonItem></PanelSectionRow>
        </> : <PanelSectionRow><ButtonItem layout="below" disabled={busy} onClick={() => void plugin.rescan()}>Find World of Warcraft</ButtonItem></PanelSectionRow>}
        <PanelSectionRow><ButtonItem layout="below" onClick={() => open("installations")}>Manage installations</ButtonItem></PanelSectionRow>
        <PanelSectionRow><ButtonItem layout="below" onClick={() => open("diagnostics")}>Diagnostics</ButtonItem></PanelSectionRow>
      </PanelSection>
      <ReportingNudge />
    </>
  );
};
