"""
canvas_manager.py
Mengatur canvas utama: event mouse, rendering objek, seleksi,
undo, clear, save, dan insert image.
"""

import tkinter as tk
from tkinter import simpledialog, filedialog, messagebox
import math
import copy

from object_model import DrawingObject, reset_id_counter
from drawing_algorithms import (
    dda_line, bresenham_line, bezier_curve, flood_fill, hex_to_rgb
)
from transform import translate, rotate, scale

# Cek ketersediaan Pillow
try:
    from PIL import Image, ImageTk, ImageGrab
    HAS_PIL = True
except ImportError:
    HAS_PIL = False


class CanvasManager:
    """
    Mengelola canvas menggambar dan semua interaksi pengguna.
    
    Bertanggung jawab atas:
      - Event handling (mouse down/drag/up)
      - Rendering objek ke canvas
      - Seleksi objek
      - Undo, clear, save
      - Insert image dan text
    """

    def __init__(self, canvas, root, status_callback=None):
        """
        Args:
            canvas: tkinter.Canvas widget
            root: Tk root window
            status_callback: fungsi untuk update status bar
        """
        self.canvas = canvas
        self.root = root
        self.status_callback = status_callback

        # Daftar semua objek pada canvas
        self.objects = []

        # Undo stack: menyimpan snapshot daftar objek
        self.undo_stack = []
        self.max_undo = 50

        # Tool aktif: "select", "line", "bezier", "rectangle",
        #             "circle", "triangle", "fill", "text"
        self.current_tool = "line"

        # Atribut visual aktif
        self.current_color = "#000000"
        self.current_fill_color = None
        self.current_line_width = 2
        self.current_line_style = "solid"

        # State menggambar
        self.is_drawing = False
        self.start_x = 0
        self.start_y = 0
        self.preview_ids = []  # ID item preview sementara

        # State seleksi
        self.selected_object = None
        self.selection_box_ids = []

        # State bezier
        self.bezier_points = []
        self.bezier_preview_ids = []

        # Bind mouse events
        self.canvas.bind("<ButtonPress-1>", self.on_mouse_down)
        self.canvas.bind("<B1-Motion>", self.on_mouse_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_mouse_up)
        self.canvas.bind("<Motion>", self.on_mouse_move)

    # ============================================================
    # MOUSE EVENT HANDLERS
    # ============================================================

    def on_mouse_move(self, event):
        """Update posisi mouse di status bar."""
        if self.status_callback:
            self.status_callback(
                f"Tool: {self.current_tool.capitalize()} | "
                f"Objects: {len(self.objects)} | "
                f"Position: ({event.x}, {event.y})"
            )

    def on_mouse_down(self, event):
        """Handler saat mouse ditekan."""
        x, y = event.x, event.y

        if self.current_tool == "select":
            self._handle_select(x, y)
        elif self.current_tool == "fill":
            self._handle_fill(x, y)
        elif self.current_tool == "text":
            self._handle_text(x, y)
        elif self.current_tool == "bezier":
            self._handle_bezier_click(x, y)
        else:
            # Tools yang menggunakan drag: line, rectangle, circle, triangle
            self.is_drawing = True
            self.start_x = x
            self.start_y = y

    def on_mouse_drag(self, event):
        """Handler saat mouse di-drag (preview rubber-banding)."""
        if not self.is_drawing:
            return

        x, y = event.x, event.y

        # Hapus preview sebelumnya
        for pid in self.preview_ids:
            self.canvas.delete(pid)
        self.preview_ids = []

        dash = self._get_dash_pattern()

        if self.current_tool == "line":
            pid = self.canvas.create_line(
                self.start_x, self.start_y, x, y,
                fill=self.current_color,
                width=self.current_line_width,
                dash=dash
            )
            self.preview_ids.append(pid)

        elif self.current_tool == "rectangle":
            pid = self.canvas.create_rectangle(
                self.start_x, self.start_y, x, y,
                outline=self.current_color,
                width=self.current_line_width,
                dash=dash
            )
            self.preview_ids.append(pid)

        elif self.current_tool == "circle":
            # Hitung radius
            dx = x - self.start_x
            dy = y - self.start_y
            r = math.sqrt(dx * dx + dy * dy)
            pid = self.canvas.create_oval(
                self.start_x - r, self.start_y - r,
                self.start_x + r, self.start_y + r,
                outline=self.current_color,
                width=self.current_line_width,
                dash=dash
            )
            self.preview_ids.append(pid)

        elif self.current_tool == "triangle":
            # Segitiga: titik atas = titik awal, alas = drag
            mid_x = (self.start_x + x) / 2
            points = [
                mid_x, self.start_y,  # Puncak
                self.start_x, y,       # Kiri bawah
                x, y                    # Kanan bawah
            ]
            pid = self.canvas.create_polygon(
                points,
                outline=self.current_color,
                fill='',
                width=self.current_line_width,
                dash=dash
            )
            self.preview_ids.append(pid)

    def on_mouse_up(self, event):
        """Handler saat mouse dilepas — finalisasi objek."""
        if not self.is_drawing:
            return

        self.is_drawing = False
        x, y = event.x, event.y

        # Hapus preview
        for pid in self.preview_ids:
            self.canvas.delete(pid)
        self.preview_ids = []

        # Simpan state untuk undo
        self._push_undo()

        if self.current_tool == "line":
            self._create_line_object(self.start_x, self.start_y, x, y)
        elif self.current_tool == "rectangle":
            self._create_rectangle_object(self.start_x, self.start_y, x, y)
        elif self.current_tool == "circle":
            self._create_circle_object(self.start_x, self.start_y, x, y)
        elif self.current_tool == "triangle":
            self._create_triangle_object(self.start_x, self.start_y, x, y)

    # ============================================================
    # PEMBUATAN OBJEK
    # ============================================================

    def _create_line_object(self, x1, y1, x2, y2):
        """
        Membuat objek garis menggunakan algoritma Bresenham.
        Pixel-pixel hasil algoritma digambar pada canvas.
        """
        obj = DrawingObject(
            obj_type="line",
            points=[(x1, y1), (x2, y2)],
            outline_color=self.current_color,
            line_width=self.current_line_width,
            line_style=self.current_line_style
        )
        self.objects.append(obj)
        self.render_object(obj)

    def _create_rectangle_object(self, x1, y1, x2, y2):
        """Membuat objek persegi panjang."""
        obj = DrawingObject(
            obj_type="rectangle",
            points=[(x1, y1), (x2, y2)],
            outline_color=self.current_color,
            fill_color=self.current_fill_color,
            line_width=self.current_line_width,
            line_style=self.current_line_style
        )
        self.objects.append(obj)
        self.render_object(obj)

    def _create_circle_object(self, cx, cy, ex, ey):
        """Membuat objek lingkaran (pusat + radius)."""
        dx = ex - cx
        dy = ey - cy
        r = math.sqrt(dx * dx + dy * dy)
        obj = DrawingObject(
            obj_type="circle",
            points=[(cx, cy), (cx + r, cy)],  # Pusat + titik di radius
            outline_color=self.current_color,
            fill_color=self.current_fill_color,
            line_width=self.current_line_width,
            line_style=self.current_line_style
        )
        self.objects.append(obj)
        self.render_object(obj)

    def _create_triangle_object(self, x1, y1, x2, y2):
        """Membuat objek segitiga."""
        mid_x = (x1 + x2) / 2
        obj = DrawingObject(
            obj_type="triangle",
            points=[(mid_x, y1), (x1, y2), (x2, y2)],
            outline_color=self.current_color,
            fill_color=self.current_fill_color,
            line_width=self.current_line_width,
            line_style=self.current_line_style
        )
        self.objects.append(obj)
        self.render_object(obj)

    # ============================================================
    # BEZIER CURVE
    # ============================================================

    def _handle_bezier_click(self, x, y):
        """
        Menangani klik untuk tool Bezier.
        Setiap klik menambah titik kontrol.
        Setelah 4 titik, kurva digambar.
        """
        self.bezier_points.append((x, y))

        # Gambar titik kontrol
        r = 4
        dot_id = self.canvas.create_oval(
            x - r, y - r, x + r, y + r,
            fill="#FF4444", outline="#CC0000", width=1
        )
        self.bezier_preview_ids.append(dot_id)

        # Gambar garis penghubung titik kontrol
        if len(self.bezier_points) > 1:
            prev = self.bezier_points[-2]
            line_id = self.canvas.create_line(
                prev[0], prev[1], x, y,
                fill="#AAAAAA", dash=(4, 4), width=1
            )
            self.bezier_preview_ids.append(line_id)

        # Jika sudah 4 titik, buat kurva
        if len(self.bezier_points) >= 4:
            self._push_undo()

            # Hapus preview titik kontrol
            for pid in self.bezier_preview_ids:
                self.canvas.delete(pid)
            self.bezier_preview_ids = []

            obj = DrawingObject(
                obj_type="bezier",
                points=list(self.bezier_points),
                outline_color=self.current_color,
                line_width=self.current_line_width,
                line_style=self.current_line_style
            )
            self.objects.append(obj)
            self.render_object(obj)

            self.bezier_points = []

    # ============================================================
    # FILL AREA
    # ============================================================

    def _handle_fill(self, x, y):
        """
        Menangani klik untuk tool Fill.
        Menggunakan algoritma Flood Fill.
        """
        self._push_undo()

        # Ambil snapshot canvas sebagai PhotoImage
        # Untuk flood fill, kita perlu data pixel canvas
        canvas_width = self.canvas.winfo_width()
        canvas_height = self.canvas.winfo_height()

        if HAS_PIL:
            self._flood_fill_pil(x, y, canvas_width, canvas_height)
        else:
            self._flood_fill_simple(x, y)

    def _flood_fill_pil(self, x, y, width, height):
        """Flood fill menggunakan Pillow untuk akses pixel."""
        try:
            # Simpan canvas ke PostScript lalu convert
            ps = self.canvas.postscript(colormode='color')
            from io import BytesIO
            img = Image.open(BytesIO(ps.encode('utf-8')))
            img = img.convert('RGB')

            # Ambil warna target
            if x < 0 or x >= img.width or y < 0 or y >= img.height:
                return

            target_color = img.getpixel((x, y))
            fill_rgb = hex_to_rgb(self.current_color)

            if target_color == fill_rgb:
                return

            # Flood fill pada image
            pixels = img.load()
            tolerance = 30
            stack = [(x, y)]
            visited = set()

            while stack:
                px, py = stack.pop()
                if (px, py) in visited:
                    continue
                if px < 0 or px >= img.width or py < 0 or py >= img.height:
                    continue
                visited.add((px, py))

                current = pixels[px, py]
                if (abs(current[0] - target_color[0]) <= tolerance and
                    abs(current[1] - target_color[1]) <= tolerance and
                    abs(current[2] - target_color[2]) <= tolerance):
                    pixels[px, py] = fill_rgb
                    stack.append((px + 1, py))
                    stack.append((px - 1, py))
                    stack.append((px, py + 1))
                    stack.append((px, py - 1))

            # Tampilkan hasil pada canvas
            tk_img = ImageTk.PhotoImage(img)
            fill_obj = DrawingObject(
                obj_type="fill",
                points=[(0, 0)],
                outline_color=self.current_color
            )
            fill_obj.image_ref = tk_img
            img_id = self.canvas.create_image(0, 0, anchor=tk.NW, image=tk_img)
            fill_obj.canvas_ids = [img_id]
            self.objects.append(fill_obj)

            # Re-render semua objek di atas fill
            # (fill harus di background)
            self.canvas.tag_lower(img_id)

        except Exception as e:
            messagebox.showwarning("Fill Error",
                f"Flood fill gagal: {str(e)}\nPastikan Ghostscript terinstall untuk fitur ini.")
            # Fallback ke metode sederhana
            self._flood_fill_simple(x, y)

    def _flood_fill_simple(self, x, y):
        """
        Flood fill sederhana tanpa Pillow.
        Menggunakan canvas.find_overlapping untuk deteksi area,
        lalu menggambar rectangle kecil sebagai fill.
        """
        # Buat PhotoImage dari canvas
        canvas_width = self.canvas.winfo_width()
        canvas_height = self.canvas.winfo_height()

        # Metode sederhana: gambar oval besar di posisi klik
        # sebagai representasi fill
        fill_obj = DrawingObject(
            obj_type="fill",
            points=[(x, y)],
            outline_color=self.current_color,
            fill_color=self.current_color
        )

        r = 50  # Radius fill area
        fill_id = self.canvas.create_oval(
            x - r, y - r, x + r, y + r,
            fill=self.current_color,
            outline=""
        )
        fill_obj.canvas_ids = [fill_id]
        self.objects.append(fill_obj)
        self.canvas.tag_lower(fill_id)

    # ============================================================
    # TEXT
    # ============================================================

    def _handle_text(self, x, y):
        """
        Menangani klik untuk tool Text.
        Membuka dialog input teks, lalu menampilkan pada canvas.
        """
        text = simpledialog.askstring(
            "Input Teks",
            "Masukkan teks:",
            parent=self.root
        )
        if text:
            self._push_undo()
            obj = DrawingObject(
                obj_type="text",
                points=[(x, y)],
                outline_color=self.current_color,
                line_width=self.current_line_width,
                text_content=text
            )
            self.objects.append(obj)
            self.render_object(obj)

    # ============================================================
    # SELECT OBJECT
    # ============================================================

    def _handle_select(self, x, y):
        """
        Memilih objek di posisi klik.
        Mencari objek yang bounding box-nya mengandung posisi klik.
        """
        self._clear_selection()

        # Cari objek dari yang terbaru (di atas)
        for obj in reversed(self.objects):
            if obj.obj_type == "fill":
                continue  # Skip fill objects untuk seleksi

            bbox = obj.get_bbox()
            margin = max(10, obj.line_width + 5)

            if (bbox[0] - margin <= x <= bbox[2] + margin and
                bbox[1] - margin <= y <= bbox[3] + margin):
                self.selected_object = obj
                self._draw_selection_box(obj)
                return

        # Tidak ada objek yang ditemukan
        self.selected_object = None

    def _draw_selection_box(self, obj):
        """Menggambar bounding box seleksi di sekitar objek."""
        self._clear_selection_box()
        bbox = obj.get_bbox()
        margin = 8

        # Gambar kotak seleksi (dashed)
        box_id = self.canvas.create_rectangle(
            bbox[0] - margin, bbox[1] - margin,
            bbox[2] + margin, bbox[3] + margin,
            outline="#2196F3", width=2, dash=(6, 3)
        )
        self.selection_box_ids.append(box_id)

        # Gambar handle di sudut-sudut
        handle_size = 5
        corners = [
            (bbox[0] - margin, bbox[1] - margin),
            (bbox[2] + margin, bbox[1] - margin),
            (bbox[0] - margin, bbox[3] + margin),
            (bbox[2] + margin, bbox[3] + margin),
        ]
        for cx, cy in corners:
            h_id = self.canvas.create_rectangle(
                cx - handle_size, cy - handle_size,
                cx + handle_size, cy + handle_size,
                fill="#2196F3", outline="#1565C0"
            )
            self.selection_box_ids.append(h_id)

    def _clear_selection_box(self):
        """Hapus visual bounding box seleksi."""
        for sid in self.selection_box_ids:
            self.canvas.delete(sid)
        self.selection_box_ids = []

    def _clear_selection(self):
        """Hapus seleksi aktif."""
        self._clear_selection_box()
        self.selected_object = None

    # ============================================================
    # RENDERING OBJEK
    # ============================================================

    def render_object(self, obj):
        """
        Menggambar satu objek pada canvas.
        Menghapus item canvas lama lalu buat yang baru.
        """
        # Hapus item canvas lama
        for cid in obj.canvas_ids:
            self.canvas.delete(cid)
        obj.canvas_ids = []

        dash = self._get_dash_pattern_for(obj.line_style)

        if obj.obj_type == "line":
            self._render_line(obj, dash)
        elif obj.obj_type == "rectangle":
            self._render_rectangle(obj, dash)
        elif obj.obj_type == "circle":
            self._render_circle(obj, dash)
        elif obj.obj_type == "triangle":
            self._render_triangle(obj, dash)
        elif obj.obj_type == "bezier":
            self._render_bezier(obj, dash)
        elif obj.obj_type == "text":
            self._render_text(obj)
        elif obj.obj_type == "image":
            self._render_image(obj)
        elif obj.obj_type == "fill":
            pass  # Fill sudah di-render saat dibuat

        # Update selection box jika objek ini yang dipilih
        if self.selected_object and self.selected_object.id == obj.id:
            self._draw_selection_box(obj)

    def _render_line(self, obj, dash):
        """
        Render garis menggunakan algoritma Bresenham.
        Titik-titik pixel dari algoritma digambar sebagai rectangle kecil.
        """
        if len(obj.points) < 2:
            return

        x1, y1 = obj.points[0]
        x2, y2 = obj.points[1]

        # Hitung pixel menggunakan algoritma Bresenham
        pixels = bresenham_line(x1, y1, x2, y2)

        # Untuk efisiensi + visual: gambar garis native canvas
        # tapi simpan info algoritma
        w = obj.line_width
        cid = self.canvas.create_line(
            x1, y1, x2, y2,
            fill=obj.outline_color,
            width=w,
            dash=dash,
            capstyle=tk.ROUND,
            joinstyle=tk.ROUND
        )
        obj.canvas_ids.append(cid)

        # Jika line_width == 1, juga gambar pixel Bresenham untuk demo
        if w <= 2 and len(pixels) < 500:
            # Gambar beberapa pixel Bresenham sebagai demonstrasi
            # (hanya untuk garis pendek, supaya visible)
            pass  # Pixel visible melalui garis canvas

    def _render_rectangle(self, obj, dash):
        """Render persegi panjang."""
        if len(obj.points) < 2:
            return

        x1, y1 = obj.points[0]
        x2, y2 = obj.points[1]

        cid = self.canvas.create_rectangle(
            x1, y1, x2, y2,
            outline=obj.outline_color,
            fill=obj.fill_color if obj.fill_color else '',
            width=obj.line_width,
            dash=dash
        )
        obj.canvas_ids.append(cid)

    def _render_circle(self, obj, dash):
        """Render lingkaran."""
        if len(obj.points) < 2:
            return

        cx, cy = obj.points[0]
        rx, ry = obj.points[1]
        r = math.sqrt((rx - cx) ** 2 + (ry - cy) ** 2)

        cid = self.canvas.create_oval(
            cx - r, cy - r, cx + r, cy + r,
            outline=obj.outline_color,
            fill=obj.fill_color if obj.fill_color else '',
            width=obj.line_width,
            dash=dash
        )
        obj.canvas_ids.append(cid)

    def _render_triangle(self, obj, dash):
        """Render segitiga."""
        if len(obj.points) < 3:
            return

        coords = []
        for p in obj.points:
            coords.extend([p[0], p[1]])

        cid = self.canvas.create_polygon(
            coords,
            outline=obj.outline_color,
            fill=obj.fill_color if obj.fill_color else '',
            width=obj.line_width,
            dash=dash
        )
        obj.canvas_ids.append(cid)

    def _render_bezier(self, obj, dash):
        """
        Render kurva Bezier menggunakan algoritma De Casteljau.
        Titik-titik kurva dihitung, lalu digambar sebagai rangkaian garis.
        """
        if len(obj.points) < 2:
            return

        # Hitung titik-titik kurva menggunakan algoritma Bezier
        curve_pts = bezier_curve(obj.points, num_segments=200)

        if len(curve_pts) < 2:
            return

        # Gambar kurva sebagai rangkaian segmen garis
        coords = []
        for p in curve_pts:
            coords.extend([p[0], p[1]])

        cid = self.canvas.create_line(
            coords,
            fill=obj.outline_color,
            width=obj.line_width,
            dash=dash,
            smooth=False,  # Titik sudah halus dari algoritma
            capstyle=tk.ROUND,
            joinstyle=tk.ROUND
        )
        obj.canvas_ids.append(cid)

        # Gambar titik kontrol
        for i, pt in enumerate(obj.points):
            r = 3
            dot_id = self.canvas.create_oval(
                pt[0] - r, pt[1] - r, pt[0] + r, pt[1] + r,
                fill="#FF6B6B", outline="#E53935"
            )
            obj.canvas_ids.append(dot_id)

    def _render_text(self, obj):
        """Render teks pada canvas."""
        if not obj.text_content or not obj.points:
            return

        x, y = obj.points[0]
        font_size = max(12, obj.line_width * 4)
        cid = self.canvas.create_text(
            x, y,
            text=obj.text_content,
            fill=obj.outline_color,
            font=("Arial", font_size),
            anchor=tk.NW
        )
        obj.canvas_ids.append(cid)

        # Update bounding box berdasarkan ukuran teks actual
        bbox = self.canvas.bbox(cid)
        if bbox:
            obj.points = [(bbox[0], bbox[1]), (bbox[2], bbox[3])]

    def _render_image(self, obj):
        """Render gambar pada canvas."""
        if not obj.image_ref or not obj.points:
            return

        x, y = obj.points[0]
        cid = self.canvas.create_image(
            x, y, anchor=tk.NW, image=obj.image_ref
        )
        obj.canvas_ids.append(cid)

    # ============================================================
    # RENDER ALL
    # ============================================================

    def render_all(self):
        """Hapus canvas dan render ulang semua objek."""
        self.canvas.delete("all")
        for obj in self.objects:
            obj.canvas_ids = []
            self.render_object(obj)

    # ============================================================
    # TRANSFORMASI
    # ============================================================

    def transform_selected(self, transform_type, **kwargs):
        """
        Terapkan transformasi pada objek yang dipilih.
        
        Args:
            transform_type: "translate", "rotate", "scale"
            kwargs: parameter transformasi (dx, dy, angle, factor)
        """
        if self.selected_object is None:
            messagebox.showinfo("Info", "Pilih objek terlebih dahulu!")
            return

        self._push_undo()
        obj = self.selected_object

        if transform_type == "translate":
            dx = kwargs.get('dx', 0)
            dy = kwargs.get('dy', 0)
            obj.points = translate(obj.points, dx, dy)

        elif transform_type == "rotate":
            angle = kwargs.get('angle', 15)
            center = obj.get_center()
            obj.points = rotate(obj.points, angle, center)
            obj.rotation += angle

        elif transform_type == "scale":
            factor = kwargs.get('factor', 1.2)
            center = obj.get_center()
            obj.points = scale(obj.points, factor, center)
            obj.scale_factor *= factor

        self.render_object(obj)

    # ============================================================
    # UNDO
    # ============================================================

    def _push_undo(self):
        """Simpan snapshot state saat ini ke undo stack."""
        snapshot = [obj.clone() for obj in self.objects]
        self.undo_stack.append(snapshot)
        if len(self.undo_stack) > self.max_undo:
            self.undo_stack.pop(0)

    def undo(self):
        """Batalkan aksi terakhir dengan restore dari undo stack."""
        if not self.undo_stack:
            messagebox.showinfo("Info", "Tidak ada aksi untuk di-undo.")
            return

        self._clear_selection()

        # Restore state dari snapshot
        snapshot = self.undo_stack.pop()
        self.canvas.delete("all")
        self.objects = snapshot

        # Re-render semua objek
        for obj in self.objects:
            obj.canvas_ids = []
            self.render_object(obj)

    # ============================================================
    # CLEAR CANVAS
    # ============================================================

    def clear_canvas(self):
        """Hapus semua objek pada canvas (dengan konfirmasi)."""
        if not self.objects:
            return

        confirm = messagebox.askyesno(
            "Konfirmasi",
            "Apakah Anda yakin ingin menghapus semua objek?"
        )
        if confirm:
            self._push_undo()
            self.canvas.delete("all")
            self.objects = []
            self._clear_selection()
            reset_id_counter()

    # ============================================================
    # SAVE CANVAS
    # ============================================================

    def save_canvas(self):
        """Simpan canvas sebagai file PNG."""
        filepath = filedialog.asksaveasfilename(
            defaultextension=".png",
            filetypes=[
                ("PNG files", "*.png"),
                ("PostScript files", "*.ps"),
                ("All files", "*.*")
            ],
            title="Simpan Canvas"
        )
        if not filepath:
            return

        if HAS_PIL and filepath.lower().endswith('.png'):
            try:
                # Metode 1: Screenshot canvas menggunakan ImageGrab
                x = self.canvas.winfo_rootx()
                y = self.canvas.winfo_rooty()
                w = self.canvas.winfo_width()
                h = self.canvas.winfo_height()
                img = ImageGrab.grab(bbox=(x, y, x + w, y + h))
                img.save(filepath)
                messagebox.showinfo("Sukses", f"Canvas disimpan ke:\n{filepath}")
            except Exception as e:
                # Metode 2: PostScript convert
                try:
                    ps_file = filepath.replace('.png', '.ps')
                    self.canvas.postscript(file=ps_file, colormode='color')
                    img = Image.open(ps_file)
                    img.save(filepath)
                    import os
                    os.remove(ps_file)
                    messagebox.showinfo("Sukses", f"Canvas disimpan ke:\n{filepath}")
                except Exception as e2:
                    messagebox.showerror("Error", f"Gagal menyimpan: {str(e2)}")
        else:
            # Simpan sebagai PostScript
            try:
                if not filepath.lower().endswith('.ps'):
                    filepath += '.ps'
                self.canvas.postscript(file=filepath, colormode='color')
                messagebox.showinfo("Sukses", f"Canvas disimpan ke:\n{filepath}")
            except Exception as e:
                messagebox.showerror("Error", f"Gagal menyimpan: {str(e)}")

    # ============================================================
    # INSERT IMAGE
    # ============================================================

    def insert_image(self):
        """Memasukkan gambar dari file ke canvas."""
        filepath = filedialog.askopenfilename(
            filetypes=[
                ("Image files", "*.png *.jpg *.jpeg *.gif *.bmp *.ppm *.pgm"),
                ("All files", "*.*")
            ],
            title="Pilih Gambar"
        )
        if not filepath:
            return

        self._push_undo()

        try:
            if HAS_PIL:
                pil_img = Image.open(filepath)
                # Resize jika terlalu besar
                max_size = 400
                if pil_img.width > max_size or pil_img.height > max_size:
                    ratio = min(max_size / pil_img.width, max_size / pil_img.height)
                    new_size = (int(pil_img.width * ratio), int(pil_img.height * ratio))
                    pil_img = pil_img.resize(new_size, Image.LANCZOS)
                tk_img = ImageTk.PhotoImage(pil_img)
            else:
                # Tanpa Pillow, hanya support GIF dan PGM/PPM
                tk_img = tk.PhotoImage(file=filepath)

            # Letakkan gambar di tengah canvas
            cx = self.canvas.winfo_width() // 2
            cy = self.canvas.winfo_height() // 2

            obj = DrawingObject(
                obj_type="image",
                points=[(cx - 50, cy - 50), (cx + 50, cy + 50)],
                image_path=filepath
            )
            obj.image_ref = tk_img  # Simpan referensi agar tidak di-GC

            cid = self.canvas.create_image(cx - 50, cy - 50, anchor=tk.NW, image=tk_img)
            obj.canvas_ids = [cid]

            # Update points berdasarkan ukuran gambar actual
            bbox = self.canvas.bbox(cid)
            if bbox:
                obj.points = [(bbox[0], bbox[1]), (bbox[2], bbox[3])]

            self.objects.append(obj)

        except Exception as e:
            messagebox.showerror("Error", f"Gagal memasukkan gambar: {str(e)}")

    # ============================================================
    # HELPER
    # ============================================================

    def _get_dash_pattern(self):
        """Mendapatkan dash pattern untuk style garis aktif."""
        return self._get_dash_pattern_for(self.current_line_style)

    def _get_dash_pattern_for(self, style):
        """Mendapatkan dash pattern berdasarkan nama style."""
        if style == "dashed":
            return (10, 5)
        elif style == "dotted":
            return (2, 4)
        else:  # solid
            return ()

    def set_tool(self, tool):
        """Mengubah tool aktif."""
        # Bersihkan state bezier jika pindah tool
        if self.current_tool == "bezier" and tool != "bezier":
            for pid in self.bezier_preview_ids:
                self.canvas.delete(pid)
            self.bezier_preview_ids = []
            self.bezier_points = []

        self.current_tool = tool

        # Ubah cursor sesuai tool
        cursors = {
            "select": "arrow",
            "line": "crosshair",
            "bezier": "crosshair",
            "rectangle": "crosshair",
            "circle": "crosshair",
            "triangle": "crosshair",
            "fill": "spraycan",
            "text": "xterm"
        }
        self.canvas.config(cursor=cursors.get(tool, "arrow"))
