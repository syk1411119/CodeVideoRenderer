"""PyQt5 GUI for CodeVideoRenderer: write code, configure effects, render a typing video."""
import sys
import traceback
from pathlib import Path

from PyQt5.QtCore import Qt, QThread, QSize, QRect, pyqtSignal
from PyQt5.QtGui import (
    QColor, QFont, QFontMetrics, QPainter, QSyntaxHighlighter, QTextCharFormat,
    QTextFormat, QKeySequence,
)
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QPlainTextEdit, QComboBox, QLineEdit, QCheckBox, QPushButton, QLabel,
    QFormLayout, QScrollArea, QSpinBox, QDoubleSpinBox, QTableWidget,
    QTableWidgetItem, QFileDialog, QMessageBox, QTextBrowser, QAbstractItemView,
    QHeaderView, QTextEdit,
)

from CodeVideoRenderer import (
    CameraFollowCursorCV, add_background_music, add_background,
    replace_background, add_sound, add_subtitles, add_lyrics, add_watermark,
)

EDITOR_BG = "#1e1e1e"
EDITOR_FG = "#d4d4d4"
EDITOR_SELECTION = "#264f78"
EDITOR_CURRENT_LINE = "#2a2d2e"
EDITOR_GUTTER = "#252526"
EDITOR_GUTTER_FG = "#858585"

LANGUAGES = [
    "python", "javascript", "typescript", "cpp", "c", "java", "go", "rust",
    "html", "css", "json", "bash", "ruby", "php", "sql", "markdown", "lua",
    "csharp", "kotlin", "swift", "r", "matlab", "yaml", "xml",
]

POSITIONS = [
    "bottom-left", "bottom-center", "bottom-right",
    "middle-left", "middle-center", "middle-right",
    "top-left", "top-center", "top-right",
]

PY_CONTROL_KEYWORDS = [
    "if", "elif", "else", "for", "while", "return", "break", "continue",
    "pass", "try", "except", "finally", "raise", "with", "yield", "assert",
    "in", "is", "not", "and", "or",
]

PY_KEYWORDS = [
    "def", "class", "import", "from", "as", "lambda", "global", "nonlocal",
    "del", "await", "async",
]

PY_BUILTINS = [
    "print", "len", "range", "str", "int", "float", "bool", "list", "dict",
    "set", "tuple", "type", "isinstance", "enumerate", "zip", "map", "filter",
    "sum", "min", "max", "abs", "round", "open", "input", "super", "self",
    "cls", "True", "False", "None",
]


class PythonHighlighter(QSyntaxHighlighter):
    def __init__(self, document):
        super().__init__(document)
        self.rules = []
        self._make_fmt(self.rules, "#CE9178", None, None, r'"[^"\\]*(\\.[^"\\]*)*"')
        self._make_fmt(self.rules, "#CE9178", None, None, r"'[^'\\]*(\\.[^'\\]*)*'")
        self._make_fmt(self.rules, "#6A9955", None, None, r"#[^\n]*")
        self._make_fmt(self.rules, "#B5CEA8", None, None, r"\b[0-9]+(\.[0-9]+)?\b")
        self._make_fmt(self.rules, "#C586C0", None, None, r"\b(" + "|".join(PY_CONTROL_KEYWORDS) + r")\b")
        self._make_fmt(self.rules, "#569CD6", None, None, r"\b(" + "|".join(PY_KEYWORDS) + r")\b")
        self._make_fmt(self.rules, "#9CDCFE", None, None, r"\b(" + "|".join(PY_BUILTINS) + r")\b")
        self._make_fmt(self.rules, "#DCDCAA", None, None, r"\bdef\s+([A-Za-z_]\w*)\b", group=1)
        self._make_fmt(self.rules, "#DCDCAA", None, None, r"\bclass\s+([A-Za-z_]\w*)\b", group=1)
        self._make_fmt(self.rules, "#DCDCAA", None, None, r"@[A-Za-z_]\w*")

        self.triple = QTextCharFormat()
        self.triple.setForeground(QColor("#CE9178"))

    def _make_fmt(self, rules, color, bold, italic, pattern, group=0):
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(color))
        if bold:
            fmt.setFontWeight(QFont.Bold)
        if italic:
            fmt.setFontItalic(True)
        from PyQt5.QtCore import QRegularExpression
        rules.append((QRegularExpression(pattern), fmt, group))

    def highlightBlock(self, text):
        from PyQt5.QtCore import QRegularExpression
        for expr, fmt, group in self.rules:
            it = expr.globalMatch(text)
            while it.hasNext():
                m = it.next()
                if group:
                    start = m.capturedStart(group)
                    length = m.capturedLength(group)
                else:
                    start = m.capturedStart()
                    length = m.capturedLength()
                if length > 0:
                    self.setFormat(start, length, fmt)

        start = self.currentBlock().position()
        end = start + len(text)
        block = self.currentBlock()
        if block.previous().isValid() and self.previousBlockState() == 1:
            self.setFormat(0, len(text), self.triple)
        triple_count = text.count('"""') + text.count("'''")
        if triple_count % 2 == 1:
            idx = max(text.rfind('"""'), text.rfind("'''"))
            if idx >= 0:
                self.setFormat(idx, len(text) - idx, self.triple)
                self.setCurrentBlockState(1)
            else:
                self.setCurrentBlockState(1)
        else:
            self.setCurrentBlockState(0)


class CodeEditor(QPlainTextEdit):
    def __init__(self):
        super().__init__()
        self.setFont(QFont("Consolas", 13))
        self.setTabStopDistance(4 * self.fontMetrics().horizontalAdvance(" "))
        self.setStyleSheet(f"""
            QPlainTextEdit {{
                background-color: {EDITOR_BG};
                color: {EDITOR_FG};
                border: none;
                selection-background-color: {EDITOR_SELECTION};
            }}
        """)
        self.highlighter = PythonHighlighter(self.document())
        self.setLineWrapMode(QPlainTextEdit.NoWrap)

        self.line_number_area = LineNumberArea(self)
        self.blockCountChanged.connect(self._update_width)
        self.updateRequest.connect(self._update_area)
        self.cursorPositionChanged.connect(self._highlight_current)
        self._update_width()
        self._highlight_current()

    def _update_width(self):
        self.setViewportMargins(self._area_width(), 0, 0, 0)

    def _area_width(self):
        digits = len(str(max(1, self.blockCount())))
        return 16 + self.fontMetrics().horizontalAdvance("9") * digits

    def _update_area(self, rect, dy):
        if dy:
            self.line_number_area.scroll(0, dy)
        else:
            self.line_number_area.update(0, rect.y(), self.line_number_area.width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self._update_width()

    def _highlight_current(self):
        extra = []
        if not self.isReadOnly():
            selection = QTextEdit.ExtraSelection()
            selection.format.setBackground(QColor(EDITOR_CURRENT_LINE))
            selection.format.setProperty(QTextFormat.FullWidthSelection, True)
            selection.cursor = self.textCursor()
            selection.cursor.clearSelection()
            extra.append(selection)
        self.setExtraSelections(extra)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        cr = self.contentsRect()
        self.line_number_area.setGeometry(QRect(cr.left(), cr.top(), self._area_width(), cr.height()))

    def line_number_area_paint(self, event):
        painter = QPainter(self.line_number_area)
        painter.fillRect(event.rect(), QColor(EDITOR_GUTTER))
        block = self.firstVisibleBlock()
        block_number = block.blockNumber()
        top = round(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + round(self.blockBoundingRect(block).height())
        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                painter.setPen(QColor(EDITOR_GUTTER_FG))
                painter.drawText(0, top, self.line_number_area.width() - 6, self.fontMetrics().height(),
                                 Qt.AlignRight, str(block_number + 1))
            block = block.next()
            top = bottom
            bottom = top + round(self.blockBoundingRect(block).height())
            block_number += 1


class LineNumberArea(QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor

    def sizeHint(self):
        return QSize(self.editor._area_width(), 0)

    def paintEvent(self, event):
        self.editor.line_number_area_paint(event)


class RenderThread(QThread):
    done = pyqtSignal(str)
    failed = pyqtSignal(str)
    status = pyqtSignal(str)

    def __init__(self, cfg, parent=None):
        super().__init__(parent)
        self.cfg = cfg

    def _find_output(self, filename):
        cwd = Path.cwd()
        candidates = sorted(cwd.rglob(filename), key=lambda p: p.stat().st_mtime, reverse=True)
        if candidates:
            return str(candidates[0])
        raise FileNotFoundError(
            f"Rendered output '{filename}' was not found under {cwd}. "
            "Check the Manim media directory."
        )

    def run(self):
        try:
            c = self.cfg
            self.status.emit("Rendering typing animation (Manim)...")
            renderer = CameraFollowCursorCV(
                code=("string", c["code"]),
                language=c["language"],
                formatter_style="vscode-dark-plus",
                video_name=c["video_name"],
                background_color=c["background_color"],
                line_highlight_color=c["line_highlight_color"],
                interval_range=(c["interval_min"], c["interval_max"]),
                camera_scale=c["camera_scale"],
                autocomplete=c["autocomplete"],
                autocomplete_wait_time=c["autocomplete_wait_time"],
                chinese_ime=c["chinese_ime"],
                ime_wait_time=c["ime_wait_time"],
                clear_code=c["clear_code"],
                clear_code_mode=c["clear_code_mode"],
                clear_code_run_time=c["clear_code_run_time"],
                end_wait_time=c["end_wait_time"],
            )
            renderer.render(output=False)

            video = self._find_output(c["video_name"] + ".mp4")

            if c.get("music"):
                self.status.emit("Mixing background music...")
                video = add_background_music(
                    video, c["music"], volume=c["music_volume"],
                    loop=c["music_loop"], mix_original=c["music_mix"],
                )

            if c.get("background_image"):
                self.status.emit("Compositing background...")
                if c.get("background_mode") == "replace":
                    video = replace_background(
                        video, c["background_image"], key_color=c["key_color"],
                        similarity=c["similarity"], blend=c["blend"], blur=c["blur"],
                    )
                else:
                    video = add_background(video, image=c["background_image"], blur=c["blur"])

            if c.get("sound"):
                self.status.emit("Adding sound effect...")
                video = add_sound(video, c["sound"], at=c["sound_at"], volume=c["sound_volume"])

            if c.get("subtitle_file"):
                self.status.emit("Burning subtitles...")
                video = add_subtitles(
                    video, c["subtitle_file"],
                    font=c.get("sub_font") or None,
                    fontsize=c.get("sub_fontsize") or None,
                    color=c.get("sub_color") or None,
                    position=c.get("sub_position") or None,
                )

            if c.get("lyrics"):
                self.status.emit("Burning lyrics...")
                video = add_lyrics(
                    video, c["lyrics"],
                    font=c.get("lyrics_font") or "",
                    fontsize=c.get("lyrics_fontsize") or 48,
                    color=c.get("lyrics_color") or "white",
                    highlight_color=c.get("lyrics_highlight") or "yellow",
                    position=c.get("lyrics_position") or "bottom-center",
                    margin=c.get("lyrics_margin") or 80,
                    karaoke=c.get("karaoke", True),
                )

            if c.get("watermark_text") or c.get("watermark_image"):
                self.status.emit("Adding watermark...")
                video = add_watermark(
                    video,
                    text=c.get("watermark_text") or None,
                    image_path=c.get("watermark_image") or None,
                    position=c.get("watermark_position") or "bottom-right",
                    fontsize=c.get("watermark_fontsize") or 24,
                    opacity=c.get("watermark_opacity") or 0.6,
                    color=c.get("watermark_color") or "white",
                )

            self.status.emit("Done.")
            self.done.emit(video)
        except Exception:
            self.failed.emit(traceback.format_exc())


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("CodeVideoRenderer Editor")
        self.resize(1280, 800)

        self.editor = CodeEditor()
        self.editor.setPlainText(
            'def fibonacci(n):\n'
            '    """Return the n-th Fibonacci number."""\n'
            '    a, b = 0, 1\n'
            '    for _ in range(n):\n'
            '        a, b = b, a + b\n'
            '    return a\n'
            '\n'
            'print(fibonacci(10))\n'
        )

        self.settings = self._build_settings()

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self.editor)
        splitter.addWidget(self.settings)
        splitter.setSizes([760, 520])

        self.status = QTextBrowser()
        self.status.setMaximumHeight(120)
        self.status.setStyleSheet(f"background-color: {EDITOR_GUTTER}; color: {EDITOR_FG}; border: none;")

        self.render_btn = QPushButton("Render Video")
        self.render_btn.setMinimumHeight(36)
        self.render_btn.clicked.connect(self._start_render)

        self.result_label = QLabel("")
        self.result_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.result_label.setStyleSheet(f"color: #9CDCFE;")

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.addWidget(splitter)
        layout.addWidget(self.status)
        bottom = QHBoxLayout()
        bottom.addWidget(self.render_btn, 1)
        bottom.addWidget(self.result_label, 3)
        layout.addLayout(bottom)
        self.setCentralWidget(central)

        self.thread = None

    def _add_row(self, form, label, widget):
        form.addRow(label, widget)
        return widget

    def _build_settings(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMinimumWidth(380)
        panel = QWidget()
        form = QFormLayout(panel)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)

        self.language = QComboBox()
        self.language.addItems(LANGUAGES)
        form.addRow("Language", self.language)

        self.video_name = QLineEdit("code_video")
        form.addRow("Video name", self.video_name)

        self.background_color = QLineEdit("#23272e")
        bg_color_btn = QPushButton("Pick")
        bg_color_btn.clicked.connect(self._pick_background_color)
        bg_row = QWidget()
        bg_lay = QHBoxLayout(bg_row)
        bg_lay.setContentsMargins(0, 0, 0, 0)
        bg_lay.addWidget(self.background_color)
        bg_lay.addWidget(bg_color_btn)
        form.addRow("Background", bg_row)

        self.line_highlight_color = QLineEdit("#2c313c")
        form.addRow("Line highlight", self.line_highlight_color)

        self.interval_min = QDoubleSpinBox()
        self.interval_min.setRange(0.01, 2.0)
        self.interval_min.setSingleStep(0.01)
        self.interval_min.setValue(0.03)
        self.interval_max = QDoubleSpinBox()
        self.interval_max.setRange(0.01, 2.0)
        self.interval_max.setSingleStep(0.01)
        self.interval_max.setValue(0.06)
        interval_row = QWidget()
        interval_lay = QHBoxLayout(interval_row)
        interval_lay.setContentsMargins(0, 0, 0, 0)
        interval_lay.addWidget(self.interval_min)
        interval_lay.addWidget(QLabel("-"))
        interval_lay.addWidget(self.interval_max)
        form.addRow("Type interval (s)", interval_row)

        self.camera_scale = QDoubleSpinBox()
        self.camera_scale.setRange(0.1, 2.0)
        self.camera_scale.setSingleStep(0.05)
        self.camera_scale.setValue(0.5)
        form.addRow("Camera scale", self.camera_scale)

        self.autocomplete = QCheckBox()
        self.autocomplete.setChecked(True)
        self.autocomplete_wait_time = QDoubleSpinBox()
        self.autocomplete_wait_time.setRange(0.1, 5.0)
        self.autocomplete_wait_time.setValue(0.6)
        form.addRow("Autocomplete", self.autocomplete)
        form.addRow("Autocomplete wait", self.autocomplete_wait_time)

        self.chinese_ime = QCheckBox()
        self.chinese_ime.setChecked(True)
        self.ime_wait_time = QDoubleSpinBox()
        self.ime_wait_time.setRange(0.1, 5.0)
        self.ime_wait_time.setValue(0.6)
        form.addRow("Chinese IME", self.chinese_ime)
        form.addRow("IME wait", self.ime_wait_time)

        self.clear_code = QCheckBox()
        self.clear_code_mode = QComboBox()
        self.clear_code_mode.addItems(["backspace", "fade"])
        self.clear_code_run_time = QDoubleSpinBox()
        self.clear_code_run_time.setRange(0.1, 10.0)
        self.clear_code_run_time.setValue(1.0)
        form.addRow("Clear code", self.clear_code)
        form.addRow("Clear mode", self.clear_code_mode)
        form.addRow("Clear time", self.clear_code_run_time)

        self.end_wait_time = QDoubleSpinBox()
        self.end_wait_time.setRange(0.0, 10.0)
        self.end_wait_time.setValue(1.0)
        form.addRow("End wait (s)", self.end_wait_time)

        form.addRow(QLabel("<b>Music</b>"), QWidget())

        self.music = QLineEdit()
        music_btn = QPushButton("Browse")
        music_btn.clicked.connect(lambda: self._browse_file(self.music, "Audio (*.mp3 *.wav *.m4a *.aac)"))
        music_row = self._file_row(self.music, music_btn)
        form.addRow("Music file", music_row)

        self.music_volume = QDoubleSpinBox()
        self.music_volume.setRange(0.0, 2.0)
        self.music_volume.setSingleStep(0.05)
        self.music_volume.setValue(0.3)
        form.addRow("Music volume", self.music_volume)
        self.music_loop = QCheckBox()
        self.music_loop.setChecked(True)
        self.music_mix = QCheckBox()
        self.music_mix.setChecked(True)
        form.addRow("Loop music", self.music_loop)
        form.addRow("Mix with video audio", self.music_mix)

        form.addRow(QLabel("<b>Background</b>"), QWidget())

        self.background_image = QLineEdit()
        bg_img_btn = QPushButton("Browse")
        bg_img_btn.clicked.connect(lambda: self._browse_file(self.background_image, "Images (*.png *.jpg *.jpeg *.webp)"))
        form.addRow("Background image", self._file_row(self.background_image, bg_img_btn))

        self.background_mode = QComboBox()
        self.background_mode.addItems(["overlay (transparent code)", "replace (chroma key)"])
        form.addRow("Mode", self.background_mode)

        self.key_color = QLineEdit("0x00FF00")
        form.addRow("Key color", self.key_color)
        self.similarity = QDoubleSpinBox()
        self.similarity.setRange(0.0, 1.0)
        self.similarity.setSingleStep(0.01)
        self.similarity.setValue(0.3)
        form.addRow("Similarity", self.similarity)
        self.blend = QDoubleSpinBox()
        self.blend.setRange(0.0, 1.0)
        self.blend.setSingleStep(0.01)
        self.blend.setValue(0.1)
        form.addRow("Blend", self.blend)
        self.blur = QDoubleSpinBox()
        self.blur.setRange(0.0, 50.0)
        self.blur.setValue(0.0)
        form.addRow("Blur background", self.blur)

        form.addRow(QLabel("<b>Sound effect</b>"), QWidget())

        self.sound = QLineEdit()
        sound_btn = QPushButton("Browse")
        sound_btn.clicked.connect(lambda: self._browse_file(self.sound, "Audio (*.mp3 *.wav *.m4a *.aac)"))
        form.addRow("Sound file", self._file_row(self.sound, sound_btn))
        self.sound_at = QDoubleSpinBox()
        self.sound_at.setRange(0.0, 3600.0)
        self.sound_at.setValue(0.0)
        form.addRow("Sound at (s)", self.sound_at)
        self.sound_volume = QDoubleSpinBox()
        self.sound_volume.setRange(0.0, 2.0)
        self.sound_volume.setSingleStep(0.05)
        self.sound_volume.setValue(1.0)
        form.addRow("Sound volume", self.sound_volume)

        form.addRow(QLabel("<b>Subtitle file</b>"), QWidget())

        self.subtitle_file = QLineEdit()
        sub_btn = QPushButton("Browse")
        sub_btn.clicked.connect(lambda: self._browse_file(self.subtitle_file, "Subtitles (*.srt *.ass *.vtt)"))
        form.addRow("Subtitle file", self._file_row(self.subtitle_file, sub_btn))
        self.sub_font = QLineEdit("")
        form.addRow("Subtitle font", self.sub_font)
        self.sub_fontsize = QSpinBox()
        self.sub_fontsize.setRange(1, 200)
        self.sub_fontsize.setValue(24)
        form.addRow("Subtitle size", self.sub_fontsize)
        self.sub_color = QLineEdit("white")
        form.addRow("Subtitle color", self.sub_color)
        self.sub_position = QComboBox()
        self.sub_position.addItems(POSITIONS)
        self.sub_position.setCurrentText("bottom-center")
        form.addRow("Subtitle position", self.sub_position)

        form.addRow(QLabel("<b>Lyrics / music subtitles</b>"), QWidget())

        self.lyrics_font = QLineEdit("")
        form.addRow("Lyrics font", self.lyrics_font)
        self.lyrics_fontsize = QSpinBox()
        self.lyrics_fontsize.setRange(1, 300)
        self.lyrics_fontsize.setValue(48)
        form.addRow("Lyrics size", self.lyrics_fontsize)
        self.lyrics_color = QLineEdit("white")
        form.addRow("Lyrics color", self.lyrics_color)
        self.lyrics_highlight = QLineEdit("yellow")
        form.addRow("Highlight color", self.lyrics_highlight)
        self.lyrics_position = QComboBox()
        self.lyrics_position.addItems(POSITIONS)
        self.lyrics_position.setCurrentText("bottom-center")
        form.addRow("Lyrics position", self.lyrics_position)
        self.karaoke = QCheckBox()
        self.karaoke.setChecked(True)
        form.addRow("Karaoke highlight", self.karaoke)

        self.lyrics_table = QTableWidget(0, 3)
        self.lyrics_table.setHorizontalHeaderLabels(["Start (s)", "End (s)", "Text"])
        self.lyrics_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.lyrics_table.setMinimumHeight(120)
        form.addRow("Lyrics", self.lyrics_table)

        lyrics_btn_row = QWidget()
        lyrics_btn_lay = QHBoxLayout(lyrics_btn_row)
        lyrics_btn_lay.setContentsMargins(0, 0, 0, 0)
        add_lyrics_btn = QPushButton("+ Row")
        add_lyrics_btn.clicked.connect(self._add_lyric_row)
        del_lyrics_btn = QPushButton("- Row")
        del_lyrics_btn.clicked.connect(self._del_lyric_row)
        lyrics_btn_lay.addWidget(add_lyrics_btn)
        lyrics_btn_lay.addWidget(del_lyrics_btn)
        lyrics_btn_lay.addStretch()
        form.addRow("", lyrics_btn_row)

        form.addRow(QLabel("<b>Watermark</b>"), QWidget())

        self.watermark_text = QLineEdit("")
        form.addRow("Watermark text", self.watermark_text)
        self.watermark_image = QLineEdit()
        wm_btn = QPushButton("Browse")
        wm_btn.clicked.connect(lambda: self._browse_file(self.watermark_image, "Images (*.png *.jpg *.jpeg *.webp)"))
        form.addRow("Watermark image", self._file_row(self.watermark_image, wm_btn))
        self.watermark_position = QComboBox()
        self.watermark_position.addItems(POSITIONS)
        self.watermark_position.setCurrentText("bottom-right")
        form.addRow("Watermark position", self.watermark_position)
        self.watermark_fontsize = QSpinBox()
        self.watermark_fontsize.setRange(1, 200)
        self.watermark_fontsize.setValue(24)
        form.addRow("Watermark size", self.watermark_fontsize)
        self.watermark_opacity = QDoubleSpinBox()
        self.watermark_opacity.setRange(0.05, 1.0)
        self.watermark_opacity.setSingleStep(0.05)
        self.watermark_opacity.setValue(0.6)
        form.addRow("Watermark opacity", self.watermark_opacity)
        self.watermark_color = QLineEdit("white")
        form.addRow("Watermark color", self.watermark_color)

        scroll.setWidget(panel)
        return scroll

    def _file_row(self, line_edit, browse_btn):
        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(line_edit)
        lay.addWidget(browse_btn)
        return w

    def _browse_file(self, line_edit, pattern):
        path, _ = QFileDialog.getOpenFileName(self, "Select file", "", pattern)
        if path:
            line_edit.setText(path)

    def _pick_background_color(self):
        color = QColorDialog.getColor(QColor(self.background_color.text()), self, "Background color")
        if color.isValid():
            self.background_color.setText(color.name())

    def _add_lyric_row(self):
        row = self.lyrics_table.rowCount()
        self.lyrics_table.insertRow(row)
        self.lyrics_table.setItem(row, 0, QTableWidgetItem("0.0"))
        self.lyrics_table.setItem(row, 1, QTableWidgetItem("3.0"))
        self.lyrics_table.setItem(row, 2, QTableWidgetItem(""))

    def _del_lyric_row(self):
        row = self.lyrics_table.currentRow()
        if row >= 0:
            self.lyrics_table.removeRow(row)

    def _collect_lyrics(self):
        lyrics = []
        for row in range(self.lyrics_table.rowCount()):
            try:
                start = float(self.lyrics_table.item(row, 0).text())
                end = float(self.lyrics_table.item(row, 1).text())
            except (ValueError, AttributeError):
                continue
            text_item = self.lyrics_table.item(row, 2)
            text = text_item.text().strip() if text_item else ""
            if text and end > start:
                lyrics.append((start, end, text))
        return lyrics

    def _start_render(self):
        if self.thread is not None and self.thread.isRunning():
            return
        code = self.editor.toPlainText()
        if not code.strip():
            QMessageBox.warning(self, "Empty code", "Write some code first.")
            return
        video_name = self.video_name.text().strip() or "code_video"

        cfg = {
            "code": code,
            "language": self.language.currentText(),
            "video_name": video_name,
            "background_color": self.background_color.text().strip() or "#23272e",
            "line_highlight_color": self.line_highlight_color.text().strip() or "#2c313c",
            "interval_min": self.interval_min.value(),
            "interval_max": self.interval_max.value(),
            "camera_scale": self.camera_scale.value(),
            "autocomplete": self.autocomplete.isChecked(),
            "autocomplete_wait_time": self.autocomplete_wait_time.value(),
            "chinese_ime": self.chinese_ime.isChecked(),
            "ime_wait_time": self.ime_wait_time.value(),
            "clear_code": self.clear_code.isChecked(),
            "clear_code_mode": self.clear_code_mode.currentText(),
            "clear_code_run_time": self.clear_code_run_time.value(),
            "end_wait_time": self.end_wait_time.value(),
            "music": self.music.text().strip() or None,
            "music_volume": self.music_volume.value(),
            "music_loop": self.music_loop.isChecked(),
            "music_mix": self.music_mix.isChecked(),
            "background_image": self.background_image.text().strip() or None,
            "background_mode": "replace" if self.background_mode.currentIndex() == 1 else "overlay",
            "key_color": self.key_color.text().strip() or "0x00FF00",
            "similarity": self.similarity.value(),
            "blend": self.blend.value(),
            "blur": self.blur.value(),
            "sound": self.sound.text().strip() or None,
            "sound_at": self.sound_at.value(),
            "sound_volume": self.sound_volume.value(),
            "subtitle_file": self.subtitle_file.text().strip() or None,
            "sub_font": self.sub_font.text().strip() or None,
            "sub_fontsize": self.sub_fontsize.value(),
            "sub_color": self.sub_color.text().strip() or None,
            "sub_position": self.sub_position.currentText(),
            "lyrics_font": self.lyrics_font.text().strip() or None,
            "lyrics_fontsize": self.lyrics_fontsize.value(),
            "lyrics_color": self.lyrics_color.text().strip() or "white",
            "lyrics_highlight": self.lyrics_highlight.text().strip() or "yellow",
            "lyrics_position": self.lyrics_position.currentText(),
            "karaoke": self.karaoke.isChecked(),
            "lyrics": self._collect_lyrics(),
            "watermark_text": self.watermark_text.text().strip() or None,
            "watermark_image": self.watermark_image.text().strip() or None,
            "watermark_position": self.watermark_position.currentText(),
            "watermark_fontsize": self.watermark_fontsize.value(),
            "watermark_opacity": self.watermark_opacity.value(),
            "watermark_color": self.watermark_color.text().strip() or "white",
        }

        self.render_btn.setEnabled(False)
        self.status.clear()
        self.result_label.setText("")
        self.thread = RenderThread(cfg)
        self.thread.status.connect(lambda msg: self.status.append(msg))
        self.thread.done.connect(self._on_done)
        self.thread.failed.connect(self._on_failed)
        self.thread.start()

    def _on_done(self, path):
        self.render_btn.setEnabled(True)
        self.result_label.setText(f"Ready: {path}")

    def _on_failed(self, err):
        self.render_btn.setEnabled(True)
        self.status.append("ERROR:\n" + err)


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(f"""
        QWidget {{ background-color: {EDITOR_BG}; color: {EDITOR_FG}; font-size: 13px; }}
        QLabel {{ background: transparent; }}
        QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QTableWidget {{
            background-color: {EDITOR_GUTTER}; color: {EDITOR_FG};
            border: 1px solid #3c3c3c; border-radius: 3px; padding: 3px;
        }}
        QPushButton {{
            background-color: #0e639c; color: white; border: none;
            border-radius: 3px; padding: 6px 12px;
        }}
        QPushButton:hover {{ background-color: #1177bb; }}
        QPushButton:disabled {{ background-color: #3c3c3c; color: #808080; }}
        QCheckBox {{ background: transparent; }}
        QScrollArea {{ border: none; }}
        QHeaderView::section {{ background-color: {EDITOR_GUTTER}; color: {EDITOR_FG}; border: 1px solid #3c3c3c; }}
    """)
    win = MainWindow()
    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
