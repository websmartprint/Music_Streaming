import os, sys
from pathlib import Path

if getattr(sys, 'frozen', False):
    # Running from bundled exe
    base_dir = Path(sys._MEIPASS)
else:
    # Running in normal Python
    base_dir = Path(__file__).parent

vlc_dir = base_dir / "third_party" / "vlc-3.0.21-win64" / "vlc-3.0.21"
os.environ["PYTHON_VLC_LIB_PATH"] = str(vlc_dir / "libvlc.dll")
if os.name == "nt" and hasattr(os, "add_dll_directory"):
    os.add_dll_directory(str(vlc_dir))
    os.add_dll_directory(str(vlc_dir / "plugins"))
os.environ.setdefault("VLC_PLUGIN_PATH", str(vlc_dir / "plugins"))
# ---- end VLC bootstrap ----

import sys, threading, traceback
from pathlib import Path
import customtkinter as ctk
from tkinter import messagebox
import tkinter as tk
import random


# Local imports
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    import search  # must expose find_or_download(query) -> Path
except Exception:
    print("Failed to import search.py. Ensure gui_ctk.py is next to search.py and fetcher.py.")
    raise

try:
    from playback_service import PlaybackService
except Exception:
    print("Failed to import playback_service.py. Put it next to gui_ctk.py, then `pip install python-vlc`.")
    raise

#Website themes
#Control website colorscheme, fonts, etc
#Use these for consitency
APP_NAME = "Fluss"
START_PAGE = "search"
INIT_GEOMETRY = "900x360"
INIT_MINISIZE_X = 760
INIT_MINISIZE_Y = 320
# Main color of website
ACCENT = "#B34A5A"
#lighter acent for active elements        
ACCENT_HOVER = "#C65D6C"
# near-black background
BG = "#0E0E0E"
# panels / rows            
CARD_BG = "#181818"
#Text color       
TEXT = "#FFFFFF"
#For "deactivated" elemnts
TEXT_MUTED = "#B3B3B3"
# default font for labels, buttons, etc.
FONT = "Segoe UI"
#Unused, need to implement, universal font sizes for consistency
SMALL_TEXT = 12
MED_TITLE = 40
LARGE_TITLE = 80  

#Set window theme to match apps dark theme
ctk.set_appearance_mode("dark")

#customtkinter has no gradient function, this helper creates the gradient
#function used in the titlecards of the app
def paint_vertical_gradient(canvas: tk.Canvas, color1: str, color2: str):
    canvas.delete("all")
    w, h = int(canvas.winfo_width()), int(canvas.winfo_height())
    if w <= 0 or h <= 0:
        return
    r1, g1, b1 = canvas.winfo_rgb(color1)
    r2, g2, b2 = canvas.winfo_rgb(color2)
    dr = (r2 - r1) / max(1, h)
    dg = (g2 - g1) / max(1, h)
    db = (b2 - b1) / max(1, h)
    for y in range(h):
        rr = int(r1 + dr * y) // 256
        gg = int(g1 + dg * y) // 256
        bb = int(b1 + db * y) // 256
        canvas.create_line(0, y, w, y, fill=f"#{rr:02x}{gg:02x}{bb:02x}")

#Main app graphics body, this controls all the visual and interactable elements, all later classes are utilized here
#Structure its that the left Menu and the bottom music bar+controls are always on display
#The remaining space is a 3x3 grid which can be used to "sink" or "raise" different windows
# e.g. the playlists tab, search, playlist creation, etc. This is how you navigate different pages
# These swappable pages are the later declared classes  
class MusicGUI(ctk.CTk):
    def __init__(self):
        super().__init__()
        vlc_dir = Path(__file__).parent / "third_party" / "vlc-3.0.21-win64" / "vlc-3.0.21"
        self.player = PlaybackService(vlc_dir=vlc_dir)
        self.title(APP_NAME)
        self.geometry(INIT_GEOMETRY)
        self.minsize(INIT_MINISIZE_X, INIT_MINISIZE_Y)
        self.configure(fg_color=BG)

        #self.player = PlaybackService()

        # Play queue states used for playing a plylist
        #playlist queue is a list of filepaths to play
        self.play_queue: list[Path] = []
        #Queue index is used to cycle through the queue list
        #starts at -1 since each call of playlist advances by 1, including first call
        self.queue_index: int = -1
        #Shuffle mode is to save state between methods if we should iterate 
        #sequentially or randomly through playlist queue
        self.shuffle_mode: bool = False


        # More states 
        #current song path (used when not playing from a playlist, like from the search feature)
        self.current_path: Path | None = None
        #Is a song currently playing
        self.playing = False
        #Is the user moving the playbar cursor, helps not have conflict between drag and cursor advance
        self.user_dragging = False
        #keept track of current page
        self.current_page_key: str | None = None
        #maktes the page name to the class that actually creates page
        self.pages: dict[str, ctk.CTkFrame] = {}

        # 1) Layout frame/weights
        self._configure_grid()

        # 2) Build header/sidebar
        self._build_header()
        self._build_menu()

        # 3) Build footer (music bar) — this creates self.seek
        self._build_music_bar()
        self._build_playback_row()
        self._build_controls_row()
        self._build_status_line()

        # 4) Build page container + pages
        self._build_pages_container()
        self._build_pages()

        # 5) Now it’s safe to wire events; widgets exist
        self._wire_events()

        # 6) Start progress loop
        self._start_progress_loop()

    # Gradient helper (legacy, I dont think its used anymore)
    def _redraw_top_gradient(self):
        c = self.top_canvas
        c.delete("all")
        w = int(c.winfo_width()); h = int(c.winfo_height())
        if w <= 0 or h <= 0: return
        r1, g1, b1 = c.winfo_rgb(ACCENT)
        r2, g2, b2 = c.winfo_rgb(BG)
        dr = (r2 - r1) / max(1, h); dg = (g2 - g1) / max(1, h); db = (b2 - b1) / max(1, h)
        for y in range(h):
            rr = int(r1 + dr * y) // 256
            gg = int(g1 + dg * y) // 256
            bb = int(b1 + db * y) // 256
            c.create_line(0, y, w, y, fill=f"#{rr:02x}{gg:02x}{bb:02x}")

    # UI creation
    def _configure_grid(self):
        # 4 columns total: First is menure sidebar, rest is content [sidebar][content x3]
        self.grid_columnconfigure(0, weight=2)
        self.grid_columnconfigure(1, weight=4)
        self.grid_columnconfigure(2, weight=3)
        self.grid_columnconfigure(3, weight=4)
        # rows: Top will always be title, bottom will be player, middle three will be content
        #  Title | pages | pages | pages | Music player
        self.grid_rowconfigure(0, weight=0)
        self.grid_rowconfigure(1, weight=3)
        self.grid_rowconfigure(2, weight=3)
        self.grid_rowconfigure(3, weight=3)
        self.grid_rowconfigure(4, weight=0)

    # --------Filesystem playlists helpers--------

    def _playlists_root(self) -> Path:
        # ROOT should already be defined at module top
        root = ROOT / "playlists"
        # ensure it exists
        root.mkdir(parents=True, exist_ok=True) 
        return root

    def _list_playlists_fs(self) -> list[str]:
        root = self._playlists_root()
        names = [p.name for p in root.iterdir() if p.is_dir()]
        names.sort(key=str.casefold)
        return names

    #Refreshes playlist sidebar so that when a
    #new playlist is made it showes up in the sidebar menue
    def refresh_playlists_sidebar(self):
        for w in self.playlists_container.winfo_children():
            w.destroy()

        names = self._list_playlists_fs()
        if not names:
            lbl = ctk.CTkLabel(self.playlists_container, text="(no playlists yet)", text_color=TEXT_MUTED)
            lbl.pack(fill="x", padx=8, pady=(4, 8))
            return

        for name in names:
            b = ctk.CTkButton(
                self.playlists_container,
                text=name,
                command=lambda n=name: self.show_playlist(n),
                fg_color=CARD_BG, hover_color="#242424",
                text_color=TEXT, corner_radius=12, height=36
            )
            b.pack(fill="x", padx=8, pady=4)

    #Helps display the songs inside of a playlist
    #does this by going through the playlist and displaying all the filenames
    def show_playlist(self, name: str):
        key = f"playlist::{name}"
        page = self.pages.get(key)

        if page is None:
            # create page once, then reuse
            page = PlaylistViewPage(self.page_container, app=self, fg_color=BG)
            page.grid(row=0, column=0, sticky="nsew")
            self.pages[key] = page

        # (re)populate the list
        page.load_playlist(name)  
        self.show_page(key)

    # --------- PlaybackService helpers ---------
    def _play_path(self, path: Path):
        """Start playback of a single file."""
        self.current_path = path
        self.player.stop()
        self.player.play(path)
        self.playing = True
        self.pause_btn.configure(text="Pause")
        self.set_status(f"Playing: {path.name}")

    def _advance_queue(self):
        if not self.play_queue:
            return

        if getattr(self, "shuffle_mode", False):
            # pick a random index; avoid immediate repeat if >1 track
            if len(self.play_queue) > 1 and 0 <= self.queue_index < len(self.play_queue):
                prev = self.queue_index
                while True:
                    idx = random.randrange(len(self.play_queue))
                    if idx != prev:
                        break
                self.queue_index = idx
            else:
                self.queue_index = random.randrange(len(self.play_queue))
        else:
            self.queue_index += 1
            if self.queue_index >= len(self.play_queue):
                if getattr(self, "loop_list", True):
                    self.queue_index = 0
                    self.set_status("Queue reset.")
                else:
                    self.playing = False
                    self.current_path = None
                    self.set_status("Playlist finished.")
                    return

        self._play_path(self.play_queue[self.queue_index])

    def start_playlist_folder(self, folder: Path, shuffle_list=False, loop_list=True):
        """Build queue from a folder and start playing."""
        if not folder.exists() or not folder.is_dir():
            messagebox.showerror("Fluss", f"Folder not found:\n{folder}")
            return

        # collect playable files 
        exts = {".mp3", ".m4a", ".mp4", ".webm", ".opus", ".wav", ".flac"}
        files = sorted(
            [p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in exts],
            key=lambda p: p.name.casefold()
        )
        if not files:
            messagebox.showinfo("Fluss", "No audio files in that playlist folder.")
            return

        # load the queue and reset position
        self.play_queue = files
        self.queue_index = -1

        # remember modes
        self.shuffle_mode = bool(shuffle_list)
        self.loop_list   = bool(loop_list)

        # kick off first track
        self._advance_queue()




    # --------- Page container + pages (router) ----------
    def _build_pages_container(self):
        self.page_container = ctk.CTkFrame(self, fg_color=BG)
        self.page_container.grid(row=1, column=1, rowspan=3, columnspan=3,
                                 sticky="nsew", padx=18, pady=14)
        self.page_container.grid_rowconfigure(0, weight=1)
        self.page_container.grid_columnconfigure(0, weight=1)

    def _build_pages(self):
        self.pages = {
            "search":    SearchPage(self.page_container, app=self, fg_color=BG),
            "make playlist": MakePlayList(self.page_container, app=self, fg_color=BG),
            "library":   LibraryPage(self.page_container, app=self, fg_color=BG),
            "settings":  SettingsPage(self.page_container, app=self, fg_color=BG),
        }
        for p in self.pages.values():
            # stacked in same cell
            p.grid(row=0, column=0, sticky="nsew") 
        # default page
        self.show_page(START_PAGE) 

    def show_page(self, key: str):  
        #Raise the target page; call lifecycle hooks
        if key not in self.pages:
            return
        if self.current_page_key and self.current_page_key != key:
            prev = self.pages[self.current_page_key]
            if hasattr(prev, "on_hide"):
                prev.on_hide()
        page = self.pages[key]
        page.tkraise()
        if hasattr(page, "on_show"):
            page.on_show()
        self.current_page_key = key

    # --------- Header & side menu ----------
    def _build_header(self):
        self.header = ctk.CTkFrame(self, fg_color=CARD_BG, corner_radius=0, height=56)
        self.header.grid(row=0, column=0, columnspan=4, sticky="ew")
        self.header.grid_columnconfigure(0, weight=1)
        self.title_lbl = ctk.CTkLabel(self.header, text="Fluss",
                                      text_color=TEXT, font=(FONT, 18, "bold"))
        self.title_lbl.grid(row=0, column=0, sticky="w", padx=16, pady=12)

    def _build_menu(self):
        self.menu_frame = ctk.CTkFrame(self, fg_color=CARD_BG, corner_radius=12)
        self.menu_frame.grid(row=1, column=0, rowspan=4, sticky="nesw",
                            padx=(18, 6), pady=(14, 14))

        # Make the sidebar vertical layout:
        # row 0: static buttons
        # row 1: "Playlists" label
        # row 2: dynamic playlist buttons (in a simple frame)
        self.menu_frame.grid_rowconfigure(2, weight=1)  
        self.menu_frame.grid_columnconfigure(0, weight=1)

        # --- Static section ---
        static_box = ctk.CTkFrame(self.menu_frame, fg_color="transparent")
        static_box.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 6))
        static_box.grid_columnconfigure(0, weight=1)

        btn_search = ctk.CTkButton(
            static_box, text="Search",
            command=lambda: self.show_page("search"),
            fg_color=ACCENT, hover_color=ACCENT_HOVER,
            text_color=TEXT, corner_radius=18, height=36
        )
        btn_search.grid(row=0, column=0, sticky="ew", pady=(0, 6))

        btn_settings = ctk.CTkButton(
            static_box, text="Manage Playlists",
            command=lambda: self.show_page("make playlist"),
            fg_color=ACCENT, hover_color=ACCENT_HOVER,
            text_color=TEXT, corner_radius=18, height=36
        )
        btn_settings.grid(row=2, column=0, sticky="ew", pady=6)

        # --- "Playlists" label ---
        lbl = ctk.CTkLabel(self.menu_frame, text="Playlists", text_color=TEXT_MUTED)
        lbl.grid(row=1, column=0, sticky="w", padx=12, pady=(6, 4))

        # --- Dynamic playlist buttons container ---
        self.playlists_container = ctk.CTkFrame(self.menu_frame, fg_color="transparent")
        self.playlists_container.grid(row=2, column=0, sticky="nsew", padx=4, pady=(0, 8))

        # build initial list
        self.refresh_playlists_sidebar()

    # --------- Music bar (bottom) ----------
    def _build_music_bar(self):
        self.music_bar = ctk.CTkFrame(self, fg_color=BG)
        self.music_bar.grid(row=4, column=1, columnspan=3, sticky="nsew", padx=18, pady=14)
        self.music_bar.grid_columnconfigure(0, weight=1)

    def _build_playback_row(self):
        self.playback_row = ctk.CTkFrame(self.music_bar, fg_color=BG)
        self.playback_row.grid(row=2, column=0, sticky="ew", pady=(8, 2))
        self.playback_row.grid_columnconfigure(1, weight=1)
        self.time_cur = ctk.CTkLabel(self.playback_row, text="0:00", text_color=TEXT_MUTED, font=(FONT, 11))
        self.time_cur.grid(row=0, column=0, padx=(0, 10))
        self.seek_var = ctk.DoubleVar(value=0.0)
        self.seek = ctk.CTkSlider(
            self.playback_row, from_=0.0, to=100.0,
            variable=self.seek_var, number_of_steps=None,
            command=self._on_seek_drag,
            fg_color="#404040",
            progress_color=ACCENT,
            button_color=ACCENT,
            button_hover_color=ACCENT_HOVER,
            height=10
        )
        self.seek.grid(row=0, column=1, sticky="ew")
        self.time_tot = ctk.CTkLabel(self.playback_row, text="0:00", text_color=TEXT_MUTED, font=(FONT, 11))
        self.time_tot.grid(row=0, column=2, padx=(10, 0))

    def _build_controls_row(self):
        self.controls_row = ctk.CTkFrame(self.music_bar, fg_color=BG)
        self.controls_row.grid(row=3, column=0, sticky="w", pady=(10, 0))
        self.pause_btn = ctk.CTkButton(
            self.controls_row, text="Pause",
            command=self.on_pause_resume,
            fg_color=BG, hover_color="#1f1f1f", text_color=ACCENT,
            border_width=1, border_color=ACCENT, corner_radius=18, width=90
        )

        self.pause_btn.grid(row=0, column=0)
        self.stop_btn = ctk.CTkButton(
            self.controls_row, text="Stop",
            command=self.on_stop_clicked,
            fg_color=BG, hover_color="#1f1f1f", text_color=ACCENT,
            border_width=1, border_color=ACCENT, corner_radius=18, width=90
        )
        self.stop_btn.grid(row=0, column=1 , padx=(8, 0))

        self.skip_btn = ctk.CTkButton(
            self.controls_row, text="Skip",
            command=self.skip_song,
            fg_color=BG, hover_color="#1f1f1f", text_color=ACCENT,
            border_width=1, border_color=ACCENT, corner_radius=18, width=90
        )
        self.skip_btn.grid(row=0, column=2 , padx=(8, 0))

    def _build_status_line(self):
        self.status = ctk.CTkLabel(self.music_bar, text="Ready", text_color=TEXT_MUTED, font=(FONT, 20, "bold"))
        self.status.grid(row=0, column=0, sticky="w", pady=(10, 0))


    # --------- Events / actions ----------
    def _wire_events(self):
        # Enter triggers play only if we're on the Search page
        def on_return(_e):
            if self.current_page_key == "search":
                page: SearchPage = self.pages["search"]
                try:
                    q = page.entry.get().strip()
                except Exception:
                    q = ""
                if q:
                    self.play_query(q)
        self.bind("<Return>", on_return)

        # Seek on mouse release
        self.seek.bind("<ButtonPress-1>", lambda e: self._set_dragging(True))
        self.seek.bind("<ButtonRelease-1>", lambda e: self._seek_release())

    def set_status(self, text: str):
        self.status.configure(text=text)
        self.status.update_idletasks()

    def _set_dragging(self, v: bool):
        self.user_dragging = v

    def _seek_release(self):
        self.user_dragging = False
        self._seek_to_percent(self.seek_var.get())

    def _on_seek_drag(self, _pct):
        pass

    def _seek_to_percent(self, percent: float):
        cur, tot = self.player.get_position()
        if tot > 0:
            self.player.seek(tot * (max(0.0, min(100.0, percent)) / 100.0))

    def download_query(self, query: str):
        if not query:
            messagebox.showinfo("LocalStream", "Please type a song name.")
            return

        self._disable_controls()
        self.set_status("Searching")

        def worker():
            try:
                path = search.find_or_download(query)
                if path is None:
                    raise RuntimeError("Could not resolve a file for that query.")
                self.current_path = Path(path)
                self.set_status(f"Downloaded: {self.current_path.name}")

            except Exception as e:
                err = "".join(traceback.format_exception_only(type(e), e)).strip()
                print(traceback.format_exc())
                self.after(0, lambda: (
                    self.set_status("Error. See console for details."),
                    messagebox.showerror("LocalStream Error", err)
                ))
            finally:
                self.after(0, self._enable_controls)

        threading.Thread(target=worker, daemon=True).start()

    def add_query_to_paylist(self, query: str, playlist: str, play_song  = False):
        if not query:
            messagebox.showinfo("LocalStream", "Please type a song name.")
            return

        self._disable_controls()
        self.set_status("Searching")

        def worker():
            try:
                path = search.find_or_download_in_playlist(playlist, query)
                if path is None:
                    raise RuntimeError("Could not resolve a file for that query.")
                self.current_path = Path(path)
                if play_song:
                    self.player.stop()
                    self.player.play(self.current_path)
                    self.playing = True
                    self.after(0, lambda: (
                        self.set_status(f"Playing: {self.current_path.name}"),
                        self.pause_btn.configure(text="Pause")
                    ))
                else:
                    self.set_status(f"Downloaded: {self.current_path.name}")

            except Exception as e:
                err = "".join(traceback.format_exception_only(type(e), e)).strip()
                print(traceback.format_exc())
                self.after(0, lambda: (
                    self.set_status("Error. See console for details."),
                    messagebox.showerror("LocalStream Error", err)
                ))
            finally:
                self.after(0, self._enable_controls)

        threading.Thread(target=worker, daemon=True).start()

    #  reusable play method (SearchPage calls this)
    def play_query(self, query: str):
        if not query:
            messagebox.showinfo("LocalStream", "Please type a song name.")
            return

        self._disable_controls()
        self.set_status("Searching")

        def worker():
            try:
                path = search.find_or_download(query)
                if path is None:
                    raise RuntimeError("Could not resolve a file for that query.")
                self.current_path = Path(path)

                self.player.stop()
                self.player.play(self.current_path)
                self.playing = True
                self.after(0, lambda: (
                    self.set_status(f"Playing: {self.current_path.name}"),
                    self.pause_btn.configure(text="Pause")
                ))
            except Exception as e:
                err = "".join(traceback.format_exception_only(type(e), e)).strip()
                print(traceback.format_exc())
                self.after(0, lambda: (
                    self.set_status("Error. See console for details."),
                    messagebox.showerror("LocalStream Error", err)
                ))
            finally:
                self.after(0, self._enable_controls)

        threading.Thread(target=worker, daemon=True).start()

    def on_pause_resume(self):
        if self.playing:
            self.player.pause()
            self.playing = False
            self.pause_btn.configure(text="Resume")
            self.set_status("Paused.")
        else:
            self.player.resume()
            self.playing = True
            self.pause_btn.configure(text="Pause")
            self.set_status("Playing…")

    def skip_song(self):
        if not self.playing:
            messagebox.showinfo("LocalStream", "Nothing is currently playing.")
            return
        
        self._advance_queue()
        self.set_status(f"Skipped to: {self.current_path.name if self.current_path else 'unknown'}")

    def on_stop_clicked(self):
        self.player.stop()
        self.playing = False
        self.seek_var.set(0.0)
        self.pause_btn.configure(text="Pause")
        self.set_status("Stopped.")
        self.current_path = None

    def _on_finished(self):
        self.after(0, lambda: (
            self.set_status("Finished."),
            self.pause_btn.configure(text="Pause"),
            self.seek_var.set(0.0)
        ))
        self.playing = False
        self.current_path = None

    # ---------- Progress Loop ----------
    def _start_progress_loop(self):
        def tick():
            try:
                cur, tot = self.player.get_position()
                self.time_cur.configure(text=self._fmt_time(cur))
                self.time_tot.configure(text=self._fmt_time(tot))
                if not self.user_dragging and tot > 0:
                    pct = (cur / tot) * 100.0
                    self.seek_var.set(max(0.0, min(100.0, pct)))
            finally:
                self.after(200, tick)

                try:
                    if self.playing and tot > 0 and (tot - cur) <= 0.8:
                        # small hysteresis: only advance once per track
                        # stop current, mark not playing, then advance
                        self.playing = False
                        self._advance_queue()
                except Exception:
                    pass
        tick()

    @staticmethod
    def _fmt_time(seconds: float) -> str:
        if seconds <= 0 or seconds == float("inf"):
            return "0:00"
        m, s = divmod(int(seconds), 60)
        return f"{m}:{s:02d}"

    # ---------- Enable / Disable ----------
    def _disable_controls(self):
        # Do enable in diable control buttons, also give visual que (grey out)
        #used while doanloading song
        self.pause_btn.configure(state="disabled")
        self.stop_btn.configure(state="disabled")
        self.skip_btn.configure(state="disabled")

    def _enable_controls(self):
        self.pause_btn.configure(state="normal")
        self.stop_btn.configure(state="normal")
        self.skip_btn.configure(state="normal")


# --------- Pages ---------

class Page(ctk.CTkFrame):
    def on_show(self): pass
    def on_hide(self): pass

class Page(ctk.CTkFrame):
    def on_show(self): pass
    def on_hide(self): pass


class SearchPage(Page):
    def __init__(self, parent, app, **kwargs):
        super().__init__(parent, **kwargs)
        self.app = app

        # --- Page grid ---

        #Contains title
        self.grid_columnconfigure(0, weight=4) 
        #Search tool is here, has lower stretch weight as to restrict search bar length
        self.grid_columnconfigure(1, weight=3) 
        self.grid_columnconfigure(2, weight=4)

        #Top row has title
        self.grid_rowconfigure(0, weight=1)
        #Search tools and buttons live here     
        self.grid_rowconfigure(1, weight=1)  

        # --- Row 0: gradient spanning all columns ---
        grad_frame = ctk.CTkFrame(self, fg_color=BG, corner_radius=8)
        grad_frame.grid(row=0, column=0, columnspan=3, sticky="nsew", padx=0, pady=(0, 10))

        self.grad_canvas = tk.Canvas(grad_frame, height=90, highlightthickness=0, bd=0)
        self.grad_canvas.pack(fill="both", expand=True)

        # keep the "current" title here; load_playlist updates it
        self._title_text = "Search"
        self.title_item = None  # canvas item id (int) or None

        def _paint(_evt=None):
            c = self.grad_canvas
            w, h = int(c.winfo_width()), int(c.winfo_height())
            if w <= 0 or h <= 0:
                return

            # 1) redraw gradient ONLY, written this way to preserve text above grad
            c.delete("grad") 
            r1, g1, b1 = c.winfo_rgb(ACCENT)
            r2, g2, b2 = c.winfo_rgb(BG)
            dr = (r2 - r1) / max(1, h)
            dg = (g2 - g1) / max(1, h)
            db = (b2 - b1) / max(1, h)
            for y in range(h):
                rr = int(r1 + dr*y) // 256
                gg = int(g1 + dg*y) // 256
                bb = int(b1 + db*y) // 256
                c.create_line(0, y, w, y, fill=f"#{rr:02x}{gg:02x}{bb:02x}", tags=("grad",))

            # 2) ensure title exists, using the CURRENT title text
            y = max(10, min(h - 10, int(h * 0.6)))
            x = 12
            if self.title_item is None:
                self.title_item = c.create_text(
                    x, y, text=self._title_text, fill=TEXT,
                    font=(FONT, LARGE_TITLE, "bold"), anchor="w"
                )
            else:
                # keep its y aligned on resize and text unchanged here
                c.coords(self.title_item, x, y)
                c.tag_raise(self.title_item)

        self.grad_canvas.bind("<Configure>", _paint)
        # --- Row 1: three content columns; we only *use* the center one now ---
        left_col  = ctk.CTkFrame(self, fg_color=BG)
        mid_col   = ctk.CTkFrame(self, fg_color=BG)
        right_col = ctk.CTkFrame(self, fg_color=BG)

        left_col.grid(row=1, column=0, sticky="nsew", padx=(0, 8), pady=0)
        mid_col.grid(row=1, column=1, sticky="nsew", padx=0,       pady=0)
        right_col.grid(row=1, column=2, sticky="nsew", padx=(8, 0), pady=0)

        # The middle column stretches; give it rows for search/tools/spacer
        mid_col.grid_columnconfigure(0, weight=1)
        mid_col.grid_rowconfigure(0, weight=0)   # search row
        mid_col.grid_rowconfigure(1, weight=0)   # tools row
        mid_col.grid_rowconfigure(2, weight=1)   # spacer (pushes content up)

        # --- Middle column: SEARCH (row 0) ---
        rail = ctk.CTkFrame(mid_col, fg_color=BG)
        rail.grid(row=0, column=0, sticky="ew", pady=(8, 10))
        rail.grid_columnconfigure(0, weight=1)

        # Search row (entry + Play)
        row_frame = ctk.CTkFrame(rail, fg_color=BG)
        row_frame.grid(row=0, column=0, sticky="ew")
        row_frame.grid_columnconfigure(0, weight=1)  # entry stretches

        self.entry = ctk.CTkEntry(
            row_frame, placeholder_text="Type a song…",
            height=40, corner_radius=22,
            fg_color=CARD_BG, border_color=ACCENT, border_width=1,
            text_color=TEXT
        )
        self.entry.grid(row=0, column=0, sticky="ew")

        play_btn = ctk.CTkButton(
            row_frame, text="Play",
            command=self._on_play_clicked,
            fg_color=ACCENT, hover_color=ACCENT_HOVER,
            text_color=TEXT, corner_radius=22, width=90, height=40
        )
        play_btn.grid(row=0, column=1, padx=(10, 0))

        download_btn = ctk.CTkButton(
            row_frame, text="Download",
            command=self._on_download_clicked,
            fg_color=ACCENT, hover_color=ACCENT_HOVER,
            text_color=TEXT, corner_radius=22, width=90, height=40
        )
        download_btn.grid(row=0, column=2, padx=(10, 0))

        # --- Middle column: (optional) TOOLS (row 1) ---
        # tools = ctk.CTkFrame(mid_col, fg_color=BG)
        # tools.grid(row=1, column=0, sticky="ew", padx=0, pady=(8, 0))
        # tools.grid_columnconfigure(0, weight=1)

    # Make sure the play button target exists
    def _on_play_clicked(self):
        q = self.entry.get().strip()
        if q:
            self.app.play_query(q)

    def _on_download_clicked(self):
        q = self.entry.get().strip()
        if q:
            self.app.download_query(q)



class LibraryPage(Page):
    def __init__(self, parent, app, **kwargs):
        super().__init__(parent, **kwargs)
        self.app = app
        ctk.CTkLabel(self, text="Library (TODO)", font=(FONT, 16, "bold")).pack(pady=12)

class MakePlayList(Page):
    """Page to create and manage playlists (folders in ./playlists/<name>)."""
    def __init__(self, parent, app, **kwargs):
        super().__init__(parent, **kwargs)
        self.app = app

        # 3 columns: 4 / 3 / 4
        self.grid_columnconfigure(0, weight=4)
        self.grid_columnconfigure(1, weight=3)
        self.grid_columnconfigure(2, weight=4)
        # rows: 0 = gradient, 1 = form row, 2 = list row
        self.grid_rowconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self.grid_rowconfigure(2, weight=1)

        # --- Row 0: gradient ---
        grad_frame = ctk.CTkFrame(self, fg_color=BG, corner_radius=8)
        grad_frame.grid(row=0, column=0, columnspan=3, sticky="nsew", padx=0, pady=(0, 10))

        self.grad_canvas = tk.Canvas(grad_frame, height=90, highlightthickness=0, bd=0)
        self.grad_canvas.pack(fill="both", expand=True)

        self._title_text = "Manage Playlists"
        self.title_item = None

        def _paint(_evt=None):
            c = self.grad_canvas
            w, h = int(c.winfo_width()), int(c.winfo_height())
            if w <= 0 or h <= 0:
                return
            # gradient only
            c.delete("grad")
            r1, g1, b1 = c.winfo_rgb(ACCENT)
            r2, g2, b2 = c.winfo_rgb(BG)
            dr = (r2 - r1) / max(1, h)
            dg = (g2 - g1) / max(1, h)
            db = (b2 - b1) / max(1, h)
            for y in range(h):
                rr = int(r1 + dr*y) // 256
                gg = int(g1 + dg*y) // 256
                bb = int(b1 + db*y) // 256
                c.create_line(0, y, w, y, fill=f"#{rr:02x}{gg:02x}{bb:02x}", tags=("grad",))
            # title (center-ish vertically)
            y = max(10, min(h - 10, int(h * 0.6)))
            if self.title_item is None:
                self.title_item = c.create_text(
                    12, y, text=self._title_text, fill=TEXT,
                    font=(FONT, 60, "bold"), anchor="w"
                )
            else:
                c.coords(self.title_item, 12, y)
                c.tag_raise(self.title_item)

        self.grad_canvas.bind("<Configure>", _paint)

        # --- Row 1: create form (entry + button) ---
        form = ctk.CTkFrame(self, fg_color=BG)
        form.grid(row=1, column=1, sticky="ew", padx=0, pady=(0, 10))
        form.grid_columnconfigure(0, weight=1)

        self.name_entry = ctk.CTkEntry(
            form, placeholder_text="New playlist name…",
            height=36, corner_radius=14, fg_color=CARD_BG,
            border_color=ACCENT, border_width=1, text_color=TEXT
        )
        self.name_entry.grid(row=0, column=0, sticky="ew")

        create_btn = ctk.CTkButton(
            form, text="Create",
            command=self._create_playlist,
            fg_color=ACCENT, hover_color=ACCENT_HOVER,
            text_color=TEXT, corner_radius=14, width=90, height=36
        )
        create_btn.grid(row=0, column=1, padx=(10, 0))

        hint = ctk.CTkLabel(
            self,
            text="Playlists are folders in the 'playlists' directory next to the app.",
            text_color=TEXT_MUTED, font=(FONT, 11)
        )
        hint.grid(row=1, column=0, columnspan=3, sticky="swe", padx=2, pady=(6, 0))

        # --- Row 2: playlists list (with optional scrollbar) ---
        list_frame = ctk.CTkFrame(self, fg_color=BG)
        list_frame.grid(row=2, column=0, columnspan=3, sticky="nsew", padx=0, pady=(0, 0))
        list_frame.grid_rowconfigure(0, weight=1)
        list_frame.grid_columnconfigure(0, weight=1)

        self.pl_listbox = tk.Listbox(
            list_frame, bg=BG, fg=TEXT, font=(FONT, 24, "bold"),
            selectbackground="#333333", highlightthickness=0, bd=0, activestyle="none"
        )
        self.pl_listbox.grid(row=0, column=0, sticky="nsew")

        # Scrollbar (visible—remove if you want hidden behavior)
        sb = tk.Scrollbar(list_frame, command=self.pl_listbox.yview)
        sb.grid(row=0, column=1, sticky="ns")
        self.pl_listbox.config(yscrollcommand=sb.set)

        # Bind delete/backspace and double-click to open
        self.pl_listbox.bind("<Delete>", lambda _e: self._delete_selected_playlists())
        self.pl_listbox.bind("<BackSpace>", lambda _e: self._delete_selected_playlists())
        self.pl_listbox.bind("<Double-Button-1>", self._open_selected_playlist)

        # initial load
        self.refresh_list()

    # -------- helpers --------
    def _playlists_root(self) -> Path:
        return ROOT / "playlists"

    def _safe_name(self, name: str) -> str:
        bad = set('<>:"/\\|?*')
        cleaned = "".join("_" if (ch in bad or ord(ch) < 32) else ch for ch in name)
        cleaned = cleaned.strip().rstrip(".")
        return cleaned

    def refresh_list(self):
        """Reload the list of playlist folders."""
        root = self._playlists_root()
        root.mkdir(parents=True, exist_ok=True)
        self.pl_listbox.delete(0, tk.END)

        names = sorted([p.name for p in root.iterdir() if p.is_dir()], key=str.casefold)
        if not names:
            self.pl_listbox.insert(tk.END, "(no playlists)")
            self.pl_listbox.configure(state="disabled")
        else:
            self.pl_listbox.configure(state="normal")
            for n in names:
                self.pl_listbox.insert(tk.END, n)

    # -------- actions --------
    def _create_playlist(self):
        raw = self.name_entry.get().strip()
        if not raw:
            messagebox.showinfo("Create Playlist", "Please type a playlist name.")
            return
        safe = self._safe_name(raw)
        if not safe:
            messagebox.showerror("Create Playlist", "That name is not valid after sanitizing. Try another.")
            return

        root = self._playlists_root()
        try:
            root.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            messagebox.showerror("Create Playlist", f"Could not create playlists folder:\n{e}")
            return

        folder = root / safe
        if folder.exists():
            messagebox.showinfo("Create Playlist", f"A playlist named '{raw}' already exists.")
            return

        try:
            folder.mkdir()
        except Exception as e:
            messagebox.showerror("Create Playlist", f"Could not create playlist:\n{e}")
            return

        self.name_entry.delete(0, tk.END)
        self.refresh_list()
        if hasattr(self.app, "refresh_playlists_sidebar"):
            self.app.refresh_playlists_sidebar()

    def _delete_selected_playlists(self):
        """Delete selected playlist folders (with confirmation)."""
        sel = list(self.pl_listbox.curselection())
        if not sel:
            messagebox.showinfo("Delete", "Select one or more playlists to delete.")
            return

        # if the list is disabled because it's empty placeholder, do nothing
        if str(self.pl_listbox.cget("state")) == "disabled":
            return

        names = [self.pl_listbox.get(i) for i in sel]
        if not messagebox.askyesno("Delete", f"Delete {len(names)} playlist folder(s)?\n\n" +
                                   "\n".join(names)):
            return

        root = self._playlists_root()
        errors = []
        import shutil

        for name in names:
            folder = root / name
            try:
                # If current play queue comes from this folder, stop playback and clear queue
                if getattr(self.app, "play_queue", None):
                    # Remove any queued items from this folder
                    self.app.play_queue = [p for p in self.app.play_queue if p.resolve().parent != folder.resolve()]
                    if getattr(self.app, "queue_index", -1) >= len(self.app.play_queue):
                        self.app.queue_index = len(self.app.play_queue) - 1
                # If currently playing file is inside the folder, stop
                cur = getattr(self.app, "current_path", None)
                if cur and cur.resolve().parents and folder.resolve() in cur.resolve().parents:
                    self.app.on_stop_clicked()

                # Delete the folder (even if not empty)
                if folder.exists() and folder.is_dir():
                    shutil.rmtree(folder)
            except Exception as e:
                errors.append(f"{name}: {e}")

        if errors:
            messagebox.showerror("Delete", "Some playlists could not be deleted:\n" + "\n".join(errors))
        else:
            messagebox.showinfo("Delete", "Deleted.")

        self.refresh_list()
        if hasattr(self.app, "refresh_playlists_sidebar"):
            self.app.refresh_playlists_sidebar()

    def _open_selected_playlist(self, _e=None):
        """Double-click behavior: open the selected playlist page."""
        sel = list(self.pl_listbox.curselection())
        if not sel:
            return
        name = self.pl_listbox.get(sel[0])
        # ignore placeholder row
        if name.strip() == "(no playlists)":
            return
        if hasattr(self.app, "show_playlist"):
            self.app.show_playlist(name)

    # If your router calls on_show/on_hide, auto-refresh when entering the page.
    def on_show(self):
        self.refresh_list()




class SettingsPage(Page):
    def __init__(self, parent, app, **kwargs):
        super().__init__(parent, **kwargs)
        self.app = app
        ctk.CTkLabel(self, text="Settings (TODO)", font=(FONT, 16, "bold")).pack(pady=12)

class PlaylistViewPage(Page):

    # Make sure the play button target exists
    def _on_play_clicked(self):
        q = self.entry.get().strip()
        if q:
            self.app.add_query_to_paylist(q, self.current_playlist, play_song=True)

    def _on_add_to_list_clicked(self):
        q = self.entry.get().strip()
        if q:
            self.app.add_query_to_paylist(q, self.current_playlist, play_song=False)

    def _on_play_all(self):
        if not self.current_playlist:
            messagebox.showinfo("LocalStream", "Open a playlist first.")
            return
        folder = self.app._playlists_root() / self.current_playlist
        self.app.start_playlist_folder(folder)

    def _on_play_shuffle(self):
        if not self.current_playlist:
            messagebox.showinfo("LocalStream", "Open a playlist first.")
            return
        folder = self.app._playlists_root() / self.current_playlist
        self.app.start_playlist_folder(folder, shuffle_list=True)

    def _on_delete_selected(self):
        if not self.current_playlist:
            messagebox.showinfo("Delete", "Open a playlist first.")
            return

        sel = list(self.listbox.curselection())
        if not sel:
            messagebox.showinfo("Delete", "Select one or more files to delete.")
            return

        names = [self.listbox.get(i) for i in sel]
        if not messagebox.askyesno(
            "Delete",
            f"Delete {len(names)} file(s) from '{self.current_playlist}'?"
        ):
            return

        folder = self.app._playlists_root() / self.current_playlist
        targets = [(folder / n) for n in names]

        # If the currently playing track is among the targets, stop or skip
        cur = getattr(self.app, "current_path", None)
        deleting_current = cur and any(t.samefile(cur) if t.exists() and cur.exists() else (t == cur)
                                    for t in targets)

        if deleting_current:
            # simple behavior: stop. Or call self.app._advance_queue() if you prefer skip.
            self.app.on_stop_clicked()

        # Remove from play_queue if it came from the same playlist
        if getattr(self.app, "play_queue", None):
            keep = []
            for p in self.app.play_queue:
                try:
                    in_targets = any(t == p or (t.exists() and p.exists() and t.samefile(p)) for t in targets)
                except Exception:
                    in_targets = any(t == p for t in targets)
                if not in_targets:
                    keep.append(p)
            self.app.play_queue = keep

            # fix queue_index if it points past the end
            if self.app.queue_index >= len(self.app.play_queue):
                self.app.queue_index = len(self.app.play_queue) - 1

        # Delete files (permanent)
        import os
        errors = []
        for t in targets:
            try:
                if t.exists():
                    os.remove(t)
            except Exception as e:
                errors.append(f"{t.name}: {e}")

        if errors:
            messagebox.showerror("Delete", "Some files could not be deleted:\n" + "\n".join(errors))
        else:
            messagebox.showinfo("Delete", "Deleted.")

        # Refresh the listbox to reflect changes
        self.load_playlist(self.current_playlist)


    """Shows the file names inside a playlist folder."""
    def __init__(self, parent, app, **kwargs):
        super().__init__(parent, **kwargs)
        self.app = app
        self.current_playlist: str | None = None

        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # 3 columns: 4 / 3 / 4
        self.grid_columnconfigure(0, weight=4)
        self.grid_columnconfigure(1, weight=3)
        self.grid_columnconfigure(2, weight=4)
        # rows: 0 = gradient (fixed-ish), 1 = header, 2 = form, 3 = hint/fill
        self.grid_rowconfigure(0, weight=1)  
        self.grid_rowconfigure(1, weight=0)
        self.grid_rowconfigure(2, weight=1)
        self.grid_rowconfigure(3, weight=1)  

        # --- Row 0: gradient spanning all columns ---
        grad_frame = ctk.CTkFrame(self, fg_color=BG, corner_radius=8)
        grad_frame.grid(row=0, column=0, columnspan=3, sticky="nsew", padx=0, pady=(0, 10))

        self.grad_canvas = tk.Canvas(grad_frame, height=90, highlightthickness=0, bd=0)
        self.grad_canvas.pack(fill="both", expand=True)

        # keep the "current" title here; load_playlist updates it
        self._title_text = "Playlist"
        self.title_item = None  # canvas item id (int) or None

        def _paint(_evt=None):
            c = self.grad_canvas
            w, h = int(c.winfo_width()), int(c.winfo_height())
            if w <= 0 or h <= 0:
                return

            # 1) redraw gradient ONLY (don't nuke the text)
            c.delete("grad")
            r1, g1, b1 = c.winfo_rgb(ACCENT)
            r2, g2, b2 = c.winfo_rgb(BG)
            dr = (r2 - r1) / max(1, h)
            dg = (g2 - g1) / max(1, h)
            db = (b2 - b1) / max(1, h)
            for y in range(h):
                rr = int(r1 + dr*y) // 256
                gg = int(g1 + dg*y) // 256
                bb = int(b1 + db*y) // 256
                c.create_line(0, y, w, y, fill=f"#{rr:02x}{gg:02x}{bb:02x}", tags=("grad",))

            # 2) ensure title exists, using the CURRENT title text
            # place roughly centered vertically (h*0.5) and with 12px left margin
            y = max(10, min(h - 10, int(h * 0.6)))
            x = 12
            if self.title_item is None:
                self.title_item = c.create_text(
                    x, y, text=self._title_text, fill=TEXT,
                    font=(FONT, 60, "bold"), anchor="w"
                )
            else:
                # keep its y aligned on resize and text unchanged here
                c.coords(self.title_item, 12, y)
                c.tag_raise(self.title_item)

        self.grad_canvas.bind("<Configure>", _paint)


        self.title_item = self.grad_canvas.create_text(
            12, 45,                  # x, y position (tweak as you like)
            text="Playlist",
            fill=TEXT,
            font=(FONT, 50, "bold"),
            anchor="w"
        )

        # --- Row 1: three content columns; we only *use* the center one now ---
        left_col  = ctk.CTkFrame(self, fg_color=BG)
        mid_col   = ctk.CTkFrame(self, fg_color=BG)
        right_col = ctk.CTkFrame(self, fg_color=BG)

        left_col.grid(row=1, column=0, sticky="nsew", padx=(0, 8), pady=0)
        mid_col.grid(row=1, column=1, sticky="nsew", padx=0,       pady=0)
        right_col.grid(row=1, column=2, sticky="nsew", padx=(8, 0), pady=0)

        # The middle column stretches; give it rows for search/tools/spacer
        mid_col.grid_columnconfigure(0, weight=1)
        mid_col.grid_rowconfigure(0, weight=0)   # search row
        mid_col.grid_rowconfigure(1, weight=0)   # tools row
        mid_col.grid_rowconfigure(2, weight=1)   # spacer 

        # ----- top
        rail = ctk.CTkFrame(mid_col, fg_color=BG)
        rail.grid(row=0, column=0, sticky="ew", pady=(8, 10))
        rail.grid_columnconfigure(0, weight=1)

        # Search row (entry + Play)
        row_frame = ctk.CTkFrame(rail, fg_color=BG)
        row_frame.grid(row=0, column=0, sticky="ew")
        row_frame.grid_columnconfigure(0, weight=1)  # entry stretches

        self.entry = ctk.CTkEntry(
            row_frame, placeholder_text="Type a song…",
            height=40, corner_radius=22,
            fg_color=CARD_BG, border_color=ACCENT, border_width=1,
            text_color=TEXT
        )
        self.entry.grid(row=0, column=0, sticky="ew")

        play_btn = ctk.CTkButton(
            row_frame, text="Play and Add",
            command=self._on_play_clicked,
            fg_color=ACCENT, hover_color=ACCENT_HOVER,
            text_color=TEXT, corner_radius=22, width=90, height=40
        )
        play_btn.grid(row=0, column=2, padx=(10, 0))

        download_btn = ctk.CTkButton(
            row_frame, text="Add",
            command=self._on_add_to_list_clicked,
            fg_color=ACCENT, hover_color=ACCENT_HOVER,
            text_color=TEXT, corner_radius=22, width=90, height=40
        )
        download_btn.grid(row=0, column=1, padx=(10, 0))

        play_all_btn = ctk.CTkButton(
            self, text="Play All",
            command=self._on_play_all,
            fg_color=ACCENT, hover_color=ACCENT_HOVER, text_color=TEXT,
            corner_radius=16, width=180, height=36
        )
        # Put it just under the gradient block:
        play_all_btn.grid(row=1, column=1, sticky="e", padx=0, pady=(0, 10))

        play_all_btn = ctk.CTkButton(
            self, text="Shuffle Play",
            command=self._on_play_shuffle,
            fg_color=ACCENT, hover_color=ACCENT_HOVER, text_color=TEXT,
            corner_radius=16, width=180, height=36
        )
        # Put it just under the gradient block:
        play_all_btn.grid(row=1, column=1, sticky="w", padx=0, pady=(0, 10))



        # List area
        list_frame = ctk.CTkFrame(self, fg_color=BG)
        list_frame.grid(row=2, column=0, columnspan=3, sticky="nsew", padx=0, pady=(0, 0))
        list_frame.grid_columnconfigure(0, weight=1)
        list_frame.grid_rowconfigure(0, weight=1)

        self.listbox = tk.Listbox(
            list_frame, bg=BG, fg=TEXT, font=(FONT, 30, "bold"), selectbackground="#333333",
            highlightthickness=0, bd=0, activestyle="none"
        )
        self.listbox.grid(row=1, column=0, sticky="nsew")

         #delete selected song when delete is hit
        self.listbox.bind("<Delete>", lambda _e: self._on_delete_selected())
        self.listbox.bind("<BackSpace>", lambda _e: self._on_delete_selected())

    def load_playlist(self, name: str):
        self.current_playlist = name
        self.grad_canvas.itemconfigure(self.title_item, text=f"Playlist — {name}")

        folder = self.app._playlists_root() / name
        self.listbox.delete(0, tk.END)

        if not folder.exists() or not folder.is_dir():
            self.listbox.insert(tk.END, "(missing playlist folder)")
            return

        # list files (you can filter by extension if you want)
        files = [p for p in folder.iterdir() if p.is_file()]
        files.sort(key=lambda p: p.name.casefold())

        if not files:
            self.listbox.insert(tk.END, "(no files)")
            return

        for f in files:
            self.listbox.insert(tk.END, f.name)




if __name__ == "__main__":
    app = MusicGUI()
    app.mainloop()
