"""
object_model.py
Struktur data objek gambar untuk Mini Paint Application.
Setiap objek yang digambar pada canvas disimpan sebagai DrawingObject.
"""

import copy
import math

# Counter global untuk ID unik objek
_next_id = 1


def _generate_id():
    """Menghasilkan ID unik untuk setiap objek."""
    global _next_id
    obj_id = _next_id
    _next_id += 1
    return obj_id


def reset_id_counter():
    """Reset counter ID (dipakai saat clear canvas)."""
    global _next_id
    _next_id = 1


class DrawingObject:
    """
    Representasi satu objek gambar pada canvas.
    
    Tipe objek yang didukung:
      - line, rectangle, circle, triangle, bezier, fill, text, image
    
    Atribut:
      - id: ID unik objek
      - obj_type: tipe objek (string)
      - points: list of (x, y) tuples — koordinat utama objek
      - outline_color: warna garis (hex string)
      - fill_color: warna isi (hex string atau None)
      - line_width: ketebalan garis (int, pixel)
      - line_style: style garis ("solid", "dashed", "dotted")
      - rotation: sudut rotasi kumulatif (derajat)
      - scale_factor: faktor skala kumulatif
      - text_content: isi teks (untuk objek tipe text)
      - image_path: path file gambar (untuk objek tipe image)
      - image_ref: referensi PhotoImage (agar tidak di-garbage-collect)
      - pil_image: referensi PIL.Image untuk render ulang image/fill
      - canvas_ids: list ID item canvas Tkinter yang merepresentasikan objek ini
    """

    def __init__(self, obj_type, points=None, outline_color="#000000",
                 fill_color=None, line_width=2, line_style="solid",
                 text_content=None, image_path=None, algorithm=None):
        self.id = _generate_id()
        self.obj_type = obj_type
        self.points = points if points is not None else []
        self.outline_color = outline_color
        self.fill_color = fill_color
        self.line_width = line_width
        self.line_style = line_style
        self.algorithm = algorithm
        self.rotation = 0.0
        self.scale_factor = 1.0
        self.text_content = text_content
        self.image_path = image_path
        self.image_ref = None  # Simpan referensi PhotoImage
        self.pil_image = None
        self.canvas_ids = []

    def get_center(self):
        """Menghitung titik pusat dari bounding box objek."""
        if not self.points:
            return (0, 0)
        if self.obj_type == "circle" and len(self.points) >= 2:
            return self.points[0]
        xs = [p[0] for p in self.points]
        ys = [p[1] for p in self.points]
        cx = (min(xs) + max(xs)) / 2
        cy = (min(ys) + max(ys)) / 2
        return (cx, cy)

    def get_bbox(self):
        """Menghitung bounding box (x_min, y_min, x_max, y_max)."""
        if not self.points:
            return (0, 0, 0, 0)
        if self.obj_type == "circle" and len(self.points) >= 2:
            cx, cy = self.points[0]
            rx, ry = self.points[1]
            r = math.sqrt((rx - cx) ** 2 + (ry - cy) ** 2)
            return (cx - r, cy - r, cx + r, cy + r)
        xs = [p[0] for p in self.points]
        ys = [p[1] for p in self.points]
        return (min(xs), min(ys), max(xs), max(ys))

    def clone(self):
        """Membuat deep copy objek untuk undo stack."""
        new_obj = DrawingObject.__new__(DrawingObject)
        new_obj.id = self.id
        new_obj.obj_type = self.obj_type
        new_obj.points = copy.deepcopy(self.points)
        new_obj.outline_color = self.outline_color
        new_obj.fill_color = self.fill_color
        new_obj.line_width = self.line_width
        new_obj.line_style = self.line_style
        new_obj.algorithm = self.algorithm
        new_obj.rotation = self.rotation
        new_obj.scale_factor = self.scale_factor
        new_obj.text_content = self.text_content
        new_obj.image_path = self.image_path
        new_obj.image_ref = self.image_ref
        pil_image = getattr(self, 'pil_image', None)
        try:
            new_obj.pil_image = pil_image.copy() if pil_image is not None else None
        except Exception:
            new_obj.pil_image = pil_image
        new_obj.canvas_ids = []  # Canvas IDs tidak di-copy
        return new_obj

    def __repr__(self):
        return (f"DrawingObject(id={self.id}, type='{self.obj_type}', "
                f"points={len(self.points)}, color='{self.outline_color}')")
