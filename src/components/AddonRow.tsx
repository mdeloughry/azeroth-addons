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

import { usePlugin } from "../state";
import { Addon } from "../types";
import { ProviderBadge, StateBadge } from "./Badges";

const ROW: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: "6px",
  padding: "6px 0",
  borderTop: "1px solid rgba(255,255,255,0.07)",
};

const NAME: React.CSSProperties = {
  flex: "1 1 auto",
  minWidth: 0,
};

const META: React.CSSProperties = {
  display: "flex",
  gap: "6px",
  alignItems: "center",
  fontSize: "11px",
  opacity: 0.7,
  marginTop: "2px",
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
        <div style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{addon.name}</div>
        <div style={META}>
          <ProviderBadge label={addon.providerLabel} />
          {version ? <span style={VERSION}>{version}</span> : null}
          {addon.folderName && !addon.installedVersion ? <span>{addon.folderName}</span> : null}
        </div>
      </div>

      <StateBadge state={addon.state} />

      {addon.homepage ? (
        <DialogButton onClick={() => Navigation.NavigateToExternalWeb(addon.homepage as string)}>Page</DialogButton>
      ) : null}

      {actions?.showInstall ? (
        <DialogButton
          disabled={blocked || Boolean(actions.installed)}
          onClick={() => void plugin.installAddon(addon.provider, addon.providerId)}
        >
          {actions.installed ? "Installed" : "Install"}
        </DialogButton>
      ) : null}

      {actions?.showUpdate ? (
        <DialogButton disabled={blocked} onClick={() => void plugin.updateAddon(addon.id)}>
          Update
        </DialogButton>
      ) : null}

      {actions?.showRollback ? (
        <DialogButton disabled={blocked} onClick={() => void plugin.rollbackAddon(addon.id)}>
          Rollback
        </DialogButton>
      ) : null}

      {actions?.showRemove ? (
        <DialogButton
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
          Remove
        </DialogButton>
      ) : null}
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
