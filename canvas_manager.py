import tkinter as tk
from tkinter import simpledialog, filedialog, messagebox
import math
import copy

from object_model import DrawingObject, reset_id_counter
from drawing_algorithms import (
    dda_line, bresenham_line, bezier_curve, bspline_curve, flood_fill, boundary_fill, hex_to_rgb
)
from transform import translate, rotate, scale, reflect

try:
    from PIL import Image, ImageTk, ImageGrab, ImageDraw
    HAS_PIL = True
except ImportError:
    HAS_PIL = False


class CanvasManager:
    def __init__(self, canvas, root, status_callback=None):
        self.canvas = canvas
        self.root = root
        self.status_callback = status_callback

        self.objects = []

        self.undo_stack = []
        self.max_undo = 50

        self.current_tool = "line"

        self.current_color = "#000000"
        self.current_fill_color = None
        self.current_line_width = 2
        self.current_line_style = "solid"
        self.current_line_algorithm = "Bresenham"
        self.current_curve_algorithm = "Bezier"
        self.current_fill_algorithm = "Flood Fill"

        self.is_drawing = False
        self.start_x = 0
        self.start_y = 0
        self.preview_ids = []

        self.selected_object = None
        self.selected_objects = []
        self.selection_box_ids = []
        self.marquee_start = None
        self.marquee_rect_id = None
        self.marquee_min_size = 5
        self._suppress_selection_refresh = False

        self.selection_mode = None
        self.selection_drag_start = (0, 0)
        self.selection_orig_points = None
        self.selection_orig_points_by_id = None
        self.selection_orig_rotation = 0.0
        self.selection_center = None
        self.selection_control_index = None

        self.bezier_points = []
        self.bezier_preview_ids = []

        self.freehand_points = []
        self.freehand_preview_ids = []

        self.canvas.bind("<ButtonPress-1>", self.on_mouse_down)
        self.canvas.bind("<B1-Motion>", self.on_mouse_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_mouse_up)
        self.canvas.bind("<ButtonPress-2>", self.on_marquee_down)
        self.canvas.bind("<B2-Motion>", self.on_marquee_drag)
        self.canvas.bind("<ButtonRelease-2>", self.on_marquee_up)
        self.canvas.bind("<ButtonPress-3>", self.on_marquee_down)
        self.canvas.bind("<B3-Motion>", self.on_marquee_drag)
        self.canvas.bind("<ButtonRelease-3>", self.on_marquee_up)
        self.canvas.bind("<Motion>", self.on_mouse_move)

    # ============================================================
    # MOUSE EVENT HANDLERS
    # ============================================================

    def on_mouse_move(self, event):
        x, y = event.x, event.y
        if self.current_tool == 'select':
            if (self.selected_object and
                self.selected_object.obj_type == 'bezier' and
                self._find_control_point_at(self.selected_object, x, y) is not None):
                try:
                    self.canvas.config(cursor='hand2')
                except Exception:
                    pass
                if self.status_callback:
                    self.status_callback(
                        f"Tool: Select | Objects: {len(self.objects)} | "
                        f"Edit curve point: ({x}, {y})"
                    )
                return

            items = self.canvas.find_overlapping(x, y, x, y)
            cursor = None
            for cid in items:
                tags = self.canvas.gettags(cid)
                if 'rotation_handle' in tags:
                    cursor = 'exchange'
                    break
                if any(t.startswith('corner_') for t in tags):
                    cursor = 'size_nw_se'
                    break
                if 'selection_handle' in tags or 'selection_box' in tags:
                    cursor = 'fleur'
                    break
            if cursor:
                try:
                    self.canvas.config(cursor=cursor)
                except Exception:
                    pass
            else:
                try:
                    self.canvas.config(cursor='arrow')
                except Exception:
                    pass
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
        x, y = event.x, event.y

        if self.current_tool == "select":
            clicked = False

            control_idx = None
            if self.selected_object and self.selected_object.obj_type == 'bezier':
                control_idx = self._find_control_point_at(self.selected_object, x, y)
            if control_idx is not None:
                self.selection_mode = 'edit_curve_point'
                self.selection_control_index = control_idx
                self.selection_orig_points = [p for p in self.selected_object.points]
                self._push_undo()
                return

            items = self.canvas.find_overlapping(x, y, x, y)
            for cid in items:
                tags = self.canvas.gettags(cid)
                if 'rotation_handle' in tags and self.selected_object:
                    self.selection_mode = 'rotate'
                    self.selection_center = self.selected_object.get_center()
                    cx, cy = self.selection_center
                    self.selection_rotate_start_angle = math.degrees(math.atan2(y - cy, x - cx))
                    self.selection_orig_points = [p for p in self.selected_object.points]
                    self.selection_orig_rotation = getattr(self.selected_object, 'rotation', 0.0)
                    self._push_undo()
                    clicked = True
                    break
                if any(t.startswith('corner_') for t in tags) and self.selected_object:
                    corner_tag = [t for t in tags if t.startswith('corner_')][0]
                    corner_idx = int(corner_tag.split('_')[1])
                    self.selection_mode = 'scale'
                    self.selection_scale_corner = corner_idx
                    self.selection_orig_points = [p for p in self.selected_object.points]
                    self.selection_scale_origin = self.selected_object.get_center()
                    self.selection_orig_scale = getattr(self.selected_object, 'scale_factor', 1.0)
                    self.selection_drag_start = (x, y)
                    self._push_undo()
                    clicked = True
                    break
                if ('selection_box' in tags or 'selection_handle' in tags) and self.selected_object:
                    self.selection_mode = 'translate'
                    self.selection_drag_start = (x, y)
                    self.selection_orig_points = [p for p in self.selected_object.points]
                    self.selection_orig_points_by_id = {
                        obj.id: [p for p in obj.points]
                        for obj in (self.selected_objects or [self.selected_object])
                    }
                    self._push_undo()
                    clicked = True
                    break

            if not clicked and self.selected_object:
                bbox = self.selected_object.get_bbox()
                margin = 8
                if (bbox[0] - margin <= x <= bbox[2] + margin and
                    bbox[1] - margin <= y <= bbox[3] + margin):
                    self.selection_mode = 'translate'
                    self.selection_drag_start = (x, y)
                    self.selection_orig_points = [p for p in self.selected_object.points]
                    self.selection_orig_points_by_id = {
                        obj.id: [p for p in obj.points]
                        for obj in (self.selected_objects or [self.selected_object])
                    }
                    self._push_undo()
                    clicked = True

            if clicked:
                return

            self._handle_select(x, y)
            if self.selected_object is None:
                self.selection_mode = 'marquee'
                self.on_marquee_down(event)
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
            self.is_drawing = True
            self.start_x = x
            self.start_y = y

    def on_mouse_drag(self, event):
        if self.current_tool == 'select' and self.selection_mode == 'marquee':
            self.on_marquee_drag(event)
            return

        if self.current_tool == 'select' and self.selection_mode and self.selected_object:
            x, y = event.x, event.y
            obj = self.selected_object
            if self.selection_mode == 'edit_curve_point':
                idx = self.selection_control_index
                if idx is not None and 0 <= idx < len(obj.points):
                    obj.points[idx] = (x, y)
                    self.render_object(obj)
                return
            elif self.selection_mode == 'translate':
                sx, sy = self.selection_drag_start
                dx = x - sx
                dy = y - sy
                if self.selection_orig_points_by_id and len(self.selected_objects) > 1:
                    for selected in self.selected_objects:
                        orig_points = self.selection_orig_points_by_id.get(selected.id)
                        if orig_points is not None:
                            selected.points = translate(orig_points, dx, dy)
                    self.render_all()
                else:
                    obj.points = translate(self.selection_orig_points, dx, dy)
                    self.render_object(obj)
                return
            elif self.selection_mode == 'rotate':
                cx, cy = self.selection_center
                start_angle = self.selection_rotate_start_angle
                curr_angle = math.degrees(math.atan2(y - cy, x - cx))
                delta = curr_angle - start_angle
                obj.points = rotate(self.selection_orig_points, delta, (cx, cy))
                obj.rotation = self.selection_orig_rotation + delta
                self.render_object(obj)
                return
            elif self.selection_mode == 'scale':
                orig_pts = self.selection_orig_points
                xs = [p[0] for p in orig_pts]
                ys = [p[1] for p in orig_pts]
                x_min, x_max = min(xs), max(xs)
                y_min, y_max = min(ys), max(ys)

                corner_idx = getattr(self, 'selection_scale_corner', 3)
                opp = {0:3, 1:2, 2:1, 3:0}[corner_idx]
                corners = [(x_min, y_min), (x_max, y_min), (x_min, y_max), (x_max, y_max)]
                ox, oy = corners[opp]

                sx0, sy0 = corners[corner_idx]
                nx, ny = x, y

                orig_dx = sx0 - ox
                orig_dy = sy0 - oy
                new_dx = nx - ox
                new_dy = ny - oy

                sx_fact = (new_dx / orig_dx) if orig_dx != 0 else (new_dx / (abs(orig_dx) + 1e-6))
                sy_fact = (new_dy / orig_dy) if orig_dy != 0 else (new_dy / (abs(orig_dy) + 1e-6))
                scale_factor = (abs(sx_fact) + abs(sy_fact)) / 2.0
                if (sx_fact < 0) ^ (sy_fact < 0):
                    pass

                obj.points = scale(self.selection_orig_points, scale_factor, (ox, oy))
                obj.scale_factor = getattr(self, 'selection_orig_scale', 1.0) * scale_factor
                self.render_object(obj)
                return

        if not self.is_drawing:
            return

        x, y = event.x, event.y

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
            mid_x = (self.start_x + x) / 2
            points = [
                mid_x, self.start_y,
                self.start_x, y,
                x, y
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
        if self.selection_mode == 'marquee':
            self.selection_mode = None
            self.on_marquee_up(event)
            return

        if self.selection_mode is not None:
            self.selection_mode = None
            self.selection_drag_start = (0, 0)
            self.selection_orig_points = None
            self.selection_orig_points_by_id = None
            self.selection_center = None
            self.selection_control_index = None
            return

        if not self.is_drawing:
            return

        self.is_drawing = False
        x, y = event.x, event.y

        for pid in self.preview_ids:
            self.canvas.delete(pid)
        self.preview_ids = []

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
            for pid in self.freehand_preview_ids:
                self.canvas.delete(pid)
            self.freehand_preview_ids = []
            self.freehand_points = []
            self.render_object(obj)

    def on_marquee_down(self, event):
        self.marquee_start = (event.x, event.y)
        self._delete_marquee_rect()
        self.marquee_rect_id = self.canvas.create_rectangle(
            event.x, event.y, event.x, event.y,
            outline="#1D4ED8",
            width=1,
            dash=(5, 3),
            fill="#60A5FA",
            stipple="gray12",
            tags=("marquee_select",)
        )

    def on_marquee_drag(self, event):
        if self.marquee_start is None or self.marquee_rect_id is None:
            return

        x0, y0 = self.marquee_start
        self.canvas.coords(self.marquee_rect_id, x0, y0, event.x, event.y)

        if self.status_callback:
            x1, y1, x2, y2 = self._normalized_bbox(x0, y0, event.x, event.y)
            self.status_callback(
                f"Box Select | Area: {int(x2 - x1)} x {int(y2 - y1)} | "
                f"Objects: {len(self.objects)}"
            )

    def on_marquee_up(self, event):
        if self.marquee_start is None:
            return

        x0, y0 = self.marquee_start
        x1, y1, x2, y2 = self._normalized_bbox(x0, y0, event.x, event.y)
        self._delete_marquee_rect()
        self.marquee_start = None

        if (x2 - x1) < self.marquee_min_size and (y2 - y1) < self.marquee_min_size:
            self._handle_select(event.x, event.y)
            return

        self._handle_area_select((x1, y1, x2, y2))

    # ============================================================
    # PEMBUATAN OBJEK
    # ============================================================

    def _create_line_object(self, x1, y1, x2, y2):
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
        obj = DrawingObject(
            obj_type="rectangle",
            points=[(x1, y1), (x2, y2)],
            outline_color=self.current_color,
            fill_color=None,
            line_width=self.current_line_width,
            line_style=self.current_line_style
        )
        self.objects.append(obj)
        self.render_object(obj)

    def _create_circle_object(self, cx, cy, ex, ey):
        dx = ex - cx
        dy = ey - cy
        r = math.sqrt(dx * dx + dy * dy)
        obj = DrawingObject(
            obj_type="circle",
            points=[(cx, cy), (cx + r, cy)],
            outline_color=self.current_color,
            fill_color=None,
            line_width=self.current_line_width,
            line_style=self.current_line_style
        )
        self.objects.append(obj)
        self.render_object(obj)

    def _create_triangle_object(self, x1, y1, x2, y2):
        mid_x = (x1 + x2) / 2
        obj = DrawingObject(
            obj_type="triangle",
            points=[(mid_x, y1), (x1, y2), (x2, y2)],
            outline_color=self.current_color,
            fill_color=None,
            line_width=self.current_line_width,
            line_style=self.current_line_style
        )
        self.objects.append(obj)
        self.render_object(obj)

    def _create_trapezium_object(self, x1, y1, x2, y2):
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
            fill_color=None,
            line_width=self.current_line_width,
            line_style=self.current_line_style
        )
        self.objects.append(obj)
        self.render_object(obj)

    def _create_ellipse_object(self, x1, y1, x2, y2):
        obj = DrawingObject(
            obj_type="ellipse",
            points=[(x1, y1), (x2, y2)],
            outline_color=self.current_color,
            fill_color=None,
            line_width=self.current_line_width,
            line_style=self.current_line_style
        )
        self.objects.append(obj)
        self.render_object(obj)

    # ============================================================
    # BEZIER CURVE
    # ============================================================

    def _handle_bezier_click(self, x, y):
        self.bezier_points.append((x, y))

        r = 4
        dot_id = self.canvas.create_oval(
            x - r, y - r, x + r, y + r,
            fill="#FF4444", outline="#CC0000", width=1
        )
        self.bezier_preview_ids.append(dot_id)

        if len(self.bezier_points) > 1:
            prev = self.bezier_points[-2]
            line_id = self.canvas.create_line(
                prev[0], prev[1], x, y,
                fill="#AAAAAA", dash=(4, 4), width=1
            )
            self.bezier_preview_ids.append(line_id)

        if len(self.bezier_points) >= 4:
            self._push_undo()

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
        fill_color = self.current_fill_color or self.current_color

        target = self._find_fill_target(x, y)
        if target is not None:
            if target.fill_color == fill_color:
                return
            self._push_undo()
            target.fill_color = fill_color
            self.render_object(target)
            return

        self._push_undo()

        canvas_width = self.canvas.winfo_width()
        canvas_height = self.canvas.winfo_height()

        if HAS_PIL:
            self._flood_fill_pil(x, y, canvas_width, canvas_height)
        else:
            self._flood_fill_simple(x, y)

    def _find_fill_target(self, x, y):
        for obj in reversed(self.objects):
            if obj.obj_type == "fill":
                continue
            if self._point_in_fillable_object(obj, x, y):
                return obj
        return None

    def _point_in_fillable_object(self, obj, x, y):
        if obj.obj_type == "rectangle":
            return self._point_in_bbox(x, y, obj.get_bbox())
        if obj.obj_type == "circle":
            return self._point_in_circle(x, y, obj.points)
        if obj.obj_type == "ellipse":
            return self._point_in_ellipse(x, y, obj.points)
        if obj.obj_type in ("triangle", "trapezium"):
            return self._point_in_polygon(x, y, obj.points)
        if obj.obj_type == "freehand" and self._is_closed_path(obj.points):
            return self._point_in_polygon(x, y, obj.points)
        return False

    def _find_control_point_at(self, obj, x, y, radius=10):
        if obj is None or obj.obj_type != "bezier":
            return None

        radius_sq = radius * radius
        for idx, (px, py) in enumerate(obj.points):
            if (x - px) ** 2 + (y - py) ** 2 <= radius_sq:
                return idx
        return None

    def _point_in_bbox(self, x, y, bbox):
        x1, y1, x2, y2 = bbox
        return x1 <= x <= x2 and y1 <= y <= y2

    def _point_in_circle(self, x, y, points):
        if len(points) < 2:
            return False
        cx, cy = points[0]
        rx, ry = points[1]
        r = math.sqrt((rx - cx) ** 2 + (ry - cy) ** 2)
        return (x - cx) ** 2 + (y - cy) ** 2 <= r ** 2

    def _point_in_ellipse(self, x, y, points):
        if len(points) < 2:
            return False
        x1, y1 = points[0]
        x2, y2 = points[1]
        cx = (x1 + x2) / 2
        cy = (y1 + y2) / 2
        rx = abs(x2 - x1) / 2
        ry = abs(y2 - y1) / 2
        if rx == 0 or ry == 0:
            return False
        nx = (x - cx) / rx
        ny = (y - cy) / ry
        return (nx * nx + ny * ny) <= 1.0

    def _point_in_polygon(self, x, y, points):
        if len(points) < 3:
            return False
        inside = False
        j = len(points) - 1
        for i in range(len(points)):
            xi, yi = points[i]
            xj, yj = points[j]
            intersects = ((yi > y) != (yj > y)) and (
                x < (xj - xi) * (y - yi) / ((yj - yi) if (yj - yi) != 0 else 1e-6) + xi
            )
            if intersects:
                inside = not inside
            j = i
        return inside

    def _is_closed_path(self, points, tolerance=12):
        if len(points) < 3:
            return False
        sx, sy = points[0]
        ex, ey = points[-1]
        return (sx - ex) ** 2 + (sy - ey) ** 2 <= tolerance ** 2

    def _point_in_fill_object(self, x, y, obj):
        if len(obj.points) < 2:
            return self._point_in_bbox(x, y, obj.get_bbox())

        x1, y1 = obj.points[0]
        x2, y2 = obj.points[1]
        left, right = sorted((x1, x2))
        top, bottom = sorted((y1, y2))

        if not (left <= x <= right and top <= y <= bottom):
            return False

        pil_img = getattr(obj, 'pil_image', None)
        if pil_img is None:
            return True

        width = max(1, right - left)
        height = max(1, bottom - top)
        local_x = int((x - left) * pil_img.width / width)
        local_y = int((y - top) * pil_img.height / height)
        local_x = max(0, min(pil_img.width - 1, local_x))
        local_y = max(0, min(pil_img.height - 1, local_y))

        try:
            return pil_img.convert('RGBA').getpixel((local_x, local_y))[3] > 0
        except Exception:
            return True

    def _flood_fill_pil(self, x, y, width, height):
        try:
            img = self._render_canvas_to_pil(width, height)

            if x < 0 or x >= img.width or y < 0 or y >= img.height:
                return

            target_color = img.getpixel((x, y))
            fill_color = self.current_fill_color or self.current_color
            fill_rgb = hex_to_rgb(fill_color)

            if target_color == fill_rgb:
                return

            pixels = img.load()
            tolerance = 30
            stack = [(x, y)]
            visited = set()
            filled_pixels = []
            algo = getattr(self, 'current_fill_algorithm', 'Flood Fill')
            is_boundary = ("boundary" in algo.lower())
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
                    is_boundary_color = (
                        abs(current[0] - boundary_color[0]) <= tolerance and
                        abs(current[1] - boundary_color[1]) <= tolerance and
                        abs(current[2] - boundary_color[2]) <= tolerance
                    )
                    is_fill_color = (
                        abs(current[0] - fill_rgb[0]) <= tolerance and
                        abs(current[1] - fill_rgb[1]) <= tolerance and
                        abs(current[2] - fill_rgb[2]) <= tolerance
                    )
                    should_fill = not is_boundary_color and not is_fill_color
                else:
                    should_fill = (
                        abs(current[0] - target_color[0]) <= tolerance and
                        abs(current[1] - target_color[1]) <= tolerance and
                        abs(current[2] - target_color[2]) <= tolerance
                    )

                if should_fill:
                    pixels[px, py] = fill_rgb
                    filled_pixels.append((px, py))
                    stack.append((px + 1, py))
                    stack.append((px - 1, py))
                    stack.append((px, py + 1))
                    stack.append((px, py - 1))

            if not filled_pixels:
                return

            min_x = min(px for px, _ in filled_pixels)
            min_y = min(py for _, py in filled_pixels)
            max_x = max(px for px, _ in filled_pixels)
            max_y = max(py for _, py in filled_pixels)
            layer = Image.new('RGBA', (max_x - min_x + 1, max_y - min_y + 1), (0, 0, 0, 0))
            layer_pixels = layer.load()
            for px, py in filled_pixels:
                layer_pixels[px - min_x, py - min_y] = (*fill_rgb, 255)

            tk_img = ImageTk.PhotoImage(layer)
            fill_obj = DrawingObject(
                obj_type="fill",
                points=[(min_x, min_y), (max_x + 1, max_y + 1)],
                outline_color=fill_color,
                fill_color=fill_color
            )
            fill_obj.image_ref = tk_img
            fill_obj.pil_image = layer
            self.objects.append(fill_obj)
            self.render_all()

        except Exception as e:
            messagebox.showwarning("Fill Error",
                f"Flood fill gagal: {str(e)}\nPastikan Pillow terinstall dan akses screenshot diizinkan.")
            self._flood_fill_simple(x, y)

    def _render_canvas_to_pil(self, width, height):
        img = Image.new('RGB', (max(1, width), max(1, height)), (255, 255, 255))
        draw = ImageDraw.Draw(img)

        ordered_objects = (
            [obj for obj in self.objects if obj.obj_type == 'fill'] +
            [obj for obj in self.objects if obj.obj_type != 'fill']
        )

        for obj in ordered_objects:
            try:
                otype = obj.obj_type
                if otype == 'line':
                    p0, p1 = obj.points[0], obj.points[1]
                    draw.line([p0, p1], fill=obj.outline_color, width=max(1, int(obj.line_width)))
                elif otype == 'circle':
                    cx, cy = obj.points[0]
                    rx, ry = obj.points[1]
                    r = math.sqrt((rx - cx) ** 2 + (ry - cy) ** 2)
                    box = [cx - r, cy - r, cx + r, cy + r]
                    if obj.fill_color:
                        draw.ellipse(box, fill=obj.fill_color, outline=obj.outline_color, width=max(1, int(obj.line_width)))
                    else:
                        draw.ellipse(box, outline=obj.outline_color, width=max(1, int(obj.line_width)))
                elif otype in ('rectangle', 'ellipse'):
                    (x1, y1), (x2, y2) = obj.points[0], obj.points[1]
                    left, right = sorted((x1, x2))
                    top, bottom = sorted((y1, y2))
                    box = [left, top, right, bottom]
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
                elif otype in ('triangle', 'trapezium'):
                    pts = [tuple(p) for p in obj.points]
                    if obj.fill_color:
                        draw.polygon(pts, fill=obj.fill_color, outline=obj.outline_color)
                    else:
                        draw.line(pts + [pts[0]], fill=obj.outline_color, width=max(1, int(obj.line_width)))
                elif otype == 'bezier':
                    if len(obj.points) >= 2:
                        algo = (obj.algorithm or self.current_curve_algorithm or "Bezier").lower()
                        if "spline" in algo:
                            pts = bspline_curve(obj.points, num_segments=200)
                        else:
                            pts = bezier_curve(obj.points, num_segments=200)
                        if len(pts) >= 2:
                            draw.line(pts, fill=obj.outline_color, width=max(1, int(obj.line_width)))
                elif otype == 'freehand':
                    pts = [tuple(p) for p in obj.points]
                    if len(pts) >= 2:
                        w = max(1, int(obj.line_width) + 1)
                        if obj.fill_color and self._is_closed_path(pts):
                            draw.polygon(pts, fill=obj.fill_color)
                        draw.line(pts, fill=obj.outline_color, width=w)
                        r = max(1, int(w / 2))
                        for px, py in pts:
                            draw.ellipse([px - r, py - r, px + r, py + r], fill=obj.outline_color, outline=obj.outline_color)
                        sx, sy = pts[0]
                        ex, ey = pts[-1]
                        if (sx - ex) ** 2 + (sy - ey) ** 2 <= 36:
                            draw.line([(sx, sy), (ex, ey)], fill=obj.outline_color, width=w)
                elif otype == 'text':
                    xy = obj.points[0]
                    draw.text((xy[0], xy[1]), str(obj.text_content or ''), fill=obj.outline_color)
                elif otype == 'image':
                    pil = getattr(obj, 'pil_image', None)
                    if pil is not None and obj.points:
                        self._paste_pil_layer(img, pil, obj.points)
                elif otype == 'fill':
                    pil = getattr(obj, 'pil_image', None)
                    if pil is not None:
                        self._paste_pil_layer(img, pil, obj.points)
            except Exception:
                continue

        return img

    def _paste_pil_layer(self, base_img, layer_img, points):
        if not points:
            return

        x1, y1 = points[0]
        if len(points) > 1:
            x2, y2 = points[1]
            left, right = sorted((x1, x2))
            top, bottom = sorted((y1, y2))
            target_w = max(1, int(round(right - left)))
            target_h = max(1, int(round(bottom - top)))
            paste_x, paste_y = left, top
        else:
            target_w, target_h = layer_img.size
            paste_x, paste_y = x1, y1

        layer = layer_img.convert('RGBA')
        if layer.size != (target_w, target_h):
            layer = layer.resize((target_w, target_h), Image.LANCZOS)

        base_img.paste(layer.convert('RGB'), (int(round(paste_x)), int(round(paste_y))), layer)

    def _flood_fill_simple(self, x, y):
        canvas_width = self.canvas.winfo_width()
        canvas_height = self.canvas.winfo_height()

        fill_color = self.current_fill_color or self.current_color
        r = 50
        fill_obj = DrawingObject(
            obj_type="fill",
            points=[(x - r, y - r), (x + r, y + r)],
            outline_color=fill_color,
            fill_color=fill_color
        )

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
        self._clear_selection()

        for obj in reversed(self.objects):
            if obj.obj_type == "fill":
                if self._point_in_fill_object(x, y, obj):
                    merged_target = self._merge_fill_into_target(obj, x, y)
                    if merged_target is not None:
                        self._set_selected_objects([merged_target])
                        self.render_all()
                        return
                continue

            bbox = obj.get_bbox()
            margin = max(10, obj.line_width + 5)

            is_inside_filled_area = obj.fill_color and self._point_in_fillable_object(obj, x, y)
            is_inside_bbox = (
                bbox[0] - margin <= x <= bbox[2] + margin and
                bbox[1] - margin <= y <= bbox[3] + margin
            )

            if is_inside_filled_area or is_inside_bbox:
                self._set_selected_objects([obj])
                return

        self._set_selected_objects([])

    def _handle_area_select(self, area_bbox):
        self._clear_selection()

        selected = []
        for obj in reversed(self.objects):
            if obj.obj_type == "fill":
                continue

            if self._bboxes_intersect(area_bbox, obj.get_bbox()):
                selected.append(obj)

        self._set_selected_objects(selected)
        if selected:
            if self.status_callback:
                self.status_callback(
                    f"Box Select | Selected: {len(selected)} object(s) | "
                    f"Objects: {len(self.objects)}"
                )
            return

        if self.status_callback:
            self.status_callback(
                f"Box Select | No object selected | Objects: {len(self.objects)}"
            )

    def _normalized_bbox(self, x1, y1, x2, y2):
        return (min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2))

    def _bboxes_intersect(self, a, b):
        ax1, ay1, ax2, ay2 = a
        bx1, by1, bx2, by2 = b
        return not (ax2 < bx1 or bx2 < ax1 or ay2 < by1 or by2 < ay1)

    def _delete_marquee_rect(self):
        if self.marquee_rect_id is not None:
            self.canvas.delete(self.marquee_rect_id)
            self.marquee_rect_id = None

    def _merge_fill_into_target(self, fill_obj, x, y):
        fill_color = fill_obj.fill_color or fill_obj.outline_color

        mergeable_types = {"rectangle", "circle", "ellipse", "triangle", "trapezium", "freehand"}

        for candidate in reversed(self.objects):
            if candidate.id == fill_obj.id or candidate.obj_type == "fill":
                continue
            if candidate.obj_type not in mergeable_types:
                continue

            if self._point_in_fillable_object(candidate, x, y):
                candidate.fill_color = fill_color
                for cid in fill_obj.canvas_ids:
                    self.canvas.delete(cid)
                self.objects = [obj for obj in self.objects if obj.id != fill_obj.id]
                return candidate

        return None

    def _set_selected_objects(self, objects):
        self.selected_objects = [obj for obj in objects if obj is not None]
        self.selected_object = self.selected_objects[0] if self.selected_objects else None
        self._draw_selection_boxes()

    def _draw_selection_boxes(self):
        self._clear_selection_box()
        selected = self.selected_objects
        if not selected and self.selected_object:
            selected = [self.selected_object]

        secondary = [obj for obj in selected if obj is not self.selected_object]
        ordered = secondary + ([self.selected_object] if self.selected_object else [])

        for obj in ordered:
            self._draw_selection_box(obj, clear_existing=False)

    def _draw_selection_box(self, obj, clear_existing=True):
        if clear_existing:
            self._clear_selection_box()
        bbox = obj.get_bbox()
        margin = 8

        is_primary = obj is self.selected_object
        outline_color = "#1D4ED8" if is_primary else "#60A5FA"
        fill_color = "#DBEAFE" if is_primary else "#BFDBFE"

        fill_id = self.canvas.create_rectangle(
            bbox[0] - margin, bbox[1] - margin,
            bbox[2] + margin, bbox[3] + margin,
            outline="",
            fill=fill_color,
            stipple="gray12",
            tags=("selection_box", "selection_fill")
        )
        self.selection_box_ids.append(fill_id)

        box_id = self.canvas.create_rectangle(
            bbox[0] - margin, bbox[1] - margin,
            bbox[2] + margin, bbox[3] + margin,
            outline=outline_color, width=2, dash=(6, 3),
            tags=("selection_box",)
        )
        self.selection_box_ids.append(box_id)

        if not is_primary:
            return

        handle_size = 5
        corners = [
            (bbox[0] - margin, bbox[1] - margin),
            (bbox[2] + margin, bbox[1] - margin),
            (bbox[0] - margin, bbox[3] + margin),
            (bbox[2] + margin, bbox[3] + margin),
        ]
        for cx, cy in corners:
            idx = corners.index((cx, cy))
            h_id = self.canvas.create_rectangle(
                cx - handle_size, cy - handle_size,
                cx + handle_size, cy + handle_size,
                fill="#2196F3", outline="#1565C0",
                tags=("selection_handle", f"corner_{idx}")
            )
            self.selection_box_ids.append(h_id)

        rx = bbox[2] + margin + 12
        ry = bbox[1] - margin - 12
        rsize = 6
        rot_id = self.canvas.create_oval(
            rx - rsize, ry - rsize, rx + rsize, ry + rsize,
            fill="#FFB74D", outline="#F57C00",
            tags=("rotation_handle", "selection_handle")
        )
        txt_id = self.canvas.create_text(rx, ry, text="⤾", fill="#4E342E", font=("Segoe UI", 8), tags=("rotation_handle",))
        self.selection_box_ids.append(rot_id)
        self.selection_box_ids.append(txt_id)

    def _clear_selection_box(self):
        for sid in self.selection_box_ids:
            self.canvas.delete(sid)
        self.selection_box_ids = []

    def _clear_selection(self):
        self._clear_selection_box()
        self.selected_object = None
        self.selected_objects = []

    # ============================================================
    # RENDERING OBJEK
    # ============================================================

    def render_object(self, obj):
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
            self._render_fill(obj)
        elif obj.obj_type == "freehand":
            self._render_freehand(obj, dash)

        if (not self._suppress_selection_refresh and
            self.selected_objects and
            any(selected.id == obj.id for selected in self.selected_objects)):
            self._draw_selection_boxes()

    def _render_line(self, obj, dash):
        if len(obj.points) < 2:
            return

        x1, y1 = obj.points[0]
        x2, y2 = obj.points[1]

        algo = obj.algorithm or getattr(self, 'current_line_algorithm', 'Bresenham')
        if algo == "DDA":
            pixels = dda_line(x1, y1, x2, y2)
        else:
            pixels = bresenham_line(x1, y1, x2, y2)

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

        if w <= 2 and len(pixels) < 500:
            pass

    def _render_rectangle(self, obj, dash):
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
        if len(obj.points) < 2:
            return

        algo = (obj.algorithm or self.current_curve_algorithm or "Bezier").lower()
        if "spline" in algo:
            curve_pts = bspline_curve(obj.points, num_segments=200)
        else:
            curve_pts = bezier_curve(obj.points, num_segments=200)

        if len(curve_pts) < 2:
            return

        coords = []
        for p in curve_pts:
            coords.extend([p[0], p[1]])

        cid = self.canvas.create_line(
            coords,
            fill=obj.outline_color,
            width=obj.line_width,
            dash=dash,
            smooth=False,
            capstyle=tk.ROUND,
            joinstyle=tk.ROUND
        )
        obj.canvas_ids.append(cid)

        for p in obj.points:
            dot_id = self.canvas.create_oval(
                p[0]-3, p[1]-3, p[0]+3, p[1]+3,
                fill="#FF4444", outline=""
            )
            obj.canvas_ids.append(dot_id)

    def _render_freehand(self, obj, dash):
        if len(obj.points) < 2:
            return
            
        coords = []
        for p in obj.points:
            coords.extend([p[0], p[1]])

        if obj.fill_color and self._is_closed_path(obj.points):
            fill_id = self.canvas.create_polygon(
                coords,
                fill=obj.fill_color,
                outline='',
                smooth=True
            )
            obj.canvas_ids.append(fill_id)
            
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

        bbox = self.canvas.bbox(cid)
        if bbox:
            obj.points = [(bbox[0], bbox[1]), (bbox[2], bbox[3])]

    def _render_image(self, obj):
        if not obj.points:
            return

        x1, y1 = obj.points[0]
        draw_x, draw_y = x1, y1
        if len(obj.points) > 1:
            x2, y2 = obj.points[1]
            left, right = sorted((x1, x2))
            top, bottom = sorted((y1, y2))
            draw_x, draw_y = left, top
            w = max(1, int(round(right - left)))
            h = max(1, int(round(bottom - top)))
        else:
            if getattr(obj, 'image_ref', None):
                try:
                    w = obj.image_ref.width()
                    h = obj.image_ref.height()
                except Exception:
                    return
            else:
                return

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
                pass

        cid = self.canvas.create_image(draw_x, draw_y, anchor=tk.NW, image=getattr(obj, 'image_ref', None))
        obj.canvas_ids.append(cid)

    def _render_fill(self, obj):
        if not obj.points:
            return

        pil_img = getattr(obj, 'pil_image', None)
        if pil_img is None:
            if len(obj.points) >= 2:
                x1, y1 = obj.points[0]
                x2, y2 = obj.points[1]
                cid = self.canvas.create_oval(
                    x1, y1, x2, y2,
                    fill=obj.fill_color or obj.outline_color,
                    outline=""
                )
                obj.canvas_ids.append(cid)
            return

        x1, y1 = obj.points[0]
        draw_x, draw_y = x1, y1
        layer = pil_img
        if len(obj.points) > 1:
            x2, y2 = obj.points[1]
            left, right = sorted((x1, x2))
            top, bottom = sorted((y1, y2))
            draw_x, draw_y = left, top
            w = max(1, int(round(right - left)))
            h = max(1, int(round(bottom - top)))
            if layer.size != (w, h):
                layer = layer.resize((w, h), Image.LANCZOS)

        obj.image_ref = ImageTk.PhotoImage(layer)
        cid = self.canvas.create_image(draw_x, draw_y, anchor=tk.NW, image=obj.image_ref)
        obj.canvas_ids.append(cid)

    # ============================================================
    # RENDER ALL
    # ============================================================

    def render_all(self):
        self.canvas.delete("all")
        for obj in self.objects:
            obj.canvas_ids = []

        self._suppress_selection_refresh = True
        try:
            for obj in self.objects:
                if obj.obj_type == "fill":
                    self.render_object(obj)

            for obj in self.objects:
                if obj.obj_type != "fill":
                    self.render_object(obj)
        finally:
            self._suppress_selection_refresh = False

        self.selected_objects = [
            obj for obj in self.selected_objects
            if any(existing.id == obj.id for existing in self.objects)
        ]
        self.selected_object = self.selected_objects[0] if self.selected_objects else None
        self._draw_selection_boxes()

    # ============================================================
    # TRANSFORMASI
    # ============================================================

    def transform_selected(self, transform_type, **kwargs):
        if self.selected_object is None:
            messagebox.showinfo("Info", "Pilih objek terlebih dahulu!")
            return

        self._push_undo()
        selected = self.selected_objects or [self.selected_object]

        for obj in selected:
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

        self.render_all()

    # ============================================================
    # UNDO
    # ============================================================

    def _push_undo(self):
        snapshot = [obj.clone() for obj in self.objects]
        self.undo_stack.append(snapshot)
        if len(self.undo_stack) > self.max_undo:
            self.undo_stack.pop(0)

    def undo(self):
        if not self.undo_stack:
            messagebox.showinfo("Info", "Tidak ada aksi untuk di-undo.")
            return

        self._clear_selection()

        snapshot = self.undo_stack.pop()
        self.canvas.delete("all")
        self.objects = snapshot

        self.render_all()

    # ============================================================
    # CLEAR CANVAS
    # ============================================================

    def clear_canvas(self):
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
                x = self.canvas.winfo_rootx()
                y = self.canvas.winfo_rooty()
                w = self.canvas.winfo_width()
                h = self.canvas.winfo_height()
                img = ImageGrab.grab(bbox=(x, y, x + w, y + h))
                img.save(filepath)
                messagebox.showinfo("Sukses", f"Canvas disimpan ke:\n{filepath}")
            except Exception as e:
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
                max_size = 400
                if pil_img.width > max_size or pil_img.height > max_size:
                    ratio = min(max_size / pil_img.width, max_size / pil_img.height)
                    new_size = (int(pil_img.width * ratio), int(pil_img.height * ratio))
                    pil_img = pil_img.resize(new_size, Image.LANCZOS)
                tk_img = ImageTk.PhotoImage(pil_img)
            else:
                tk_img = tk.PhotoImage(file=filepath)

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
            obj.image_ref = tk_img
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
        return self._get_dash_pattern_for(self.current_line_style)

    def _get_dash_pattern_for(self, style):
        if style == "dashed":
            return (10, 5)
        elif style == "dotted":
            return (2, 4)
        else:
            return ()

    def set_tool(self, tool):
        if self.current_tool == "bezier" and tool != "bezier":
            for pid in self.bezier_preview_ids:
                self.canvas.delete(pid)
            self.bezier_preview_ids = []
            self.bezier_points = []

        self.current_tool = tool

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
