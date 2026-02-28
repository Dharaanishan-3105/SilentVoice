<p align="center">
  <img src="frontend/public/logo.png" width="120" alt="SilentVoice Logo">
</p>

# SilentVoice — Web-Based AI Sign Language Translator

**SilentVoice** is a real-time, browser-based, AI-powered communication tool that breaks the barrier between hearing and Deaf individuals. It offers real-time two-way translation between speech and three distinct sign languages (ASL, ISL, TSL), eliminating the need for a human interpreter.

![Version](https://img.shields.io/badge/Version-4.1-blueviolet)
![Next.js](https://img.shields.io/badge/Next.js-15.1-black)
![PyTorch](https://img.shields.io/badge/PyTorch-AI-orange)
![MediaPipe](https://img.shields.io/badge/MediaPipe-Vision-blue)

---

## ✨ Features

- **🌐 Tri-lingual Support**: Supports American Sign Language (ASL), Indian Sign Language (ISL), and Tamil Sign Language (TSL).
- **⚡ Real-Time In-Browser Detection**: Utilizes MediaPipe Hand Landmarker combined with a Transformer + BiLSTM architecture to accurately classify 220+ signs under 200ms latency.
- **🗣️ Sign-to-Speech & Speech-to-Sign**: Converts live hand signs into spoken audio, and spoken words into animated, anatomically correct 2D hand sign avatars.
- **🚨 Emergency Mode**: High-priority alert phrase detection (e.g., "I need help", "Call an ambulance") using rule-based algorithms with zero dependency on the internet.
- **📚 Interactive Learning Center**: Gamified learning modules to help users practice ASL, ISL, and TSL. Includes real-time camera feedback on accuracy.
- **🔒 Guest Restrictions**: Dedicated roles restricting specific modules (Learning, Workplace, Expression) to registered accounts to encourage user retention.
- **💎 Premium UI/UX**: High-end glassmorphic dark theme built with TailwindCSS techniques compiled into standard CSS for optimal performance.

---

## 🛠️ Architecture

SilentVoice uses a dual-engine architecture to ensure privacy, speed, and accuracy.

1.  **Frontend (Next.js + React)**
    *   **MediaPipe Tasks Vision**: Extracts 21 3D landmarks for both hands, entirely client-side. No video streams are transmitted, preserving privacy.
    *   **Web Speech API**: Handles Speech-to-Text (STT) and Text-to-Speech (TTS).
    *   **WebSocket Client**: Streams normalized, lightweight hand landmark coordinates to the backend payload.
2.  **Backend (FastAPI + PyTorch)**
    *   **Dual-Pipeline Engine**:
        *   **Static Signs (A-Z, 0-9, Tamil Letters)**: Uses dynamic **Template Matching** directly against the anatomical pose library (`sign_library.py`) when low-motion is detected. Holding a static sign for 8 frames returns the prediction immediately.
        *   **Dynamic Signs (Phrases, Words)**: Uses a rolling sliding window buffer fed into the **Sign Language Transformer (BiLSTM + Mean Pool)** model.
    *   **Authentication Hub**: Built-in SQLite + JWT structure to handle users.

### Accuracy Specs (Synthetic Baseline)
*   **Model Capacity**: 256 d_model, 8 heads, 4 layers, ~1.5M parameters
*   **Augmentations**: Frame dropping (missed camera detection simulation), 3D spatial rotation, position shifting, and scaling.
*   **Validation Goal**: 85%–95% baseline accuracy across 220+ distinct signs.

---

## 🚀 Installation & Setup

### Prerequisites
*   Node.js 18+
*   Python 3.10+
*   NPM & pip

### 1. Clone the Repository
```bash
git clone https://github.com/yourusername/silentvoice.git
cd silentvoice
```

### 2. Setup Backend
Open a terminal in the `/backend` folder.
```bash
cd backend
python -m venv venv
# Windows
venv\Scripts\activate
# Mac/Linux
source venv/bin/activate

pip install -r requirements.txt
```

### 3. Setup Frontend
Open a new terminal in the `/frontend` folder.
```bash
cd frontend
npm install
```

### 4. Running the Application
You will need to run both the frontend and backend servers simultaneously.

**Terminal 1 (Backend)**:
```bash
cd backend
python main.py
```
*Runs on `http://localhost:8000`*

**Terminal 2 (Frontend)**:
```bash
cd frontend
npm run dev
```
*Runs on `http://localhost:3000`*

---

## 🧠 Training the Model

If you wish to augment the vocabulary or view the model in action, you can generate the synthetic dataset and rebuild the deep learning weights.

```bash
cd backend
python train.py --epochs 60 --samples 800
```
*Note: Due to the expanded augmentations (rotation, jitter, scaling, and frame-drops), generating the dataset and training the transformer takes roughly 15-30 minutes depending on your CUDA availability.*

---

## 📄 License & Credits

© 2026 Dharaanishan. All rights reserved. 
Built to make communication accessible for everyone, everywhere.
