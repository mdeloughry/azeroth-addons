/** Route used by the full-screen page and the Quick Access Menu entry point. */

export const ROUTE = "/azeroth-addons";
export const ROUTE_TITLE = "Azeroth Addons";

export const PAGE_TABS = ["addons", "find", "installations", "settings", "diagnostics"] as const;
export type PageTab = typeof PAGE_TABS[number];
export const TAB_ROUTES: Record<PageTab, string> = {
  addons: ROUTE,
  find: `${ROUTE}/find`,
  installations: `${ROUTE}/installations`,
  settings: `${ROUTE}/settings`,
  diagnostics: `${ROUTE}/diagnostics`,
};
