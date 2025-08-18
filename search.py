# search.py  (renamed from player.py so gui can `import search`)
import os
import re
import sys
import time
from pathlib import Path

MUSIC_DIR = Path(__file__).resolve().parent / "music"
MUSIC_DIR.mkdir(parents=True, exist_ok=True)

# NOTE: If the GUI (PlaybackService) is responsible for playback,
# you can remove VLC entirely from this module. Keeping it here
# only for the CLI/back-compat `search_and_play`.
try:
    import vlc
except Exception:
    vlc = None


def _normalize(s: str) -> str:
    s = s.strip().lower()
    s = re.sub(r"\s+", " ", s)
    return s


def _candidate_audio_files():
    exts = {".m4a", ".webm", ".mp4", ".mp3", ".opus"}
    for p in MUSIC_DIR.iterdir():
        if p.is_file() and p.suffix.lower() in exts:
            yield p


def _find_local_match(song_name: str) -> Path | None:
    q = _normalize(song_name)

    # Exact (normalized) stem match first
    for path in _candidate_audio_files():
        stem_norm = _normalize(path.stem)
        if stem_norm == q:
            return path

    # Fallback: substring either way
    for path in _candidate_audio_files():
        stem_norm = _normalize(path.stem)
        if q in stem_norm or stem_norm in q:
            return path

    return None


def exists_in_library(song_name: str) -> bool:
    return _find_local_match(song_name) is not None


def fetch_with_fetcher(song_name: str) -> Path:
    """
    Call your downloader. Assumes fetcher.make_yt_search returns a string path.
    """
    import fetcher
    result = fetcher.make_yt_search(song_name)
    if not result:
        raise RuntimeError("Fetcher did not return a file path.")
    return Path(result)


# ---------- NEW: pure resolve method (no playback) ----------
def download_youtube_video(url_or_query, output_dir="videos", filename=None):
    import yt_dlp
    import os

    os.makedirs(output_dir, exist_ok=True)
    outtmpl = os.path.join(output_dir, "%(title)s.%(ext)s")
    if filename:
        outtmpl = os.path.join(output_dir, filename)

    ydl_opts = {
        "format": "best[ext=mp4]/best",  # Only download mp4 if available, else best available
        "outtmpl": outtmpl,
        "noplaylist": True,
        "quiet": False,
        "restrictfilenames": True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        result = ydl.download([url_or_query])
    return outtmpl  # Returns the intended output path

def find_or_download(song_name: str) -> Path:
    """
    Return a local Path for `song_name`. If not present, download it.
    DOES NOT play the file. This is what the GUI should call.
    """
    local = _find_local_match(song_name)
    if local:
        return local

    downloaded = fetch_with_fetcher(song_name)
    return downloaded

def find_or_download_in_playlist(playlist_name: str, song_name: str) -> Path:
    """
    Like find_or_download(), but operates entirely within
    playlists/<playlist_name>/ instead of MUSIC_DIR.

    Creates the folder if needed, searches there, and downloads
    into it if not found.
    """
    # Base playlists dir
    playlists_dir = Path(__file__).resolve().parent / "playlists"
    playlists_dir.mkdir(parents=True, exist_ok=True)

    # Specific playlist folder
    playlist_dir = playlists_dir / playlist_name
    playlist_dir.mkdir(parents=True, exist_ok=True)

    # Local search in this playlist only
    def _candidate_audio_files_in_playlist():
        exts = {".m4a", ".webm", ".mp4", ".mp3", ".opus"}
        for p in playlist_dir.iterdir():
            if p.is_file() and p.suffix.lower() in exts:
                yield p

    def _find_local_match_in_playlist():
        q = _normalize(song_name)
        # Exact match
        for path in _candidate_audio_files_in_playlist():
            if _normalize(path.stem) == q:
                return path
        # Fallback substring match
        for path in _candidate_audio_files_in_playlist():
            stem_norm = _normalize(path.stem)
            if q in stem_norm or stem_norm in q:
                return path
        return None

    # Try to find locally
    local = _find_local_match_in_playlist()
    if local:
        return local

    # Download into this playlist folder
    downloaded = fetch_with_fetcher(song_name)
    # Move it into the playlist folder if needed
    downloaded = Path(downloaded)
    target_path = playlist_dir / downloaded.name
    if downloaded.resolve() != target_path.resolve():
        downloaded.replace(target_path)
    return target_path


# ---------- Optional: CLI/back-compat that also plays ----------
def _play_file_direct(path: Path) -> None:
    """
    Minimal built-in playback for CLI use only.
    GUI should use PlaybackService instead.
    """
    path = path.resolve()
    if not path.exists():
        raise FileNotFoundError(path)

    if vlc is not None:
        try:
            instance = vlc.Instance("--no-video")
            player = instance.media_player_new()
            media = instance.media_new(str(path))
            player.set_media(media)
            print(f"Playing: {path.name}")
            player.play()
            time.sleep(0.5)
            while True:
                state = player.get_state()
                if state in (vlc.State.Ended, vlc.State.Stopped, vlc.State.Error):
                    break
                time.sleep(0.2)
            return
        except Exception as e:
            print(f"[search] VLC failed ({e}). Falling back to OS default…")

    # Fallback: OS default
    print(f"Opening with system player: {path.name}")
    if sys.platform.startswith("win"):
        os.startfile(str(path))  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        os.spawnlp(os.P_NOWAIT, "open", "open", str(path))
    else:
        os.spawnlp(os.P_NOWAIT, "xdg-open", "xdg-open", str(path))


def search_and_play(song_name: str) -> Path:
    """
    Legacy convenience: resolve (find or download) then play.
    Useful for command-line tests.
    """
    path = find_or_download(song_name)
    print(f"Resolved: {path}")
    _play_file_direct(path)
    return path


if __name__ == "__main__":
    song_query = input("What song do you want to listen to? ").strip()
    if not song_query:
        print("No song entered. Exiting.")
        sys.exit(0)
    search_and_play(song_query)
