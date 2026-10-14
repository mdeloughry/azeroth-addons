/** Shared across QAM/full-page providers; lifecycle belongs to definePlugin. */
import { toaster } from "@decky/api";
import { Navigation } from "@decky/ui";
import { useSyncExternalStore } from "react";
import { api, errorMessage } from "./api";
import { TAB_ROUTES } from "./routes";
import { PluginRelease, PluginUpdateStatus } from "./types";

type Snapshot = { status: PluginUpdateStatus | null; checking: boolean; requesting: boolean; message: string | null };
let snapshot: Snapshot = { status: null, checking: false, requesting: false, message: null };
const listeners = new Set<() => void>();
let generation = 0;
let notifiedVersion: string | null = null;
let resetTimer: ReturnType<typeof setTimeout> | undefined;

function publish(values: Partial<Snapshot>) {
  snapshot = { ...snapshot, ...values };
  listeners.forEach((listener) => listener());
}

export function usePluginUpdater() {
  return useSyncExternalStore((listener) => {
    listeners.add(listener);
    return () => { listeners.delete(listener); };
  }, () => snapshot);
}

export async function checkPluginUpdate(force = false) {
  if (snapshot.checking || snapshot.requesting) return;
  const epoch = generation;
  publish({ checking: true, message: null });
  try {
    const status = await api.checkPluginUpdate(force);
    if (epoch !== generation) return;
    publish({ status });
    if (status.state === "available" && status.release && notifiedVersion !== status.release.version) {
      notifiedVersion = status.release.version;
      try {
        toaster.toast({ title: "Azeroth Addons update", body: `Version ${status.release.version} is available.`,
          onClick: () => { Navigation.Navigate(TAB_ROUTES.settings); Navigation.CloseSideMenus(); } });
      } catch { /* notification is optional */ }
    }
  } catch (cause) {
    if (epoch === generation) publish({ message: errorMessage(cause) });
  } finally {
    if (epoch === generation) publish({ checking: false });
  }
}

/** Internal loader transport; keep isolated with a manual-install fallback.
 * Upstream: SteamDeckHomebrew/decky-loader frontend/src/plugin.ts (UPDATE = 2).
 */
export async function requestDeckyUpdate(release: PluginRelease) {
  const host = window as unknown as { DeckyBackend?: { call: (route: string, ...args: unknown[]) => Promise<unknown> } };
  if (typeof host.DeckyBackend?.call !== "function") {
    throw new Error("This Decky version cannot open the update installer. Use Settings → Developer → Install Plugin from URL.");
  }
  await host.DeckyBackend.call("utilities/install_plugin", release.assetUrl, "Azeroth Addons", release.version, release.sha256, 2);
}

export async function installPluginUpdate() {
  const release = snapshot.status?.release;
  if (!release || snapshot.requesting || snapshot.checking) return;
  const epoch = generation;
  publish({ requesting: true, message: null });
  try {
    const plan = await api.preparePluginUpdate(release.version);
    if (epoch !== generation) return;
    await requestDeckyUpdate(plan);
    if (epoch !== generation) return;
    publish({ message: "Confirm the update in Decky. The plugin reloads after installation. If you cancel, you can retry." });
    // Decky owns the dialog and installation, including cancellation. Returning
    // from this RPC means a prompt opened, not that installation succeeded.
    resetTimer = setTimeout(() => { if (epoch === generation) publish({ requesting: false }); }, 30000);
  } catch (cause) {
    if (epoch !== generation) return;
    publish({ requesting: false, message: errorMessage(cause) });
  }
}

export function startPluginUpdater(): () => void {
  generation += 1;
  snapshot = { status: null, checking: false, requesting: false, message: null };
  void checkPluginUpdate();
  const timer = setInterval(() => { void checkPluginUpdate(); }, 5 * 60 * 1000);
  return () => {
    generation += 1;
    clearInterval(timer);
    if (resetTimer) clearTimeout(resetTimer);
  };
}
