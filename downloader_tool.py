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
APP_NAME = "Fluss Downloader"
START_PAGE = "search"
INIT_GEOMETRY = "900x360"
INIT_MINISIZE_X = 760
INIT_MINISIZE_Y = 320
# Main color of website
ACCENT = "#060270"
#lighter acent for active elements        
ACCENT_HOVER = "#0902D0"
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
#Unsed, need to implenet, unevsal fint sizes for consistency
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

        # 4) Build page container + pages
        self._build_pages_container()
        self._build_pages()

        # 5) Now it’s safe to wire events; widgets exist
        self._wire_events()


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
        # 4 columns total: First is menure sidebar, rest is content [sidebar][content x3])
        self.grid_columnconfigure(1, weight=4)
        self.grid_columnconfigure(2, weight=3)
        self.grid_columnconfigure(3, weight=4)
        # rows: Top will always be title, bottom will be player, middle three will be content
        #  Title | pages | pages | pages | Music player
        self.grid_rowconfigure(0, weight=0)
        self.grid_rowconfigure(1, weight=3)
        self.grid_rowconfigure(2, weight=3)

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


    # --------- Page container + pages (router) ----------
    def _build_pages_container(self):
        self.page_container = ctk.CTkFrame(self, fg_color=BG)
        self.page_container.grid(row=1, column=1, rowspan=3, columnspan=3,
                                 sticky="nsew", padx=18, pady=14)
        self.page_container.grid_rowconfigure(0, weight=1)
        self.page_container.grid_columnconfigure(0, weight=1)

    def _build_pages(self):
        self.pages = {
            "search":    SearchPage(self.page_container, app=self, fg_color=BG)
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
        self.title_lbl = ctk.CTkLabel(self.header, text=APP_NAME,
                                      text_color=TEXT, font=(FONT, 18, "bold"))
        self.title_lbl.grid(row=0, column=0, sticky="w", padx=16, pady=12)

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
            messagebox.showinfo("Fluss Doanloader", "Please copy Youtube link.")
            return

        def worker():
            try:
                path = search.download_youtube_video(query)
                if path is None:
                    raise RuntimeError("Could not resolve a file for that query.")
                self.current_path = Path(path)

            except Exception as e:
                err = "".join(traceback.format_exception_only(type(e), e)).strip()
                print(traceback.format_exc())
                self.after(0, lambda: (
                    messagebox.showerror("Fluss Doanloader Error", err)
                ))

        threading.Thread(target=worker, daemon=True).start()

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
        self.grid_columnconfigure(0, weight=2) 
        self.grid_columnconfigure(1, weight=4) 
        self.grid_columnconfigure(2, weight=2)

        #Top row has title
        self.grid_rowconfigure(0, weight=1)
        #Search tools and buttons live here     
 

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
            row_frame, placeholder_text="Please copy youtube link.",
            height=40, corner_radius=22,
            fg_color=CARD_BG, border_color=ACCENT, border_width=1,
            text_color=TEXT
        )
        self.entry.grid(row=0, column=0, sticky="ew")

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

    def _on_download_clicked(self):
        q = self.entry.get().strip()
        if q:
            self.app.download_query(q)



if __name__ == "__main__":
    app = MusicGUI()
    app.mainloop()
