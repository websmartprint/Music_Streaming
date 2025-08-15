# fetcher.py
import yt_dlp
import os

def download_youtube_audio(url_or_query, output_dir="music", prefer_m4a=True, filename=None):
    """
    Download audio-only stream using yt-dlp.
    - No ffmpeg required (no conversion).
    - Result ext is usually .m4a (AAC) or .webm (Opus).
    Returns the FULL PATH (string) to the downloaded file.
    """
    os.makedirs(output_dir, exist_ok=True)

    # Prefer AAC in .m4a if available; else fall back to any bestaudio
    fmt = "bestaudio[ext=m4a]/bestaudio[ext=mp4]/bestaudio/best" if prefer_m4a else "bestaudio/best"

    outtmpl = os.path.join(output_dir, "%(title)s.%(ext)s")
    if filename:
        outtmpl = os.path.join(output_dir, f"{filename}.%(ext)s")

    ydl_opts = {
        "format": fmt,
        "outtmpl": outtmpl,
        "noplaylist": True,
        "quiet": False,
        "restrictfilenames": True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url_or_query, download=True)

        # If a search/playlist was used, pick the first entry
        if isinstance(info, dict) and "entries" in info and info["entries"]:
            info = info["entries"][0]

        # Best source of truth for the final file path:
        final_path = None
        try:
            # Newer yt-dlp returns requested_downloads with finalized filepaths
            final_path = info["requested_downloads"][0]["filepath"]
        except Exception:
            # Fallback 1: prepare_filename (may show .NA sometimes)
            try:
                final_path = ydl.prepare_filename(info)
            except Exception:
                final_path = None

        # Fallback 2: try to locate by our chosen base name (if provided)
        if (not final_path or final_path.endswith(".NA")) and filename:
            base = os.path.join(output_dir, filename)
            for ext in ("m4a", "webm", "mp3", "mp4", "opus"):
                cand = f"{base}.{ext}"
                if os.path.exists(cand):
                    final_path = cand
                    break

        # Last resort: newest audio-ish file in output_dir
        if not final_path or not os.path.exists(final_path):
            candidates = [
                os.path.join(output_dir, f)
                for f in os.listdir(output_dir)
                if f.lower().endswith((".m4a", ".webm", ".mp3", ".mp4", ".opus"))
            ]
            if candidates:
                candidates.sort(key=lambda p: os.path.getmtime(p), reverse=True)
                final_path = candidates[0]

        print(f"Downloaded audio: {final_path}")
        return final_path  # <- return a string path

def make_yt_search(song_name):
    # Return the path so player.py can use it
    return download_youtube_audio('ytsearch1:' + song_name.strip(),
                                  output_dir="music",
                                  filename=song_name)
