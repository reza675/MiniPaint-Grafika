import copy
import math

_next_id = 1


def _generate_id():
    global _next_id
    obj_id = _next_id
    _next_id += 1
    return obj_id


def reset_id_counter():
    global _next_id
    _next_id = 1


class DrawingObject:
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
        self.image_ref = None
        self.pil_image = None
        self.canvas_ids = []

    def get_center(self):
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
        new_obj.canvas_ids = []
        return new_obj

    def __repr__(self):
        return (f"DrawingObject(id={self.id}, type='{self.obj_type}', "
                f"points={len(self.points)}, color='{self.outline_color}')")
