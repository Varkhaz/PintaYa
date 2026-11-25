"""PintaYa v0.01 - programa de pintura para niños (desde 2 años).

Abre cualquier dibujo en blanco y negro (jpg, png, bmp, gif, tif, heic, pdf...)
o pega una captura, lo prepara automaticamente y permite pintarlo con el bote
sin que el color se salga ni deje huecos blancos.
"""
import os
import sys
import math
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, colorchooser

import numpy as np
import cv2
from PIL import Image, ImageOps, ImageGrab

try:  # HEIC / HEIF (fotos de iPhone)
    import pillow_heif
    pillow_heif.register_heif_opener()
except Exception:  # pragma: no cover
    pass

from engine import PaintDoc, LONG_SIDE_MAX, MAX_SIDE

APP_NAME = "PintaYa"
VERSION = "0.01"

# 48 colores: 4 filas x 12 columnas
PALETTE = [
    "#FF0000", "#FF4500", "#FF8C00", "#FFC000", "#FFE800", "#B5E61D",
    "#22B14C", "#00A99D", "#00B7EF", "#0072BC", "#3F48CC", "#A349A4",

    "#FF9999", "#FFB380", "#FFD199", "#FFE699", "#FFF799", "#D9F2A0",
    "#99E6B3", "#99E6DC", "#99DFF7", "#99C2E6", "#A3A8E6", "#D6A3D9",

    "#FF69B4", "#FF1493", "#C71585", "#8B0000", "#A52A2A", "#B97A57",
    "#D2A679", "#F5CBA7", "#FFE0BD", "#E8B88A", "#C68642", "#8D5524",

    "#000000", "#404040", "#7F7F7F", "#A6A6A6", "#C3C3C3", "#E0E0E0",
    "#FFFFFF", "#003366", "#006400", "#4B0082", "#800000", "#5C4033",
]
COLS, ROWS = 12, 4
CELL = 26
RC = 22     # lado de las muestras recientes (3 columnas x 4 filas)
assert len(PALETTE) == COLS * ROWS == 48

SIZES = {  # grosor en pixeles de PANTALLA (se convierte segun el zoom)
    "pen": [2, 4, 6, 9],
    "brush": [6, 12, 20, 32],
    "highlighter": [14, 24, 36, 52],
    "eraser": [10, 20, 32, 50],
}
DEFAULT_SIZE_IDX = {"pen": 1, "brush": 1, "highlighter": 1, "eraser": 1}
STROKE_TOOLS = ("pen", "brush", "highlighter", "eraser")
PAINT_TOOLS = ("bucket",) + STROKE_TOOLS
SEL_TOOLS = ("sel_free", "sel_rect", "sel_ellipse")
TOOL_NAMES = {
    "bucket": "Bote", "pen": "Pluma", "highlighter": "Resaltador", "eraser": "Borrador",
    "brush": "Pincel", "picker": "Gotero",
    "sel_free": "Libre", "sel_rect": "Cuadro", "sel_ellipse": "Círculo",
}

BG = "#EEF2F7"
SEL = "#FFD84D"
CANVAS_BG = "#9AA5B1"
SB = 16                       # ancho de las barras de desplazamiento
ZOOM_LEVELS = [0.05, 0.1, 0.15, 0.2, 0.25, 0.33, 0.5, 0.67, 1, 2, 3, 4, 5, 6, 7, 8, 10, 12, 16]
ALT_MASK = 0x20000 if sys.platform == "win32" else (0x10 if sys.platform == "darwin" else 0x8)
CTRL_MASK, SHIFT_MASK = 0x4, 0x1
HANDLES = ("nw", "n", "ne", "e", "se", "s", "sw", "w")
if sys.platform == "win32":
    HANDLE_CURSOR = {"nw": "size_nw_se", "se": "size_nw_se", "ne": "size_ne_sw", "sw": "size_ne_sw",
                     "n": "size_ns", "s": "size_ns", "e": "size_we", "w": "size_we"}
else:
    HANDLE_CURSOR = {"nw": "top_left_corner", "se": "bottom_right_corner", "ne": "top_right_corner",
                     "sw": "bottom_left_corner", "n": "sb_v_double_arrow", "s": "sb_v_double_arrow",
                     "e": "sb_h_double_arrow", "w": "sb_h_double_arrow"}


def is_alt(state):
    return bool(state & ALT_MASK)


# ----------------------------------------------------------------- iconos
def ic_new(c, w, h, fg):
    c.create_polygon(12, 6, 32, 6, 42, 16, 42, 42, 12, 42, fill="white", outline=fg, width=2)
    c.create_polygon(32, 6, 32, 16, 42, 16, fill="#D5DCE5", outline=fg)

def ic_open(c, w, h, fg):
    c.create_polygon(8, 14, 20, 14, 24, 19, 44, 19, 44, 36, 8, 36, fill="#F6C343", outline=fg, width=2)
    c.create_polygon(8, 36, 14, 24, 50, 24, 44, 36, fill="#FFD966", outline=fg, width=2)

def ic_insert(c, w, h, fg):
    c.create_rectangle(8, 10, 38, 36, fill="#BFE3F5", outline=fg, width=2)
    c.create_polygon(10, 34, 20, 20, 28, 30, 32, 25, 37, 34, fill="#4CAF50", outline=fg)
    c.create_oval(28, 13, 34, 19, fill="#FFD21F", outline=fg)
    c.create_oval(30, 28, 50, 48, fill="#3B7DD8", outline="white", width=2)
    c.create_line(40, 32, 40, 44, 34, 38, 46, 38, fill="white", width=3)

def ic_paste(c, w, h, fg):
    c.create_rectangle(12, 10, 40, 38, fill="#C8A26B", outline=fg, width=2)
    c.create_rectangle(19, 6, 33, 15, fill="#9AA5B1", outline=fg, width=2)
    c.create_rectangle(17, 18, 36, 34, fill="white", outline=fg)
    c.create_line(20, 24, 33, 24, 20, 29, 30, 29, fill=fg)

def ic_save(c, w, h, fg):
    c.create_rectangle(10, 8, 42, 38, fill="#3B7DD8", outline=fg, width=2)
    c.create_rectangle(16, 8, 36, 20, fill="#E8EEF7", outline=fg)
    c.create_rectangle(16, 26, 36, 38, fill="white", outline=fg)
    c.create_rectangle(29, 11, 33, 17, fill=fg)

def ic_undo(c, w, h, fg):
    c.create_arc(12, 12, 42, 40, start=90, extent=-200, style="arc", outline="#3B7DD8", width=5)
    c.create_polygon(10, 14, 24, 6, 24, 22, fill="#3B7DD8", outline="#3B7DD8")

def ic_redo(c, w, h, fg):
    c.create_arc(10, 12, 40, 40, start=90, extent=200, style="arc", outline="#3B7DD8", width=5)
    c.create_polygon(42, 14, 28, 6, 28, 22, fill="#3B7DD8", outline="#3B7DD8")

def ic_bucket(c, w, h, fg):
    c.create_polygon(10, 20, 30, 12, 38, 28, 18, 36, fill="#8896A5", outline=fg, width=2)
    c.create_polygon(10, 20, 30, 12, 32, 17, 14, 25, fill="#C5CFDA", outline=fg)
    c.create_arc(8, 4, 28, 24, start=20, extent=120, style="arc", outline=fg, width=2)
    c.create_oval(40, 30, 48, 42, fill="#2E86DE", outline="#1B5FA8")
    c.create_polygon(44, 24, 40, 33, 48, 33, fill="#2E86DE", outline="#1B5FA8")

def ic_pen(c, w, h, fg):
    c.create_polygon(36, 6, 44, 14, 20, 38, 10, 42, 14, 32, fill="#F4C542", outline=fg, width=2)
    c.create_polygon(14, 32, 20, 38, 10, 42, fill="#F2D3A4", outline=fg)
    c.create_polygon(10, 42, 12, 37, 15, 40, fill=fg)
    c.create_polygon(36, 6, 40, 2, 48, 10, 44, 14, fill="#E87979", outline=fg, width=2)

def ic_highlighter(c, w, h, fg):
    c.create_polygon(30, 6, 46, 22, 30, 38, 16, 24, fill="#FFE94D", outline=fg, width=2)
    c.create_polygon(16, 24, 30, 38, 22, 44, 8, 40, fill="#FFD21F", outline=fg, width=2)
    c.create_line(6, 46, 24, 46, fill="#FFE94D", width=4)

def ic_eraser(c, w, h, fg):
    c.create_polygon(8, 30, 28, 8, 46, 24, 28, 44, 16, 44, fill="#F59AB8", outline=fg, width=2)
    c.create_polygon(8, 30, 20, 40, 16, 44, fill="#9AA5B1", outline=fg)
    c.create_line(20, 40, 38, 16, fill=fg)

def ic_brush(c, w, h, fg):
    c.create_polygon(46, 4, 50, 8, 28, 30, 22, 24, fill="#B97A57", outline=fg, width=2)
    c.create_polygon(22, 24, 28, 30, 20, 38, 12, 44, 8, 42, 10, 34, fill="#E8414E", outline=fg, width=2)

def ic_picker(c, w, h, fg):
    c.create_polygon(32, 8, 44, 20, 40, 24, 28, 12, fill="#D5DCE5", outline=fg, width=2)
    c.create_polygon(36, 4, 48, 16, 44, 20, 32, 8, fill="#3B7DD8", outline=fg, width=2)
    c.create_polygon(28, 12, 40, 24, 18, 40, 12, 40, 12, 34, fill="#BFE3F5", outline=fg, width=2)
    c.create_polygon(12, 34, 12, 40, 18, 40, fill="#E8414E", outline=fg)
    c.create_polygon(8, 44, 12, 40, 14, 44, fill="#E8414E", outline="")

def ic_sel_free(c, w, h, fg):
    c.create_polygon(10, 28, 14, 14, 26, 10, 38, 16, 42, 28, 32, 38, 22, 34, 16, 40,
                     fill="", outline=fg, width=2, dash=(4, 3), smooth=True)

def ic_sel_rect(c, w, h, fg):
    c.create_rectangle(8, 12, 44, 38, outline=fg, width=2, dash=(4, 3))

def ic_sel_ellipse(c, w, h, fg):
    c.create_oval(8, 12, 44, 38, outline=fg, width=2, dash=(4, 3))

def ic_cut(c, w, h, fg):
    c.create_line(14, 8, 36, 34, fill=fg, width=3)
    c.create_line(38, 8, 16, 34, fill="#8896A5", width=3)
    c.create_oval(10, 32, 20, 44, outline="#E8414E", width=3)
    c.create_oval(32, 32, 42, 44, outline="#E8414E", width=3)

def ic_copy(c, w, h, fg):
    c.create_rectangle(10, 8, 32, 32, fill="white", outline=fg, width=2)
    c.create_rectangle(20, 18, 42, 42, fill="#E8EEF7", outline=fg, width=2)

def ic_delete(c, w, h, fg):
    c.create_line(12, 12, 40, 40, fill="#E8414E", width=7, capstyle="round")
    c.create_line(40, 12, 12, 40, fill="#E8414E", width=7, capstyle="round")


class _Shift:
    """Envuelve un Canvas para dibujar un icono con etiqueta 'ic' (luego se centra)."""
    def __init__(self, c):
        self.c = c

    def __getattr__(self, name):
        fn = getattr(self.c, name)

        def call(*a, **k):
            k["tags"] = "ic"
            return fn(*a, **k)
        return call


class IconButton(tk.Canvas):
    def __init__(self, master, icon, label, command, w=56, h=62):
        super().__init__(master, width=w, height=h, bg=BG, highlightthickness=0, cursor="hand2")
        self.icon, self.label, self.command = icon, label, command
        self.selected = False
        self.enabled = True
        self._bw, self._bh = w, h
        self.bind("<Button-1>", lambda e: self.enabled and self.command())
        self.redraw()

    def redraw(self):
        self.delete("all")
        self.create_rectangle(2, 2, self._bw - 2, self._bh - 2, fill=SEL if self.selected else BG,
                              outline="#C9A227" if self.selected else "#D5DCE5", width=2)
        self.icon(_Shift(self), 52, 48, "#2D3748")
        self.move("ic", (self._bw - 52) // 2, 0)
        self.create_text(self._bw // 2, self._bh - 8, text=self.label,
                         fill="#2D3748" if self.enabled else "#9AA5B1", font=("Segoe UI", 8, "bold"))
        if not self.enabled:
            self.create_rectangle(2, 2, self._bw - 2, self._bh - 2, fill=BG, outline="", stipple="gray50")

    def set_selected(self, v):
        if self.selected != v:
            self.selected = v
            self.redraw()

    def set_enabled(self, v):
        if self.enabled != v:
            self.enabled = v
            self.configure(cursor="hand2" if v else "arrow")
            self.redraw()


# ------------------------------------------------------------------ app
class PintaYa(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_NAME} {VERSION}")
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"{min(1280, sw - 40)}x{min(840, sh - 80)}+10+10")
        self.minsize(900, 640)
        self.configure(bg=BG)

        self.doc = PaintDoc(1200, 800)
        self.tool = "bucket"
        self.prev_tool = "bucket"
        self.size_idx = dict(DEFAULT_SIZE_IDX)
        self.color_idx = 0
        self.rgb = self._hex(PALETTE[0])
        self.recent = []
        self.z, self.sx, self.sy = 1.0, 0, 0
        self.fit = True
        self.vw = self.vh = 100
        self.ox = self.oy = 0
        self.photo = None
        self.ph = (0, 0, 0, 0)
        self.vis = (0, 0, 0, 0)
        self.drag = None
        self.painting = False
        self.cursor_item = None
        self.clip = None
        self.clip_sig = None
        self.threshold = tk.IntVar(value=128)

        self._build_ribbon()
        self._build_body()
        self._build_status()
        self._bind_keys()
        self.select_tool("bucket")
        self.after(80, self.view_changed)

    @staticmethod
    def _hex(h):
        return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))

    # --------------------------------------------------------------- interfaz
    def _group(self, parent, title):
        f = tk.Frame(parent, bg=BG)
        f.pack(side="left", padx=6, pady=(4, 0), anchor="n")
        body = tk.Frame(f, bg=BG)
        body.pack()
        tk.Label(f, text=title, bg=BG, fg="#5A6778", font=("Segoe UI", 8)).pack(pady=(2, 0))
        tk.Frame(parent, bg="#CBD3DD", width=1).pack(side="left", fill="y", pady=6)
        return body

    def _build_ribbon(self):
        rib = tk.Frame(self, bg=BG)
        rib.pack(side="top", fill="x")

        g = self._group(rib, "Archivo")
        for icon, label, cmd in ((ic_new, "Nuevo", self.new_canvas), (ic_open, "Abrir", self.open_dialog),
                                 (ic_insert, "Insertar", self.insert_dialog), (ic_paste, "Pegar", self.paste_clipboard),
                                 (ic_save, "Guardar", self.save_dialog)):
            IconButton(g, icon, label, cmd).pack(side="left", padx=1)

        g = self._group(rib, "Historial")
        self.btn_undo = IconButton(g, ic_undo, "Atrás", self.undo)
        self.btn_redo = IconButton(g, ic_redo, "Adelante", self.redo)
        self.btn_undo.pack(side="left", padx=1)
        self.btn_redo.pack(side="left", padx=1)

        g = self._group(rib, "Selección")
        self.btn_cut = IconButton(g, ic_cut, "Cortar", self.sel_cut)
        self.btn_copy = IconButton(g, ic_copy, "Copiar", self.sel_copy)
        self.btn_del = IconButton(g, ic_delete, "Borrar", self.sel_delete)
        for b in (self.btn_cut, self.btn_copy, self.btn_del):
            b.pack(side="left", padx=1)

        g = self._group(rib, "Colores")
        self.cur_color = tk.Canvas(g, width=54, height=ROWS * CELL + 2, bg=BG, highlightthickness=0)
        self.cur_color.pack(side="left", padx=(0, 4))
        self.pal = tk.Canvas(g, width=COLS * CELL + 2, height=ROWS * CELL + 2, bg=BG, highlightthickness=0,
                             cursor="hand2")
        self.pal.pack(side="left")
        self.pal.bind("<Button-1>", self._palette_click)
        self.rec = tk.Canvas(g, width=3 * RC + 10, height=ROWS * CELL + 2, bg=BG, highlightthickness=0,
                             cursor="hand2")
        self.rec.pack(side="left", padx=(4, 0))
        self.rec.bind("<Button-1>", self._recent_click)
        tk.Button(g, text="+", font=("Segoe UI", 12, "bold"), width=2, command=self.pick_custom_color,
                  relief="groove", bg="white").pack(side="left", padx=(6, 0), anchor="n")
        self._draw_palette()
        self._draw_current_color()
        self._draw_recent()

    def _build_body(self):
        body = tk.Frame(self, bg=BG)
        body.pack(side="top", fill="both", expand=True)
        # panel izquierdo (como el Paint clasico)
        left = tk.Frame(body, bg=BG, width=130)
        left.pack(side="left", fill="y", padx=(4, 2))
        left.pack_propagate(False)
        self.tool_btns = {}
        icons = {"bucket": ic_bucket, "pen": ic_pen, "highlighter": ic_highlighter, "eraser": ic_eraser,
                 "brush": ic_brush, "picker": ic_picker, "sel_free": ic_sel_free, "sel_rect": ic_sel_rect,
                 "sel_ellipse": ic_sel_ellipse}

        def block(title, tools):
            tk.Label(left, text=title, bg=BG, fg="#5A6778", font=("Segoe UI", 8)).pack(pady=(4, 0))
            fr = tk.Frame(left, bg=BG)
            fr.pack()
            for i, t in enumerate(tools):
                b = IconButton(fr, icons[t], TOOL_NAMES[t], lambda t=t: self.select_tool(t), w=60, h=60)
                b.grid(row=i // 2, column=i % 2, padx=1, pady=1)
                self.tool_btns[t] = b
        block("Herramientas", ["bucket", "pen", "highlighter", "eraser", "brush", "picker"])
        block("Seleccionar", ["sel_free", "sel_rect", "sel_ellipse"])
        tk.Label(left, text="Grosor", bg=BG, fg="#5A6778", font=("Segoe UI", 8)).pack(pady=(4, 0))
        self.size_canvases = []
        for i in range(4):
            c = tk.Canvas(left, width=120, height=30, bg=BG, highlightthickness=0, cursor="hand2")
            c.pack(pady=1)
            c.bind("<Button-1>", lambda e, i=i: self.select_size(i))
            self.size_canvases.append(c)
        # area del lienzo con barras
        self.area = tk.Frame(body, bg=CANVAS_BG)
        self.area.pack(side="left", fill="both", expand=True)
        self.area.grid_rowconfigure(0, weight=1)
        self.area.grid_columnconfigure(0, weight=1)
        self.area.grid_propagate(False)
        self.cv = tk.Canvas(self.area, bg=CANVAS_BG, highlightthickness=0, cursor="hand2")
        self.cv.grid(row=0, column=0, sticky="nsew")
        self.vsb = tk.Scrollbar(self.area, orient="vertical", command=self._yview)
        self.hsb = tk.Scrollbar(self.area, orient="horizontal", command=self._xview)
        self.vsb.grid(row=0, column=1, sticky="ns")
        self.hsb.grid(row=1, column=0, sticky="ew")
        self.vsb.grid_remove()
        self.hsb.grid_remove()
        self._sb_state = (False, False)
        self.area.bind("<Configure>", lambda e: self.view_changed())
        self.cv.bind("<ButtonPress-1>", self._press)
        self.cv.bind("<B1-Motion>", self._drag)
        self.cv.bind("<ButtonRelease-1>", self._release)
        self.cv.bind("<Motion>", self._hover)
        self.cv.bind("<Leave>", lambda e: self._hide_cursor())

    def _build_status(self):
        st = tk.Frame(self, bg="#DDE3EA")
        st.pack(side="bottom", fill="x")
        self.status = tk.Label(st, text="Abre una imagen o pega una captura (Ctrl+V)", bg="#DDE3EA", anchor="w",
                               font=("Segoe UI", 9))
        self.status.pack(side="left", padx=8, pady=3)
        lab = dict(bg="#DDE3EA", font=("Segoe UI", 9))
        tk.Label(st, text="Más", fg="#5A6778", **lab).pack(side="right", padx=(2, 8))
        s = tk.Scale(st, from_=60, to=200, orient="horizontal", variable=self.threshold, showvalue=False, length=130,
                     bg="#DDE3EA", highlightthickness=0, sliderlength=16)
        s.pack(side="right")
        s.bind("<ButtonRelease-1>", lambda e: self.reprocess())
        tk.Label(st, text="Menos", fg="#5A6778", **lab).pack(side="right", padx=(8, 2))
        tk.Label(st, text="Detectar líneas:", **lab).pack(side="right")
        tk.Button(st, text="Ajustar", command=self.zoom_fit, relief="groove", font=("Segoe UI", 8)).pack(
            side="right", padx=8)
        self.zoom_lbl = tk.Label(st, text="", **lab)
        self.zoom_lbl.pack(side="right", padx=4)

    def _bind_keys(self):
        def key(seq, fn):
            # con Bloq Mayús activo Tk entrega el keysym en mayuscula: enlazar ambos
            for s in (seq, seq[:-2] + seq[-2:].upper()):
                self.bind(s, lambda e, fn=fn: fn())
        for seq, fn in (("<Control-y>", self.redo), ("<Control-v>", self.paste_clipboard),
                        ("<Control-o>", self.open_dialog), ("<Control-s>", self.save_dialog),
                        ("<Control-x>", self.sel_cut), ("<Control-c>", self.sel_copy), ("<Control-n>", self.new_canvas)):
            key(seq, fn)
        for seq, fn in (("<Delete>", self.sel_delete), ("<Escape>", self.commit_sel), ("<Return>", self.commit_sel),
                        ("<Control-0>", self.zoom_fit), ("<Control-1>", lambda: self.set_zoom(1.0))):
            self.bind(seq, lambda e, fn=fn: fn())
        for seq in ("<Control-z>", "<Control-Z>"):   # Ctrl+Z deshace; Ctrl+Mayús+Z rehace (con o sin Bloq Mayús)
            self.bind(seq, lambda e: self.redo() if e.state & SHIFT_MASK else self.undo())
        self.bind("<KeyRelease-Alt_L>", lambda e: "break")
        self.bind("<KeyRelease-Alt_R>", lambda e: "break")
        self.bind_all("<MouseWheel>", lambda e: self._wheel_event(e.delta, e.state))
        self.bind_all("<Button-4>", lambda e: self._wheel_event(120, e.state))
        self.bind_all("<Button-5>", lambda e: self._wheel_event(-120, e.state))

    # ----------------------------------------------------------- paleta / color
    def _draw_palette(self):
        self.pal.delete("all")
        for i, hx in enumerate(PALETTE):
            r, c = divmod(i, COLS)
            x, y = c * CELL + 1, r * CELL + 1
            sel = i == self.color_idx
            self.pal.create_rectangle(x + 1, y + 1, x + CELL - 1, y + CELL - 1, fill=hx,
                                      outline="#000000" if sel else "#8A94A1", width=3 if sel else 1)
            if sel:
                self.pal.create_rectangle(x + 4, y + 4, x + CELL - 4, y + CELL - 4,
                                          outline="white" if sum(self._hex(hx)) < 380 else "black")

    def _draw_recent(self):
        self.rec.delete("all")
        self.rec.create_text(3 * RC // 2 + 5, 7, text="Muestras", fill="#5A6778", font=("Segoe UI", 7))
        for i in range(12):
            r, c = divmod(i, 3)
            x, y = c * RC + 5, r * RC + 15
            col = self.recent[i] if i < len(self.recent) else None
            self.rec.create_rectangle(x, y, x + RC - 2, y + RC - 2,
                                      fill="#%02x%02x%02x" % col if col else BG,
                                      outline="#8A94A1" if col else "#D5DCE5")

    def _palette_click(self, e):
        c, r = (e.x - 1) // CELL, (e.y - 1) // CELL
        if 0 <= c < COLS and 0 <= r < ROWS:
            self.set_color(self._hex(PALETTE[r * COLS + c]), r * COLS + c)

    def _recent_click(self, e):
        c, r = (e.x - 5) // RC, (e.y - 15) // RC
        i = r * 3 + c
        if 0 <= c < 3 and 0 <= r and 0 <= i < len(self.recent):
            self.set_color(self.recent[i], -1)

    def set_color(self, rgb, idx=-1):
        self.rgb = tuple(int(v) for v in rgb)
        self.color_idx = idx
        self._draw_palette()
        self._draw_current_color()
        if self.tool == "eraser":
            self.select_tool("brush")
        elif self.tool == "picker" or self.tool in SEL_TOOLS:
            self.select_tool(self.prev_tool)

    def _draw_current_color(self):
        c = self.cur_color
        c.delete("all")
        c.create_rectangle(4, 4, 50, 70, fill="#%02x%02x%02x" % self.rgb, outline="#2D3748", width=3)
        c.create_text(27, 88, text="Color", fill="#2D3748", font=("Segoe UI", 8, "bold"))

    def pick_custom_color(self):
        res = colorchooser.askcolor(color="#%02x%02x%02x" % self.rgb, title="Elegir color")
        if res and res[0]:
            self.set_color(res[0], -1)

    def add_recent(self, rgb):
        rgb = tuple(int(v) for v in rgb)
        if rgb in self.recent:
            self.recent.remove(rgb)
        self.recent.insert(0, rgb)
        del self.recent[12:]
        self._draw_recent()

    # ---------------------------------------------------- herramientas / grosor
    def select_tool(self, t):
        if t != self.tool and self.tool in SEL_TOOLS and t not in SEL_TOOLS:
            self.commit_sel()
        if t in PAINT_TOOLS:
            self.prev_tool = t
        self.tool = t
        for k, b in self.tool_btns.items():
            b.set_selected(k == t)
        self._draw_sizes()
        self._set_tool_cursor()
        if t not in STROKE_TOOLS:
            self._hide_cursor()

    def _set_tool_cursor(self):
        t = self.tool
        self.cv.configure(cursor="none" if t in STROKE_TOOLS else ("hand2" if t == "bucket" else "crosshair"))

    def select_size(self, i):
        if self.tool in SIZES:
            self.size_idx[self.tool] = i
            self._draw_sizes()

    def _draw_sizes(self):
        sizes = SIZES.get(self.tool)
        for i, c in enumerate(self.size_canvases):
            c.delete("all")
            sel = sizes is not None and i == self.size_idx[self.tool]
            c.create_rectangle(2, 2, 118, 28, fill=SEL if sel else BG, outline="#C9A227" if sel else "#D5DCE5", width=2)
            if sizes is None:
                c.create_line(20, 15, 100, 15, fill="#C5CDD7", width=2)
                continue
            d = min(sizes[i], 22)
            c.create_line(20, 15, 100, 15, fill="#2D3748", width=d, capstyle="round")

    # ------------------------------------------------------------ vista / zoom
    def z_max(self):
        return min(16.0, MAX_SIDE / max(self.doc.w, self.doc.h))

    def _fit_zoom(self):
        aw, ah = max(60, self.area.winfo_width()), max(60, self.area.winfo_height())
        return max(0.02, min(1.0, (aw - 16) / self.doc.w, (ah - 16) / self.doc.h))

    def zoom_fit(self):
        self.fit = True
        self.view_changed()

    def set_zoom(self, z, ax=None, ay=None):
        z = max(0.02, min(self.z_max(), z))
        if ax is None:
            ax, ay = self.vw / 2, self.vh / 2
        px, py = (ax - self.ox + self.sx) / self.z, (ay - self.oy + self.sy) / self.z   # punto imagen bajo el cursor
        self.fit = False
        self.z = z
        self._compute_view()
        self.sx = int(round(px * z - ax + self.ox))
        self.sy = int(round(py * z - ay + self.oy))
        self.view_changed(keep=True)

    def zoom_step(self, direction, ax, ay):
        zmax = self.z_max()
        levels = sorted({l for l in ZOOM_LEVELS if l <= zmax + 1e-9})
        cur = self.z
        if direction > 0:
            nxt = next((l for l in levels if l > cur * 1.001), levels[-1])
        else:
            nxt = next((l for l in reversed(levels) if l < cur * 0.999), levels[0])
        self.set_zoom(nxt, ax, ay)

    def _compute_view(self):
        aw, ah = max(60, self.area.winfo_width()), max(60, self.area.winfo_height())
        if self.fit:
            self.z = self._fit_zoom()
        W, H = self.doc.w * self.z, self.doc.h * self.z
        need_v, need_h = H > ah, W > aw
        if need_v:
            need_h = W > aw - SB
        if need_h:
            need_v = H > ah - SB
        self.vw = aw - (SB if need_v else 0)
        self.vh = ah - (SB if need_h else 0)
        self.ox = int((self.vw - W) // 2) if W <= self.vw else 0
        self.oy = int((self.vh - H) // 2) if H <= self.vh else 0
        self.sx = 0 if W <= self.vw else int(min(max(0, self.sx), W - self.vw))
        self.sy = 0 if H <= self.vh else int(min(max(0, self.sy), H - self.vh))
        if (need_v, need_h) != self._sb_state:
            (self.vsb.grid if need_v else self.vsb.grid_remove)()
            (self.hsb.grid if need_h else self.hsb.grid_remove)()
            self._sb_state = (need_v, need_h)
            self.update_idletasks()
        if need_h:
            self.hsb.set(self.sx / W, (self.sx + self.vw) / W)
        if need_v:
            self.vsb.set(self.sy / H, (self.sy + self.vh) / H)

    def view_changed(self, keep=False):
        """Recalcula la geometria y repinta todo."""
        self._compute_view()
        self.render()
        self._update_labels()

    def _update_labels(self):
        self.zoom_lbl.config(text=f"Zoom {round(self.z * 100)}%   ·   Lienzo {self.doc.w}×{self.doc.h}")

    def _xview(self, *a):
        W = self.doc.w * self.z
        if a[0] == "moveto":
            self.sx = int(float(a[1]) * W)
        else:
            self.sx += int(a[1]) * (40 if a[2] == "units" else int(self.vw * 0.9))
        self.view_changed()

    def _yview(self, *a):
        H = self.doc.h * self.z
        if a[0] == "moveto":
            self.sy = int(float(a[1]) * H)
        else:
            self.sy += int(a[1]) * (40 if a[2] == "units" else int(self.vh * 0.9))
        self.view_changed()

    def _wheel_event(self, delta, state):
        try:
            px = self.winfo_pointerx() - self.cv.winfo_rootx()
            py = self.winfo_pointery() - self.cv.winfo_rooty()
        except tk.TclError:
            return
        self.on_wheel(delta, state, px, py)

    def on_wheel(self, delta, state, px, py):
        """Alt+rueda: zoom. Rueda: desplazamiento vertical. Ctrl (o Mayús)+rueda: horizontal."""
        if not (0 <= px < self.vw and 0 <= py < self.vh):
            return
        if is_alt(state):
            self._zacc = getattr(self, "_zacc", 0) + delta     # el trackpad envia deltas pequeños: acumular
            if abs(self._zacc) >= 120:
                self.zoom_step(1 if self._zacc > 0 else -1, px, py)
                self._zacc = 0
            return
        step = int(round(delta / 120.0 * 80)) or (80 if delta > 0 else -80)
        if state & (CTRL_MASK | SHIFT_MASK):
            self.sx -= step
        else:
            self.sy -= step
        self.view_changed()

    # --------------------------------------------------------------- dibujado
    @staticmethod
    def _ppm(arr):
        h, w = arr.shape[:2]
        return b"P6 %d %d 255\n" % (w, h) + np.ascontiguousarray(arr).tobytes()

    def _view_patch(self, x0, y0, x1, y1):
        patch = self.doc.composite(x0, y0, x1, y1)
        z = self.z
        tw, th = max(1, round((x1 - x0) * z)), max(1, round((y1 - y0) * z))
        interp = cv2.INTER_NEAREST if z >= 1 else cv2.INTER_AREA
        return cv2.resize(patch, (tw, th), interpolation=interp)

    def render(self):
        d, z = self.doc, self.z
        ix0 = max(0, int(math.floor((self.sx - self.ox) / z)))
        iy0 = max(0, int(math.floor((self.sy - self.oy) / z)))
        ix1 = min(d.w, int(math.ceil((self.sx - self.ox + self.vw) / z)))
        iy1 = min(d.h, int(math.ceil((self.sy - self.oy + self.vh) / z)))
        self.cv.delete("all")
        self.cursor_item = None
        self.vis = (ix0, iy0, ix1, iy1)
        if ix1 > ix0 and iy1 > iy0:
            view = self._view_patch(ix0, iy0, ix1, iy1)
            self.photo = tk.PhotoImage(data=self._ppm(view), format="PPM")
            px, py = round(self.ox + ix0 * z - self.sx), round(self.oy + iy0 * z - self.sy)
            self.ph = (px, py, ix0, iy0)
            self.cv.create_image(px, py, image=self.photo, anchor="nw", tags="img")
        self.draw_overlay()
        self._update_buttons()

    def refresh_box(self, box):
        if box is None:
            return
        if box == "all":
            self.view_changed()
            return
        vx0, vy0, vx1, vy1 = self.vis
        x0, y0, x1, y1 = max(box[0], vx0), max(box[1], vy0), min(box[2], vx1), min(box[3], vy1)
        if x1 <= x0 or y1 <= y0 or self.photo is None:
            return
        z = self.z
        patch = self._view_patch(x0, y0, x1, y1)
        px = round(self.ox + x0 * z - self.sx) - self.ph[0]
        py = round(self.oy + y0 * z - self.sy) - self.ph[1]
        pw, phh = self.photo.width(), self.photo.height()
        px, py = max(0, px), max(0, py)
        patch = patch[:max(1, phh - py), :max(1, pw - px)]
        if px >= pw or py >= phh:
            return
        tmp = tk.PhotoImage(data=self._ppm(patch), format="PPM")
        self.photo.tk.call(self.photo, "copy", tmp, "-to", px, py)
        del tmp

    def i2v(self, x, y):
        return self.ox + x * self.z - self.sx, self.oy + y * self.z - self.sy

    def _handle_positions(self):
        x0, y0 = self.i2v(0, 0)
        x1, y1 = self.i2v(self.doc.w, self.doc.h)
        xm, ym = (x0 + x1) / 2, (y0 + y1) / 2
        return {"nw": (x0, y0), "n": (xm, y0), "ne": (x1, y0), "e": (x1, ym), "se": (x1, y1),
                "s": (xm, y1), "sw": (x0, y1), "w": (x0, ym)}

    def draw_overlay(self):
        cv = self.cv
        cv.delete("ov")
        d = self.doc
        x0, y0 = self.i2v(0, 0)
        x1, y1 = self.i2v(d.w, d.h)
        cv.create_rectangle(x0 - 1, y0 - 1, x1, y1, outline="#5A6778", tags="ov")
        for name, (hx, hy) in self._handle_positions().items():
            if -8 <= hx <= self.vw + 8 and -8 <= hy <= self.vh + 8:
                cv.create_rectangle(hx - 4, hy - 4, hx + 4, hy + 4, fill="white", outline="#2D5BA8", tags="ov")
        if d.sel:
            self._draw_sel_outline()
        if not d.has_content() and self.photo is not None:
            cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
            cv.create_text(cx, cy - 18, text="Abre una imagen para pintarla", fill="#5A6778",
                           font=("Segoe UI", 22, "bold"), tags="ov")
            cv.create_text(cx, cy + 22, text="Botón «Abrir», o pega una captura con Ctrl+V",
                           fill="#7B8794", font=("Segoe UI", 13), tags="ov")

    def _draw_sel_outline(self):
        s = self.doc.sel
        m = s["mask"].astype(np.uint8)
        cs, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for c in cs:
            c = cv2.approxPolyDP(c, 1.2, True)[:, 0, :]
            if len(c) < 2:
                continue
            pts = []
            for px, py in c:
                pts.extend(self.i2v(px + s["x"], py + s["y"]))
            pts.extend(pts[:2])
            self.cv.create_line(*pts, fill="white", width=2, tags="ov")
            self.cv.create_line(*pts, fill="black", width=1, dash=(5, 4), tags="ov")

    # ------------------------------------------------------------------ ratón
    def _to_img(self, e):
        return (e.x - self.ox + self.sx) / self.z, (e.y - self.oy + self.sy) / self.z

    def _inside(self, x, y):
        return 0 <= x < self.doc.w and 0 <= y < self.doc.h

    def _handle_at(self, ex, ey):
        for name, (hx, hy) in self._handle_positions().items():
            if abs(ex - hx) <= 6 and abs(ey - hy) <= 6:
                return name
        return None

    def _press(self, e):
        self.cv.focus_set()
        h = self._handle_at(e.x, e.y)
        if h:
            self.commit_sel()
            self.drag = {"k": "resize", "h": h, "x": e.x, "y": e.y, "d": (0, 0, 0, 0)}
            return
        x, y = self._to_img(e)
        t = self.tool
        if t in SEL_TOOLS:
            if self.doc.sel and self.doc.sel_contains(x, y):
                self.drag = {"k": "move", "x0": x, "y0": y, "ox": self.doc.sel["x"], "oy": self.doc.sel["y"]}
            else:
                self.commit_sel()
                if self._inside(x, y):
                    self.drag = {"k": "selnew", "x0": x, "y0": y, "pts": [(x, y)]}
            return
        self.commit_sel()
        if not self._inside(x, y):
            return
        if t == "bucket":
            self.refresh_box(self.doc.fill(int(x), int(y), self.rgb))
            self._update_buttons()
        elif t == "picker":
            self.drag = {"k": "pick"}
            self._pick(x, y)
        else:
            self.doc.begin_stroke(t, self.rgb, SIZES[t][self.size_idx[t]] / self.z)
            self.painting = True
            self.refresh_box(self.doc.stroke_to(x, y))
            self._move_cursor(e)

    def _drag(self, e):
        dr = self.drag
        x, y = self._to_img(e)
        if self.painting:
            x = min(max(x, 0), self.doc.w - 1)
            y = min(max(y, 0), self.doc.h - 1)
            self.refresh_box(self.doc.stroke_to(x, y))
            self._move_cursor(e)
        elif dr is None:
            return
        elif dr["k"] == "pick":
            self._pick(x, y)
        elif dr["k"] == "resize":
            self._resize_preview(e, dr)
        elif dr["k"] == "move":
            if self.doc.sel["layers"] is None:
                self.refresh_box(self.doc.lift())
            nx, ny = dr["ox"] + round(x - dr["x0"]), dr["oy"] + round(y - dr["y0"])
            s = self.doc.sel
            box = self.doc.move_sel(nx - s["x"], ny - s["y"])
            self.refresh_box(box)
            self.draw_overlay()
        elif dr["k"] == "selnew":
            dr["pts"].append((x, y))
            self._selnew_preview(dr, x, y)

    def _release(self, e):
        dr, self.drag = self.drag, None
        if self.painting:
            self.painting = False
            self.doc.end_stroke()
            self._update_buttons()
            return
        if dr is None:
            return
        if dr["k"] == "pick":
            self._finish_pick()
            self.select_tool(self.prev_tool)
        elif dr["k"] == "resize":
            self.cv.delete("rb")
            dl, dt, ddr, db = dr["d"]
            if (dl, dt, ddr, db) != (0, 0, 0, 0):
                self._apply_resize(dl, dt, ddr, db)
        elif dr["k"] == "selnew":
            self.cv.delete("rb")
            x, y = self._to_img(e)
            self._finish_selection(dr, x, y)
        self._update_buttons()

    def _hover(self, e):
        if self.drag is None and not self.painting:
            h = self._handle_at(e.x, e.y)
            if h:
                try:
                    self.cv.configure(cursor=HANDLE_CURSOR[h])
                except tk.TclError:
                    self.cv.configure(cursor="fleur")
                self._hide_cursor()
                return
            if self.tool in SEL_TOOLS:
                x, y = self._to_img(e)
                self.cv.configure(cursor="fleur" if self.doc.sel and self.doc.sel_contains(x, y) else "crosshair")
            else:
                self._set_tool_cursor()
        self._move_cursor(e)

    def _move_cursor(self, e):
        if self.tool not in STROKE_TOOLS or self._handle_at(e.x, e.y):
            return
        r = max(2, SIZES[self.tool][self.size_idx[self.tool]] / 2)
        if self.cursor_item is None:
            self.cursor_item = self.cv.create_oval(0, 0, 1, 1, outline="#000000", width=1, tags="curs")
        self.cv.coords(self.cursor_item, e.x - r, e.y - r, e.x + r, e.y + r)
        self.cv.itemconfigure(self.cursor_item, state="normal")
        self.cv.tag_raise(self.cursor_item)

    def _hide_cursor(self):
        if self.cursor_item is not None:
            self.cv.itemconfigure(self.cursor_item, state="hidden")

    # ---------------------------------------------------------------- gotero
    def _pick(self, x, y):
        c = self.doc.sample(x, y)
        if c:
            self.rgb = c
            self.color_idx = -1
            self._draw_palette()
            self._draw_current_color()
            self._picked = c

    def _finish_pick(self):
        c = getattr(self, "_picked", None)
        if c:
            self.add_recent(c)
            self._picked = None

    # --------------------------------------------------- tamaño del lienzo (asas)
    def _resize_preview(self, e, dr):
        dx, dy = round((e.x - dr["x"]) / self.z), round((e.y - dr["y"]) / self.z)
        h = dr["h"]
        dl = dx if "w" in h else 0
        dt = dy if "n" in h else 0
        drr = dx if "e" in h else 0
        db = dy if "s" in h else 0
        dr["d"] = (dl, dt, drr, db)
        d = self.doc
        self.cv.delete("rb")
        a, b = self.i2v(dl, dt)
        c, f = self.i2v(d.w + drr, d.h + db)
        self.cv.create_rectangle(a, b, c, f, outline="#2D5BA8", dash=(5, 4), width=2, tags="rb")
        self.status.config(text=f"Tamaño del lienzo: {d.w + drr - dl} × {d.h + db - dt}")

    def _apply_resize(self, dl, dt, dr, db):
        d = self.doc
        if not d.resize_canvas(dl, dt, dr, db):
            self.status.config(text=f"Tamaño no permitido (mínimo 16 px, máximo {MAX_SIDE} px por lado)")
            return
        z = self.z
        self.sx = int(self.sx - dl * z)
        self.sy = int(self.sy - dt * z)
        self.status.config(text=f"Lienzo: {d.w} × {d.h}")
        self.view_changed()

    # -------------------------------------------------------------- selecciones
    def _selnew_preview(self, dr, x, y):
        self.cv.delete("rb")
        t = self.tool
        if t == "sel_free":
            pts = []
            for px, py in dr["pts"]:
                pts.extend(self.i2v(px, py))
            if len(pts) >= 4:
                self.cv.create_line(*pts, fill="black", dash=(4, 3), tags="rb")
        else:
            a, b = self.i2v(dr["x0"], dr["y0"])
            c, f = self.i2v(x, y)
            if t == "sel_rect":
                self.cv.create_rectangle(a, b, c, f, outline="black", dash=(4, 3), tags="rb")
            else:
                self.cv.create_oval(a, b, c, f, outline="black", dash=(4, 3), tags="rb")

    def _finish_selection(self, dr, x, y):
        d = self.doc
        t = self.tool
        if t == "sel_free":
            pts = np.array([[min(max(px, 0), d.w - 1), min(max(py, 0), d.h - 1)] for px, py in dr["pts"]], np.float32)
            if len(pts) < 3:
                return
            x0, y0 = int(pts[:, 0].min()), int(pts[:, 1].min())
            x1, y1 = int(math.ceil(pts[:, 0].max())) + 1, int(math.ceil(pts[:, 1].max())) + 1
            if x1 - x0 < 3 or y1 - y0 < 3:
                return
            mask = np.zeros((y1 - y0, x1 - x0), np.uint8)
            cv2.fillPoly(mask, [np.round(pts - [x0, y0]).astype(np.int32)], 1)
        else:
            ax, bx = sorted((min(max(dr["x0"], 0), d.w), min(max(x, 0), d.w)))
            ay, by = sorted((min(max(dr["y0"], 0), d.h), min(max(y, 0), d.h)))
            x0, y0, x1, y1 = int(ax), int(ay), int(math.ceil(bx)), int(math.ceil(by))
            if x1 - x0 < 3 or y1 - y0 < 3:
                return
            w, h = x1 - x0, y1 - y0
            mask = np.zeros((h, w), np.uint8)
            if t == "sel_rect":
                mask[:] = 1
            else:
                cv2.ellipse(mask, (w // 2, h // 2), (max(1, w // 2), max(1, h // 2)), 0, 0, 360, 1, -1)
        if mask.any():
            d.make_selection(mask.astype(bool), x0, y0)
            self.draw_overlay()

    def commit_sel(self):
        if self.doc.sel:
            box = self.doc.commit()
            self.refresh_box(box)
            self.draw_overlay()
            self._update_buttons()

    def sel_delete(self):
        if self.doc.sel:
            self.refresh_box(self.doc.delete_sel())
            self.draw_overlay()
            self._update_buttons()

    def sel_copy(self):
        if self.doc.sel:
            self.clip = self.doc.copy_clip()
            self.clip_sig = self._clip_signature(self._grab())
            self.status.config(text="Copiado. Usa Pegar (Ctrl+V) para colocarlo.")

    def sel_cut(self):
        if self.doc.sel:
            self.clip = self.doc.copy_clip()
            self.clip_sig = self._clip_signature(self._grab())
            self.refresh_box(self.doc.delete_sel())
            self.draw_overlay()
            self._update_buttons()
            self.status.config(text="Cortado. Usa Pegar (Ctrl+V) para colocarlo en otro sitio.")

    # ---------------------------------------------------------------- historial
    def undo(self):
        if self.doc.sel:
            box = self.doc.cancel()
            self.refresh_box(box)
            self.draw_overlay()
        else:
            r = self.doc.undo()
            self.refresh_box(r)
            if r == "all":
                self.draw_overlay()
        self._update_buttons()

    def redo(self):
        if self.doc.sel:
            self.commit_sel()
        r = self.doc.redo()
        self.refresh_box(r)
        self._update_buttons()

    def _update_buttons(self):
        d = self.doc
        self.btn_undo.set_enabled(bool(d.undo_stack) or bool(d.sel))
        self.btn_redo.set_enabled(bool(d.redo_stack))
        has = bool(d.sel)
        for b in (self.btn_cut, self.btn_copy, self.btn_del):
            b.set_enabled(has)
        if self.drag is None and self.tool == "picker":
            pass

    # ------------------------------------------------------------ cargar / pegar
    def _confirm_discard(self):
        if self.doc.undo_stack or self.doc.sel:
            return messagebox.askyesno(APP_NAME, "Se perderá lo que has pintado en este lienzo.\n¿Continuar?")
        return True

    def new_canvas(self):
        if not self._confirm_discard():
            return
        self.doc.blank(1200, 800)
        self.title(f"{APP_NAME} {VERSION}")
        self.status.config(text="Lienzo en blanco. Pega una imagen con Ctrl+V.")
        self.fit = True
        self.sx = self.sy = 0
        self.view_changed()

    def load_pil(self, pil, name="imagen"):
        try:
            pil = ImageOps.exif_transpose(pil)
        except Exception:
            pass
        self.config(cursor="watch")
        self.update_idletasks()
        try:
            self.doc.load(pil, threshold=self.threshold.get())
        finally:
            self.config(cursor="")
        self.title(f"{APP_NAME} {VERSION} - {name}")
        self.status.config(text=f"{name}  ·  {self.doc.w}×{self.doc.h}")
        self.fit = True
        self.sx = self.sy = 0
        self.view_changed()

    def _read_path(self, path):
        ext = os.path.splitext(path)[1].lower()
        try:
            if ext == ".pdf":
                return self._pdf_page(path)
            pil = Image.open(path)
            pil.load()
            return pil
        except Exception as ex:
            messagebox.showerror(APP_NAME, f"No se pudo abrir el archivo.\n\n{ex}")
            return None

    def open_path(self, path):
        if not self._confirm_discard():
            return
        pil = self._read_path(path)
        if pil is not None:
            self.load_pil(pil, os.path.basename(path))

    def _pdf_page(self, path):
        import pymupdf
        d = pymupdf.open(path)
        page_no = 1
        if d.page_count > 1:
            page_no = simpledialog.askinteger(APP_NAME, f"El PDF tiene {d.page_count} páginas.\n¿Cuál quieres pintar?",
                                              minvalue=1, maxvalue=d.page_count, initialvalue=1, parent=self)
            if page_no is None:
                return None
        page = d[page_no - 1]
        zoom = min(4.0, max(1.0, LONG_SIDE_MAX / max(page.rect.width, page.rect.height)))
        pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
        return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)

    FILETYPES = [("Imágenes y PDF", "*.jpg *.jpeg *.jpe *.jfif *.png *.bmp *.dib *.gif *.tif *.tiff *.heic *.heif *.pdf *.webp"),
                 ("Todos los archivos", "*.*")]

    def open_dialog(self):
        path = filedialog.askopenfilename(title="Abrir imagen para pintar", filetypes=self.FILETYPES)
        if path:
            self.open_path(path)

    def insert_dialog(self):
        path = filedialog.askopenfilename(title="Insertar imagen de referencia (con colores)", filetypes=self.FILETYPES)
        if path:
            pil = self._read_path(path)
            if pil is not None:
                self._float_image(pil)

    @staticmethod
    def _grab():
        try:
            return ImageGrab.grabclipboard()
        except Exception:
            return None

    @staticmethod
    def _clip_signature(data):
        if isinstance(data, Image.Image):
            return (data.size, hash(data.convert("RGB").resize((8, 8)).tobytes()))
        if isinstance(data, list) and data:
            return tuple(data)
        return None

    def _view_origin(self):
        return (max(0, int((self.sx - self.ox) / self.z)), max(0, int((self.sy - self.oy) / self.z)))

    def _float_image(self, pil):
        self.commit_sel()
        try:
            pil = ImageOps.exif_transpose(pil)
        except Exception:
            pass
        # La referencia se coloca a la derecha del dibujo (ampliando el lienzo) para no taparlo.
        right = self.doc.content_right()
        x, y = (right + 16, 0) if right else (0, 0)
        self._after_float(self.doc.paste_image(pil, x, y))

    def _after_float(self, box):
        self.select_tool("sel_rect")
        self.view_changed()
        self.status.config(text="Arrastra la imagen para colocarla. Clic fuera (o Intro) para fijarla. Usa el gotero para copiar sus colores.")

    def paste_clipboard(self):
        self.commit_sel()
        data = self._grab()
        sig = self._clip_signature(data)
        use_internal = self.clip is not None and (sig == self.clip_sig or not isinstance(data, (Image.Image, list)))
        if use_internal:
            x, y = self._view_origin()
            self._after_float(self.doc.paste_clip(self.clip, x, y))
            return
        if isinstance(data, list) and data:
            pil = self._read_path(data[0])
        elif isinstance(data, Image.Image):
            pil = data
        else:
            messagebox.showinfo(APP_NAME, "No hay ninguna imagen en el portapapeles.\n\n"
                                          "Haz una captura de pantalla (tecla Windows + Mayús + S) y pulsa Pegar.")
            return
        if pil is None:
            return
        if not self.doc.has_content():
            self.load_pil(pil, "Captura pegada")      # lienzo vacio: se procesa como dibujo
        else:
            self._float_image(pil)                    # lienzo con dibujo: imagen de referencia

    def reprocess(self):
        d = self.doc
        if d.source_rgb is None:
            return
        if (d.undo_stack or d.structural) and not messagebox.askyesno(
                APP_NAME, "Cambiar la detección de líneas vuelve a empezar el dibujo:\n"
                          "se perderá lo pintado, el tamaño del lienzo y las imágenes pegadas.\n¿Continuar?"):
            return
        d.process(self.threshold.get())
        self.fit = True
        self.sx = self.sy = 0
        self.view_changed()

    def save_dialog(self):
        self.commit_sel()
        path = filedialog.asksaveasfilename(title="Guardar dibujo", defaultextension=".png",
                                            filetypes=[("PNG", "*.png"), ("JPEG", "*.jpg")])
        if not path:
            return
        Image.fromarray(self.doc.composite()).save(path)
        self.status.config(text=f"Guardado: {path}")


def main():
    app = PintaYa()
    if len(sys.argv) > 1 and os.path.isfile(sys.argv[1]):
        app.after(200, lambda: app.open_path(sys.argv[1]))
    app.mainloop()


if __name__ == "__main__":
    main()
