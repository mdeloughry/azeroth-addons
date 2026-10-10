import { Dropdown, PanelSection, PanelSectionRow } from "@decky/ui";
import { FC, useMemo } from "react";

import { AvailabilityBadge } from "../components/Badges";
import { usePlugin } from "../state";

/** Controller-friendly installation selector (Dropdown works with the gamepad). */
export const InstallationSelector: FC = () => {
  const plugin = usePlugin();

  const options = useMemo(
    () =>
      plugin.installations.map((installation, index) => ({
        data: index,
        label: `${installation.displayName}${installation.available ? "" : " (unavailable)"}`,
      })),
    [plugin.installations],
  );

  const selectedIndex = useMemo(() => {
    const index = plugin.installations.findIndex((installation) => installation.id === plugin.selectedId);
    return index >= 0 ? index : 0;
  }, [plugin.installations, plugin.selectedId]);

  if (plugin.installations.length === 0) return null;

  return (
    <PanelSection>
      <PanelSectionRow>
        <Dropdown
          menuLabel="World of Warcraft"
          rgOptions={options}
          selectedOption={selectedIndex}
          disabled={plugin.busy !== null}
          onChange={(option) => {
            const installation = plugin.installations[option.data as number];
            if (installation) void plugin.selectInstallation(installation.id);
          }}
        />
      </PanelSectionRow>
      {plugin.selected ? (
        <PanelSectionRow>
          <div style={{ display: "flex", gap: "8px", alignItems: "center", fontSize: "11px", opacity: 0.75 }}>
            <AvailabilityBadge
              available={plugin.selected.available}
              running={plugin.installed?.running}
            />
            <span>{plugin.selected.flavourLabel}</span>
            <span>·</span>
            <span>{plugin.selected.locationLabel}</span>
          </div>
        </PanelSectionRow>
      ) : null}
    </PanelSection>
  );
};
