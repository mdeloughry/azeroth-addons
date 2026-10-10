/**
 * Shared types.
 *
 * These mirror the backend payloads exactly. The UI never sees raw CurseForge
 * ids, instawow structures or provider response formats - only these shapes.
 */

export type AddonState =
  | "current"
  | "update-available"
  | "installing"
  | "updating"
  | "unmanaged"
  | "error";

export interface AzerothError {
  code: string;
  message: string;
  details?: string;
  installationId?: string;
  provider?: string;
  engine?: string;
}

export type Envelope<T> = { ok: true; data: T } | { ok: false; error: AzerothError };

export interface Addon {
  id: string;
  name: string;
  provider: string;
  providerLabel: string;
  providerId: string;
  state: AddonState;
  gameFlavours: string[];
  pinned: boolean;
  description?: string;
  installedVersion?: string;
  availableVersion?: string;
  homepage?: string;
  error?: string;
  folderName?: string;
  downloadUrl?: string;
}

export type Flavour = "retail" | "classic-era" | "forever" | "classic" | "unknown";

export interface WowInstallation {
  id: string;
  displayName: string;
  flavour: Flavour;
  flavourLabel: string;
  source: string;
  rootPath: string;
  addonsPath: string;
  executablePath?: string | null;
  available: boolean;
  engineProfile: string;
  locationLabel: string;
  versionFolder: string;
}

export interface EngineCapabilities {
  install: boolean;
  update: boolean;
  remove: boolean;
  reconcile: boolean;
  rollback: boolean;
  search: boolean;
  listInstalled: boolean;
}

export interface EngineStatus {
  id: string;
  displayName: string;
  state: string;
  available: boolean;
  version?: string | null;
  bundledVersion?: string | null;
  message?: string | null;
  detail?: string | null;
  capabilities: EngineCapabilities;
}

export interface ProviderCapabilities {
  search: boolean;
  metadata: boolean;
  versions: boolean;
  downloads: boolean;
}

export interface ProviderStatus {
  id: string;
  displayName: string;
  available: boolean;
  state: string;
  message?: string | null;
  detail?: string | null;
  requiresCredential: boolean;
  credentialConfigured: boolean;
  credentialMode: string;
  capabilities: ProviderCapabilities;
}

export interface BinaryInfo {
  path: string;
  exists: boolean;
  executable: boolean;
  size?: number | null;
  bundledVersion: string;
  artifact: string;
  downloadUrl: string;
  sha256: string;
}

export interface InstallationsSummary {
  total: number;
  available: number;
  byFlavour: Record<string, number>;
  selectedId: string | null;
}

export interface RuntimeStatus {
  pluginVersion: string;
  engine: EngineStatus | null;
  installations: InstallationsSummary;
  binary: BinaryInfo;
  paths?: Record<string, string>;
}

export interface InstallationsPayload {
  installations: WowInstallation[];
  selectedId: string | null;
}

export interface InstalledPayload {
  installationId: string;
  addons: Addon[];
  unmanaged: Addon[];
  counts: { installed: number; unmanaged: number; updates: number };
  running: boolean;
  fetchedAt: number;
}

export interface UpdatesPayload {
  installationId: string;
  updates: Addon[];
  count: number;
}

export interface UpdateAllResult {
  installationId: string;
  updated: Addon[];
  updatedCount: number;
  failures: { addonId: string; error: AzerothError }[];
}

export interface SearchFailure {
  source: string;
  error: AzerothError;
}

export interface SearchPayload {
  installationId: string;
  query: string;
  flavour?: Flavour;
  results: Addon[];
  failures: SearchFailure[];
  sources: string[];
  truncated?: boolean;
}

export interface OperationEvent {
  installationId: string;
  kind: string;
  phase: "start" | "progress" | "done" | string;
  current: number;
  total: number;
  addon?: Addon;
  message?: string;
}

export interface InstallationOption {
  label: string;
  path: string;
}

export interface PathPreview {
  path: string;
  found: { rootPath: string; flavour: Flavour; flavourLabel: string; locationLabel: string }[];
}

export interface SettingsPayload {
  values: Record<string, unknown>;
  credentials: Record<string, { configured: boolean; hint: string }>;
  selectedInstallationId: string | null;
}

export interface ProfileStatus {
  installationId?: string;
  engineProfile: string;
  profile?: string;
  configPath?: string;
  addonDir?: string | null;
  flavourOverride?: string | null;
  validated?: boolean;
  error?: AzerothError;
}

export interface EngineListPayload {
  default: string | null;
  engines: EngineStatus[];
}

export interface ProviderListPayload {
  providers: ProviderStatus[];
  enabled: string[];
}
