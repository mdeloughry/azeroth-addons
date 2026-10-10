import { FileSelectionType, openFilePicker } from "@decky/api";
import {
  ButtonItem,
  ConfirmModal,
  DialogButton,
  Dropdown,
  PanelSection,
  PanelSectionRow,
  TextField,
  showModal,
} from "@decky/ui";
import { FC, useEffect, useMemo, useState } from "react";

import { api, errorMessage } from "../api";
import { AvailabilityBadge } from "../components/Badges";
import { usePlugin } from "../state";
import { InstallationOption } from "../types";

/** FileSelectionType.FOLDER. It is declared as an ambient const enum, which
 * `isolatedModules` forbids reading as a value, so the member is cast instead. */
const PICK_FOLDER = 1 as FileSelectionType;

const ROW: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: "8px",
  padding: "6px 0",
  borderTop: "1px solid rgba(255,255,255,0.07)",
};

/** Installation management: scan, add custom paths, rename, remove. */
export const InstallationsView: FC = () => {
  const plugin = usePlugin();
  const [options, setOptions] = useState<InstallationOption[]>([]);
  const [quickPick, setQuickPick] = useState(0);
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState("");
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    void api
      .getInstallationOptions()
      .then((payload) => setOptions(payload.options))
      .catch(() => setOptions([]));
  }, []);

  const busy = plugin.busy !== null;

  const pickOptions = useMemo(
    () => options.map((option, index) => ({ data: index, label: option.label })),
    [options],
  );

  const addFrom = async (path: string) => {
    setNotice(null);
    try {
      const preview = await api.validateCustomPath(path);
      if (preview.found.length === 0) {
        setNotice("No World of Warcraft installation found in that folder.");
        return;
      }
      const added = await plugin.addCustomInstallation(path);
      setNotice(
        added > 0
          ? `Added ${added} installation(s): ${preview.found.map((item) => item.flavourLabel).join(", ")}`
          : "Those installations are already registered.",
      );
    } catch (cause) {
      setNotice(errorMessage(cause));
    }
  };

  const browse = async () => {
    const start = options[quickPick]?.path ?? "/home";
    try {
      const picked = await openFilePicker(PICK_FOLDER, start);
      if (picked?.path) await addFrom(picked.path);
    } catch (cause) {
      setNotice(errorMessage(cause));
    }
  };

  return (
    <>
      <PanelSection title="World of Warcraft installations">
        <PanelSectionRow>
          <ButtonItem layout="below" disabled={busy} onClick={() => void plugin.rescan()}>
            Scan for installations
          </ButtonItem>
        </PanelSectionRow>
        <PanelSectionRow>
          <div style={{ fontSize: "11px", opacity: 0.7 }}>
            Scans Steam libraries, Proton prefixes, {"/run/media"} and {"/mnt"} for internal, SD card and external
            drives.
          </div>
        </PanelSectionRow>
      </PanelSection>

      <PanelSection title="Add installation">
        {pickOptions.length > 0 ? (
          <PanelSectionRow>
            <Dropdown
              menuLabel="Starting location"
              rgOptions={pickOptions}
              selectedOption={quickPick}
              onChange={(option) => setQuickPick(option.data as number)}
            />
          </PanelSectionRow>
        ) : null}
        <PanelSectionRow>
          <ButtonItem layout="below" disabled={busy} onClick={() => void browse()}>
            Browse for World of Warcraft folder
          </ButtonItem>
        </PanelSectionRow>
        <PanelSectionRow>
          <ButtonItem
            layout="below"
            disabled={busy || options.length === 0}
            onClick={() => void addFrom(options[quickPick]?.path ?? "")}
          >
            Add from “{options[quickPick]?.label ?? "—"}”
          </ButtonItem>
        </PanelSectionRow>
        {notice ? (
          <PanelSectionRow>
            <div style={{ fontSize: "12px", opacity: 0.85 }}>{notice}</div>
          </PanelSectionRow>
        ) : null}
      </PanelSection>

      <PanelSection title={`Registered (${plugin.installations.length})`} spinner={plugin.booting}>
        {plugin.installations.length === 0 ? (
          <PanelSectionRow>
            <div style={{ fontSize: "12px", opacity: 0.7 }}>
              Nothing registered yet. Scan, or add a folder manually.
            </div>
          </PanelSectionRow>
        ) : null}
        {plugin.installations.map((installation) => (
          <div key={installation.id} style={ROW}>
            <div style={{ flex: "1 1 auto", minWidth: 0 }}>
              <div style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {installation.displayName}
              </div>
              <div style={{ fontSize: "11px", opacity: 0.65, overflow: "hidden", textOverflow: "ellipsis" }}>
                {installation.rootPath}
              </div>
            </div>
            <AvailabilityBadge available={installation.available} />
            <DialogButton
              onClick={() => {
                setRenamingId(installation.id);
                setRenameValue(installation.displayName);
              }}
            >
              Rename
            </DialogButton>
            <DialogButton disabled={busy} onClick={() => void plugin.selectInstallation(installation.id)}>
              Select
            </DialogButton>
            <DialogButton
              disabled={busy}
              onClick={() =>
                showModal(
                  <ConfirmModal
                    strTitle={`Remove ${installation.displayName}?`}
                    strDescription="Azeroth Addons forgets this installation. Its addon files are NOT deleted."
                    strOKButtonText="Remove"
                    strCancelButtonText="Cancel"
                    onOK={() => void plugin.removeInstallation(installation.id)}
                  />,
                )
              }
            >
              Remove
            </DialogButton>
          </div>
        ))}
      </PanelSection>

      {renamingId ? (
        <PanelSection title="Rename installation">
          <PanelSectionRow>
            <TextField
              label="Display name"
              disabled={busy}
              value={renameValue}
              onChange={(event) => setRenameValue(event.currentTarget.value)}
            />
          </PanelSectionRow>
          <PanelSectionRow>
            <ButtonItem
              layout="below"
              disabled={busy || renameValue.trim().length === 0}
              onClick={() => {
                const target = renamingId;
                if (!target) return;
                void plugin.renameInstallation(target, renameValue.trim());
                setRenamingId(null);
              }}
            >
              Save name
            </ButtonItem>
          </PanelSectionRow>
          <PanelSectionRow>
            <ButtonItem layout="below" onClick={() => setRenamingId(null)}>
              Cancel
            </ButtonItem>
          </PanelSectionRow>
        </PanelSection>
      ) : null}
    </>
  );
};
