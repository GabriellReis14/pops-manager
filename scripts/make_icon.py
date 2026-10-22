"""Draws the POPS Manager icon (original artwork, no Sony trademarks) and writes:

    src/pops_manager/assets/icon.png   256x256, used by the window
    src/pops_manager/assets/icon.ico   16-256 px, used by the Windows executable

Run: python scripts/make_icon.py
"""
from __future__ import annotations
from pathlib import Path
import os
import struct
import sys

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QPointF, QRectF, Qt  # noqa: E402
from PySide6.QtGui import (QBrush, QColor, QConicalGradient, QGuiApplication, QImage, QLinearGradient,  # noqa: E402
                           QPainter, QPainterPath, QPen, QPolygonF, QRadialGradient)

ASSETS = Path(__file__).resolve().parents[1] / 'src' / 'pops_manager' / 'assets'
SIZES = (16, 24, 32, 48, 64, 128, 256)


def draw(size: int) -> QImage:
    image = QImage(size, size, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    p = QPainter(image)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    s = float(size)

    # console-grey tile
    tile = QRectF(0.03 * s, 0.03 * s, 0.94 * s, 0.94 * s)
    background = QLinearGradient(0, 0, 0, s)
    background.setColorAt(0, QColor('#6b7280')); background.setColorAt(1, QColor('#2b2f38'))
    p.setPen(Qt.PenStyle.NoPen); p.setBrush(QBrush(background))
    p.drawRoundedRect(tile, 0.2 * s, 0.2 * s)

    # silver disc with a rainbow sheen
    center = QPointF(0.47 * s, 0.47 * s)
    radius = 0.36 * s
    sheen = QConicalGradient(center, 35)
    for stop, color in ((0.0, '#f4f4f6'), (0.15, '#c9d8f5'), (0.3, '#eef0f2'), (0.45, '#f5e3c6'),
                        (0.6, '#e9ecef'), (0.75, '#d3f0dc'), (0.9, '#f0d6ee'), (1.0, '#f4f4f6')):
        sheen.setColorAt(stop, QColor(color))
    p.setBrush(QBrush(sheen))
    p.setPen(QPen(QColor('#9aa1ad'), max(1.0, 0.012 * s)))
    p.drawEllipse(center, radius, radius)
    if size >= 32:                                   # data area groove
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(255, 255, 255, 120), max(1.0, 0.01 * s)))
        p.drawEllipse(center, 0.25 * s, 0.25 * s)
    hub = QRadialGradient(center, 0.12 * s)
    hub.setColorAt(0, QColor('#d7dbe0')); hub.setColorAt(1, QColor('#9aa1ad'))
    p.setPen(Qt.PenStyle.NoPen); p.setBrush(QBrush(hub))
    p.drawEllipse(center, 0.12 * s, 0.12 * s)
    p.setBrush(QColor('#2b2f38'))
    p.drawEllipse(center, 0.045 * s, 0.045 * s)

    # green "install" badge with a down arrow
    badge = QPointF(0.74 * s, 0.74 * s)
    p.setBrush(QColor('#2e7d32')); p.setPen(QPen(QColor('#f5f5f5'), max(1.0, 0.025 * s)))
    p.drawEllipse(badge, 0.18 * s, 0.18 * s)
    arrow = QPainterPath()
    w, h = 0.09 * s, 0.11 * s
    arrow.addPolygon(QPolygonF([QPointF(badge.x() - 0.035 * s, badge.y() - h), QPointF(badge.x() + 0.035 * s, badge.y() - h),
                                QPointF(badge.x() + 0.035 * s, badge.y() - 0.01 * s), QPointF(badge.x() + w, badge.y() - 0.01 * s),
                                QPointF(badge.x(), badge.y() + 0.1 * s), QPointF(badge.x() - w, badge.y() - 0.01 * s),
                                QPointF(badge.x() - 0.035 * s, badge.y() - 0.01 * s)]))
    p.setPen(Qt.PenStyle.NoPen); p.setBrush(QColor('#ffffff'))
    p.drawPath(arrow)
    p.end()
    return image


def png_bytes(image: QImage) -> bytes:
    data = QByteArray()
    buffer = QBuffer(data); buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, 'PNG')
    return bytes(data)


def write_ico(path: Path, images: list[bytes]) -> None:
    """ICO container with PNG-compressed entries (supported since Windows Vista)."""
    header = struct.pack('<HHH', 0, 1, len(images))
    entries, offset = b'', 6 + 16 * len(images)
    for size, data in zip(SIZES, images):
        dim = 0 if size >= 256 else size
        entries += struct.pack('<BBBBHHII', dim, dim, 0, 0, 1, 32, len(data), offset)
        offset += len(data)
    path.write_bytes(header + entries + b''.join(images))


def main() -> None:
    app = QGuiApplication.instance() or QGuiApplication(sys.argv)  # noqa: F841
    ASSETS.mkdir(parents=True, exist_ok=True)
    images = [png_bytes(draw(size)) for size in SIZES]
    (ASSETS / 'icon.png').write_bytes(images[-1])
    write_ico(ASSETS / 'icon.ico', images)
    print(f'written {ASSETS / "icon.png"} and {ASSETS / "icon.ico"} ({", ".join(map(str, SIZES))} px)')


if __name__ == '__main__':
    main()
