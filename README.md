# Podcast Shorts Generator 🎙️✂️

An automated, cloud-native AI pipeline and web application that converts long-form podcast & YouTube videos into viral 9:16 vertical shorts (with face tracking, animated karaoke captions, visual color grading, and audio polish).

---

## ⚡ Key Features

- **1-Click AI Video Repurposing**: Paste any YouTube link to generate high-engagement shorts automatically.
- **100% Cloud-Native & Fast**: Uses AssemblyAI Cloud API for ultra-fast multilingual transcription (~15–25s) with word-level timestamps.
- **AI Semantic Ranking**: Automatically evaluates and ranks the strongest hooks using Google Gemini Flash or OpenAI GPT-4o-mini.
- **9:16 AI Face Tracking**: DNN-based face detection (YuNet) smoothly centers the speaker in vertical format.
- **Animated Karaoke Captions**: Dynamic active-word highlighting with emoji auto-insertion.
- **Production-Ready & Secure**: Zero API key leakage. All keys remain safely in server environment variables.

---

## 🚀 Live Cloud Deployment

The repository is pre-configured for 1-click cloud deployment on **Render, Railway, Docker, Fly.io, or VPS**.

### 1. Required Environment Variables

Configure these 3 environment variables in your hosting dashboard or `.env` file:

```env
VIDEOSAILOR_API_KEY=your_videosailor_api_key_here
ASSEMBLYAI_API_KEY=your_assemblyai_api_key_here
GOOGLE_API_KEY=your_google_gemini_api_key_here
```

### 2. Deploy to Render / Railway / Cloud

- **Render**: Connect your GitHub repository as a **Web Service (Docker)**. It automatically uses the included `Dockerfile` and `render.yaml`.
- **Railway**: Connect repo $\to$ Add the environment variables $\to$ Deploy.
- **Docker Compose**:
  ```bash
  docker compose up -d --build
  ```

---

## 💻 Local Development

### Prerequisites
- Python 3.11+
- FFmpeg installed and available on PATH

### Run the App
```bash
# 1. Install lean dependencies
pip install -r requirements.txt

# 2. Start the unified server & web UI
python server.py

# 3. Open in your browser
http://localhost:5000
```

---

## 📁 Directory Structure

```
podcast-shorts-generator/
├── app/
│   ├── clip_selector.py   ← Phase 3: Highlight moment selection
│   ├── main.py            ← Unified CLI entry point
│   ├── semantic_ranker.py ← Phase 3.5: AI Semantic ranking (Gemini / OpenAI)
│   └── transcriber.py     ← Phase 2: AssemblyAI Cloud transcription
├── frontend/              ← Clean, modern web application UI
├── src/
│   ├── caption_renderer.py← Phase 5: Animated karaoke captions
│   ├── config.py          ← Central configuration
│   ├── downloader.py      ← Phase 1: High-speed YouTube download
│   ├── face_tracker.py    ← Phase 4: Face tracking engine
│   ├── inspector.py       ← Phase 1: Video metadata inspector
│   ├── reframer.py        ← Phase 4: 9:16 vertical reframing
│   └── renderer.py        ← Phase 4/5: Shorts video rendering engine
├── models/                ← Face detection DNN weights (YuNet)
├── Dockerfile             ← Production container definition
├── render.yaml            ← Render cloud deployment blueprint
├── docker-compose.yml     ← Docker Compose deployment
├── requirements.txt       ← Lean Python dependencies
└── server.py              ← Unified Web server & REST API
```
