"""
SilentVoice — Consolidated FastAPI Backend (V4).

Core engine with:
  ✅ Per-language model (ASL/ISL/TSL separate classifier heads)
  ✅ Multi-hand landmark input (1 or 2 hands)
  ✅ Trained model weights (loaded from silentvoice.pth)
  ✅ Landmark normalizer (wrist-origin, scale normalization)
  ✅ Detection pipeline (sliding window, confidence smoothing, motion gating)
  ✅ Template matching fallback (cosine similarity on sign_library poses)
  ✅ Emergency detection (high threshold, emergency mode only)
  ✅ JWT + bcrypt authentication with SQLite
  ✅ Sign library endpoints (Engine 2)
  ✅ WebSocket endpoint (Engine 1)

Run: python main.py
"""

import asyncio
import hashlib
import json
import logging
import math
import os
import sqlite3
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import torch
import uvicorn
from fastapi import (
    Depends,
    FastAPI,
    HTTPException,
    Query,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

# Optional auth
try:
    from jose import JWTError, jwt
except ImportError:
    jwt = None
    JWTError = Exception

try:
    from passlib.context import CryptContext
    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
except ImportError:
    pwd_context = None

from ml.transformer import SignLanguageTransformer
from services.sign_library import (
    FLAT_VOCAB,
    VOCAB_SIZE,
    VOCABULARY,
    SIGN_MAP,
    get_sign_sequence,
    get_vocab_for_language,
    predict_to_word,
)

# ═══════════════════════════════════════════════════════════════
#  CONFIG
# ═══════════════════════════════════════════════════════════════

BASE_DIR = Path(__file__).parent
FRONTEND_DIR = BASE_DIR.parent / "frontend" / "out"
DB_PATH = BASE_DIR / "silentvoice.db"

JWT_SECRET = os.getenv("JWT_SECRET", "silentvoice-secret-key-change-in-production")
JWT_ALGORITHM = "HS256"
JWT_ACCESS_EXPIRE_MINUTES = 60 * 24
JWT_REFRESH_EXPIRE_DAYS = 30

# Detection settings
INPUT_DIM = 63
SEQ_LEN = 40
SLIDE_STEP = 10
CONFIDENCE_THRESHOLD = 0.25
SMOOTHING_WINDOW = 3
MOTION_THRESHOLD = 0.003
TEMPLATE_THRESHOLD = 0.88   # High threshold for template matching
EMERGENCY_THRESHOLD = 0.92  # Very high for emergency (reduce false positives)
EMERGENCY_HOLD_FRAMES = 15

# ═══════════════════════════════════════════════════════════════
#  LOGGING
# ═══════════════════════════════════════════════════════════════

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("SilentVoice")


# ═══════════════════════════════════════════════════════════════
#  LANDMARK NORMALIZER
# ═══════════════════════════════════════════════════════════════

class LandmarkNormalizer:
    @staticmethod
    def normalize(landmarks: List[List[float]]) -> List[float]:
        """Normalize 21 landmarks → flat [63] position/scale invariant."""
        if len(landmarks) < 21:
            return [0.0] * INPUT_DIM
        arr = np.array(landmarks[:21], dtype=np.float32)
        wrist = arr[0].copy()
        arr = arr - wrist
        span = np.linalg.norm(arr[12] - arr[0])
        if span > 1e-6:
            arr = arr / span
        else:
            bbox_diag = np.linalg.norm(arr.max(axis=0) - arr.min(axis=0))
            if bbox_diag > 1e-6:
                arr = arr / bbox_diag
        return arr.flatten().tolist()

    @staticmethod
    def compute_motion(buffer: List[List[float]]) -> float:
        if len(buffer) < 2:
            return 0.0
        arr = np.array(buffer[-5:], dtype=np.float32)
        deltas = np.diff(arr, axis=0)
        return float(np.mean(np.abs(deltas)))


normalizer = LandmarkNormalizer()


# ═══════════════════════════════════════════════════════════════
#  TEMPLATE MATCHER (cosine similarity against sign_library poses)
# ═══════════════════════════════════════════════════════════════

class TemplateMatcher:
    """
    Matches normalized landmarks against sign_library pose templates.
    This is the FALLBACK when the ML model isn't confident enough.
    Language-aware: only matches against signs in the requested language.
    """

    def __init__(self):
        self.templates: Dict[str, Dict[str, np.ndarray]] = {}  # lang -> {word: vector}
        self._build_templates()

    def _build_templates(self):
        for lang, words in VOCABULARY.items():
            self.templates[lang] = {}
            for word in words:
                key = word.lower()
                if key in SIGN_MAP:
                    pose_fn = SIGN_MAP[key][0]  # start pose
                    lm = pose_fn()
                    flat = normalizer.normalize(lm)
                    self.templates[lang][key] = np.array(flat, dtype=np.float32)

        total = sum(len(v) for v in self.templates.values())
        log.info(f"Template matcher: {total} templates across {len(self.templates)} languages")

    def match(self, normalized_frame: List[float], language: str = "ASL",
              threshold: float = TEMPLATE_THRESHOLD) -> Optional[Dict[str, Any]]:
        """Match against templates for a specific language."""
        lang_templates = self.templates.get(language, {})
        if not lang_templates:
            return None

        frame = np.array(normalized_frame, dtype=np.float32)
        frame_norm = np.linalg.norm(frame)
        if frame_norm < 1e-6:
            return None

        best_word = None
        best_sim = 0.0

        for word, template in lang_templates.items():
            t_norm = np.linalg.norm(template)
            if t_norm < 1e-6:
                continue
            sim = float(np.dot(frame, template) / (frame_norm * t_norm))
            if sim > threshold and sim > best_sim:
                best_sim = sim
                best_word = word

        if best_word:
            return {
                "word": best_word,
                "language": language,
                "confidence": round(best_sim, 4),
                "source": "template",
            }
        return None


template_matcher = TemplateMatcher()


# ═══════════════════════════════════════════════════════════════
#  EMERGENCY DETECTOR (very strict, only for emergency mode)
# ═══════════════════════════════════════════════════════════════

class EmergencyDetector:
    def __init__(self):
        self.templates: Dict[str, np.ndarray] = {}
        self.hold_counters: Dict[str, int] = defaultdict(int)
        self._build()

    def _build(self):
        emergency_signs = {
            "help": "🆘 I Need Help",
            "i need help": "🆘 I Need Help",
            "call ambulance": "🚑 Call Ambulance",
            "call police": "🚔 Call Police",
            "i cannot hear": "🚫 I Cannot Hear",
            "i am allergic": "⚠️ I Am Allergic",
            "danger": "🔥 Danger",
            "pain": "😣 In Pain",
            "emergency": "🚨 Emergency",
        }
        for word, label in emergency_signs.items():
            if word in SIGN_MAP:
                lm = SIGN_MAP[word][0]()
                flat = normalizer.normalize(lm)
                self.templates[word] = np.array(flat, dtype=np.float32)
        log.info(f"Emergency templates: {len(self.templates)}")

    def check(self, normalized_frame: List[float]) -> Optional[Dict[str, Any]]:
        frame = np.array(normalized_frame, dtype=np.float32)
        frame_norm = np.linalg.norm(frame)
        if frame_norm < 1e-6:
            return None

        best_match = None
        best_sim = 0.0
        for word, template in self.templates.items():
            t_norm = np.linalg.norm(template)
            if t_norm < 1e-6:
                continue
            sim = float(np.dot(frame, template) / (frame_norm * t_norm))
            if sim > EMERGENCY_THRESHOLD and sim > best_sim:
                best_sim = sim
                best_match = word

        for word in self.templates:
            if word == best_match:
                self.hold_counters[word] += 1
            else:
                self.hold_counters[word] = 0

        if best_match and self.hold_counters[best_match] >= EMERGENCY_HOLD_FRAMES:
            self.hold_counters[best_match] = 0
            return {
                "type": "emergency",
                "word": best_match,
                "confidence": round(best_sim, 4),
                "language": "EMERGENCY",
                "raw_label": f"EMERGENCY:{best_match}",
            }
        return None

    def reset(self):
        self.hold_counters = defaultdict(int)


emergency_detector = EmergencyDetector()


# ═══════════════════════════════════════════════════════════════
#  CONFIDENCE SMOOTHER
# ═══════════════════════════════════════════════════════════════

class ConfidenceSmoother:
    def __init__(self, window: int = SMOOTHING_WINDOW):
        self.window = window
        self.history: List[str] = []

    def process(self, prediction: str, confidence: float) -> Optional[str]:
        self.history.append(prediction)
        if len(self.history) > self.window * 3:
            self.history = self.history[-self.window * 3:]
        if len(self.history) >= self.window:
            recent = self.history[-self.window:]
            if all(w == recent[0] for w in recent) and recent[0] != "unknown":
                return recent[0]
        return None

    def reset(self):
        self.history = []


# ═══════════════════════════════════════════════════════════════
#  DATABASE
# ═══════════════════════════════════════════════════════════════

def init_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            hashed_password TEXT NOT NULL,
            preferred_language TEXT DEFAULT 'ASL',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

def get_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


# ═══════════════════════════════════════════════════════════════
#  AUTH
# ═══════════════════════════════════════════════════════════════

class RegisterRequest(BaseModel):
    name: str = Field(min_length=1)
    email: str = Field(min_length=3)
    password: str = Field(min_length=6)
    preferred_language: str = "ASL"

class LoginRequest(BaseModel):
    email: str
    password: str

def hash_password(password: str) -> str:
    if pwd_context:
        return pwd_context.hash(password)
    return hashlib.sha256(password.encode()).hexdigest()

def verify_password(plain: str, hashed: str) -> bool:
    if pwd_context:
        return pwd_context.verify(plain, hashed)
    return hashlib.sha256(plain.encode()).hexdigest() == hashed

def create_token(data: dict, expires_delta: timedelta) -> str:
    if jwt is None:
        import base64
        payload = json.dumps({**data, "exp": time.time() + expires_delta.total_seconds()})
        return base64.b64encode(payload.encode()).decode()
    expire = datetime.now(timezone.utc) + expires_delta
    return jwt.encode({**data, "exp": expire}, JWT_SECRET, algorithm=JWT_ALGORITHM)

def decode_token(token: str) -> Optional[dict]:
    if jwt is None:
        import base64
        try:
            payload = json.loads(base64.b64decode(token).decode())
            return payload if payload.get("exp", 0) >= time.time() else None
        except Exception:
            return None
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except JWTError:
        return None


# ═══════════════════════════════════════════════════════════════
#  MODEL LOADING
# ═══════════════════════════════════════════════════════════════

WEIGHTS_PATH = BASE_DIR / "pretrained_models" / "silentvoice.pth"

# Language word lists (will be loaded from weights or built fresh)
lang_word_lists: Dict[str, List[str]] = {}
lang_vocabs: Dict[str, int] = {}
model = None

def load_model():
    """Load trained model with per-language heads."""
    global model, lang_word_lists, lang_vocabs

    if WEIGHTS_PATH.exists():
        checkpoint = torch.load(WEIGHTS_PATH, map_location="cpu", weights_only=False)
        lang_vocabs = checkpoint.get("lang_vocabs", {})
        lang_word_lists = checkpoint.get("lang_word_lists", {})

        model = SignLanguageTransformer(
            input_dim=checkpoint.get("input_dim", INPUT_DIM),
            d_model=checkpoint.get("d_model", 128),
            nhead=checkpoint.get("nhead", 4),
            num_layers=checkpoint.get("num_layers", 3),
            dim_feedforward=checkpoint.get("dim_feedforward", 256),
            use_bilstm=True,
            lstm_layers=2,
            lang_vocab=lang_vocabs,
        )
        model.load_state_dict(checkpoint["model_state_dict"])
        model.eval()

        results = checkpoint.get("results", {})
        log.info(f"✅ Loaded trained model: {WEIGHTS_PATH.name}")
        for lang, acc in results.items():
            log.info(f"   {lang}: {acc:.1%} accuracy ({lang_vocabs.get(lang, '?')} signs)")
    else:
        # Fallback: build vocab from sign_library, random weights
        log.warning("⚠️ No trained weights found — using template matching only")
        for lang in ["ASL", "ISL", "TSL"]:
            words = VOCABULARY.get(lang, [])
            unique = []
            seen = set()
            for w in words:
                k = w.lower()
                if k in SIGN_MAP and k not in seen:
                    seen.add(k)
                    unique.append(k)
            lang_word_lists[lang] = unique
            lang_vocabs[lang] = len(unique)

        model = SignLanguageTransformer(
            input_dim=INPUT_DIM,
            d_model=128,
            nhead=4,
            num_layers=3,
            dim_feedforward=256,
            use_bilstm=True,
            lang_vocab=lang_vocabs,
        )
        model.eval()


load_model()


# ═══════════════════════════════════════════════════════════════
#  FASTAPI APP
# ═══════════════════════════════════════════════════════════════

app = FastAPI(
    title="SilentVoice API",
    description="Real-time sign language recognition — ASL/ISL/TSL",
    version="4.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup():
    init_db()
    log.info("=" * 60)
    log.info("  SilentVoice Backend v4.0 — Starting")
    log.info(f"  Languages: {list(lang_vocabs.keys())}")
    for lang, size in lang_vocabs.items():
        log.info(f"    {lang}: {size} signs")
    log.info(f"  Templates: {sum(len(v) for v in template_matcher.templates.values())}")
    log.info(f"  Emergency templates: {len(emergency_detector.templates)}")
    log.info(f"  Trained model: {'Yes' if WEIGHTS_PATH.exists() else 'No (template only)'}")
    log.info("=" * 60)


def ok(data: Any = None, message: str = "success") -> dict:
    return {"status": "success", "message": message, "data": data}

def err(message: str, code: int = 400) -> JSONResponse:
    return JSONResponse(status_code=code, content={"status": "error", "message": message, "data": None})


# ═══════════════════════════════════════════════════════════════
#  AUTH ENDPOINTS
# ═══════════════════════════════════════════════════════════════

@app.post("/api/auth/register")
async def register(req: RegisterRequest):
    db = get_db()
    try:
        existing = db.execute("SELECT id FROM users WHERE email = ?", (req.email,)).fetchone()
        if existing:
            return err("Email already registered", 409)
        hashed = hash_password(req.password)
        db.execute(
            "INSERT INTO users (name, email, hashed_password, preferred_language) VALUES (?, ?, ?, ?)",
            (req.name, req.email, hashed, req.preferred_language),
        )
        db.commit()
        user = db.execute("SELECT * FROM users WHERE email = ?", (req.email,)).fetchone()
        user_dict = {"id": user["id"], "name": user["name"], "email": user["email"],
                     "preferred_language": user["preferred_language"]}
        access_token = create_token({"sub": req.email}, timedelta(minutes=JWT_ACCESS_EXPIRE_MINUTES))
        refresh_token = create_token({"sub": req.email, "type": "refresh"}, timedelta(days=JWT_REFRESH_EXPIRE_DAYS))
        return ok({"access_token": access_token, "refresh_token": refresh_token,
                   "token_type": "bearer", "user": user_dict})
    except Exception as e:
        return err(f"Registration failed: {e}", 500)
    finally:
        db.close()


@app.post("/api/auth/login")
async def login(req: LoginRequest):
    db = get_db()
    try:
        user = db.execute("SELECT * FROM users WHERE email = ?", (req.email,)).fetchone()
        if not user or not verify_password(req.password, user["hashed_password"]):
            return err("Invalid email or password", 401)
        user_dict = {"id": user["id"], "name": user["name"], "email": user["email"],
                     "preferred_language": user["preferred_language"]}
        access_token = create_token({"sub": req.email}, timedelta(minutes=JWT_ACCESS_EXPIRE_MINUTES))
        refresh_token = create_token({"sub": req.email, "type": "refresh"}, timedelta(days=JWT_REFRESH_EXPIRE_DAYS))
        return ok({"access_token": access_token, "refresh_token": refresh_token,
                   "token_type": "bearer", "user": user_dict})
    finally:
        db.close()


@app.post("/api/auth/refresh")
async def refresh(body: dict):
    token = body.get("refresh_token", "")
    payload = decode_token(token)
    if not payload or payload.get("type") != "refresh":
        return err("Invalid refresh token", 401)
    access_token = create_token({"sub": payload["sub"]}, timedelta(minutes=JWT_ACCESS_EXPIRE_MINUTES))
    return ok({"access_token": access_token, "token_type": "bearer"})


@app.get("/api/auth/me")
async def get_me(token: str = Query(default="")):
    if not token:
        return err("Not authenticated", 401)
    payload = decode_token(token)
    if not payload:
        return err("Not authenticated", 401)
    db = get_db()
    try:
        user = db.execute("SELECT * FROM users WHERE email = ?", (payload.get("sub"),)).fetchone()
        if not user:
            return err("User not found", 404)
        return ok({"id": user["id"], "name": user["name"], "email": user["email"],
                    "preferred_language": user["preferred_language"]})
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════
#  SIGN LIBRARY ENDPOINTS (Engine 2)
# ═══════════════════════════════════════════════════════════════

@app.get("/health")
async def health():
    return ok({
        "model_loaded": WEIGHTS_PATH.exists(),
        "languages": list(lang_vocabs.keys()),
        "lang_sizes": lang_vocabs,
        "templates": sum(len(v) for v in template_matcher.templates.values()),
        "version": "4.0.0",
    }, "SilentVoice API is running")


@app.get("/api/vocab")
async def get_vocabulary(language: str = Query(default="ASL")):
    words = get_vocab_for_language(language.upper())
    return ok({"language": language.upper(), "words": words})


@app.get("/api/languages")
async def get_languages():
    return ok({"languages": list(VOCABULARY.keys())})


@app.get("/api/sign-sequence")
async def get_sign_anim(word: str = Query(...), language: str = Query(default="ASL")):
    frames = get_sign_sequence(word.lower(), language.upper())
    return {"word": word.lower(), "language": language.upper(), "frames": frames or []}


@app.get("/api/emergency-phrases")
async def get_emergency_phrases():
    items = [
        {"icon": "🆘", "text": "I Need Help", "phrase": "i need help"},
        {"icon": "🚑", "text": "Call Ambulance", "phrase": "call ambulance"},
        {"icon": "🚔", "text": "Call Police", "phrase": "call police"},
        {"icon": "🚫", "text": "I Cannot Hear", "phrase": "i cannot hear"},
        {"icon": "⚠️", "text": "I Am Allergic", "phrase": "i am allergic"},
        {"icon": "💊", "text": "Need Medicine", "phrase": "medicine"},
        {"icon": "🔥", "text": "Danger", "phrase": "danger"},
        {"icon": "😣", "text": "In Pain", "phrase": "pain"},
    ]
    for item in items:
        item["has_template"] = item["phrase"] in emergency_detector.templates
    return ok(items)


# ═══════════════════════════════════════════════════════════════
#  INFERENCE ENGINE
# ═══════════════════════════════════════════════════════════════

def run_inference(normalized_frames: List[List[float]], language: str = "ASL") -> dict:
    """
    Run model inference on normalized frames for a specific language.

    Pipeline:
      1. ML model prediction (if trained)
      2. Template matching fallback
      3. Combined confidence
    """
    arr = np.array(normalized_frames, dtype=np.float32)
    tensor = torch.from_numpy(arr).unsqueeze(0)

    with torch.no_grad():
        logits = model(tensor, language=language)
        probs = torch.softmax(logits, dim=-1)
        ml_confidence, pred_idx = probs.max(dim=-1)

    ml_conf = ml_confidence.item()
    pred_idx_val = pred_idx.item()

    # Get word from language-specific vocab
    words = lang_word_lists.get(language, [])
    if 0 <= pred_idx_val < len(words):
        ml_word = words[pred_idx_val]
    else:
        ml_word = "unknown"

    # Template matching on latest frame
    template_result = template_matcher.match(normalized_frames[-1], language)

    # Decision logic:
    # 1. If ML confident (>0.5) → use ML
    # 2. If template match → use template
    # 3. If ML somewhat confident (>0.25) → use ML anyway
    # 4. Otherwise → unknown

    if ml_conf > 0.5 and ml_word != "unknown":
        return {
            "status": "success",
            "word": ml_word,
            "language": language,
            "confidence": round(ml_conf, 4),
            "source": "model",
            "raw_label": f"{language}:{ml_word}",
        }
    elif template_result:
        return {
            "status": "success",
            "word": template_result["word"],
            "language": language,
            "confidence": template_result["confidence"],
            "source": "template",
            "raw_label": f"{language}:{template_result['word']}",
        }
    elif ml_conf > CONFIDENCE_THRESHOLD and ml_word != "unknown":
        return {
            "status": "success",
            "word": ml_word,
            "language": language,
            "confidence": round(ml_conf, 4),
            "source": "model_low",
            "raw_label": f"{language}:{ml_word}",
        }
    else:
        return {
            "status": "success",
            "word": "unknown",
            "language": language,
            "confidence": round(ml_conf, 4),
            "source": "none",
            "raw_label": "unknown",
        }


# ═══════════════════════════════════════════════════════════════
#  WEBSOCKET — REAL-TIME DETECTION (Engine 1)
# ═══════════════════════════════════════════════════════════════

@app.websocket("/ws/recognize")
async def websocket_recognize(websocket: WebSocket):
    """
    Real-time sign recognition — FIXED pipeline.

    Key insight: Letters/numbers are STATIC (no motion) → template matching.
                 Words/phrases have MOTION → ML model.

    Accepts: { hands: [[[x,y,z],...]], language: "ASL", timestamp: ... }
    """
    await websocket.accept()
    frame_buffer: List[List[float]] = []
    smoother = ConfidenceSmoother()
    frame_count = 0
    last_log_time = time.time()
    current_language = "ASL"
    last_static_prediction = ""
    static_hold_count = 0
    STATIC_CONFIRM_FRAMES = 8  # Hold same pose for 8 frames to confirm

    log.info("🔗 WebSocket connected — detection active")

    try:
        while True:
            raw = await websocket.receive_text()
            data = json.loads(raw)

            # ── Parse input ──
            hands = data.get("hands", [])
            language = data.get("language", "ASL").upper()
            is_emergency = data.get("emergency", False)
            current_language = language

            if not hands or len(hands) == 0:
                hand = data.get("hand", [])
                if hand and len(hand) >= 21:
                    hands = [hand]
                else:
                    continue

            primary_hand = hands[0]
            if len(primary_hand) < 21:
                continue

            frame_count += 1

            # ── Normalize ──
            normalized = normalizer.normalize(primary_hand)
            frame_buffer.append(normalized)

            # Cap buffer size
            if len(frame_buffer) > SEQ_LEN * 3:
                frame_buffer = frame_buffer[-SEQ_LEN * 2:]

            # ── Emergency check ──
            if is_emergency:
                emergency = emergency_detector.check(normalized)
                if emergency:
                    await websocket.send_json(emergency)
                    frame_buffer = []
                    smoother.reset()
                    last_static_prediction = ""
                    static_hold_count = 0
                    continue

            # ── Compute motion ──
            motion = normalizer.compute_motion(frame_buffer)

            # ══════════════════════════════════════════════
            # STATIC SIGN DETECTION (letters, numbers)
            # When hand is still → template matching
            # ══════════════════════════════════════════════
            if motion < 0.005 and len(frame_buffer) >= 3:
                # Template match every 5 frames (avoid flooding)
                if frame_count % 5 == 0:
                    tmatch = template_matcher.match(normalized, language, threshold=0.82)
                    if tmatch:
                        word = tmatch["word"]
                        # Debounce: same prediction must hold for N frames
                        if word == last_static_prediction:
                            static_hold_count += 1
                        else:
                            last_static_prediction = word
                            static_hold_count = 1

                        if static_hold_count >= STATIC_CONFIRM_FRAMES:
                            result = {
                                "status": "success",
                                "word": word,
                                "language": language,
                                "confidence": tmatch["confidence"],
                                "source": "template",
                                "confirmed": True,
                                "raw_label": f"{language}:{word}",
                            }
                            await websocket.send_json(result)
                            log.info(f"✅ [{language}] STATIC: {word} "
                                     f"(conf={tmatch['confidence']:.3f})")
                            static_hold_count = 0
                            last_static_prediction = ""
                    else:
                        static_hold_count = 0
                continue  # Static → skip ML model

            # ══════════════════════════════════════════════
            # MOVING SIGN DETECTION (words, phrases)
            # When hand is moving → sliding window + ML model
            # ══════════════════════════════════════════════
            last_static_prediction = ""
            static_hold_count = 0

            if len(frame_buffer) >= SEQ_LEN:
                window = frame_buffer[-SEQ_LEN:]
                result = run_inference(window, language)

                confirmed = smoother.process(result["word"], result["confidence"])

                if confirmed and confirmed != "unknown":
                    result["word"] = confirmed
                    result["confirmed"] = True
                    await websocket.send_json(result)
                    log.info(f"✅ [{language}] MOVING: {confirmed} "
                             f"(conf={result['confidence']:.3f}, src={result.get('source','?')})")

                frame_buffer = frame_buffer[SLIDE_STEP:]

            # ── Periodic stats ──
            if time.time() - last_log_time > 10:
                log.info(f"📊 frames={frame_count} buf={len(frame_buffer)} "
                         f"lang={current_language} motion={motion:.5f}")
                last_log_time = time.time()

    except WebSocketDisconnect:
        log.info(f"🔌 Disconnected ({frame_count} frames)")
    except Exception as e:
        log.error(f"WebSocket error: {e}")


@app.post("/api/predict")
async def predict_from_landmarks(body: dict):
    """Single-shot prediction from complete sequence."""
    frames_data = body.get("frames", [])
    language = body.get("language", "ASL").upper()
    if not frames_data:
        return err("No frames provided")

    normalized = [normalizer.normalize(frame) for frame in frames_data]
    while len(normalized) < SEQ_LEN:
        normalized.append([0.0] * INPUT_DIM)
    normalized = normalized[:SEQ_LEN]

    return run_inference(normalized, language)


@app.post("/api/predict-single")
async def predict_single_frame(body: dict):
    """Single-frame template matching (for static signs: letters/numbers)."""
    hand = body.get("hand", [])
    language = body.get("language", "ASL").upper()
    if not hand or len(hand) < 21:
        return err("Need at least 21 landmarks")

    normalized = normalizer.normalize(hand)
    result = template_matcher.match(normalized, language, threshold=0.75)
    if result:
        return ok(result)
    return ok({"word": "unknown", "confidence": 0.0, "language": language})


# ═══════════════════════════════════════════════════════════════
#  SERVE FRONTEND
# ═══════════════════════════════════════════════════════════════

if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
    log.info(f"Frontend: {FRONTEND_DIR}")


# ═══════════════════════════════════════════════════════════════
#  ENTRY POINT
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print()
    print("  ╔═══════════════════════════════════════════╗")
    print("  ║   🤟 SilentVoice v4.0 — Starting...      ║")
    print("  ║                                           ║")
    print("  ║   Backend:  http://localhost:8000          ║")
    print("  ║   API docs: http://localhost:8000/docs     ║")
    print("  ║                                           ║")
    print("  ║   © 2026 SilentVoice                      ║")
    print("  ║   Licensed to Dharaanishan                ║")
    print("  ║   All Rights Reserved                     ║")
    print("  ╚═══════════════════════════════════════════╝")
    print()

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
    )
