"""
SilentVoice — Sign Library Service (V3).

Complete sign animation library with:
  ✅ 26 unique ASL fingerspelling hand poses (A-Z)
  ✅ 10 number poses with distinct shapes
  ✅ 30+ word/phrase poses per language
  ✅ Emergency poses
  ✅ Case-insensitive lookup
  ✅ Smooth interpolation + motion animation

Each pose is built with anatomically correct finger positions
based on ASL fingerspelling reference charts.
"""

import json
import math
import random
from pathlib import Path
from typing import Any, Dict, List, Optional

DATA_DIR = Path(__file__).parent.parent / "data" / "sign_library"

# ═══════════════════════════════════════════════════════════════
#  VOCABULARY
# ═══════════════════════════════════════════════════════════════

COMMON_NUMBERS = ["0", "1", "2", "3", "4", "5", "6", "7", "8", "9"]
COMMON_ALPHABET = list("abcdefghijklmnopqrstuvwxyz")

EMERGENCY_PHRASES = [
    "help", "call ambulance", "i need help",
    "i cannot hear", "i am allergic", "call police",
    "emergency", "danger", "pain", "medicine",
]

TAMIL_VOWELS = ["அ", "ஆ", "இ", "ஈ", "உ", "ஊ", "எ", "ஏ", "ஐ", "ஒ", "ஓ", "ஔ"]
TAMIL_CONSONANTS = ["க", "ங", "ச", "ஞ", "ட", "ண", "த", "ந", "ப", "ம", "ய", "ர", "ல", "வ", "ழ", "ள", "ற", "ன"]
TAMIL_ALPHABET = TAMIL_VOWELS + TAMIL_CONSONANTS

VOCABULARY: Dict[str, List[str]] = {
    "ASL": [
        "hello", "thank you", "please", "yes", "no",
        "help", "sorry", "love", "friend", "family",
        "eat", "drink", "water", "more", "stop",
        "good", "bad", "happy", "sad", "want",
        "name", "how", "what", "where", "when",
        "come", "go", "finish", "again", "understand",
    ] + COMMON_NUMBERS + COMMON_ALPHABET + EMERGENCY_PHRASES,

    "ISL": [
        "namaste", "dhanyavaad", "kripaya", "haan", "nahi",
        "madad", "maafi", "pyaar", "dost", "parivaar",
        "khana", "peena", "paani", "aur", "ruko",
        "accha", "bura", "khush", "dukhi", "chahiye",
        "naam", "kaise", "kya", "kahan", "kab",
        "aao", "jao", "khatam", "phir_se", "samajh",
    ] + COMMON_NUMBERS + COMMON_ALPHABET + EMERGENCY_PHRASES,

    "TSL": [
        "vanakkam", "nandri", "thayavu_seithu", "aam", "illai",
        "udavi", "mannithu", "anbu", "nanbane", "kudumbam",
        "saapidu", "kudi", "thanni", "innum", "nil",
        "nalla", "ketta", "santhosham", "varutham", "venum",
        "peyar", "eppadi", "enna", "enga", "eppo",
        "vaa", "po", "mudinthathu", "meendum", "puriyuthu",
    ] + COMMON_NUMBERS + TAMIL_ALPHABET + EMERGENCY_PHRASES,
}

# Flat index for model output
FLAT_VOCAB: List[str] = []
FLAT_INDEX: Dict[str, int] = {}
for _lang, _words in VOCABULARY.items():
    for _w in _words:
        key = f"{_lang}:{_w}"
        if key not in FLAT_INDEX:
            FLAT_INDEX[key] = len(FLAT_VOCAB)
            FLAT_VOCAB.append(key)
VOCAB_SIZE = len(FLAT_VOCAB)


# ═══════════════════════════════════════════════════════════════
#  HAND POSE BUILDER
#  MediaPipe: wrist(0), thumb(1-4), index(5-8),
#  middle(9-12), ring(13-16), pinky(17-20)
# ═══════════════════════════════════════════════════════════════

# All poses centered at (0.5, 0.5) with hand spanning ~0.35 of canvas
CX, CY = 0.50, 0.50


def _ext(bx, by, dx, dy, length=1.0):
    """Build 4 joints for an extended finger."""
    return [
        [bx, by, 0],
        [bx + dx * 0.33 * length, by + dy * 0.33 * length, 0],
        [bx + dx * 0.66 * length, by + dy * 0.66 * length, 0],
        [bx + dx * length, by + dy * length, 0],
    ]


def _curl(bx, by, dx=0.01, dy=0.02):
    """Build 4 joints for a curled/closed finger."""
    return [
        [bx, by, 0],
        [bx + dx, by - 0.01, -0.02],
        [bx + dx * 0.3, by + dy, -0.04],
        [bx + dx * 0.1, by + dy * 1.3, -0.03],
    ]


def _bent(bx, by, dx, dy, bend=0.5):
    """Build 4 joints for a partially bent finger (bent at middle)."""
    return [
        [bx, by, 0],
        [bx + dx * 0.4, by + dy * 0.4, 0],
        [bx + dx * 0.5, by + dy * 0.3, -0.03],
        [bx + dx * 0.3, by + dy * 0.15 * bend, -0.04],
    ]


def _make_hand(thumb, index, middle, ring, pinky):
    """
    Assemble 21 landmarks from 5 finger specs.
    Each finger spec: ('ext'|'curl'|'bent'|custom_list, params)
    """
    lm = [[CX, CY + 0.10, 0]]  # wrist at bottom center

    finger_bases = [
        (CX - 0.07, CY + 0.04),   # thumb
        (CX - 0.04, CY - 0.02),   # index
        (CX - 0.01, CY - 0.03),   # middle
        (CX + 0.02, CY - 0.02),   # ring
        (CX + 0.05, CY - 0.01),   # pinky
    ]

    default_dirs = [
        (-0.08, -0.14),  # thumb goes left-up
        (-0.02, -0.22),  # index straight up
        (0.00, -0.24),   # middle straight up
        (0.02, -0.22),   # ring up-right
        (0.05, -0.18),   # pinky right-up
    ]

    specs = [thumb, index, middle, ring, pinky]

    for i, spec in enumerate(specs):
        bx, by = finger_bases[i]
        dx, dy = default_dirs[i]

        if isinstance(spec, list):
            # Custom explicit landmarks
            lm += spec
        elif spec == "ext":
            lm += _ext(bx, by, dx, dy)
        elif spec == "curl":
            lm += _curl(bx, by)
        elif spec == "bent":
            lm += _bent(bx, by, dx, dy)
        elif spec == "ext_side":
            lm += _ext(bx, by, dx * 0.7, dy * 0.3)  # extended sideways
        elif spec == "ext_out":
            lm += _ext(bx, by, abs(dx) * 1.2, -0.05)  # pointing forward/out
        else:
            lm += _curl(bx, by)

    return lm


# ═══════════════════════════════════════════════════════════════
#  ALL 26 ASL FINGERSPELLING POSES (unique per letter!)
# ═══════════════════════════════════════════════════════════════

def _pose_A():
    """A: Fist with thumb beside index finger."""
    return _make_hand(
        _ext(CX - 0.07, CY + 0.04, -0.06, -0.12),  # thumb alongside
        "curl", "curl", "curl", "curl"
    )

def _pose_B():
    """B: Four fingers extended up, thumb tucked across palm."""
    return _make_hand(
        _curl(CX - 0.07, CY + 0.04, 0.02, 0.02),  # thumb across
        "ext", "ext", "ext", "ext"
    )

def _pose_C():
    """C: Curved hand forming C shape."""
    bx, by = CX - 0.07, CY + 0.04
    return _make_hand(
        _ext(bx, by, -0.06, -0.10, 0.8),
        _bent(CX - 0.04, CY - 0.02, -0.04, -0.22),
        _bent(CX - 0.01, CY - 0.03, -0.01, -0.24),
        _bent(CX + 0.02, CY - 0.02, 0.02, -0.22),
        _bent(CX + 0.05, CY - 0.01, 0.04, -0.18)
    )

def _pose_D():
    """D: Index up, middle+ring+pinky curled touching thumb."""
    return _make_hand(
        _curl(CX - 0.07, CY + 0.04, 0.05, 0.04),  # thumb touches middle
        "ext",   # index up
        "curl", "curl", "curl"
    )

def _pose_E():
    """E: All fingertips curled down touching thumb."""
    return _make_hand(
        _curl(CX - 0.07, CY + 0.04, 0.04, 0.03),
        _bent(CX - 0.04, CY - 0.02, -0.02, -0.10, 2.0),
        _bent(CX - 0.01, CY - 0.03, 0.00, -0.12, 2.0),
        _bent(CX + 0.02, CY - 0.02, 0.02, -0.10, 2.0),
        _bent(CX + 0.05, CY - 0.01, 0.04, -0.08, 2.0)
    )

def _pose_F():
    """F: Index+thumb form circle, other fingers extended."""
    return _make_hand(
        _ext(CX - 0.07, CY + 0.04, -0.03, -0.10, 0.7),  # thumb toward index
        [  # index curves to thumb
            [CX - 0.04, CY - 0.02, 0],
            [CX - 0.06, CY - 0.08, 0],
            [CX - 0.08, CY - 0.12, -0.01],
            [CX - 0.09, CY - 0.14, -0.02],
        ],
        "ext", "ext", "ext"  # middle, ring, pinky extended
    )

def _pose_G():
    """G: Index pointing sideways, thumb parallel."""
    return _make_hand(
        _ext(CX - 0.07, CY + 0.04, -0.12, -0.04),  # thumb sideways
        _ext(CX - 0.04, CY - 0.02, -0.18, -0.04),  # index sideways
        "curl", "curl", "curl"
    )

def _pose_H():
    """H: Index + middle pointing sideways together."""
    return _make_hand(
        "curl",
        _ext(CX - 0.04, CY - 0.02, -0.18, -0.03),  # index sideways
        _ext(CX - 0.01, CY - 0.03, -0.17, -0.01),  # middle sideways
        "curl", "curl"
    )

def _pose_I():
    """I: Pinky extended up, rest curled."""
    return _make_hand("curl", "curl", "curl", "curl", "ext")

def _pose_J():
    """J: Like I but with downward arc motion (static pose = pinky up)."""
    return _pose_I()  # Motion handles the J arc

def _pose_K():
    """K: Index + middle spread up like V, thumb between them."""
    return _make_hand(
        _ext(CX - 0.07, CY + 0.04, -0.04, -0.14),  # thumb up between
        _ext(CX - 0.04, CY - 0.02, -0.05, -0.22),   # index up-left
        _ext(CX - 0.01, CY - 0.03, 0.03, -0.24),     # middle up-right
        "curl", "curl"
    )

def _pose_L():
    """L: Thumb out + index up forming L shape."""
    return _make_hand(
        _ext(CX - 0.07, CY + 0.04, -0.14, -0.02),  # thumb horizontal left
        "ext",   # index vertical up
        "curl", "curl", "curl"
    )

def _pose_M():
    """M: Three fingers over thumb (fist-like but thumb under 3 fingers)."""
    return _make_hand(
        _curl(CX - 0.07, CY + 0.04, 0.06, 0.06),  # thumb tucked under
        _bent(CX - 0.04, CY - 0.02, -0.01, -0.12, 3.0),
        _bent(CX - 0.01, CY - 0.03, 0.01, -0.14, 3.0),
        _bent(CX + 0.02, CY - 0.02, 0.03, -0.12, 3.0),
        "curl"
    )

def _pose_N():
    """N: Two fingers over thumb."""
    return _make_hand(
        _curl(CX - 0.07, CY + 0.04, 0.05, 0.05),  # thumb under
        _bent(CX - 0.04, CY - 0.02, -0.01, -0.12, 3.0),
        _bent(CX - 0.01, CY - 0.03, 0.01, -0.14, 3.0),
        "curl", "curl"
    )

def _pose_O():
    """O: All fingertips touch thumb forming O circle."""
    return _make_hand(
        _ext(CX - 0.07, CY + 0.04, -0.02, -0.10, 0.6),
        _bent(CX - 0.04, CY - 0.02, -0.04, -0.16, 1.5),
        _bent(CX - 0.01, CY - 0.03, -0.02, -0.18, 1.5),
        _bent(CX + 0.02, CY - 0.02, 0.00, -0.16, 1.5),
        _bent(CX + 0.05, CY - 0.01, 0.02, -0.12, 1.5)
    )

def _pose_P():
    """P: Like K but pointing down."""
    return _make_hand(
        _ext(CX - 0.07, CY + 0.04, -0.04, 0.10),  # thumb down
        _ext(CX - 0.04, CY - 0.02, -0.12, 0.14),   # index down-left
        _ext(CX - 0.01, CY - 0.03, -0.06, 0.16),   # middle down
        "curl", "curl"
    )

def _pose_Q():
    """Q: Like G but pointing down."""
    return _make_hand(
        _ext(CX - 0.07, CY + 0.04, -0.10, 0.08),  # thumb down
        _ext(CX - 0.04, CY - 0.02, -0.14, 0.12),   # index down
        "curl", "curl", "curl"
    )

def _pose_R():
    """R: Index and middle crossed."""
    return _make_hand(
        "curl",
        _ext(CX - 0.04, CY - 0.02, 0.01, -0.24),   # index slightly right
        _ext(CX - 0.01, CY - 0.03, -0.03, -0.24),   # middle crosses over
        "curl", "curl"
    )

def _pose_S():
    """S: Fist with thumb over curled fingers."""
    return _make_hand(
        _ext(CX - 0.07, CY + 0.04, 0.06, -0.04, 0.6),  # thumb across front
        "curl", "curl", "curl", "curl"
    )

def _pose_T():
    """T: Fist with thumb between index and middle."""
    return _make_hand(
        _ext(CX - 0.07, CY + 0.04, 0.04, -0.08, 0.5),  # thumb peeking up
        "curl", "curl", "curl", "curl"
    )

def _pose_U():
    """U: Index + middle together pointing up."""
    return _make_hand(
        "curl",
        _ext(CX - 0.04, CY - 0.02, -0.01, -0.22),  # index up
        _ext(CX - 0.01, CY - 0.03, 0.00, -0.24),    # middle up (parallel)
        "curl", "curl"
    )

def _pose_V():
    """V: Index + middle spread apart (peace/victory)."""
    return _make_hand(
        "curl",
        _ext(CX - 0.04, CY - 0.02, -0.06, -0.22),  # index up-left
        _ext(CX - 0.01, CY - 0.03, 0.04, -0.24),    # middle up-right
        "curl", "curl"
    )

def _pose_W():
    """W: Index + middle + ring spread."""
    return _make_hand(
        "curl",
        _ext(CX - 0.04, CY - 0.02, -0.06, -0.20),  # index
        _ext(CX - 0.01, CY - 0.03, 0.00, -0.24),    # middle
        _ext(CX + 0.02, CY - 0.02, 0.06, -0.20),    # ring
        "curl"
    )

def _pose_X():
    """X: Index finger hooked/bent."""
    return _make_hand(
        "curl",
        [  # index hooked
            [CX - 0.04, CY - 0.02, 0],
            [CX - 0.04, CY - 0.12, 0],
            [CX - 0.02, CY - 0.16, -0.02],
            [CX + 0.00, CY - 0.12, -0.04],
        ],
        "curl", "curl", "curl"
    )

def _pose_Y():
    """Y: Thumb + pinky extended (shaka/hang loose)."""
    return _make_hand(
        _ext(CX - 0.07, CY + 0.04, -0.10, -0.12),  # thumb out
        "curl", "curl", "curl",
        _ext(CX + 0.05, CY - 0.01, 0.08, -0.16),   # pinky out
    )

def _pose_Z():
    """Z: Index traces Z in air (static = index pointing)."""
    return _make_hand(
        "curl",
        _ext(CX - 0.04, CY - 0.02, -0.02, -0.22),  # index up
        "curl", "curl", "curl"
    )

# ── Common gesture poses ──

def _pose_open():
    """Open palm — hello, stop, 5."""
    return _make_hand("ext", "ext", "ext", "ext", "ext")

def _pose_fist():
    """Basic fist — yes (nod)."""
    return _make_hand("curl", "curl", "curl", "curl", "curl")

def _pose_point():
    """Point up — 1, where, when."""
    return _pose_D()

def _pose_peace():
    """Peace / V sign — 2."""
    return _pose_V()

def _pose_three():
    """Three fingers — 3, W."""
    return _pose_W()

def _pose_four():
    """Four fingers — 4, B."""
    return _pose_B()

def _pose_thumb_up():
    """Thumbs up — good, like."""
    return _make_hand(
        _ext(CX - 0.07, CY + 0.04, -0.04, -0.18),  # thumb straight up
        "curl", "curl", "curl", "curl"
    )

def _pose_thumb_down():
    """Thumbs down — bad."""
    return _make_hand(
        _ext(CX - 0.07, CY + 0.04, -0.04, 0.16),  # thumb down
        "curl", "curl", "curl", "curl"
    )

def _pose_flat():
    """Flat hand sideways — please."""
    return _make_hand(
        _ext(CX - 0.07, CY + 0.04, -0.12, -0.04),
        _ext(CX - 0.04, CY - 0.02, -0.20, -0.02),
        _ext(CX - 0.01, CY - 0.03, -0.22, 0.00),
        _ext(CX + 0.02, CY - 0.02, -0.20, 0.02),
        _ext(CX + 0.05, CY - 0.01, -0.16, 0.04)
    )

def _pose_pinch():
    """Pinch — okay, small, eat."""
    return _pose_F()

def _pose_ily():
    """I Love You — thumb + index + pinky extended."""
    return _make_hand(
        _ext(CX - 0.07, CY + 0.04, -0.10, -0.12),  # thumb
        "ext",    # index
        "curl",   # middle curled
        "curl",   # ring curled
        "ext"     # pinky
    )


# ═══════════════════════════════════════════════════════════════
#  SIGN MAP — word → (start_pose, end_pose, motion)
#  All keys are LOWERCASE for case-insensitive lookup
# ═══════════════════════════════════════════════════════════════

SIGN_MAP: Dict[str, tuple] = {
    # ── Greetings ──
    "hello":        (_pose_open, _pose_open, "wave"),
    "vanakkam":     (_pose_open, _pose_flat, "nod"),
    "namaste":      (_pose_flat, _pose_flat, "nod"),
    "thank you":    (_pose_flat, _pose_open, "slide"),
    "dhanyavaad":   (_pose_flat, _pose_open, "slide"),
    "nandri":       (_pose_flat, _pose_open, "slide"),
    "please":       (_pose_flat, _pose_flat, "circle"),
    "kripaya":      (_pose_flat, _pose_flat, "circle"),
    "thayavu_seithu": (_pose_flat, _pose_flat, "circle"),
    "yes":          (_pose_fist, _pose_fist, "nod"),
    "haan":         (_pose_fist, _pose_fist, "nod"),
    "aam":          (_pose_S, _pose_S, "nod"),
    "no":           (_pose_U, _pose_fist, "shake"),
    "nahi":         (_pose_U, _pose_fist, "shake"),
    "illai":        (_pose_open, _pose_fist, "shake"),

    # ── Feelings ──
    "love":         (_pose_ily, _pose_ily, "static"),
    "pyaar":        (_pose_ily, _pose_ily, "static"),
    "anbu":         (_pose_ily, _pose_ily, "static"),
    "happy":        (_pose_open, _pose_open, "wave"),
    "khush":        (_pose_open, _pose_open, "wave"),
    "santhosham":   (_pose_open, _pose_open, "wave"),
    "sad":          (_pose_open, _pose_fist, "slide"),
    "dukhi":        (_pose_open, _pose_fist, "slide"),
    "varutham":     (_pose_open, _pose_fist, "slide"),

    # ── Actions ──
    "help":         (_pose_thumb_up, _pose_open, "wave"),
    "madad":        (_pose_thumb_up, _pose_open, "wave"),
    "udavi":        (_pose_thumb_up, _pose_open, "wave"),
    "sorry":        (_pose_A, _pose_A, "circle"),
    "maafi":        (_pose_A, _pose_A, "circle"),
    "mannithu":     (_pose_A, _pose_A, "circle"),
    "stop":         (_pose_open, _pose_open, "static"),
    "ruko":         (_pose_open, _pose_open, "static"),
    "nil":          (_pose_open, _pose_open, "static"),
    "eat":          (_pose_pinch, _pose_pinch, "nod"),
    "khana":        (_pose_pinch, _pose_pinch, "nod"),
    "saapidu":      (_pose_pinch, _pose_pinch, "nod"),
    "drink":        (_pose_C, _pose_C, "nod"),
    "peena":        (_pose_C, _pose_C, "nod"),
    "kudi":         (_pose_C, _pose_C, "nod"),
    "water":        (_pose_W, _pose_W, "shake"),
    "paani":        (_pose_W, _pose_W, "shake"),
    "thanni":       (_pose_W, _pose_W, "shake"),
    "want":         (_pose_C, _pose_fist, "slide"),
    "chahiye":      (_pose_C, _pose_fist, "slide"),
    "venum":        (_pose_C, _pose_fist, "slide"),
    "more":         (_pose_O, _pose_O, "nod"),
    "aur":          (_pose_O, _pose_O, "nod"),
    "innum":        (_pose_O, _pose_O, "nod"),

    # ── People ──
    "friend":       (_pose_X, _pose_X, "shake"),
    "dost":         (_pose_X, _pose_X, "shake"),
    "nanbane":      (_pose_X, _pose_X, "shake"),
    "family":       (_pose_F, _pose_F, "circle"),
    "parivaar":     (_pose_F, _pose_F, "circle"),
    "kudumbam":     (_pose_F, _pose_F, "circle"),

    # ── Good/Bad ──
    "good":         (_pose_thumb_up, _pose_thumb_up, "static"),
    "accha":        (_pose_thumb_up, _pose_thumb_up, "static"),
    "nalla":        (_pose_thumb_up, _pose_thumb_up, "static"),
    "bad":          (_pose_thumb_down, _pose_thumb_down, "static"),
    "bura":         (_pose_thumb_down, _pose_thumb_down, "static"),
    "ketta":        (_pose_thumb_down, _pose_thumb_down, "static"),

    # ── Questions ──
    "name":         (_pose_H, _pose_H, "nod"),
    "naam":         (_pose_H, _pose_H, "nod"),
    "peyar":        (_pose_H, _pose_H, "nod"),
    "how":          (_pose_open, _pose_C, "wave"),
    "kaise":        (_pose_open, _pose_C, "wave"),
    "eppadi":       (_pose_open, _pose_C, "wave"),
    "what":         (_pose_open, _pose_open, "shake"),
    "kya":          (_pose_open, _pose_open, "shake"),
    "enna":         (_pose_open, _pose_open, "shake"),
    "where":        (_pose_point, _pose_point, "shake"),
    "kahan":        (_pose_point, _pose_point, "shake"),
    "enga":         (_pose_point, _pose_point, "shake"),
    "when":         (_pose_point, _pose_point, "circle"),
    "kab":          (_pose_point, _pose_point, "circle"),
    "eppo":         (_pose_point, _pose_point, "circle"),

    # ── Movement ──
    "come":         (_pose_point, _pose_fist, "slide"),
    "aao":          (_pose_point, _pose_fist, "slide"),
    "vaa":          (_pose_point, _pose_fist, "slide"),
    "go":           (_pose_open, _pose_point, "slide"),
    "jao":          (_pose_open, _pose_point, "slide"),
    "po":           (_pose_open, _pose_point, "slide"),
    "finish":       (_pose_open, _pose_fist, "shake"),
    "khatam":       (_pose_open, _pose_fist, "shake"),
    "mudinthathu":  (_pose_open, _pose_fist, "shake"),
    "again":        (_pose_flat, _pose_C, "nod"),
    "phir_se":      (_pose_flat, _pose_C, "nod"),
    "meendum":      (_pose_flat, _pose_C, "nod"),
    "understand":   (_pose_point, _pose_open, "nod"),
    "samajh":       (_pose_point, _pose_open, "nod"),
    "puriyuthu":    (_pose_point, _pose_open, "nod"),

    # ── Numbers ──
    "0": (_pose_O,     _pose_O,     "static"),
    "1": (_pose_point, _pose_point, "static"),
    "2": (_pose_V,     _pose_V,     "static"),
    "3": (_pose_W,     _pose_W,     "static"),
    "4": (_pose_B,     _pose_B,     "static"),
    "5": (_pose_open,  _pose_open,  "static"),
    "6": (_pose_W,     _pose_O,     "nod"),
    "7": (_pose_B,     _pose_O,     "nod"),
    "8": (_pose_L,     _pose_O,     "nod"),
    "9": (_pose_F,     _pose_fist,  "nod"),

    # ── Emergency ──
    "call ambulance": (_pose_fist, _pose_open, "shake"),
    "i need help":    (_pose_open, _pose_thumb_up, "wave"),
    "i cannot hear":  (_pose_point, _pose_fist, "shake"),
    "i am allergic":  (_pose_open, _pose_fist, "nod"),
    "call police":    (_pose_fist, _pose_open, "wave"),
    "emergency":      (_pose_open, _pose_fist, "shake"),
    "danger":         (_pose_open, _pose_fist, "shake"),
    "pain":           (_pose_fist, _pose_fist, "nod"),
    "medicine":       (_pose_flat, _pose_pinch, "circle"),

    # ── Alphabet (all unique ASL fingerspelling!) ──
    "a": (_pose_A, _pose_A, "static"),
    "b": (_pose_B, _pose_B, "static"),
    "c": (_pose_C, _pose_C, "static"),
    "d": (_pose_D, _pose_D, "static"),
    "e": (_pose_E, _pose_E, "static"),
    "f": (_pose_F, _pose_F, "static"),
    "g": (_pose_G, _pose_G, "static"),
    "h": (_pose_H, _pose_H, "static"),
    "i": (_pose_I, _pose_I, "static"),
    "j": (_pose_J, _pose_J, "circle"),  # J has arc motion
    "k": (_pose_K, _pose_K, "static"),
    "l": (_pose_L, _pose_L, "static"),
    "m": (_pose_M, _pose_M, "static"),
    "n": (_pose_N, _pose_N, "static"),
    "o": (_pose_O, _pose_O, "static"),
    "p": (_pose_P, _pose_P, "static"),
    "q": (_pose_Q, _pose_Q, "static"),
    "r": (_pose_R, _pose_R, "static"),
    "s": (_pose_S, _pose_S, "static"),
    "t": (_pose_T, _pose_T, "static"),
    "u": (_pose_U, _pose_U, "static"),
    "v": (_pose_V, _pose_V, "static"),
    "w": (_pose_W, _pose_W, "static"),
    "x": (_pose_X, _pose_X, "static"),
    "y": (_pose_Y, _pose_Y, "static"),
    "z": (_pose_Z, _pose_Z, "slide"),  # Z has slide motion

    # ── Tamil Vowels (உயிர் எழுத்துகள்) ──
    "அ": (_pose_A, _pose_A, "static"),         # a
    "ஆ": (_pose_A, _pose_open, "wave"),         # aa - open palm wave
    "இ": (_pose_I, _pose_I, "static"),          # i
    "ஈ": (_pose_I, _pose_E, "nod"),             # ii - nod motion
    "உ": (_pose_U, _pose_U, "static"),          # u
    "ஊ": (_pose_U, _pose_O, "wave"),            # uu - wave motion
    "எ": (_pose_E, _pose_E, "static"),          # e
    "ஏ": (_pose_E, _pose_A, "slide"),           # ee - slide motion
    "ஐ": (_pose_ily, _pose_ily, "nod"),         # ai - ILY with nod
    "ஒ": (_pose_O, _pose_O, "static"),          # o
    "ஓ": (_pose_O, _pose_C, "wave"),            # oo - wave motion
    "ஔ": (_pose_open, _pose_fist, "shake"),     # au - open to fist

    # ── Tamil Consonants (மெய் எழுத்துகள்) ──
    "க": (_pose_K, _pose_K, "static"),          # ka
    "ங": (_pose_N, _pose_G, "nod"),             # nga
    "ச": (_pose_C, _pose_C, "static"),          # cha
    "ஞ": (_pose_N, _pose_Y, "slide"),           # nya
    "ட": (_pose_D, _pose_D, "static"),          # ta
    "ண": (_pose_N, _pose_D, "nod"),             # Na
    "த": (_pose_T, _pose_T, "static"),          # tha
    "ந": (_pose_N, _pose_T, "wave"),            # na
    "ப": (_pose_B, _pose_B, "static"),          # pa
    "ம": (_pose_M, _pose_M, "static"),          # ma
    "ய": (_pose_Y, _pose_Y, "static"),          # ya
    "ர": (_pose_R, _pose_R, "static"),          # ra
    "ல": (_pose_L, _pose_L, "static"),          # la
    "வ": (_pose_V, _pose_V, "static"),          # va
    "ழ": (_pose_Z, _pose_L, "circle"),          # zha
    "ள": (_pose_L, _pose_flat, "nod"),          # La
    "ற": (_pose_R, _pose_T, "shake"),           # Ra
    "ன": (_pose_N, _pose_N, "static"),          # na
}


# ═══════════════════════════════════════════════════════════════
#  ANIMATION GENERATOR
# ═══════════════════════════════════════════════════════════════

def _lerp(a, b, t):
    return a + (b - a) * t

def _lerp_landmarks(lm_a, lm_b, t):
    result = []
    for i in range(min(len(lm_a), len(lm_b), 21)):
        x = _lerp(lm_a[i][0], lm_b[i][0], t)
        y = _lerp(lm_a[i][1], lm_b[i][1], t)
        z = _lerp(lm_a[i][2], lm_b[i][2], t)
        result.append([round(x, 4), round(y, 4), round(z, 4)])
    return result

def _apply_motion(landmarks, motion_type, t, amp=0.025):
    result = []
    for lm in landmarks:
        x, y, z = lm[0], lm[1], lm[2]
        if motion_type == "wave":
            x += amp * math.sin(2 * math.pi * t * 2)
        elif motion_type == "nod":
            y += amp * math.sin(2 * math.pi * t)
        elif motion_type == "slide":
            x += amp * 1.5 * (t - 0.5)
        elif motion_type == "circle":
            x += amp * math.cos(2 * math.pi * t)
            y += amp * math.sin(2 * math.pi * t)
        elif motion_type == "shake":
            x += amp * math.sin(4 * math.pi * t)
        result.append([round(x, 4), round(y, 4), round(z, 4)])
    return result


def _generate_sign_frames(word: str, num_frames: int = 36) -> List[dict]:
    """Generate animation frames for a word."""
    key = word.lower()

    if key in SIGN_MAP:
        start_fn, end_fn, motion = SIGN_MAP[key]
        start_lm = start_fn()
        end_lm = end_fn()
    else:
        # Fallback: use a deterministic pose based on word hash
        random.seed(abs(hash(key)) % 2**32)
        all_poses = [
            _pose_A, _pose_B, _pose_C, _pose_D, _pose_E, _pose_F,
            _pose_G, _pose_H, _pose_K, _pose_L, _pose_O, _pose_R,
            _pose_V, _pose_W, _pose_Y, _pose_open, _pose_fist,
            _pose_thumb_up, _pose_flat, _pose_ily,
        ]
        start_fn = random.choice(all_poses)
        end_fn = random.choice(all_poses)
        motion = random.choice(["wave", "nod", "slide", "circle", "shake"])
        start_lm = start_fn()
        end_lm = end_fn()

    # Ensure both have 21 landmarks
    while len(start_lm) < 21:
        start_lm.append([CX, CY, 0])
    while len(end_lm) < 21:
        end_lm.append([CX, CY, 0])

    frames = []
    for i in range(num_frames):
        t = i / max(num_frames - 1, 1)
        shape_t = 0.5 - 0.5 * math.cos(math.pi * t)
        lm = _lerp_landmarks(start_lm, end_lm, shape_t)
        lm = _apply_motion(lm, motion, t)
        frames.append({"hand": lm, "pose": []})

    return frames


# ═══════════════════════════════════════════════════════════════
#  PUBLIC API
# ═══════════════════════════════════════════════════════════════

_pose_cache: Dict[str, Any] = {}


def get_sign_sequence(word: str, language: str = "ASL") -> Optional[List[dict]]:
    """Return landmark animation frames. Case-insensitive."""
    word = word.lower()
    key = f"{language}:{word}"
    if key in _pose_cache:
        return _pose_cache[key]

    # Try JSON file
    json_path = DATA_DIR / language / f"{word}.json"
    if json_path.exists():
        with open(json_path, "r") as f:
            data = json.load(f)
            _pose_cache[key] = data.get("frames", [])
            return _pose_cache[key]

    # Generate
    frames = _generate_sign_frames(word)
    _pose_cache[key] = frames
    return frames


def get_vocab_for_language(language: str) -> List[str]:
    return VOCABULARY.get(language, [])


def predict_to_word(class_index: int) -> Optional[str]:
    if 0 <= class_index < len(FLAT_VOCAB):
        return FLAT_VOCAB[class_index]
    return None
