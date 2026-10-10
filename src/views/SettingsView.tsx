import { ButtonItem, Field, PanelSection, PanelSectionRow, ToggleField } from "@decky/ui";
import { FC, useEffect, useState } from "react";

import { api, errorMessage } from "../api";
import { EngineStateBadge, ProviderStateBadge } from "../components/Badges";
import { usePlugin } from "../state";
import { ProfileStatus } from "../types";

const INPUT: React.CSSProperties = {
  width: "100%",
  padding: "6px 8px",
  borderRadius: "3px",
  border: "1px solid rgba(255,255,255,0.2)",
  background: "rgba(0,0,0,0.3)",
  color: "inherit",
  fontSize: "13px",
};

const META: React.CSSProperties = { fontSize: "11px", opacity: 0.65, wordBreak: "break-all" };

const CREDENTIALS: { key: string; label: string; description: string }[] = [
  {
    key: "curseforge",
    label: "CurseForge API key",
    description: "Optional. CurseForge needs a key for downloads.",
  },
  {
    key: "github",
    label: "GitHub token",
    description: "Optional. Raises the rate limit from 60 to 5000 per hour.",
  },
  { key: "wago", label: "Wago token", description: "Optional. Required for Wago addons." },
  {
    key: "wowinterface",
    label: "WoWInterface token",
    description: "Optional. Only used for older retail installs.",
  },
];

/** Advanced settings: engine health, source status, credentials, feature flags. */
export const SettingsView: FC = () => {
  const plugin = usePlugin();
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [profile, setProfile] = useState<ProfileStatus | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const engine = plugin.status?.engine ?? plugin.engines[0] ?? null;
  const binary = plugin.status?.binary;
  const values = plugin.settings?.values ?? {};
  const busy = plugin.busy !== null;

  useEffect(() => {
    if (!plugin.selectedId) {
      setProfile(null);
      return;
    }
    void api
      .getEngineProfile(plugin.selectedId)
      .then(setProfile)
      .catch(() => setProfile(null));
  }, [plugin.selectedId, engine?.state]);

  const warmUp = async () => {
    setNotice(null);
    try {
      const status = await api.prepareEngine();
      setNotice(status.message ?? status.state);
      await plugin.boot({ silent: true });
    } catch (cause) {
      setNotice(errorMessage(cause));
    }
  };

  return (
    <>
      <PanelSection title="Addon engine">
        <PanelSectionRow>
          <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
            <span style={{ fontWeight: 500 }}>{engine?.displayName ?? "Addon engine"}</span>
            {engine ? <EngineStateBadge state={engine.state} /> : null}
          </div>
        </PanelSectionRow>
        <PanelSectionRow>
          <div style={META}>
            bundled {engine?.bundledVersion ?? binary?.bundledVersion ?? "?"}
            {engine?.version ? ` · running ${engine.version}` : ""}
            {engine?.message ? ` · ${engine.message}` : ""}
          </div>
        </PanelSectionRow>
        {engine?.detail ? (
          <PanelSectionRow>
            <div style={META}>{engine.detail}</div>
          </PanelSectionRow>
        ) : null}
        <PanelSectionRow>
          <ButtonItem layout="below" disabled={busy} onClick={() => void warmUp()}>
            {engine?.state === "ready" ? "Re-check the engine" : "Start the engine"}
          </ButtonItem>
        </PanelSectionRow>
        {notice ? (
          <PanelSectionRow>
            <div style={META}>{notice}</div>
          </PanelSectionRow>
        ) : null}
      </PanelSection>

      {profile ? (
        <PanelSection title="Engine profile for the selected installation">
          <PanelSectionRow>
            <div style={{ fontSize: "12px" }}>
              {profile.engineProfile} · {profile.validated ? "validated" : "not validated yet"}
            </div>
          </PanelSectionRow>
          {profile.addonDir ? (
            <PanelSectionRow>
              <div style={META}>{profile.addonDir}</div>
            </PanelSectionRow>
          ) : null}
        </PanelSection>
      ) : null}

      <PanelSection title="Addon sources">
        {plugin.providers.length === 0 ? (
          <PanelSectionRow>
            <div style={META}>Checking sources…</div>
          </PanelSectionRow>
        ) : null}
        {plugin.providers.map((provider) => (
          <PanelSectionRow key={provider.id}>
            {/* One line per source. The long explanation lives in the tooltip. */}
            <div style={{ width: "100%" }} title={provider.detail ?? undefined}>
              <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                <span style={{ fontWeight: 500 }}>{provider.displayName}</span>
                <ProviderStateBadge state={provider.state} />
                <span style={{ marginLeft: "auto", ...META }}>
                  {provider.credentialConfigured
                    ? provider.credentialMode
                    : provider.requiresCredential
                      ? "no key"
                      : ""}
                </span>
              </div>
              {provider.message ? <div style={META}>{provider.message}</div> : null}
            </div>
          </PanelSectionRow>
        ))}
      </PanelSection>

      <PanelSection title="Credentials">
        <PanelSectionRow>
          <div style={META}>Stored on this device only. Never shown again, never sent to the UI.</div>
        </PanelSectionRow>
        {CREDENTIALS.map((entry) => {
          const state = plugin.settings?.credentials?.[entry.key];
          return (
            <PanelSectionRow key={entry.key}>
              <Field label={entry.label} description={entry.description}>
                <input
                  style={INPUT}
                  type="password"
                  placeholder={state?.configured ? `Saved (${state.hint}) — type to replace` : "Not set"}
                  value={drafts[entry.key] ?? ""}
                  onChange={(event) =>
                    setDrafts((previous) => ({ ...previous, [entry.key]: event.currentTarget.value }))
                  }
                />
              </Field>
              <div style={{ display: "flex", gap: "6px", marginTop: "4px" }}>
                <ButtonItem
                  layout="inline"
                  disabled={busy || !(drafts[entry.key] ?? "").trim()}
                  onClick={() => {
                    void plugin.setCredential(entry.key, (drafts[entry.key] ?? "").trim());
                    setDrafts((previous) => ({ ...previous, [entry.key]: "" }));
                  }}
                >
                  Save
                </ButtonItem>
                <ButtonItem
                  layout="inline"
                  disabled={busy || !state?.configured}
                  onClick={() => void plugin.clearCredential(entry.key)}
                >
                  Clear
                </ButtonItem>
              </div>
            </PanelSectionRow>
          );
        })}
      </PanelSection>

      <PanelSection title="Advanced">
        <PanelSectionRow>
          <ToggleField
            label="Experimental rollback"
            description="Enable version rollback. The engine's rollback is interactive, so this is off by default."
            checked={Boolean(values.enableExperimentalRollback)}
            disabled={busy}
            onChange={(value: boolean) => void plugin.saveSettings({ enableExperimentalRollback: value })}
          />
        </PanelSectionRow>
        <PanelSectionRow>
          <ToggleField
            label="Direct CurseForge API"
            description="Prototype. Requires an approved CurseForge credential and respects each author's distribution settings."
            checked={Boolean(values.enableDirectCurseForge)}
            disabled={busy}
            onChange={(value: boolean) => void plugin.saveSettings({ enableDirectCurseForge: value })}
          />
        </PanelSectionRow>
      </PanelSection>

      <PanelSection title="Bundled engine file">
        <PanelSectionRow>
          <div style={META}>
            {binary?.exists
              ? `${binary.path} (${binary.executable ? "executable" : "not executable"})`
              : "The bundled engine binary is missing. Reinstall the plugin."}
          </div>
        </PanelSectionRow>
        <PanelSectionRow>
          <div style={META}>
            {binary?.artifact} · sha256 {binary?.sha256?.slice(0, 16)}…
          </div>
        </PanelSectionRow>
        <PanelSectionRow>
          <div style={META}>Azeroth Addons {plugin.status?.pluginVersion ?? ""}</div>
        </PanelSectionRow>
      </PanelSection>
    </>
  );
};
