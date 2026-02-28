"use client";

import { useEffect, useRef, useState, useCallback } from "react";

interface Landmark { x: number; y: number; z: number; }
interface HandLandmarkerResult { landmarks: Landmark[][]; }

interface CameraStreamProps {
    onLandmarks: (hands: number[][][]) => void;  // Array of hands
    active: boolean;
}

// Hand skeleton connections
const HAND_CONNECTIONS = [
    [0, 1], [1, 2], [2, 3], [3, 4],
    [0, 5], [5, 6], [6, 7], [7, 8],
    [0, 9], [9, 10], [10, 11], [11, 12],
    [0, 13], [13, 14], [14, 15], [15, 16],
    [0, 17], [17, 18], [18, 19], [19, 20],
    [5, 9], [9, 13], [13, 17],
];

const HAND_COLORS = [
    { line: "#00e5ff", joint: "#ffffff", glow: "#00e5ff" },  // Hand 1: cyan
    { line: "#ff4081", joint: "#ffe0e0", glow: "#ff4081" },  // Hand 2: pink
];

export default function CameraStream({ onLandmarks, active }: CameraStreamProps) {
    const videoRef = useRef<HTMLVideoElement>(null);
    const canvasRef = useRef<HTMLCanvasElement>(null);
    const streamRef = useRef<MediaStream | null>(null);
    const animFrameRef = useRef<number>(0);
    const handLandmarkerRef = useRef<any>(null);
    const [cameraReady, setCameraReady] = useState(false);
    const [error, setError] = useState<string>("");
    const [handCount, setHandCount] = useState(0);

    const initMediaPipe = useCallback(async () => {
        try {
            const vision = await import("@mediapipe/tasks-vision");
            const { HandLandmarker, FilesetResolver } = vision;

            const filesetResolver = await FilesetResolver.forVisionTasks(
                "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@latest/wasm"
            );

            handLandmarkerRef.current = await HandLandmarker.createFromOptions(
                filesetResolver,
                {
                    baseOptions: {
                        modelAssetPath:
                            "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task",
                        delegate: "GPU",
                    },
                    runningMode: "VIDEO",
                    numHands: 2,
                }
            );
            console.log("[SilentVoice] MediaPipe initialized (2 hands)");
        } catch (err) {
            console.error("[SilentVoice] MediaPipe init error:", err);
            setError("Failed to load hand tracking. Please refresh.");
        }
    }, []);

    const startCamera = useCallback(async () => {
        try {
            const stream = await navigator.mediaDevices.getUserMedia({
                video: { facingMode: "user", width: 640, height: 480 },
            });
            streamRef.current = stream;
            if (videoRef.current) {
                videoRef.current.srcObject = stream;
                await videoRef.current.play();
                setCameraReady(true);
            }
        } catch {
            setError("Camera access denied. Please allow camera permissions.");
        }
    }, []);

    const stopCamera = useCallback(() => {
        streamRef.current?.getTracks().forEach((t) => t.stop());
        streamRef.current = null;
        setCameraReady(false);
        setHandCount(0);
        if (animFrameRef.current) cancelAnimationFrame(animFrameRef.current);
    }, []);

    const drawHand = (
        ctx: CanvasRenderingContext2D,
        landmarks: Landmark[],
        w: number, h: number,
        colors: typeof HAND_COLORS[0]
    ) => {
        // Connections
        ctx.strokeStyle = colors.line;
        ctx.lineWidth = 2.5;
        ctx.shadowColor = colors.glow;
        ctx.shadowBlur = 8;
        for (const [a, b] of HAND_CONNECTIONS) {
            const la = landmarks[a], lb = landmarks[b];
            if (!la || !lb) continue;
            ctx.beginPath();
            ctx.moveTo((1 - la.x) * w, la.y * h);
            ctx.lineTo((1 - lb.x) * w, lb.y * h);
            ctx.stroke();
        }
        ctx.shadowBlur = 0;

        // Joints
        for (let i = 0; i < landmarks.length; i++) {
            const lm = landmarks[i];
            const isTip = [4, 8, 12, 16, 20].includes(i);
            ctx.fillStyle = isTip ? colors.glow : colors.joint;
            ctx.shadowColor = colors.glow;
            ctx.shadowBlur = isTip ? 12 : 6;
            ctx.beginPath();
            ctx.arc((1 - lm.x) * w, lm.y * h, isTip ? 5 : 3, 0, 2 * Math.PI);
            ctx.fill();
        }
        ctx.shadowBlur = 0;
    };

    const detect = useCallback(() => {
        if (!videoRef.current || !canvasRef.current || !handLandmarkerRef.current) return;
        const video = videoRef.current;
        const canvas = canvasRef.current;
        const ctx = canvas.getContext("2d");
        if (!ctx) return;

        canvas.width = video.videoWidth || 640;
        canvas.height = video.videoHeight || 480;

        // Draw mirrored video
        ctx.save();
        ctx.scale(-1, 1);
        ctx.drawImage(video, -canvas.width, 0, canvas.width, canvas.height);
        ctx.restore();

        try {
            const result: HandLandmarkerResult =
                handLandmarkerRef.current.detectForVideo(video, performance.now());

            if (result.landmarks && result.landmarks.length > 0) {
                setHandCount(result.landmarks.length);

                // Draw ALL detected hands
                result.landmarks.forEach((hand, idx) => {
                    drawHand(ctx, hand, canvas.width, canvas.height, HAND_COLORS[idx] || HAND_COLORS[0]);
                });

                // Send ALL hands to parent as array of coordinate arrays
                const allHands = result.landmarks.map(hand =>
                    hand.map((lm: Landmark) => [lm.x, lm.y, lm.z])
                );
                onLandmarks(allHands);
            } else {
                setHandCount(0);
            }
        } catch {
            // Frame skip
        }

        animFrameRef.current = requestAnimationFrame(detect);
    }, [onLandmarks]);

    useEffect(() => {
        initMediaPipe();
        return () => stopCamera();
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    useEffect(() => {
        if (active) startCamera();
        else stopCamera();
    }, [active, startCamera, stopCamera]);

    useEffect(() => {
        if (cameraReady && active) detect();
        return () => { if (animFrameRef.current) cancelAnimationFrame(animFrameRef.current); };
    }, [cameraReady, active, detect]);

    return (
        <div className="camera-container">
            <video ref={videoRef} autoPlay playsInline muted style={{ display: "none" }} />
            <canvas ref={canvasRef} className="camera-canvas" />
            {handCount > 0 && (
                <div style={{
                    position: "absolute", top: 8, right: 8, padding: "4px 10px",
                    background: "rgba(0,229,255,0.2)", borderRadius: 8,
                    fontSize: 12, color: "#00e5ff"
                }}>
                    {handCount === 2 ? "✌️ Two Hands" : "✋ One Hand"}
                </div>
            )}
            {error && <div className="camera-error">{error}</div>}
            {!cameraReady && active && !error && (
                <div className="camera-loading">
                    <div className="spinner" />
                    <span>Initializing camera &amp; hand tracker…</span>
                </div>
            )}
        </div>
    );
}
