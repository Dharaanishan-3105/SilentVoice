"use client";

import { useEffect, useRef, useState, useCallback } from "react";

interface Frame {
    hand: number[][]; // [[x,y,z], ...] — 21 landmarks
    pose: number[][];
}

interface SignAvatarProps {
    frames: Frame[];
    playing: boolean;
    loop?: boolean;
    label?: string;
}

// Hand connections for stick figure
const HAND_CONNECTIONS = [
    [0, 1], [1, 2], [2, 3], [3, 4],
    [0, 5], [5, 6], [6, 7], [7, 8],
    [0, 9], [9, 10], [10, 11], [11, 12],
    [0, 13], [13, 14], [14, 15], [15, 16],
    [0, 17], [17, 18], [18, 19], [19, 20],
    [5, 9], [9, 13], [13, 17],
];

export default function SignAvatar({
    frames,
    playing,
    loop = true,
    label,
}: SignAvatarProps) {
    const canvasRef = useRef<HTMLCanvasElement>(null);
    const frameIdx = useRef(0);
    const animRef = useRef<number>(0);
    const lastTime = useRef(0);
    const [currentFrame, setCurrentFrame] = useState(0);

    const FPS = 24;

    const drawFrame = useCallback(
        (ctx: CanvasRenderingContext2D, frame: Frame, w: number, h: number) => {
            ctx.clearRect(0, 0, w, h);

            // Background gradient
            const grad = ctx.createRadialGradient(w / 2, h / 2, 0, w / 2, h / 2, w * 0.6);
            grad.addColorStop(0, "rgba(124, 77, 255, 0.08)");
            grad.addColorStop(1, "rgba(0, 229, 255, 0.03)");
            ctx.fillStyle = grad;
            ctx.fillRect(0, 0, w, h);

            if (!frame.hand || frame.hand.length < 21) return;

            // Draw connections with gradient effect
            for (const [a, b] of HAND_CONNECTIONS) {
                const la = frame.hand[a];
                const lb = frame.hand[b];
                if (!la || !lb) continue;

                const lineGrad = ctx.createLinearGradient(
                    la[0] * w, la[1] * h,
                    lb[0] * w, lb[1] * h
                );
                lineGrad.addColorStop(0, "#7c4dff");
                lineGrad.addColorStop(1, "#00e5ff");

                ctx.strokeStyle = lineGrad;
                ctx.lineWidth = 3;
                ctx.shadowColor = "#00e5ff";
                ctx.shadowBlur = 12;
                ctx.lineCap = "round";
                ctx.beginPath();
                ctx.moveTo(la[0] * w, la[1] * h);
                ctx.lineTo(lb[0] * w, lb[1] * h);
                ctx.stroke();
            }
            ctx.shadowBlur = 0;

            // Draw joints with glow
            for (let i = 0; i < frame.hand.length; i++) {
                const [x, y] = frame.hand[i];
                const isFingerTip = [4, 8, 12, 16, 20].includes(i);
                const radius = isFingerTip ? 6 : 4;

                // Outer glow
                ctx.fillStyle = isFingerTip
                    ? "rgba(0, 229, 255, 0.4)"
                    : "rgba(124, 77, 255, 0.3)";
                ctx.beginPath();
                ctx.arc(x * w, y * h, radius + 4, 0, 2 * Math.PI);
                ctx.fill();

                // Inner dot
                ctx.fillStyle = isFingerTip ? "#00e5ff" : "#e0e0e0";
                ctx.shadowColor = isFingerTip ? "#00e5ff" : "#7c4dff";
                ctx.shadowBlur = 10;
                ctx.beginPath();
                ctx.arc(x * w, y * h, radius, 0, 2 * Math.PI);
                ctx.fill();
            }
            ctx.shadowBlur = 0;

            // Label overlay
            if (label) {
                ctx.fillStyle = "rgba(0, 229, 255, 0.9)";
                ctx.font = "bold 16px 'Inter', sans-serif";
                ctx.textAlign = "center";
                ctx.fillText(label.toUpperCase(), w / 2, h - 16);
            }
        },
        [label]
    );

    const animate = useCallback(
        (timestamp: number) => {
            if (!canvasRef.current || frames.length === 0) return;
            const ctx = canvasRef.current.getContext("2d");
            if (!ctx) return;
            const w = canvasRef.current.width;
            const h = canvasRef.current.height;

            const elapsed = timestamp - lastTime.current;
            if (elapsed >= 1000 / FPS) {
                lastTime.current = timestamp;
                drawFrame(ctx, frames[frameIdx.current], w, h);
                setCurrentFrame(frameIdx.current);

                frameIdx.current++;
                if (frameIdx.current >= frames.length) {
                    if (loop) {
                        frameIdx.current = 0;
                    } else {
                        return;
                    }
                }
            }
            animRef.current = requestAnimationFrame(animate);
        },
        [frames, loop, drawFrame]
    );

    useEffect(() => {
        if (playing && frames.length > 0) {
            frameIdx.current = 0;
            lastTime.current = 0;
            animRef.current = requestAnimationFrame(animate);
        }
        return () => {
            if (animRef.current) cancelAnimationFrame(animRef.current);
        };
    }, [playing, frames, animate]);

    // Draw static first frame if not playing
    useEffect(() => {
        if (!playing && frames.length > 0 && canvasRef.current) {
            const ctx = canvasRef.current.getContext("2d");
            if (ctx) {
                drawFrame(ctx, frames[0], canvasRef.current.width, canvasRef.current.height);
            }
        }
    }, [playing, frames, drawFrame]);

    return (
        <div className="avatar-container">
            <canvas
                ref={canvasRef}
                width={400}
                height={400}
                className="avatar-canvas"
            />
            {frames.length > 0 && (
                <div className="avatar-progress">
                    <div
                        className="avatar-progress-bar"
                        style={{ width: `${((currentFrame + 1) / frames.length) * 100}%` }}
                    />
                </div>
            )}
        </div>
    );
}
