"""
server.py
---------
Production REST API & Web Server for Podcast Shorts Generator.
Endpoints:
- Static UI serving (frontend/)
- Pipeline control & status (auto-generate, 5-phase)
- Video library & streaming (input/ and output/ directories)
- Video editor export (trim, filter, pitch, speed)

Run:
    python server.py
    python server.py --port 5000
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import shutil
import sys
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from src.editor_processor import export_edited_video
from src.logger import get_logger

log = get_logger("server")

ROOT_DIR = Path(__file__).parent.resolve()
FRONTEND_DIR = ROOT_DIR / "frontend"
INPUT_DIR = ROOT_DIR / "input"
OUTPUT_DIR = ROOT_DIR / "output"
TEMP_DIR = ROOT_DIR / "temp"

# Global pipeline state tracker
pipeline_state = {
    "status": "idle",       # "idle", "running", "completed", "error"
    "current_phase": None,  # "download", "transcribe", "select", "rank", "render"
    "progress": 0,          # 0-100
    "logs": [],
    "error": None,
}


def log_pipeline_msg(msg: str):
    log.info("[Pipeline] %s", msg)
    pipeline_state["logs"].append(msg)
    if len(pipeline_state["logs"]) > 200:
        pipeline_state["logs"].pop(0)


class PodcastShortsAPIHandler(SimpleHTTPRequestHandler):
    """Custom HTTP request handler providing both REST API endpoints and static frontend files."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(FRONTEND_DIR), **kwargs)

    def do_OPTIONS(self):
        self.send_response(200)
        self._send_cors_headers()
        self.end_headers()

    def _send_cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _send_json(self, data: Any, status: int = 200):
        self.send_response(status)
        self._send_cors_headers()
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data, indent=2).encode("utf-8"))

    def _send_error_json(self, message: str, status: int = 400):
        self._send_json({"success": False, "error": message}, status=status)

    def _read_json_body(self) -> dict:
        content_len = int(self.headers.get("Content-Length", 0))
        if content_len == 0:
            return {}
        raw = self.wfile if False else self.rfile.read(content_len)
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception:
            return {}

    # ── GET Handler ────────────────────────────────────────────────────────
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path in ("/health", "/api/health"):
            self._send_json({"status": "healthy", "service": "podcast-shorts-generator", "version": "1.0.0"})
            return
        elif path == "/api/status":
            self._handle_status()
            return
        elif path == "/api/files/input":
            self._handle_list_inputs()
            return
        elif path == "/api/files/output":
            self._handle_list_outputs()
            return
        elif path == "/api/config":
            self._handle_get_config()
            return
        elif path.startswith("/api/stream/output/"):
            filename = path.replace("/api/stream/output/", "")
            self._handle_stream_file(OUTPUT_DIR / filename)
            return
        elif path.startswith("/api/stream/input/"):
            filename = path.replace("/api/stream/input/", "")
            self._handle_stream_file(INPUT_DIR / filename)
            return
        elif path == "/" or path == "/index.html":
            self.path = "/index.html"
            return super().do_GET()

        # Fallback to serving static files from frontend directory
        return super().do_GET()

    # ── POST Handler ───────────────────────────────────────────────────────
    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/pipeline/auto-generate":
            self._handle_auto_generate()
        elif path == "/api/config":
            self._handle_save_config()
        elif path == "/api/editor/export":
            self._handle_editor_export()
        elif path in ("/api/files/output/clear", "/api/outputs/clear"):
            self._handle_clear_outputs()
        elif path in ("/api/files/output/delete", "/api/outputs/delete"):
            self._handle_delete_output()
        else:
            self._send_error_json(f"Unknown endpoint: {path}", status=404)

    # ── Route Handlers ─────────────────────────────────────────────────────

    def _handle_get_config(self):
        try:
            from src.config import get_all_api_config
            cfg = get_all_api_config()
            self._send_json({"success": True, "config": cfg})
        except Exception as exc:
            self._send_error_json(f"Failed to read API configuration: {exc}")

    def _handle_save_config(self):
        body = self._read_json_body()
        try:
            from src.config import save_api_config, get_all_api_config
            save_api_config(body)
            self._send_json({
                "success": True,
                "message": "API keys and configuration saved successfully!",
                "config": get_all_api_config(),
            })
        except Exception as exc:
            self._send_error_json(f"Failed to save API configuration: {exc}")

    def _handle_status(self):
        from src.config import get_all_api_config
        cfg = get_all_api_config()
        self._send_json({
            "success": True,
            "pipeline": pipeline_state,
            "services": {
                "assemblyai": cfg["assemblyai"]["is_set"],
                "videosailor": cfg["videosailor"]["is_set"],
                "gemini": cfg["google"]["is_set"],
                "openai": cfg["openai"]["is_set"],
                "ffmpeg": True,
            }
        })

    def _handle_list_inputs(self):
        INPUT_DIR.mkdir(parents=True, exist_ok=True)
        files = []
        for f in INPUT_DIR.glob("*"):
            if f.suffix.lower() in [".mp4", ".mkv", ".mov", ".webm"]:
                files.append({
                    "name": f.name,
                    "size_mb": round(f.stat().st_size / (1024 * 1024), 2),
                    "modified": f.stat().st_mtime,
                })
        self._send_json({"success": True, "files": sorted(files, key=lambda x: x["modified"], reverse=True)})

    def _handle_list_outputs(self):
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        files = []
        for f in OUTPUT_DIR.glob("*.mp4"):
            stat = f.stat()
            files.append({
                "name": f.name,
                "size_mb": round(stat.st_size / (1024 * 1024), 2),
                "modified": stat.st_mtime,
                "url": f"/api/stream/output/{f.name}",
            })
        self._send_json({"success": True, "files": sorted(files, key=lambda x: x["name"])})

    def _handle_clear_outputs(self):
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        count = 0
        for f in OUTPUT_DIR.glob("*.mp4"):
            try:
                f.unlink(missing_ok=True)
                count += 1
            except Exception:
                pass
        self._send_json({"success": True, "message": f"Deleted {count} output files"})

    def _handle_delete_output(self):
        body = self._read_json_body()
        filename = body.get("filename", "")
        if not filename:
            self._send_error_json("Missing filename")
            return
        target = OUTPUT_DIR / filename
        if target.exists() and target.is_file():
            try:
                target.unlink()
                self._send_json({"success": True, "message": f"Deleted {filename}"})
                return
            except Exception as ex:
                self._send_error_json(f"Could not delete: {ex}", status=500)
                return
        self._send_error_json("File not found", status=404)

    def _handle_stream_file(self, file_path: Path):
        if not file_path.exists() or not file_path.is_file():
            self.send_error(404, "File not found")
            return

        mime_type, _ = mimetypes.guess_type(str(file_path))
        if not mime_type:
            mime_type = "video/mp4"

        stat = file_path.stat()
        file_size = stat.st_size

        # Simple file delivery with range support
        range_header = self.headers.get("Range")
        if range_header:
            try:
                ranges = range_header.replace("bytes=", "").split("-")
                start = int(ranges[0])
                end = int(ranges[1]) if ranges[1] else file_size - 1
                length = end - start + 1

                self.send_response(206)
                self.send_header("Content-Type", mime_type)
                self.send_header("Content-Range", f"bytes {start}-{end}/{file_size}")
                self.send_header("Content-Length", str(length))
                self.send_header("Accept-Ranges", "bytes")
                self._send_cors_headers()
                self.end_headers()

                with open(file_path, "rb") as f:
                    f.seek(start)
                    remaining = length
                    while remaining > 0:
                        chunk_size = min(64 * 1024, remaining)
                        data = f.read(chunk_size)
                        if not data:
                            break
                        self.wfile.write(data)
                        remaining -= len(data)
                return
            except Exception:
                pass

        self.send_response(200)
        self.send_header("Content-Type", mime_type)
        self.send_header("Content-Length", str(file_size))
        self.send_header("Accept-Ranges", "bytes")
        self._send_cors_headers()
        self.end_headers()

        with open(file_path, "rb") as f:
            while chunk := f.read(64 * 1024):
                self.wfile.write(chunk)

    # ── Pipeline Execution Endpoints ───────────────────────────────────────

    def _handle_auto_generate(self):
        body = self._read_json_body()
        url = body.get("url", "").strip()
        filename = body.get("filename", "").strip()
        num_shorts_raw = body.get("num_shorts")
        if str(num_shorts_raw).lower() in ("all", "none", "", "0") or num_shorts_raw is None:
            num_shorts = None
        else:
            try:
                num_shorts = int(num_shorts_raw)
            except Exception:
                num_shorts = None
        if not url and not filename:
            self._send_error_json("Please provide a YouTube URL or a video file.")
            return

        if pipeline_state["status"] == "running":
            self._send_json({"success": True, "message": "Pipeline already running", "pipeline": pipeline_state})
            return

        def run_full_pipeline_task():
            pipeline_state["status"] = "running"
            pipeline_state["progress"] = 5
            pipeline_state["error"] = None
            pipeline_state["logs"] = []
            pipeline_state["new_outputs"] = []

            # ── Clean previous input/temp/output data so runs never mix across videos ──
            try:
                # 1. Clear temp directory completely
                for temp_item in TEMP_DIR.glob("*"):
                    if temp_item.is_file():
                        temp_item.unlink(missing_ok=True)
                    elif temp_item.is_dir():
                        shutil.rmtree(temp_item, ignore_errors=True)

                # 2. If a new YouTube URL is provided, permanently delete old input videos
                if url:
                    for old_vid in INPUT_DIR.glob("*"):
                        if old_vid.is_file():
                            try:
                                old_vid.unlink(missing_ok=True)
                            except Exception as del_err:
                                log.warning("Could not delete old input %s: %s", old_vid.name, del_err)

                # 3. Clean old output shorts so gallery only displays new video results
                for old_out in OUTPUT_DIR.glob("*.mp4"):
                    if old_out.is_file():
                        try:
                            old_out.unlink(missing_ok=True)
                        except Exception as del_err:
                            log.warning("Could not delete old output %s: %s", old_out.name, del_err)

            except Exception as clean_err:
                log.warning("Could not clean previous workspace data: %s", clean_err)

            try:
                # ── Phase 1: Video Download or Selection ───────────────────
                pipeline_state["current_phase"] = "download"
                video_path = None

                if url:
                    log_pipeline_msg(f"🎬 [1/5] Downloading fresh video from: {url}")
                    from src.downloader import download_video
                    video_path = download_video(url)
                    log_pipeline_msg(f"✓ Video downloaded: {video_path.name}")
                elif filename:
                    video_path = INPUT_DIR / filename
                    if not video_path.exists():
                        raise FileNotFoundError(f"Input file not found: {filename}")
                    log_pipeline_msg(f"✓ Using input video: {video_path.name}")
                else:
                    from app.transcriber import load_latest_video
                    video_path = load_latest_video()
                    log_pipeline_msg(f"✓ Using latest input video: {video_path.name}")

                pipeline_state["progress"] = 25

                # ── Phase 2: Speech Transcription (AssemblyAI Cloud API) ───
                pipeline_state["current_phase"] = "transcribe"
                log_pipeline_msg("🎙️ [2/5] Transcribing audio with AssemblyAI Cloud API...")
                from app.transcriber import transcribe_video
                tr_result = transcribe_video(
                    video_path=video_path,
                    language=None,
                    keep_audio=False,
                )
                if tr_result.num_segments == 0:
                    log_pipeline_msg("ℹ No spoken dialogue detected — switched to High-Energy Action / Scene Highlight Detection Engine!")
                else:
                    log_pipeline_msg(f"✓ Transcription complete: {tr_result.num_segments} segments ({tr_result.language})")
                pipeline_state["progress"] = 45

                # ── Phase 3: Clip Selection Across Entire Full Video ────────
                pipeline_state["current_phase"] = "select"
                if tr_result.num_segments == 0:
                    log_pipeline_msg("⚡ [3/5] Detecting high-energy battle/action climaxes across full video...")
                else:
                    log_pipeline_msg("⚡ [3/5] Extracting all key viral highlight moments across full video...")
                from app.clip_selector import run_selection
                top_count = 100 if num_shorts is None else max(num_shorts * 2, 20)
                report = run_selection(
                    transcript_path=TEMP_DIR / "transcript.json",
                    min_dur=15.0,
                    max_dur=30.0,
                    top_n=top_count,
                    min_score=20.0,
                    min_separation=20.0,
                )
                log_pipeline_msg(f"✓ Selected {report['final_count']} highlight clips from entire video")
                pipeline_state["progress"] = 65

                # ── Phase 3.5: LLM Ranking ────────────────────────────────
                pipeline_state["current_phase"] = "rank"
                log_pipeline_msg("🧠 [4/5] Evaluating candidates with semantic AI ranking...")
                candidates_json = TEMP_DIR / "candidates.json"
                
                try:
                    from app.semantic_ranker import run_semantic_ranking
                    rank_target = report["final_count"] if num_shorts is None else num_shorts
                    rank_result = run_semantic_ranking(
                        candidates_path=TEMP_DIR / "candidate_pool.json",
                        transcript_path=TEMP_DIR / "transcript.json",
                        top_n=rank_target,
                        semantic_pool_size=max(rank_target, 50),
                        min_score=20.0,
                        min_separation=20.0,
                    )
                    candidates_json = Path(rank_result["json_path"])
                    log_pipeline_msg(f"✓ AI Semantic ranking complete: {len(rank_result['final_selected'])} top shorts ranked")
                except Exception as llm_err:
                    log_pipeline_msg(f"ℹ Semantic LLM ranking ({llm_err}) - using high-energy heuristic ranking.")

                pipeline_state["progress"] = 75

                # ── Phase 4 & 5: Render 9:16 Shorts for Full Video ────────
                pipeline_state["current_phase"] = "render"

                with open(candidates_json, "r", encoding="utf-8") as f:
                    candidates_data = json.load(f)

                if isinstance(candidates_data, dict):
                    clips_list = candidates_data.get("candidates", candidates_data.get("final_selected", []))
                elif isinstance(candidates_data, list):
                    clips_list = candidates_data
                else:
                    clips_list = []

                if num_shorts is not None and num_shorts > 0:
                    clips_to_render = clips_list[:num_shorts]
                else:
                    clips_to_render = clips_list

                num_to_render = len(clips_to_render)
                log_pipeline_msg(f"🎥 [5/5] Reframing 9:16 AI Face Tracking & burning captions for all {num_to_render} shorts across full video...")

                rendered_files = []

                from src.renderer import render_clip

                for idx in range(1, num_to_render + 1):
                    clip = clips_to_render[idx - 1]
                    out_name = f"short_{idx:03d}.mp4"
                    log_pipeline_msg(f"  Rendering Short #{idx}/{num_to_render}: {clip.get('text', '')[:45]}...")
                    
                    try:
                        result = render_clip(
                            rank=idx,
                            output_filename=out_name,
                            video_path=video_path,
                            candidates_path=candidates_json,
                            transcript_path=TEMP_DIR / "transcript.json",
                        )
                        rendered_files.append(out_name)
                        log_pipeline_msg(f"  ✓ Short #{idx} rendered → {out_name}")
                    except Exception as rend_exc:
                        log_pipeline_msg(f"  ✗ Failed rendering #{idx}: {rend_exc}")
                    finally:
                        # Force release of OpenCV buffers, NumPy arrays, Whisper model
                        import gc
                        gc.collect()

                    progress_pct = 75 + int((idx / num_to_render) * 24)
                    pipeline_state["progress"] = min(99, progress_pct)

                pipeline_state["progress"] = 100
                pipeline_state["status"] = "completed"
                pipeline_state["new_outputs"] = rendered_files
                log_pipeline_msg(f"🎉 Pipeline finished! {len(rendered_files)} new shorts ready in gallery.")

            except Exception as e:
                log_pipeline_msg(f"❌ Pipeline Error: {e}")
                pipeline_state["status"] = "error"
                pipeline_state["error"] = str(e)

        threading.Thread(target=run_full_pipeline_task, daemon=True).start()
        self._send_json({"success": True, "message": "Automatic generation pipeline started!"})

    # ── Video Editor Export Endpoint ───────────────────────────────────────

    def _handle_editor_export(self):
        body = self._read_json_body()
        filename = body.get("filename", "short_001.mp4")
        input_path = OUTPUT_DIR / filename
        if not input_path.exists():
            # Check input dir
            alt_path = INPUT_DIR / filename
            if alt_path.exists():
                input_path = alt_path
            else:
                self._send_error_json(f"Source video file '{filename}' not found in output or input directories.")
                return

        # Parameters
        start_time = body.get("start_time")
        end_time = body.get("end_time")
        preset = body.get("filter_preset", "none")
        brightness = float(body.get("brightness", 100.0))
        contrast = float(body.get("contrast", 100.0))
        saturation = float(body.get("saturation", 100.0))
        sharpen = float(body.get("sharpen", 0.0))
        pitch_semitones = float(body.get("pitch_semitones", 0.0))
        speed = float(body.get("speed", 1.0))
        volume = float(body.get("volume", 100.0))

        # Output path
        stem = input_path.stem
        out_filename = f"{stem}_edited.mp4"
        output_path = OUTPUT_DIR / out_filename

        try:
            exported = export_edited_video(
                input_path=input_path,
                output_path=output_path,
                start_time=start_time,
                end_time=end_time,
                preset=preset,
                brightness=brightness,
                contrast=contrast,
                saturation=saturation,
                sharpen=sharpen,
                pitch_semitones=pitch_semitones,
                speed=speed,
                volume=volume,
            )
            self._send_json({
                "success": True,
                "exported_file": exported.name,
                "url": f"/api/stream/output/{exported.name}",
            })
        except Exception as exc:
            log.error("Editor export error: %s", exc)
            self._send_error_json(f"Export processing failed: {exc}", status=500)


# Force UTF-8 output on Windows so emojis/logs render correctly
if sys.platform == "win32":
    import io
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "buffer"):
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")



def ensure_directories():
    for d in (INPUT_DIR, OUTPUT_DIR, TEMP_DIR, ROOT_DIR / "logs"):
        d.mkdir(parents=True, exist_ok=True)


def run_server(port: int | None = None, host: str | None = None):
    ensure_directories()
    
    # Resolve host and port with environment fallbacks
    if port is None:
        port = int(os.environ.get("PORT", 5000))
    if host is None:
        host = os.environ.get("HOST", "0.0.0.0")

    server_address = (host, port)
    httpd = ThreadingHTTPServer(server_address, PodcastShortsAPIHandler)
    
    display_host = "localhost" if host in ("0.0.0.0", "") else host
    print(f"\n=======================================================")
    print(f" [*] Podcast Shorts Web App & API Server Running!")
    print(f" [*] App URL:      http://{display_host}:{port}/")
    print(f" [*] Health Check: http://{display_host}:{port}/health")
    print(f" [*] Environment:  {'Production' if os.environ.get('PORT') else 'Development'}")
    print(f"=======================================================\n")

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[+] Gracefully shutting down server...")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Podcast Shorts Generator Web Server")
    parser.add_argument("--port", type=int, default=None, help="Port to listen on (default: 5000 or $PORT)")
    parser.add_argument("--host", type=str, default=None, help="Host to bind to (default: 0.0.0.0 or $HOST)")
    args = parser.parse_args()
    run_server(port=args.port, host=args.host)
