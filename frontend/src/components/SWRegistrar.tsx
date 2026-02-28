"use client";

import { useEffect } from "react";

export default function ServiceWorkerRegistrar() {
    useEffect(() => {
        if ("serviceWorker" in navigator) {
            navigator.serviceWorker
                .register("/sw.js")
                .then(() => console.log("[SilentVoice] SW registered"))
                .catch((err) => console.error("[SilentVoice] SW error:", err));
        }
    }, []);
    return null;
}
