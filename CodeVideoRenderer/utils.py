from __future__ import annotations # for Sphinx typehints
from manim import config
from rich.progress import Progress, BarColumn, TextColumn, TimeRemainingColumn, TransferSpeedColumn
from copy import copy
from contextlib import contextmanager
from io import StringIO
from typing import get_args, get_origin, Generator, Any, Union, List
from moviepy.video.io.VideoFileClip import VideoFileClip
from PIL import Image, ImageFilter, ImageEnhance
from proglog import ProgressBarLogger
from collections import OrderedDict
import numpy as np
import time, sys

try:
    from types import UnionType
except ImportError:
    UnionType = type(Union[int, str])

from .config import *
from .typing import StrPath

@contextmanager
def noManimOutput() -> Generator[None, Any, None]:
    """
    Context manager used to execute code without outputting Manim logs.

    Within the ``with`` block, Manim's standard output, standard error, and
    progress bars are suppressed. Streams are restored when the block exits.

    Yields:
        None
    """
    sys.stdout = StringIO()
    stderr_buffer = StringIO()
    sys.stderr = stderr_buffer
    config.progress_bar = "none"

    try:
        yield
    finally:
        sys.stdout = ORIGINAL_STDOUT
        sys.stderr = ORIGINAL_STDERR
        config.progress_bar = ORIGINAL_PROGRESS_BAR
        stderr_content = stderr_buffer.getvalue()
        if stderr_content:
            print(stderr_content, file=ORIGINAL_STDERR)

def stripEmptyLines(text: str) -> str:
    """
    Remove empty lines from the beginning and end of a string.

    Args:
        text (str): The input string to process.

    Returns:
        str: The string with empty lines removed from the beginning and end.
    """
    lines = text.split("\n")

    start = 0
    while start < len(lines) and lines[start].strip() == '':
        start += 1

    end = len(lines)
    while end > start and lines[end - 1].strip() == '':
        end -= 1

    return '\n'.join(lines[start:end])

def typeName(item_type: Any) -> str:
    """
    Get the name of a type, handling union types and generic types.

    Args:
        item_type: The type or value to get the name of.

    Returns:
        str: The name of the type.
    """
    # Handle UnionType
    if isinstance(item_type, UnionType):
        return str(item_type).replace(" | ", "' or '")

    # Handle non-type objects (like Literal values)
    if not isinstance(item_type, type):
        if isinstance(item_type, str):
            return f"'{item_type}'"
        return str(item_type)

    # Handle generic types
    origin = get_origin(item_type)
    if origin:
        args = get_args(item_type)
        if args:
            arg_names = ', '.join([typeName(arg) for arg in args])
            return f"{origin.__name__}[{arg_names}]"
        return origin.__name__

    # Handle basic types
    return item_type.__name__

def addGlowEffect(input_path: StrPath, output_path: StrPath, output: bool) -> None:
    """
    Add a glow effect to a video.

    Args:
        input_path (StrPath): Path to the input video file.
        output_path (StrPath): Path to save the output video file.
        output (bool): Whether to display progress bars.

    Returns:
        None
    """
    # Inner frame-processing function
    def _frame_glow(t: np.ndarray):
        # Get the MoviePy numpy frame and convert it to a PIL image
        frame = t.astype(np.uint8)
        pil_img = Image.fromarray(frame).convert("RGBA")

        # Boost base brightness
        brightness_enhancer = ImageEnhance.Brightness(pil_img)
        pil_img = brightness_enhancer.enhance(1.2)

        # Create the blurred glow layer
        glow = pil_img.filter(ImageFilter.GaussianBlur(radius=10))

        # Boost the glow's brightness and saturation
        glow_bright_enhancer = ImageEnhance.Brightness(glow)
        glow = glow_bright_enhancer.enhance(1.6)
        glow_color_enhancer = ImageEnhance.Color(glow)
        glow = glow_color_enhancer.enhance(2)

        # Blend the original image with the glow layer
        soft_glow_img = Image.blend(glow, pil_img, 0.4)
        glow_frame = np.array(soft_glow_img.convert("RGB")).astype(np.uint8)
        return np.clip(glow_frame, 0, 255)

    glow_video: VideoFileClip = VideoFileClip(input_path).image_transform(_frame_glow)
    glow_video.write_videofile(output_path, codec='libx264', audio=True, logger=RichProgressBarLogger(output=output, title="Glow Effect", leave_bars=False))

def findSpacePositions(string: str) -> List[List[int]]:
    """
    Find the 2D positions of all non-leading, non-trailing spaces in a string.
    Each position is represented as a list ``[row_index, column_index]``.

    Args:
        string (str): A string.

    Returns:
        List[List[int]]: A list of 2D positions of all non-leading, non-trailing spaces.
        Each position is represented as a list ``[row_index, column_index]``.
    """
    result = []  # Store all space positions in [row, col] form
    for row_idx, s in enumerate(string.splitlines()):
        # Find the column index of the first non-space character
        first_non_space = 0
        while first_non_space < len(s) and s[first_non_space] == ' ':
            first_non_space += 1

        # Find the column index of the last non-space character
        last_non_space = len(s) - 1
        while last_non_space >= 0 and s[last_non_space] == ' ':
            last_non_space -= 1

        # All spaces / empty string; skip
        if first_non_space > last_non_space:
            result.extend([[row_idx, col_idx] for col_idx in range(len(s))])  # Record the whole line's space positions
            continue

        # Scan the middle section and collect [row, col] positions
        for col_idx in range(first_non_space, last_non_space + 1):
            if s[col_idx] == ' ':
                result.append([row_idx, col_idx])

    return result

def findEmptyLinePositions(string: str) -> List[int]:
    """
    Find the line indices of all empty lines in a string.

    Args:
        string (str): A string.

    Returns:
        List[int]: A list of line indices of all empty lines.
    """
    return [idx for idx, line in enumerate(string.splitlines()) if line.strip() == '']

def replaceMiddleSpacesWithOccupyCharacter(string: str) -> str:
    """
    Replace all non-leading, non-trailing spaces in the input string with :data:`~.OCCUPY_CHARACTER`.
    Retain leading and trailing spaces.

    Args:
        string (str): Original string.

    Returns:
        str: Processed string with middle spaces replaced by :data:`~.OCCUPY_CHARACTER`.
    """
    result = []
    for s in string.splitlines():
        # Keep non-string elements as-is
        if not isinstance(s, str):
            result.append(s)
            continue

        # Keep empty strings as-is
        if len(s) == 0:
            result.append(s)
            continue

        # Convert to a list so characters can be modified
        s_list = list(s)

        # Find the index of the first non-space character
        first_non_space = 0
        while first_non_space < len(s_list) and s_list[first_non_space] == ' ':
            first_non_space += 1

        # Find the index of the last non-space character
        last_non_space = len(s_list) - 1
        while last_non_space >= 0 and s_list[last_non_space] == ' ':
            last_non_space -= 1

        # All spaces: keep the original string unchanged
        if first_non_space > last_non_space:
            result.append(s.replace(' ', OCCUPY_CHARACTER))
            continue

        # Scan the middle region and replace spaces with the occupy character
        for idx in range(first_non_space, last_non_space + 1):
            if s_list[idx] == ' ':
                s_list[idx] = OCCUPY_CHARACTER

        # Convert back to a string and append to the result
        result.append(''.join(s_list))

    return '\n'.join(result)

class DefaultProgressBar(Progress):
    """
    Default progress bar used during video rendering.

    This is a thin wrapper around ``rich.progress.Progress`` pre-configured with
    descriptive columns (task name, bar, completion count, percentage, time remaining,
    and transfer speed).
    """
    def __init__(self, output: bool):
        """
        Args:
            output (bool): If ``False``, the progress bar is attached to a ``None`` console
                so that no output is displayed.
        """
        super().__init__(
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[yellow]{task.completed}/{task.total}"),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeRemainingColumn(),
            TransferSpeedColumn(),
            console=DEFAULT_OUTPUT_CONSOLE if output else None
        )

class RichProgressBarLogger(ProgressBarLogger):
    """
    A progress logger that uses Rich to display progress bars.

    This class bridges ``proglog`` (used by MoviePy) and ``rich`` progress bars,
    allowing the glow-effect post-processing step to show a native-looking progress
    indicator in the terminal.
    """
    def __init__(
        self,
        output: bool,
        title: str,
        init_state=None,
        bars=None,
        leave_bars=True,
        ignored_bars=None,
        logged_bars="all",
        print_messages=True,
        min_time_interval=0.1,
        ignore_bars_under=0,
    ):
        """
        Args:
            output (bool): Whether to display the progress bar.
            title (str): Title shown at the top of the progress bar.
            init_state: Initial state forwarded to ``ProgressBarLogger``.
            bars: Bar definitions forwarded to ``ProgressBarLogger``.
            leave_bars (bool): If ``True``, finished bars remain visible.
            ignored_bars: Bars to ignore forwarded to ``ProgressBarLogger``.
            logged_bars: Bars to log forwarded to ``ProgressBarLogger``.
            print_messages (bool): Whether to print log messages.
            min_time_interval (float): Minimum update interval in seconds.
            ignore_bars_under (int): Ignore bars with fewer than this many items.
        """
        # Call the parent constructor to initialize core attributes
        super().__init__(
            init_state=init_state,
            bars=bars,
            ignored_bars=ignored_bars,
            logged_bars=logged_bars,
            ignore_bars_under=ignore_bars_under,
            min_time_interval=min_time_interval, # type: ignore
        )

        # Initialize custom attributes
        self.leave_bars = leave_bars
        self.print_messages = print_messages
        self.output = output
        self.title = title
        self.start_time = time.time()

        # Initialize the Rich progress bar
        self.progress_bar = copy(DefaultProgressBar(self.output))
        self.rich_bars = OrderedDict()  # Store {bar_name: task_id}

        # Start the Rich progress bar
        if self.progress_bar and not self.progress_bar.live.is_started:
            self.progress_bar.start()

    def new_tqdm_bar(self, bar):
        """
        Create a Rich progress bar task for the given bar.
        """
        if not self.output or self.progress_bar is None:
            return

        # Close any existing progress bar
        if bar in self.rich_bars:
            self.close_tqdm_bar(bar)

        # Get the progress-bar info maintained by the parent class
        infos = self.bars[bar]
        # Create a Rich progress-bar task
        task_id = self.progress_bar.add_task(description=f"[yellow]{self.title}[/yellow]", total=infos["total"])
        self.rich_bars[bar] = task_id

    def close_tqdm_bar(self, bar):
        """
        Close the Rich progress bar task for the given bar.
        """
        if not self.output or self.progress_bar is None:
            return

        if bar in self.rich_bars:
            task_id = self.rich_bars[bar]
            # Remove the task if it should not be kept
            if not self.leave_bars:
                self.progress_bar.remove_task(task_id)
            del self.rich_bars[bar]

    def bars_callback(self, bar, attr, value, old_value):
        """
        Update the Rich progress bar task based on the attribute change.
        """
        if not self.output or self.progress_bar is None:
            return
        if bar not in self.rich_bars:
            self.new_tqdm_bar(bar)

        task_id = self.rich_bars.get(bar)
        if task_id is None:
            return
        if attr == "index":
            # Handle frame-count updates (core)
            if value >= old_value:
                total = self.bars[bar]["total"]
                # Calculate processing speed
                elapsed = time.time() - self.start_time
                speed = value / elapsed if elapsed > 0 else 0.0

                # Update the Rich progress bar
                self.progress_bar.update(
                    task_id, # type: ignore
                    completed=value,
                    speed=speed
                )

                # Close once complete (mirror the original logic)
                if total and (value >= total):
                    self.close_tqdm_bar(bar)
            else:
                # Frame-count rollback: reset the progress bar
                self.new_tqdm_bar(bar)
                self.progress_bar.update(self.rich_bars[bar], completed=value)

    def stop(self):
        """
        Stop the Rich progress bar.
        """
        if self.progress_bar and self.progress_bar.live.is_started:
            self.progress_bar.stop()

__all__ = [
    "noManimOutput",
    "stripEmptyLines",
    "typeName",
    "addGlowEffect",
    "findSpacePositions",
    "findEmptyLinePositions",
    "replaceMiddleSpacesWithOccupyCharacter",
    "DefaultProgressBar",
    "RichProgressBarLogger"
]
