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
    dda_line, bresenham_line, bezier_curve, bspline_curve, flood_fill, boundary_fill, hex_to_rgb
)
from transform import translate, rotate, scale, reflect

# Cek ketersediaan Pillow
try:
    from PIL import Image, ImageTk, ImageGrab, ImageDraw
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
        self.current_line_algorithm = "Bresenham"
        self.current_curve_algorithm = "Bezier"
        self.current_fill_algorithm = "Flood Fill"

        # State menggambar
        self.is_drawing = False
        self.start_x = 0
        self.start_y = 0
        self.preview_ids = []  # ID item preview sementara

        # State seleksi
        self.selected_object = None
        self.selection_box_ids = []

        # Interactive selection transform state
        self.selection_mode = None  # None | 'translate' | 'rotate'
        self.selection_drag_start = (0, 0)
        self.selection_orig_points = None
        self.selection_orig_rotation = 0.0
        self.selection_center = None

        # State bezier
        self.bezier_points = []
        self.bezier_preview_ids = []

        # State pencil/eraser
        self.freehand_points = []
        self.freehand_preview_ids = []

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
        x, y = event.x, event.y
        # Change cursor if hovering over selection handles when in select mode
        if self.current_tool == 'select':
            items = self.canvas.find_overlapping(x, y, x, y)
            cursor = None
            for cid in items:
                tags = self.canvas.gettags(cid)
                if 'rotation_handle' in tags:
                    cursor = 'exchange'  # rotate-like cursor
                    break
                if any(t.startswith('corner_') for t in tags):
                    cursor = 'size_nw_se'  # generic scale cursor
                    break
                if 'selection_handle' in tags or 'selection_box' in tags:
                    cursor = 'fleur'  # move
                    break
            if cursor:
                try:
                    self.canvas.config(cursor=cursor)
                except Exception:
                    pass
            else:
                # default status update
                if self.status_callback:
                    self.status_callback(
                        f"Tool: {self.current_tool.capitalize()} | "
                        f"Objects: {len(self.objects)} | "
                        f"Position: ({x}, {y})"
                    )
        else:
            if self.status_callback:
                self.status_callback(
                    f"Tool: {self.current_tool.capitalize()} | "
                    f"Objects: {len(self.objects)} | "
                    f"Position: ({x}, {y})"
                )

    def on_mouse_down(self, event):
        """Handler saat mouse ditekan."""
        x, y = event.x, event.y

        if self.current_tool == "select":
            # If clicking on selection visuals, start translate/rotate instead of re-selecting
            clicked = False
            # find small overlapping items at the click
            items = self.canvas.find_overlapping(x, y, x, y)
            for cid in items:
                tags = self.canvas.gettags(cid)
                if 'rotation_handle' in tags and self.selected_object:
                    # Start rotation
                    self.selection_mode = 'rotate'
                    self.selection_center = self.selected_object.get_center()
                    cx, cy = self.selection_center
                    # angle in degrees from center to mouse
                    self.selection_rotate_start_angle = math.degrees(math.atan2(y - cy, x - cx))
                    self.selection_orig_points = [p for p in self.selected_object.points]
                    self.selection_orig_rotation = getattr(self.selected_object, 'rotation', 0.0)
                    # Save undo snapshot for the whole drag operation
                    self._push_undo()
                    clicked = True
                    break
                if any(t.startswith('corner_') for t in tags) and self.selected_object:
                    # Start scale from corner
                    corner_tag = [t for t in tags if t.startswith('corner_')][0]
                    corner_idx = int(corner_tag.split('_')[1])
                    self.selection_mode = 'scale'
                    self.selection_scale_corner = corner_idx
                    self.selection_orig_points = [p for p in self.selected_object.points]
                    self.selection_scale_origin = self.selected_object.get_center()
                    # store original scale metadata
                    self.selection_orig_scale = getattr(self.selected_object, 'scale_factor', 1.0)
                    self.selection_drag_start = (x, y)
                    self._push_undo()
                    clicked = True
                    break
                if ('selection_box' in tags or 'selection_handle' in tags) and self.selected_object:
                    # Start translate
                    self.selection_mode = 'translate'
                    self.selection_drag_start = (x, y)
                    self.selection_orig_points = [p for p in self.selected_object.points]
                    self._push_undo()
                    clicked = True
                    break

            # If click didn't hit visual handles but is inside selected object's bbox, start translate
            if not clicked and self.selected_object:
                bbox = self.selected_object.get_bbox()
                margin = 8
                if (bbox[0] - margin <= x <= bbox[2] + margin and
                    bbox[1] - margin <= y <= bbox[3] + margin):
                    self.selection_mode = 'translate'
                    self.selection_drag_start = (x, y)
                    self.selection_orig_points = [p for p in self.selected_object.points]
                    self._push_undo()
                    clicked = True

            if clicked:
                return

            # Otherwise perform selection as before
            self._handle_select(x, y)
        elif self.current_tool == "fill":
            self._handle_fill(x, y)
        elif self.current_tool == "text":
            self._handle_text(x, y)
        elif self.current_tool == "bezier":
            self._handle_bezier_click(x, y)
        elif self.current_tool in ["pencil", "eraser"]:
            self.is_drawing = True
            self.freehand_points = [(x, y)]
            self.start_x, self.start_y = x, y
        else:
            # Tools yang menggunakan drag: line, rectangle, circle, triangle, trapezium, ellipse
            self.is_drawing = True
            self.start_x = x
            self.start_y = y

    def on_mouse_drag(self, event):
        """Handler saat mouse di-drag (preview rubber-banding)."""
        # If an interactive selection transform is active, handle it
        if self.current_tool == 'select' and self.selection_mode and self.selected_object:
            x, y = event.x, event.y
            obj = self.selected_object
            if self.selection_mode == 'translate':
                sx, sy = self.selection_drag_start
                dx = x - sx
                dy = y - sy
                # Apply translation relative to original points
                obj.points = translate(self.selection_orig_points, dx, dy)
                self.render_object(obj)
                return
            elif self.selection_mode == 'rotate':
                cx, cy = self.selection_center
                start_angle = self.selection_rotate_start_angle
                curr_angle = math.degrees(math.atan2(y - cy, x - cx))
                delta = curr_angle - start_angle
                # Rotate original points by delta
                obj.points = rotate(self.selection_orig_points, delta, (cx, cy))
                obj.rotation = self.selection_orig_rotation + delta
                self.render_object(obj)
                return
            elif self.selection_mode == 'scale':
                # Proportional scaling based on dragged corner
                # Determine bbox of original points
                orig_pts = self.selection_orig_points
                xs = [p[0] for p in orig_pts]
                ys = [p[1] for p in orig_pts]
                x_min, x_max = min(xs), max(xs)
                y_min, y_max = min(ys), max(ys)

                # corner index mapping: 0=tl,1=tr,2=bl,3=br (as created)
                corner_idx = getattr(self, 'selection_scale_corner', 3)
                # opposite corner
                opp = {0:3, 1:2, 2:1, 3:0}[corner_idx]
                corners = [(x_min, y_min), (x_max, y_min), (x_min, y_max), (x_max, y_max)]
                ox, oy = corners[opp]

                # original distance from opposite corner to dragged corner
                sx0, sy0 = corners[corner_idx]
                # current mouse position (x,y) determines new corner position
                nx, ny = x, y

                # Compute scale factors along x and y (proportional scaling uses average)
                orig_dx = sx0 - ox
                orig_dy = sy0 - oy
                new_dx = nx - ox
                new_dy = ny - oy

                # Avoid division by zero
                sx_fact = (new_dx / orig_dx) if orig_dx != 0 else (new_dx / (abs(orig_dx) + 1e-6))
                sy_fact = (new_dy / orig_dy) if orig_dy != 0 else (new_dy / (abs(orig_dy) + 1e-6))
                # Use uniform scale = average of absolute factors, preserve sign
                scale_factor = (abs(sx_fact) + abs(sy_fact)) / 2.0
                # Determine final factor sign by area ratio
                if (sx_fact < 0) ^ (sy_fact < 0):
                    # If signs differ, keep positive scale (flip handled by reflect)
                    pass

                # Apply scaling around opposite corner (ox,oy)
                obj.points = scale(self.selection_orig_points, scale_factor, (ox, oy))
                obj.scale_factor = getattr(self, 'selection_orig_scale', 1.0) * scale_factor
                self.render_object(obj)
                return

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

        elif self.current_tool == "trapezium":
            # Trapezium: sisi atas lebih pendek dari sisi bawah
            w = abs(x - self.start_x)
            points = [
                self.start_x + w * 0.25, self.start_y,
                self.start_x + w * 0.75, self.start_y,
                x, y,
                self.start_x, y
            ]
            pid = self.canvas.create_polygon(
                points,
                outline=self.current_color,
                fill='',
                width=self.current_line_width,
                dash=dash
            )
            self.preview_ids.append(pid)

        elif self.current_tool == "ellipse":
            pid = self.canvas.create_oval(
                self.start_x, self.start_y, x, y,
                outline=self.current_color,
                width=self.current_line_width,
                dash=dash
            )
            self.preview_ids.append(pid)

        elif self.current_tool in ["pencil", "eraser"]:
            color = "#FFFFFF" if self.current_tool == "eraser" else self.current_color
            w = max(5, self.current_line_width * 2) if self.current_tool == "eraser" else self.current_line_width
            
            last_x, last_y = self.freehand_points[-1]
            pid = self.canvas.create_line(
                last_x, last_y, x, y,
                fill=color,
                width=w,
                capstyle=tk.ROUND,
                joinstyle=tk.ROUND
            )
            self.freehand_preview_ids.append(pid)
            self.freehand_points.append((x, y))

    def on_mouse_up(self, event):
        """Handler saat mouse dilepas — finalisasi objek."""
        # If we were doing an interactive selection transform, finalize it
        if self.selection_mode is not None:
            # End translate/rotate mode
            self.selection_mode = None
            self.selection_drag_start = (0, 0)
            self.selection_orig_points = None
            self.selection_center = None
            # No further action required; render_object was called during drag
            return

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
        elif self.current_tool == "trapezium":
            self._create_trapezium_object(self.start_x, self.start_y, x, y)
        elif self.current_tool == "ellipse":
            self._create_ellipse_object(self.start_x, self.start_y, x, y)
        elif self.current_tool in ["pencil", "eraser"]:
            color = "#FFFFFF" if self.current_tool == "eraser" else self.current_color
            w = max(5, self.current_line_width * 2) if self.current_tool == "eraser" else self.current_line_width
            obj = DrawingObject(
                obj_type="freehand",
                points=list(self.freehand_points),
                outline_color=color,
                line_width=w
            )
            self.objects.append(obj)
            # Karena freehand preview sudah tergambar di canvas, hapus preview
            for pid in self.freehand_preview_ids:
                self.canvas.delete(pid)
            self.freehand_preview_ids = []
            self.freehand_points = []
            self.render_object(obj)

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
            line_style=self.current_line_style,
            algorithm=self.current_line_algorithm
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

    def _create_trapezium_object(self, x1, y1, x2, y2):
        """Membuat objek Trapezium."""
        w = abs(x2 - x1)
        points = [
            (x1 + w * 0.25, y1),
            (x1 + w * 0.75, y1),
            (x2, y2),
            (x1, y2)
        ]
        obj = DrawingObject(
            obj_type="trapezium",
            points=points,
            outline_color=self.current_color,
            fill_color=self.current_fill_color,
            line_width=self.current_line_width,
            line_style=self.current_line_style
        )
        self.objects.append(obj)
        self.render_object(obj)

    def _create_ellipse_object(self, x1, y1, x2, y2):
        """Membuat objek Ellipse."""
        obj = DrawingObject(
            obj_type="ellipse",
            points=[(x1, y1), (x2, y2)],
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
                line_style=self.current_line_style,
                algorithm=self.current_curve_algorithm
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
            # Render canvas contents into a PIL Image instead of screen capture.
            # This avoids requiring screen access / ImageGrab permissions.
            img = self._render_canvas_to_pil(width, height)

            # Ambil warna target
            if x < 0 or x >= img.width or y < 0 or y >= img.height:
                return

            target_color = img.getpixel((x, y))
            fill_color = self.current_fill_color or self.current_color
            fill_rgb = hex_to_rgb(fill_color)

            if target_color == fill_rgb:
                return

            # Flood fill / Boundary fill pada image
            pixels = img.load()
            tolerance = 30
            stack = [(x, y)]
            visited = set()
            
            algo = getattr(self, 'current_fill_algorithm', 'Flood Fill')
            is_boundary = ("boundary" in algo.lower())
            
            # Untuk boundary fill, asumsi boundary color adalah warna outline saat ini
            # atau kita bisa asumsikan boundary adalah sesuatu yang beda dengan target_color
            # Di sini kita gunakan warna saat ini (current_color) sebagai boundary color
            boundary_color = hex_to_rgb(self.current_color)

            while stack:
                px, py = stack.pop()
                if (px, py) in visited:
                    continue
                if px < 0 or px >= img.width or py < 0 or py >= img.height:
                    continue
                visited.add((px, py))

                current = pixels[px, py]
                
                if is_boundary:
                    # Boundary Fill
                    is_boundary_color = (abs(current[0] - boundary_color[0]) <= tolerance and
                                         abs(current[1] - boundary_color[1]) <= tolerance and
                                         abs(current[2] - boundary_color[2]) <= tolerance)
                    is_fill_color = (abs(current[0] - fill_rgb[0]) <= tolerance and
                                     abs(current[1] - fill_rgb[1]) <= tolerance and
                                     abs(current[2] - fill_rgb[2]) <= tolerance)
                    
                    if not is_boundary_color and not is_fill_color:
                        pixels[px, py] = fill_rgb
                        stack.append((px + 1, py))
                        stack.append((px - 1, py))
                        stack.append((px, py + 1))
                        stack.append((px, py - 1))
                else:
                    # Flood Fill
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
                outline_color=fill_color,
                fill_color=fill_color
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
                f"Flood fill gagal: {str(e)}\nPastikan Pillow terinstall dan akses screenshot diizinkan.")
            # Fallback ke metode sederhana
            self._flood_fill_simple(x, y)

    def _render_canvas_to_pil(self, width, height):
        """
        Renderkan current objects menjadi sebuah PIL.Image RGB berukuran (width, height).

        Tujuan: menghindari ImageGrab/screen capture. Metode ini mencoba menggambar
        semua objek vektor yang kita simpan (lines, rectangles, circles, polygons,
        text) pada sebuah ImageDraw. Untuk objek image, jika kita punya referensi
        PhotoImage pada objek, kita paste-nya ke image hasil.

        Catatan: Ini adalah renderer sederhana yang mencukupi untuk operasi fill.
        Tidak menjamin kesempurnaan visual identik dengan tkinter.Canvas.
        """
        img = Image.new('RGB', (max(1, width), max(1, height)), (255, 255, 255))
        draw = ImageDraw.Draw(img)

        for obj in self.objects:
            try:
                otype = obj.obj_type
                if otype == 'line':
                    p0, p1 = obj.points[0], obj.points[1]
                    draw.line([p0, p1], fill=obj.outline_color, width=max(1, int(obj.line_width)))
                elif otype in ('rectangle', 'ellipse'):
                    (x1, y1), (x2, y2) = obj.points[0], obj.points[1]
                    box = [x1, y1, x2, y2]
                    if otype == 'rectangle':
                        if obj.fill_color:
                            draw.rectangle(box, fill=obj.fill_color, outline=obj.outline_color, width=max(1, int(obj.line_width)))
                        else:
                            draw.rectangle(box, outline=obj.outline_color, width=max(1, int(obj.line_width)))
                    else:
                        if obj.fill_color:
                            draw.ellipse(box, fill=obj.fill_color, outline=obj.outline_color, width=max(1, int(obj.line_width)))
                        else:
                            draw.ellipse(box, outline=obj.outline_color, width=max(1, int(obj.line_width)))
                elif otype in ('triangle', 'trapezium', 'bezier'):
                    pts = [tuple(p) for p in obj.points]
                    if obj.fill_color:
                        draw.polygon(pts, fill=obj.fill_color, outline=obj.outline_color)
                    else:
                        draw.line(pts + [pts[0]], fill=obj.outline_color, width=max(1, int(obj.line_width)))
                elif otype == 'freehand':
                    pts = [tuple(p) for p in obj.points]
                    if len(pts) >= 2:
                        draw.line(pts, fill=obj.outline_color, width=max(1, int(obj.line_width)))
                elif otype == 'text':
                    # Simple text draw (no advanced font handling)
                    xy = obj.points[0]
                    draw.text((xy[0], xy[1]), str(obj.text_content or ''), fill=obj.outline_color)
                elif otype == 'image':
                    # If object has image_ref (PhotoImage), try to get its PIL image via _PhotoImage__photo (not portable)
                    # Fallback: skip if we can't access image bytes
                    if getattr(obj, 'image_ref', None) is not None:
                        try:
                            pil = obj.image_ref._PhotoImage__photo.convert('RGB')
                            img.paste(pil, (int(obj.points[0][0]), int(obj.points[0][1])))
                        except Exception:
                            # Can't extract, skip
                            pass
                elif otype == 'fill':
                    # If previous fills are stored as images, draw them
                    if getattr(obj, 'image_ref', None) is not None:
                        try:
                            pil = obj.image_ref._PhotoImage__photo.convert('RGB')
                            img.paste(pil, (0, 0))
                        except Exception:
                            pass
            except Exception:
                # Ignore rendering errors for individual objects
                continue

        return img

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
        fill_color = self.current_fill_color or self.current_color
        fill_obj = DrawingObject(
            obj_type="fill",
            points=[(x, y)],
            outline_color=fill_color,
            fill_color=fill_color
        )

        r = 50  # Radius fill area
        fill_id = self.canvas.create_oval(
            x - r, y - r, x + r, y + r,
            fill=fill_color,
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
            outline="#2196F3", width=2, dash=(6, 3),
            tags=("selection_box",)
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
            # Determine corner index for tagging
            idx = corners.index((cx, cy))
            h_id = self.canvas.create_rectangle(
                cx - handle_size, cy - handle_size,
                cx + handle_size, cy + handle_size,
                fill="#2196F3", outline="#1565C0",
                tags=("selection_handle", f"corner_{idx}")
            )
            self.selection_box_ids.append(h_id)

        # Gambar rotation handle (circle) slightly above the top-right corner
        rx = bbox[2] + margin + 12
        ry = bbox[1] - margin - 12
        rsize = 6
        rot_id = self.canvas.create_oval(
            rx - rsize, ry - rsize, rx + rsize, ry + rsize,
            fill="#FFB74D", outline="#F57C00",
            tags=("rotation_handle", "selection_handle")
        )
        # Optional: draw a small rotate icon (text) on top for affordance
        txt_id = self.canvas.create_text(rx, ry, text="⤾", fill="#4E342E", font=("Segoe UI", 8), tags=("rotation_handle",))
        self.selection_box_ids.append(rot_id)
        self.selection_box_ids.append(txt_id)

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
        elif obj.obj_type == "trapezium":
            self._render_trapezium(obj, dash)
        elif obj.obj_type == "ellipse":
            self._render_ellipse(obj, dash)
        elif obj.obj_type == "bezier":
            self._render_bezier(obj, dash)
        elif obj.obj_type == "text":
            self._render_text(obj)
        elif obj.obj_type == "image":
            self._render_image(obj)
        elif obj.obj_type == "fill":
            pass  # Fill sudah di-render saat dibuat
        elif obj.obj_type == "freehand":
            self._render_freehand(obj, dash)

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
        algo = obj.algorithm or getattr(self, 'current_line_algorithm', 'Bresenham')
        if algo == "DDA":
            pixels = dda_line(x1, y1, x2, y2)
        else:
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

    def _render_trapezium(self, obj, dash):
        """Render trapesium."""
        if len(obj.points) < 4:
            return
        coords = []
        for p in obj.points[:4]:
            coords.extend([p[0], p[1]])
        cid = self.canvas.create_polygon(
            coords,
            outline=obj.outline_color,
            fill=obj.fill_color if obj.fill_color else '',
            width=obj.line_width,
            dash=dash
        )
        obj.canvas_ids.append(cid)

    def _render_ellipse(self, obj, dash):
        """Render elips."""
        if len(obj.points) < 2:
            return
        x1, y1 = obj.points[0]
        x2, y2 = obj.points[1]
        cid = self.canvas.create_oval(
            x1, y1, x2, y2,
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
        algo = (obj.algorithm or self.current_curve_algorithm or "Bezier").lower()
        if "spline" in algo:
            curve_pts = bspline_curve(obj.points, num_segments=200)
        else:
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
        for p in obj.points:
            dot_id = self.canvas.create_oval(
                p[0]-3, p[1]-3, p[0]+3, p[1]+3,
                fill="#FF4444", outline=""
            )
            obj.canvas_ids.append(dot_id)

    def _render_freehand(self, obj, dash):
        """Render garis freehand (Pencil/Eraser)."""
        if len(obj.points) < 2:
            return
            
        coords = []
        for p in obj.points:
            coords.extend([p[0], p[1]])
            
        cid = self.canvas.create_line(
            coords,
            fill=obj.outline_color,
            width=obj.line_width,
            dash=dash,
            smooth=True,
            capstyle=tk.ROUND,
            joinstyle=tk.ROUND
        )
        obj.canvas_ids.append(cid)

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
        if not obj.points:
            return

        x1, y1 = obj.points[0]
        # Determine target size from second point if present
        if len(obj.points) > 1:
            x2, y2 = obj.points[1]
            w = max(1, int(round(x2 - x1)))
            h = max(1, int(round(y2 - y1)))
        else:
            if getattr(obj, 'image_ref', None):
                try:
                    w = obj.image_ref.width()
                    h = obj.image_ref.height()
                except Exception:
                    return
            else:
                return

        # If PIL source exists, resize it to target size and create a PhotoImage
        if HAS_PIL and getattr(obj, 'pil_image', None) is not None:
            try:
                pil_src = obj.pil_image
                recreate = True
                if getattr(obj, 'image_ref', None):
                    try:
                        if obj.image_ref.width() == w and obj.image_ref.height() == h:
                            recreate = False
                    except Exception:
                        recreate = True

                if recreate:
                    resized = pil_src.resize((w, h), Image.LANCZOS)
                    obj.image_ref = ImageTk.PhotoImage(resized)
            except Exception:
                # fallback to existing image_ref
                pass

        # Draw the image at top-left
        cid = self.canvas.create_image(x1, y1, anchor=tk.NW, image=getattr(obj, 'image_ref', None))
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
        
        elif transform_type == "reflect":
            axis = kwargs.get('axis', 'x')
            center = obj.get_center()
            obj.points = reflect(obj.points, axis, center)

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
            
            w = tk_img.width()
            h = tk_img.height()
            
            x1, y1 = cx - w // 2, cy - h // 2
            x2, y2 = x1 + w, y1 + h

            obj = DrawingObject(
                obj_type="image",
                points=[(x1, y1), (x2, y2)],
                image_path=filepath
            )
            obj.image_ref = tk_img  # Simpan referensi agar tidak di-GC
            # Jika tersedia Pillow, simpan juga sumber PIL agar bisa di-resize/rotate
            if HAS_PIL:
                try:
                    obj.pil_image = pil_img.copy()
                except Exception:
                    obj.pil_image = None
            else:
                obj.pil_image = None

            cid = self.canvas.create_image(x1, y1, anchor=tk.NW, image=tk_img)
            obj.canvas_ids = [cid]

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
