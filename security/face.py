"""Local face detection, tracking and recognition.

Detection/tracking: YuNet (bundled ONNX, ~340 KB).
Recognition:        SFace  (ONNX, ~37 MB) — 128-d embeddings, cosine match.
Both run entirely on-device via OpenCV DNN; no frame ever leaves the machine.
Models are downloaded once from the official OpenCV model zoo into
config/security_data/models/ and cached.

TRACKING and RECOGNITION are separate functions by design:
  * tracking  = per-frame detection + bbox/landmark motion (cheap, every frame)
  * recognition = embedding + identity match (throttled, ~1/s)
"""
from __future__ import annotations

import os
import threading
import time
import urllib.request

import cv2
import numpy as np

from . import config

_MODELS = {
    "yunet": (
        "face_detection_yunet_2023mar.onnx",
        "https://github.com/opencv/opencv_zoo/raw/main/models/"
        "face_detection_yunet/face_detection_yunet_2023mar.onnx",
    ),
    "sface": (
        "face_recognition_sface_2021dec.onnx",
        "https://github.com/opencv/opencv_zoo/raw/main/models/"
        "face_recognition_sface/face_recognition_sface_2021dec.onnx",
    ),
}


def models_ready() -> bool:
    d = config.DATA_DIR / "models"
    return all((d / fname).exists() for fname, _ in _MODELS.values())


def ensure_models(progress=None) -> None:
    """Download missing models (once). Raises on failure with a clear message."""
    d = config.DATA_DIR / "models"
    d.mkdir(parents=True, exist_ok=True)
    for key, (fname, url) in _MODELS.items():
        dest = d / fname
        if dest.exists() and dest.stat().st_size > 100_000:
            continue
        if progress:
            progress(f"Downloading {fname} …")
        tmp = dest.with_suffix(".part")
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "JARVIS"})
            with urllib.request.urlopen(req, timeout=60) as r, open(tmp, "wb") as f:
                while True:
                    chunk = r.read(1 << 16)
                    if not chunk:
                        break
                    f.write(chunk)
            tmp.replace(dest)
        except Exception as e:
            tmp.unlink(missing_ok=True)
            raise RuntimeError(
                f"Could not download face model '{fname}': {e}. "
                "Download it manually from the OpenCV model zoo into "
                f"{d} and try again.") from e


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


class FaceEngine:
    """Model holder. Thread-safe lazy loading; usable without a camera."""

    def __init__(self):
        self._det = None
        self._rec = None
        self._lock = threading.Lock()
        self._det_size = (320, 240)

    def _load(self, recognition: bool) -> None:
        with self._lock:
            if self._det is None:
                ensure_models()
                self._det = cv2.FaceDetectorYN.create(
                    str(config.DATA_DIR / "models" / _MODELS["yunet"][0]),
                    "", self._det_size, 0.7, 0.3, 5000)
            if recognition and self._rec is None:
                self._rec = cv2.FaceRecognizerSF.create(
                    str(config.DATA_DIR / "models" / _MODELS["sface"][0]), "")

    def detect(self, frame) -> list[np.ndarray]:
        """Tracking primitive: faces in one frame (bbox + 5 landmarks + score)."""
        self._load(recognition=False)
        h, w = frame.shape[:2]
        with self._lock:
            if (w, h) != self._det_size:
                self._det_size = (w, h)
                self._det.setInputSize((w, h))
            _, faces = self._det.detect(frame)
        return [] if faces is None else [f for f in faces]

    def embed(self, frame, face) -> np.ndarray:
        """Recognition primitive: 128-d identity embedding for one face."""
        self._load(recognition=True)
        with self._lock:
            aligned = self._rec.alignCrop(frame, face)
            feat = self._rec.feature(aligned)
        return np.asarray(feat, dtype=np.float32).flatten()

    def match(self, emb: np.ndarray, templates: list[list[float]],
              threshold: float) -> tuple[bool, float]:
        best = max((_cosine(emb, np.asarray(t, dtype=np.float32))
                    for t in templates), default=0.0)
        return best >= threshold, best


def head_direction(face: np.ndarray) -> str:
    """Coarse head pose from YuNet landmarks (eyes, nose tip, mouth corners)."""
    try:
        le, re_, nose = face[4:6], face[6:8], face[8:10]
        eye_mid = (le + re_) / 2.0
        eye_dist = float(np.linalg.norm(re_ - le)) or 1.0
        dx = float(nose[0] - eye_mid[0]) / eye_dist
        dy = float(nose[1] - eye_mid[1]) / eye_dist
        if dx < -0.18:
            return "LEFT"
        if dx > 0.18:
            return "RIGHT"
        if dy > 0.62:
            return "DOWN"
        if dy < 0.30:
            return "UP"
        return "CENTER"
    except Exception:
        return "UNKNOWN"


class FaceMonitor:
    """Background camera loop: tracking every frame, identity ~1/s.

    The camera only ever opens after explicit camera permission + a feature
    toggle, and `status()` always reports whether it is live (the UI shows a
    permanent indicator while it is).
    """

    def __init__(self, engine: FaceEngine, event_cb=None):
        self.engine = engine
        self.event_cb = event_cb or (lambda kind, data: None)
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._frame_lock = threading.Lock()
        self._latest_frame = None
        self._latest_jpeg: bytes | None = None
        # live status (read by UI / manager)
        self.camera_status = "off"          # off | active | disconnected | error
        self.face_present = False
        self.authorized_present = False
        self.unknown_present = False
        self.head = "—"
        self.movement = "STILL"
        self.last_authorized_seen = 0.0
        self.last_face_seen = 0.0
        self.error = ""
        # registration
        self._reg_target = 0
        self._reg_samples: list[np.ndarray] = []
        self._reg_cb = None
        self._prev_centroid = None
        self._last_recog = 0.0

    # ── lifecycle ────────────────────────────────────────────────────────────

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.running:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="FaceMonitor",
                                        daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=3.0)
        self._thread = None
        self.camera_status = "off"
        self.face_present = self.authorized_present = self.unknown_present = False
        with self._frame_lock:
            self._latest_frame = None
            self._latest_jpeg = None

    def latest_jpeg(self) -> bytes | None:
        with self._frame_lock:
            return self._latest_jpeg

    def status(self) -> dict:
        return {
            "camera_status": self.camera_status,
            "camera_active": self.camera_status == "active",
            "face_present": self.face_present,
            "authorized_present": self.authorized_present,
            "unknown_present": self.unknown_present,
            "head_direction": self.head,
            "movement": self.movement,
            "last_authorized_seen": self.last_authorized_seen,
            "error": self.error,
        }

    # ── registration ─────────────────────────────────────────────────────────

    def begin_registration(self, callback, samples: int = 12) -> None:
        """Collect identity samples while the monitor runs. cb(done, total, templates|None)."""
        if not self.running:
            callback(0, samples, None, "Camera monitor is not running.")
            return
        self._reg_samples = []
        self._reg_target = samples
        self._reg_cb = callback

    def cancel_registration(self) -> None:
        self._reg_target = 0
        self._reg_cb = None
        self._reg_samples = []

    @property
    def registering(self) -> bool:
        return self._reg_target > 0

    # ── main loop ────────────────────────────────────────────────────────────

    def _emit(self, kind: str, data: dict) -> None:
        try:
            self.event_cb(kind, data)
        except Exception:
            pass

    def _open_capture(self):
        idx = int(config.get("camera_index") or 0)
        backend = cv2.CAP_DSHOW if os.name == "nt" else cv2.CAP_ANY
        cap = cv2.VideoCapture(idx, backend)
        if cap.isOpened():
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        return cap

    def _run(self) -> None:
        cap = None
        fail_reads = 0
        prev_authorized = False
        prev_unknown = False
        try:
            while not self._stop.is_set():
                settings = config.load_settings()
                fps = max(1, min(30, int(settings.get("face_monitor_fps", 8))))
                interval = 1.0 / fps
                recog_on = bool(settings.get("face_recognition_enabled"))
                templates = []
                if recog_on:
                    from . import storage
                    blob = storage.load_blob("face") or {}
                    templates = blob.get("templates") or []
                threshold = float(settings.get("face_match_threshold", 0.40))

                if cap is None or not cap.isOpened():
                    cap = self._open_capture()
                    if not cap.isOpened():
                        if self.camera_status != "disconnected":
                            self.camera_status = "disconnected"
                            self.error = f"Camera {settings.get('camera_index')} unavailable."
                            self._emit("camera_disconnected", {})
                        self.face_present = False
                        self.authorized_present = False
                        cap = None
                        self._stop.wait(5.0)
                        continue
                    fail_reads = 0
                    self.camera_status = "active"
                    self.error = ""
                    self._emit("camera_active", {})

                t0 = time.monotonic()
                ret, frame = cap.read()
                if not ret or frame is None:
                    fail_reads += 1
                    if fail_reads >= 10:
                        try:
                            cap.release()
                        except Exception:
                            pass
                        cap = None
                    self._stop.wait(interval)
                    continue
                fail_reads = 0

                try:
                    faces = self.engine.detect(frame)
                except Exception as e:
                    self.camera_status = "error"
                    self.error = str(e)
                    self._emit("face_error", {"error": str(e)})
                    self._stop.wait(5.0)
                    continue

                now = time.time()
                self.face_present = bool(faces)
                if faces:
                    self.last_face_seen = now
                    face = max(faces, key=lambda f: f[2] * f[3])
                    # tracking: head pose + movement
                    self.head = head_direction(face)
                    centroid = (float(face[0] + face[2] / 2),
                                float(face[1] + face[3] / 2))
                    if self._prev_centroid is not None:
                        d = np.hypot(centroid[0] - self._prev_centroid[0],
                                     centroid[1] - self._prev_centroid[1])
                        self.movement = "MOVING" if d > 6.0 else "STILL"
                    self._prev_centroid = centroid

                    # recognition (separate cadence from tracking)
                    if recog_on and (now - self._last_recog) >= 0.8:
                        self._last_recog = now
                        try:
                            emb = self.engine.embed(frame, face)
                            if self.registering:
                                self._reg_samples.append(emb)
                                cb = self._reg_cb
                                if cb:
                                    if len(self._reg_samples) >= self._reg_target:
                                        tpl = [e.tolist() for e in self._reg_samples]
                                        total = self._reg_target
                                        self.cancel_registration()
                                        cb(total, total, tpl, "")
                                    else:
                                        cb(len(self._reg_samples), self._reg_target, None, "")
                            if templates:
                                ok, score = self.engine.match(emb, templates, threshold)
                                self.authorized_present = ok
                                self.unknown_present = not ok
                                if ok:
                                    self.last_authorized_seen = now
                            else:
                                self.authorized_present = False
                                self.unknown_present = False
                        except Exception as e:
                            self.error = f"recognition: {e}"
                    elif not recog_on:
                        self.authorized_present = False
                        self.unknown_present = False
                else:
                    self._prev_centroid = None
                    self.authorized_present = False
                    self.unknown_present = False
                    self.movement = "—"

                if self.authorized_present != prev_authorized:
                    prev_authorized = self.authorized_present
                    self._emit("authorized_present" if prev_authorized
                               else "authorized_absent", {})
                if self.unknown_present and not prev_unknown:
                    self._emit("unknown_person", {})
                prev_unknown = self.unknown_present

                with self._frame_lock:
                    self._latest_frame = frame
                    ok, buf = cv2.imencode(".jpg", frame,
                                           [cv2.IMWRITE_JPEG_QUALITY, 70])
                    self._latest_jpeg = buf.tobytes() if ok else None

                elapsed = time.monotonic() - t0
                self._stop.wait(max(0.01, interval - elapsed))
        except Exception as e:
            self.camera_status = "error"
            self.error = str(e)
            self._emit("face_error", {"error": str(e)})
        finally:
            if cap is not None:
                try:
                    cap.release()
                except Exception:
                    pass
            self.camera_status = "off"