from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QWidget


@dataclass
class _ConfettiParticle:
    x: float
    y: float
    vx: float
    vy: float
    size: float
    rotation: float
    spin: float
    color: QColor
    shape: str
    life: float = 0.0


class TutorialConfettiOverlay(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.hide()
        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._advance)
        self._particles: list[_ConfettiParticle] = []
        self._running = False
        self._start_time = 0.0
        self._duration = 1.5
        self._gravity = 950.0

    @property
    def is_active(self) -> bool:
        return self._running

    def burst(self):
        width = max(1, self.width())
        height = max(1, self.height())
        origin_x = width * 0.5
        origin_y = height * 0.18
        palette = [
            QColor("#0ea5c6"),
            QColor("#53d8f4"),
            QColor("#7cf2aa"),
            QColor("#f6d365"),
            QColor("#f8fafc"),
            QColor("#82f7ff"),
        ]
        self._particles = []
        for _ in range(64):
            angle = random.uniform(-2.55, -0.55)
            speed = random.uniform(180.0, 460.0)
            self._particles.append(
                _ConfettiParticle(
                    x=origin_x + random.uniform(-36.0, 36.0),
                    y=origin_y + random.uniform(-10.0, 10.0),
                    vx=math.cos(angle) * speed,
                    vy=math.sin(angle) * speed,
                    size=random.uniform(6.0, 12.0),
                    rotation=random.uniform(0.0, 360.0),
                    spin=random.uniform(-420.0, 420.0),
                    color=random.choice(palette),
                    shape=random.choice(["rect", "diamond", "circle"]),
                )
            )
        self._start_time = time.monotonic()
        self._running = True
        self.show()
        self.raise_()
        self._timer.start()
        self.update()

    def stop(self):
        self._timer.stop()
        self._particles = []
        self._running = False
        self.hide()
        self.update()

    def _advance(self):
        if not self._running:
            return
        elapsed = time.monotonic() - self._start_time
        dt = 0.016
        for particle in self._particles:
            particle.life = elapsed
            particle.x += particle.vx * dt
            particle.y += particle.vy * dt
            particle.vy += self._gravity * dt
            particle.rotation += particle.spin * dt
        if elapsed >= self._duration:
            self.stop()
            return
        self.update()

    def paintEvent(self, event):
        _ = event
        if not self._running or not self._particles:
            return
        elapsed = time.monotonic() - self._start_time
        fade = max(0.0, 1.0 - (elapsed / self._duration))

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)

        for particle in self._particles:
            color = QColor(particle.color)
            color.setAlphaF(max(0.0, min(1.0, fade)))
            painter.save()
            painter.translate(particle.x, particle.y)
            painter.rotate(particle.rotation)
            painter.setBrush(color)
            size = particle.size
            if particle.shape == "circle":
                painter.drawEllipse(int(-size / 2), int(-size / 2), int(size), int(size))
            elif particle.shape == "diamond":
                painter.drawRect(int(-size / 2), int(-size / 2), int(size), int(size * 0.6))
            else:
                painter.drawRoundedRect(int(-size / 2), int(-size / 3), int(size), int(size * 0.7), 2, 2)
            painter.restore()
