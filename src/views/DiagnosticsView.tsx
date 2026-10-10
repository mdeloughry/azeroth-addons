import {
  ButtonItem,
  Dropdown,
  PanelSection,
  PanelSectionRow,
  Spinner,
  TextField,
  ToggleField,
} from "@decky/ui";
import { FC, useCallback, useEffect, useState } from "react";

import { api, errorMessage } from "../api";
import { Badge } from "../components/Badges";
import { usePlugin } from "../state";
import { JournalEvent, JournalPayload, ReportingPayload } from "../types";

const META: React.CSSProperties = { fontSize: "11px", opacity: 0.68 };
const MONO: React.CSSProperties = {
  fontFamily: "monospace",
  fontSize: "11px",
  whiteSpace: "pre-wrap",
  wordBreak: "break-word",
  background: "rgba(0,0,0,0.35)",
  borderRadius: "3px",
  padding: "6px",
  marginTop: "4px",
  maxHeight: "150px",
  overflowY: "auto",
};

const FORMAT_OPTIONS = [
  { data: 0, label: "Sentry / GlitchTip (recommended)" },
  { data: 1, label: "Plain JSON webhook" },
];

function formatWhen(timestamp: string): string {
  const parsed = new Date(timestamp);
  return Number.isNaN(parsed.getTime()) ? timestamp : parsed.toLocaleString();
}

const EventDetails: FC<{ event: JournalEvent }> = ({ event }) => (
  <div style={{ marginTop: "4px" }}>
    {event.context && Object.keys(event.context).length > 0 ? (
      <div style={MONO}>
        {Object.entries(event.context)
          .map(([key, value]) => `${key}: ${String(value)}`)
          .join("\n")}
      </div>
    ) : null}
    {event.details ? <div style={MONO}>{event.details}</div> : null}
    {event.frames && event.frames.length > 0 ? (
      <div style={MONO}>
        {event.frames
          .map((frame) => `${frame.filename ?? "?"}:${frame.lineno ?? 0} in ${frame.function ?? "?"}`)
          .join("\n")}
      </div>
    ) : null}
  </div>
);

/**
 * Diagnostics: what went wrong on this device, and strictly opt-in reporting.
 *
 * Nothing is transmitted until reporting is switched on and a destination is
 * configured, and the exact request body is shown before that happens.
 */
export const DiagnosticsView: FC = () => {
  const plugin = usePlugin();
  const [journal, setJournal] = useState<JournalPayload | null>(null);
  const [reporting, setReporting] = useState<ReportingPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [notice, setNotice] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [dsnDraft, setDsnDraft] = useState("");
  const [endpointDraft, setEndpointDraft] = useState("");
  const [showPreview, setShowPreview] = useState(false);

  const busy = plugin.busy !== null;
  const status = reporting?.status;
  const sendSentry = (status?.format ?? "sentry") === "sentry";

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [journalPayload, reportingPayload] = await Promise.all([
        api.getErrorJournal(50),
        api.getErrorReporting(),
      ]);
      setJournal(journalPayload);
      setReporting(reportingPayload);
      if (reportingPayload.status.format === "custom") {
        setEndpointDraft((current) => current || reportingPayload.status.destination);
      }
    } catch (cause) {
      setNotice(errorMessage(cause));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const applySettings = async (values: Record<string, unknown>) => {
    setNotice(null);
    await plugin.saveSettings(values);
    await load();
  };

  const saveDestination = async () => {
    setNotice(null);
    try {
      if (sendSentry) {
        await api.setCredential("sentry", dsnDraft.trim());
        setDsnDraft("");
      } else {
        await plugin.saveSettings({ errorReportingEndpoint: endpointDraft.trim() });
      }
      await load();
      setNotice("Destination saved.");
    } catch (cause) {
      setNotice(errorMessage(cause));
    }
  };

  const sendTest = async () => {
    setNotice(null);
    try {
      const result = await api.sendTestErrorReport();
      setNotice(
        result.result.sent
          ? `Test report delivered (HTTP ${result.result.status}).`
          : `Not delivered: ${result.result.reason ?? "unknown reason"}`,
      );
      await load();
    } catch (cause) {
      setNotice(errorMessage(cause));
    }
  };

  return (
    <>
      <PanelSection title="Errors on this device" spinner={loading && !journal}>
        <PanelSectionRow>
          <div style={META}>
            {journal
              ? `${journal.summary.total} recorded · ${journal.summary.distinctCodes} distinct · stored locally only`
              : "Loading…"}
          </div>
        </PanelSectionRow>
        <PanelSectionRow>
          <ButtonItem layout="below" disabled={busy} onClick={() => void load()}>
            Refresh
          </ButtonItem>
        </PanelSectionRow>
        {journal && journal.events.length > 0 ? (
          <PanelSectionRow>
            <ButtonItem
              layout="below"
              disabled={busy}
              onClick={() => {
                void (async () => {
                  await api.clearErrorJournal();
                  await load();
                })();
              }}
            >
              Clear journal
            </ButtonItem>
          </PanelSectionRow>
        ) : null}
      </PanelSection>

      {journal && journal.events.length === 0 ? (
        <PanelSection>
          <PanelSectionRow>
            <div style={META}>Nothing recorded. Errors will appear here as they happen.</div>
          </PanelSectionRow>
        </PanelSection>
      ) : null}

      {journal?.events.map((event) => (
        <PanelSection key={event.id}>
          <PanelSectionRow>
            <div style={{ width: "100%" }}>
              <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                <span style={{ fontWeight: 600, fontSize: "12px" }}>{event.code}</span>
                {event.count > 1 ? <Badge tone="warn">×{event.count}</Badge> : null}
                <Badge tone={event.source === "frontend" ? "info" : "muted"}>{event.source}</Badge>
                <span style={{ marginLeft: "auto", ...META }}>{formatWhen(event.timestamp)}</span>
              </div>
              <div style={{ fontSize: "12px", opacity: 0.85, marginTop: "2px" }}>{event.message}</div>
              {expanded === event.id ? <EventDetails event={event} /> : null}
            </div>
          </PanelSectionRow>
          <PanelSectionRow>
            <ButtonItem
              layout="below"
              onClick={() => setExpanded(expanded === event.id ? null : event.id)}
            >
              {expanded === event.id ? "Hide details" : "Details"}
            </ButtonItem>
          </PanelSectionRow>
        </PanelSection>
      ))}

      <PanelSection title="Send error reports">
        <PanelSectionRow>
          <div style={META}>
            Off by default. Nothing leaves this device unless you turn it on and point it at your own destination.
          </div>
        </PanelSectionRow>
        <PanelSectionRow>
          <ToggleField
            label="Send error reports"
            description="Sends redacted errors to the destination below."
            checked={Boolean(status?.enabled)}
            disabled={busy || !status}
            onChange={(value: boolean) => void applySettings({ enableErrorReporting: value })}
          />
        </PanelSectionRow>
        <PanelSectionRow>
          <Dropdown
            menuLabel="Destination type"
            rgOptions={FORMAT_OPTIONS}
            selectedOption={sendSentry ? 0 : 1}
            disabled={busy || !status}
            onChange={(option) =>
              void applySettings({ errorReportingFormat: option.data === 0 ? "sentry" : "custom" })
            }
          />
        </PanelSectionRow>

        {sendSentry ? (
          <PanelSectionRow>
            <TextField
              label="Sentry DSN"
              description={
                status?.destination
                  ? `Saved: ${status.destination}`
                  : "From your GlitchTip or Sentry project settings."
              }
              bIsPassword
              bShowClearAction
              disabled={busy}
              value={dsnDraft}
              onChange={(event) => setDsnDraft(event.currentTarget.value)}
            />
          </PanelSectionRow>
        ) : (
          <PanelSectionRow>
            <TextField
              label="Webhook URL"
              description="Must be https. The event JSON is POSTed here."
              disabled={busy}
              value={endpointDraft}
              onChange={(event) => setEndpointDraft(event.currentTarget.value)}
            />
          </PanelSectionRow>
        )}

        <PanelSectionRow>
          <ButtonItem
            layout="below"
            disabled={busy || (sendSentry ? dsnDraft.trim().length === 0 : endpointDraft.trim().length === 0)}
            onClick={() => void saveDestination()}
          >
            Save destination
          </ButtonItem>
        </PanelSectionRow>
        <PanelSectionRow>
          <ButtonItem layout="below" disabled={busy || Boolean(status?.problem)} onClick={() => void sendTest()}>
            Send a test report
          </ButtonItem>
        </PanelSectionRow>
        <PanelSectionRow>
          <ButtonItem layout="below" onClick={() => setShowPreview((current) => !current)}>
            {showPreview ? "Hide preview" : "Preview what would be sent"}
          </ButtonItem>
        </PanelSectionRow>

        {status?.problem ? (
          <PanelSectionRow>
            <div style={{ ...META, color: "#f0ad4e" }}>{status.problem}</div>
          </PanelSectionRow>
        ) : null}
        {status ? (
          <PanelSectionRow>
            <div style={META}>
              {status.usable ? "Ready" : "Not ready"} · sent {status.sent} · failed {status.failed}
              {status.lastSentAt ? ` · last ${formatWhen(status.lastSentAt)}` : ""}
            </div>
          </PanelSectionRow>
        ) : null}
        {status?.lastError ? (
          <PanelSectionRow>
            <div style={{ ...META, color: "#ef8b8b" }}>Last attempt: {status.lastError}</div>
          </PanelSectionRow>
        ) : null}
        {loading && !reporting ? (
          <PanelSectionRow>
            <Spinner style={{ width: "16px", height: "16px" }} />
          </PanelSectionRow>
        ) : null}
      </PanelSection>

      {showPreview ? (
        <PanelSection title="Exactly what gets sent">
          {reporting?.preview.problem ? (
            <PanelSectionRow>
              <div style={META}>{reporting.preview.problem}</div>
            </PanelSectionRow>
          ) : null}
          {reporting?.preview.request ? (
            <>
              <PanelSectionRow>
                <div style={META}>{reporting.preview.request.url}</div>
              </PanelSectionRow>
              <PanelSectionRow>
                <div style={{ ...MONO, maxHeight: "260px" }}>
                  {JSON.stringify(reporting.preview.request.body, null, 2)}
                </div>
              </PanelSectionRow>
              <PanelSectionRow>
                <div style={META}>Credentials are masked here; the real request carries them.</div>
              </PanelSectionRow>
            </>
          ) : null}
        </PanelSection>
      ) : null}

      {notice ? (
        <PanelSection>
          <PanelSectionRow>
            <div style={META}>{notice}</div>
          </PanelSectionRow>
        </PanelSection>
      ) : null}
    </>
  );
};
