"""Los íconos propios de los botones: el ecualizador, el marcador y las velocidades.

Son SVG pequeños, de 24×24 y de un solo color, escritos aquí, y se dibujan en el
color del texto de los botones del tema (con el de lo apagado, y con el del texto
sobre la selección para un botón encendido), de modo que se ven igual de bien en
un tema claro y en uno oscuro, en Linux, Windows y macOS: los temas de íconos solo
existen en Linux, y los de cada escritorio tienen otro estilo. La ventana los
vuelve a dibujar cuando cambia el tema.
"""

from __future__ import annotations

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QIcon, QPainter, QPalette, QPixmap
from PySide6.QtSvg import QSvgRenderer

_LINE = 'stroke="INK" stroke-width="1.8" fill="none" stroke-linecap="round" stroke-linejoin="round"'

SHAPES = {
    # Tres deslizadores verticales, cada uno a otra altura: el signo de siempre de un ecualizador.
    "equalizer": (f'<g {_LINE}><path d="M6 3v18M12 3v18M18 3v18"/></g>'
                  '<g fill="INK"><rect x="3.5" y="12" width="5" height="3" rx="1"/>'
                  '<rect x="9.5" y="6" width="5" height="3" rx="1"/>'
                  '<rect x="15.5" y="14" width="5" height="3" rx="1"/></g>'),
    # Una cinta de marcador con un «+»: añadir un marcador.
    "bookmark": f'<g {_LINE}><path d="M6 3h9v18l-4.5-4-4.5 4z"/><path d="M19 6v6M16 9h6"/></g>',
    # Un velocímetro: la aguja, del centro a la escala.
    "speed": (f'<g {_LINE}><path d="M4 17a8.5 8.5 0 1 1 16 0"/><path d="M12 15l4-6"/></g>'
              '<circle cx="12" cy="15" r="1.8" fill="INK"/>'),
}
SIZES = (24, 48)  # (el doble, para las pantallas de alta densidad)


def svg(name: str, color: str) -> bytes:
    """The SVG of the icon NAME drawn in COLOR (#rrggbb)."""
    body = SHAPES[name].replace("INK", color)
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">{body}</svg>'.encode()


def pixmap(name: str, color: str, size: int) -> QPixmap:
    picture = QPixmap(size, size)
    picture.fill(Qt.GlobalColor.transparent)
    painter = QPainter(picture)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    QSvgRenderer(QByteArray(svg(name, color))).render(painter, QRectF(0, 0, size, size))
    painter.end()
    return picture


def icon(name: str, palette: QPalette) -> QIcon:
    """The icon NAME in the colours of PALETTE: its button text, greyed out when disabled, and the text on the
    selection for a button that is on (it is filled with the selection's colour)."""
    roles = QPalette.ColorRole
    groups = QPalette.ColorGroup
    colors = (
        (QIcon.Mode.Normal, QIcon.State.Off, palette.color(groups.Active, roles.ButtonText)),
        (QIcon.Mode.Active, QIcon.State.Off, palette.color(groups.Active, roles.ButtonText)),
        (QIcon.Mode.Disabled, QIcon.State.Off, palette.color(groups.Disabled, roles.ButtonText)),
        (QIcon.Mode.Normal, QIcon.State.On, palette.color(groups.Active, roles.HighlightedText)),
        (QIcon.Mode.Active, QIcon.State.On, palette.color(groups.Active, roles.HighlightedText)),
        (QIcon.Mode.Disabled, QIcon.State.On, palette.color(groups.Disabled, roles.ButtonText)),
    )
    result = QIcon()
    for mode, state, color in colors:
        for size in SIZES:
            result.addPixmap(pixmap(name, color.name(), size), mode, state)
    return result
