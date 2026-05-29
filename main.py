"""
main.py
Aplikasi Mini Paint — Entry point dan GUI utama.

Menjalankan aplikasi:
    python main.py

Fitur:
  - Canvas menggambar interaktif
  - Tool: Line, Bezier, Rectangle, Circle, Triangle, Fill, Text, Select
  - Algoritma: DDA/Bresenham (garis), Bezier Curve, Flood Fill
    - Kurva: Bezier / B-Spline
  - Atribut: Warna, Ketebalan, Style garis
  - Transformasi: Translasi, Rotasi, Scaling
  - Animasi: Bounce, Pulse, Spin
  - Multimedia: Teks dan Gambar
  - Undo, Clear Canvas, Save PNG

Tugas Akhir Grafika Komputer dan Multimedia
"""

import tkinter as tk
from tkinter import ttk, colorchooser, messagebox
import sys
import os

try:
    import ctypes
    # Meminta Windows agar aplikasi tidak di-scale secara otomatis (membuatnya tajam)
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    pass
# Tambahkan direktori saat ini ke path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from canvas_manager import CanvasManager
from animation import AnimationController


class MiniPaintApp:
    """
    Kelas utama aplikasi Mini Paint.
    Membangun seluruh GUI dan menghubungkan komponen.
    """

    def __init__(self, root):
        self.root = root
        self.root.title("Mini Paint — Grafika Komputer & Multimedia")
        self.root.geometry("1200x780")
        self.root.minsize(900, 600)

        # Warna tema
        self.BG_DARK = "#1E1E2E"
        self.BG_MEDIUM = "#2D2D44"
        self.BG_LIGHT = "#3A3A55"
        self.BG_HOVER = "#4A4A6A"
        self.ACCENT = "#7C3AED"
        self.ACCENT_LIGHT = "#A78BFA"
        self.TEXT_PRIMARY = "#E2E8F0"
        self.TEXT_SECONDARY = "#94A3B8"
        self.BORDER_COLOR = "#4A4A6A"
        self.CANVAS_BG = "#FFFFFF"
        self.SUCCESS = "#10B981"
        self.WARNING = "#F59E0B"
        self.DANGER = "#EF4444"

        # Konfigurasi style ttk
        self.style = ttk.Style()
        self.style.theme_use('clam')
        self._configure_styles()

        # Inisialisasi variabel
        self.active_tool = tk.StringVar(value="line")
        self.line_width_var = tk.IntVar(value=2)
        self.line_style_var = tk.StringVar(value="solid")
        self.anim_type_var = tk.StringVar(value="bounce")

        # Controller animasi
        self.animation_controller = AnimationController()

        # Canvas manager akan diinisialisasi di _build_canvas
        self.canvas_mgr = None

        # Bangun UI
        self._build_ui()

        # Bind keyboard shortcuts
        self.root.bind("<Control-z>", lambda e: self.canvas_mgr.undo())
        self.root.bind("<Control-s>", lambda e: self.canvas_mgr.save_canvas())
        self.root.bind("<Delete>", lambda e: self._delete_selected())
        self.root.bind("<Escape>", lambda e: self._on_tool_select("select"))

    def _configure_styles(self):
        """Konfigurasi style tema untuk ttk widgets."""
        self.style.configure("Dark.TFrame", background=self.BG_DARK)
        self.style.configure("Medium.TFrame", background=self.BG_MEDIUM)

        self.style.configure("Dark.TLabel",
            background=self.BG_DARK,
            foreground=self.TEXT_PRIMARY,
            font=("Segoe UI", 9)
        )
        self.style.configure("Header.TLabel",
            background=self.BG_DARK,
            foreground=self.TEXT_PRIMARY,
            font=("Segoe UI", 10, "bold")
        )
        self.style.configure("Section.TLabel",
            background=self.BG_DARK,
            foreground=self.ACCENT_LIGHT,
            font=("Segoe UI", 9, "bold")
        )

        self.style.configure("Toolbar.TFrame", background=self.BG_MEDIUM)

        self.style.configure("Tool.TButton",
            background=self.BG_LIGHT,
            foreground=self.TEXT_PRIMARY,
            font=("Segoe UI", 9),
            padding=(8, 5),
            borderwidth=0
        )
        self.style.map("Tool.TButton",
            background=[("active", self.ACCENT), ("pressed", self.ACCENT)],
            foreground=[("active", "#FFFFFF"), ("pressed", "#FFFFFF")]
        )

        self.style.configure("Active.TButton",
            background=self.ACCENT,
            foreground="#FFFFFF",
            font=("Segoe UI", 9, "bold"),
            padding=(8, 5),
            borderwidth=0
        )

        self.style.configure("Action.TButton",
            background=self.BG_LIGHT,
            foreground=self.TEXT_PRIMARY,
            font=("Segoe UI", 8),
            padding=(6, 3),
            borderwidth=0
        )
        self.style.map("Action.TButton",
            background=[("active", self.ACCENT), ("pressed", self.ACCENT)],
            foreground=[("active", "#FFFFFF"), ("pressed", "#FFFFFF")]
        )

        self.style.configure("Danger.TButton",
            background=self.DANGER,
            foreground="#FFFFFF",
            font=("Segoe UI", 8),
            padding=(6, 3),
            borderwidth=0
        )

        self.style.configure("Success.TButton",
            background=self.SUCCESS,
            foreground="#FFFFFF",
            font=("Segoe UI", 8),
            padding=(6, 3),
            borderwidth=0
        )

    # ============================================================
    # BUILD UI
    # ============================================================

    def _build_ui(self):
        """Membangun seluruh antarmuka pengguna."""
        self.root.configure(bg=self.BG_DARK)

        # Container utama
        main_container = tk.Frame(self.root, bg=self.BG_DARK)
        main_container.pack(fill=tk.BOTH, expand=True)

        # === TOOLBAR ATAS ===
        self._build_toolbar(main_container)

        # === BODY: panel kiri + canvas + panel kanan ===
        body = tk.Frame(main_container, bg=self.BG_DARK)
        body.pack(fill=tk.BOTH, expand=True, padx=4, pady=(0, 4))

        # Panel kiri (tools)
        self._build_tool_panel(body)

        # Canvas tengah
        self._build_canvas(body)

        # Panel kanan (properties)
        self._build_property_panel(body)

        # === STATUS BAR ===
        self._build_status_bar(main_container)

        # Aktifkan tool default (setelah semua UI siap)
        self._on_tool_select("line")

    # ============================================================
    # TOOLBAR ATAS
    # ============================================================

    def _build_toolbar(self, parent):
        """Membangun toolbar utama di bagian atas."""
        toolbar = tk.Frame(parent, bg=self.BG_MEDIUM, height=48)
        toolbar.pack(fill=tk.X, padx=4, pady=4)
        toolbar.pack_propagate(False)

        inner = tk.Frame(toolbar, bg=self.BG_MEDIUM)
        inner.pack(fill=tk.BOTH, expand=True, padx=8, pady=6)

        # Logo / Judul
        title = tk.Label(inner, text="🎨 Mini Paint",
            bg=self.BG_MEDIUM, fg=self.ACCENT_LIGHT,
            font=("Segoe UI", 13, "bold"))
        title.pack(side=tk.LEFT, padx=(0, 20))

        # Separator
        sep = tk.Frame(inner, width=1, bg=self.BORDER_COLOR)
        sep.pack(side=tk.LEFT, fill=tk.Y, padx=8)

        # Tombol toolbar
        toolbar_buttons = [
            ("📄 New", self._on_clear_canvas),
            ("💾 Save", self._on_save),
            ("↩ Undo", self._on_undo),
            ("🖼 Image", self._on_insert_image),
            ("🎨 Color", self._on_choose_color),
        ]

        for text, cmd in toolbar_buttons:
            btn = tk.Button(inner, text=text,
                bg=self.BG_LIGHT, fg=self.TEXT_PRIMARY,
                font=("Segoe UI", 9), relief=tk.FLAT,
                padx=10, pady=3, cursor="hand2",
                activebackground=self.ACCENT,
                activeforeground="#FFFFFF",
                command=cmd)
            btn.pack(side=tk.LEFT, padx=2)
            btn.bind("<Enter>", lambda e, b=btn: b.config(bg=self.BG_HOVER))
            btn.bind("<Leave>", lambda e, b=btn: b.config(bg=self.BG_LIGHT))

        # Separator
        sep2 = tk.Frame(inner, width=1, bg=self.BORDER_COLOR)
        sep2.pack(side=tk.LEFT, fill=tk.Y, padx=8)

        # Animasi controls
        anim_label = tk.Label(inner, text="Animation:",
            bg=self.BG_MEDIUM, fg=self.TEXT_SECONDARY,
            font=("Segoe UI", 9))
        anim_label.pack(side=tk.LEFT, padx=(0, 4))

        anim_combo = ttk.Combobox(inner, textvariable=self.anim_type_var,
            values=["bounce", "pulse", "spin"],
            state="readonly", width=8,
            font=("Segoe UI", 9))
        anim_combo.pack(side=tk.LEFT, padx=2)

        btn_animate = tk.Button(inner, text="▶ Animate",
            bg="#10B981", fg="#FFFFFF",
            font=("Segoe UI", 9, "bold"), relief=tk.FLAT,
            padx=10, pady=3, cursor="hand2",
            activebackground="#059669",
            command=self._on_animate)
        btn_animate.pack(side=tk.LEFT, padx=2)

        btn_stop = tk.Button(inner, text="⏹ Stop",
            bg=self.DANGER, fg="#FFFFFF",
            font=("Segoe UI", 9, "bold"), relief=tk.FLAT,
            padx=10, pady=3, cursor="hand2",
            activebackground="#DC2626",
            command=self._on_stop_animation)
        btn_stop.pack(side=tk.LEFT, padx=2)

    # ============================================================
    # PANEL TOOLS (KIRI)
    # ============================================================

    def _build_tool_panel(self, parent):
        """Membangun panel tools di sisi kiri."""
        panel = tk.Frame(parent, bg=self.BG_DARK, width=130)
        panel.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 4))
        panel.pack_propagate(False)

        # Header
        header = tk.Label(panel, text="🔧 TOOLS",
            bg=self.BG_DARK, fg=self.ACCENT_LIGHT,
            font=("Segoe UI", 10, "bold"))
        header.pack(pady=(8, 8), padx=8, anchor=tk.W)

        # Separator
        sep = tk.Frame(panel, height=1, bg=self.BORDER_COLOR)
        sep.pack(fill=tk.X, padx=8, pady=(0, 8))

        # List tool dasar yang disederhanakan
        tools = [
            ("select",    "⬚   Select"),
            ("pencil",    "✎   Pencil"),
            ("eraser",    "▱   Eraser"),
            ("fill",      "♨   Fill"),
            ("text",      "T   Text"),
        ]

        self.tool_buttons = {}

        for tool_id, tool_label in tools:
            btn = tk.Button(panel, text=tool_label,
                bg=self.BG_LIGHT, fg=self.TEXT_PRIMARY,
                font=("Segoe UI", 12), relief=tk.FLAT,
                anchor=tk.W, justify=tk.LEFT, padx=16, pady=8,
                cursor="hand2",
                activebackground=self.ACCENT,
                activeforeground="#FFFFFF",
                command=lambda t=tool_id: self._on_tool_select(t))
            btn.pack(fill=tk.X, padx=8, pady=3)
            self.tool_buttons[tool_id] = btn

            # Hover effect
            btn.bind("<Enter>", lambda e, b=btn, t=tool_id:
                b.config(bg=self.BG_HOVER) if self.active_tool.get() != t else None)
            btn.bind("<Leave>", lambda e, b=btn, t=tool_id:
                b.config(bg=self.ACCENT if self.active_tool.get() == t else self.BG_LIGHT))

        # Separator
        sep2 = tk.Frame(panel, height=1, bg=self.BORDER_COLOR)
        sep2.pack(fill=tk.X, padx=8, pady=12)

        # Dropdown Shapes
        tk.Label(panel, text="Shapes:", bg=self.BG_DARK, fg=self.TEXT_SECONDARY, font=("Segoe UI", 8)).pack(padx=8, anchor=tk.W)
        self.shape_var = tk.StringVar(value="Line")
        self.shape_combo = ttk.Combobox(panel, textvariable=self.shape_var,
                           values=["Line", "Curve", "Rectangle", "Circle", "Triangle", "Trapezium", "Ellipse"],
                           state="readonly", width=14, font=("Segoe UI", 9))
        self.shape_combo.pack(padx=8, pady=(2, 10))
        self.shape_combo.bind("<<ComboboxSelected>>", self._on_shape_change)

        # Separator
        sep3 = tk.Frame(panel, height=1, bg=self.BORDER_COLOR)
        sep3.pack(fill=tk.X, padx=8, pady=8)

        # Dropdown Line/Curve Algorithm
        tk.Label(panel, text="Line/Curve Algo:", bg=self.BG_DARK, fg=self.TEXT_SECONDARY, font=("Segoe UI", 8)).pack(padx=8, anchor=tk.W)

        self.line_algo_var = tk.StringVar(value="Bresenham Line")
        self.algo_combo = ttk.Combobox(panel, textvariable=self.line_algo_var,
                           values=["Bresenham Line", "DDA Line", "Bezier Curve", "B-Spline Curve"],
                           state="readonly", width=14, font=("Segoe UI", 9))
        self.algo_combo.pack(padx=8, pady=(2, 10))
        
        self.algo_combo.bind("<<ComboboxSelected>>", self._on_algo_change)

        # Dropdown Fill Algorithm
        tk.Label(panel, text="Fill Algo:", bg=self.BG_DARK, fg=self.TEXT_SECONDARY, font=("Segoe UI", 8)).pack(padx=8, anchor=tk.W)
        
        self.fill_algo_var = tk.StringVar(value="Flood Fill")
        self.fill_combo = ttk.Combobox(panel, textvariable=self.fill_algo_var,
                           values=["Flood Fill", "Boundary Fill"],
                           state="readonly", width=14, font=("Segoe UI", 9))
        self.fill_combo.pack(padx=8, pady=(2, 10))
        self.fill_combo.bind("<<ComboboxSelected>>", self._on_fill_algo_change)
        
        # Info algoritma
        self.algo_label = tk.Label(panel,
            text="Algorithm:\nBresenham Line",
            bg=self.BG_DARK, fg=self.TEXT_SECONDARY,
            font=("Segoe UI", 8), justify=tk.LEFT,
            wraplength=110)
        self.algo_label.pack(padx=8, anchor=tk.W)

    # ============================================================
    # CANVAS
    # ============================================================

    def _build_canvas(self, parent):
        """Membangun area canvas utama."""
        canvas_frame = tk.Frame(parent, bg=self.BORDER_COLOR,
            highlightthickness=0)
        canvas_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Canvas dengan border
        inner_frame = tk.Frame(canvas_frame, bg=self.BORDER_COLOR, bd=2)
        inner_frame.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)

        self.canvas = tk.Canvas(inner_frame,
            bg=self.CANVAS_BG,
            highlightthickness=0,
            cursor="crosshair")
        self.canvas.pack(fill=tk.BOTH, expand=True)

        # Inisialisasi canvas manager
        self.canvas_mgr = CanvasManager(
            self.canvas, self.root,
            status_callback=self._update_status
        )

    # ============================================================
    # PANEL PROPERTIES (KANAN)
    # ============================================================

    def _build_property_panel(self, parent):
        """Membangun panel properti di sisi kanan."""
        panel = tk.Frame(parent, bg=self.BG_DARK, width=170)
        panel.pack(side=tk.RIGHT, fill=tk.Y, padx=(4, 0))
        panel.pack_propagate(False)

        # Header
        header = tk.Label(panel, text="⚙ PROPERTIES",
            bg=self.BG_DARK, fg=self.ACCENT_LIGHT,
            font=("Segoe UI", 10, "bold"))
        header.pack(pady=(8, 8), padx=8, anchor=tk.W)

        sep = tk.Frame(panel, height=1, bg=self.BORDER_COLOR)
        sep.pack(fill=tk.X, padx=8, pady=(0, 8))

        # === Warna Aktif ===
        color_frame = tk.Frame(panel, bg=self.BG_DARK)
        color_frame.pack(fill=tk.X, padx=8, pady=4)

        tk.Label(color_frame, text="Outline Color",
            bg=self.BG_DARK, fg=self.TEXT_SECONDARY,
            font=("Segoe UI", 8)).pack(anchor=tk.W)

        self.color_indicator = tk.Button(color_frame,
            bg="#000000", width=16, height=1,
            relief=tk.FLAT, cursor="hand2",
            command=self._on_choose_color)
        self.color_indicator.pack(fill=tk.X, pady=(2, 0))

        # === Fill Color ===
        fill_frame = tk.Frame(panel, bg=self.BG_DARK)
        fill_frame.pack(fill=tk.X, padx=8, pady=4)

        tk.Label(fill_frame, text="Fill Color",
            bg=self.BG_DARK, fg=self.TEXT_SECONDARY,
            font=("Segoe UI", 8)).pack(anchor=tk.W)

        fill_btn_row = tk.Frame(fill_frame, bg=self.BG_DARK)
        fill_btn_row.pack(fill=tk.X, pady=(2, 0))

        self.fill_indicator = tk.Button(fill_btn_row,
            bg="#FFFFFF", text="None", fg="#999999",
            width=10, height=1,
            relief=tk.FLAT, cursor="hand2",
            font=("Segoe UI", 8),
            command=self._on_choose_fill_color)
        self.fill_indicator.pack(side=tk.LEFT, expand=True, fill=tk.X)

        btn_clear_fill = tk.Button(fill_btn_row, text="✕",
            bg=self.BG_LIGHT, fg=self.DANGER,
            font=("Segoe UI", 8, "bold"), relief=tk.FLAT,
            width=3, cursor="hand2",
            command=self._on_clear_fill_color)
        btn_clear_fill.pack(side=tk.RIGHT, padx=(2, 0))

        sep2 = tk.Frame(panel, height=1, bg=self.BORDER_COLOR)
        sep2.pack(fill=tk.X, padx=8, pady=8)

        # === Ketebalan Garis ===
        width_frame = tk.Frame(panel, bg=self.BG_DARK)
        width_frame.pack(fill=tk.X, padx=8, pady=4)

        self.width_label = tk.Label(width_frame,
            text="Line Width: 2 px",
            bg=self.BG_DARK, fg=self.TEXT_SECONDARY,
            font=("Segoe UI", 8))
        self.width_label.pack(anchor=tk.W)

        width_slider = tk.Scale(width_frame,
            from_=1, to=10, orient=tk.HORIZONTAL,
            variable=self.line_width_var,
            bg=self.BG_DARK, fg=self.TEXT_PRIMARY,
            troughcolor=self.BG_LIGHT,
            highlightthickness=0,
            sliderrelief=tk.FLAT,
            font=("Segoe UI", 8),
            command=self._on_width_change)
        width_slider.pack(fill=tk.X, pady=(2, 0))

        # === Style Garis ===
        style_frame = tk.Frame(panel, bg=self.BG_DARK)
        style_frame.pack(fill=tk.X, padx=8, pady=4)

        tk.Label(style_frame, text="Line Style",
            bg=self.BG_DARK, fg=self.TEXT_SECONDARY,
            font=("Segoe UI", 8)).pack(anchor=tk.W)

        style_combo = ttk.Combobox(style_frame,
            textvariable=self.line_style_var,
            values=["solid", "dashed", "dotted"],
            state="readonly", width=14,
            font=("Segoe UI", 9))
        style_combo.pack(fill=tk.X, pady=(2, 0))
        style_combo.bind("<<ComboboxSelected>>", self._on_style_change)

        sep3 = tk.Frame(panel, height=1, bg=self.BORDER_COLOR)
        sep3.pack(fill=tk.X, padx=8, pady=8)

        # === TRANSFORMASI ===
        tk.Label(panel, text="🔄 TRANSFORM",
            bg=self.BG_DARK, fg=self.ACCENT_LIGHT,
            font=("Segoe UI", 9, "bold")).pack(padx=8, anchor=tk.W)

        # Tombol arah (Move)
        move_frame = tk.Frame(panel, bg=self.BG_DARK)
        move_frame.pack(padx=8, pady=6)

        # Baris atas: tombol Up
        btn_up = tk.Button(move_frame, text="▲",
            bg=self.BG_LIGHT, fg=self.TEXT_PRIMARY,
            font=("Segoe UI", 10), relief=tk.FLAT,
            width=3, cursor="hand2",
            activebackground=self.ACCENT,
            command=lambda: self._on_transform("translate", dy=-20))
        btn_up.grid(row=0, column=1, padx=2, pady=2)

        # Baris tengah: Left, label, Right
        btn_left = tk.Button(move_frame, text="◄",
            bg=self.BG_LIGHT, fg=self.TEXT_PRIMARY,
            font=("Segoe UI", 10), relief=tk.FLAT,
            width=3, cursor="hand2",
            activebackground=self.ACCENT,
            command=lambda: self._on_transform("translate", dx=-20))
        btn_left.grid(row=1, column=0, padx=2, pady=2)

        move_label = tk.Label(move_frame, text="Move",
            bg=self.BG_DARK, fg=self.TEXT_SECONDARY,
            font=("Segoe UI", 7))
        move_label.grid(row=1, column=1, padx=2, pady=2)

        btn_right = tk.Button(move_frame, text="►",
            bg=self.BG_LIGHT, fg=self.TEXT_PRIMARY,
            font=("Segoe UI", 10), relief=tk.FLAT,
            width=3, cursor="hand2",
            activebackground=self.ACCENT,
            command=lambda: self._on_transform("translate", dx=20))
        btn_right.grid(row=1, column=2, padx=2, pady=2)

        # Baris bawah: Down
        btn_down = tk.Button(move_frame, text="▼",
            bg=self.BG_LIGHT, fg=self.TEXT_PRIMARY,
            font=("Segoe UI", 10), relief=tk.FLAT,
            width=3, cursor="hand2",
            activebackground=self.ACCENT,
            command=lambda: self._on_transform("translate", dy=20))
        btn_down.grid(row=2, column=1, padx=2, pady=2)

        # Hover effects untuk tombol arah
        for btn in [btn_up, btn_down, btn_left, btn_right]:
            btn.bind("<Enter>", lambda e, b=btn: b.config(bg=self.BG_HOVER))
            btn.bind("<Leave>", lambda e, b=btn: b.config(bg=self.BG_LIGHT))

        # Tombol Rotate & Scale
        rs_frame = tk.Frame(panel, bg=self.BG_DARK)
        rs_frame.pack(fill=tk.X, padx=8, pady=4)
        
        btn_flip_h = tk.Button(rs_frame, text="↔ Flip Horizontal",
            bg=self.BG_LIGHT, fg=self.TEXT_PRIMARY, font=("Segoe UI", 8), relief=tk.FLAT, cursor="hand2", pady=4,
            activebackground=self.ACCENT, activeforeground="#FFFFFF",
            command=lambda: self._on_transform("reflect", axis='x'))
        btn_flip_h.pack(fill=tk.X, pady=1)
        btn_flip_h.bind("<Enter>", lambda e: btn_flip_h.config(bg=self.BG_HOVER))
        btn_flip_h.bind("<Leave>", lambda e: btn_flip_h.config(bg=self.BG_LIGHT))

        btn_flip_v = tk.Button(rs_frame, text="↕ Flip Vertical",
            bg=self.BG_LIGHT, fg=self.TEXT_PRIMARY, font=("Segoe UI", 8), relief=tk.FLAT, cursor="hand2", pady=4,
            activebackground=self.ACCENT, activeforeground="#FFFFFF",
            command=lambda: self._on_transform("reflect", axis='y'))
        btn_flip_v.pack(fill=tk.X, pady=2)
        btn_flip_v.bind("<Enter>", lambda e: btn_flip_v.config(bg=self.BG_HOVER))
        btn_flip_v.bind("<Leave>", lambda e: btn_flip_v.config(bg=self.BG_LIGHT))

        btn_rotate = tk.Button(rs_frame, text="🔄 Rotate 15°",
            bg=self.BG_LIGHT, fg=self.TEXT_PRIMARY,
            font=("Segoe UI", 8), relief=tk.FLAT,
            cursor="hand2", pady=4,
            activebackground=self.ACCENT,
            activeforeground="#FFFFFF",
            command=lambda: self._on_transform("rotate", angle=15))
        btn_rotate.pack(fill=tk.X, pady=2)
        btn_rotate.bind("<Enter>", lambda e: btn_rotate.config(bg=self.BG_HOVER))
        btn_rotate.bind("<Leave>", lambda e: btn_rotate.config(bg=self.BG_LIGHT))

        scale_row = tk.Frame(rs_frame, bg=self.BG_DARK)
        scale_row.pack(fill=tk.X, pady=2)

        btn_scale_up = tk.Button(scale_row, text="🔍+ Scale Up",
            bg=self.BG_LIGHT, fg=self.TEXT_PRIMARY,
            font=("Segoe UI", 8), relief=tk.FLAT,
            cursor="hand2", pady=4,
            activebackground=self.ACCENT,
            activeforeground="#FFFFFF",
            command=lambda: self._on_transform("scale", factor=1.2))
        btn_scale_up.pack(fill=tk.X, pady=1)
        btn_scale_up.bind("<Enter>", lambda e: btn_scale_up.config(bg=self.BG_HOVER))
        btn_scale_up.bind("<Leave>", lambda e: btn_scale_up.config(bg=self.BG_LIGHT))

        btn_scale_down = tk.Button(scale_row, text="🔍- Scale Down",
            bg=self.BG_LIGHT, fg=self.TEXT_PRIMARY,
            font=("Segoe UI", 8), relief=tk.FLAT,
            cursor="hand2", pady=4,
            activebackground=self.ACCENT,
            activeforeground="#FFFFFF",
            command=lambda: self._on_transform("scale", factor=0.8))
        btn_scale_down.pack(fill=tk.X, pady=1)
        btn_scale_down.bind("<Enter>", lambda e: btn_scale_down.config(bg=self.BG_HOVER))
        btn_scale_down.bind("<Leave>", lambda e: btn_scale_down.config(bg=self.BG_LIGHT))

        sep4 = tk.Frame(panel, height=1, bg=self.BORDER_COLOR)
        sep4.pack(fill=tk.X, padx=8, pady=8)

        # === DELETE OBJECT ===
        btn_delete = tk.Button(panel, text="🗑 Delete Object",
            bg=self.DANGER, fg="#FFFFFF",
            font=("Segoe UI", 8, "bold"), relief=tk.FLAT,
            cursor="hand2", pady=4,
            activebackground="#DC2626",
            command=self._delete_selected)
        btn_delete.pack(fill=tk.X, padx=8, pady=2)

    # ============================================================
    # STATUS BAR
    # ============================================================

    def _build_status_bar(self, parent):
        """Membangun status bar di bagian bawah."""
        self.status_bar = tk.Label(parent,
            text="Tool: Line | Objects: 0 | Position: (0, 0)",
            bg=self.BG_MEDIUM, fg=self.TEXT_SECONDARY,
            font=("Segoe UI", 8),
            anchor=tk.W, padx=12, pady=4)
        self.status_bar.pack(fill=tk.X, side=tk.BOTTOM, padx=4, pady=(0, 4))

    # ============================================================
    # EVENT HANDLERS
    # ============================================================

    def _on_tool_select(self, tool):
        """Handler saat tool dipilih."""
        self.active_tool.set(tool)
        if self.canvas_mgr:
            self.canvas_mgr.set_tool(tool)

        # Update visual tombol
        for t_id, btn in self.tool_buttons.items():
            if t_id == tool:
                btn.config(bg=self.ACCENT, fg="#FFFFFF",
                    font=("Segoe UI", 9, "bold"))
            else:
                btn.config(bg=self.BG_LIGHT, fg=self.TEXT_PRIMARY,
                    font=("Segoe UI", 9))

        # Update label algoritma
        curve_algo = getattr(self.canvas_mgr, "current_curve_algorithm", "Bezier")
        line_algo = getattr(self.canvas_mgr, "current_line_algorithm", "Bresenham")
        fill_algo = getattr(self.canvas_mgr, "current_fill_algorithm", "Flood Fill")
        
        algo_texts = {
            "pencil": "Tool: Pencil\n(Freehand)",
            "eraser": "Tool: Eraser\n(White Freehand)",
            "line": f"Algorithm:\n{line_algo} Line",
            "curve": f"Algorithm:\n{curve_algo} Curve\n(click 4 points)",
            "bezier": f"Algorithm:\n{curve_algo} Curve\n(click 4 points)",
            "fill": f"Algorithm:\n{fill_algo}",
            "select": "Mode:\nSelect & Transform",
            "rectangle": "Shape:\nRectangle",
            "circle": "Shape:\nCircle",
            "triangle": "Shape:\nTriangle",
            "trapezium": "Shape:\nTrapezium",
            "ellipse": "Shape:\nEllipse",
            "text": "Multimedia:\nText Input",
        }
        self.algo_label.config(text=algo_texts.get(tool, ""))

    def _on_shape_change(self, event):
        """Handler saat shape diubah dari dropdown."""
        shape = self.shape_var.get().lower()
        if shape == "curve":
            shape = "bezier"
        self._on_tool_select(shape)

    def _on_fill_algo_change(self, event):
        """Handler saat algoritma fill diubah."""
        if self.canvas_mgr:
            self.canvas_mgr.current_fill_algorithm = self.fill_algo_var.get()
            self._on_tool_select("fill")

    def _on_choose_color(self):
        """Membuka color picker untuk outline color."""
        color = colorchooser.askcolor(
            initialcolor=self.canvas_mgr.current_color,
            title="Pilih Warna Outline"
        )
        if color[1]:
            self.canvas_mgr.current_color = color[1]
            self.color_indicator.config(bg=color[1])
            if self.active_tool.get() == "select" and self.canvas_mgr.selected_object:
                obj = self.canvas_mgr.selected_object
                obj.outline_color = color[1]
                self.canvas_mgr.render_object(obj)

    def _on_choose_fill_color(self):
        """Membuka color picker untuk fill color."""
        initial = self.canvas_mgr.current_fill_color or "#FFFFFF"
        color = colorchooser.askcolor(
            initialcolor=initial,
            title="Pilih Warna Fill"
        )
        if color[1]:
            self.canvas_mgr.current_fill_color = color[1]
            self.fill_indicator.config(bg=color[1], text="", fg=color[1])
            if self.active_tool.get() == "select" and self.canvas_mgr.selected_object:
                obj = self.canvas_mgr.selected_object
                obj.fill_color = color[1]
                self.canvas_mgr.render_object(obj)

    def _on_clear_fill_color(self):
        """Menghapus fill color (set ke None)."""
        self.canvas_mgr.current_fill_color = None
        self.fill_indicator.config(bg="#FFFFFF", text="None", fg="#999999")
        if self.active_tool.get() == "select" and self.canvas_mgr.selected_object:
            obj = self.canvas_mgr.selected_object
            obj.fill_color = None
            self.canvas_mgr.render_object(obj)

    def _on_width_change(self, value):
        """Handler saat ketebalan garis diubah."""
        w = int(float(value))
        self.canvas_mgr.current_line_width = w
        self.width_label.config(text=f"Line Width: {w} px")
        if self.active_tool.get() == "select" and self.canvas_mgr.selected_object:
            obj = self.canvas_mgr.selected_object
            obj.line_width = w
            self.canvas_mgr.render_object(obj)

    def _on_style_change(self, event):
        """Handler saat style garis diubah."""
        self.canvas_mgr.current_line_style = self.line_style_var.get()
        if self.active_tool.get() == "select" and self.canvas_mgr.selected_object:
            obj = self.canvas_mgr.selected_object
            obj.line_style = self.line_style_var.get()
            self.canvas_mgr.render_object(obj)
    def _on_algo_change(self, event):
        """Handler saat algoritma garis diubah."""
        if not self.canvas_mgr:
            return

        selected = self.line_algo_var.get()
        if "Line" in selected:
            if "DDA" in selected:
                self.canvas_mgr.current_line_algorithm = "DDA"
            else:
                self.canvas_mgr.current_line_algorithm = "Bresenham"
            self.shape_var.set("Line")
            self._on_tool_select("line")
        else:
            if "B-Spline" in selected:
                self.canvas_mgr.current_curve_algorithm = "B-Spline"
            else:
                self.canvas_mgr.current_curve_algorithm = "Bezier"
            self.shape_var.set("Curve")
            self._on_tool_select("bezier")

    def _on_transform(self, transform_type, **kwargs):
        """Handler untuk tombol transformasi."""
        self.canvas_mgr.transform_selected(transform_type, **kwargs)

    def _on_undo(self):
        """Handler tombol Undo."""
        self.canvas_mgr.undo()

    def _on_save(self):
        """Handler tombol Save."""
        self.canvas_mgr.save_canvas()

    def _on_clear_canvas(self):
        """Handler tombol New/Clear Canvas."""
        self.canvas_mgr.clear_canvas()

    def _on_insert_image(self):
        """Handler tombol Insert Image."""
        self.canvas_mgr.insert_image()

    def _on_animate(self):
        """Memulai animasi pada objek yang dipilih."""
        if self.canvas_mgr.selected_object is None:
            messagebox.showinfo("Info",
                "Pilih objek terlebih dahulu!\n"
                "Gunakan tool Select, lalu klik objek.")
            return

        anim_type = self.anim_type_var.get()
        self.animation_controller.start(
            self.canvas_mgr.selected_object,
            self.canvas_mgr,
            self.root,
            anim_type
        )

    def _on_stop_animation(self):
        """Menghentikan animasi."""
        self.animation_controller.stop()

    def _delete_selected(self):
        """Menghapus objek yang dipilih."""
        if self.canvas_mgr.selected_object is None:
            return

        self.canvas_mgr._push_undo()
        obj = self.canvas_mgr.selected_object

        # Hapus dari canvas
        for cid in obj.canvas_ids:
            self.canvas.delete(cid)

        # Hapus dari daftar objek
        self.canvas_mgr.objects = [
            o for o in self.canvas_mgr.objects if o.id != obj.id
        ]
        self.canvas_mgr._clear_selection()

    def _update_status(self, text):
        """Update teks status bar."""
        self.status_bar.config(text=text)


# ============================================================
# ENTRY POINT
# ============================================================

def main():
    """Menjalankan aplikasi Mini Paint."""
    root = tk.Tk()

    # Konfigurasi agar tampilan lebih baik di macOS
    try:
        root.tk.call('tk', 'scaling', 1.0)
    except Exception:
        pass

    app = MiniPaintApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
