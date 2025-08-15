#!/usr/bin/env python3
"""
Lightweight playback wrapper around python-vlc (libVLC).

Features:
- play / pause / resume / stop
- seek (seconds)
- set/get volume (0.0..1.0)
- get_position() -> (current_sec, total_sec)
- is_playing()
- end-of-track callback (on_finished)

Portable VLC (Windows):
- Pass vlc_dir=Path("tools/vlc") if you keep VLC next to your app.
"""

from __future__ import annotations
import os
import sys
import threading
import time
from pathlib import Path
from typing import Callable, Optional

# Optional: point to a portable VLC folder on Windows (e.g., tools/vlc/)
# Otherwise, leave vlc_dir=None and use a regular VLC install.
def _prep_portable_vlc(vlc_dir: Optional[Path]) -> None:
    if vlc_dir is None:
        return
    vlc_dir = Path(vlc_dir).resolve()
    if os.name == "nt":
        # Make libvlc.dll discoverable
        if hasattr(os, "add_dll_directory"):
            os.add_dll_directory(str(vlc_dir))
        # Let VLC find its decoders
        os.environ["VLC_PLUGIN_PATH"] = str(vlc_dir / "plugins")

class PlaybackService:
    def __init__(self, vlc_dir: Optional[Path] = None) -> None:
        """
        vlc_dir: path to a portable VLC folder (contains libvlc.dll, plugins/)
                 e.g., Path("tools/vlc"). If None, uses system VLC.
        """
        _prep_portable_vlc(vlc_dir)

        try:
            import vlc  # lazy import so env is set first
        except Exception as e:
            raise RuntimeError(
                "Failed to import python-vlc. Did you `pip install python-vlc` "
                "and have VLC available (portable or system)?"
            ) from e

        self._vlc = vlc
        # If using portable, reinforce plugin-path
        inst_args = ["--no-video"]
        if vlc_dir is not None:
            inst_args.append(f"--plugin-path={Path(vlc_dir) / 'plugins'}")

        self._instance = vlc.Instance(*inst_args)
        self._player = self._instance.media_player_new()
        self._lock = threading.RLock()

        self._on_finished: Optional[Callable[[], None]] = None
        em = self._player.event_manager()
        em.event_attach(vlc.EventType.MediaPlayerEndReached, self._handle_end)
        em.event_attach(vlc.EventType.MediaPlayerEncounteredError, self._handle_error)

    # ---------- Public API ----------

    def play(self, path: str | Path) -> None:
        """Start playing the given file path."""
        with self._lock:
            p = str(Path(path).resolve())
            media = self._instance.media_new(p)
            self._player.set_media(media)
            self._player.play()

    def pause(self) -> None:
        """Pause if playing; no-op if already paused/stopped."""
        with self._lock:
            # pause() toggles; set_pause(True) is explicit
            self._player.set_pause(True)

    def resume(self) -> None:
        """Resume if paused; no-op if already playing."""
        with self._lock:
            self._player.set_pause(False)

    def stop(self) -> None:
        with self._lock:
            self._player.stop()

    def seek(self, seconds: float) -> None:
        """Seek to absolute position (seconds)."""
        with self._lock:
            self._player.set_time(int(max(0.0, seconds) * 1000))

    def set_volume(self, vol01: float) -> None:
        """Set volume in [0.0, 1.0]."""
        with self._lock:
            v = int(max(0.0, min(1.0, vol01)) * 100)
            self._player.audio_set_volume(v)

    def get_volume(self) -> float:
        with self._lock:
            v = self._player.audio_get_volume()  # 0..100 or -1
            return 0.0 if v < 0 else float(v) / 100.0

    def get_position(self) -> tuple[float, float]:
        """
        Returns (current_sec, total_sec). If unknown, total_sec may be 0.0.
        """
        with self._lock:
            cur_ms = self._player.get_time()      # -1 if unknown
            tot_ms = self._player.get_length()    # -1 if unknown
            cur = 0.0 if cur_ms is None or cur_ms < 0 else cur_ms / 1000.0
            tot = 0.0 if tot_ms is None or tot_ms < 0 else tot_ms / 1000.0
            return (cur, tot)

    def is_playing(self) -> bool:
        with self._lock:
            return bool(self._player.is_playing())

    def get_state(self) -> str:
        with self._lock:
            st = self._player.get_state()
            return str(st)

    def on_finished(self, callback: Optional[Callable[[], None]]) -> None:
        """
        Register a callback called when the current track ends normally.
        Pass None to clear.
        """
        with self._lock:
            self._on_finished = callback

    # ---------- Internal event handlers ----------

    def _handle_end(self, event) -> None:  # event is a vlc.Event
        cb = None
        with self._lock:
            cb = self._on_finished
        if cb:
            try:
                cb()
            except Exception:
                # don't crash the player on user callback errors
                pass

    def _handle_error(self, event) -> None:
        # You can expand this to log or surface errors in your UI
        pass


# ---------- Ad-hoc CLI test ----------
if __name__ == "__main__":
    """
    Quick manual test:
    python playback_service.py "path/to/song.m4a"
    """
    if len(sys.argv) < 2:
        print("Usage: python playback_service.py <audio-file>")
        sys.exit(0)

    audio = Path(sys.argv[1])
    if not audio.exists():
        print(f"File not found: {audio}")
        sys.exit(1)

    # Example: use portable VLC under tools/vlc (Windows)
    # svc = PlaybackService(vlc_dir=Path(__file__).parent / "tools" / "vlc")
    svc = PlaybackService()

    def finished():
        print("\n[Playback finished]")
        os._exit(0)  # end the test process

    svc.on_finished(finished)
    svc.set_volume(0.9)
    svc.play(audio)

    # Simple progress ticker for the test (ctrl+c to stop)
    try:
        while True:
            cur, tot = svc.get_position()
            if tot > 0:
                print(f"\r{cur:6.1f}/{tot:6.1f} sec   ", end="", flush=True)
            time.sleep(0.2)
    except KeyboardInterrupt:
        svc.stop()
        print("\nStopped.")
