"use client";

import { useRef, useState, useCallback, useEffect } from "react";

export interface PredictionResult {
  word: string;
  language: string;
  confidence: number;
  raw_label: string;
  type?: string;  // "emergency" | "prediction"
  confirmed?: boolean;
  error?: string;
}

const WS_URL = process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8000/ws/recognize";

export function useWebSocket() {
  const wsRef = useRef<WebSocket | null>(null);
  const [connected, setConnected] = useState(false);
  const [lastPrediction, setLastPrediction] = useState<PredictionResult | null>(null);

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    const ws = new WebSocket(WS_URL);

    ws.onopen = () => {
      setConnected(true);
      console.log("[SilentVoice] WebSocket connected");
    };

    ws.onmessage = (event) => {
      try {
        const data: PredictionResult = JSON.parse(event.data);
        setLastPrediction(data);
      } catch {
        console.error("[SilentVoice] Failed to parse WS message");
      }
    };

    ws.onclose = () => {
      setConnected(false);
    };

    ws.onerror = () => {
      console.error("[SilentVoice] WebSocket error");
    };

    wsRef.current = ws;
  }, []);

  const disconnect = useCallback(() => {
    wsRef.current?.close();
    wsRef.current = null;
    setConnected(false);
    setLastPrediction(null);
  }, []);

  const sendLandmarks = useCallback(
    (hands: number[][][], language: string = "ASL") => {
      if (wsRef.current?.readyState !== WebSocket.OPEN) return;
      wsRef.current.send(
        JSON.stringify({
          hands,
          language,
          timestamp: Date.now(),
        })
      );
    },
    []
  );

  const resetPrediction = useCallback(() => {
    setLastPrediction(null);
  }, []);

  useEffect(() => {
    return () => {
      wsRef.current?.close();
    };
  }, []);

  return { connected, connect, disconnect, sendLandmarks, lastPrediction, resetPrediction };
}
