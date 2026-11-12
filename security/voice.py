"""Local speaker verification (voice identity, NOT speech-to-text).

Speech recognition stays exactly as it was (Gemini / Whisper / Vosk).  This
module answers a different question: "is the person speaking the enrolled
user?"  It computes a compact speaker embedding from log-mel MFCC statistics
with numpy only — no cloud, no extra dependency.

Pipeline:
  mic PCM (16 kHz int16) → non-blocking ring feed → worker thread →
  energy VAD → log-mel spectral shape + CMN mel/MFCC stats + pitch deviation
  → L2-normalised vector → cosine similarity vs enrolled templates (max over
  templates, slow adaptive update on high-confidence matches).

Voice alone is never accepted for sensitive operations — the privacy manager
always combines it with face presence or the PIN backup.
"""
from __future__ import annotations

import queue
import threading
import time

import numpy as np

from . import config, storage

_SR = 16000
_FRAME = 400          # 25 ms
_HOP = 160            # 10 ms
_NFFT = 512
_MELS = 26
_NMFCC = 13
_SEGMENT_SECONDS = 1.6
_VERIFY_SECONDS = 0.8   # verification must keep up with short spoken commands
_MAX_QUEUE = 40       # ~2.5 s of 1024-sample chunks; overflow is dropped


def _mel_filterbank() -> np.ndarray:
    def hz2mel(f):
        return 2595.0 * np.log10(1.0 + f / 700.0)

    def mel2hz(m):
        return 700.0 * (10.0 ** (m / 2595.0) - 1.0)

    pts = np.linspace(hz2mel(80), hz2mel(_SR / 2 - 100), _MELS + 2)
    bins = np.floor((_NFFT + 1) * mel2hz(pts) / _SR).astype(int)
    fb = np.zeros((_MELS, _NFFT // 2 + 1))
    for i in range(_MELS):
        l, c, r = bins[i], bins[i + 1], bins[i + 2]
        if c > l:
            fb[i, l:c] = (np.arange(l, c) - l) / (c - l)
        if r > c:
            fb[i, c:r] = (r - np.arange(c, r)) / (r - c)
    return fb


def _dct_matrix() -> np.ndarray:
    n = np.arange(_MELS)
    k = np.arange(_NMFCC)
    return np.cos(np.pi * k[:, None] * (2 * n[None, :] + 1) / (2 * _MELS))


_FB = None
_DCT = None
_WIN = np.hamming(_FRAME)


def speaker_embedding(pcm: np.ndarray) -> np.ndarray | None:
    """pcm: float32 [-1,1] mono 16 kHz. Returns unit-norm embedding or None.

    Features: per-frame level-normalised log-mel shape (the vocal-tract /
    formant envelope — the primary speaker cue) + time-CMN log-mel and MFCC
    statistics (articulation dynamics) + pitch deviation from a 160 Hz
    reference (x3). Measured on formant-differentiated synthetic speakers:
    same 0.99–1.0, different vocal tract ~0.15, volume-invariant.
    """
    global _FB, _DCT
    if _FB is None:
        _FB = _mel_filterbank()
        _DCT = _dct_matrix()
    x = np.asarray(pcm, dtype=np.float32).flatten()
    if x.size < _FRAME * 8:
        return None
    x = np.append(x[0], x[1:] - 0.97 * x[:-1])          # pre-emphasis
    n_frames = 1 + (x.size - _FRAME) // _HOP
    idx = (np.arange(_FRAME)[None, :] + _HOP * np.arange(n_frames)[:, None])
    frames = x[idx] * _WIN
    energy = np.mean(frames * frames, axis=1)
    # energy VAD: keep frames above 25% of the segment's 90th-percentile energy
    thr = 0.25 * np.percentile(energy, 90)
    keep = energy > max(thr, 1e-7)
    voiced = frames[keep]
    if voiced.shape[0] < 20:
        return None
    spec = np.abs(np.fft.rfft(voiced, _NFFT)) ** 2 / _NFFT
    mel = np.log(spec @ _FB.T + 1e-10)
    # Static vocal-tract shape: per-FRAME level normalisation (removes
    # loudness, keeps formant envelope). Time-CMN alone erased this — the
    # actual speaker cue — and every stationary voice looked identical.
    shape = mel - mel.mean(axis=1, keepdims=True)
    meln = mel - mel.mean(axis=0)                        # channel/level norm
    mfcc = (meln @ _DCT.T)[:, 1:]                        # drop c0 (loudness)
    # pitch (80–400 Hz) via per-frame autocorrelation, every 3rd voiced frame
    lo, hi = _SR // 400, _SR // 80
    pitches = []
    for f in voiced[::3]:
        ac = np.correlate(f, f, "full")[_FRAME - 1:]
        if ac[0] <= 0:
            continue
        seg = ac[lo:hi]
        if seg.size and seg.max() > 0.3 * ac[0]:
            pitches.append(np.log(_SR / (lo + int(seg.argmax()))))
    # Deviations from a neutral reference, NOT raw magnitudes: raw log-pitch
    # is ~4.6 for every voiced speaker, and after x3 weighting it dominated
    # the vector's norm — every speaker scored ~0.99 against every other.
    if pitches:
        p = np.asarray(pitches)
        pitch_mean = float(p.mean()) - float(np.log(_SR / 160.0))
        pitch_std = float(p.std()) - 0.15
    else:
        pitch_mean, pitch_std = 0.0, 0.0
    feat = np.concatenate([
        shape.mean(axis=0), shape.std(axis=0),
        meln.mean(axis=0), meln.std(axis=0),
        mfcc.mean(axis=0), mfcc.std(axis=0),
        [3.0 * pitch_mean, 3.0 * pitch_std, float(keep.mean()) - 0.5],
    ])
    norm = np.linalg.norm(feat)
    return feat / norm if norm > 0 else None


def similarity(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b))    # both unit-norm


class VoiceVerifier:
    """Fed from the mic callback; all work happens on its own thread."""

    def __init__(self, event_cb=None):
        self.event_cb = event_cb or (lambda kind, data: None)
        self._q: queue.Queue = queue.Queue(maxsize=_MAX_QUEUE)
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self.verified = False
        self.last_verified = 0.0
        self.last_score = 0.0
        self.error = ""
        # registration
        self._reg_target = 0
        self._reg_samples: list[np.ndarray] = []
        self._reg_cb = None

    # ── lifecycle ────────────────────────────────────────────────────────────

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.running:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="VoiceVerifier",
                                        daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        self._thread = None
        self.verified = False

    def feed(self, indata) -> None:
        """NON-BLOCKING mic tap — a queue push only, like the wake detector."""
        try:
            self._q.put_nowait(np.asarray(indata, dtype=np.int16).copy())
        except queue.Full:
            pass
        except Exception:
            pass

    # ── registration ─────────────────────────────────────────────────────────

    @property
    def enrolling(self) -> bool:
        return self._reg_target > 0

    def begin_enrollment(self, callback, segments: int = 4) -> None:
        """Ask the user to speak naturally; collect `segments` voice samples.
        cb(done, total, templates|None, message)."""
        if not storage.has_blob("voice") and not self.running:
            self.start()
        self._reg_samples = []
        self._reg_target = segments
        self._reg_cb = callback
        if callback:
            callback(0, segments, None, "Speak naturally for a few seconds…")

    def cancel_enrollment(self) -> None:
        self._reg_target = 0
        self._reg_cb = None
        self._reg_samples = []

    @staticmethod
    def enrolled() -> bool:
        return storage.has_blob("voice")

    def status(self) -> dict:
        ttl = float(config.get("voice_verify_ttl_seconds"))
        live = self.verified and (time.time() - self.last_verified) < ttl
        return {
            "enrolled": self.enrolled(),
            "verified": live,
            "last_score": round(self.last_score, 3),
            "last_verified": self.last_verified,
            "enrolling": self.enrolling,
            "error": self.error,
        }

    # ── worker ───────────────────────────────────────────────────────────────

    def _emit(self, kind, data):
        try:
            self.event_cb(kind, data)
        except Exception:
            pass

    def _run(self) -> None:
        buf = np.zeros(0, dtype=np.float32)
        max_buf = int(_SEGMENT_SECONDS * _SR) * 4
        last_process = 0.0
        while not self._stop.is_set():
            try:
                chunk = self._q.get(timeout=0.5)
            except queue.Empty:
                # decay: verification expires silently via TTL in status()
                if buf.size and time.monotonic() - last_process > 3.0:
                    buf = np.zeros(0, dtype=np.float32)
                continue
            buf = np.concatenate([buf, chunk.astype(np.float32).flatten() / 32768.0])
            if buf.size > max_buf:
                buf = buf[-max_buf:]
            need = int((_SEGMENT_SECONDS if self.enrolling else _VERIFY_SECONDS) * _SR)
            if buf.size < need:
                continue
            last_process = time.monotonic()
            segment, buf = buf[:need], buf[need:]
            try:
                self._process_segment(segment)
            except Exception as e:
                self.error = str(e)

    def _process_segment(self, segment: np.ndarray) -> None:
        emb = speaker_embedding(segment)
        if emb is None:
            return                                   # silence, not a speaker
        settings = config.load_settings()
        threshold = float(settings.get("voice_match_threshold"))
        unauth_below = float(settings.get("voice_unauthorized_below"))

        if self.enrolling:
            self._reg_samples.append(emb)
            cb = self._reg_cb
            if cb:
                if len(self._reg_samples) >= self._reg_target:
                    tpl = [e.tolist() for e in self._reg_samples]
                    total = self._reg_target
                    self.cancel_enrollment()
                    cb(total, total, tpl, "")
                else:
                    cb(len(self._reg_samples), self._reg_target, None,
                       "Good — keep speaking naturally…")
            return

        blob = storage.load_blob("voice") or {}
        templates = [np.asarray(t, dtype=np.float32)
                     for t in blob.get("templates") or []]
        if not templates:
            return
        scores = [similarity(emb, t) for t in templates]
        best = max(scores)
        self.last_score = best
        was = self.verified
        if best >= threshold:
            self.verified = True
            self.last_verified = time.time()
            # slow adaptive update of the closest template (voice drift)
            i = int(np.argmax(scores))
            updated = 0.95 * templates[i] + 0.05 * emb
            n = np.linalg.norm(updated)
            if n > 0:
                templates[i] = updated / n
                blob["templates"] = [t.tolist() for t in templates]
                storage.save_blob("voice", blob)
            if not was:
                self._emit("voice_verified", {"score": best})
        else:
            ttl = float(settings.get("voice_verify_ttl_seconds"))
            if time.time() - self.last_verified > ttl:
                if self.verified:
                    self._emit("voice_expired", {})
                self.verified = False
            if best < unauth_below:
                self._emit("unauthorized_voice", {"score": best})