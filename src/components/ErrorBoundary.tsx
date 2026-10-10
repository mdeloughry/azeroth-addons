import { ButtonItem } from "@decky/ui";
import { Component, ErrorInfo, ReactNode } from "react";

import { reportError } from "../reporting";

interface Props {
  children: ReactNode;
  label?: string;
}

interface State {
  error: Error | null;
}

/**
 * Catches render crashes so a broken view cannot take the whole plugin down,
 * and records them so they show up in Diagnostics.
 */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    reportError({
      code: "UI_CRASH",
      message: error.message || "The interface stopped responding.",
      details: [error.stack, info.componentStack].filter(Boolean).join("\n\n"),
    });
  }

  render(): ReactNode {
    if (!this.state.error) return this.props.children;

    return (
      <div style={{ padding: "16px" }}>
        <div style={{ fontWeight: 600, marginBottom: "4px" }}>
          {this.props.label ?? "Azeroth Addons"} hit an interface error.
        </div>
        <div style={{ fontSize: "11px", opacity: 0.7, marginBottom: "10px" }}>
          {this.state.error.message}
        </div>
        <ButtonItem layout="below" onClick={() => this.setState({ error: null })}>
          Try again
        </ButtonItem>
      </div>
    );
  }
}
