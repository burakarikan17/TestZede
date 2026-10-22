from __future__ import annotations

from PySide6.QtCore import QSize
from PySide6.QtGui import QColor

from testzede.gui import app_icon


def test_icon_has_every_size_and_is_not_empty(qapp):
    icon = app_icon.make_icon()
    assert not icon.isNull()
    available = {(s.width(), s.height()) for s in icon.availableSizes()}
    assert available == {(n, n) for n in app_icon.SIZES}


def test_every_size_is_painted_with_a_transparent_corner_and_opaque_body(qapp):
    for size in app_icon.SIZES:
        image = app_icon.draw_pixmap(size).toImage()
        assert image.size() == QSize(size, size)
        assert image.pixelColor(0, 0).alpha() == 0  # yuvarlak köşe
        body = image.pixelColor(int(size * 0.5), int(size * 0.12))
        assert body.alpha() == 255 and body != QColor("#FFFFFF")  # zemin rengi, beyaz değil


def test_the_z_strokes_are_white(qapp):
    for size in app_icon.SIZES[1:]:
        image = app_icon.draw_pixmap(size).toImage()
        top_bar = image.pixelColor(int(size * 0.44), int(size * 0.21 + size * 0.05))
        diagonal = image.pixelColor(int(size * 0.44), int(size * 0.43))
        for color in (top_bar, diagonal):
            assert min(color.red(), color.green(), color.blue()) > 200, (size, color.name())


def test_set_app_identity_sets_the_window_icon_and_name(qapp):
    app_icon.set_app_identity(qapp)
    assert not qapp.windowIcon().isNull()
    assert qapp.applicationName() == "TestZede"
