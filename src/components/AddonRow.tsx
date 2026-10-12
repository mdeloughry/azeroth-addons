import {
  ConfirmModal,
  DialogButton,
  Focusable,
  Navigation,
  PanelSection,
  PanelSectionRow,
  showModal,
} from "@decky/ui";
import { FC, useMemo } from "react";
import { FaDownload, FaExternalLinkAlt, FaHistory, FaSyncAlt, FaTrashAlt } from "react-icons/fa";

import { usePlugin } from "../state";
import { Addon } from "../types";
import { Badge, ProviderBadge, StateBadge } from "./Badges";

const ROW: React.CSSProperties = {
  display: "flex",
  flexDirection: "column",
  gap: "8px",
  padding: "14px 0",
  borderTop: "1px solid rgba(255,255,255,0.07)",
};

const NAME: React.CSSProperties = {
  minWidth: 0,
  width: "100%",
};

const META: React.CSSProperties = {
  display: "flex",
  flexWrap: "wrap",
  gap: "6px",
  alignItems: "center",
  fontSize: "11px",
  lineHeight: "1.5",
};

const ICON_BUTTON: React.CSSProperties = {
  display: "inline-flex",
  alignItems: "center",
  justifyContent: "center",
  width: "36px",
  minWidth: "36px",
  height: "36px",
  padding: 0,
  flex: "0 0 36px",
  margin: 0,
};

const FLAVOUR_LABELS: Record<string, string> = {
  retail: "Retail", "classic-era": "Classic Era", forever: "Forever", classic: "Classic",
};

const VERSION: React.CSSProperties = {
  fontVariantNumeric: "tabular-nums",
};

export interface AddonRowActions {
  showInstall?: boolean;
  showUpdate?: boolean;
  showRemove?: boolean;
  showRollback?: boolean;
  installed?: boolean;
}

export const AddonRow: FC<{
  addon: Addon;
  actions?: AddonRowActions;
  disabled?: boolean;
}> = ({ addon, actions, disabled }) => {
  const plugin = usePlugin();
  const busy = plugin.busy !== null;
  const blocked = busy || disabled;

  const version = addon.installedVersion
    ? addon.availableVersion && addon.availableVersion !== addon.installedVersion
      ? `${addon.installedVersion} → ${addon.availableVersion}`
      : addon.installedVersion
    : addon.availableVersion ?? "";

  return (
    <div style={ROW}>
      <div style={NAME} title={addon.name}>
        <div style={{ fontWeight: 600, lineHeight: "1.4", whiteSpace: "normal", overflowWrap: "anywhere" }}>{addon.name}</div>
        {addon.description ? (
          <div style={{ marginTop: "4px", fontSize: "12px", lineHeight: "1.5", opacity: 0.8, overflowWrap: "anywhere", whiteSpace: "pre-wrap" }}>
            {addon.description}
          </div>
        ) : actions?.showInstall ? (
          <div style={{ marginTop: "4px", fontSize: "12px", lineHeight: "1.5", opacity: 0.65 }}>
            No summary supplied by this source. Open addon page for description.
          </div>
        ) : null}
      </div>

      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "12px", flexWrap: "wrap", width: "100%" }}>
        <div style={META}>
          <ProviderBadge label={addon.providerLabel} />
          {actions?.showInstall ? (
            <Badge tone={actions.installed ? "ok" : "muted"}>{actions.installed ? "Installed" : "Not installed"}</Badge>
          ) : <StateBadge state={addon.state} />}
          {version ? <span style={VERSION}>{version}</span> : null}
          {addon.folderName && !addon.installedVersion ? <span>{addon.folderName}</span> : null}
          {addon.gameFlavours.length > 0 ? (
            <span>{addon.gameFlavours.map((flavour) => FLAVOUR_LABELS[flavour] ?? flavour).join(" · ")}</span>
          ) : null}
          {addon.lastUpdated ? <span>Updated {new Date(addon.lastUpdated).toLocaleDateString()}</span> : null}
          {addon.downloadCount !== undefined ? <span>{addon.downloadCount.toLocaleString()} downloads</span> : null}
        </div>

        <Focusable style={{ display: "flex", gap: "8px", flexWrap: "wrap" }}>

          {addon.homepage ? (
            <DialogButton style={ICON_BUTTON} aria-label={`Open page for ${addon.name}`} onOKActionDescription="Open addon page" onClick={() => Navigation.NavigateToExternalWeb(addon.homepage as string)}>
              <FaExternalLinkAlt aria-hidden="true" />
            </DialogButton>
          ) : null}

          {actions?.showInstall ? (
            <DialogButton
              style={ICON_BUTTON}
              aria-label={actions.installed ? `${addon.name} installed` : `Install ${addon.name}`}
              onOKActionDescription={actions.installed ? "Installed" : "Install"}
              disabled={blocked || Boolean(actions.installed)}
              onClick={() => void plugin.installAddon(addon.provider, addon.providerId)}
            >
              <FaDownload aria-hidden="true" />
            </DialogButton>
          ) : null}

          {actions?.showUpdate ? (
            <DialogButton style={ICON_BUTTON} aria-label={`Update ${addon.name}`} onOKActionDescription="Update" disabled={blocked} onClick={() => void plugin.updateAddon(addon.id)}>
              <FaSyncAlt aria-hidden="true" />
            </DialogButton>
          ) : null}

          {actions?.showRollback ? (
            <DialogButton style={ICON_BUTTON} aria-label={`Roll back ${addon.name}`} onOKActionDescription="Roll back" disabled={blocked} onClick={() => void plugin.rollbackAddon(addon.id)}>
              <FaHistory aria-hidden="true" />
            </DialogButton>
          ) : null}

          {actions?.showRemove ? (
            <DialogButton
              style={ICON_BUTTON}
              aria-label={`Remove ${addon.name}`}
              onOKActionDescription="Remove"
              disabled={blocked}
              onClick={() =>
                showModal(
                  <ConfirmModal
                    strTitle={`Uninstall ${addon.name}?`}
                    strDescription="The addon files are removed from this installation. Your in-game settings are kept."
                    strOKButtonText="Uninstall"
                    strCancelButtonText="Cancel"
                    onOK={() => void plugin.removeAddon(addon.id)}
                  />,
                )
              }
            >
              <FaTrashAlt aria-hidden="true" />
            </DialogButton>
          ) : null}
        </Focusable>
      </div>
    </div>
  );
};

export const AddonList: FC<{
  title: string;
  addons: Addon[];
  actions?: AddonRowActions;
  emptyMessage?: string;
  spinner?: boolean;
}> = ({ title, addons, actions, emptyMessage, spinner }) => {
  const plugin = usePlugin();
  const canRollback = useMemo(
    () => plugin.engines.some((engine) => engine.capabilities?.rollback),
    [plugin.engines],
  );

  return (
    <PanelSection title={title} spinner={Boolean(spinner)}>
      {addons.length === 0 ? (
        <PanelSectionRow>
          <div style={{ opacity: 0.6, fontSize: "12px" }}>{emptyMessage ?? "Nothing here yet."}</div>
        </PanelSectionRow>
      ) : (
        <Focusable style={{ display: "flex", flexDirection: "column" }}>
          {addons.map((addon) => (
            <AddonRow
              key={addon.id}
              addon={addon}
              disabled={plugin.selected?.available === false}
              actions={{
                ...actions,
                showRollback: Boolean(actions?.showRollback && canRollback),
              }}
            />
          ))}
        </Focusable>
      )}
    </PanelSection>
  );
};
