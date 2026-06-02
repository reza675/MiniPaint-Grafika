"""
transform.py
Fungsi-fungsi transformasi 2D untuk objek gambar:
  - Translasi (perpindahan posisi)
  - Rotasi (pemutaran terhadap pusat objek)
  - Scaling (pembesaran/pengecilan terhadap pusat objek)
"""

import math


def translate(points, dx, dy):
    """
    Translasi: menggeser semua titik objek sebesar (dx, dy).
    
    Rumus:
      x' = x + dx
      y' = y + dy
    
    Args:
        points: list of (x, y) — titik-titik objek
        dx: perpindahan horizontal (positif = kanan)
        dy: perpindahan vertikal (positif = bawah)
    
    Returns:
        list of (x', y'): titik-titik setelah translasi
    """
    return [(x + dx, y + dy) for (x, y) in points]


def rotate(points, angle_degrees, center=None):
    """
    Rotasi: memutar semua titik objek terhadap titik pusat.
    
    Rumus (rotasi terhadap origin):
      x' = x * cos(θ) - y * sin(θ)
      y' = x * sin(θ) + y * cos(θ)
    
    Untuk rotasi terhadap titik pusat (cx, cy):
      1. Translasi ke origin: (x - cx, y - cy)
      2. Rotasi terhadap origin
      3. Translasi kembali: + (cx, cy)
    
    Args:
        points: list of (x, y) — titik-titik objek
        angle_degrees: sudut rotasi dalam derajat (positif = searah jarum jam)
        center: (cx, cy) titik pusat rotasi. Jika None, gunakan pusat bbox.
    
    Returns:
        list of (x', y'): titik-titik setelah rotasi
    """
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
    """
    Scaling: memperbesar atau memperkecil objek terhadap titik pusat.
    
    Rumus (scaling terhadap origin):
      x' = x * factor
      y' = y * factor
    
    Untuk scaling terhadap titik pusat (cx, cy):
      1. Translasi ke origin: (x - cx, y - cy)
      2. Scaling: * factor
      3. Translasi kembali: + (cx, cy)
    
    Args:
        points: list of (x, y) — titik-titik objek
        factor: faktor skala (> 1 = perbesar, < 1 = perkecil)
        center: (cx, cy) titik pusat scaling. Jika None, gunakan pusat bbox.
    
    Returns:
        list of (x', y'): titik-titik setelah scaling
    """
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
    """
    Refleksi: membalikkan objek terhadap sumbu horizontal atau vertikal.
    """
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
