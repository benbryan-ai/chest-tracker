"""Draws a CardData as a picture."""

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter

from sharecard import CardData
from widgets import ASH, BONE, DUSK, GOLD, GOLD_LIGHT, LINE, MINT, NIGHT, display_font

WIDTH, HEIGHT = 1200, 675


def _text_font(pixels: int, bold: bool = False) -> QFont:
    font = QFont("Segoe UI")
    font.setPixelSize(pixels)
    font.setWeight(QFont.Weight.DemiBold if bold else QFont.Weight.Normal)
    return font


def render(card: CardData) -> QImage:
    image = QImage(WIDTH, HEIGHT, QImage.Format.Format_ARGB32)
    image.fill(QColor(NIGHT))
    p = QPainter(image)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    left, right = 64, WIDTH - 64

    p.fillRect(QRectF(0, 0, WIDTH, 6), QColor(GOLD))
    p.setFont(_text_font(20, True))
    p.setPen(QColor(GOLD))
    p.drawText(QRectF(left, 36, 500, 28), Qt.AlignmentFlag.AlignLeft, "CHEST TRACKER")
    p.setFont(_text_font(22))
    p.setPen(QColor(ASH))
    p.drawText(QRectF(left, 36, right - left, 28), Qt.AlignmentFlag.AlignRight, card.range_text)

    p.setFont(display_font(44))
    p.setPen(QColor(BONE))
    heading = f"{card.name}: {card.title}" if card.name else card.title
    p.drawText(QRectF(left, 78, right - left, 56), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, heading)

    # the big number
    p.setFont(display_font(150))
    p.setPen(QColor(GOLD_LIGHT))
    p.drawText(QRectF(left, 130, 520, 160), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, f"{card.chests:,}")
    p.setFont(_text_font(26))
    p.setPen(QColor(ASH))
    p.drawText(QRectF(left + 4, 284, 520, 34), Qt.AlignmentFlag.AlignLeft, "chests searched" if card.chests != 1 else "chest searched")

    # the smaller numbers, in a 3 x 2 grid on the right
    stats = [
        (f"{card.matches:,}", "matches"),
        (f"{card.best:,}", "best match"),
        (f"{card.average:.1f}", "per match"),
        (f"{card.opened:,}", "opened"),
        (f"{card.broken:,}", "broken"),
        (f"{card.treasures:,}", "treasures"),
    ]
    grid_left, cell_w, cell_h = 640, 160, 96
    for index, (value, caption) in enumerate(stats):
        x = grid_left + (index % 3) * cell_w
        y = 150 + (index // 3) * cell_h
        p.setFont(display_font(52))
        p.setPen(QColor(BONE))
        p.drawText(QRectF(x, y, cell_w - 8, 56), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, value)
        p.setFont(_text_font(19))
        p.setPen(QColor(ASH))
        p.drawText(QRectF(x, y + 54, cell_w - 8, 26), Qt.AlignmentFlag.AlignLeft, caption)

    if card.streak > 1:
        p.setFont(_text_font(22, True))
        p.setPen(QColor(MINT))
        p.drawText(QRectF(left + 4, 322, 520, 30), Qt.AlignmentFlag.AlignLeft, f"{card.streak}-day goal streak")

    # chests per day
    chart = QRectF(left, 372, right - left, 250)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(DUSK))
    p.drawRoundedRect(chart, 12, 12)
    bars = card.bars
    top = max((n for _, n in bars), default=0)
    if bars:
        inner = chart.adjusted(20, 40, -20, -34)
        slot = inner.width() / len(bars)
        width = min(54.0, slot * 0.62)
        p.setFont(_text_font(17))
        for index, (label, value) in enumerate(bars):
            cx = inner.left() + slot * (index + 0.5)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(LINE))
            p.drawRoundedRect(QRectF(cx - width / 2, inner.bottom() - 3, width, 3), 1.5, 1.5)
            if value > 0 and top > 0:
                height = max(4.0, inner.height() * value / top)
                p.setBrush(QColor(GOLD))
                p.drawRoundedRect(QRectF(cx - width / 2, inner.bottom() - height, width, height), 4, 4)
                if len(bars) <= 16:
                    p.setPen(QColor(BONE))
                    p.drawText(QRectF(cx - slot / 2, inner.bottom() - height - 24, slot, 22),
                               Qt.AlignmentFlag.AlignCenter, str(value))
            p.setPen(QColor(ASH))
            if len(bars) <= 16 or index % 2 == 0:
                p.drawText(QRectF(cx - slot, inner.bottom() + 6, slot * 2, 24), Qt.AlignmentFlag.AlignCenter, label)
    p.setFont(_text_font(18, True))
    p.setPen(QColor(ASH))
    p.drawText(chart.adjusted(20, 10, -20, 0), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
               f"Chests per {card.unit}")
    p.end()
    return image


def to_png(card: CardData) -> bytes:
    """The card as PNG bytes, ready to save or upload."""
    from PySide6.QtCore import QBuffer, QByteArray, QIODevice

    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    render(card).save(buffer, "PNG")
    return bytes(data)
