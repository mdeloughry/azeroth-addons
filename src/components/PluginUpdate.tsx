import { ButtonItem, Navigation, PanelSection, PanelSectionRow, ToggleField } from "@decky/ui";
import { FC } from "react";
import { checkPluginUpdate, installPluginUpdate, usePluginUpdater } from "../pluginUpdater";
import { TAB_ROUTES } from "../routes";
import { usePlugin } from "../state";

export const PluginUpdate: FC<{ compact?: boolean }> = ({ compact = false }) => {
  const plugin = usePlugin();
  const update = usePluginUpdater();
  const status = update.status;
  const release = status?.state === "available" ? status.release : null;
  const disabled = Boolean(plugin.busy) || update.checking || update.requesting;
  if (compact && !release) return null;
  return <PanelSection title="Azeroth Addons updates">
    <PanelSectionRow><div style={{ fontSize: "12px", overflowWrap: "anywhere" }}>
      {release ? `Version ${release.version} available · installed ${status?.currentVersion}`
        : update.checking ? "Checking GitHub releases…"
        : status?.state === "up-to-date" ? `Version ${status.currentVersion} · up to date`
        : status?.state === "disabled" ? "Automatic checks are off. You can check manually."
        : status?.message ?? "Updates are downloaded from GitHub releases."}
    </div></PanelSectionRow>
    {release ? <PanelSectionRow><ButtonItem layout="below" disabled={disabled}
      onClick={() => void installPluginUpdate()}>
      {update.requesting ? "Confirm in Decky…" : `Update plugin to ${release.version}`}
    </ButtonItem></PanelSectionRow> : null}
    {compact ? <PanelSectionRow><ButtonItem layout="below" onClick={() => {
      Navigation.Navigate(TAB_ROUTES.settings); Navigation.CloseSideMenus();
    }}>Release details</ButtonItem></PanelSectionRow> : <>
      <PanelSectionRow><ToggleField label="Automatically check for plugin updates"
        description="Check GitHub at startup and hourly while Decky is running. Installation requires your confirmation."
        checked={Boolean(plugin.settings?.values.autoCheckPluginUpdates ?? status?.automatic ?? true)}
        disabled={disabled} onChange={(value: boolean) => {
          void plugin.saveSettings({ autoCheckPluginUpdates: value }).then(() => checkPluginUpdate());
        }} /></PanelSectionRow>
      <PanelSectionRow><ButtonItem layout="below" disabled={disabled} onClick={() => void checkPluginUpdate(true)}>
        {update.checking ? "Checking…" : "Check for plugin updates"}
      </ButtonItem></PanelSectionRow>
      {release?.notes ? <PanelSectionRow><div style={{ whiteSpace: "pre-wrap", fontSize: "12px", overflowWrap: "anywhere" }}>
        {release.notes}
      </div></PanelSectionRow> : null}
      {status?.checkedAt ? <PanelSectionRow><div style={{ fontSize: "11px", opacity: 0.7 }}>
        Last check: {new Date(status.checkedAt * 1000).toLocaleString()}
      </div></PanelSectionRow> : null}
      <PanelSectionRow><div style={{ fontSize: "11px", overflowWrap: "anywhere", opacity: 0.8 }}>
        Finish addon operations before updating. Decky verifies the checksum and reloads the plugin; settings stay on-device.
        {" "}Manual install URL: {status?.manualDownloadUrl ?? "https://github.com/mdeloughry/azeroth-addons/releases/latest/download/azeroth-addons.zip"}
      </div></PanelSectionRow>
    </>}
    {update.message ? <PanelSectionRow><div role="status" style={{ fontSize: "12px", overflowWrap: "anywhere" }}>{update.message}</div></PanelSectionRow> : null}
  </PanelSection>;
};
