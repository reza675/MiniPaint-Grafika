import math


def translate(points, dx, dy):
    return [(x + dx, y + dy) for (x, y) in points]


def rotate(points, angle_degrees, center=None):
    if not points:
        return points
    
    if center is None:
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        center = ((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2)
    
    cx, cy = center
    
    theta = math.radians(angle_degrees)
    cos_t = math.cos(theta)
    sin_t = math.sin(theta)
    
    rotated = []
    for (x, y) in points:
        dx = x - cx
        dy = y - cy
        
        new_x = dx * cos_t - dy * sin_t
        new_y = dx * sin_t + dy * cos_t
        
        rotated.append((new_x + cx, new_y + cy))
    
    return rotated


def scale(points, factor, center=None):
    if not points:
        return points
    
    if center is None:
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        center = ((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2)
    
    cx, cy = center
    
    scaled = []
    for (x, y) in points:
        new_x = (x - cx) * factor + cx
        new_y = (y - cy) * factor + cy
        scaled.append((new_x, new_y))
    
    return scaled

def reflect(points, axis='x', center=None):
    if not points:
        return points
    
    if center is None:
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        center = ((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2)
    
    cx, cy = center
    reflected = []
    
    for (x, y) in points:
        if axis == 'x':
            new_x = cx - (x - cx)
            new_y = y
        elif axis == 'y':
            new_x = x
            new_y = cy - (y - cy)
        reflected.append((new_x, new_y))
        
    return reflected
