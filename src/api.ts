/**
 * The single place the frontend talks to the backend.
 *
 * Every backend route returns an envelope; `rpc` unwraps it and throws a typed
 * error otherwise, so no component has to handle "ok" flags.
 */

import { addEventListener, call, removeEventListener } from "@decky/api";

import {
  Addon,
  AzerothError,
  EngineListPayload,
  EngineStatus,
  Envelope,
  InstallationOption,
  InstallationsPayload,
  InstallationsSummary,
  InstalledPayload,
  PathPreview,
  ProfileStatus,
  ProviderListPayload,
  ProviderStatus,
  RuntimeStatus,
  SearchPayload,
  SettingsPayload,
  UpdateAllResult,
  UpdatesPayload,
  WowInstallation,
} from "./types";

export class AzerothApiError extends Error {
  constructor(public readonly error: AzerothError) {
    super(error.message);
    this.name = "AzerothApiError";
  }
}

export function isAzerothApiError(value: unknown): value is AzerothApiError {
  return value instanceof AzerothApiError;
}

export function errorMessage(value: unknown): string {
  if (isAzerothApiError(value)) return value.error.message;
  if (value instanceof Error) return value.message;
  return String(value);
}

export function errorCode(value: unknown): string | null {
  return isAzerothApiError(value) ? value.error.code : null;
}

async function rpc<Args extends unknown[], Result>(route: string, ...args: Args): Promise<Result> {
  const envelope = await call<Args, Envelope<Result>>(route, ...args);
  if (!envelope) {
    throw new AzerothApiError({
      code: "NO_RESPONSE",
      message: "The Azeroth Addons backend did not respond. Try reloading Decky.",
    });
  }
  if (!envelope.ok) {
    throw new AzerothApiError(envelope.error);
  }
  return envelope.data;
}

export const api = {
  // runtime / engines / providers
  getRuntimeStatus: () => rpc<[], RuntimeStatus>("get_runtime_status"),
  prepareEngine: () => rpc<[], EngineStatus>("prepare_engine"),
  getEngines: () => rpc<[], EngineListPayload>("get_engines"),
  getEngineStatus: (engineId?: string) => rpc<[string | undefined], EngineStatus>("get_engine_status", engineId),
  getProviders: () => rpc<[], ProviderListPayload>("get_providers"),
  getProviderStatus: (providerId?: string) =>
    rpc<[string | undefined], ProviderStatus | ProviderListPayload>("get_provider_status", providerId),

  // installations
  getInstallations: () =>
    rpc<[], InstallationsPayload & { summary: InstallationsSummary; running: string[] }>("get_installations"),
  discoverWowInstallations: () =>
    rpc<[], { added: WowInstallation[]; installations: WowInstallation[]; selectedId: string | null }>(
      "discover_wow_installations",
    ),
  rescanInstallations: () =>
    rpc<[], { added: WowInstallation[]; installations: WowInstallation[]; selectedId: string | null }>(
      "rescan_installations",
    ),
  addCustomInstallation: (path: string) =>
    rpc<[string], { added: WowInstallation[]; existing: WowInstallation[]; installations: WowInstallation[] }>(
      "add_custom_installation",
      path,
    ),
  validateCustomPath: (path: string) => rpc<[string], PathPreview>("validate_custom_path", path),
  getInstallationOptions: () => rpc<[], { options: InstallationOption[] }>("get_installation_options"),
  updateInstallation: (installationId: string, displayName: string) =>
    rpc<[string, string], InstallationsPayload>("update_installation", installationId, displayName),
  removeInstallation: (installationId: string) =>
    rpc<[string], InstallationsPayload>("remove_installation", installationId),
  setSelectedInstallation: (installationId: string | null) =>
    rpc<[string | null], InstallationsPayload>("set_selected_installation", installationId),
  getEngineProfile: (installationId: string) => rpc<[string], ProfileStatus>("get_engine_profile", installationId),

  // addons
  getInstalledAddons: (installationId: string, refresh = false) =>
    rpc<[string, boolean], InstalledPayload>("get_installed_addons", installationId, refresh),
  reconcileAddons: (installationId: string) => rpc<[string], InstalledPayload>("reconcile_addons", installationId),
  checkUpdates: (installationId: string) => rpc<[string], UpdatesPayload>("check_updates", installationId),
  searchAddons: (installationId: string, query: string, limit = 25) =>
    rpc<[string, string, number], SearchPayload>("search_addons", installationId, query, limit),
  installAddon: (installationId: string, provider: string, providerId: string, replace = false) =>
    rpc<[string, string, string, boolean], { installationId: string; addon: Addon }>(
      "install_addon",
      installationId,
      provider,
      providerId,
      replace,
    ),
  updateAddon: (installationId: string, addonId: string) =>
    rpc<[string, string], { installationId: string; addon: Addon }>("update_addon", installationId, addonId),
  updateAll: (installationId: string) => rpc<[string], UpdateAllResult>("update_all", installationId),
  removeAddon: (installationId: string, addonId: string) =>
    rpc<[string, string], { installationId: string; removed: Addon }>("remove_addon", installationId, addonId),
  rollbackAddon: (installationId: string, addonId: string) =>
    rpc<[string, string], { installationId: string; addon: Addon }>("rollback_addon", installationId, addonId),

  // settings
  getSettings: () => rpc<[], SettingsPayload>("get_settings"),
  setSettings: (values: Record<string, unknown>) => rpc<[Record<string, unknown>], SettingsPayload>("set_settings", values),
  setCredential: (provider: string, value: string | null) =>
    rpc<[string, string | null], SettingsPayload>("set_credential", provider, value),
  clearCredential: (provider: string) => rpc<[string], SettingsPayload>("clear_credential", provider),
};

/** Subscribe to a backend event. Returns an unsubscribe function. */
export function onEvent<Args extends unknown[]>(event: string, listener: (...args: Args) => void): () => void {
  const wrapped = (...args: Args) => listener(...args);
  addEventListener<Args>(event, wrapped);
  return () => removeEventListener<Args>(event, wrapped);
}

export const EVENTS = {
  runtimeStatus: "az:runtime_status",
  installationsChanged: "az:installations_changed",
  addonsChanged: "az:addons_changed",
  operation: "az:operation",
  error: "az:error",
} as const;
