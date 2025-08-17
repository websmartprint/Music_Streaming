# fetcher.py
import yt_dlp
import os

#Downloads audio only, as .m4a or webm using youtube-dl
#Returns full path as a string to the saved auido file
#takes the url or query (as per youtube-dl peramaters) as  string, the output folder name as a string,
#prefernce for the m4a filetype (bool), and a the option for a custom filename
#If no output directroy is specified it will be saved to the music folder, if non exists it will create one
#If no filename is specified, it will use youtube-dl's given name (usually just the youtube video name)
def download_youtube_audio(url_or_query, output_dir="music", prefer_m4a=True, filename=None):

    os.makedirs(output_dir, exist_ok=True)

    # Prefer AAC in .m4a if available; else fall back to any bestaudio
    fmt = "bestaudio[ext=m4a]/bestaudio[ext=mp4]/bestaudio/best" if prefer_m4a else "bestaudio/best"

    #Check directory
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
        #Returns path as a string
        return final_path  

#Cleans up the song name so it diaplys more nicely in the GUI
#Replaces spaces with underscores, removes leading and trailing spaces
def clean_song_name(song_name: str) -> str:
    return song_name.strip().replace(" ", "_")

def make_yt_search(song_name):
    # Return the path so player.py can use it
    #Crurrently accepts only name search, should modify to take link and name

    if "http" in song_name:
        return download_youtube_audio(song_name, output_dir="music", prefer_m4a=True)

    return download_youtube_audio('ytsearch1:' + song_name.strip(), output_dir="music", prefer_m4a=True)# filename=song_name) <--- removed this, older version had filename as search query, not its the video name
