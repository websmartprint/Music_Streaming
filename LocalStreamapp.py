#!/usr/bin/env python3
# gui_ctk.py — Spotify-ish GUI using customtkinter (light maroon + black)

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

# --- Theme ---
ACCENT = "#B34A5A"        # light maroon accent
ACCENT_HOVER = "#C65D6C"
BG = "#0E0E0E"            # near-black background
CARD_BG = "#181818"       # panels / rows
TEXT = "#FFFFFF"
TEXT_MUTED = "#B3B3B3"
FONT = "Segoe UI"  # default font for labels, buttons, etc.

ctk.set_appearance_mode("dark")

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

class MusicGUI(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Fluss")
        self.geometry("900x360")
        self.minsize(760, 320)
        self.configure(fg_color=BG)

        self.player = PlaybackService()

        # --- simple play queue state ---
        self.play_queue: list[Path] = []
        self.queue_index: int = -1
        self.shuffle_mode: bool = False


        # State
        self.current_path: Path | None = None
        self.playing = False
        self.user_dragging = False
        self.current_page_key: str | None = None
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

    # ---------- Gradient helper (kept for future use if you add to a page) ----------
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

    # ---------- UI ----------
    def _configure_grid(self):
        # 4 columns total: [sidebar][content x3]
        self.grid_columnconfigure(0, weight=2)
        self.grid_columnconfigure(1, weight=4)
        self.grid_columnconfigure(2, weight=3)
        self.grid_columnconfigure(3, weight=4)
        # rows: header | pages | pages | pages | footer
        self.grid_rowconfigure(0, weight=0)
        self.grid_rowconfigure(1, weight=3)
        self.grid_rowconfigure(2, weight=3)
        self.grid_rowconfigure(3, weight=3)
        self.grid_rowconfigure(4, weight=0)

    # ---- Filesystem playlists helpers ----
    def _playlists_root(self) -> Path:
        # ROOT should already be defined at module top
        root = ROOT / "playlists"
        root.mkdir(parents=True, exist_ok=True)   # ensure it exists
        return root

    def _list_playlists_fs(self) -> list[str]:
        root = self._playlists_root()
        names = [p.name for p in root.iterdir() if p.is_dir()]
        names.sort(key=str.casefold)
        return names

    def refresh_playlists_sidebar(self):
        """Rebuild the dynamic list of playlist buttons in the sidebar."""
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

    def show_playlist(self, name: str):
        """Show a page that lists the files inside ./playlists/<name>."""
        key = f"playlist::{name}"
        page = self.pages.get(key)

        if page is None:
            # create page once, then reuse
            page = PlaylistViewPage(self.page_container, app=self, fg_color=BG)
            page.grid(row=0, column=0, sticky="nsew")
            self.pages[key] = page

        page.load_playlist(name)   # (re)populate the list
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

        # collect playable files (tweak extensions as you like)
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
            p.grid(row=0, column=0, sticky="nsew")  # stacked in same cell
        self.show_page("search")  # default page

    def show_page(self, key: str):  # ★ NEW
        """Raise the target page; call lifecycle hooks."""
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
        self.menu_frame.grid_rowconfigure(2, weight=1)  # let the list area expand
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
            static_box, text="Create Playlist",
            command=lambda: self.show_page("make playlist"),
            fg_color=ACCENT, hover_color=ACCENT_HOVER,
            text_color=TEXT, corner_radius=18, height=36
        )
        btn_settings.grid(row=2, column=0, sticky="ew", pady=6)

        # --- "Playlists" label ---
        lbl = ctk.CTkLabel(self.menu_frame, text="Playlists", text_color=TEXT_MUTED)
        lbl.grid(row=1, column=0, sticky="w", padx=12, pady=(6, 4))

        # --- Dynamic playlist buttons container ---
        # (You can swap for CTkScrollableFrame if you expect many)
        self.playlists_container = ctk.CTkFrame(self.menu_frame, fg_color="transparent")
        self.playlists_container.grid(row=2, column=0, sticky="nsew", padx=4, pady=(0, 8))

        # build initial list
        self.refresh_playlists_sidebar()

    # --------- Footer (music bar) ----------
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
        # Enter triggers play only if we're on the Search page ★ NEW
        def on_return(_e):
            if self.current_page_key == "search":
                page: SearchPage = self.pages["search"]  # type: ignore
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
        # We only disable footer controls here; Search controls live on the page
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

        # --- Page grid: 3 columns (weights 4, 3, 4) + rows (0=gradient, 1=content) ---
        self.grid_columnconfigure(0, weight=4)
        self.grid_columnconfigure(1, weight=3)   # center column (search/tools live here)
        self.grid_columnconfigure(2, weight=4)
        self.grid_rowconfigure(0, weight=1)     
        self.grid_rowconfigure(1, weight=1)      # main content grows

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
                    font=(FONT, 80, "bold"), anchor="w"
                )
            else:
                # keep its y aligned on resize and text unchanged here
                c.coords(self.title_item, 12, y)
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
        # If you want to add the “add to playlist” UI later, put it here.
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
    """Page to create a new playlist as a folder in ./playlists/<name>."""
    def __init__(self, parent, app, **kwargs):
        super().__init__(parent, **kwargs)
        self.app = app

        # 3 columns: 4 / 3 / 4
        self.grid_columnconfigure(0, weight=4)
        self.grid_columnconfigure(1, weight=3)
        self.grid_columnconfigure(2, weight=4)
        # rows: 0 = gradient (fixed-ish), 1 = header, 2 = form, 3 = hint/fill
        self.grid_rowconfigure(0, weight=1)   # <-- fixed height
        self.grid_rowconfigure(1, weight=1)
        self.grid_rowconfigure(2, weight=1)
        self.grid_rowconfigure(3, weight=1)   # filler grows

        # --- Row 0: gradient spanning all columns ---
        grad_frame = ctk.CTkFrame(self, fg_color=BG, corner_radius=8)
        grad_frame.grid(row=0, column=0, columnspan=3, sticky="nsew", padx=0, pady=(0, 10))

        self.grad_canvas = tk.Canvas(grad_frame, height=90, highlightthickness=0, bd=0)
        self.grad_canvas.pack(fill="both", expand=True)

        # keep the "current" title here; load_playlist updates it
        self._title_text = "Create Playlist"
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

        # --- Row 1: form (entry + button) in the center column ---
        row = ctk.CTkFrame(self, fg_color=BG)
        row.grid(row=1, column=1, sticky="ew", padx=0, pady=(0, 10))
        row.grid_columnconfigure(0, weight=1)

        self.name_entry = ctk.CTkEntry(
            row, placeholder_text="Playlist name…",
            height=36, corner_radius=14, fg_color=CARD_BG,
            border_color=ACCENT, border_width=1, text_color=TEXT
        )
        self.name_entry.grid(row=0, column=0, sticky="new")

        create_btn = ctk.CTkButton(
            row, text="Create",
            command=self._create_playlist,
            fg_color=ACCENT, hover_color=ACCENT_HOVER,
            text_color=TEXT, corner_radius=14, width=90, height=36
        )
        create_btn.grid(row=0, column=1, padx=(10, 0))

        self.hint = ctk.CTkLabel(
            self,
            text="Playlists will be created in the 'playlists' folder next to the app.",
            text_color=TEXT_MUTED, font=(FONT, 11)
        )
        self.hint.grid(row=1, column=0, columnspan=3, sticky="swe", padx=2, pady=(0, 0))

    # --- helpers ---
    def _playlists_root(self) -> Path:
        return ROOT / "playlists"

    def _safe_name(self, name: str) -> str:
        bad = set('<>:"/\\|?*')
        cleaned = "".join("_" if (ch in bad or ord(ch) < 32) else ch for ch in name)
        cleaned = cleaned.strip().rstrip(".")
        return cleaned

    # --- actions ---
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
        # refresh your sidebar if you have that method:
        if hasattr(self.app, "refresh_playlists_sidebar"):
            self.app.refresh_playlists_sidebar()



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
        self.grid_rowconfigure(0, weight=1)   # <-- fixed height
        self.grid_rowconfigure(1, weight=0)
        self.grid_rowconfigure(2, weight=1)
        self.grid_rowconfigure(3, weight=1)   # filler grows

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
