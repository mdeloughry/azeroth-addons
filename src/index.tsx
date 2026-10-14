import { definePlugin, routerHook } from "@decky/api";
import { staticClasses } from "@decky/ui";
import { FaDragon } from "react-icons/fa";

import { ErrorBoundary } from "./components/ErrorBoundary";
import { installErrorReporting } from "./reporting";
import { startPluginUpdater } from "./pluginUpdater";
import { PAGE_TABS, TAB_ROUTES, ROUTE_TITLE } from "./routes";
import { PluginProvider } from "./state";
import { FullPage } from "./views/FullPage";
import { MainPanel } from "./views/MainPanel";

export default definePlugin(() => {
  // Capture interface crashes and unhandled rejections into the local journal.
  installErrorReporting();
  const stopUpdater = startPluginUpdater();

  // The full-screen page is registered once and removed when the plugin unloads.
  // Decky mounts routes outside the Quick Access Menu tree, so the page carries
  // its own provider.
  for (const tab of PAGE_TABS) routerHook.addRoute(
    TAB_ROUTES[tab],
    () => (
      <ErrorBoundary label="Azeroth Addons">
        <PluginProvider>
          <FullPage initialTab={tab} />
        </PluginProvider>
      </ErrorBoundary>
    ),
    { exact: true },
  );

  return {
    name: "Azeroth Addons",
    titleView: <div className={staticClasses.Title}>{ROUTE_TITLE}</div>,
    content: (
      <ErrorBoundary label="Azeroth Addons">
        <PluginProvider>
          <MainPanel />
        </PluginProvider>
      </ErrorBoundary>
    ),
    icon: <FaDragon />,
    onDismount() {
      stopUpdater();
      for (const path of Object.values(TAB_ROUTES)) routerHook.removeRoute(path);
    },
  };
});
