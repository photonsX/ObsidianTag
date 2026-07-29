import hashlib
from PyQt6.QtGui import QColor, QPixmap, QPainter, QIcon
from PyQt6.QtCore import Qt

# Distinguishable palette of 16 vibrant colors tailored for dark backgrounds
COLOR_PALETTE = [
    "#4a90e2",  # Bright Blue
    "#e67e22",  # Vibrant Orange
    "#2ecc71",  # Emerald Green
    "#9b59b6",  # Deep Purple
    "#e74c3c",  # Crimson Red
    "#1abc9c",  # Teal Green
    "#f1c40f",  # Amber Gold
    "#e84393",  # Hot Pink
    "#00cec9",  # Cyan
    "#6c5ce7",  # Indigo
    "#fdcb6e",  # Sun Yellow
    "#ff7675",  # Coral
    "#55efc4",  # Mint
    "#a29bfe",  # Lavender
    "#fd79a8",  # Rose
    "#00b894"   # Turquoise
]

class ColorManager:
    @staticmethod
    def get_color(tag_name: str) -> str:
        """
        Computes a deterministic hex color for any tag name using MD5 hashing.
        Guarantees the exact same tag name always maps to the same color across sessions.
        """
        clean_name = tag_name.lstrip("#").lower().strip()
        hash_val = int(hashlib.md5(clean_name.encode("utf-8")).hexdigest(), 16)
        index = hash_val % len(COLOR_PALETTE)
        return COLOR_PALETTE[index]

    @staticmethod
    def create_color_icon(color_hex: str, size: int = 12) -> QIcon:
        """
        Generates a small circular QIcon color dot indicator.
        """
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QColor(color_hex))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(0, 0, size, size)
        painter.end()

        return QIcon(pixmap)
