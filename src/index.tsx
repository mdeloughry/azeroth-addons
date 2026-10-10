import { definePlugin, routerHook } from "@decky/api";
import { staticClasses } from "@decky/ui";
import { FaDragon } from "react-icons/fa";

import { ErrorBoundary } from "./components/ErrorBoundary";
import { installErrorReporting } from "./reporting";
import { ROUTE, ROUTE_TITLE } from "./routes";
import { PluginProvider } from "./state";
import { FullPage } from "./views/FullPage";
import { MainPanel } from "./views/MainPanel";

export default definePlugin(() => {
  // Capture interface crashes and unhandled rejections into the local journal.
  installErrorReporting();

  // The full-screen page is registered once and removed when the plugin unloads.
  // Decky mounts routes outside the Quick Access Menu tree, so the page carries
  // its own provider.
  routerHook.addRoute(
    ROUTE,
    () => (
      <ErrorBoundary label="Azeroth Addons">
        <PluginProvider>
          <FullPage />
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
      routerHook.removeRoute(ROUTE);
    },
  };
});
