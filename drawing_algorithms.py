import math

# ============================================================
# ALGORITMA GARIS DDA (Digital Differential Analyzer)
# ============================================================
def dda_line(x1, y1, x2, y2):
    points = []
    
    dx = x2 - x1
    dy = y2 - y1
    
    steps = max(abs(dx), abs(dy))
    
    if steps == 0:
        return [(round(x1), round(y1))]
    
    x_inc = dx / steps
    y_inc = dy / steps
    
    x = float(x1)
    y = float(y1)
    
    for i in range(int(steps) + 1):
        points.append((round(x), round(y)))
        x += x_inc
        y += y_inc
    
    return points


# ============================================================
# ALGORITMA GARIS BRESENHAM
# ============================================================

def bresenham_line(x1, y1, x2, y2):
    points = []
    
    x1, y1, x2, y2 = int(round(x1)), int(round(y1)), int(round(x2)), int(round(y2))
    
    dx = abs(x2 - x1)
    dy = abs(y2 - y1)
    
    sx = 1 if x1 < x2 else -1
    sy = 1 if y1 < y2 else -1
    
    err = dx - dy
    
    while True:
        points.append((x1, y1))
        
        if x1 == x2 and y1 == y2:
            break
        
        e2 = 2 * err
        
        if e2 > -dy:
            err -= dy
            x1 += sx
        
        if e2 < dx:
            err += dx
            y1 += sy
    
    return points


# ============================================================
# ALGORITMA KURVA BEZIER (KUBIK)
# ============================================================

def bezier_curve(control_points, num_segments=200):
    if len(control_points) < 2:
        return list(control_points)
    
    curve_points = []
    n = len(control_points) - 1
    
    for i in range(num_segments + 1):
        t = i / num_segments
        
        temp_points = list(control_points)
        
        for level in range(n):
            new_points = []
            for j in range(len(temp_points) - 1):
                x = (1 - t) * temp_points[j][0] + t * temp_points[j + 1][0]
                y = (1 - t) * temp_points[j][1] + t * temp_points[j + 1][1]
                new_points.append((x, y))
            temp_points = new_points
        
        curve_points.append(temp_points[0])
    
    return curve_points


def bezier_cubic(p0, p1, p2, p3, num_segments=200):
    return bezier_curve([p0, p1, p2, p3], num_segments)


# ============================================================
# ALGORITMA B-SPLINE KUBIK (UNIFORM)
# ============================================================

def bspline_curve(control_points, num_segments=200):
    if len(control_points) < 4:
        return list(control_points)

    def basis(t):
        t2 = t * t
        t3 = t2 * t
        b0 = (-t3 + 3 * t2 - 3 * t + 1) / 6
        b1 = (3 * t3 - 6 * t2 + 4) / 6
        b2 = (-3 * t3 + 3 * t2 + 3 * t + 1) / 6
        b3 = t3 / 6
        return b0, b1, b2, b3

    curve_points = []

    segments = len(control_points) - 3
    for s in range(segments):
        p0, p1, p2, p3 = control_points[s:s + 4]
        for i in range(num_segments + 1):
            t = i / num_segments
            b0, b1, b2, b3 = basis(t)
            x = b0 * p0[0] + b1 * p1[0] + b2 * p2[0] + b3 * p3[0]
            y = b0 * p0[1] + b1 * p1[1] + b2 * p2[1] + b3 * p3[1]
            curve_points.append((x, y))

    return curve_points


# ============================================================
# ALGORITMA FLOOD FILL (ITERATIF)
# ============================================================

def flood_fill(photo_image, start_x, start_y, fill_color_rgb, tolerance=30):
    width = photo_image.width()
    height = photo_image.height()
    
    if start_x < 0 or start_x >= width or start_y < 0 or start_y >= height:
        return photo_image
    
    target_color = photo_image.get(start_x, start_y)
    
    fill_r, fill_g, fill_b = fill_color_rgb
    if isinstance(target_color, tuple):
        tr, tg, tb = target_color
    else:
        parts = str(target_color).split()
        tr, tg, tb = int(parts[0]), int(parts[1]), int(parts[2])
    
    if (tr, tg, tb) == (fill_r, fill_g, fill_b):
        return photo_image
    
    def color_match(pixel_color):
        if isinstance(pixel_color, tuple):
            pr, pg, pb = pixel_color
        else:
            parts = str(pixel_color).split()
            pr, pg, pb = int(parts[0]), int(parts[1]), int(parts[2])
        
        return (abs(pr - tr) <= tolerance and
                abs(pg - tg) <= tolerance and
                abs(pb - tb) <= tolerance)
    
    fill_hex = f"#{fill_r:02x}{fill_g:02x}{fill_b:02x}"
    
    visited = set()
    stack = [(start_x, start_y)]
    pixels_to_fill = []
    
    while stack:
        x, y = stack.pop()
        
        if (x, y) in visited:
            continue
        if x < 0 or x >= width or y < 0 or y >= height:
            continue
        
        visited.add((x, y))
        
        pixel = photo_image.get(x, y)
        if not color_match(pixel):
            continue
        
        pixels_to_fill.append((x, y))
        
        stack.append((x + 1, y))
        stack.append((x - 1, y))
        stack.append((x, y + 1))
        stack.append((x, y - 1))
    
    rows = {}
    for (x, y) in pixels_to_fill:
        if y not in rows:
            rows[y] = []
        rows[y].append(x)
    
    for y, x_list in rows.items():
        for x in x_list:
            photo_image.put(fill_hex, (x, y))
    
    return photo_image


def boundary_fill(photo_image, start_x, start_y, fill_color_rgb, boundary_color_rgb, tolerance=30):
    width = photo_image.width()
    height = photo_image.height()

    if start_x < 0 or start_x >= width or start_y < 0 or start_y >= height:
        return photo_image

    fill_r, fill_g, fill_b = fill_color_rgb
    br, bg, bb = boundary_color_rgb

    def color_match(pixel_color, r, g, b):
        if isinstance(pixel_color, tuple):
            pr, pg, pb = pixel_color
        else:
            parts = str(pixel_color).split()
            pr, pg, pb = int(parts[0]), int(parts[1]), int(parts[2])
        return (abs(pr - r) <= tolerance and
                abs(pg - g) <= tolerance and
                abs(pb - b) <= tolerance)

    fill_hex = f"#{fill_r:02x}{fill_g:02x}{fill_b:02x}"
    visited = set()
    stack = [(start_x, start_y)]
    pixels_to_fill = []

    while stack:
        x, y = stack.pop()

        if (x, y) in visited:
            continue
        if x < 0 or x >= width or y < 0 or y >= height:
            continue

        visited.add((x, y))
        pixel = photo_image.get(x, y)

        if color_match(pixel, br, bg, bb) or color_match(pixel, fill_r, fill_g, fill_b):
            continue

        pixels_to_fill.append((x, y))

        stack.append((x + 1, y))
        stack.append((x - 1, y))
        stack.append((x, y + 1))
        stack.append((x, y - 1))

    for x, y in pixels_to_fill:
        photo_image.put(fill_hex, (x, y))

    return photo_image


def hex_to_rgb(hex_color):
    hex_color = hex_color.lstrip('#')
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))


def rgb_to_hex(r, g, b):
    return f"#{r:02x}{g:02x}{b:02x}"
