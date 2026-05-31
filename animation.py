"""
animation.py
Controller untuk animasi objek pada canvas.
Mendukung tiga jenis animasi:
  - Bounce: objek bergerak kiri-kanan (translasi)
  - Pulse: objek membesar-mengecil (scaling)
  - Spin: objek berputar perlahan (rotasi)
"""

from transform import translate, rotate, scale


class AnimationController:
    """
    Mengontrol animasi pada objek yang dipilih.
    
    Menggunakan root.after() untuk loop animasi yang smooth.
    Interval default 30ms (~33 FPS).
    """

    def __init__(self, on_stop=None):
        self.is_running = False
        self.after_id = None
        self.anim_type = "bounce"  # "bounce", "pulse", "spin"
        self.target_obj = None
        self.canvas_manager = None
        self.root = None
        self.on_stop = on_stop

        # Parameter animasi bounce
        self.bounce_dx = 3        # Kecepatan gerak horizontal
        self.bounce_direction = 1  # 1 = kanan, -1 = kiri
        self.bounce_count = 0
        self.bounce_max = 60       # Jumlah langkah sebelum balik arah

        # Parameter animasi pulse
        self.pulse_phase = 0       # 0 = membesar, 1 = mengecil
        self.pulse_count = 0
        self.pulse_max = 30
        self.pulse_scale_up = 1.02
        self.pulse_scale_down = 0.98

        # Parameter animasi spin
        self.spin_angle = 3  # Derajat per frame

    def start(self, obj, canvas_manager, root, anim_type="bounce"):
        """
        Memulai animasi pada objek tertentu.
        
        Args:
            obj: DrawingObject yang akan dianimasikan
            canvas_manager: referensi ke CanvasManager untuk re-render
            root: Tk root window untuk after()
            anim_type: "bounce", "pulse", atau "spin"
        """
        # Hentikan animasi sebelumnya jika ada
        self.stop()

        self.target_obj = obj
        self.canvas_manager = canvas_manager
        self.root = root
        self.anim_type = anim_type
        self.is_running = True

        # Reset parameter
        self.bounce_count = 0
        self.bounce_direction = 1
        self.pulse_phase = 0
        self.pulse_count = 0

        # Mulai loop animasi
        self._animate_step()

    def stop(self):
        """Menghentikan animasi yang sedang berjalan."""
        was_active = self.is_running or self.target_obj is not None
        self.is_running = False
        if self.after_id and self.root:
            try:
                self.root.after_cancel(self.after_id)
            except Exception:
                pass
        self.after_id = None
        self.target_obj = None
        if was_active and self.on_stop:
            self.on_stop()

    def _animate_step(self):
        """Satu langkah animasi. Dipanggil berulang via after()."""
        if not self.is_running or self.target_obj is None:
            return
        
        if self.canvas_manager is None:
            return

        obj = self.target_obj
        if obj not in self.canvas_manager.objects:
            self.stop()
            return

        if self.anim_type == "bounce":
            self._step_bounce(obj)
        elif self.anim_type == "pulse":
            self._step_pulse(obj)
        elif self.anim_type == "spin":
            self._step_spin(obj)

        # Re-render objek yang berubah
        self.canvas_manager.render_object(obj)

        # Jadwalkan langkah berikutnya
        if self.is_running:
            self.after_id = self.root.after(30, self._animate_step)

    def _step_bounce(self, obj):
        """
        Animasi bounce: objek bergerak kiri-kanan.
        Menerapkan translasi horizontal bolak-balik.
        """
        dx = self.bounce_dx * self.bounce_direction
        obj.points = translate(obj.points, dx, 0)
        
        self.bounce_count += 1
        if self.bounce_count >= self.bounce_max:
            self.bounce_count = 0
            self.bounce_direction *= -1  # Balik arah

    def _step_pulse(self, obj):
        """
        Animasi pulse: objek membesar-mengecil.
        Menerapkan scaling berulang.
        """
        if self.pulse_phase == 0:
            factor = self.pulse_scale_up
        else:
            factor = self.pulse_scale_down

        center = obj.get_center()
        obj.points = scale(obj.points, factor, center)
        
        self.pulse_count += 1
        if self.pulse_count >= self.pulse_max:
            self.pulse_count = 0
            self.pulse_phase = 1 - self.pulse_phase  # Toggle fase

    def _step_spin(self, obj):
        """
        Animasi spin: objek berputar perlahan.
        Menerapkan rotasi kecil setiap frame.
        """
        center = obj.get_center()
        obj.points = rotate(obj.points, self.spin_angle, center)
        obj.rotation += self.spin_angle
