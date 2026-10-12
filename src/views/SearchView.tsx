import { ButtonItem, DialogButton, DialogCheckbox, PanelSection, PanelSectionRow, Spinner, TextField } from "@decky/ui";
import { FC, useMemo, useState } from "react";

import { AddonRow } from "../components/AddonRow";
import { usePlugin } from "../state";
import { Addon } from "../types";

const GROUP: React.CSSProperties = {
  marginTop: "6px",
};

/** Search across every compatible source; results are grouped by provider. */
export const SearchView: FC = () => {
  const plugin = usePlugin();
  const [query, setQuery] = useState("");
  const [excludedSources, setExcludedSources] = useState<Set<string>>(new Set());
  const [setupSource, setSetupSource] = useState<string | null>(null);
  const sourceAvailable = (provider: typeof plugin.providers[number]) => Boolean(provider.searchAvailable && provider.state !== "degraded");
  const selectedSources = plugin.providers.filter((provider) => sourceAvailable(provider) && !excludedSources.has(provider.id)).map((provider) => provider.id);

  const results = (plugin.search?.results ?? []).filter((addon) => selectedSources.includes(addon.provider));
  const installedIds = useMemo(
    () => new Set((plugin.installed?.addons ?? []).map((addon) => `${addon.provider}:${addon.providerId}`.toLowerCase())),
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

  const submit = () => void plugin.runSearch(query, selectedSources);

  return (
    <>
      <PanelSection title="Find addons">
        <PanelSectionRow>
          <TextField
            label="Search addons"
            description="Search checked sources for your selected game version."
            disabled={plugin.busy !== null}
            value={query}
            onChange={(event) => setQuery(event.currentTarget.value)}
          />
        </PanelSectionRow>
        <PanelSectionRow>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 180px), 1fr))", gap: "8px", marginBlock: "8px" }}>
            {plugin.providers.map((provider) => {
              const available = sourceAvailable(provider);
              return (
                <div key={provider.id} style={{ padding: "8px", minWidth: 0, borderRadius: "6px", background: available ? "rgba(103,165,235,0.12)" : "rgba(255,255,255,0.04)" }}>
                  <DialogCheckbox
                    controlled
                    checked={available && !excludedSources.has(provider.id)}
                    disabled={!available || plugin.searching}
                    label={provider.displayName}
                    description={available ? "Search this source" : "Unavailable"}
                    onChange={(checked) => {
                      setExcludedSources((previous) => {
                        const next = new Set(previous);
                        if (checked) next.delete(provider.id); else next.add(provider.id);
                        return next;
                      });
                      plugin.clearSearch();
                    }}
                  />
                  {!available ? (
                    <DialogButton style={{ width: "auto", minWidth: 0, padding: "4px 8px", marginTop: "6px" }} onClick={() => setSetupSource(setupSource === provider.id ? null : provider.id)}>
                      {setupSource === provider.id ? "Hide help" : provider.setupInstructions ? "Set up" : "Why unavailable?"}
                    </DialogButton>
                  ) : null}
                  {setupSource === provider.id ? (
                    <div style={{ marginTop: "8px", fontSize: "12px", lineHeight: "1.5", overflowWrap: "anywhere" }}>
                      {provider.setupInstructions || provider.detail || provider.message || "Check source status in Settings and retry."}
                    </div>
                  ) : null}
                </div>
              );
            })}
          </div>
          {selectedSources.length === 0 ? <div style={{ fontSize: "12px", opacity: 0.7 }}>Check an available source to search.</div> : null}
        </PanelSectionRow>
        <PanelSectionRow>
          <ButtonItem
            layout="below"
            disabled={plugin.busy !== null || plugin.searching || query.trim().length === 0 || selectedSources.length === 0}
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
                {failure.error.details ? (
                  <div style={{ marginTop: "4px", overflowWrap: "anywhere" }}>
                    {failure.error.code}: {failure.error.details}
                  </div>
                ) : null}
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
                actions={{ showInstall: true, installed: Boolean(addon.installed || addon.installedVersion || installedIds.has(`${addon.provider}:${addon.providerId}`.toLowerCase())) }}
                disabled={plugin.selected?.available === false}
              />
            ))}
          </div>
        </PanelSection>
      ))}
    </>
  );
};
