import { ButtonItem, Focusable, Navigation, PanelSection, PanelSectionRow, Spinner } from "@decky/ui";
import { FC, useState } from "react";

import { Badge } from "../components/Badges";
import { usePlugin } from "../state";
import { AddonsView } from "./AddonsView";
import { InstallationsView } from "./InstallationsView";
import { SearchView } from "./SearchView";
import { SettingsView } from "./SettingsView";

type Tab = "addons" | "find" | "installations" | "settings";

const TABS: { id: Tab; label: string }[] = [
  { id: "addons", label: "Addons" },
  { id: "find", label: "Find Addons" },
  { id: "installations", label: "Installations" },
  { id: "settings", label: "Settings" },
];

const HEADER: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: "10px",
  padding: "4px 0 10px",
};

const NAV: React.CSSProperties = {
  display: "flex",
  gap: "6px",
  flexWrap: "wrap",
  paddingBottom: "6px",
  borderBottom: "1px solid rgba(255,255,255,0.12)",
};

const NAV_ITEM: React.CSSProperties = {
  padding: "6px 12px",
  borderRadius: "3px",
  background: "rgba(255,255,255,0.08)",
  fontSize: "13px",
};

const NAV_ITEM_ACTIVE: React.CSSProperties = {
  ...NAV_ITEM,
  background: "#1a9fff",
  color: "#fff",
  fontWeight: 600,
};

/** The full-screen, controller-navigable Azeroth Addons page. */
export const FullPage: FC<{ initialTab?: Tab }> = ({ initialTab = "addons" }) => {
  const plugin = usePlugin();
  const [tab, setTab] = useState<Tab>(initialTab);
  const engine = plugin.status?.engine ?? plugin.engines[0] ?? null;
  const updateCount = Math.max(plugin.updates.length, plugin.installed?.counts.updates ?? 0);

  return (
    <div style={{ padding: "16px", height: "100%", overflowY: "auto" }}>
      <Focusable style={HEADER}>
        <span style={{ fontSize: "19px", fontWeight: 700, letterSpacing: "0.06em" }}>AZEROTH ADDONS</span>
        {engine ? (
          <Badge tone={engine.state === "ready" ? "ok" : engine.state === "error" ? "error" : "info"}>
            {engine.displayName} {engine.version ?? engine.state}
          </Badge>
        ) : null}
        {updateCount > 0 ? <Badge tone="warn">{updateCount} updates</Badge> : null}
        <div style={{ marginLeft: "auto" }}>
          <ButtonItem
            layout="inline"
            onClick={() => {
              Navigation.NavigateBack();
            }}
          >
            Back
          </ButtonItem>
        </div>
      </Focusable>

      <Focusable style={NAV}>
        {TABS.map((entry) => (
          <Focusable
            key={entry.id}
            style={tab === entry.id ? NAV_ITEM_ACTIVE : NAV_ITEM}
            onClick={() => setTab(entry.id)}
            onOKButton={() => setTab(entry.id)}
          >
            {entry.label}
          </Focusable>
        ))}
      </Focusable>

      {plugin.error ? (
        <PanelSection>
          <PanelSectionRow>
            <div style={{ fontSize: "12px", color: "#ef8b8b" }}>{plugin.error}</div>
          </PanelSectionRow>
        </PanelSection>
      ) : null}

      {plugin.booting && plugin.installations.length === 0 ? (
        <PanelSection>
          <PanelSectionRow>
            <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
              <Spinner style={{ width: "16px", height: "16px" }} />
              <span>Starting Azeroth Addons…</span>
            </div>
          </PanelSectionRow>
        </PanelSection>
      ) : null}

      {tab === "addons" ? <AddonsView /> : null}
      {tab === "find" ? <SearchView /> : null}
      {tab === "installations" ? <InstallationsView /> : null}
      {tab === "settings" ? <SettingsView /> : null}
    </div>
  );
};
