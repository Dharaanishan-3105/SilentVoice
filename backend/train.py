"""
SilentVoice — Model Training Script.

Generates synthetic training data from sign_library.py poses,
trains per-language classifier heads, and saves weights.

Usage:
    python train.py              # Train all languages
    python train.py --epochs 50  # Custom epochs

This will:
  1. Generate 200 synthetic 40-frame sequences per sign (with noise + augmentation)
  2. Train 3 separate language heads (ASL, ISL, TSL) sharing one encoder
  3. Save weights to pretrained_models/silentvoice.pth
  4. Print accuracy per language
"""

import argparse
import math
import os
import random
import sys
import time

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from services.sign_library import SIGN_MAP, VOCABULARY, get_sign_sequence
from ml.transformer import SignLanguageTransformer

# ═══════════════════════════════════════════════════════════════
#  CONFIG
# ═══════════════════════════════════════════════════════════════

SEQ_LEN = 40
INPUT_DIM = 63  # 21 landmarks * 3
SAMPLES_PER_SIGN = 800  # Increased for higher accuracy
BATCH_SIZE = 32
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

# ═══════════════════════════════════════════════════════════════
#  NORMALIZER (same as main.py)
# ═══════════════════════════════════════════════════════════════

def normalize_landmarks(landmarks):
    """Normalize 21 landmarks to be position/scale invariant."""
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


# ═══════════════════════════════════════════════════════════════
#  SYNTHETIC DATA GENERATION
# ═══════════════════════════════════════════════════════════════

def add_noise(landmarks, scale=0.015):
    """Add Gaussian noise to landmarks for augmentation."""
    return [[x + random.gauss(0, scale),
             y + random.gauss(0, scale),
             z + random.gauss(0, scale * 0.5)]
            for x, y, z in landmarks]


def jitter_timing(t, amount=0.15):
    """Randomly jitter the interpolation timing."""
    return max(0.0, min(1.0, t + random.gauss(0, amount)))


def scale_hand(landmarks, factor):
    """Scale hand by factor around centroid."""
    n = len(landmarks)
    if n == 0:
        return landmarks
    cx = sum(l[0] for l in landmarks) / n
    cy = sum(l[1] for l in landmarks) / n
    return [[(l[0] - cx) * factor + cx,
             (l[1] - cy) * factor + cy,
             l[2] * factor] for l in landmarks]


def shift_hand(landmarks, dx, dy):
    """Translate hand position."""
    return [[l[0] + dx, l[1] + dy, l[2]] for l in landmarks]


def rotate_hand(landmarks, angle_deg):
    """Rotate hand landmarks around Z axis (in xy plane) by angle_deg."""
    angle_rad = math.radians(angle_deg)
    cos_a = math.cos(angle_rad)
    sin_a = math.sin(angle_rad)
    n = len(landmarks)
    if n == 0:
        return landmarks
        
    cx = sum(l[0] for l in landmarks) / n
    cy = sum(l[1] for l in landmarks) / n
    
    rotated = []
    for l in landmarks:
        x, y, z = l[0] - cx, l[1] - cy, l[2]
        nx = x * cos_a - y * sin_a
        ny = x * sin_a + y * cos_a
        rotated.append([nx + cx, ny + cy, z])
    return rotated


def drop_frames(frames, drop_prob=0.08):
    """Randomly drop frames to simulate camera missed detections (replaces with previous frame)."""
    if not frames:
        return frames
    result = [frames[0]]
    for i in range(1, len(frames)):
        if random.random() < drop_prob:
            result.append(result[-1])  # Duplicate previous frame (simulate freeze/drop)
        else:
            result.append(frames[i])
    return result


def generate_sequence(sign_key, num_frames=SEQ_LEN):
    """Generate one synthetic training sequence for a sign."""
    if sign_key not in SIGN_MAP:
        return None

    start_fn, end_fn, motion = SIGN_MAP[sign_key]
    start_lm = start_fn()
    end_lm = end_fn()

    # Ensure 21 landmarks
    while len(start_lm) < 21:
        start_lm.append([0.5, 0.5, 0.0])
    while len(end_lm) < 21:
        end_lm.append([0.5, 0.5, 0.0])

    # Random augmentation parameters
    noise_scale = random.uniform(0.005, 0.035)
    scale_factor = random.uniform(0.75, 1.25)
    dx = random.uniform(-0.1, 0.1)
    dy = random.uniform(-0.1, 0.1)
    speed_factor = random.uniform(0.6, 1.4)
    motion_amp = random.uniform(0.01, 0.05)
    rotation_angle = random.uniform(-25.0, 25.0)

    frames = []
    for i in range(num_frames):
        # Variable speed
        raw_t = i / max(num_frames - 1, 1)
        t = max(0.0, min(1.0, raw_t * speed_factor + random.gauss(0, 0.02)))

        # Smooth ease for shape interpolation
        shape_t = 0.5 - 0.5 * math.cos(math.pi * t)

        # Interpolate between start and end pose
        lm = []
        for j in range(21):
            x = start_lm[j][0] + (end_lm[j][0] - start_lm[j][0]) * shape_t
            y = start_lm[j][1] + (end_lm[j][1] - start_lm[j][1]) * shape_t
            z = start_lm[j][2] + (end_lm[j][2] - start_lm[j][2]) * shape_t
            lm.append([x, y, z])

        # Apply motion
        for j in range(len(lm)):
            x, y, z = lm[j]
            if motion == "wave":
                x += motion_amp * math.sin(2 * math.pi * t * 2)
            elif motion == "nod":
                y += motion_amp * math.sin(2 * math.pi * t)
            elif motion == "slide":
                x += motion_amp * 1.5 * (t - 0.5)
            elif motion == "circle":
                x += motion_amp * math.cos(2 * math.pi * t)
                y += motion_amp * math.sin(2 * math.pi * t)
            elif motion == "shake":
                x += motion_amp * math.sin(4 * math.pi * t)
            lm[j] = [x, y, z]

        # Augment: scale, rotate, shift, noise
        lm = scale_hand(lm, scale_factor)
        lm = rotate_hand(lm, rotation_angle)
        lm = shift_hand(lm, dx, dy)
        lm = add_noise(lm, noise_scale)

        # Normalize (same as real-time pipeline)
        normalized = normalize_landmarks(lm)
        frames.append(normalized)

    # Apply frame dropout
    frames = drop_frames(frames, drop_prob=0.1)

    return frames


def _generate_samples_for_word(args):
    """Helper for multiprocessing generation."""
    word, samples = args
    seqs = []
    for _ in range(samples):
        seq = generate_sequence(word)
        if seq is not None:
            seqs.append(seq)
    return word, seqs

def build_language_vocab(language):
    """Build word list and index mapping for one language."""
    words = VOCABULARY.get(language, [])
    # Only keep words that have a sign definition
    valid_words = []
    for w in words:
        key = w.lower()
        if key in SIGN_MAP:
            valid_words.append(key)

    # Deduplicate preserving order
    seen = set()
    unique = []
    for w in valid_words:
        if w not in seen:
            seen.add(w)
            unique.append(w)

    word_to_idx = {w: i for i, w in enumerate(unique)}
    return unique, word_to_idx


def generate_dataset(language, samples_per_sign=SAMPLES_PER_SIGN):
    """Generate full training dataset for one language."""
    import concurrent.futures
    words, word_to_idx = build_language_vocab(language)

    print(f"\n  [{language}] {len(words)} signs with definitions (Generating in parallel...)")

    all_X = []
    all_y = []

    tasks = [(word, samples_per_sign) for word in words]
    with concurrent.futures.ProcessPoolExecutor() as executor:
        for word, seqs in executor.map(_generate_samples_for_word, tasks):
            idx = word_to_idx[word]
            for seq in seqs:
                all_X.append(seq)
                all_y.append(idx)

    X = np.array(all_X, dtype=np.float32)
    y = np.array(all_y, dtype=np.int64)

    print(f"  [{language}] Generated {len(all_X)} samples "
          f"({len(words)} signs × {samples_per_sign} each)")
    print(f"  [{language}] Shape: X={X.shape}, y={y.shape}")

    return X, y, words, word_to_idx


# ═══════════════════════════════════════════════════════════════
#  TRAINING
# ═══════════════════════════════════════════════════════════════

def train_language(model, language, X, y, epochs=30, lr=0.001):
    """Train one language head."""
    # Split 85/15 train/val
    n = len(X)
    perm = np.random.permutation(n)
    split = int(n * 0.85)
    train_idx = perm[:split]
    val_idx = perm[split:]

    X_train = torch.from_numpy(X[train_idx]).to(DEVICE)
    y_train = torch.from_numpy(y[train_idx]).to(DEVICE)
    X_val = torch.from_numpy(X[val_idx]).to(DEVICE)
    y_val = torch.from_numpy(y[val_idx]).to(DEVICE)

    train_ds = TensorDataset(X_train, y_train)
    train_dl = DataLoader(train_ds, batch_size=BATCH_SIZE, shuffle=True)

    val_ds = TensorDataset(X_val, y_val)
    val_dl = DataLoader(val_ds, batch_size=BATCH_SIZE, shuffle=False)

    optimizer = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-4)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs)
    criterion = nn.CrossEntropyLoss()

    best_val_acc = 0.0
    best_state = None

    for epoch in range(epochs):
        model.train()
        total_loss = 0.0
        correct = 0
        total = 0

        for xb, yb in train_dl:
            optimizer.zero_grad()
            logits = model(xb, language=language)
            loss = criterion(logits, yb)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()

            total_loss += loss.item() * len(xb)
            correct += (logits.argmax(dim=-1) == yb).sum().item()
            total += len(xb)

        scheduler.step()
        train_acc = correct / total
        train_loss = total_loss / total

        # Validation
        model.eval()
        val_loss = 0.0
        val_correct = 0
        val_total = 0
        with torch.no_grad():
            for xb, yb in val_dl:
                logits = model(xb, language=language)
                loss = criterion(logits, yb)
                val_loss += loss.item() * len(xb)
                val_correct += (logits.argmax(dim=-1) == yb).sum().item()
                val_total += len(xb)
        
        val_acc = val_correct / val_total
        val_loss = val_loss / val_total

        if val_acc > best_val_acc:
            best_val_acc = val_acc
            best_state = {k: v.clone() for k, v in model.state_dict().items()}

        if (epoch + 1) % 5 == 0 or epoch == 0:
            print(f"  [{language}] Epoch {epoch+1:3d}/{epochs}  "
                  f"Loss: {train_loss:.4f}  "
                  f"Train Acc: {train_acc:.1%}  "
                  f"Val Acc: {val_acc:.1%}  "
                  f"Best: {best_val_acc:.1%}")

    # Restore best weights
    if best_state:
        model.load_state_dict(best_state)

    return best_val_acc


def main():
    parser = argparse.ArgumentParser(description="Train SilentVoice model")
    parser.add_argument("--epochs", type=int, default=30, help="Training epochs per language")
    parser.add_argument("--samples", type=int, default=200, help="Samples per sign")
    parser.add_argument("--lr", type=float, default=0.001, help="Learning rate")
    args = parser.parse_args()

    print()
    print("  ╔═══════════════════════════════════════════╗")
    print("  ║   🧠 SilentVoice — Model Training         ║")
    print("  ║                                           ║")
    print("  ║   © 2026 Dharaanishan                     ║")
    print("  ╚═══════════════════════════════════════════╝")
    print()

    # Build per-language vocabs
    lang_vocabs = {}
    lang_data = {}
    lang_word_lists = {}

    for language in ["ASL", "ISL", "TSL"]:
        X, y, words, word_to_idx = generate_dataset(language, args.samples)
        lang_vocabs[language] = len(words)
        lang_data[language] = (X, y)
        lang_word_lists[language] = words

    print(f"\n  Language vocab sizes: {lang_vocabs}")

    # Create model with higher capacity for 95% accuracy
    model = SignLanguageTransformer(
        input_dim=INPUT_DIM,
        d_model=256,
        nhead=8,
        num_layers=4,
        dim_feedforward=512,
        dropout=0.2,
        use_bilstm=True,
        lstm_layers=2,
        lang_vocab=lang_vocabs,
    ).to(DEVICE)

    param_count = sum(p.numel() for p in model.parameters())
    print(f"  Model parameters: {param_count:,}")
    print(f"  Device: {DEVICE}")

    # Train each language
    results = {}
    start_time = time.time()

    for language in ["ASL", "ISL", "TSL"]:
        print(f"\n{'='*60}")
        print(f"  Training {language}...")
        print(f"{'='*60}")

        X, y = lang_data[language]
        acc = train_language(model, language, X, y, epochs=args.epochs, lr=args.lr)
        results[language] = acc

    elapsed = time.time() - start_time

    # Save weights
    save_dir = os.path.join(os.path.dirname(__file__), "pretrained_models")
    os.makedirs(save_dir, exist_ok=True)
    save_path = os.path.join(save_dir, "silentvoice.pth")

    # Save model weights + metadata
    torch.save({
        "model_state_dict": model.state_dict(),
        "lang_vocabs": lang_vocabs,
        "lang_word_lists": lang_word_lists,
        "input_dim": INPUT_DIM,
        "d_model": 256,
        "nhead": 8,
        "num_layers": 4,
        "dim_feedforward": 512,
        "results": results,
    }, save_path)

    print(f"\n{'='*60}")
    print(f"  ✅ Training Complete!")
    print(f"{'='*60}")
    print(f"  Time: {elapsed:.1f}s")
    print(f"  Weights saved: {save_path}")
    print()
    for lang, acc in results.items():
        emoji = "✅" if acc > 0.85 else "⚠️" if acc > 0.6 else "❌"
        print(f"  {emoji} {lang}: {acc:.1%} accuracy ({lang_vocabs[lang]} signs)")
    print()


if __name__ == "__main__":
    main()
