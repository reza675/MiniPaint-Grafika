"""
drawing_algorithms.py
Implementasi algoritma grafika komputer:
  - Algoritma garis DDA (Digital Differential Analyzer)
  - Algoritma garis Bresenham
  - Algoritma kurva Bezier (kubik)
    - Algoritma kurva B-Spline (kubik uniform)
  - Algoritma Flood Fill (iteratif dengan stack)
"""

import math


# ============================================================
# ALGORITMA GARIS DDA (Digital Differential Analyzer)
# ============================================================

def dda_line(x1, y1, x2, y2):
    """
    Menggambar garis dari (x1,y1) ke (x2,y2) menggunakan algoritma DDA.
    
    Langkah-langkah:
    1. Hitung dx = x2 - x1, dy = y2 - y1
    2. Tentukan steps = max(|dx|, |dy|)
    3. Hitung increment: x_inc = dx/steps, y_inc = dy/steps
    4. Iterasi dari titik awal, tambahkan increment setiap langkah
    
    Returns:
        list of (int, int): kumpulan koordinat pixel pembentuk garis
    """
    points = []
    
    dx = x2 - x1
    dy = y2 - y1
    
    # Tentukan jumlah langkah berdasarkan jarak terbesar
    steps = max(abs(dx), abs(dy))
    
    if steps == 0:
        # Titik tunggal
        return [(round(x1), round(y1))]
    
    # Hitung increment per langkah
    x_inc = dx / steps
    y_inc = dy / steps
    
    # Iterasi dan kumpulkan titik-titik pixel
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
    """
    Menggambar garis dari (x1,y1) ke (x2,y2) menggunakan algoritma Bresenham.
    
    Keunggulan: hanya menggunakan operasi integer (tanpa floating point).
    Mendukung semua 8 oktan (semua arah garis).
    
    Langkah-langkah:
    1. Hitung dx, dy dan tentukan arah step (+1 atau -1)
    2. Gunakan parameter keputusan (decision parameter) p
    3. Jika p < 0: pilih pixel di arah utama saja
       Jika p >= 0: pilih pixel di kedua arah
    
    Returns:
        list of (int, int): kumpulan koordinat pixel pembentuk garis
    """
    points = []
    
    x1, y1, x2, y2 = int(round(x1)), int(round(y1)), int(round(x2)), int(round(y2))
    
    dx = abs(x2 - x1)
    dy = abs(y2 - y1)
    
    # Tentukan arah step
    sx = 1 if x1 < x2 else -1
    sy = 1 if y1 < y2 else -1
    
    # Inisialisasi error
    err = dx - dy
    
    while True:
        points.append((x1, y1))
        
        # Cek apakah sudah sampai titik akhir
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
    """
    Menggambar kurva Bezier berdasarkan titik kontrol.
    
    Mendukung:
      - Bezier kuadratik (3 titik kontrol)
      - Bezier kubik (4 titik kontrol)
    
    Menggunakan algoritma De Casteljau untuk menghitung titik pada kurva.
    
    Parameter t berjalan dari 0.0 hingga 1.0, menghasilkan titik-titik
    sepanjang kurva.
    
    Args:
        control_points: list of (x, y) — titik-titik kontrol
        num_segments: jumlah segmen kurva (semakin banyak = semakin halus)
    
    Returns:
        list of (float, float): titik-titik sepanjang kurva
    """
    if len(control_points) < 2:
        return list(control_points)
    
    curve_points = []
    n = len(control_points) - 1
    
    for i in range(num_segments + 1):
        t = i / num_segments
        
        # Algoritma De Casteljau
        # Reduksi titik kontrol secara rekursif
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
    """
    Shortcut untuk kurva Bezier kubik dengan tepat 4 titik kontrol.
    
    Rumus Bezier kubik:
      B(t) = (1-t)^3 * P0 + 3*(1-t)^2*t * P1 + 3*(1-t)*t^2 * P2 + t^3 * P3
    
    Returns:
        list of (float, float): titik-titik sepanjang kurva
    """
    return bezier_curve([p0, p1, p2, p3], num_segments)


# ============================================================
# ALGORITMA B-SPLINE KUBIK (UNIFORM)
# ============================================================

def bspline_curve(control_points, num_segments=200):
    """
    Menggambar kurva B-Spline kubik (uniform) berdasarkan titik kontrol.

    Minimal 4 titik kontrol. Jika > 4, kurva dibuat per segmen
    (setiap segmen menggunakan 4 titik kontrol berurutan).

    Args:
        control_points: list of (x, y) — titik-titik kontrol
        num_segments: jumlah segmen per batch (semakin banyak = halus)

    Returns:
        list of (float, float): titik-titik sepanjang kurva
    """
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

    # Jika hanya 4 titik, satu segmen saja
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
    """
    Mengisi area tertutup dengan warna baru menggunakan Flood Fill iteratif.
    
    Menggunakan pendekatan stack-based (bukan rekursif) untuk menghindari
    stack overflow pada area yang besar.
    
    Langkah-langkah:
    1. Ambil warna pixel di posisi klik (target_color)
    2. Jika target_color == fill_color, tidak perlu fill (sudah sama)
    3. Masukkan posisi klik ke stack
    4. Selama stack tidak kosong:
       a. Pop posisi dari stack
       b. Jika pixel di posisi tersebut == target_color:
          - Ubah warna pixel menjadi fill_color
          - Push 4 tetangga (atas, bawah, kiri, kanan) ke stack
    
    Args:
        photo_image: tkinter.PhotoImage dari canvas
        start_x, start_y: posisi klik user
        fill_color_rgb: tuple (r, g, b) warna baru
        tolerance: toleransi perbedaan warna (untuk anti-aliasing)
    
    Returns:
        photo_image yang sudah di-fill
    """
    width = photo_image.width()
    height = photo_image.height()
    
    # Validasi posisi
    if start_x < 0 or start_x >= width or start_y < 0 or start_y >= height:
        return photo_image
    
    # Ambil warna target (warna di posisi klik)
    target_color = photo_image.get(start_x, start_y)
    
    # Jika warna target sama dengan warna fill, tidak perlu apa-apa
    fill_r, fill_g, fill_b = fill_color_rgb
    if isinstance(target_color, tuple):
        tr, tg, tb = target_color
    else:
        # PhotoImage.get() mengembalikan string "r g b"
        parts = str(target_color).split()
        tr, tg, tb = int(parts[0]), int(parts[1]), int(parts[2])
    
    if (tr, tg, tb) == (fill_r, fill_g, fill_b):
        return photo_image
    
    def color_match(pixel_color):
        """Cek apakah warna pixel cocok dengan target (dengan toleransi)."""
        if isinstance(pixel_color, tuple):
            pr, pg, pb = pixel_color
        else:
            parts = str(pixel_color).split()
            pr, pg, pb = int(parts[0]), int(parts[1]), int(parts[2])
        
        return (abs(pr - tr) <= tolerance and
                abs(pg - tg) <= tolerance and
                abs(pb - tb) <= tolerance)
    
    # Format warna fill untuk PhotoImage.put()
    fill_hex = f"#{fill_r:02x}{fill_g:02x}{fill_b:02x}"
    
    # Stack-based flood fill
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
        
        # Push 4 tetangga
        stack.append((x + 1, y))
        stack.append((x - 1, y))
        stack.append((x, y + 1))
        stack.append((x, y - 1))
    
    # Terapkan perubahan warna secara batch (lebih efisien)
    # Kelompokkan pixel per baris untuk optimasi
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
    """
    Mengisi area menggunakan algoritma Boundary Fill iteratif.

    Boundary Fill berhenti saat bertemu warna batas (boundary_color),
    berbeda dari Flood Fill yang mengikuti warna target awal.
    """
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
    """Konversi warna hex (#RRGGBB) ke tuple (R, G, B)."""
    hex_color = hex_color.lstrip('#')
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))


def rgb_to_hex(r, g, b):
    """Konversi tuple (R, G, B) ke warna hex (#RRGGBB)."""
    return f"#{r:02x}{g:02x}{b:02x}"
