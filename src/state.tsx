/**
 * Plugin state: one hook owns all backend interaction, so views stay declarative.
 *
 * Backend push events (runtime status, installations changed, operation
 * progress) are subscribed here and folded into React state.
 */

import { toaster } from "@decky/api";
import {
  FC,
  ReactNode,
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import { api, EVENTS, errorMessage, isAzerothApiError, onEvent } from "./api";
import {
  Addon,
  EngineStatus,
  InstallationsSummary,
  InstalledPayload,
  OperationEvent,
  ProviderStatus,
  RuntimeStatus,
  SearchPayload,
  SettingsPayload,
  WowInstallation,
} from "./types";

const EMPTY_SUMMARY: InstallationsSummary = { total: 0, available: 0, byFlavour: {}, selectedId: null };

export interface PluginState {
  status: RuntimeStatus | null;
  summary: InstallationsSummary;
  installations: WowInstallation[];
  selectedId: string | null;
  selected: WowInstallation | null;
  installed: InstalledPayload | null;
  updates: Addon[];
  search: SearchPayload | null;
  settings: SettingsPayload | null;
  providers: ProviderStatus[];
  engines: EngineStatus[];
  operation: OperationEvent | null;
  busy: string | null;
  error: string | null;
  booting: boolean;
  loadingInstalled: boolean;
  checkingUpdates: boolean;
  searching: boolean;
  lastUpdatedAt: number | null;

  boot: (options?: { silent?: boolean }) => Promise<void>;
  refreshRuntime: () => Promise<void>;
  selectInstallation: (installationId: string) => Promise<void>;
  loadInstalled: (options?: { refresh?: boolean }) => Promise<void>;
  checkUpdates: () => Promise<void>;
  updateAll: () => Promise<void>;
  updateAddon: (addonId: string) => Promise<void>;
  removeAddon: (addonId: string) => Promise<void>;
  rollbackAddon: (addonId: string) => Promise<void>;
  installAddon: (provider: string, providerId: string, replace?: boolean) => Promise<void>;
  runSearch: (query: string) => Promise<void>;
  clearSearch: () => void;
  rescan: () => Promise<void>;
  addCustomInstallation: (path: string) => Promise<number>;
  removeInstallation: (installationId: string) => Promise<void>;
  renameInstallation: (installationId: string, displayName: string) => Promise<void>;
  saveSettings: (values: Record<string, unknown>) => Promise<void>;
  setCredential: (provider: string, value: string) => Promise<void>;
  clearCredential: (provider: string) => Promise<void>;
  reloadProviders: () => Promise<void>;
}

const PluginContext = createContext<PluginState | null>(null);

export const usePlugin = (): PluginState => {
  const context = useContext(PluginContext);
  if (!context) {
    throw new Error("usePlugin must be used inside <PluginProvider>");
  }
  return context;
};

export const PluginProvider: FC<{ children: ReactNode }> = ({ children }) => {
  const [status, setStatus] = useState<RuntimeStatus | null>(null);
  const [summary, setSummary] = useState<InstallationsSummary>(EMPTY_SUMMARY);
  const [installations, setInstallations] = useState<WowInstallation[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [installed, setInstalled] = useState<InstalledPayload | null>(null);
  const [updates, setUpdates] = useState<Addon[]>([]);
  const [search, setSearch] = useState<SearchPayload | null>(null);
  const [settings, setSettings] = useState<SettingsPayload | null>(null);
  const [providers, setProviders] = useState<ProviderStatus[]>([]);
  const [engines, setEngines] = useState<EngineStatus[]>([]);
  const [operation, setOperation] = useState<OperationEvent | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [booting, setBooting] = useState(true);
  const [loadingInstalled, setLoadingInstalled] = useState(false);
  const [checkingUpdates, setCheckingUpdates] = useState(false);
  const [searching, setSearching] = useState(false);
  const [lastUpdatedAt, setLastUpdatedAt] = useState<number | null>(null);

  const selectedRef = useRef<string | null>(null);
  selectedRef.current = selectedId;

  const notify = useCallback((title: string, body?: string) => {
    try {
      toaster.toast({ title, body });
    } catch {
      /* toasts are best effort */
    }
  }, []);

  const fail = useCallback(
    (cause: unknown, prefix?: string) => {
      const message = errorMessage(cause);
      setError(message);
      notify(prefix ? `${prefix} failed` : "Something went wrong", message);
      if (!isAzerothApiError(cause)) {
        console.error("azeroth-addons", cause);
      }
    },
    [notify],
  );

  const refreshRuntime = useCallback(async () => {
    const next = await api.getRuntimeStatus();
    setStatus(next);
    setSummary(next.installations ?? EMPTY_SUMMARY);
  }, []);

  const loadInstallations = useCallback(async () => {
    const payload = await api.getInstallations();
    setInstallations(payload.installations);
    setSummary(payload.summary ?? EMPTY_SUMMARY);
    const nextSelected = payload.selectedId ?? payload.installations[0]?.id ?? null;
    setSelectedId(nextSelected);
    return nextSelected;
  }, []);

  const reloadProviders = useCallback(async () => {
    const payload = await api.getProviders();
    setProviders(payload.providers);
  }, []);

  const reloadEngines = useCallback(async () => {
    const payload = await api.getEngines();
    setEngines(payload.engines);
  }, []);

  const loadInstalled = useCallback(
    async (options?: { refresh?: boolean }) => {
      const installationId = selectedRef.current;
      if (!installationId) {
        setInstalled(null);
        return;
      }
      setLoadingInstalled(true);
      try {
        const payload = await api.getInstalledAddons(installationId, options?.refresh ?? false);
        if (selectedRef.current !== installationId) return;
        setInstalled(payload);
        setUpdates((previous) => previous.filter((addon) => addon.state === "update-available"));
        setLastUpdatedAt(Date.now());
      } catch (cause) {
        fail(cause, "Loading addons");
      } finally {
        setLoadingInstalled(false);
      }
    },
    [fail],
  );

  const boot = useCallback(
    async (options?: { silent?: boolean }) => {
      if (!options?.silent) setBooting(true);
      setError(null);
      try {
        await refreshRuntime();
        const nextSelected = await loadInstallations();
        await Promise.all([reloadProviders(), reloadEngines()]);
        try {
          setSettings(await api.getSettings());
        } catch {
          /* settings are non-critical for the main view */
        }
        if (nextSelected) {
          selectedRef.current = nextSelected;
          await loadInstalled();
        }
      } catch (cause) {
        fail(cause, "Starting Azeroth Addons");
      } finally {
        setBooting(false);
      }
    },
    [fail, loadInstallations, loadInstalled, refreshRuntime, reloadEngines, reloadProviders],
  );

  // --- boot + events ------------------------------------------------------

  useEffect(() => {
    void boot();
    const unsubscribers = [
      onEvent<[RuntimeStatus]>(EVENTS.runtimeStatus, (payload) => {
        if (!payload) return;
        setStatus(payload);
        setSummary(payload.installations ?? EMPTY_SUMMARY);
        setEngines((previous) =>
          payload.engine
            ? [payload.engine, ...previous.filter((engine) => engine.id !== payload.engine?.id)]
            : previous,
        );
      }),
      onEvent<[WowInstallation[]]>(EVENTS.installationsChanged, () => {
        void loadInstallations()
          .then((nextSelected) => {
            if (nextSelected !== selectedRef.current) {
              selectedRef.current = nextSelected;
              void loadInstalled({ refresh: true });
            }
          })
          .catch(() => undefined);
      }),
      onEvent<[OperationEvent]>(EVENTS.operation, (payload) => {
        if (payload) setOperation(payload);
      }),
      onEvent<[{ installationId?: string; reason?: string }]>(EVENTS.addonsChanged, (payload) => {
        if (!payload || !payload.installationId) return;
        if (payload.installationId !== selectedRef.current) return;
        void loadInstalled({ refresh: true });
      }),
    ];
    return () => {
      unsubscribers.forEach((unsubscribe) => unsubscribe());
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // --- actions -----------------------------------------------------------

  const run = useCallback(
    async (label: string, action: () => Promise<void>, toast?: { title: string; body?: string }) => {
      setBusy(label);
      setError(null);
      try {
        await action();
        if (toast) notify(toast.title, toast.body);
      } catch (cause) {
        fail(cause, label);
      } finally {
        setBusy(null);
      }
    },
    [fail, notify],
  );

  const selectInstallation = useCallback(
    async (installationId: string) => {
      selectedRef.current = installationId;
      setSelectedId(installationId);
      setInstalled(null);
      setUpdates([]);
      setSearch(null);
      await run("Switching installation", async () => {
        await api.setSelectedInstallation(installationId);
        await loadInstalled({ refresh: true });
      });
    },
    [loadInstalled, run],
  );

  const checkUpdates = useCallback(async () => {
    const installationId = selectedRef.current;
    if (!installationId) return;
    setCheckingUpdates(true);
    try {
      const payload = await api.checkUpdates(installationId);
      if (selectedRef.current !== installationId) return;
      setUpdates(payload.updates);
      setInstalled((previous) =>
        previous ? { ...previous, counts: { ...previous.counts, updates: payload.count } } : previous,
      );
    } catch (cause) {
      fail(cause, "Checking for updates");
    } finally {
      setCheckingUpdates(false);
    }
  }, [fail]);

  const updateAll = useCallback(async () => {
    const installationId = selectedRef.current;
    if (!installationId) return;
    await run("Updating all addons", async () => {
      const result = await api.updateAll(installationId);
      await loadInstalled({ refresh: true });
      setUpdates([]);
      if (result.failures.length > 0) {
        notify(
          `Updated ${result.updatedCount} addon(s)`,
          `${result.failures.length} failed: ${result.failures.map((failure) => failure.addonId).join(", ")}`,
        );
      }
    });
  }, [loadInstalled, notify, run]);

  const updateAddon = useCallback(
    async (addonId: string) => {
      const installationId = selectedRef.current;
      if (!installationId) return;
      await run("Updating addon", async () => {
        await api.updateAddon(installationId, addonId);
        await loadInstalled({ refresh: true });
        setUpdates((previous) => previous.filter((addon) => addon.id !== addonId));
      });
    },
    [loadInstalled, run],
  );

  const removeAddon = useCallback(
    async (addonId: string) => {
      const installationId = selectedRef.current;
      if (!installationId) return;
      await run("Removing addon", async () => {
        await api.removeAddon(installationId, addonId);
        await loadInstalled({ refresh: true });
      });
    },
    [loadInstalled, run],
  );

  const rollbackAddon = useCallback(
    async (addonId: string) => {
      const installationId = selectedRef.current;
      if (!installationId) return;
      await run("Rolling back addon", async () => {
        await api.rollbackAddon(installationId, addonId);
        await loadInstalled({ refresh: true });
      });
    },
    [loadInstalled, run],
  );

  const installAddon = useCallback(
    async (provider: string, providerId: string, replace = false) => {
      const installationId = selectedRef.current;
      if (!installationId) return;
      await run("Installing addon", async () => {
        await api.installAddon(installationId, provider, providerId, replace);
        await loadInstalled({ refresh: true });
      });
    },
    [loadInstalled, run],
  );

  const runSearch = useCallback(
    async (query: string) => {
      const installationId = selectedRef.current;
      if (!installationId) return;
      const clean = query.trim();
      if (!clean) {
        setSearch(null);
        return;
      }
      setSearching(true);
      setError(null);
      try {
        const payload = await api.searchAddons(installationId, clean);
        if (selectedRef.current !== installationId) return;
        setSearch(payload);
      } catch (cause) {
        fail(cause, "Searching");
      } finally {
        setSearching(false);
      }
    },
    [fail],
  );

  const clearSearch = useCallback(() => setSearch(null), []);

  const rescan = useCallback(async () => {
    await run("Looking for World of Warcraft", async () => {
      const payload = await api.rescanInstallations();
      await loadInstallations();
      notify(
        "Scan complete",
        payload.added.length > 0
          ? `Found ${payload.added.length} new installation(s).`
          : "No new installations found.",
      );
    });
  }, [loadInstallations, notify, run]);

  const addCustomInstallation = useCallback(
    async (path: string) => {
      let addedCount = 0;
      await run("Adding installation", async () => {
        const payload = await api.addCustomInstallation(path);
        addedCount = payload.added.length;
        await loadInstallations();
      });
      return addedCount;
    },
    [loadInstallations, run],
  );

  const removeInstallation = useCallback(
    async (installationId: string) => {
      await run("Removing installation", async () => {
        await api.removeInstallation(installationId);
        const nextSelected = await loadInstallations();
        selectedRef.current = nextSelected;
        await loadInstalled({ refresh: true });
      });
    },
    [loadInstallations, loadInstalled, run],
  );

  const renameInstallation = useCallback(
    async (installationId: string, displayName: string) => {
      await run("Renaming installation", async () => {
        await api.updateInstallation(installationId, displayName);
        await loadInstallations();
      });
    },
    [loadInstallations, run],
  );

  const saveSettings = useCallback(
    async (values: Record<string, unknown>) => {
      await run("Saving settings", async () => {
        setSettings(await api.setSettings(values));
        await reloadProviders();
        await reloadEngines();
      });
    },
    [reloadEngines, reloadProviders, run],
  );

  const setCredential = useCallback(
    async (provider: string, value: string) => {
      await run("Saving credential", async () => {
        setSettings(await api.setCredential(provider, value));
        await reloadProviders();
      });
    },
    [reloadProviders, run],
  );

  const clearCredential = useCallback(
    async (provider: string) => {
      await run("Clearing credential", async () => {
        setSettings(await api.clearCredential(provider));
        await reloadProviders();
      });
    },
    [reloadProviders, run],
  );

  const selected = useMemo(
    () => installations.find((installation) => installation.id === selectedId) ?? null,
    [installations, selectedId],
  );

  const value: PluginState = {
    status,
    summary,
    installations,
    selectedId,
    selected,
    installed,
    updates,
    search,
    settings,
    providers,
    engines,
    operation,
    busy,
    error,
    booting,
    loadingInstalled,
    checkingUpdates,
    searching,
    lastUpdatedAt,
    boot,
    refreshRuntime,
    selectInstallation,
    loadInstalled,
    checkUpdates,
    updateAll,
    updateAddon,
    removeAddon,
    rollbackAddon,
    installAddon,
    runSearch,
    clearSearch,
    rescan,
    addCustomInstallation,
    removeInstallation,
    renameInstallation,
    saveSettings,
    setCredential,
    clearCredential,
    reloadProviders,
  };

  return <PluginContext.Provider value={value}>{children}</PluginContext.Provider>;
};
