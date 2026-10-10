import { ButtonItem, PanelSection, PanelSectionRow, Spinner, TextField } from "@decky/ui";
import { FC, useMemo, useState } from "react";

import { AddonRow } from "../components/AddonRow";
import { ProviderBadge, ProviderStateBadge } from "../components/Badges";
import { usePlugin } from "../state";
import { Addon } from "../types";

const GROUP: React.CSSProperties = {
  marginTop: "6px",
};

/** Search across every compatible source; results are grouped by provider. */
export const SearchView: FC = () => {
  const plugin = usePlugin();
  const [query, setQuery] = useState("");

  const results = plugin.search?.results ?? [];
  const installedIds = useMemo(
    () => new Set((plugin.installed?.addons ?? []).map((addon) => addon.id)),
    [plugin.installed],
  );

  const grouped = useMemo(() => {
    const map = new Map<string, Addon[]>();
    for (const addon of results) {
      const key = addon.provider;
      const list = map.get(key) ?? [];
      list.push(addon);
      map.set(key, list);
    }
    return [...map.entries()].sort((a, b) => a[0].localeCompare(b[0]));
  }, [results]);

  const submit = () => void plugin.runSearch(query);

  return (
    <>
      <PanelSection title="Find addons">
        <PanelSectionRow>
          <TextField
            label="Search every compatible source"
            description="CurseForge, GitHub, Wago, TukUI and more, depending on what is configured."
            disabled={plugin.busy !== null}
            value={query}
            onChange={(event) => setQuery(event.currentTarget.value)}
          />
        </PanelSectionRow>
        <PanelSectionRow>
          <ButtonItem
            layout="below"
            disabled={plugin.busy !== null || plugin.searching || query.trim().length === 0}
            onClick={submit}
          >
            {plugin.searching ? "Searching…" : "Search"}
          </ButtonItem>
        </PanelSectionRow>
        {plugin.search ? (
          <PanelSectionRow>
            <ButtonItem layout="below" onClick={() => plugin.clearSearch()}>
              Clear results
            </ButtonItem>
          </PanelSectionRow>
        ) : null}
      </PanelSection>

      {plugin.providers.length > 0 ? (
        <PanelSection title="Addon sources">
          <PanelSectionRow>
            <div style={{ display: "flex", flexWrap: "wrap", gap: "6px" }}>
              {plugin.providers.map((provider) => (
                <span
                  key={provider.id}
                  style={{ display: "inline-flex", gap: "4px", alignItems: "center" }}
                  title={provider.detail ?? provider.message ?? ""}
                >
                  <ProviderBadge label={provider.displayName} />
                  <ProviderStateBadge state={provider.state} />
                </span>
              ))}
            </div>
          </PanelSectionRow>
        </PanelSection>
      ) : null}

      {plugin.searching ? (
        <PanelSection>
          <PanelSectionRow>
            <Spinner style={{ width: "16px", height: "16px" }} />
          </PanelSectionRow>
        </PanelSection>
      ) : null}

      {plugin.search && plugin.search.failures.length > 0 ? (
        <PanelSection title="Some sources did not respond">
          {plugin.search.failures.map((failure) => (
            <PanelSectionRow key={failure.source}>
              <div style={{ fontSize: "12px" }}>
                <strong>{failure.source}</strong>: {failure.error.message}
              </div>
            </PanelSectionRow>
          ))}
        </PanelSection>
      ) : null}

      {plugin.search && results.length === 0 && !plugin.searching ? (
        <PanelSection>
          <PanelSectionRow>
            <div style={{ fontSize: "12px", opacity: 0.75 }}>
              No results for “{plugin.search.query}”. Try a different name.
            </div>
          </PanelSectionRow>
        </PanelSection>
      ) : null}

      {grouped.map(([provider, addons]) => (
        <PanelSection key={provider} title={addons[0]?.providerLabel ?? provider}>
          <div style={GROUP}>
            {addons.map((addon) => (
              <AddonRow
                key={addon.id}
                addon={addon}
                actions={{ showInstall: true, installed: installedIds.has(addon.id) }}
                disabled={plugin.selected?.available === false}
              />
            ))}
          </div>
        </PanelSection>
      ))}
    </>
  );
};
