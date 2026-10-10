/**
 * Frontend error capture.
 *
 * Backend RPC failures are already journalled by the RPC guard with a proper
 * operation name, so this deliberately does **not** report them again - it only
 * covers errors the backend cannot see: React render crashes, unhandled
 * promise rejections and uncaught window errors.
 *
 * Reporting is bounded and deduplicated so a render loop cannot flood the
 * journal, and it can never throw into the UI.
 */

import { api } from "./api";

const MAX_PER_SESSION = 25;
const DEDUPE_WINDOW_MS = 30_000;

let installed = false;
let reported = 0;
const seen = new Map<string, number>();
let currentView: string | undefined;

export function setReportingView(view: string | undefined): void {
  currentView = view;
}

export interface FrontendError {
  code?: string;
  message: string;
  details?: string;
  severity?: string;
}

export function reportError(input: FrontendError): void {
  try {
    const code = input.code ?? "UI_ERROR";
    const key = `${code}|${input.message}`;
    const now = Date.now();
    const last = seen.get(key);
    if (last !== undefined && now - last < DEDUPE_WINDOW_MS) return;
    seen.set(key, now);

    if (reported >= MAX_PER_SESSION) return;
    reported += 1;

    void api
      .reportFrontendError({
        code,
        message: input.message,
        details: input.details,
        severity: input.severity,
        view: currentView,
      })
      .catch(() => {
        /* reporting must never break the interface */
      });
  } catch {
    /* never throw from an error handler */
  }
}

function describe(value: unknown): { message: string; details?: string } {
  if (value instanceof Error) {
    return { message: value.message || value.name, details: value.stack };
  }
  if (typeof value === "string") return { message: value };
  try {
    return { message: JSON.stringify(value) };
  } catch {
    return { message: String(value) };
  }
}

export function installErrorReporting(): void {
  if (installed || typeof window === "undefined") return;
  installed = true;

  window.addEventListener("error", (event) => {
    const described = describe(event.error);
    reportError({
      code: "UI_ERROR",
      message: described.message || event.message || "Unknown interface error",
      details: described.details ?? `${event.filename ?? "?"}:${event.lineno ?? 0}`,
    });
  });

  window.addEventListener("unhandledrejection", (event) => {
    const described = describe(event.reason);
    reportError({ code: "UI_UNHANDLED_REJECTION", message: described.message, details: described.details });
  });
}
