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
        self.anim_type = "bounce"
        self.target_obj = None
        self.target_objects = []
        self.canvas_manager = None
        self.root = None
        self.on_stop = on_stop
        self.pulse_base_points = {}
        self.pulse_base_scale_factors = {}

        self.bounce_dx = 3
        self.bounce_direction = 1
        self.bounce_count = 0
        self.bounce_max = 60

        self.pulse_phase = 0
        self.pulse_count = 0
        self.pulse_max = 30
        self.pulse_amplitude = 0.25

        self.spin_angle = 3

    def start(self, obj, canvas_manager, root, anim_type="bounce"):
        """
        Memulai animasi pada satu atau beberapa objek.
        
        Args:
            obj: DrawingObject atau list DrawingObject yang akan dianimasikan
            canvas_manager: referensi ke CanvasManager untuk re-render
            root: Tk root window untuk after()
            anim_type: "bounce", "pulse", atau "spin"
        """
        self.stop()

        targets = obj if isinstance(obj, list) else [obj]
        self.target_objects = [target for target in targets if target is not None]
        if not self.target_objects:
            return

        self.target_obj = self.target_objects[0]
        self.canvas_manager = canvas_manager
        self.root = root
        self.anim_type = anim_type
        self.is_running = True

        self.bounce_count = 0
        self.bounce_direction = 1
        self.pulse_phase = 0
        self.pulse_count = 0
        self.pulse_base_points = {}
        self.pulse_base_scale_factors = {}
        if anim_type == "pulse":
            self.pulse_base_points = {
                target.id: [p for p in target.points]
                for target in self.target_objects
            }
            self.pulse_base_scale_factors = {
                target.id: getattr(target, "scale_factor", 1.0)
                for target in self.target_objects
            }

        self._animate_step()

    def stop(self):
        """Menghentikan animasi yang sedang berjalan."""
        was_active = self.is_running or bool(self.target_objects)
        target_objects = list(self.target_objects)
        canvas_manager = self.canvas_manager
        self.is_running = False
        if self.after_id and self.root:
            try:
                self.root.after_cancel(self.after_id)
            except Exception:
                pass
        self.after_id = None

        if self.anim_type == "pulse" and canvas_manager is not None:
            for target in target_objects:
                base_points = self.pulse_base_points.get(target.id)
                if base_points is None or target not in canvas_manager.objects:
                    continue
                target.points = [p for p in base_points]
                target.scale_factor = self.pulse_base_scale_factors.get(target.id, 1.0)
                canvas_manager.render_object(target)

        self.pulse_base_points = {}
        self.pulse_base_scale_factors = {}
        self.target_obj = None
        self.target_objects = []
        if was_active and self.on_stop:
            self.on_stop()

    def _animate_step(self):
        """Satu langkah animasi. Dipanggil berulang via after()."""
        if not self.is_running or not self.target_objects:
            return
        
        if self.canvas_manager is None:
            return

        if any(obj not in self.canvas_manager.objects for obj in self.target_objects):
            self.stop()
            return

        for obj in self.target_objects:
            if self.anim_type == "bounce":
                self._step_bounce(obj)
            elif self.anim_type == "pulse":
                self._step_pulse(obj)
            elif self.anim_type == "spin":
                self._step_spin(obj)

            self.canvas_manager.render_object(obj)

        if self.anim_type == "bounce":
            self.bounce_count += 1
            if self.bounce_count >= self.bounce_max:
                self.bounce_count = 0
                self.bounce_direction *= -1
        elif self.anim_type == "pulse":
            self.pulse_count += 1
            if self.pulse_count >= self.pulse_max:
                self.pulse_count = 0
                self.pulse_phase = 1 - self.pulse_phase

        self.target_obj = self.target_objects[0] if self.target_objects else None

        if self.is_running:
            self.after_id = self.root.after(30, self._animate_step)

    def _step_bounce(self, obj):
        """
        Animasi bounce: objek bergerak kiri-kanan.
        Menerapkan translasi horizontal bolak-balik.
        """
        dx = self.bounce_dx * self.bounce_direction
        obj.points = translate(obj.points, dx, 0)

    def _step_pulse(self, obj):
        """
        Animasi pulse: objek membesar-mengecil.
        Menghitung skala dari bentuk awal animasi, bukan kumulatif.
        """
        if obj.id not in self.pulse_base_points:
            self.pulse_base_points[obj.id] = [p for p in obj.points]
            self.pulse_base_scale_factors[obj.id] = getattr(obj, "scale_factor", 1.0)

        if self.pulse_phase == 0:
            progress = self.pulse_count / self.pulse_max
        else:
            progress = 1 - (self.pulse_count / self.pulse_max)

        factor = 1.0 + (self.pulse_amplitude * progress)
        base_points = self.pulse_base_points[obj.id]
        xs = [p[0] for p in base_points]
        ys = [p[1] for p in base_points]
        center = ((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2)
        obj.points = scale(base_points, factor, center)
        obj.scale_factor = self.pulse_base_scale_factors.get(obj.id, 1.0) * factor

    def _step_spin(self, obj):
        """
        Animasi spin: objek berputar perlahan.
        Menerapkan rotasi kecil setiap frame.
        """
        center = obj.get_center()
        obj.points = rotate(obj.points, self.spin_angle, center)
        obj.rotation += self.spin_angle
