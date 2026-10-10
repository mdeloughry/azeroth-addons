import { definePlugin, routerHook } from "@decky/api";
import { staticClasses } from "@decky/ui";
import { FaDragon } from "react-icons/fa";

import { ROUTE, ROUTE_TITLE } from "./routes";
import { PluginProvider } from "./state";
import { FullPage } from "./views/FullPage";
import { MainPanel } from "./views/MainPanel";

export default definePlugin(() => {
  // The full-screen page is registered once and removed when the plugin unloads.
  // Decky mounts routes outside the Quick Access Menu tree, so the page carries
  // its own provider.
  routerHook.addRoute(
    ROUTE,
    () => (
      <PluginProvider>
        <FullPage />
      </PluginProvider>
    ),
    { exact: true },
  );

  return {
    name: "Azeroth Addons",
    titleView: <div className={staticClasses.Title}>{ROUTE_TITLE}</div>,
    content: (
      <PluginProvider>
        <MainPanel />
      </PluginProvider>
    ),
    icon: <FaDragon />,
    onDismount() {
      routerHook.removeRoute(ROUTE);
    },
  };
});
