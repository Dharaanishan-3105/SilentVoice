"use client";

import { useRouter } from "next/navigation";
import Link from "next/link";
import Image from "next/image";

export default function LandingPage() {
  const router = useRouter();

  const handleGuest = () => {
    localStorage.setItem("sv_user", JSON.stringify({
      email: "guest", name: "Guest", loggedIn: true, isGuest: true,
    }));
    router.push("/app");
  };

  return (
    <div className="landing-container">
      {/* ── Navbar ── */}
      <nav className="landing-nav">
        <Link href="/" className="landing-nav-brand">
          <Image src="/logo.png" alt="SilentVoice" width={36} height={36} style={{ borderRadius: 8 }} />
          <span>SilentVoice</span>
        </Link>
        <div className="landing-nav-links">
          <a href="#features">Features</a>
          <a href="#how">How It Works</a>
          <a href="#languages">Languages</a>
        </div>
        <div className="landing-nav-actions">
          <Link href="/login" className="btn btn-ghost" style={{ fontSize: "0.85rem" }}>
            Sign In
          </Link>
          <Link href="/register" className="btn btn-primary" style={{ fontSize: "0.85rem", padding: "8px 20px" }}>
            Get Started Free
          </Link>
        </div>
      </nav>

      {/* ── Hero ── */}
      <section className="landing-hero">
        <div className="hero-glow" />
        <div className="hero-glow-2" />

        <div className="hero-badge-row">
          <span className="hero-badge">🤟 AI-Powered</span>
          <span className="hero-badge accent">Real-Time Translation</span>
        </div>

        <h1 className="hero-title">
          Breaking <span className="gradient-text">Communication</span> Barriers
          <br />
          With Sign Language AI
        </h1>

        <p className="hero-subtitle">
          The first real-time sign language translator supporting <strong>ASL</strong>, <strong>ISL</strong> &amp; <strong>TSL</strong>.
          <br />
          Sign to speak. Speak to sign. No interpreter needed.
        </p>

        <div className="hero-actions">
          <Link href="/register" className="btn btn-primary btn-xl hero-btn-primary">
            <span className="btn-shine" />
            🚀 Create Free Account
          </Link>
          <Link href="/login" className="btn btn-secondary btn-xl">
            Sign In
          </Link>
        </div>

        <p className="hero-guest-link">
          or <button onClick={handleGuest} className="guest-link" style={{ background: "none", border: "none", cursor: "pointer", font: "inherit" }}>
            continue as guest
          </button> with limited features
        </p>

        {/* Hero Stats */}
        <div className="hero-stats-grid">
          <div className="hero-stat-card">
            <div className="stat-number">3</div>
            <div className="stat-label">Sign Languages</div>
            <div className="stat-detail">ASL · ISL · TSL</div>
          </div>
          <div className="hero-stat-card">
            <div className="stat-number">220+</div>
            <div className="stat-label">Signs Trained</div>
            <div className="stat-detail">Letters, Words, Phrases</div>
          </div>
          <div className="hero-stat-card">
            <div className="stat-number">&lt;200ms</div>
            <div className="stat-label">Detection Speed</div>
            <div className="stat-detail">Real-Time in Browser</div>
          </div>
          <div className="hero-stat-card">
            <div className="stat-number">A-Z</div>
            <div className="stat-label">Full Alphabet</div>
            <div className="stat-detail">+ Numbers 0-9 + தமிழ்</div>
          </div>
        </div>
      </section>

      {/* ── Demo Section ── */}
      <section className="demo-section">
        <div className="demo-card">
          <div className="demo-visual">
            <div className="demo-hand">
              <div className="hand-pulse" />
              <span className="hand-emoji">🤟</span>
            </div>
            <div className="demo-arrow">→</div>
            <div className="demo-result">
              <span className="result-text">&ldquo;I Love You&rdquo;</span>
              <span className="result-conf">98.4% confident</span>
            </div>
          </div>
          <p className="demo-caption">Show a sign → AI translates instantly → Speaks it aloud</p>
        </div>
      </section>

      {/* ── Features ── */}
      <section className="features-section" id="features">
        <div className="section-header">
          <span className="section-badge">Features</span>
          <h2>Everything You Need for <span className="gradient-text">Accessible Communication</span></h2>
          <p className="section-sub">Six powerful modes designed for real-world communication, learning, and safety.</p>
        </div>

        <div className="features-grid">
          <div className="feature-card feature-primary">
            <div className="feature-icon cyan">💬</div>
            <h3>Real-Time Conversation</h3>
            <p>Two-way translation between sign language and speech. A deaf and hearing person can talk naturally — no interpreter needed.</p>
            <div className="feature-tag">Core Feature</div>
          </div>
          <div className="feature-card">
            <div className="feature-icon red">🚨</div>
            <h3>Emergency Mode</h3>
            <p>Instant rule-based detection for critical phrases. &ldquo;I need help&rdquo;, &ldquo;Call ambulance&rdquo; — triggers without AI delay.</p>
            <div className="feature-tag">Life-Saving</div>
          </div>
          <div className="feature-card">
            <div className="feature-icon green">📚</div>
            <h3>Interactive Learning</h3>
            <p>Learn sign language with AI accuracy feedback, gamified levels, and practice for all letters, numbers, and phrases.</p>
            <div className="feature-tag-locked">🔒 Account Required</div>
          </div>
          <div className="feature-card">
            <div className="feature-icon purple">🏢</div>
            <h3>Workplace Accessibility</h3>
            <p>Live meeting captioning with sign avatar display. For corporate diversity &amp; inclusion teams and HR.</p>
            <div className="feature-tag-locked">🔒 Account Required</div>
          </div>
          <div className="feature-card">
            <div className="feature-icon orange">📡</div>
            <h3>Offline Ready</h3>
            <p>Core recognition and emergency mode work without internet. Built for rural clinics, schools, and community centers.</p>
          </div>
          <div className="feature-card">
            <div className="feature-icon pink">💜</div>
            <h3>Personal Expression</h3>
            <p>Record sign messages, convert to voice, share with family. Emotional empowerment through technology.</p>
            <div className="feature-tag-locked">🔒 Account Required</div>
          </div>
        </div>
      </section>

      {/* ── How It Works ── */}
      <section className="how-section" id="how">
        <div className="section-header">
          <span className="section-badge">Technology</span>
          <h2>How <span className="gradient-text">SilentVoice</span> Works</h2>
        </div>

        <div className="how-timeline">
          <div className="timeline-step">
            <div className="step-number">1</div>
            <div className="step-content">
              <h3>Camera Captures Hands</h3>
              <p>MediaPipe Hand Landmarker extracts 21 3D landmarks per hand, entirely in your browser. <em>No video sent to any server.</em></p>
            </div>
          </div>
          <div className="timeline-connector" />
          <div className="timeline-step">
            <div className="step-number">2</div>
            <div className="step-content">
              <h3>AI Model Recognizes</h3>
              <p>BiLSTM + Transformer processes landmark sequences. Static signs → template matching. Motion signs → ML model.</p>
            </div>
          </div>
          <div className="timeline-connector" />
          <div className="timeline-step">
            <div className="step-number">3</div>
            <div className="step-content">
              <h3>Instant Translation</h3>
              <p>Recognized signs appear as text and are spoken aloud. Text-to-sign renders animated 2D hand avatars with correct poses.</p>
            </div>
          </div>
        </div>
      </section>

      {/* ── Languages ── */}
      <section className="languages-section" id="languages">
        <div className="section-header">
          <span className="section-badge">Languages</span>
          <h2>Three Sign Languages, <span className="gradient-text">One Platform</span></h2>
        </div>

        <div className="lang-cards">
          <div className="lang-card">
            <div className="lang-flag">🇺🇸</div>
            <h3>American Sign Language</h3>
            <p className="lang-code">ASL</p>
            <div className="lang-stats">
              <span>75 Signs</span>
              <span>A-Z Alphabet</span>
              <span>0-9 Numbers</span>
            </div>
          </div>
          <div className="lang-card">
            <div className="lang-flag">🇮🇳</div>
            <h3>Indian Sign Language</h3>
            <p className="lang-code">ISL</p>
            <div className="lang-stats">
              <span>76 Signs</span>
              <span>Hindi Phrases</span>
              <span>A-Z Alphabet</span>
            </div>
          </div>
          <div className="lang-card">
            <div className="lang-flag">🇮🇳</div>
            <h3>Tamil Sign Language</h3>
            <p className="lang-code">TSL</p>
            <div className="lang-stats">
              <span>76+ Signs</span>
              <span>30 Tamil Characters</span>
              <span>அ ஆ இ க ச ட த ப ம ...</span>
            </div>
          </div>
        </div>
      </section>

      {/* ── CTA ── */}
      <section className="cta-section">
        <div className="cta-glow" />
        <h2>Ready to Break Communication Barriers?</h2>
        <p>Join the movement to make sign language accessible to everyone, everywhere.</p>
        <div className="cta-actions">
          <Link href="/register" className="btn btn-primary btn-xl">
            🚀 Create Free Account
          </Link>
          <Link href="/login" className="btn btn-secondary btn-xl">
            Sign In
          </Link>
        </div>
        <p className="cta-note">Free forever. No credit card required.</p>
      </section>

      {/* ── Footer ── */}
      <footer className="landing-footer">
        <div className="footer-content">
          <div className="footer-brand">
            <Image src="/logo.png" alt="SilentVoice" width={28} height={28} style={{ borderRadius: 6 }} />
            <span>SilentVoice</span>
          </div>
          <div className="footer-links">
            <a href="#features">Features</a>
            <a href="#how">Technology</a>
            <a href="#languages">Languages</a>
          </div>
          <div className="footer-copy">
            © 2026 SilentVoice · Licensed to Dharaanishan · All Rights Reserved
            <br />
            ASL · ISL · TSL · A Communication Rights Platform
          </div>
        </div>
      </footer>
    </div>
  );
}
