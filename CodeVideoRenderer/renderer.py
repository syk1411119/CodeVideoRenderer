from __future__ import annotations # for Sphinx typehints
from manim import VGroup, Code, SurroundingRectangle, RoundedRectangle, Rectangle, Line, MovingCameraScene, rate_functions, RendererType, config, WHITE, GREY, UP, DOWN, LEFT, RIGHT, register_font, FadeOut, FadeIn, Text
from manim.typing import Point3D
from pathlib import Path
from copy import copy
from typing import Literal, Union, Tuple, List, Dict
from timeit import timeit
from rich import traceback
from dataclasses import dataclass
from typeguard import typechecked
import numpy as np
import random, inspect, os

from .config import *
from .typing import *
from .utils import *
from .vscode_theme import register_vscode, resolve_language, STYLE_NAME
from .ime import is_cjk, get_ime

traceback.install()
register_vscode()

# VS Code-style code completion: trigger keyword -> candidate suggestions (label, kind, detail)
AUTOCOMPLETE_SUGGESTIONS: Dict[str, List[Tuple[str, str, str]]] = {
    "def": [
        ("def", "keyword", "keyword"),
        ("def name():", "snippet", "function"),
        ("def name(args):", "snippet", "function"),
        ("def __init__(self):", "method", "method"),
    ],
    "class": [
        ("class", "keyword", "keyword"),
        ("class Name:", "snippet", "class"),
        ("class Name(Base):", "snippet", "class"),
        ("class Meta:", "snippet", "class"),
    ],
    "import": [
        ("import os", "module", "module"),
        ("import sys", "module", "module"),
        ("import numpy as np", "module", "module"),
        ("import re", "module", "module"),
    ],
    "from": [
        ("from module import name", "snippet", "import"),
        ("from . import name", "module", "import"),
        ("from typing import List", "module", "module"),
    ],
    "for": [
        ("for i in range(n):", "snippet", "loop"),
        ("for item in iterable:", "snippet", "loop"),
        ("for k, v in d.items():", "snippet", "loop"),
    ],
    "if": [
        ("if condition:", "snippet", "conditional"),
        ("if x is None:", "snippet", "conditional"),
        ("if __name__ == '__main__':", "snippet", "main"),
    ],
    "return": [
        ("return", "keyword", "keyword"),
        ("return value", "snippet", "statement"),
        ("return None", "snippet", "statement"),
        ("return self", "snippet", "statement"),
    ],
    "print": [
        ("print", "function", "built-in"),
        ("print(*args)", "function", "built-in"),
        ("print(f'...')", "function", "built-in"),
    ],
    "while": [
        ("while condition:", "snippet", "loop"),
        ("while True:", "snippet", "loop"),
    ],
    "try": [
        ("try:", "snippet", "exception"),
        ("try: ... except Exception as e:", "snippet", "exception"),
    ],
    "with": [
        ("with open(...) as f:", "snippet", "context manager"),
        ("with contextlib.suppress(...):", "snippet", "context manager"),
    ],
}

# VS Code completion icons: kind -> (glyph, color). Glyphs/colors mirror VS Code's Codicon + symbolIcon colors
AUTOCOMPLETE_KIND_STYLE: Dict[str, Tuple[str, str]] = {
    "keyword": ("⚿", "#569CD6"),     # blue key icon
    "function": ("ƒ", "#B180D7"),     # purple ƒ
    "method": ("ƒ", "#B180D7"),       # purple ƒ
    "class": ("▣", "#EE9D28"),        # orange square
    "module": ("▣", "#75BEFF"),       # blue square
    "snippet": ("➤", "#75BEFF"),      # blue arrow
    "variable": ("●", "#75BEFF"),     # blue dot
    "string": ("§", "#CE9178"),       # orange §
    "number": ("≡", "#B5CEA8"),       # green ≡
    "constant": ("≡", "#B5CEA8"),
    "property": ("●", "#75BEFF"),
}

# Completion box colors from VS Code's dark theme (consistent with Dark+)
_SUGGEST_BG = "#252526"
_SUGGEST_BORDER = "#454545"
_SUGGEST_FG = "#D4D4D4"
_SUGGEST_DETAIL = "#808080"
_SUGGEST_SELECTED_BG = "#04395E"

class CameraFollowCursorCV:
    """
    CameraFollowCursorCV is a class designed to create animated videos that simulate the process of typing code. It animates code line by line and character by
    character while smoothly moving the camera to follow the cursor, creating a professional-looking coding demonstration.

    Args:
        code (Union[Tuple[Literal['string'], str], Tuple[Literal['file'], StrPath]]): The code to be animated. **When using a string**, provide a tuple with the first element as ``'string'`` and the second element as the code string. **When using a file**, provide a tuple with the first element as ``'file'`` and the second element as the file path.
        language (PygmentsLanguage): The programming language of the code.
        formatter_style (PygmentsFormatterStyle): The style for syntax highlighting. Defaults to ``"vscode-dark-plus"`` (VS Code Dark+ colors).
        line_spacing (Union[float, int]): The line spacing for the code. Defaults to :data:`~.DEFAULT_LINE_SPACING`.
        interval_range (Tuple[Union[float, int], Union[float, int]]): The range of typing intervals between characters. Defaults to (:data:`~.DEFAULT_TYPE_INTERVAL`, :data:`~.DEFAULT_TYPE_INTERVAL`).
        camera_scale (Union[float, int]): The scale factor for the camera. Defaults to 0.5.
        video_name (str): The name of the output video file. Defaults to ``"CameraFollowCursorCV"``.
        renderer (Literal['cairo', 'opengl']): The renderer to use for video rendering. Defaults to ``'cairo'``.
        clear_code (bool): Whether to clear the code off screen after the typing animation finishes. Defaults to ``False``.
        clear_code_mode (Literal['fade', 'backspace']): How to clear the code. ``'backspace'`` deletes character by character (like pressing backspace); ``'fade'`` fades the whole block out at once. Defaults to ``'backspace'``.
        clear_code_run_time (float): Duration (seconds) of the whole-block fade (``clear_code_mode='fade'``) or the final fade of line numbers/cursor (backspace mode). Defaults to 1.0.
        clear_code_interval (float): Time between deleting each character in backspace mode — controls the deletion speed. Defaults to 0.03.
        autocomplete (bool): Whether to show VS Code-style completion popups when a keyword (``def``, ``import``, ``class``, …) is typed. Defaults to ``False``.
        autocomplete_wait_time (float): How long each completion popup stays on screen (seconds). Defaults to 0.6.
        chinese_ime (bool): Whether to show a Chinese IME-style candidate box (pinyin + candidates) when Chinese characters are typed. Defaults to ``False``.
        ime_wait_time (float): How long each IME candidate box stays on screen (seconds). Defaults to 0.6.
        background_color (str): The scene background color. Defaults to ``"#000000"``.
        line_highlight_color (str): Fill color of the rectangle highlighting the line being typed. Defaults to ``"#333333"``.
        end_wait_time (float): How long to pause on the final frame after typing (seconds). Defaults to 1.0.
    """
    __all__ = ["render"]

    @typechecked
    def __init__(self,
        code: Union[Tuple[Literal['string'], str], Tuple[Literal['file'], StrPath]],
        language: PygmentsLanguage,
        formatter_style: PygmentsFormatterStyle = "vscode-dark-plus",
        line_spacing: Union[float, int] = DEFAULT_LINE_SPACING,
        interval_range: Tuple[Union[float, int], Union[float, int]] = (DEFAULT_TYPE_INTERVAL, DEFAULT_TYPE_INTERVAL),
        camera_scale: Union[float, int] = 0.5,
        video_name: str = "CameraFollowCursorCV",
        renderer: Literal['cairo', 'opengl'] = 'cairo',
        clear_code: bool = False,
        clear_code_mode: Literal['fade', 'backspace'] = 'backspace',
        clear_code_run_time: float = 1.0,
        clear_code_interval: float = 0.03,
        autocomplete: bool = False,
        autocomplete_wait_time: float = 0.6,
        chinese_ime: bool = False,
        ime_wait_time: float = 0.6,
        background_color: str = "#000000",
        line_highlight_color: str = "#333333",
        end_wait_time: float = 1.0,
    ):
        # ----- Video name -----
        if not video_name:
            raise ValueError("video_name must be provided")

        # ----- Code input -----
        if code[0] == 'string':
            self.code_str = code[1].expandtabs(tabsize=DEFAULT_TAB_WIDTH)
            if not all(char not in NOT_AVAILABLE_CHARACTERS for char in self.code_str):
                raise ValueError("'code_string' contains invalid characters")
        elif code[0] == 'file':
            try:
                self.code_str = Path(code[1]).read_text(encoding="utf-8").expandtabs(tabsize=DEFAULT_TAB_WIDTH)
                if not all(char not in NOT_AVAILABLE_CHARACTERS for char in self.code_str):
                    raise ValueError(f"'{code[1]}' contains invalid characters")
            except UnicodeDecodeError:
                raise ValueError(f"Failed to decode '{code[1]}' with UTF-8 encoding") from None

        # ----- Line spacing -----
        if line_spacing <= 0:
            raise ValueError("line_spacing must be greater than 0")

        # ----- Typing interval -----
        shortest_possible_duration = round(1/config.frame_rate, 7)
        if not all(interval >= shortest_possible_duration for interval in interval_range):
            raise ValueError(f"interval_range must be greater than or equal to {shortest_possible_duration}")
        del shortest_possible_duration
        if interval_range[0] > interval_range[1]:
            raise ValueError("The first term of interval_range must be less than or equal to the second term")

        # ----- Deletion speed -----
        if clear_code_interval <= 0:
            raise ValueError("clear_code_interval must be greater than 0")

        # Parameters
        global Parameters
        @dataclass
        class Parameters:
            code: Union[Tuple[Literal['string'], str], Tuple[Literal['file'], StrPath]]
            language: PygmentsLanguage
            formatter_style: PygmentsFormatterStyle
            line_spacing: Union[float, int]
            interval_range: Tuple[Union[float, int], Union[float, int]]
            camera_scale: Union[float, int]
            video_name: str
            renderer: Literal['cairo', 'opengl']
            clear_code: bool
            clear_code_mode: Literal['fade', 'backspace']
            clear_code_run_time: float
            clear_code_interval: float
            autocomplete: bool
            autocomplete_wait_time: float
            chinese_ime: bool
            ime_wait_time: float
            background_color: str
            line_highlight_color: str
            end_wait_time: float
        Parameters.code = code
        Parameters.language = language
        Parameters.formatter_style = formatter_style
        Parameters.line_spacing = line_spacing
        Parameters.interval_range = interval_range
        Parameters.camera_scale = camera_scale
        Parameters.video_name = video_name
        Parameters.renderer = renderer
        Parameters.clear_code = clear_code
        Parameters.clear_code_mode = clear_code_mode
        Parameters.clear_code_run_time = clear_code_run_time
        Parameters.clear_code_interval = clear_code_interval
        Parameters.autocomplete = autocomplete
        Parameters.autocomplete_wait_time = autocomplete_wait_time
        Parameters.chinese_ime = chinese_ime
        Parameters.ime_wait_time = ime_wait_time
        Parameters.background_color = background_color
        Parameters.line_highlight_color = line_highlight_color
        Parameters.end_wait_time = end_wait_time

        # Other
        self.code_str = stripEmptyLines(self.code_str)
        self.space_positions = findSpacePositions(self.code_str)
        self.empty_line_positions = findEmptyLinePositions(self.code_str)
        self.code_str = replaceMiddleSpacesWithOccupyCharacter("\n".join([" " if line == "" else line for line in self.code_str.splitlines()]))
        self.code_str_lines = self.code_str.splitlines()
        self.origin_config = {
            'disable_caching': config.disable_caching,
            'renderer': config.renderer,
            'background_color': config.background_color
        }
        config.disable_caching = True
        config.renderer = renderer
        config.background_color = background_color
        self.scene = self._create_scene()

    def _create_scene(self):
        """Create manim scene to animate code rendering."""
        class CameraFollowCursorCVScene(MovingCameraScene):

            def construct(scene):
                """Build the code animation scene."""

                # Initialize the cursor
                cursor = RoundedRectangle(
                    height=DEFAULT_CURSOR_HEIGHT,
                    width=DEFAULT_CURSOR_WIDTH,
                    corner_radius=DEFAULT_CURSOR_WIDTH / 2,
                    fill_opacity=1,
                    fill_color=WHITE,
                    color=WHITE
                )

                # Create the code block
                with register_font(os.path.join(os.path.dirname(__file__), 'fonts/CodeVideoRendererFont.ttf')):
                    line_number_mobject, code_mobject = Code(
                        code_string=self.code_str + f"\n{(max([len(line.rstrip()) for line in self.code_str_lines])*2)*' ' + OCCUPY_CHARACTER}",
                        language=resolve_language(Parameters.language),
                        formatter_style=Parameters.formatter_style,
                        paragraph_config={
                            'font': 'CodeVideoRendererFont',
                            'line_spacing': Parameters.line_spacing
                        }
                    ).submobjects[1:3]
                line_number_mobject.set_color(GREY)

                total_line_numbers = len(self.code_str_lines)
                total_char_numbers = len(''.join(line.strip() for line in self.code_str_lines))

                # Adjust code alignment (manim built-in bug)
                offset_lines = []
                for line_index, line in enumerate(self.code_str_lines):
                    if all(check in "acegmnopqrsuvwxyz+,-.:;<=>_~ " for check in line):
                        if line_index == 0:
                            code_mobject.shift(DOWN*CODE_OFFSET)
                        offset_lines.append(line_index)
                del line_index, line

                # Create the code-line rectangle
                code_line_rectangle = SurroundingRectangle(
                    VGroup(code_mobject[-1], line_number_mobject[-1]), # type: ignore
                    color=Parameters.line_highlight_color,
                    fill_opacity=1,
                    stroke_width=0
                ).set_y(code_mobject[0].get_y())
                # Handle the code_line_rectangle offset when the first line is offset
                if 0 in offset_lines:
                    code_line_rectangle.shift(UP*CODE_OFFSET/2)

                # Initialize the cursor position
                cursor.align_to(code_mobject[0], LEFT).set_y(code_line_rectangle.get_y())

                # Adapt for opengl
                if config.renderer == RendererType.OPENGL:
                    scene.camera.frame = scene.camera # type: ignore

                # Entrance animation
                target_center = cursor.get_center()
                start_center = target_center + UP * 3
                scene.camera.frame.scale(Parameters.camera_scale).move_to(start_center) # type: ignore
                scene.add(code_line_rectangle, line_number_mobject[0].set_color(WHITE), cursor)

                scene.play(
                    scene.camera.frame.animate.move_to(target_center), # type: ignore[reportArgumentType, reportAttributeAccessIssue]
                    run_time=1,
                    rate_func=rate_functions.ease_out_cubic
                )

                # Define fixed animations
                scene.Animation_list: List[Dict[str, Union[Point3D, float]]] = []
                def linebreakAnimation():
                    scene.Animation_list.append({"move_to": cursor.get_center()})

                camera_scale = Parameters.camera_scale
                def JUDGE_cameraScaleAnimation():
                    nonlocal camera_scale
                    distance = (scene.camera.frame.get_x() - line_number_mobject.get_x()) / 14.22 # type: ignore
                    if distance > camera_scale:
                        scene.Animation_list.append({"scale": distance/camera_scale})
                        camera_scale = distance

                def playAnimation(**kwargs):
                    if scene.Animation_list:
                        cameraAnimation = scene.camera.frame.animate # type: ignore

                        for anim in scene.Animation_list:
                            if "move_to" in anim:
                                cameraAnimation.move_to(anim["move_to"])
                            elif "scale" in anim:
                                cameraAnimation.scale(anim["scale"])

                        scene.play(cameraAnimation, **kwargs)
                        scene.Animation_list.clear()
                        del cameraAnimation

                # Record all typed characters for backspace deletion
                typed_mobjects: List = []

                font_path = os.path.join(os.path.dirname(__file__), 'fonts/CodeVideoRendererFont.ttf')

                def showAutocomplete(keyword: str):
                    """Show a VS Code-style IntelliSense completion box: icon + label + detail + selection highlight."""
                    suggestions = AUTOCOMPLETE_SUGGESTIONS.get(keyword, [])[:5]
                    if not suggestions:
                        return
                    with register_font(font_path):
                        rows = []
                        for label, kind, detail in suggestions:
                            glyph, color = AUTOCOMPLETE_KIND_STYLE.get(kind, ("▣", "#75BEFF"))
                            icon = Text(glyph, font="CodeVideoRendererFont", font_size=16, color=color)
                            label_t = Text(label, font="CodeVideoRendererFont", font_size=20, color=_SUGGEST_FG)
                            detail_t = Text(detail, font="CodeVideoRendererFont", font_size=16, color=_SUGGEST_DETAIL)
                            rows.append((icon, label_t, detail_t))

                    # Compact, row-aligned layout: icon + label on the left, detail right-aligned.
                    pad_x, pad_y = 0.22, 0.15
                    icon_gap, detail_gap, row_buff = 0.12, 0.5, 0.12
                    lefts = [VGroup(ic, lb).arrange(RIGHT, aligned_edge=DOWN, buff=icon_gap) for ic, lb, _ in rows]
                    details = [dt for _, _, dt in rows]

                    max_left_w = max(l.width for l in lefts)
                    max_detail_w = max(d.width for d in details)
                    row_h = max(l.height for l in lefts)
                    row_step = row_h + row_buff

                    box = RoundedRectangle(
                        width=max_left_w + detail_gap + max_detail_w + 2 * pad_x,
                        height=row_h * len(rows) + row_buff * (len(rows) - 1) + 2 * pad_y,
                        corner_radius=0.06,
                        color=_SUGGEST_BORDER, fill_color=_SUGGEST_BG, fill_opacity=1, stroke_width=1,
                    )

                    content_left = box.get_left()[0] + pad_x
                    content_right = box.get_right()[0] - pad_x
                    top_y = box.get_top()[1] - pad_y
                    for i, (left, detail_t) in enumerate(zip(lefts, details)):
                        row_y = top_y - row_step * i - row_h / 2
                        left.move_to([content_left + left.width / 2, row_y, 0])
                        detail_t.move_to([content_right - detail_t.width / 2, row_y, 0])

                    # Highlight the whole row of the first (selected) item
                    sel = Rectangle(
                        width=box.width - 0.1, height=row_step,
                        color=_SUGGEST_SELECTED_BG, fill_opacity=1, stroke_width=0,
                    ).move_to([box.get_x(), lefts[0].get_y(), 0])

                    popup = VGroup(box, sel, *lefts, *details)
                    popup.next_to(cursor, DOWN, buff=0.3)

                    scene.add(popup)
                    scene.play(FadeIn(popup), run_time=0.12)
                    scene.wait(Parameters.autocomplete_wait_time)
                    scene.play(FadeOut(popup), run_time=0.12)

                def showIme(pinyin: str, candidates):
                    """Show a Chinese IME candidate box: pinyin (hyphen-separated) + divider + candidates."""
                    if not candidates:
                        return
                    with register_font(font_path):
                        py_t = Text(pinyin, font="CodeVideoRendererFont", font_size=18, color="#9CDCFE")
                        cands = [Text(c, font="CodeVideoRendererFont", font_size=20, color="#808080") for c in candidates]
                    cands[0].set_color(_SUGGEST_FG)

                    cand_row = VGroup(*cands).arrange(RIGHT, aligned_edge=UP, buff=0.22)
                    inner_w = max(py_t.get_width(), cand_row.get_width())
                    bar = Rectangle(width=inner_w, height=0.03, fill_color=_SUGGEST_BORDER, fill_opacity=1, stroke_width=0)
                    content = VGroup(py_t, bar, cand_row).arrange(DOWN, aligned_edge=LEFT, buff=0.12)

                    first_hl = Rectangle(
                        width=cands[0].width + 0.18, height=cands[0].height + 0.12,
                        color=_SUGGEST_SELECTED_BG, fill_opacity=1, stroke_width=0,
                    ).move_to(cands[0])

                    box = RoundedRectangle(
                        width=inner_w + 0.44, height=content.height + 0.3,
                        corner_radius=0.06,
                        color=_SUGGEST_BORDER, fill_color=_SUGGEST_BG, fill_opacity=1, stroke_width=1,
                    )
                    popup = VGroup(box, first_hl, py_t, bar, cand_row)
                    popup.next_to(cursor, DOWN, buff=0.3)

                    scene.add(popup)
                    scene.play(FadeIn(popup), run_time=0.12)
                    scene.wait(Parameters.ime_wait_time)
                    scene.play(FadeOut(popup), run_time=0.12)

                with copy(DefaultProgressBar(self.output)) as progress:
                    total_progress = progress.add_task(description="[yellow]Total[/yellow]", total=total_char_numbers)

                    # Iterate over the code lines
                    for line in range(total_line_numbers):

                        line_number_mobject.set_color(GREY)
                        line_number_mobject[line].set_color(WHITE)

                        char_num = len(self.code_str_lines[line].strip())
                        current_line_progress = progress.add_task(description=f"[green]Line {line+1}[/green]", total=char_num)

                        code_line_rectangle.set_y(code_mobject[line].get_y())
                        # Handle the code_line_rectangle offset when the line is offset
                        if line in offset_lines:
                            code_line_rectangle.shift(UP*CODE_OFFSET/2)
                        scene.add(line_number_mobject[line])

                        cursor.align_to(code_mobject[line], LEFT).set_y(code_line_rectangle.get_y())
                        if line != 0:
                            linebreakAnimation()
                        JUDGE_cameraScaleAnimation()
                        playAnimation(run_time=DEFAULT_LINE_BREAK_RUN_TIME)

                        # Skip empty lines
                        if line in self.empty_line_positions:
                            progress.remove_task(current_line_progress)
                            continue

                        first_non_space_index = len(self.code_str_lines[line]) - len(self.code_str_lines[line].lstrip())
                        total_typing_chars = char_num # Number of characters actually typed on this line

                        # Compute the autocomplete trigger point for this line (the moment the keyword is fully typed)
                        trigger_column = None
                        trigger_keyword = None
                        if Parameters.autocomplete:
                            stripped = self.code_str_lines[line].lstrip()
                            for kw in AUTOCOMPLETE_SUGGESTIONS:
                                if stripped.startswith(kw):
                                    rest = stripped[len(kw):]
                                    if rest == "" or not (rest[0].isalnum() or rest[0] == "_"):
                                        trigger_keyword = kw
                                        trigger_column = first_non_space_index + len(kw) - 1
                                        break

                        # Iterate over each character of the current line
                        submobjects_char_index = 0
                        for column in range(first_non_space_index, char_num + first_non_space_index):
                            # Handle the disappearing-space issue introduced in manim==0.19.1
                            if not self.code_str_lines[line][column].isspace():
                                if [line, column] not in self.space_positions:
                                    scene.add(code_mobject[line][submobjects_char_index])
                                    typed_mobjects.append(code_mobject[line][submobjects_char_index])
                                submobjects_char_index += 1
                            cursor.next_to(
                                code_mobject[line][submobjects_char_index-1],
                                RIGHT,
                                buff=DEFAULT_CURSOR_TO_CHAR_BUFFER
                            ).set_y(code_line_rectangle.get_y())

                            # Camera sway logic
                            line_break = False
                            if column == first_non_space_index and first_non_space_index != 0:
                                # If this is the first character after indentation, perform the line-break reset first
                                linebreakAnimation()
                                line_break = True
                            else:
                                # Compute the progress within the current line (0.0 -> 1.0)
                                current_idx = column - first_non_space_index
                                max_idx = total_typing_chars - 1

                                if max_idx > 0:
                                    alpha = current_idx / max_idx
                                else:
                                    alpha = 1.0

                                # Envelope sin(alpha * pi), ensuring it is 0 at both ends
                                envelope = np.sin(alpha * np.pi)

                                # Oscillation term: sin(alpha * omega)
                                wave_count = total_typing_chars / 15
                                omega = wave_count * 2 * np.pi
                                oscillation = np.sin(alpha * omega)

                                # Amplitude is 2.5% of the camera frame height
                                amplitude = scene.camera.frame.height * 0.025 # type: ignore
                                offset_y = amplitude * envelope * oscillation

                                target_pos = cursor.get_center() + UP * offset_y
                                scene.Animation_list.append({"move_to": target_pos})

                            # Scale detection & playback
                            JUDGE_cameraScaleAnimation()
                            playAnimation(
                                run_time=DEFAULT_LINE_BREAK_RUN_TIME if line_break else random.uniform(*Parameters.interval_range),
                                rate_func=rate_functions.smooth if line_break else rate_functions.linear
                            )

                            # Report progress
                            progress.advance(total_progress, advance=1)
                            progress.advance(current_line_progress, advance=1)

                            # Keyword fully typed: show the completion popup
                            if trigger_column is not None and column == trigger_column:
                                showAutocomplete(trigger_keyword)

                            # Chinese character typed: show the IME candidate box (triggered on the first char of each CJK run)
                            if Parameters.chinese_ime:
                                ch = self.code_str_lines[line][column]
                                if is_cjk(ch):
                                    prev_ch = self.code_str_lines[line][column - 1] if column > 0 else ""
                                    if not is_cjk(prev_ch):
                                        pinyin, cands = get_ime(self.code_str_lines[line], column)
                                        if cands:
                                            showIme(pinyin, cands)

                        progress.remove_task(current_line_progress)
                    progress.remove_task(total_progress)

                # Deletion animation after typing completes
                if Parameters.clear_code:
                    # Pull the camera back to the full code view and hold it still before
                    # deleting; otherwise the camera stays at the last character during
                    # backspace deletion and looks like it is "deleting along with the code"
                    frame = scene.camera.frame
                    code_center = code_mobject.get_center()
                    fit_h = code_mobject.get_height() * 1.4 + 1.5
                    fit_w = code_mobject.get_width() * 1.4 + 1.5
                    aspect = frame.get_width() / frame.get_height()
                    need_h = max(fit_h, fit_w / aspect)
                    scene.play(
                        frame.animate.move_to(code_center).set_height(need_h),
                        run_time=0.6,
                        rate_func=rate_functions.ease_in_out_cubic,
                    )

                    if Parameters.clear_code_mode == "backspace":
                        # Delete character by character in reverse, like pressing backspace
                        for mobject in reversed(typed_mobjects):
                            cursor.next_to(mobject, RIGHT, buff=DEFAULT_CURSOR_TO_CHAR_BUFFER).set_y(code_line_rectangle.get_y())
                            scene.play(
                                FadeOut(mobject),
                                run_time=Parameters.clear_code_interval,
                                rate_func=rate_functions.linear
                            )
                        # Finally remove line numbers, cursor, and the line-highlight rectangle
                        scene.play(
                            FadeOut(VGroup(line_number_mobject, cursor, code_line_rectangle)),
                            run_time=Parameters.clear_code_run_time,
                            rate_func=rate_functions.ease_in_out_cubic
                        )
                    else:
                        # Fade the whole block out
                        scene.play(
                            FadeOut(VGroup(code_mobject, line_number_mobject, cursor, code_line_rectangle)),
                            run_time=Parameters.clear_code_run_time,
                            rate_func=rate_functions.ease_in_out_cubic
                        )

                scene.wait(Parameters.end_wait_time)

            def render(scene):
                """Override render to add timing log."""
                if self.output:
                    DEFAULT_OUTPUT_CONSOLE.log(f"Start rendering {Parameters.video_name}.mp4.")
                    DEFAULT_OUTPUT_CONSOLE.log("Start rendering CameraFollowCursorCVScene. [dim](by manim)[/]")
                    if config.renderer == RendererType.CAIRO:
                        DEFAULT_OUTPUT_CONSOLE.log('[blue]Currently using CPU (Cairo Renderer) for rendering.[/]')
                    else:
                        DEFAULT_OUTPUT_CONSOLE.log('[blue]Currently using GPU (OpenGL Renderer) for rendering.[/]')
                    DEFAULT_OUTPUT_CONSOLE.log("Manim's config has been modified.")

                # Render and measure time
                with noManimOutput():
                    total_render_time = timeit(super().render, number=1)
                if self.output:
                    DEFAULT_OUTPUT_CONSOLE.log(f"Successfully rendered CameraFollowCursorCVScene in {total_render_time:,.2f} seconds. [dim](by manim)[/]")
                del total_render_time

                # Restore config
                config.disable_caching = self.origin_config['disable_caching']
                config.renderer = self.origin_config['renderer']
                config.background_color = self.origin_config['background_color']
                if self.output:
                    DEFAULT_OUTPUT_CONSOLE.log("Manim's config has been restored.")
                del self.origin_config
                if self.output:
                    DEFAULT_OUTPUT_CONSOLE.log(f"Start adding glow effect to CameraFollowCursorCVScene.mp4. [dim](by moviepy)[/]\n")

                # Add the glow effect
                input_path = Path(scene.renderer.file_writer.movie_file_path)
                output_path = str(input_path.with_name(f"{Parameters.video_name}.mp4"))
                total_effect_time = timeit(lambda: addGlowEffect(input_path=input_path, output_path=output_path, output=self.output), number=1)
                if self.output:
                    DEFAULT_OUTPUT_CONSOLE.log(f"Successfully added glow effect in {total_effect_time:,.2f} seconds. [dim](by moviepy)[/]")
                    DEFAULT_OUTPUT_CONSOLE.log(f"File ready at '{output_path}'.")
                del input_path, output_path, total_effect_time

        return CameraFollowCursorCVScene()

    @typechecked
    def render(self, output: bool = DEFAULT_OUTPUT_VALUE):
        """
        Render the animated code video.

        This method triggers the full rendering pipeline:

        1. **Manim rendering** – the code typing animation is rendered using the configured backend (Cairo or OpenGL).
        2. **Glow effect** – a soft glow post-processing effect is applied to the raw video via MoviePy.

        The final video file is saved next to Manim's default output path with the name specified by ``video_name``.

        Args:
            output (bool): Whether to print progress messages and timing logs to the console during rendering. Defaults to :data:`~.DEFAULT_OUTPUT_VALUE`.

        Returns:
            None

        Example:
            >>> video = CameraFollowCursorCV(
            ...     code=('string', 'print("Hello")'),
            ...     language='python',
            ...     video_name='HelloWorld'
            ... )
            >>> video.render()

        Note:
            The final MP4 file is typically located at ``./media/videos/1080p60/{video_name}.mp4``
            (the exact sub-directory depends on Manim's quality configuration).
        """
        self.output = output
        self.scene.render()

    def __getattribute__(self, name):
        frames = inspect.stack()
        is_internal_call = False

        for frame in frames[1:]:
            frame_self = frame.frame.f_locals.get('self')
            if isinstance(frame_self, CameraFollowCursorCV):
                is_internal_call = True
                break

        if not is_internal_call:
            allowed_attrs = super().__getattribute__("__all__")
            if name not in allowed_attrs:
                raise AttributeError(f"'CameraFollowCursorCV' object has no attribute '{name}'")

        return super().__getattribute__(name)

__all__ = ["CameraFollowCursorCV"]
