"""QAbstractListModel subclasses for the QML UI."""

from datetime import datetime

from PySide6.QtCore import (
    QAbstractListModel,
    QModelIndex,
    Qt,
    Signal,
)


class TrackPreviewModel(QAbstractListModel):
    """List model exposing parsed track previews to QML."""

    NameRole = Qt.ItemDataRole.UserRole + 1
    TimestampRole = Qt.ItemDataRole.UserRole + 2
    IsValidRole = Qt.ItemDataRole.UserRole + 3
    ErrorRole = Qt.ItemDataRole.UserRole + 4
    TrackIndexRole = Qt.ItemDataRole.UserRole + 5

    def __init__(self, parent=None):
        super().__init__(parent)
        self._items = []

    def roleNames(self):
        return {
            self.NameRole: b"trackName",
            self.TimestampRole: b"timestamp",
            self.IsValidRole: b"isValid",
            self.ErrorRole: b"trackError",
            self.TrackIndexRole: b"trackIndex",
        }

    def rowCount(self, parent=QModelIndex()):
        return len(self._items)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or index.row() >= len(self._items):
            return None
        item = self._items[index.row()]
        if role == self.NameRole:
            return item.name
        if role == self.TimestampRole:
            return item.timestamp
        if role == self.IsValidRole:
            return item.is_valid
        if role == self.ErrorRole:
            return item.error or ""
        if role == self.TrackIndexRole:
            return index.row() + 1
        return None

    def update(self, tracks):
        self.beginResetModel()
        self._items = list(tracks)
        self.endResetModel()


class StatusLogModel(QAbstractListModel):
    """List model for pipeline status log entries."""

    MessageRole = Qt.ItemDataRole.UserRole + 1
    LevelRole = Qt.ItemDataRole.UserRole + 2
    TimeRole = Qt.ItemDataRole.UserRole + 3

    countChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._items = []

    def roleNames(self):
        return {
            self.MessageRole: b"message",
            self.LevelRole: b"level",
            self.TimeRole: b"time",
        }

    def rowCount(self, parent=QModelIndex()):
        return len(self._items)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or index.row() >= len(self._items):
            return None
        item = self._items[index.row()]
        if role == self.MessageRole:
            return item["message"]
        if role == self.LevelRole:
            return item["level"]
        if role == self.TimeRole:
            return item["time"]
        return None

    def append(self, message, level="info"):
        ts = datetime.now().strftime("%H:%M:%S")
        row = len(self._items)
        self.beginInsertRows(QModelIndex(), row, row)
        self._items.append({"message": message, "level": level, "time": ts})
        self.endInsertRows()
        self.countChanged.emit()

    def clear_all(self):
        self.beginResetModel()
        self._items.clear()
        self.endResetModel()
        self.countChanged.emit()
