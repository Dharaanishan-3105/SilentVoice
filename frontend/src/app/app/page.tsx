"use client";

import { useState, useCallback, useRef, useEffect } from "react";
import dynamic from "next/dynamic";
import Link from "next/link";
import Image from "next/image";
import { useRouter } from "next/navigation";
import { useWebSocket } from "@/hooks/useWebSocket";

const CameraStream = dynamic(() => import("@/components/CameraStream"), { ssr: false });
const SignAvatar = dynamic(() => import("@/components/SignAvatar"), { ssr: false });

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type AppMode = "conversation" | "emergency" | "learning" | "workplace" | "expression";
type Language = "ASL" | "ISL" | "TSL";
type LearnCategory = "phrases" | "numbers" | "alphabet" | "emergency";

const VOCABULARY: Record<Language, Record<LearnCategory, string[]>> = {
    ASL: {
        phrases: ["hello", "thank you", "please", "yes", "no", "help", "sorry", "love", "friend", "family",
            "eat", "drink", "water", "more", "stop", "good", "bad", "happy", "sad", "want",
            "name", "how", "what", "where", "when", "come", "go", "finish", "again", "understand"],
        numbers: ["0", "1", "2", "3", "4", "5", "6", "7", "8", "9"],
        alphabet: "abcdefghijklmnopqrstuvwxyz".split(""),
        emergency: ["help", "call ambulance", "i need help", "i cannot hear", "i am allergic", "call police", "emergency", "danger", "pain", "medicine"],
    },
    ISL: {
        phrases: ["namaste", "dhanyavaad", "kripaya", "haan", "nahi", "madad", "maafi", "pyaar", "dost", "parivaar",
            "khana", "peena", "paani", "aur", "ruko", "accha", "bura", "khush", "dukhi", "chahiye",
            "naam", "kaise", "kya", "kahan", "kab", "aao", "jao", "khatam", "phir_se", "samajh"],
        numbers: ["0", "1", "2", "3", "4", "5", "6", "7", "8", "9"],
        alphabet: "abcdefghijklmnopqrstuvwxyz".split(""),
        emergency: ["help", "call ambulance", "i need help", "i cannot hear", "i am allergic", "call police", "emergency", "danger", "pain", "medicine"],
    },
    TSL: {
        phrases: ["vanakkam", "nandri", "thayavu_seithu", "aam", "illai", "udavi", "mannithu", "anbu", "nanbane", "kudumbam",
            "saapidu", "kudi", "thanni", "innum", "nil", "nalla", "ketta", "santhosham", "varutham", "venum",
            "peyar", "eppadi", "enna", "enga", "eppo", "vaa", "po", "mudinthathu", "meendum", "puriyuthu"],
        numbers: ["0", "1", "2", "3", "4", "5", "6", "7", "8", "9"],
        alphabet: [
            // Tamil Vowels (உயிர் எழுத்துகள்)
            "அ", "ஆ", "இ", "ஈ", "உ", "ஊ", "எ", "ஏ", "ஐ", "ஒ", "ஓ", "ஔ",
            // Tamil Consonants (மெய் எழுத்துகள்)
            "க", "ங", "ச", "ஞ", "ட", "ண", "த", "ந", "ப", "ம", "ய", "ர", "ல", "வ", "ழ", "ள", "ற", "ன",
        ],
        emergency: ["help", "call ambulance", "i need help", "i cannot hear", "i am allergic", "call police", "emergency", "danger", "pain", "medicine"],
    },
};

const EMERGENCY_ITEMS = [
    { icon: "🆘", text: "I Need Help", phrase: "i need help", sub: "General distress" },
    { icon: "🚑", text: "Call Ambulance", phrase: "call ambulance", sub: "Medical emergency" },
    { icon: "🚔", text: "Call Police", phrase: "call police", sub: "Safety threat" },
    { icon: "🚫", text: "I Cannot Hear", phrase: "i cannot hear", sub: "Inform others" },
    { icon: "⚠️", text: "I Am Allergic", phrase: "i am allergic", sub: "Allergy alert" },
    { icon: "💊", text: "Need Medicine", phrase: "medicine", sub: "Medical need" },
    { icon: "🔥", text: "Danger", phrase: "danger", sub: "Hazard warning" },
    { icon: "😣", text: "In Pain", phrase: "pain", sub: "Express pain" },
];

interface AvatarFrame { hand: number[][]; pose: number[][]; }

export default function AppPage() {
    const router = useRouter();
    const [authChecked, setAuthChecked] = useState(false);
    const [isGuest, setIsGuest] = useState(false);
    const [mode, setMode] = useState<AppMode>("conversation");
    const [language, setLanguage] = useState<Language>("ASL");
    const [cameraActive, setCameraActive] = useState(false);
    const [transcript, setTranscript] = useState<string[]>([]);
    const [mobileNavOpen, setMobileNavOpen] = useState(false);

    // Guest restrictions: these modes require a registered account
    const GUEST_LOCKED_MODES: AppMode[] = ["learning", "workplace", "expression"];

    // ── Auth guard ──
    useEffect(() => {
        const user = localStorage.getItem("sv_user");
        if (!user) {
            router.replace("/login");
            return;
        }
        try {
            const parsed = JSON.parse(user);
            if (!parsed.email && !parsed.name) {
                router.replace("/login");
                return;
            }
            // Check if guest
            setIsGuest(parsed.isGuest === true || parsed.email === "guest");
        } catch {
            router.replace("/login");
            return;
        }
        setAuthChecked(true);
    }, [router]);


    // Engine 2
    const [textInput, setTextInput] = useState("");
    const [avatarFrames, setAvatarFrames] = useState<AvatarFrame[]>([]);
    const [avatarPlaying, setAvatarPlaying] = useState(false);
    const [avatarLabel, setAvatarLabel] = useState("");

    // Learning
    const [learnCategory, setLearnCategory] = useState<LearnCategory>("phrases");
    const [targetWord, setTargetWord] = useState("");
    const [accuracy, setAccuracy] = useState<number | null>(null);
    const [score, setScore] = useState(0);
    const [streak, setStreak] = useState(0);
    const [level, setLevel] = useState(1);

    // Speech recognition (Conversation)
    const [isListening, setIsListening] = useState(false);
    const [speechText, setSpeechText] = useState("");
    const recognitionRef = useRef<any>(null);

    // Expression recorder
    const [isRecording, setIsRecording] = useState(false);
    const [recordedWords, setRecordedWords] = useState<string[]>([]);

    // Workplace
    const [meetingTranscript, setMeetingTranscript] = useState<string[]>([]);

    // Offline
    const [isOffline, setIsOffline] = useState(false);

    // WebSocket
    const { connected, connect, disconnect, sendLandmarks, lastPrediction, resetPrediction } = useWebSocket();
    const lastSpoken = useRef("");

    // ── Reset ALL state when switching modes ──
    const switchMode = useCallback((newMode: AppMode) => {
        if (newMode === mode) return;
        // Block guests from locked modes
        if (isGuest && GUEST_LOCKED_MODES.includes(newMode)) {
            return; // Don't switch
        }
        setCameraActive(false);
        disconnect();
        setTranscript([]);
        resetPrediction();
        lastSpoken.current = "";
        setAvatarFrames([]);
        setAvatarPlaying(false);
        setAvatarLabel("");
        setTextInput("");
        setTargetWord("");
        setAccuracy(null);
        setSpeechText("");
        setIsListening(false);
        setIsRecording(false);
        setRecordedWords([]);
        setMeetingTranscript([]);
        setMode(newMode);
    }, [mode, isGuest, disconnect, resetPrediction]);

    // Check offline status
    useEffect(() => {
        const handleOnline = () => setIsOffline(false);
        const handleOffline = () => setIsOffline(true);
        window.addEventListener("online", handleOnline);
        window.addEventListener("offline", handleOffline);
        setIsOffline(!navigator.onLine);
        return () => {
            window.removeEventListener("online", handleOnline);
            window.removeEventListener("offline", handleOffline);
        };
    }, []);

    // ── Engine 1: Camera Sign Recognition ──
    const handleToggleCamera = useCallback(() => {
        if (cameraActive) { setCameraActive(false); disconnect(); }
        else { setCameraActive(true); connect(); }
    }, [cameraActive, connect, disconnect]);

    const handleLandmarks = useCallback((hands: number[][][]) => {
        sendLandmarks(hands, language);
    }, [sendLandmarks, language]);

    // Process predictions
    useEffect(() => {
        if (!lastPrediction) return;
        const word = lastPrediction.word;
        if (word === "unknown" || word === lastSpoken.current) return;

        setTranscript((prev) => [...prev, word].slice(-30));
        lastSpoken.current = word;

        // TTS
        if ("speechSynthesis" in window && lastPrediction.confidence > 0.3) {
            const utter = new SpeechSynthesisUtterance(word);
            utter.rate = 0.9;
            speechSynthesis.speak(utter);
        }

        // Learning accuracy
        if (mode === "learning" && targetWord) {
            if (word.toLowerCase() === targetWord.toLowerCase()) {
                const acc = Math.round(lastPrediction.confidence * 100);
                setAccuracy(acc);
                if (acc > 60) {
                    setScore((s) => s + 10);
                    setStreak((s) => s + 1);
                    if ((score + 10) % 100 === 0) setLevel((l) => l + 1);
                }
            } else {
                setAccuracy(Math.max(0, Math.round(lastPrediction.confidence * 25)));
                setStreak(0);
            }
        }

        // Expression recording
        if (mode === "expression" && isRecording) {
            setRecordedWords((prev) => [...prev, word]);
        }

        // Workplace
        if (mode === "workplace") {
            setMeetingTranscript((prev) => [...prev, word].slice(-100));
        }
    }, [lastPrediction, mode, targetWord, score, isRecording]);

    // ── Engine 2: Text/Speech → Sign ──
    const handlePlaySign = useCallback(async (word: string) => {
        try {
            const res = await fetch(`${API_BASE}/api/sign-sequence?word=${encodeURIComponent(word)}&language=${language}`);
            const data = await res.json();
            if (data.frames?.length > 0) {
                setAvatarFrames(data.frames);
                setAvatarLabel(word);
                setAvatarPlaying(true);
            }
        } catch (err) {
            console.error("[SilentVoice] Fetch error:", err);
        }
    }, [language]);

    const handleTextSubmit = useCallback(() => {
        const word = textInput.trim().toLowerCase();
        if (word) { handlePlaySign(word); setTextInput(""); }
    }, [textInput, handlePlaySign]);

    // ── Speech Recognition (Conversation/Workplace) ──
    const startSpeechRecognition = useCallback(() => {
        if (!("webkitSpeechRecognition" in window || "SpeechRecognition" in window)) {
            alert("Speech recognition not supported in this browser. Try Chrome.");
            return;
        }
        const SpeechRec = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
        const recognition = new SpeechRec();
        recognition.continuous = true;
        recognition.interimResults = true;
        recognition.lang = "en-US";

        recognition.onresult = (event: any) => {
            let final = "";
            for (let i = event.resultIndex; i < event.results.length; i++) {
                const t = event.results[i][0].transcript;
                if (event.results[i].isFinal) {
                    final += t;
                } else {
                    setSpeechText(t);
                }
            }
            if (final) {
                setSpeechText(final);
                // Auto-play sign for the spoken text
                const lastWord = final.trim().split(" ").pop()?.toLowerCase() || "";
                if (lastWord) handlePlaySign(lastWord);

                if (mode === "workplace") {
                    setMeetingTranscript((prev) => [...prev, final.trim()].slice(-100));
                }
            }
        };
        recognition.onerror = () => setIsListening(false);
        recognition.onend = () => setIsListening(false);
        recognition.start();
        recognitionRef.current = recognition;
        setIsListening(true);
    }, [handlePlaySign, mode]);

    const stopSpeechRecognition = useCallback(() => {
        recognitionRef.current?.stop();
        recognitionRef.current = null;
        setIsListening(false);
    }, []);

    // ── Learning ──
    const pickRandomWord = useCallback(() => {
        const words = VOCABULARY[language][learnCategory];
        const rand = words[Math.floor(Math.random() * words.length)];
        setTargetWord(rand);
        setAccuracy(null);
        handlePlaySign(rand);
    }, [language, learnCategory, handlePlaySign]);

    // ── Emergency ──
    const handleEmergency = useCallback((phrase: string) => {
        handlePlaySign(phrase);
        if ("speechSynthesis" in window) {
            const utter = new SpeechSynthesisUtterance(phrase);
            utter.rate = 0.8;
            utter.volume = 1;
            speechSynthesis.speak(utter);
        }
    }, [handlePlaySign]);

    // ── Expression Recorder ──
    const toggleRecording = useCallback(() => {
        if (isRecording) {
            setIsRecording(false);
        } else {
            setRecordedWords([]);
            setIsRecording(true);
            if (!cameraActive) handleToggleCamera();
        }
    }, [isRecording, cameraActive, handleToggleCamera]);

    const shareExpression = useCallback(() => {
        const text = recordedWords.join(" ");
        if ("speechSynthesis" in window && text) {
            const utter = new SpeechSynthesisUtterance(text);
            speechSynthesis.speak(utter);
        }
        if (navigator.share) {
            navigator.share({ title: "SilentVoice Message", text });
        }
    }, [recordedWords]);

    const allWords = VOCABULARY[language][learnCategory] || [];

    // Show loading while checking auth
    if (!authChecked) {
        return (
            <div className="auth-container">
                <div className="glass-card" style={{ padding: 40, textAlign: "center" }}>
                    <div style={{ fontSize: 32, marginBottom: 16 }}>🤟</div>
                    <p style={{ color: "var(--sv-text-secondary)" }}>Loading SilentVoice...</p>
                </div>
            </div>
        );
    }

    return (
        <>
            {/* ── Offline Banner ── */}
            {isOffline && <div className="offline-banner">📡 You are offline — Emergency mode still available</div>}

            {/* ── Navbar ── */}
            <nav className="navbar">
                <Link href="/" className="navbar-brand" style={{ textDecoration: "none", color: "inherit" }}>
                    <Image src="/logo.png" alt="SilentVoice" width={32} height={32} style={{ borderRadius: 6 }} />
                    SilentVoice
                </Link>

                <button className="hamburger" onClick={() => setMobileNavOpen(!mobileNavOpen)}>
                    <span /><span /><span />
                </button>

                <div className={`navbar-links ${mobileNavOpen ? "open" : ""}`}>
                    {([
                        { key: "conversation", label: "💬 Conversation", cls: "" },
                        { key: "emergency", label: "🚨 Emergency", cls: "emergency" },
                        { key: "learning", label: "📚 Learning", cls: "" },
                        { key: "workplace", label: "🏢 Workplace", cls: "" },
                        { key: "expression", label: "💜 Expression", cls: "" },
                    ] as { key: AppMode; label: string; cls: string }[]).map((m) => {
                        const locked = isGuest && GUEST_LOCKED_MODES.includes(m.key);
                        return (
                            <button
                                key={m.key}
                                className={`mode-tab ${m.cls} ${mode === m.key ? "active" : ""} ${locked ? "locked" : ""}`}
                                onClick={() => {
                                    if (locked) {
                                        router.push("/register");
                                        return;
                                    }
                                    switchMode(m.key); setMobileNavOpen(false);
                                }}
                                title={locked ? "Create an account to unlock" : undefined}
                            >
                                {m.label}{locked ? " 🔒" : ""}
                            </button>
                        );
                    })}
                </div>

                <div className="navbar-right">
                    {isGuest && (
                        <Link href="/register" className="btn btn-primary" style={{ fontSize: "0.75rem", padding: "5px 14px" }}>
                            ⭐ Upgrade
                        </Link>
                    )}
                    <div className={`status-chip ${connected ? "connected" : "disconnected"}`}>
                        <span className="status-dot" />
                        {connected ? "Live" : "Offline"}
                    </div>
                    <button className="btn btn-ghost" style={{ fontSize: "0.75rem", padding: "5px 10px" }}
                        onClick={() => { localStorage.clear(); router.push("/login"); }}>
                        {isGuest ? "Sign In" : "Logout"}
                    </button>
                </div>
            </nav>

            {/* Guest Banner */}
            {isGuest && (
                <div style={{
                    position: "fixed", top: 64, left: 0, right: 0, zIndex: 90,
                    background: "linear-gradient(135deg, rgba(124,77,255,0.15), rgba(0,229,255,0.1))",
                    borderBottom: "1px solid rgba(124,77,255,0.2)",
                    padding: "8px 24px", display: "flex", alignItems: "center",
                    justifyContent: "center", gap: 12, fontSize: "0.82rem",
                }}>
                    👋 Guest Mode — Conversation &amp; Emergency only.
                    <Link href="/register" style={{ color: "var(--sv-accent-cyan)", fontWeight: 600 }}>
                        Create free account to unlock all features →
                    </Link>
                </div>
            )}

            {/* ── Main ── */}
            <div className="app-container" style={isOffline ? { paddingTop: "calc(var(--sv-nav-height) + 48px)" } : undefined}>
                {/* ── Hero ── */}
                <section className="hero-section">
                    <h1 className="hero-title">
                        {mode === "conversation" && "Two-Way Sign Translation"}
                        {mode === "emergency" && "🚨 Emergency Mode"}
                        {mode === "learning" && "Learn Sign Language"}
                        {mode === "workplace" && "Workplace Accessibility"}
                        {mode === "expression" && "Personal Expression"}
                    </h1>
                    <p className="hero-subtitle">
                        {mode === "conversation" && "Sign to speak, speak to see sign. Real-time two-way communication."}
                        {mode === "emergency" && "One-tap emergency phrases with instant sign animation and voice output."}
                        {mode === "learning" && "Practice signs with AI feedback. Alphabet, numbers, phrases — all gamified."}
                        {mode === "workplace" && "Live meeting captioning with sign avatar. Accessibility for all."}
                        {mode === "expression" && "Record sign messages, convert to voice, share with your loved ones."}
                    </p>
                    <div style={{ display: "flex", justifyContent: "center", marginTop: 16 }}>
                        <div className="lang-selector">
                            {(["ASL", "ISL", "TSL"] as Language[]).map((l) => (
                                <button key={l} className={`lang-btn ${language === l ? "active" : ""}`} onClick={() => setLanguage(l)}>
                                    {l}
                                </button>
                            ))}
                        </div>
                    </div>
                </section>

                {/* ═════════════════════ CONVERSATION MODE ═════════════════════ */}
                {mode === "conversation" && (
                    <div className="main-grid">
                        <div className="glass-card engine-panel">
                            <div className="engine-header">
                                <div className="engine-title">
                                    <span className="engine-badge e1">Engine 1</span>
                                    Sign → Text / Speech
                                </div>
                                <button className={`btn ${cameraActive ? "btn-danger" : "btn-primary"}`} onClick={handleToggleCamera}>
                                    {cameraActive ? "⏹ Stop" : "📷 Camera"}
                                </button>
                            </div>
                            <CameraStream onLandmarks={handleLandmarks} active={cameraActive} />
                            <div className="prediction-box">
                                <div className="prediction-word">
                                    {lastPrediction?.word && lastPrediction.word !== "unknown"
                                        ? lastPrediction.word
                                        : cameraActive ? "Waiting for sign…" : "Start camera to begin"}
                                </div>
                                {lastPrediction && lastPrediction.word !== "unknown" && (
                                    <div className="prediction-meta">
                                        <span>{lastPrediction.language}</span>
                                        <div className="confidence-bar">
                                            <div className="confidence-fill" style={{ width: `${lastPrediction.confidence * 100}%` }} />
                                        </div>
                                        <span>{Math.round(lastPrediction.confidence * 100)}%</span>
                                    </div>
                                )}
                            </div>
                            {transcript.length > 0 && (
                                <div className="transcript">
                                    {transcript.map((w, i) => (<span key={i}>{w}{i < transcript.length - 1 ? " " : ""}</span>))}
                                </div>
                            )}
                        </div>

                        <div className="glass-card engine-panel">
                            <div className="engine-header">
                                <div className="engine-title">
                                    <span className="engine-badge e2">Engine 2</span>
                                    Speech / Text → Sign
                                </div>
                                <button
                                    className={`btn ${isListening ? "btn-danger" : "btn-secondary"}`}
                                    onClick={isListening ? stopSpeechRecognition : startSpeechRecognition}
                                >
                                    {isListening ? "⏹ Stop Mic" : "🎤 Speak"}
                                </button>
                            </div>
                            {avatarFrames.length > 0 ? (
                                <SignAvatar frames={avatarFrames} playing={avatarPlaying} label={avatarLabel} />
                            ) : (
                                <div style={{ height: 200, display: "flex", alignItems: "center", justifyContent: "center", color: "var(--sv-text-secondary)" }}>
                                    Signs will appear here
                                </div>
                            )}
                            {isListening && (
                                <div className="speech-area">
                                    <div className={`speech-text ${isListening ? "listening" : ""}`}>
                                        {speechText || "🎤 Listening… speak now"}
                                    </div>
                                </div>
                            )}
                            <div className="text-input-group">
                                <input type="text" className="text-input" placeholder="Type a word to see its sign…"
                                    value={textInput} onChange={(e) => setTextInput(e.target.value)}
                                    onKeyDown={(e) => e.key === "Enter" && handleTextSubmit()} />
                                <button className="btn btn-primary" onClick={handleTextSubmit}>▶ Play</button>
                            </div>
                            <div className="word-chips">
                                {VOCABULARY[language].phrases.slice(0, 12).map((w) => (
                                    <button key={w} className={`word-chip ${avatarLabel === w ? "active" : ""}`} onClick={() => handlePlaySign(w)}>
                                        {w}
                                    </button>
                                ))}
                            </div>
                        </div>
                    </div>
                )}

                {/* ═════════════════════ EMERGENCY MODE ═════════════════════ */}
                {mode === "emergency" && (
                    <div>
                        <div className="emergency-grid">
                            {EMERGENCY_ITEMS.map((item) => (
                                <button key={item.phrase} className="emergency-btn" onClick={() => handleEmergency(item.phrase)}>
                                    <span className="em-icon">{item.icon}</span>
                                    <span className="em-text">{item.text}</span>
                                    <span className="em-sub">{item.sub}</span>
                                </button>
                            ))}
                        </div>
                        <div className="main-grid" style={{ marginTop: 24 }}>
                            <div className="glass-card engine-panel">
                                <div className="engine-title" style={{ marginBottom: 16 }}>
                                    <span className="engine-badge e2">Sign Output</span>
                                    Selected Emergency Sign
                                </div>
                                {avatarFrames.length > 0 ? (
                                    <SignAvatar frames={avatarFrames} playing={avatarPlaying} label={avatarLabel} />
                                ) : (
                                    <div style={{ height: 200, display: "flex", alignItems: "center", justifyContent: "center", color: "var(--sv-text-secondary)" }}>
                                        Select an emergency sign above
                                    </div>
                                )}
                            </div>
                            <div className="glass-card engine-panel">
                                <div className="engine-title" style={{ marginBottom: 16 }}>
                                    <span className="engine-badge e1">Camera</span>
                                    Your Sign Recognition
                                </div>
                                <button className={`btn ${cameraActive ? "btn-danger" : "btn-primary"}`} onClick={handleToggleCamera} style={{ marginBottom: 12 }}>
                                    {cameraActive ? "⏹ Stop" : "📷 Start Camera"}
                                </button>
                                <CameraStream onLandmarks={handleLandmarks} active={cameraActive} />
                                <div className="prediction-box">
                                    <div className="prediction-word" style={{ fontSize: "1.2rem" }}>
                                        {lastPrediction?.word && lastPrediction.word !== "unknown" ? lastPrediction.word : "—"}
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                )}

                {/* ═════════════════════ LEARNING MODE ═════════════════════ */}
                {mode === "learning" && (
                    <>
                        <div className="learning-stats">
                            <div className="stat-card">
                                <div className="stat-value">{score}</div>
                                <div className="stat-label">Score</div>
                            </div>
                            <div className="stat-card">
                                <div className="stat-value">🔥 {streak}</div>
                                <div className="stat-label">Streak</div>
                            </div>
                            <div className="stat-card">
                                <div className="stat-value">Lv.{level}</div>
                                <div className="stat-label">Level</div>
                            </div>
                            <div className="stat-card" style={{ flex: 2 }}>
                                <div className="stat-label" style={{ marginBottom: 4 }}>Progress to Level {level + 1}</div>
                                <div className="level-bar">
                                    <div className="level-fill" style={{ width: `${(score % 100)}%` }} />
                                </div>
                            </div>
                        </div>

                        <div className="category-tabs">
                            {([
                                { key: "phrases", label: "💬 Phrases" },
                                { key: "numbers", label: "🔢 Numbers" },
                                { key: "alphabet", label: "🔤 Alphabet" },
                                { key: "emergency", label: "🚨 Emergency" },
                            ] as { key: LearnCategory; label: string }[]).map((c) => (
                                <button key={c.key} className={`cat-tab ${learnCategory === c.key ? "active" : ""}`}
                                    onClick={() => { setLearnCategory(c.key); setTargetWord(""); setAccuracy(null); }}>
                                    {c.label}
                                </button>
                            ))}
                        </div>

                        <div className="main-grid">
                            <div className="glass-card engine-panel">
                                <div className="engine-header">
                                    <div className="engine-title">
                                        <span className="engine-badge e2">Target</span>
                                        Watch &amp; Learn
                                    </div>
                                    <button className="btn btn-primary" onClick={pickRandomWord}>🔀 New Sign</button>
                                </div>
                                {targetWord ? (
                                    <>
                                        <SignAvatar frames={avatarFrames} playing={avatarPlaying} loop label={targetWord} />
                                        <div className="prediction-box" style={{ marginTop: 14 }}>
                                            <div className="prediction-word" style={{ fontSize: "1.4rem" }}>
                                                &ldquo;{targetWord}&rdquo;
                                            </div>
                                            <p style={{ color: "var(--sv-text-secondary)", fontSize: "0.82rem", marginTop: 6 }}>
                                                Watch the avatar, then replicate in front of your camera.
                                            </p>
                                        </div>
                                    </>
                                ) : (
                                    <div className="prediction-box" style={{ minHeight: 280, display: "flex", alignItems: "center", justifyContent: "center" }}>
                                        <p style={{ color: "var(--sv-text-muted)" }}>Click &ldquo;New Sign&rdquo; to start!</p>
                                    </div>
                                )}
                                <div className="word-chips" style={{ marginTop: 12 }}>
                                    {allWords.slice(0, 14).map((w) => (
                                        <button key={w} className={`word-chip ${targetWord === w ? "active" : ""}`}
                                            onClick={() => { setTargetWord(w); setAccuracy(null); handlePlaySign(w); }}>
                                            {w}
                                        </button>
                                    ))}
                                </div>
                            </div>

                            <div className="glass-card engine-panel">
                                <div className="engine-header">
                                    <div className="engine-title">
                                        <span className="engine-badge e1">Your Turn</span>
                                        Practice
                                    </div>
                                    <button className={`btn ${cameraActive ? "btn-danger" : "btn-primary"}`} onClick={handleToggleCamera}>
                                        {cameraActive ? "⏹ Stop" : "📷 Camera"}
                                    </button>
                                </div>
                                <CameraStream onLandmarks={handleLandmarks} active={cameraActive} />
                                {accuracy !== null && (
                                    <div className="prediction-box accuracy-display">
                                        <div className="accuracy-ring">
                                            <svg width="90" height="90" viewBox="0 0 100 100">
                                                <circle cx="50" cy="50" r="42" fill="none" stroke="rgba(255,255,255,0.04)" strokeWidth="7" />
                                                <circle cx="50" cy="50" r="42" fill="none"
                                                    stroke={accuracy > 70 ? "#00e676" : accuracy > 40 ? "#ffab40" : "#ff4081"}
                                                    strokeWidth="7" strokeLinecap="round"
                                                    strokeDasharray={`${(accuracy / 100) * 264} 264`} />
                                            </svg>
                                            <div className="value">{accuracy}%</div>
                                        </div>
                                        <div className="accuracy-label">
                                            {accuracy > 70 ? "🎉 Excellent!" : accuracy > 40 ? "👍 Getting there!" : "💪 Keep trying!"}
                                        </div>
                                    </div>
                                )}
                                <div className="prediction-box">
                                    <div className="prediction-word" style={{ fontSize: "1.2rem" }}>
                                        {lastPrediction?.word && lastPrediction.word !== "unknown"
                                            ? `Detected: "${lastPrediction.word}"`
                                            : cameraActive ? "Show your sign…" : "Start camera to practice"}
                                    </div>
                                </div>
                            </div>
                        </div>
                    </>
                )}

                {/* ═════════════════════ WORKPLACE MODE ═════════════════════ */}
                {mode === "workplace" && (
                    <div className="main-grid">
                        <div className="glass-card engine-panel">
                            <div className="engine-header">
                                <div className="engine-title">
                                    <span className="engine-badge e1">Live Captioning</span>
                                    Meeting Transcript
                                </div>
                                <button className={`btn ${isListening ? "btn-danger" : "btn-primary"}`}
                                    onClick={isListening ? stopSpeechRecognition : startSpeechRecognition}>
                                    {isListening ? "⏹ Stop" : "🎤 Start Captioning"}
                                </button>
                            </div>
                            {isListening && (
                                <div className="speech-area">
                                    <div className="speech-text listening">{speechText || "🎤 Listening to meeting…"}</div>
                                </div>
                            )}
                            <div className="transcript" style={{ maxHeight: 300, minHeight: 200 }}>
                                {meetingTranscript.length > 0
                                    ? meetingTranscript.map((w, i) => <span key={i}>{w}{" "}</span>)
                                    : <p style={{ color: "var(--sv-text-muted)" }}>Start captioning to see the meeting transcript here.</p>
                                }
                            </div>
                            <button className="btn btn-secondary" style={{ marginTop: 12 }}
                                onClick={() => { if (navigator.clipboard) navigator.clipboard.writeText(meetingTranscript.join(" ")); }}>
                                📋 Copy Transcript
                            </button>
                        </div>
                        <div className="glass-card engine-panel">
                            <div className="engine-title" style={{ marginBottom: 16 }}>
                                <span className="engine-badge e2">Sign Avatar</span>
                                Visual Translation
                            </div>
                            {avatarFrames.length > 0 ? (
                                <SignAvatar frames={avatarFrames} playing={avatarPlaying} label={avatarLabel} />
                            ) : (
                                <div style={{ height: 200, display: "flex", alignItems: "center", justifyContent: "center", color: "var(--sv-text-secondary)" }}>
                                    Type a word or speak to see its sign
                                </div>
                            )}
                            <div className="prediction-box">
                                <div className="prediction-word" style={{ fontSize: "1.2rem" }}>
                                    {avatarLabel || "Signs will appear as you speak"}
                                </div>
                            </div>
                        </div>
                    </div>
                )}

                {/* ═════════════════════ EXPRESSION MODE ═════════════════════ */}
                {mode === "expression" && (
                    <div className="main-grid">
                        <div className="glass-card engine-panel">
                            <div className="engine-header">
                                <div className="engine-title">
                                    <span className="engine-badge e1">Record</span>
                                    Sign Your Message
                                </div>
                                <button className={`btn ${isRecording ? "btn-danger" : "btn-primary"}`} onClick={toggleRecording}>
                                    {isRecording ? "⏹ Stop Recording" : "🔴 Record"}
                                </button>
                            </div>
                            <CameraStream onLandmarks={handleLandmarks} active={cameraActive} />
                            {isRecording && (
                                <div className="prediction-box" style={{ borderColor: "rgba(255, 23, 68, 0.3)" }}>
                                    <div className="prediction-word" style={{ color: "var(--sv-accent-red)", fontSize: "1rem" }}>
                                        🔴 Recording… {recordedWords.length} words captured
                                    </div>
                                </div>
                            )}
                            <div className="prediction-box">
                                <div className="prediction-word" style={{ fontSize: "1.1rem" }}>
                                    {lastPrediction?.word && lastPrediction.word !== "unknown"
                                        ? lastPrediction.word
                                        : "Start recording to capture your message"}
                                </div>
                            </div>
                        </div>
                        <div className="glass-card engine-panel">
                            <div className="engine-title" style={{ marginBottom: 16 }}>
                                <span className="engine-badge e2">Message</span>
                                Your Recorded Message
                            </div>
                            <div className="transcript" style={{ minHeight: 120, fontSize: "1.1rem", lineHeight: 2 }}>
                                {recordedWords.length > 0
                                    ? recordedWords.map((w, i) => <span key={i}>{w}{" "}</span>)
                                    : <p style={{ color: "var(--sv-text-muted)" }}>Your recorded words will appear here.</p>
                                }
                            </div>
                            <div style={{ display: "flex", gap: 8, marginTop: 16 }}>
                                <button className="btn btn-primary" onClick={shareExpression}
                                    disabled={recordedWords.length === 0} style={{ flex: 1 }}>
                                    🔊 Speak &amp; Share
                                </button>
                                <button className="btn btn-secondary" onClick={() => setRecordedWords([])} style={{ flex: 1 }}>
                                    🗑 Clear
                                </button>
                            </div>
                        </div>
                    </div>
                )}

                <footer className="footer">
                    <Image src="/logo.png" alt="SilentVoice" width={20} height={20}
                        style={{ borderRadius: 3, verticalAlign: "middle", marginRight: 6, display: "inline-block" }} />
                    © 2026 SilentVoice · Licensed to Dharaanishan · All Rights Reserved
                    <br />
                    ASL · ISL · TSL · A Communication Rights Platform
                </footer>
            </div>
        </>
    );
}
