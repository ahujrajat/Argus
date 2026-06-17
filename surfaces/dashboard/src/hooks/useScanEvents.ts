import { useEffect, useRef, useState } from "react";

export interface ScanEvent {
  event: string;
  agent?: string;
  cost_usd?: number;
  model_id?: string;
  tokens_in?: number;
  tokens_out?: number;
  total_cost_usd?: number;
  finding_count?: number;
  error?: string;
  skipped?: boolean;
  [key: string]: unknown;
}

const BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export function useScanEvents(scanId: string | null) {
  const [events, setEvents] = useState<ScanEvent[]>([]);
  const [connected, setConnected] = useState(false);
  const esRef = useRef<EventSource | null>(null);

  useEffect(() => {
    if (!scanId) return;
    setEvents([]);
    const es = new EventSource(`${BASE}/api/v1/scans/${scanId}/events`);
    esRef.current = es;
    setConnected(true);

    es.onmessage = (e) => {
      try {
        const parsed: ScanEvent = JSON.parse(e.data) as ScanEvent;
        setEvents((prev) => [...prev, parsed]);
        if (
          parsed.event === "scan_completed" ||
          parsed.event === "scan_failed"
        ) {
          es.close();
          setConnected(false);
        }
      } catch {
        // ignore parse errors
      }
    };

    es.onerror = () => {
      es.close();
      setConnected(false);
    };

    return () => {
      es.close();
      setConnected(false);
    };
  }, [scanId]);

  return { events, connected };
}
