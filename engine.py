"""Motor de PintaYa v0.01 (sin interfaz).

Capas (todas del mismo tamaño que el lienzo):
  color    RGB   lo que se pinta con bote/pincel/resaltador (debajo de las lineas)
  line_a   alfa  lineas negras del dibujo original (encima del color)
  seal     0/1   lineas "selladas" (huecos de 1-2 px cerrados): barrera del bote
  ink_rgb  RGB   trazos de la pluma (encima de las lineas)
  ink_a    alfa  alfa de la pluma; tambien funciona como barrera del bote
  ref      0/1   imagen de referencia pegada (no se procesa; el bote no la invade)

Las regiones ya no se precalculan: cada relleno hace un flood-fill sobre
(seal | tinta | ref), asi siempre es correcto tras dibujar con la pluma,
mover/borrar selecciones o cambiar el tamaño del lienzo.
"""
from __future__ import annotations

import numpy as np
import cv2
from PIL import Image

LONG_SIDE_MIN = 1000
LONG_SIDE_MAX = 2200
MAX_SIDE = 8192            # "8K": lado maximo del lienzo y del zoom
MAX_AREA = 40_000_000      # protege la memoria (9 bytes por pixel y capa)
HOLE_PX = 12               # motas encerradas mas pequeñas que esto se pintan con la zona
MIN_PEN_PX = 2.5           # la pluma nunca es mas fina que esto (cierra huecos)

SPEC = {  # nombre: (canales o None, valor de relleno)
    "color": (3, 255), "ink_rgb": (3, 0), "ink_a": (None, 0),
    "line_a": (None, 0), "seal": (None, 0), "ref": (None, 0),
}
NAMES = list(SPEC)


def _alloc(name, h, w):
    ch, fill = SPEC[name]
    return np.full((h, w, ch) if ch else (h, w), fill, np.uint8)


def to_rgb_on_white(pil: Image.Image) -> np.ndarray:
    if pil.mode in ("RGBA", "LA") or (pil.mode == "P" and "transparency" in pil.info):
        pil = pil.convert("RGBA")
        bg = Image.new("RGBA", pil.size, (255, 255, 255, 255))
        bg.alpha_composite(pil)
        pil = bg
    return np.asarray(pil.convert("RGB"), dtype=np.uint8).copy()


def _union(a, b):
    if a is None:
        return b
    if b is None:
        return a
    return (min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3]))


class PaintDoc:
    def __init__(self, width=1200, height=800):
        self.blank(width, height)

    # ------------------------------------------------------------ estado base
    def blank(self, w, h):
        self.w, self.h = w, h
        self.L = {n: _alloc(n, h, w) for n in NAMES}
        self.source_rgb = None
        self.undo_stack, self.redo_stack = [], []
        self.sel = None
        self._stroke = None
        self.structural = False   # True tras redimensionar/pegar: reprocesar borraria cosas

    def content_right(self):
        """Columna (exclusive) hasta donde llega el contenido dibujado; 0 si esta vacio."""
        L = self.L
        used = (L["line_a"] > 0) | (L["ink_a"] > 0) | (L["ref"] > 0) | (L["color"] != 255).any(axis=2)
        cols = np.nonzero(used.any(axis=0))[0]
        return int(cols.max()) + 1 if len(cols) else 0

    def has_content(self):
        return self.source_rgb is not None or bool(self.undo_stack)

    # ------------------------------------------------------------------ carga
    def load(self, pil, threshold=128, gap=1):
        self.source_rgb = to_rgb_on_white(pil)
        self.process(threshold, gap)

    def process(self, threshold=128, gap=1):
        rgb = self.source_rgb
        h0, w0 = rgb.shape[:2]
        ls = max(h0, w0)
        if ls < LONG_SIDE_MIN:
            s = LONG_SIDE_MIN / ls
            rgb = cv2.resize(rgb, (round(w0 * s), round(h0 * s)), interpolation=cv2.INTER_CUBIC)
        elif ls > LONG_SIDE_MAX:
            s = LONG_SIDE_MAX / ls
            rgb = cv2.resize(rgb, (round(w0 * s), round(h0 * s)), interpolation=cv2.INTER_AREA)
        h, w = rgb.shape[:2]

        mx = rgb.max(axis=2).astype(np.int16)
        chroma = mx - rgb.min(axis=2).astype(np.int16)
        T = int(threshold)
        neutral = np.clip(1.0 - (chroma - 45) / 55.0, 0.0, 1.0)
        alpha = np.clip((T + 50 - mx) / 100.0, 0.0, 1.0) * neutral
        hard = ((mx <= T) & (neutral > 0.5)).astype(np.uint8)

        n, lab, st, _ = cv2.connectedComponentsWithStats(hard, connectivity=8)
        min_area = max(10, int(h * w * 0.00003))
        small = np.isin(lab, np.nonzero(st[:, cv2.CC_STAT_AREA] < min_area)[0]) & (lab > 0)
        if small.any():
            sd = cv2.dilate(small.astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool)
            alpha[sd] = 0
            hard[small] = 0

        seal = hard
        if gap > 0:
            k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * gap + 1, 2 * gap + 1))
            seal = cv2.dilate(hard, k)

        self.w, self.h = w, h
        self.L = {n: _alloc(n, h, w) for n in NAMES}
        self.L["line_a"] = (alpha * 255).astype(np.uint8)
        self.L["seal"] = seal.astype(np.uint8)
        self.undo_stack, self.redo_stack = [], []
        self.sel = None
        self.structural = False

    # -------------------------------------------------------------- composicion
    def composite(self, x0=0, y0=0, x1=None, y1=None):
        x1 = self.w if x1 is None else x1
        y1 = self.h if y1 is None else y1
        L = self.L
        out = L["color"][y0:y1, x0:x1].astype(np.float32)
        la = L["line_a"][y0:y1, x0:x1]
        if la.any():
            out *= (1.0 - la.astype(np.float32) / 255.0)[..., None]
        ia = L["ink_a"][y0:y1, x0:x1]
        if ia.any():
            f = (ia.astype(np.float32) / 255.0)[..., None]
            out = out * (1 - f) + L["ink_rgb"][y0:y1, x0:x1] * f
        s = self.sel
        if s and s["layers"] is not None:
            fx, fy = s["x"], s["y"]
            fh, fw = s["mask"].shape
            ax0, ay0, ax1, ay1 = max(x0, fx), max(y0, fy), min(x1, fx + fw), min(y1, fy + fh)
            if ax1 > ax0 and ay1 > ay0:
                sl = (slice(ay0 - fy, ay1 - fy), slice(ax0 - fx, ax1 - fx))
                fl = s["layers"]
                f_out = fl["color"][sl].astype(np.float32)
                fla = fl["line_a"][sl]
                f_out *= (1.0 - fla.astype(np.float32) / 255.0)[..., None]
                fia = (fl["ink_a"][sl].astype(np.float32) / 255.0)[..., None]
                f_out = f_out * (1 - fia) + fl["ink_rgb"][sl] * fia
                m = s["mask"][sl][..., None]
                dst = (slice(ay0 - y0, ay1 - y0), slice(ax0 - x0, ax1 - x0))
                out[dst] = np.where(m, f_out, out[dst])
        return out.astype(np.uint8)

    def sample(self, x, y):
        """Color visible en (x, y): composicion, incluida la seleccion flotante."""
        x, y = int(x), int(y)
        if not (0 <= x < self.w and 0 <= y < self.h):
            return None
        p = self.composite(x, y, x + 1, y + 1)[0, 0]
        if self.L["line_a"][y, x] >= 128 and self.L["ink_a"][y, x] < 128 and not (
                self.sel and self.sel["layers"] is not None and self._in_sel(x, y)):
            # Sobre una linea negra del dibujo: devolver el color que hay debajo.
            p = self.L["color"][y, x]
        return tuple(int(v) for v in p)

    def clamp_box(self, x0, y0, x1, y1):
        return max(0, int(x0)), max(0, int(y0)), min(self.w, int(x1)), min(self.h, int(y1))

    # --------------------------------------------------------------- historial
    def _snap(self, box, names=NAMES):
        x0, y0, x1, y1 = box
        return {n: self.L[n][y0:y1, x0:x1].copy() for n in names}

    def _restore(self, box, snap):
        x0, y0, x1, y1 = box
        for n, a in snap.items():
            self.L[n][y0:y1, x0:x1] = a

    def _push(self, entry):
        self.undo_stack.append(entry)
        if len(self.undo_stack) > 60:
            self.undo_stack.pop(0)
        self.redo_stack.clear()

    def _state(self):
        return {"w": self.w, "h": self.h, "L": dict(self.L)}

    def _set_state(self, st):
        self.w, self.h, self.L = st["w"], st["h"], dict(st["L"])

    def undo(self):
        """Devuelve el cuadro a refrescar, 'all' si cambio el lienzo, o None."""
        if not self.undo_stack:
            return None
        e = self.undo_stack.pop()
        if e[0] == "r":
            self.redo_stack.append(("r", self._state()))
            self._set_state(e[1])
            return "all"
        _, box, old, new = e
        self._restore(box, old)
        self.redo_stack.append(e)
        return box

    def redo(self):
        if not self.redo_stack:
            return None
        e = self.redo_stack.pop()
        if e[0] == "r":
            self.undo_stack.append(("r", self._state()))
            self._set_state(e[1])
            return "all"
        _, box, old, new = e
        self._restore(box, new)
        self.undo_stack.append(e)
        return box

    # ------------------------------------------------------------ bote de pintura
    def fill(self, x, y, rgb, tol=24):
        if not (0 <= x < self.w and 0 <= y < self.h):
            return None
        rgb = np.array(rgb, np.uint8)
        L = self.L
        if not L["seal"].any():
            # Sin dibujo de lineas (lienzo en blanco): relleno clasico por color,
            # los trazos de pincel/pluma actuan como limites (como en Paint).
            return self._fill_flat(x, y, rgb, tol, restrict_ref=False)
        if L["ref"][y, x]:
            return self._fill_flat(x, y, rgb, tol)
        lineb = L["seal"] > 0
        if L["ink_a"].any():
            ink = cv2.dilate((L["ink_a"] >= 128).astype(np.uint8), np.ones((3, 3), np.uint8))
            lineb = lineb | (ink > 0)
        refm = L["ref"] > 0
        bar = (lineb | refm).astype(np.uint8)
        if bar[y, x]:  # clic justo sobre una linea: region libre mas cercana
            r = 10
            wx0, wy0 = max(0, x - r), max(0, y - r)
            win = bar[wy0:y + r + 1, wx0:x + r + 1]
            ys, xs = np.nonzero(win == 0)
            if len(xs) == 0:
                return None
            i = int(((xs + wx0 - x) ** 2 + (ys + wy0 - y) ** 2).argmin())
            x, y = int(xs[i] + wx0), int(ys[i] + wy0)
        mask = np.zeros((self.h + 2, self.w + 2), np.uint8)
        _, _, mask, rect = cv2.floodFill(bar, mask, (x, y), 0, 0, 0,
                                         4 | (255 << 8) | cv2.FLOODFILL_MASK_ONLY | cv2.FLOODFILL_FIXED_RANGE)
        rx, ry, rw, rh = rect
        pad = 5
        x0, y0 = max(0, rx - pad), max(0, ry - pad)
        x1, y1 = min(self.w, rx + rw + pad), min(self.h, ry + rh + pad)
        region = mask[1 + y0:1 + y1, 1 + x0:1 + x1] > 0
        grown = cv2.dilate(region.astype(np.uint8), cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))) > 0
        under = grown & lineb[y0:y1, x0:x1] & ~refm[y0:y1, x0:x1] & ~region
        m = region | under
        # Motas diminutas encerradas dentro de la zona (ruido de JPG): rellenarlas tambien
        inv = (~m).astype(np.uint8)
        n, lab, st, _ = cv2.connectedComponentsWithStats(inv, connectivity=4)
        H_, W_ = inv.shape
        if n > 1:
            xx, yy, ww, hh, ar = (st[:, i] for i in range(5))
            keep = (ar <= HOLE_PX) & (xx > 0) & (yy > 0) & (xx + ww < W_) & (yy + hh < H_)
            keep[0] = False
            if keep.any():
                m |= keep[lab]
        patch = L["color"][y0:y1, x0:x1]
        old = patch.copy()
        patch[m] = rgb
        if np.array_equal(old, patch):
            return None
        box = (x0, y0, x1, y1)
        self._push(("p", box, {"color": old}, {"color": patch.copy()}))
        return box

    def _fill_flat(self, x, y, rgb, tol, restrict_ref=True):
        img = self.composite()
        mask = np.zeros((self.h + 2, self.w + 2), np.uint8)
        if restrict_ref:
            mask[1:-1, 1:-1] = (self.L["ref"] == 0)   # solo dentro de la imagen de referencia
        _, _, mask, rect = cv2.floodFill(img, mask, (x, y), (0, 0, 0), (tol,) * 3, (tol,) * 3,
                                         4 | (255 << 8) | cv2.FLOODFILL_MASK_ONLY | cv2.FLOODFILL_FIXED_RANGE)
        rx, ry, rw, rh = rect
        if rw == 0 or rh == 0:
            return None
        box = (rx, ry, rx + rw, ry + rh)
        m = mask[1 + ry:1 + ry + rh, 1 + rx:1 + rx + rw] == 255
        patch = self.L["color"][ry:ry + rh, rx:rx + rw]
        old = patch.copy()
        patch[m] = rgb
        if np.array_equal(old, patch):
            return None
        self._push(("p", box, {"color": old}, {"color": patch.copy()}))
        return box

    # --------------------------------------------------------------------- trazos
    def begin_stroke(self, kind, rgb, size):
        """kind: pen | brush | highlighter | eraser; size en pixeles de imagen."""
        if kind == "pen":
            size = max(size, MIN_PEN_PX)
        names = {"pen": ["ink_rgb", "ink_a"], "eraser": ["color", "ink_a"]}.get(kind, ["color"])
        self._stroke = dict(
            kind=kind, names=names,
            rgb=np.array((255, 255, 255) if kind == "eraser" else rgb, np.float32),
            size=max(1.0, float(size)),
            alpha=0.45 if kind == "highlighter" else 1.0,
            base={n: self.L[n].copy() for n in names},
            mask=np.zeros((self.h, self.w), np.uint8),
            last=None, box=None)

    def stroke_to(self, x, y):
        s = self._stroke
        if s is None:
            return None
        r = s["size"] / 2.0
        p = (int(round(x)), int(round(y)))
        t = max(1, int(round(s["size"])))
        prev = s["last"]
        if prev is None:
            cv2.circle(s["mask"], p, int(round(r)), 255, -1, cv2.LINE_AA)
        else:
            cv2.line(s["mask"], prev, p, 255, t, cv2.LINE_AA)
            cv2.circle(s["mask"], p, int(round(r)), 255, -1, cv2.LINE_AA)
        s["last"] = p
        q = prev or p
        pad = int(r) + 6
        box = self.clamp_box(min(p[0], q[0]) - pad, min(p[1], q[1]) - pad,
                             max(p[0], q[0]) + pad + 1, max(p[1], q[1]) + pad + 1)
        if box[2] <= box[0] or box[3] <= box[1]:
            return None
        s["box"] = _union(s["box"], box)
        self._apply_stroke(box)
        return box

    def _apply_stroke(self, box):
        s, L = self._stroke, self.L
        x0, y0, x1, y1 = box
        m = s["mask"][y0:y1, x0:x1].astype(np.float32) / 255.0
        if s["kind"] == "brush":
            m = np.clip(cv2.GaussianBlur(m, (0, 0), max(0.6, s["size"] * 0.07)) * 1.15, 0, 1)
        m = m * s["alpha"]
        m3 = m[..., None]
        b = s["base"]
        if s["kind"] == "pen":
            a0 = b["ink_a"][y0:y1, x0:x1].astype(np.float32) / 255.0
            c0 = b["ink_rgb"][y0:y1, x0:x1].astype(np.float32)
            a1 = m + a0 * (1 - m)
            num = s["rgb"] * m3 + c0 * (a0 * (1 - m))[..., None]
            c1 = np.where(a1[..., None] > 1e-6, num / np.maximum(a1, 1e-6)[..., None], 0)
            L["ink_a"][y0:y1, x0:x1] = np.clip(a1 * 255 + 0.5, 0, 255).astype(np.uint8)
            L["ink_rgb"][y0:y1, x0:x1] = np.clip(c1 + 0.5, 0, 255).astype(np.uint8)
        else:
            base = b["color"][y0:y1, x0:x1].astype(np.float32)
            L["color"][y0:y1, x0:x1] = (base * (1 - m3) + s["rgb"] * m3 + 0.5).astype(np.uint8)
            if s["kind"] == "eraser":
                a0 = b["ink_a"][y0:y1, x0:x1].astype(np.float32)
                L["ink_a"][y0:y1, x0:x1] = (a0 * (1 - m) + 0.5).astype(np.uint8)

    def end_stroke(self):
        s, self._stroke = self._stroke, None
        if s is None or s["box"] is None:
            return
        x0, y0, x1, y1 = s["box"]
        old = {n: s["base"][n][y0:y1, x0:x1].copy() for n in s["names"]}
        new = self._snap(s["box"], s["names"])
        if any(not np.array_equal(old[n], new[n]) for n in old):
            self._push(("p", s["box"], old, new))

    # -------------------------------------------------------------- tamaño lienzo
    def resize_canvas(self, dl, dt, dr, db):
        """Nuevo lienzo = rectangulo (dl, dt, w+dr, h+db) en coordenadas actuales.
        Devuelve True si se aplico."""
        nw, nh = self.w + dr - dl, self.h + db - dt
        if nw < 16 or nh < 16 or nw > MAX_SIDE or nh > MAX_SIDE or nw * nh > MAX_AREA:
            return False
        if (dl, dt, dr, db) == (0, 0, 0, 0):
            return False
        before = self._state()
        sx0, sy0 = max(0, dl), max(0, dt)
        sx1, sy1 = min(self.w, self.w + dr), min(self.h, self.h + db)
        newL = {n: _alloc(n, nh, nw) for n in NAMES}
        if sx1 > sx0 and sy1 > sy0:
            for n in NAMES:
                newL[n][sy0 - dt:sy1 - dt, sx0 - dl:sx1 - dl] = self.L[n][sy0:sy1, sx0:sx1]
        self.w, self.h, self.L = nw, nh, newL
        self._push(("r", before))
        self.structural = True
        return True

    def ensure_size(self, min_w, min_h):
        if min_w > self.w or min_h > self.h:
            return self.resize_canvas(0, 0, max(0, min_w - self.w), max(0, min_h - self.h))
        return True

    # --------------------------------------------------------------- selecciones
    def make_selection(self, mask, x, y):
        self.sel = dict(x=int(x), y=int(y), mask=mask.astype(bool), layers=None, src_box=None, src_snap=None)

    def _in_sel(self, px, py):
        s = self.sel
        if not s:
            return False
        lx, ly = px - s["x"], py - s["y"]
        h, w = s["mask"].shape
        return 0 <= lx < w and 0 <= ly < h and bool(s["mask"][ly, lx])

    def sel_contains(self, px, py):
        return self._in_sel(int(np.floor(px)), int(np.floor(py)))

    def _sel_box(self):
        s = self.sel
        h, w = s["mask"].shape
        return (s["x"], s["y"], s["x"] + w, s["y"] + h)

    def _clear_masked(self, box, mask):
        x0, y0, x1, y1 = box
        for n in NAMES:
            self.L[n][y0:y1, x0:x1][mask] = SPEC[n][1]

    def lift(self):
        """Levanta el contenido seleccionado (deja el origen en blanco)."""
        s = self.sel
        if s is None or s["layers"] is not None:
            return self._sel_box() if s else None
        box = self._sel_box()
        s["src_box"] = box
        s["src_snap"] = self._snap(box)
        s["layers"] = {n: a.copy() for n, a in s["src_snap"].items()}
        self._clear_masked(box, s["mask"])
        return box

    def move_sel(self, dx, dy):
        s = self.sel
        old = self._sel_box()
        s["x"] += int(dx)
        s["y"] += int(dy)
        new = self._sel_box()
        b = _union(old, new)
        return self.clamp_box(*b)

    def commit(self):
        """Fija la seleccion flotante. Una sola entrada de historial."""
        s, self.sel = self.sel, None
        if s is None or s["layers"] is None:
            return None
        dbox = (s["x"], s["y"], s["x"] + s["mask"].shape[1], s["y"] + s["mask"].shape[0])
        cd = self.clamp_box(*dbox)
        U = _union(s["src_box"], cd) if s["src_box"] else cd
        if cd[2] <= cd[0] or cd[3] <= cd[1]:
            U = s["src_box"]
            if U is None:
                return None
        old = self._snap(U)
        if s["src_snap"] is not None:
            sx0, sy0, sx1, sy1 = s["src_box"]
            for n in NAMES:
                old[n][sy0 - U[1]:sy1 - U[1], sx0 - U[0]:sx1 - U[0]] = s["src_snap"][n]
        if cd[2] > cd[0] and cd[3] > cd[1]:
            fx0, fy0 = cd[0] - dbox[0], cd[1] - dbox[1]
            fx1, fy1 = fx0 + (cd[2] - cd[0]), fy0 + (cd[3] - cd[1])
            m = s["mask"][fy0:fy1, fx0:fx1]
            for n in NAMES:
                dst = self.L[n][cd[1]:cd[3], cd[0]:cd[2]]
                dst[m] = s["layers"][n][fy0:fy1, fx0:fx1][m]
        new = self._snap(U)
        self._push(("p", U, old, new))
        self.structural = True
        return U

    def cancel(self):
        """Descarta la seleccion; si estaba levantada, vuelve todo a su sitio."""
        s, self.sel = self.sel, None
        if s is None or s["layers"] is None:
            return None
        cur = self.clamp_box(s["x"], s["y"], s["x"] + s["mask"].shape[1], s["y"] + s["mask"].shape[0])
        if s["src_snap"] is not None:
            self._restore(s["src_box"], s["src_snap"])
            return _union(s["src_box"], cur)
        return cur

    def delete_sel(self):
        s = self.sel
        if s is None:
            return None
        if s["layers"] is None:
            box = self._sel_box()
            old = self._snap(box)
            self._clear_masked(box, s["mask"])
            self._push(("p", box, old, self._snap(box)))
            self.sel = None
            self.structural = True
            return box
        cur = self.clamp_box(s["x"], s["y"], s["x"] + s["mask"].shape[1], s["y"] + s["mask"].shape[0])
        self.sel = None
        if s["src_snap"] is None:
            return cur
        self._push(("p", s["src_box"], s["src_snap"], self._snap(s["src_box"])))
        self.structural = True
        return _union(s["src_box"], cur)

    def copy_clip(self):
        s = self.sel
        if s is None:
            return None
        if s["layers"] is not None:
            layers = {n: a.copy() for n, a in s["layers"].items()}
        else:
            layers = self._snap(self._sel_box())
        return {"layers": layers, "mask": s["mask"].copy()}

    def cut(self):
        clip = self.copy_clip()
        box = self.delete_sel()
        return clip, box

    def _new_float(self, layers, mask, x, y):
        h, w = mask.shape
        if not self.ensure_size(x + w, y + h):
            # no cabe ni ampliando: recolocar en la esquina
            x = y = 0
            self.ensure_size(w, h)
        self.sel = dict(x=x, y=y, mask=mask, layers=layers, src_box=None, src_snap=None)
        return self.clamp_box(x, y, x + w, y + h)

    def paste_clip(self, clip, x=0, y=0):
        layers = {n: a.copy() for n, a in clip["layers"].items()}
        return self._new_float(layers, clip["mask"].copy(), x, y)

    def paste_image(self, pil, x=0, y=0):
        """Pega una imagen como referencia SIN procesar (conserva colores)."""
        rgba = np.asarray(pil.convert("RGBA"))
        h, w = rgba.shape[:2]
        if max(h, w) > MAX_SIDE:
            s = MAX_SIDE / max(h, w)
            rgba = cv2.resize(rgba, (max(1, int(w * s)), max(1, int(h * s))), interpolation=cv2.INTER_AREA)
            h, w = rgba.shape[:2]
        mask = rgba[..., 3] > 0
        layers = {n: _alloc(n, h, w) for n in NAMES}
        layers["color"] = np.where(mask[..., None], rgba[..., :3], 255).astype(np.uint8)
        layers["ref"] = mask.astype(np.uint8)
        return self._new_float(layers, mask, x, y)
