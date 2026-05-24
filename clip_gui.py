#!/usr/bin/env python3
"""
Stellar Theory — Clip Generator GUI
Tabbed layout with resizable panes.

Dependencies:
    pip install pyyaml pillow
    ffmpeg (full build) must be on PATH
    clip_generator.py must be in the same directory
"""

import queue
import random
import subprocess
import sys
import threading
from pathlib import Path

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
except ImportError:
    print("tkinter not found. Install python3-tk.")
    sys.exit(1)

try:
    import yaml
except ImportError:
    print("PyYAML not found: pip install pyyaml")
    sys.exit(1)

try:
    from PIL import Image, ImageTk, ImageDraw
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

try:
    script_dir = Path(__file__).parent
    sys.path.insert(0, str(script_dir))
    from clip_generator import (
        parse_time, get_video_dimensions, build_ffmpeg_command, load_config
    )
except ImportError as e:
    print(f"clip_generator.py not found in same directory: {e}")
    sys.exit(1)


# ══════════════════════════════════════════════════════════════════════
# DESIGN TOKENS
# ══════════════════════════════════════════════════════════════════════

ST = {
    "bg_deep":     "#0D0B08",
    "bg_dark":     "#141209",
    "bg_mid":      "#1C1810",
    "bg_lift":     "#242018",
    "bg_groove":   "#2C2820",
    "amber":       "#C8832A",
    "amber_lt":    "#E09840",
    "amber_dim":   "#7A4E18",
    "sepia":       "#8B7355",
    "sepia_lt":    "#A08060",
    "sepia_dim":   "#4A3D2A",
    "text_bright": "#E8D8B0",
    "text_main":   "#C4A870",
    "text_dim":    "#7A6840",
    "text_ghost":  "#4A3E28",
    "green":       "#4A8A50",
    "red":         "#8A3A2A",
    "font_heading": ("Georgia", 12, "bold"),
    "font_body":    ("Courier", 10),
    "font_label":   ("Courier", 9),
    "font_small":   ("Courier", 8),
    "font_mono":    ("Courier New", 9),
}


# ══════════════════════════════════════════════════════════════════════
# WIDGET HELPERS
# ══════════════════════════════════════════════════════════════════════

def bg(w):
    try:
        return w.cget("bg")
    except Exception:
        return ST["bg_dark"]

def st_label(parent, text="", style="body", **kw):
    fonts = {"heading": ST["font_heading"], "body": ST["font_body"],
             "label": ST["font_label"], "small": ST["font_small"]}
    kw.setdefault("bg", bg(parent))
    kw.setdefault("fg", ST["text_main"])
    kw.setdefault("font", fonts.get(style, ST["font_body"]))
    return tk.Label(parent, text=text, **kw)

def st_entry(parent, width=20, **kw):
    kw.setdefault("bg", ST["bg_mid"])
    kw.setdefault("fg", ST["text_bright"])
    kw.setdefault("insertbackground", ST["amber"])
    kw.setdefault("relief", "flat")
    kw.setdefault("font", ST["font_body"])
    kw.setdefault("bd", 3)
    return tk.Entry(parent, width=width, **kw)

def st_button(parent, text="", command=None, accent=False, small=False, **kw):
    bg_  = ST["amber"] if accent else ST["bg_lift"]
    fg_  = ST["bg_deep"] if accent else ST["text_main"]
    font = ST["font_small"] if small else ST["font_body"]
    kw.setdefault("relief", "flat"); kw.setdefault("cursor", "hand2")
    kw.setdefault("bd", 0)
    kw.setdefault("padx", 6 if small else 12)
    kw.setdefault("pady", 3 if small else 6)
    return tk.Button(parent, text=text, command=command,
                     bg=bg_, fg=fg_, font=font,
                     activebackground=ST["amber_lt"],
                     activeforeground=ST["bg_deep"], **kw)

def st_scale(parent, from_=0, to=100, **kw):
    kw.setdefault("bg", bg(parent))
    kw.setdefault("troughcolor", ST["bg_groove"])
    kw.setdefault("activebackground", ST["amber_lt"])
    kw.setdefault("highlightthickness", 0)
    kw.setdefault("relief", "flat"); kw.setdefault("sliderrelief", "flat")
    kw.setdefault("bd", 0); kw.setdefault("showvalue", False)
    return tk.Scale(parent, from_=from_, to=to,
                    orient=tk.HORIZONTAL, **kw)

def st_check(parent, text="", variable=None, **kw):
    kw.setdefault("bg", bg(parent))
    kw.setdefault("fg", ST["text_main"])
    kw.setdefault("selectcolor", ST["bg_mid"])
    kw.setdefault("activebackground", bg(parent))
    kw.setdefault("activeforeground", ST["amber"])
    kw.setdefault("font", ST["font_body"])
    kw.setdefault("relief", "flat"); kw.setdefault("bd", 0)
    kw.setdefault("cursor", "hand2")
    return tk.Checkbutton(parent, text=text, variable=variable, **kw)

def st_combo(parent, values=None, width=14, textvariable=None, **kw):
    style = ttk.Style()
    style.theme_use("default")
    style.configure("ST.TCombobox",
        fieldbackground=ST["bg_mid"], background=ST["bg_lift"],
        foreground=ST["text_bright"], selectbackground=ST["amber_dim"],
        selectforeground=ST["text_bright"], arrowcolor=ST["amber"],
        borderwidth=0, relief="flat")
    cb = ttk.Combobox(parent, values=values or [], width=width,
                      style="ST.TCombobox", textvariable=textvariable, **kw)
    cb.configure(font=ST["font_body"])
    return cb

def st_spinbox(parent, from_=0, to=100, width=6, **kw):
    kw.setdefault("bg", ST["bg_mid"]); kw.setdefault("fg", ST["text_bright"])
    kw.setdefault("insertbackground", ST["amber"]); kw.setdefault("relief", "flat")
    kw.setdefault("font", ST["font_body"]); kw.setdefault("bd", 3)
    kw.setdefault("buttonbackground", ST["bg_groove"])
    return tk.Spinbox(parent, from_=from_, to=to, width=width, **kw)

def section_header(parent, text):
    f = tk.Frame(parent, bg=bg(parent))
    f.pack(fill="x", padx=10, pady=(8, 2))
    tk.Label(f, text=text, bg=bg(parent), fg=ST["amber"],
             font=ST["font_label"]).pack(side="left")
    tk.Frame(f, bg=ST["amber_dim"], height=1).pack(
        side="left", fill="x", expand=True, padx=(6, 0), pady=6)

def row_label(parent, text, width=16):
    return tk.Label(parent, text=text, bg=bg(parent),
                    fg=ST["text_dim"], font=ST["font_label"],
                    width=width, anchor="w")


# ══════════════════════════════════════════════════════════════════════
# SCROLLABLE FRAME
# ══════════════════════════════════════════════════════════════════════

class ScrollFrame(tk.Frame):
    def __init__(self, parent, **kw):
        kw.setdefault("bg", ST["bg_dark"])
        super().__init__(parent, **kw)
        self._canvas = tk.Canvas(self, bg=ST["bg_dark"],
                                  highlightthickness=0, bd=0)
        vsb = tk.Scrollbar(self, orient="vertical",
                            command=self._canvas.yview,
                            bg=ST["bg_groove"], troughcolor=ST["bg_dark"],
                            width=7, relief="flat", bd=0)
        hsb = tk.Scrollbar(self, orient="horizontal",
                            command=self._canvas.xview,
                            bg=ST["bg_groove"], troughcolor=ST["bg_dark"],
                            width=7, relief="flat", bd=0)
        self.inner = tk.Frame(self._canvas, bg=ST["bg_dark"])
        self._win_id = self._canvas.create_window(
            (0, 0), window=self.inner, anchor="nw")
        self._canvas.configure(
            yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self.inner.bind("<Configure>", self._on_inner_configure)
        self._canvas.bind("<Configure>", self._on_canvas_configure)
        self._canvas.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self._canvas.bind_all("<MouseWheel>", self._on_mousewheel)

    def _on_inner_configure(self, e):
        self._canvas.configure(scrollregion=self._canvas.bbox("all"))

    def _on_canvas_configure(self, e):
        self._canvas.itemconfig(self._win_id, width=e.width)

    def _on_mousewheel(self, e):
        self._canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")


# ══════════════════════════════════════════════════════════════════════
# CLIP ROW
# ══════════════════════════════════════════════════════════════════════

class ClipRow(tk.Frame):
    def __init__(self, parent, index, remove_cb, preview_cb, **kw):
        kw.setdefault("bg", ST["bg_mid"])
        super().__init__(parent, **kw)
        self.index = index
        self.remove_cb = remove_cb
        self.preview_cb = preview_cb
        self.configure(highlightthickness=1,
                        highlightbackground=ST["bg_groove"])
        self._detail_visible = False
        self._build()

    def _build(self):
        # ── Header ──
        hdr = tk.Frame(self, bg=ST["bg_mid"])
        hdr.pack(fill="x", padx=6, pady=(6, 3))

        self.num_lbl = tk.Label(hdr, text=f"#{self.index:02d}",
                                bg=ST["amber_dim"], fg=ST["amber"],
                                font=ST["font_label"], padx=5, pady=1)
        self.num_lbl.pack(side="left")

        for lbl, attr, w, default in [
            ("Label", "label_var", 10, f"clip_{self.index:02d}"),
            ("Start", "start_var", 6,  "0:00"),
            ("End",   "end_var",   6,  "0:30"),
        ]:
            tk.Label(hdr, text=lbl, bg=ST["bg_mid"],
                     fg=ST["text_dim"], font=ST["font_label"]).pack(side="left", padx=(8,2))
            v = tk.StringVar(value=default)
            setattr(self, attr, v)
            st_entry(hdr, width=w, textvariable=v).pack(side="left")

        st_button(hdr, "✕", command=lambda: self.remove_cb(self),
                  small=True).pack(side="right")
        st_button(hdr, "⊡ Preview", command=lambda: self.preview_cb(self),
                  small=True).pack(side="right", padx=(0, 4))
        self._detail_btn = st_button(hdr, "▸ fx",
                                      command=self._toggle_detail, small=True)
        self._detail_btn.pack(side="right", padx=(0, 4))

        # ── Effects checkboxes ──
        fx_row = tk.Frame(self, bg=ST["bg_mid"])
        fx_row.pack(fill="x", padx=6, pady=(0, 4))

        self.fx_vars = {}
        for fx in ("vintage", "vignette", "grain", "fade_in", "fade_out"):
            v = tk.BooleanVar(value=False)
            self.fx_vars[fx] = v
            cb = st_check(fx_row, text=fx, variable=v)
            cb.configure(bg=ST["bg_mid"])
            cb.pack(side="left", padx=(0, 8))

        # ── Detail panel ──
        self._detail = tk.Frame(self, bg=ST["bg_lift"])
        self._build_sliders()

    def _build_sliders(self):
        f = self._detail

        def panel(title, row, col):
            lf = tk.LabelFrame(f, text=f" {title} ",
                               bg=ST["bg_lift"], fg=ST["amber"],
                               font=ST["font_label"], bd=1, relief="groove",
                               highlightbackground=ST["amber_dim"])
            lf.grid(row=row, column=col, padx=6, pady=4, sticky="nw")
            return lf

        def slider(parent, label, lo, hi, default):
            r = tk.Frame(parent, bg=ST["bg_lift"])
            r.pack(fill="x", padx=4, pady=1)
            tk.Label(r, text=f"{label:<11}", bg=ST["bg_lift"],
                     fg=ST["text_dim"], font=ST["font_small"],
                     width=11, anchor="w").pack(side="left")
            v = tk.IntVar(value=default)
            sc = st_scale(r, from_=lo, to=hi, variable=v, length=100)
            sc.configure(bg=ST["bg_lift"])
            sc.pack(side="left")
            tk.Label(r, textvariable=v, bg=ST["bg_lift"],
                     fg=ST["amber"], font=ST["font_small"],
                     width=4).pack(side="left")
            return v

        vp = panel("Vintage", 0, 0)
        self.warmth_v = slider(vp, "Warmth",   0, 100, 35)
        self.sepia_v  = slider(vp, "Sepia",    0, 100, 55)
        self.fade_v   = slider(vp, "Fade",     0, 100, 25)

        vi = panel("Vignette", 0, 1)
        self.vig_v    = slider(vi, "Angle",    0, 157, 80)

        gp = panel("Grain/Fades", 0, 2)
        self.grain_v  = slider(gp, "Grain",    0, 100, 20)
        self.fi_v     = slider(gp, "Fade In",  0,  30,  4)
        self.fo_v     = slider(gp, "Fade Out", 0,  30,  4)

        cp = panel("Color/Misc", 1, 0)
        self.contrast_v   = slider(cp, "Contrast",   0, 200, 100)
        self.bright_v     = slider(cp, "Brightness",-100,100,   0)
        self.sat_v        = slider(cp, "Saturation", 0, 300, 100)
        self.fps_v        = slider(cp, "FPS",       12,  60,  30)

    def _toggle_detail(self):
        self._detail_visible = not self._detail_visible
        if self._detail_visible:
            self._detail.pack(fill="x", padx=6, pady=(0, 6))
            self._detail_btn.configure(text="▾ fx")
        else:
            self._detail.pack_forget()
            self._detail_btn.configure(text="▸ fx")

    def get_clip_dict(self):
        start = parse_time(self.start_var.get()) or 0.0
        end   = parse_time(self.end_var.get())   or 0.0
        fx = {}
        if self.fx_vars["vintage"].get():
            fx["vintage"] = {"warmth": self.warmth_v.get()/100,
                             "sepia":  self.sepia_v.get()/100,
                             "fade":   self.fade_v.get()/100}
        if self.fx_vars["vignette"].get():
            fx["vignette"] = {"angle": self.vig_v.get()/100,
                              "x0": 0.5, "y0": 0.5}
        if self.fx_vars["grain"].get():
            fx["grain"] = {"strength": self.grain_v.get()}
        if self.fx_vars["fade_in"].get():
            fx["fade_in"]  = self.fi_v.get() / 10
        if self.fx_vars["fade_out"].get():
            fx["fade_out"] = self.fo_v.get() / 10
        if self.contrast_v.get() != 100:
            fx["contrast"] = self.contrast_v.get() / 100
        if self.bright_v.get() != 0:
            fx["brightness"] = self.bright_v.get() / 100
        if self.sat_v.get() != 100:
            fx["saturation"] = self.sat_v.get() / 100
        if self.fps_v.get() != 30:
            fx["fps"] = self.fps_v.get()
        return {"index": self.index,
                "label": self.label_var.get() or f"clip_{self.index:02d}",
                "start": start, "end": end,
                "duration": max(0.0, end - start),
                "effects": fx}

    def update_index(self, i):
        self.index = i
        self.num_lbl.configure(text=f"#{i:02d}")


# ══════════════════════════════════════════════════════════════════════
# CAPTION ROW
# ══════════════════════════════════════════════════════════════════════

class CaptionRow(tk.Frame):
    def __init__(self, parent, index, remove_cb, **kw):
        kw.setdefault("bg", ST["bg_mid"])
        super().__init__(parent, **kw)
        self.index = index
        self.configure(highlightthickness=1,
                        highlightbackground=ST["bg_groove"])

        row = tk.Frame(self, bg=ST["bg_mid"])
        row.pack(fill="x", padx=6, pady=5)

        self.num_lbl = tk.Label(row, text=f"#{index:02d}",
                                bg=ST["sepia_dim"], fg=ST["sepia_lt"],
                                font=ST["font_label"], padx=5, pady=1)
        self.num_lbl.pack(side="left")

        for lbl, attr in [("Hook", "hook_var"), ("Caption", "caption_var")]:
            tk.Label(row, text=lbl, bg=ST["bg_mid"],
                     fg=ST["text_dim"], font=ST["font_label"]).pack(side="left", padx=(8,2))
            v = tk.StringVar()
            setattr(self, attr, v)
            st_entry(row, width=24, textvariable=v).pack(side="left")

        st_button(row, "✕", command=lambda: remove_cb(self),
                  small=True).pack(side="right")

    def get_dict(self):
        return {"hook": self.hook_var.get(),
                "caption": self.caption_var.get()}

    def update_index(self, i):
        self.index = i
        self.num_lbl.configure(text=f"#{i:02d}")


# ══════════════════════════════════════════════════════════════════════
# PREVIEW PANEL
# ══════════════════════════════════════════════════════════════════════

class PreviewPanel(tk.Frame):
    W, H = 200, 356   # 9:16 ratio preview

    def __init__(self, parent, **kw):
        kw.setdefault("bg", ST["bg_dark"])
        super().__init__(parent, **kw)
        self._photo = None
        self._build()

    def _build(self):
        tk.Label(self, text="PREVIEW", bg=ST["bg_dark"],
                 fg=ST["amber_dim"], font=ST["font_label"]).pack(pady=(6,2))
        self.canvas = tk.Canvas(self, width=self.W, height=self.H,
                                bg=ST["bg_deep"], highlightthickness=2,
                                highlightbackground=ST["amber_dim"], bd=0)
        self.canvas.pack(padx=8, pady=2)
        self.status = tk.Label(self, text="Click ⊡ Preview on a clip",
                               bg=ST["bg_dark"], fg=ST["text_ghost"],
                               font=ST["font_small"], wraplength=190,
                               justify="center")
        self.status.pack(pady=4, padx=6)
        self._draw_placeholder()

    def _draw_placeholder(self):
        self.canvas.delete("all")
        cx, cy = self.W // 2, self.H // 2
        for r in range(8, min(cx, cy) - 10, 7):
            c = ST["bg_groove"] if r % 14 < 7 else ST["bg_mid"]
            self.canvas.create_oval(cx-r, cy-r, cx+r, cy+r, outline=c, width=1)
        self.canvas.create_text(cx, cy, text="◎",
                                fill=ST["amber_dim"], font=("Georgia", 20))

    def show_loading(self):
        self.canvas.delete("all")
        cx, cy = self.W // 2, self.H // 2
        self.canvas.create_text(cx, cy, text="rendering…",
                                fill=ST["amber"], font=ST["font_label"])
        self.status.configure(text="Generating preview…", fg=ST["text_dim"])

    def show_frame(self, img_path: Path, hook: str, caption: str):
        if not PIL_AVAILABLE:
            self.status.configure(
                text="pip install pillow for previews", fg=ST["red"])
            return
        try:
            img = Image.open(img_path).convert("RGB")
            # Maintain aspect ratio, fit into preview area
            img.thumbnail((self.W, self.H), Image.LANCZOS)
            iw, ih = img.size
            # Draw text overlays
            draw = ImageDraw.Draw(img)
            if hook:
                draw.rectangle([0, 4, iw, 22], fill=(0, 0, 0, 160))
                draw.text((iw//2, 13), hook[:32], fill="white", anchor="mm")
            if caption:
                draw.rectangle([0, ih-22, iw, ih-4], fill=(0, 0, 0, 160))
                draw.text((iw//2, ih-13), caption[:32], fill="white", anchor="mm")
            self._photo = ImageTk.PhotoImage(img)
            self.canvas.delete("all")
            self.canvas.create_image(self.W//2, self.H//2,
                                     image=self._photo, anchor="center")
            self.status.configure(text="Preview ✓", fg=ST["green"])
        except Exception as e:
            self.status.configure(text=f"Display error: {e}", fg=ST["red"])

    def show_error(self, msg):
        self._draw_placeholder()
        self.status.configure(text=msg, fg=ST["red"])


# ══════════════════════════════════════════════════════════════════════
# PROGRESS BAR
# ══════════════════════════════════════════════════════════════════════

class ProgressBar(tk.Frame):
    def __init__(self, parent, **kw):
        kw.setdefault("bg", ST["bg_deep"])
        super().__init__(parent, **kw)
        self._pct = 0.0
        self.canvas = tk.Canvas(self, height=10, bg=ST["bg_groove"],
                                highlightthickness=0, bd=0)
        self.canvas.pack(fill="x")
        self.canvas.bind("<Configure>", lambda e: self._redraw())

    def set(self, pct):
        self._pct = max(0.0, min(1.0, pct))
        self._redraw()

    def _redraw(self):
        w = self.canvas.winfo_width(); h = 10
        self.canvas.delete("all")
        self.canvas.create_rectangle(0, 0, w, h,
                                     fill=ST["bg_groove"], outline="")
        fw = int(w * self._pct)
        if fw > 0:
            self.canvas.create_rectangle(0, 0, fw, h,
                                         fill=ST["amber_dim"], outline="")
            self.canvas.create_rectangle(0, 0, fw, h//2,
                                         fill=ST["amber"], outline="")
        for p in (0.25, 0.5, 0.75):
            x = int(w * p)
            self.canvas.create_line(x, 0, x, h,
                                    fill=ST["bg_deep"], width=1)


# ══════════════════════════════════════════════════════════════════════
# LOG PANEL
# ══════════════════════════════════════════════════════════════════════

class LogPanel(tk.Frame):
    def __init__(self, parent, **kw):
        kw.setdefault("bg", ST["bg_dark"])
        super().__init__(parent, **kw)
        hdr = tk.Frame(self, bg=ST["bg_dark"])
        hdr.pack(fill="x", padx=8, pady=(4, 2))
        tk.Label(hdr, text="RENDER LOG", bg=ST["bg_dark"],
                 fg=ST["amber"], font=ST["font_label"]).pack(side="left")
        st_button(hdr, "Clear", command=self.clear,
                  small=True).pack(side="right")
        self.text = tk.Text(self, height=8, state="disabled",
                             bg=ST["bg_deep"], fg=ST["text_dim"],
                             font=ST["font_small"], relief="flat",
                             bd=4, insertbackground=ST["amber"],
                             selectbackground=ST["amber_dim"])
        self.text.pack(fill="both", expand=True, padx=8, pady=(0, 6))
        for tag, col in [("ok", ST["green"]), ("err", ST["red"]),
                          ("info", ST["amber"]), ("dim", ST["text_dim"])]:
            self.text.tag_configure(tag, foreground=col)

    def log(self, msg, tag="dim"):
        self.text.configure(state="normal")
        self.text.insert("end", msg + "\n", tag)
        self.text.see("end")
        self.text.configure(state="disabled")

    def clear(self):
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.configure(state="disabled")


# ══════════════════════════════════════════════════════════════════════
# TAB STYLES
# ══════════════════════════════════════════════════════════════════════

def apply_notebook_style():
    s = ttk.Style()
    s.theme_use("default")
    s.configure("ST.TNotebook",
                background=ST["bg_deep"],
                borderwidth=0,
                tabmargins=[0, 0, 0, 0])
    s.configure("ST.TNotebook.Tab",
                background=ST["bg_groove"],
                foreground=ST["text_dim"],
                font=ST["font_label"],
                padding=[14, 6],
                borderwidth=0,
                focuscolor=ST["bg_deep"])
    s.map("ST.TNotebook.Tab",
          background=[("selected", ST["bg_dark"]),
                      ("active",   ST["bg_lift"])],
          foreground=[("selected", ST["amber"]),
                      ("active",   ST["text_main"])])


# ══════════════════════════════════════════════════════════════════════
# MAIN APPLICATION
# ══════════════════════════════════════════════════════════════════════

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Stellar Theory — Clip Generator")
        self.configure(bg=ST["bg_deep"])
        self.minsize(900, 600)
        self.geometry("1100x780")

        # Shared state
        self.video_path    = tk.StringVar()
        self.output_dir    = tk.StringVar(
            value=str(Path.home() / "Desktop" / "output_clips"))
        self.logo_path_var = tk.StringVar()
        self.clip_rows:    list[ClipRow]    = []
        self.caption_rows: list[CaptionRow] = []
        self._render_queue = queue.Queue()
        self._vid_w = self._vid_h = 0

        apply_notebook_style()
        self._build()
        self._poll()

    # ── Top header ────────────────────────────────────────────────────

    def _build(self):
        self._build_header()

        self.notebook = ttk.Notebook(self, style="ST.TNotebook")
        self.notebook.pack(fill="both", expand=True, padx=0, pady=0)

        self._tab_clips    = tk.Frame(self.notebook, bg=ST["bg_dark"])
        self._tab_settings = tk.Frame(self.notebook, bg=ST["bg_dark"])
        self._tab_captions = tk.Frame(self.notebook, bg=ST["bg_dark"])

        self.notebook.add(self._tab_clips,    text="  Clips & Preview  ")
        self.notebook.add(self._tab_captions, text="  Hooks & Captions  ")
        self.notebook.add(self._tab_settings, text="  Settings  ")

        self._build_tab_clips()
        self._build_tab_captions()
        self._build_tab_settings()
        self._build_bottom()

    def _build_header(self):
        hdr = tk.Frame(self, bg=ST["bg_deep"], height=52)
        hdr.pack(fill="x"); hdr.pack_propagate(False)
        tk.Frame(hdr, bg=ST["amber"], width=4).pack(side="left", fill="y")
        tk.Frame(hdr, bg=ST["amber_dim"], width=1).pack(side="left", fill="y")
        inner = tk.Frame(hdr, bg=ST["bg_deep"])
        inner.pack(side="left", fill="both", expand=True, padx=18)
        tk.Label(inner, text="STELLAR THEORY", bg=ST["bg_deep"],
                 fg=ST["amber"], font=("Georgia", 18, "bold")).pack(
                     side="left", pady=12)
        tk.Label(inner, text=" ✦ Clip Generator", bg=ST["bg_deep"],
                 fg=ST["sepia"], font=("Georgia", 12, "italic")).pack(
                     side="left", pady=12)
        tk.Label(inner, text="short-form video tool", bg=ST["bg_deep"],
                 fg=ST["text_ghost"], font=ST["font_small"]).pack(
                     side="right", pady=12)
        tk.Frame(hdr, bg=ST["amber_dim"], width=1).pack(side="right", fill="y")
        tk.Frame(hdr, bg=ST["amber"], width=4).pack(side="right", fill="y")
        tk.Frame(self, bg=ST["amber_dim"], height=1).pack(fill="x")

    # ── Tab 1: Clips & Preview ────────────────────────────────────────

    def _build_tab_clips(self):
        tab = self._tab_clips

        # Horizontal PanedWindow: clips list | preview+log
        pane = tk.PanedWindow(tab, orient=tk.HORIZONTAL,
                               bg=ST["bg_groove"],
                               sashwidth=6, sashrelief="flat",
                               handlesize=8,
                               opaqueresize=True)
        pane.pack(fill="both", expand=True, padx=0, pady=0)

        # ── Left pane: clips list ──
        clips_pane = tk.Frame(pane, bg=ST["bg_dark"])
        pane.add(clips_pane, minsize=300, width=620, stretch="always")

        clip_hdr = tk.Frame(clips_pane, bg=ST["bg_dark"])
        clip_hdr.pack(fill="x", padx=10, pady=(8, 4))
        tk.Label(clip_hdr, text="CLIPS", bg=ST["bg_dark"],
                 fg=ST["amber"], font=ST["font_label"]).pack(side="left")
        for lbl, cmd in [("+ Add", self._add_clip),
                          ("Save YAML", self._save_clips_yaml),
                          ("Load YAML", self._load_clips_yaml)]:
            accent = lbl == "+ Add"
            st_button(clip_hdr, lbl, command=cmd,
                      small=True, accent=accent).pack(
                          side="right", padx=(0, 4))

        self.clips_scroll = ScrollFrame(clips_pane)
        self.clips_scroll.pack(fill="both", expand=True, padx=4, pady=(0, 4))

        # ── Right pane: preview + log (vertical PanedWindow) ──
        right_pane = tk.PanedWindow(pane, orient=tk.VERTICAL,
                                     bg=ST["bg_groove"],
                                     sashwidth=6, sashrelief="flat",
                                     handlesize=8, opaqueresize=True)
        pane.add(right_pane, minsize=220, width=380, stretch="never")

        # Preview section
        preview_outer = tk.Frame(right_pane, bg=ST["bg_dark"])
        right_pane.add(preview_outer, minsize=120, height=420, stretch="always")
        self.preview = PreviewPanel(preview_outer)
        self.preview.pack(fill="both", expand=True, pady=4)

        # Log section
        log_outer = tk.Frame(right_pane, bg=ST["bg_dark"])
        right_pane.add(log_outer, minsize=80, height=180, stretch="always")
        self.log_panel = LogPanel(log_outer)
        self.log_panel.pack(fill="both", expand=True)

    # ── Tab 2: Hooks & Captions ───────────────────────────────────────

    def _build_tab_captions(self):
        tab = self._tab_captions

        cap_hdr = tk.Frame(tab, bg=ST["bg_dark"])
        cap_hdr.pack(fill="x", padx=10, pady=(8, 4))
        tk.Label(cap_hdr, text="HOOKS & CAPTIONS", bg=ST["bg_dark"],
                 fg=ST["amber"], font=ST["font_label"]).pack(side="left")
        for lbl, cmd in [("+ Add", self._add_caption),
                          ("Save YAML", self._save_captions_yaml),
                          ("Load YAML", self._load_captions_yaml)]:
            accent = lbl == "+ Add"
            st_button(cap_hdr, lbl, command=cmd,
                      small=True, accent=accent).pack(
                          side="right", padx=(0, 4))

        tk.Label(tab,
                 text="Captions are assigned to clips in order. "
                      "Use Shuffle in Settings to randomise.",
                 bg=ST["bg_dark"], fg=ST["text_ghost"],
                 font=ST["font_small"]).pack(anchor="w", padx=12)

        self.captions_scroll = ScrollFrame(tab)
        self.captions_scroll.pack(fill="both", expand=True, padx=4, pady=(2, 4))

    # ── Tab 3: Settings ───────────────────────────────────────────────

    def _build_tab_settings(self):
        tab = self._tab_settings

        # Scrollable so it works on small screens
        sf = ScrollFrame(tab)
        sf.pack(fill="both", expand=True)
        p = sf.inner   # write into the inner frame

        # ── Source / Output ──
        section_header(p, "SOURCE VIDEO")
        src_row = tk.Frame(p, bg=ST["bg_dark"])
        src_row.pack(fill="x", padx=10, pady=(2, 4))
        self._video_entry = st_entry(src_row, width=40,
                                      textvariable=self.video_path)
        self._video_entry.pack(side="left", fill="x", expand=True)
        st_button(src_row, "Browse",
                  command=self._browse_video, small=True).pack(
                      side="right", padx=(4, 0))
        self.vid_info = tk.Label(p, text="", bg=ST["bg_dark"],
                                  fg=ST["text_dim"], font=ST["font_small"])
        self.vid_info.pack(anchor="w", padx=12)

        section_header(p, "OUTPUT FOLDER")
        out_row = tk.Frame(p, bg=ST["bg_dark"])
        out_row.pack(fill="x", padx=10, pady=(2, 4))
        st_entry(out_row, width=40,
                 textvariable=self.output_dir).pack(
                     side="left", fill="x", expand=True)
        st_button(out_row, "Browse",
                  command=self._browse_output, small=True).pack(
                      side="right", padx=(4, 0))

        # ── Format ──
        section_header(p, "FORMAT")
        fmt = tk.Frame(p, bg=ST["bg_dark"])
        fmt.pack(fill="x", padx=10, pady=(2, 8))

        def frow(label, widget_fn, row):
            row_label(fmt, label).grid(row=row, column=0, sticky="w", pady=3)
            w = widget_fn()
            w.grid(row=row, column=1, sticky="w", padx=(8, 0), pady=3)
            return w

        self.orientation_var = tk.StringVar(value="vertical")
        frow("Orientation", lambda: st_combo(
            fmt, values=["vertical", "horizontal (keep original)"],
            width=26, textvariable=self.orientation_var), 0)

        self.fit_mode_var = tk.StringVar(value="blur_fill")
        frow("Fit Mode", lambda: st_combo(
            fmt, values=["crop", "fit", "blur_fill"],
            width=12, textvariable=self.fit_mode_var), 1)

        self.crop_offset_var = tk.DoubleVar(value=0.5)
        def _make_crop_row():
            f = tk.Frame(fmt, bg=ST["bg_dark"])
            _sc = st_scale(f, from_=0, to=100, length=130,
                           command=lambda v: self.crop_offset_var.set(
                               round(int(float(v)) / 100, 2)))
            _sc.set(50)
            _sc.pack(side="left")
            tk.Label(f, textvariable=self.crop_offset_var,
                     bg=ST["bg_dark"], fg=ST["amber"],
                     font=ST["font_small"]).pack(side="left", padx=4)
            return f
        row_label(fmt, "Crop X Offset").grid(row=2, column=0, sticky="w", pady=3)
        _make_crop_row().grid(row=2, column=1, sticky="w", padx=(8,0), pady=3)

        self.blur_str_var = tk.IntVar(value=30)
        def _make_blur_row():
            f = tk.Frame(fmt, bg=ST["bg_dark"])
            st_scale(f, from_=0, to=80, variable=self.blur_str_var,
                     length=130).pack(side="left")
            tk.Label(f, textvariable=self.blur_str_var,
                     bg=ST["bg_dark"], fg=ST["amber"],
                     font=ST["font_small"]).pack(side="left", padx=4)
            return f
        row_label(fmt, "Blur Strength").grid(row=3, column=0, sticky="w", pady=3)
        _make_blur_row().grid(row=3, column=1, sticky="w", padx=(8,0), pady=3)

        # ── Text Style ──
        section_header(p, "TEXT STYLE")
        ts = tk.Frame(p, bg=ST["bg_dark"])
        ts.pack(fill="x", padx=10, pady=(2, 8))
        self.style_vars = {}
        fields = [("Hook Font Size", "hook_font_size", "72"),
                  ("Caption Font Size", "caption_font_size", "58"),
                  ("Font Color", "font_color", "white"),
                  ("Box Color", "box_color", "black@0.5"),
                  ("Hook Y", "hook_y", "80"),
                  ("Caption Y", "caption_y", "h-200"),
                  ("Font File", "font_file", "")]
        for i, (lbl, key, default) in enumerate(fields):
            row_label(ts, lbl).grid(row=i, column=0, sticky="w", pady=2)
            v = tk.StringVar(value=default)
            self.style_vars[key] = v
            st_entry(ts, width=22, textvariable=v).grid(
                row=i, column=1, sticky="w", padx=(8,0), pady=2)

        # ── Logo ──
        section_header(p, "LOGO OVERLAY")
        lo = tk.Frame(p, bg=ST["bg_dark"])
        lo.pack(fill="x", padx=10, pady=(2, 8))

        self.logo_enabled = tk.BooleanVar(value=False)
        st_check(lo, text="Enable logo overlay",
                 variable=self.logo_enabled).pack(anchor="w", pady=(0, 4))

        lpath = tk.Frame(lo, bg=ST["bg_dark"])
        lpath.pack(fill="x", pady=2)
        row_label(lpath, "File").pack(side="left")
        st_entry(lpath, width=28,
                 textvariable=self.logo_path_var).pack(
                     side="left", fill="x", expand=True)
        st_button(lpath, "Browse",
                  command=self._browse_logo, small=True).pack(
                      side="right", padx=(4, 0))

        lg = tk.Frame(lo, bg=ST["bg_dark"])
        lg.pack(fill="x", pady=2)

        self.logo_pos_var = tk.StringVar(value="bottom_right")
        row_label(lg, "Position").grid(row=0, column=0, sticky="w", pady=2)
        st_combo(lg, values=["top_left","top_right","bottom_left",
                              "bottom_right","top_center","bottom_center"],
                 width=16, textvariable=self.logo_pos_var).grid(
                     row=0, column=1, sticky="w", padx=(8,0), pady=2)

        self.logo_width_var  = tk.IntVar(value=200)
        self.logo_margin_var = tk.IntVar(value=40)
        self.logo_opacity_var = tk.DoubleVar(value=0.9)
        for i, (lbl, v, lo_, hi_, w) in enumerate([
            ("Width (px)",  self.logo_width_var,   50, 800, 6),
            ("Margin (px)", self.logo_margin_var,   0, 200, 6),
        ], start=1):
            row_label(lg, lbl).grid(row=i, column=0, sticky="w", pady=2)
            st_spinbox(lg, from_=lo_, to=hi_, textvariable=v,
                       width=w).grid(row=i, column=1, sticky="w",
                                      padx=(8,0), pady=2)

        row_label(lg, "Opacity").grid(row=3, column=0, sticky="w", pady=2)
        op_row = tk.Frame(lg, bg=ST["bg_dark"])
        op_row.grid(row=3, column=1, sticky="w", padx=(8,0), pady=2)
        st_scale(op_row, from_=0, to=100, length=110,
                 command=lambda v: self.logo_opacity_var.set(
                     round(int(float(v))/100, 2))).pack(side="left")
        tk.Label(op_row, textvariable=self.logo_opacity_var,
                 bg=ST["bg_dark"], fg=ST["amber"],
                 font=ST["font_small"]).pack(side="left", padx=4)

        # ── Options ──
        section_header(p, "OPTIONS")
        opt = tk.Frame(p, bg=ST["bg_dark"])
        opt.pack(fill="x", padx=10, pady=(2, 16))
        self.shuffle_var = tk.BooleanVar(value=False)
        self.dry_run_var = tk.BooleanVar(value=False)
        st_check(opt, text="Shuffle captions",
                 variable=self.shuffle_var).pack(anchor="w")
        st_check(opt, text="Dry run (no render)",
                 variable=self.dry_run_var).pack(anchor="w")

    # ── Bottom bar ────────────────────────────────────────────────────

    def _build_bottom(self):
        tk.Frame(self, bg=ST["amber_dim"], height=1).pack(fill="x")
        bot = tk.Frame(self, bg=ST["bg_deep"], height=52)
        bot.pack(fill="x"); bot.pack_propagate(False)
        tk.Frame(bot, bg=ST["amber"], width=4).pack(side="left", fill="y")

        inner = tk.Frame(bot, bg=ST["bg_deep"])
        inner.pack(side="left", fill="both", expand=True, padx=14)
        self.progress = ProgressBar(inner)
        self.progress.pack(fill="x", pady=(8, 2))
        self.status_var = tk.StringVar(value="Ready.")
        tk.Label(inner, textvariable=self.status_var, bg=ST["bg_deep"],
                 fg=ST["text_dim"], font=ST["font_small"]).pack(anchor="w")

        btn_row = tk.Frame(bot, bg=ST["bg_deep"])
        btn_row.pack(side="right", padx=14)
        self.render_btn = st_button(
            btn_row, "▶  RENDER CLIPS",
            command=self._start_render, accent=True)
        self.render_btn.configure(font=("Georgia", 12, "bold"), padx=20, pady=8)
        self.render_btn.pack(side="right", pady=8)
        st_button(btn_row, "Preview Frame",
                  command=lambda: self._preview_clip(None)).pack(
                      side="right", padx=(0, 8), pady=8)

    # ── Clip management ───────────────────────────────────────────────

    def _add_clip(self, data=None):
        idx = len(self.clip_rows) + 1
        row = ClipRow(self.clips_scroll.inner, idx,
                      remove_cb=self._remove_clip,
                      preview_cb=self._preview_clip)
        if data:
            row.start_var.set(self._secs_to_mmss(data.get("start", 0)))
            row.end_var.set(self._secs_to_mmss(data.get("end", 30)))
            row.label_var.set(data.get("label", f"clip_{idx:02d}"))
        row.pack(fill="x", padx=4, pady=3)
        self.clip_rows.append(row)

    def _remove_clip(self, row):
        row.pack_forget(); row.destroy()
        self.clip_rows = [r for r in self.clip_rows if r.winfo_exists()]
        for i, r in enumerate(self.clip_rows):
            r.update_index(i + 1)

    def _secs_to_mmss(self, s):
        return f"{int(s)//60}:{int(s)%60:02d}"

    # ── Caption management ────────────────────────────────────────────

    def _add_caption(self, data=None):
        idx = len(self.caption_rows) + 1
        row = CaptionRow(self.captions_scroll.inner, idx,
                         remove_cb=self._remove_caption)
        if data:
            row.hook_var.set(data.get("hook", ""))
            row.caption_var.set(data.get("caption", ""))
        row.pack(fill="x", padx=4, pady=3)
        self.caption_rows.append(row)

    def _remove_caption(self, row):
        row.pack_forget(); row.destroy()
        self.caption_rows = [r for r in self.caption_rows if r.winfo_exists()]
        for i, r in enumerate(self.caption_rows):
            r.update_index(i + 1)

    # ── File browsing ─────────────────────────────────────────────────

    def _browse_video(self):
        p = filedialog.askopenfilename(
            title="Select Video",
            filetypes=[("Video", "*.mp4 *.mov *.avi *.mkv *.webm"),
                        ("All", "*.*")])
        if p:
            self.video_path.set(p)
            self._load_video_info(p)

    def _browse_output(self):
        p = filedialog.askdirectory(title="Select Output Folder")
        if p:
            self.output_dir.set(p)

    def _browse_logo(self):
        p = filedialog.askopenfilename(
            title="Select Logo",
            filetypes=[("Image", "*.png *.jpg *.jpeg"), ("All", "*.*")])
        if p:
            self.logo_path_var.set(p)

    def _load_video_info(self, path):
        try:
            w, h = get_video_dimensions(Path(path))
            self._vid_w, self._vid_h = w, h
            self.vid_info.configure(
                text=f"{w} × {h}  •  {Path(path).name}",
                fg=ST["text_dim"])
        except Exception as e:
            self.vid_info.configure(
                text=f"Could not read: {e}", fg=ST["red"])

    # ── YAML I/O ──────────────────────────────────────────────────────

    def _load_clips_yaml(self):
        p = filedialog.askopenfilename(
            title="Load Clips YAML",
            filetypes=[("YAML","*.yaml *.yml"),("All","*.*")])
        if not p: return
        try:
            cfg = load_config(Path(p))
            for r in list(self.clip_rows): self._remove_clip(r)
            for c in cfg.get("clips", []): self._add_clip(c)
            self.log_panel.log(
                f"Loaded {len(cfg.get('clips',[]))} clips from "
                f"{Path(p).name}", "info")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def _save_clips_yaml(self):
        p = filedialog.asksaveasfilename(
            title="Save Clips YAML",
            defaultextension=".yaml",
            filetypes=[("YAML","*.yaml")])
        if not p: return
        data = {"clips": [r.get_clip_dict() for r in self.clip_rows]}
        with open(p, "w") as f:
            yaml.dump(data, f, default_flow_style=False, allow_unicode=True)
        self.log_panel.log(f"Clips saved to {Path(p).name}", "info")

    def _load_captions_yaml(self):
        p = filedialog.askopenfilename(
            title="Load Captions YAML",
            filetypes=[("YAML","*.yaml *.yml"),("All","*.*")])
        if not p: return
        try:
            cfg = load_config(Path(p))
            for r in list(self.caption_rows): self._remove_caption(r)
            for e in cfg.get("captions", []):
                if isinstance(e, str): e = {"hook":"","caption":e}
                self._add_caption(e)
            self.log_panel.log(
                f"Loaded {len(cfg.get('captions',[]))} captions from "
                f"{Path(p).name}", "info")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def _save_captions_yaml(self):
        p = filedialog.asksaveasfilename(
            title="Save Captions YAML",
            defaultextension=".yaml",
            filetypes=[("YAML","*.yaml")])
        if not p: return
        data = {"style": self._build_style_dict(),
                "captions": [r.get_dict() for r in self.caption_rows]}
        with open(p, "w") as f:
            yaml.dump(data, f, default_flow_style=False, allow_unicode=True)
        self.log_panel.log(f"Captions saved to {Path(p).name}", "info")

    # ── Style / config builders ───────────────────────────────────────

    def _build_style_dict(self):
        style = {k: v.get() for k, v in self.style_vars.items()
                 if v.get()}  # skip empty font_file
        style["fit_mode"]           = self.fit_mode_var.get()
        style["crop_offset_x"]      = round(self.crop_offset_var.get(), 2)
        style["blur_fill_strength"] = self.blur_str_var.get()
        if self.logo_enabled.get() and self.logo_path_var.get():
            style["logo"] = {
                "file":     self.logo_path_var.get(),
                "width":    self.logo_width_var.get(),
                "position": self.logo_pos_var.get(),
                "margin":   self.logo_margin_var.get(),
                "opacity":  round(self.logo_opacity_var.get(), 2),
            }
        return style

    # ── Preview ───────────────────────────────────────────────────────

    def _preview_clip(self, clip_row):
        video = self.video_path.get()
        if not video or not Path(video).exists():
            messagebox.showwarning("No video",
                                   "Select a video file in the Settings tab first.")
            return

        if clip_row is None:
            clip_row = self.clip_rows[0] if self.clip_rows else None

        self.preview.show_loading()
        self.update_idletasks()

        # Switch to clips tab so the user can see the preview
        self.notebook.select(0)

        def _worker():
            try:
                if clip_row:
                    clip   = clip_row.get_clip_dict()
                    midpt  = clip["start"] + clip["duration"] / 2
                else:
                    midpt = 5.0

                out_dir = Path(self.output_dir.get())
                out_dir.mkdir(parents=True, exist_ok=True)
                preview_jpg = out_dir / "_preview_frame.jpg"

                if not self._vid_w:
                    self._vid_w, self._vid_h = get_video_dimensions(Path(video))

                style     = self._build_style_dict()
                vertical  = "horizontal" not in self.orientation_var.get()
                out_w     = int(style.get("output_width",  1080))
                out_h     = int(style.get("output_height", 1920))
                fit       = style.get("fit_mode", "blur_fill")

                # ── Build a single-frame FFmpeg command ──
                # Key fix: filter_complex with split/overlay must use
                # -map to name the final output stream.
                # We output a downscaled JPEG for speed.
                preview_w, preview_h = 540, 960   # half res, faster

                if vertical:
                    if fit == "blur_fill":
                        bs = style.get("blur_fill_strength", 30)
                        fc = (
                            f"[0:v]split=2[bg][fg];"
                            f"[bg]scale={preview_w}:{preview_h}"
                            f":force_original_aspect_ratio=increase,"
                            f"crop={preview_w}:{preview_h},"
                            f"gblur=sigma={bs}[blurred];"
                            f"[fg]scale={preview_w}:{preview_h}"
                            f":force_original_aspect_ratio=decrease[fitted];"
                            f"[blurred][fitted]overlay="
                            f"(W-w)/2:(H-h)/2[out]"
                        )
                        cmd = ["ffmpeg", "-y",
                               "-ss", str(midpt),
                               "-i", video,
                               "-vframes", "1",
                               "-filter_complex", fc,
                               "-map", "[out]",
                               str(preview_jpg)]

                    elif fit == "fit":
                        cmd = ["ffmpeg", "-y",
                               "-ss", str(midpt),
                               "-i", video,
                               "-vframes", "1",
                               "-vf",
                               f"scale={preview_w}:{preview_h}"
                               f":force_original_aspect_ratio=decrease,"
                               f"pad={preview_w}:{preview_h}:"
                               f"(ow-iw)/2:(oh-ih)/2:black",
                               str(preview_jpg)]

                    else:  # crop
                        sr = self._vid_w / max(self._vid_h, 1)
                        tr = preview_w / preview_h
                        if sr > tr:
                            ch = self._vid_h; cw = int(ch * tr)
                        else:
                            cw = self._vid_w; ch = int(cw / tr)
                        ox = int((self._vid_w - cw) *
                                 style.get("crop_offset_x", 0.5))
                        oy = int((self._vid_h - ch) * 0.5)
                        cmd = ["ffmpeg", "-y",
                               "-ss", str(midpt),
                               "-i", video,
                               "-vframes", "1",
                               "-vf",
                               f"crop={cw}:{ch}:{ox}:{oy},"
                               f"scale={preview_w}:{preview_h}",
                               str(preview_jpg)]
                else:
                    # Horizontal — just grab the frame as-is
                    cmd = ["ffmpeg", "-y",
                           "-ss", str(midpt),
                           "-i", video,
                           "-vframes", "1",
                           str(preview_jpg)]

                result = subprocess.run(cmd, capture_output=True, text=True)
                if result.returncode == 0 and preview_jpg.exists():
                    cap = (self.caption_rows[0].get_dict()
                           if self.caption_rows
                           else {"hook": "", "caption": ""})
                    self._render_queue.put(
                        ("preview_ok", preview_jpg, cap))
                else:
                    self._render_queue.put(
                        ("preview_err",
                         result.stderr[-300:] or "Unknown ffmpeg error"))
            except Exception as e:
                self._render_queue.put(("preview_err", str(e)))

        threading.Thread(target=_worker, daemon=True).start()

    # ── Render ────────────────────────────────────────────────────────

    def _start_render(self):
        video = self.video_path.get()
        if not video or not Path(video).exists():
            messagebox.showwarning("No video",
                                   "Select a video file in the Settings tab.")
            return
        if not self.clip_rows:
            messagebox.showwarning("No clips", "Add at least one clip.")
            return

        self.render_btn.configure(state="disabled", text="Rendering…")
        self.log_panel.clear()
        self.progress.set(0)
        self.status_var.set("Starting render…")
        self.notebook.select(0)   # switch to clips tab to show log
        threading.Thread(target=self._render_worker, daemon=True).start()

    def _render_worker(self):
        try:
            video   = Path(self.video_path.get())
            out_dir = Path(self.output_dir.get())
            out_dir.mkdir(parents=True, exist_ok=True)

            style    = self._build_style_dict()
            captions = [r.get_dict() for r in self.caption_rows] \
                       or [{"hook": "", "caption": ""}]
            clips    = [r.get_clip_dict() for r in self.clip_rows]
            vertical = "horizontal" not in self.orientation_var.get()

            if not vertical:
                style["fit_mode"] = "none"
            if self.shuffle_var.get():
                random.shuffle(captions)
            if not self._vid_w:
                self._vid_w, self._vid_h = get_video_dimensions(video)

            total = len(clips)
            ok = fail = 0

            for i, clip in enumerate(clips):
                cap = captions[i % len(captions)]
                out_path = out_dir / f"{clip['label']}.mp4"

                self._render_queue.put(("log",
                    f"Clip {i+1}/{total}: {clip['label']}  "
                    f"[{self._secs_to_mmss(clip['start'])} → "
                    f"{self._secs_to_mmss(clip['end'])}]", "info"))

                cmd = build_ffmpeg_command(
                    video_path=video, output_path=out_path,
                    start=clip["start"], duration=clip["duration"],
                    hook=cap.get("hook", ""),
                    caption=cap.get("caption", ""),
                    video_width=self._vid_w, video_height=self._vid_h,
                    style=style, effects=clip.get("effects", {}))

                if self.dry_run_var.get():
                    self._render_queue.put(
                        ("log", "  DRY: " + " ".join(cmd), "dim"))
                    ok += 1
                else:
                    res = subprocess.run(cmd, capture_output=True, text=True)
                    if res.returncode == 0:
                        sz = out_path.stat().st_size / (1024 * 1024)
                        self._render_queue.put(
                            ("log", f"  ✓ {clip['label']}.mp4 "
                                    f"({sz:.1f} MB)", "ok"))
                        ok += 1
                    else:
                        self._render_queue.put(
                            ("log", f"  ✗ {res.stderr[-180:]}", "err"))
                        fail += 1

                self._render_queue.put(("progress", (i + 1) / total))

            self._render_queue.put(("log",
                f"\n{'─'*36}\n"
                f"Done — {ok} rendered, {fail} failed.\n"
                f"Output: {out_dir.resolve()}", "info"))
            self._render_queue.put(("done",))

        except Exception as e:
            self._render_queue.put(("log", f"Error: {e}", "err"))
            self._render_queue.put(("done",))

    # ── Queue poll ────────────────────────────────────────────────────

    def _poll(self):
        try:
            while True:
                msg = self._render_queue.get_nowait()
                k = msg[0]
                if k == "log":
                    self.log_panel.log(msg[1], msg[2])
                elif k == "progress":
                    self.progress.set(msg[1])
                    self.status_var.set(
                        f"Rendering… {int(msg[1]*100)}%")
                elif k == "done":
                    self.render_btn.configure(
                        state="normal", text="▶  RENDER CLIPS")
                    self.status_var.set("Complete.")
                    self.progress.set(1.0)
                elif k == "preview_ok":
                    self.preview.show_frame(
                        msg[1], msg[2].get("hook",""),
                        msg[2].get("caption",""))
                elif k == "preview_err":
                    self.preview.show_error(msg[1])
        except queue.Empty:
            pass
        self.after(80, self._poll)


# ══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    App().mainloop()
