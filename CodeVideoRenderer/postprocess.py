"""Video post-processing utilities for CodeVideoRenderer.

This module provides a collection of standalone functions that operate on
already-rendered (or any) video files.  They are thin, well-documented wrappers
around ``ffmpeg`` and are designed to be called *after* a video has been
generated, e.g.:

.. code-block:: python

    from CodeVideoRenderer import remove_subtitles, add_background_music

    remove_subtitles("my_video.mp4")          # -> my_video_no_subs.mp4
    add_background_music("my_video.mp4", "bgm.mp3")

All functions accept ``input_path`` (a ``str`` or ``os.PathLike``) and an
optional ``output_path``.  When ``output_path`` is omitted, a sensible name is
derived from the input file.  Every function returns the resolved output path.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from fractions import Fraction
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple, Union

from .typing import StrPath

# ---------------------------------------------------------------------------
# ffmpeg discovery
# ---------------------------------------------------------------------------

_POSITION_ALIASES = {
    "top-left": "tl",
    "top-right": "tr",
    "bottom-left": "bl",
    "bottom-right": "br",
    "center": "center",
    "tl": "tl",
    "tr": "tr",
    "bl": "bl",
    "br": "br",
}

_RESOLUTION_PRESETS = {
    "480p": (854, 480),
    "720p": (1280, 720),
    "1080p": (1920, 1080),
    "2k": (2560, 1440),
    "4k": (3840, 2160),
}


def find_ffmpeg() -> str:
    """Locate the ``ffmpeg`` executable.

    Resolution order:

    1. The ``CODEVIDEORENDERER_FFMPEG`` / ``FFMPEG_BINARY`` environment variables.
    2. ``ffmpeg`` on ``PATH``.
    3. A handful of common install locations.
    4. The binary bundled with ``imageio-ffmpeg`` (a dependency of this library).

    Returns:
        str: The absolute path to ``ffmpeg``.

    Raises:
        FileNotFoundError: If no ``ffmpeg`` binary could be found.
    """
    for var in ("CODEVIDEORENDERER_FFMPEG", "FFMPEG_BINARY"):
        candidate = os.environ.get(var)
        if candidate and Path(candidate).exists():
            return str(Path(candidate))

    which = shutil.which("ffmpeg")
    if which:
        return which

    common = [
        r"C:\ffmpeg\bin\ffmpeg.exe",
        r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
        "/usr/local/bin/ffmpeg",
        "/usr/bin/ffmpeg",
        "/opt/homebrew/bin/ffmpeg",
    ]
    for candidate in common:
        if Path(candidate).exists():
            return candidate

    try:
        import imageio_ffmpeg  # type: ignore

        bundled = imageio_ffmpeg.get_ffmpeg_exe()
        if bundled and Path(bundled).exists():
            return bundled
    except Exception:
        pass

    raise FileNotFoundError(
        "Could not locate ffmpeg. Install it and make it available on PATH, or "
        "set the CODEVIDEORENDERER_FFMPEG environment variable to its full path."
    )


def find_ffprobe() -> str:
    """Locate ``ffprobe`` next to :func:`find_ffmpeg`.

    Returns:
        str: The absolute path to ``ffprobe``.

    Raises:
        FileNotFoundError: If ``ffprobe`` cannot be found.
    """
    ffmpeg = Path(find_ffmpeg())
    name = "ffprobe.exe" if os.name == "nt" else "ffprobe"
    candidate = ffmpeg.with_name(name)
    if candidate.exists():
        return str(candidate)

    which = shutil.which("ffprobe")
    if which:
        return which

    raise FileNotFoundError("Could not locate ffprobe (expected next to ffmpeg).")


def _run_ffmpeg(args: Sequence[str]) -> None:
    """Run ffmpeg, raising a descriptive error on failure."""
    cmd = [find_ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", *args]
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed ({proc.returncode}): {proc.stderr.strip()}")


def _run_ffprobe(args: Sequence[str]) -> str:
    """Run ffprobe and return its stdout."""
    cmd = [find_ffprobe(), "-v", "error", *args]
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffprobe failed ({proc.returncode}): {proc.stderr.strip()}")
    return proc.stdout


def _default_output(input_path: StrPath, tag: str) -> str:
    """Build a default output path by inserting ``tag`` before the extension."""
    p = Path(input_path)
    return str(p.with_name(f"{p.stem}_{tag}{p.suffix}"))


def _ffmpeg_filter_path(path: StrPath) -> str:
    """Escape a path so it can be embedded in an ffmpeg filter argument."""
    p = str(path).replace("\\", "/")
    if os.name == "nt":
        p = p.replace(":", r"\:")
    return p


def _drawtext_escape(text: str) -> str:
    """Escape special characters for use inside an ffmpeg ``drawtext`` filter."""
    return (
        text.replace("\\", "\\\\")
        .replace(":", "\\:")
        .replace("'", "\\'")
        .replace("%", "\\%")
    )


def _default_font() -> str:
    """Return a font file that supports CJK when available, else empty (ffmpeg default)."""
    candidates = [
        r"C:\Windows\Fonts\msyh.ttc",  # 微软雅黑
        r"C:\Windows\Fonts\msyh.ttf",
        r"C:\Windows\Fonts\simhei.ttf",
        r"C:\Windows\Fonts\simsun.ttc",
        r"C:\Windows\Fonts\arial.ttf",
        "/System/Library/Fonts/PingFang.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for candidate in candidates:
        if Path(candidate).exists():
            return candidate
    return ""


def _has_audio_stream(path: StrPath) -> bool:
    """Return ``True`` if the input contains at least one audio stream."""
    out = _run_ffprobe(["-select_streams", "a", "-show_entries", "stream=index", "-of", "json", str(path)])
    try:
        return bool(json.loads(out).get("streams"))
    except Exception:
        return False


def _probe_video_info(path: StrPath) -> Tuple[int, int, float]:
    """Return ``(width, height, fps)`` of the first video stream."""
    out = _run_ffprobe(
        [
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height,r_frame_rate",
            "-of",
            "json",
            str(path),
        ]
    )
    stream = json.loads(out)["streams"][0]
    fps = float(Fraction(stream.get("r_frame_rate", "30/1")))
    return int(stream["width"]), int(stream["height"]), fps


def _parse_resolution(resolution) -> Tuple[int, int]:
    """Normalise a resolution specification to a ``(width, height)`` tuple.

    ``-2`` as a width means "keep aspect ratio" (ffmpeg ``scale=-2:HEIGHT``).
    """
    if isinstance(resolution, (tuple, list)) and len(resolution) == 2:
        return int(resolution[0]), int(resolution[1])
    if isinstance(resolution, int):
        return -2, int(resolution)
    key = str(resolution).lower()
    if key in _RESOLUTION_PRESETS:
        return _RESOLUTION_PRESETS[key]
    raise ValueError(
        f"Unsupported resolution {resolution!r}. Use a preset "
        f"({', '.join(_RESOLUTION_PRESETS)}), a height (int), or a (width, height) tuple."
    )


# ---------------------------------------------------------------------------
# Subtitles
# ---------------------------------------------------------------------------

def remove_subtitles(input_path: StrPath, output_path: Optional[StrPath] = None) -> str:
    """Strip all embedded subtitle streams from a video.

    Args:
        input_path: Path to the input video.
        output_path: Optional output path. Defaults to ``<name>_no_subs.<ext>``.

    Returns:
        str: The output file path.
    """
    output_path = output_path or _default_output(input_path, "no_subs")
    _run_ffmpeg(["-i", str(input_path), "-map", "0", "-c", "copy", "-sn", str(output_path)])
    return str(output_path)


def add_subtitles(
    input_path: StrPath,
    subtitle_path: StrPath,
    output_path: Optional[StrPath] = None,
    soft: bool = False,
) -> str:
    """Add subtitles to a video.

    Args:
        input_path: Path to the input video.
        subtitle_path: Path to a subtitle file (``.srt`` / ``.ass`` / ``.vtt``).
        output_path: Optional output path. Defaults to ``<name>_subbed.<ext>``.
        soft: If ``True``, embed the subtitle as a switchable (soft) track
            without re-encoding video/audio. If ``False`` (default), the
            subtitles are *burned* into the picture (always visible).

    Returns:
        str: The output file path.
    """
    output_path = output_path or _default_output(input_path, "subbed")

    if soft:
        _run_ffmpeg(
            [
                "-i", str(input_path),
                "-i", str(subtitle_path),
                "-map", "0", "-map", "1",
                "-c", "copy", "-c:s", "mov_text",
                "-metadata:s:s:0", "language=chi",
                str(output_path),
            ]
        )
    else:
        vf = f"subtitles='{_ffmpeg_filter_path(subtitle_path)}'"
        _run_ffmpeg(
            [
                "-i", str(input_path),
                "-vf", vf,
                "-c:v", "libx264", "-c:a", "copy",
                str(output_path),
            ]
        )
    return str(output_path)


# ---------------------------------------------------------------------------
# Audio
# ---------------------------------------------------------------------------

def add_background_music(
    input_path: StrPath,
    music_path: StrPath,
    output_path: Optional[StrPath] = None,
    volume: float = 0.3,
    loop: bool = True,
    mix_original: bool = True,
) -> str:
    """Mix a background-music track into a video.

    Args:
        input_path: Path to the input video.
        music_path: Path to the audio file (``.mp3`` / ``.wav`` / ``.m4a`` …).
        output_path: Optional output path. Defaults to ``<name>_bgm.<ext>``.
        volume: Volume multiplier applied to the music (0.0–1.0+). Defaults to 0.3.
        loop: Loop the music to cover the whole video. Defaults to ``True``.
        mix_original: If the video already has audio, mix it with the music.
            If the video has no audio, the music simply becomes the audio track.

    Returns:
        str: The output file path.
    """
    output_path = output_path or _default_output(input_path, "bgm")
    loop_args: List[str] = ["-stream_loop", "-1"] if loop else []
    has_audio = _has_audio_stream(input_path)

    if has_audio and mix_original:
        filter_complex = (
            f"[1:a]volume={volume}[bg];"
            f"[0:a][bg]amix=inputs=2:duration=first:normalize=0[aout]"
        )
        audio_map = "[aout]"
    else:
        filter_complex = f"[1:a]volume={volume}[bg]"
        audio_map = "[bg]"

    _run_ffmpeg(
        [
            "-i", str(input_path),
            *loop_args,
            "-i", str(music_path),
            "-filter_complex", filter_complex,
            "-map", "0:v", "-map", audio_map,
            "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
            "-shortest",
            str(output_path),
        ]
    )
    return str(output_path)


def extract_audio(input_path: StrPath, output_path: Optional[StrPath] = None, format: str = "mp3") -> str:
    """Extract the audio track of a video into a standalone audio file.

    Args:
        input_path: Path to the input video.
        output_path: Optional output path. Defaults to ``<name>.<format>``.
        format: Output audio format (``mp3`` / ``wav`` / ``m4a`` / ``aac``).

    Returns:
        str: The output audio path.
    """
    fmt = format.lower().lstrip(".")
    codecs = {"mp3": "libmp3lame", "wav": "pcm_s16le", "m4a": "aac", "aac": "aac"}
    if fmt not in codecs:
        raise ValueError(f"Unsupported audio format {format!r}. Choose from {sorted(codecs)}.")

    if output_path is None:
        output_path = str(Path(input_path).with_suffix(f".{fmt}"))
    _run_ffmpeg(["-i", str(input_path), "-vn", "-acodec", codecs[fmt], str(output_path)])
    return str(output_path)


def remove_audio(input_path: StrPath, output_path: Optional[StrPath] = None) -> str:
    """Remove the audio track from a video (producing a silent video).

    Returns:
        str: The output file path.
    """
    output_path = output_path or _default_output(input_path, "mute")
    _run_ffmpeg(["-i", str(input_path), "-c", "copy", "-an", str(output_path)])
    return str(output_path)


# ---------------------------------------------------------------------------
# Editing / quality
# ---------------------------------------------------------------------------

def concat_videos(
    input_paths: Iterable[StrPath],
    output_path: StrPath,
    reencode: bool = False,
) -> str:
    """Concatenate multiple videos into one.

    Args:
        input_paths: An iterable of input video paths, in the desired order.
        output_path: The output path (required).
        reencode: If ``False`` (default), streams are copied without re-encoding
            — fast, but all inputs must share the same codec/resolution. Set to
            ``True`` to re-encode (handles codec differences; inputs must still
            have matching resolution for the concat filter).

    Returns:
        str: The output file path.
    """
    paths = [str(Path(p).resolve()) for p in input_paths]
    if len(paths) < 2:
        raise ValueError("concat_videos requires at least two input videos.")

    if reencode:
        inputs: List[str] = []
        for p in paths:
            inputs += ["-i", p]
        n = len(paths)
        has_audio_flags = [_has_audio_stream(p) for p in paths]

        # 视频流统一成 yuv420p，避免不同像素格式导致 concat 失败
        v_parts = [f"[{i}:v]format=yuv420p[v{i}]" for i in range(n)]

        if all(has_audio_flags):
            a_parts = [f"[{i}:a]aformat=sample_rates=44100:channel_layouts=stereo[a{i}]" for i in range(n)]
            joins = "".join(f"[v{i}][a{i}]" for i in range(n))
            filter_complex = ";".join(v_parts + a_parts) + ";" + joins + f"concat=n={n}:v=1:a=1[v][a]"
            _run_ffmpeg(
                [
                    *inputs,
                    "-filter_complex", filter_complex,
                    "-map", "[v]", "-map", "[a]",
                    "-c:v", "libx264", "-c:a", "aac",
                    str(output_path),
                ]
            )
        elif not any(has_audio_flags):
            joins = "".join(f"[v{i}]" for i in range(n))
            filter_complex = ";".join(v_parts) + ";" + joins + f"concat=n={n}:v=1:a=0[v]"
            _run_ffmpeg(
                [
                    *inputs,
                    "-filter_complex", filter_complex,
                    "-map", "[v]",
                    "-c:v", "libx264", "-an",
                    str(output_path),
                ]
            )
        else:
            raise ValueError(
                "concat_videos(reencode=True) requires all inputs to either have audio or "
                "all to be silent; mixed audio presence is not supported. Normalise the "
                "inputs first (e.g. with remove_audio / add_background_music)."
            )
        return str(output_path)

    with tempfile.TemporaryDirectory() as tmp:
        list_file = Path(tmp) / "concat.txt"
        list_file.write_text(
            "".join(f"file '{p}'" + "\n" for p in paths),
            encoding="utf-8",
        )
        _run_ffmpeg(["-f", "concat", "-safe", "0", "-i", str(list_file), "-c", "copy", str(output_path)])
    return str(output_path)


def set_quality(
    input_path: StrPath,
    output_path: Optional[StrPath] = None,
    resolution: Optional[Union[str, int, Tuple[int, int]]] = None,
    fps: Optional[Union[int, float]] = None,
    bitrate: Optional[str] = None,
    crf: Optional[int] = None,
) -> str:
    """Re-encode a video with a chosen resolution, frame rate, bitrate or CRF.

    Args:
        input_path: Path to the input video.
        output_path: Optional output path. Defaults to ``<name>_quality.<ext>``.
        resolution: A preset string (``"1080p"``, ``"4k"`` …), a target height
            (``1080``), or a ``(width, height)`` tuple.
        fps: Output frame rate.
        bitrate: Video bitrate, e.g. ``"5M"``.
        crf: Constant Rate Factor (lower = higher quality, 18–28 typical).

    Returns:
        str: The output file path.
    """
    output_path = output_path or _default_output(input_path, "quality")
    args: List[str] = ["-i", str(input_path)]

    if resolution is not None:
        width, height = _parse_resolution(resolution)
        if width == -2:
            vf = f"scale=-2:{height}"
        else:
            vf = f"scale={width}:{height}"
        args += ["-vf", vf]

    args += ["-c:v", "libx264"]
    if fps is not None:
        args += ["-r", str(fps)]
    if bitrate is not None:
        args += ["-b:v", str(bitrate)]
    if crf is not None:
        args += ["-crf", str(crf)]
    args += ["-c:a", "aac", "-b:a", "192k", str(output_path)]

    _run_ffmpeg(args)
    return str(output_path)


def trim_video(
    input_path: StrPath,
    output_path: Optional[StrPath] = None,
    start: float = 0.0,
    end: Optional[float] = None,
    duration: Optional[float] = None,
) -> str:
    """Cut a segment out of a video.

    Args:
        input_path: Path to the input video.
        output_path: Optional output path. Defaults to ``<name>_trim.<ext>``.
        start: Start time in seconds.
        end: End time in seconds (alternative to ``duration``).
        duration: Segment duration in seconds.

    Returns:
        str: The output file path.
    """
    output_path = output_path or _default_output(input_path, "trim")
    args: List[str] = ["-i", str(input_path), "-ss", str(start)]
    if duration is not None:
        args += ["-t", str(duration)]
    elif end is not None:
        args += ["-to", str(end)]
    args += ["-c", "copy", str(output_path)]
    _run_ffmpeg(args)
    return str(output_path)


def change_speed(
    input_path: StrPath,
    output_path: Optional[StrPath] = None,
    speed: float = 1.0,
) -> str:
    """Speed up or slow down a video while keeping audio in sync.

    Args:
        input_path: Path to the input video.
        output_path: Optional output path. Defaults to ``<name>_speed.<ext>``.
        speed: Playback speed multiplier (e.g. 2.0 = twice as fast).

    Returns:
        str: The output file path.
    """
    if speed <= 0:
        raise ValueError("speed must be greater than 0")
    output_path = output_path or _default_output(input_path, f"speed{speed}".replace(".", "_"))
    _run_ffmpeg(
        [
            "-i", str(input_path),
            "-filter_complex", f"[0:v]setpts={1 / speed:.6f}*PTS[v];[0:a]atempo={speed}[a]",
            "-map", "[v]", "-map", "[a]",
            str(output_path),
        ]
    )
    return str(output_path)


# ---------------------------------------------------------------------------
# Overlays (watermark / title / cover)
# ---------------------------------------------------------------------------

def _overlay_position(position: str, margin: int) -> Tuple[str, str]:
    """Return ffmpeg overlay ``(x, y)`` expressions for a named position."""
    pos = _POSITION_ALIASES.get(position.lower(), "br")
    if pos == "tl":
        return f"{margin}", f"{margin}"
    if pos == "tr":
        return f"W-w-{margin}", f"{margin}"
    if pos == "bl":
        return f"{margin}", f"H-h-{margin}"
    if pos == "center":
        return "(W-w)/2", "(H-h)/2"
    return f"W-w-{margin}", f"H-h-{margin}"  # bottom-right


def _drawtext_position(position: str, margin: int) -> Tuple[str, str]:
    """Return drawtext ``(x, y)`` expressions for a named position."""
    pos = _POSITION_ALIASES.get(position.lower(), "br")
    if pos == "tl":
        return f"{margin}", f"{margin}"
    if pos == "tr":
        return f"w-text_w-{margin}", f"{margin}"
    if pos == "bl":
        return f"{margin}", f"h-text_h-{margin}"
    if pos == "center":
        return "(w-text_w)/2", "(h-text_h)/2"
    return f"w-text_w-{margin}", f"h-text_h-{margin}"


def add_watermark(
    input_path: StrPath,
    output_path: Optional[StrPath] = None,
    text: Optional[str] = None,
    image_path: Optional[StrPath] = None,
    position: str = "bottom-right",
    fontsize: int = 24,
    opacity: float = 0.6,
    color: str = "white",
    margin: int = 20,
) -> str:
    """Overlay a text or image watermark onto a video.

    Args:
        input_path: Path to the input video.
        output_path: Optional output path. Defaults to ``<name>_wm.<ext>``.
        text: Watermark text (used when ``image_path`` is ``None``).
        image_path: Path to a watermark image (with transparency recommended).
        position: One of ``"top-left"``, ``"top-right"``, ``"bottom-left"``,
            ``"bottom-right"``, ``"center"``.
        fontsize: Font size for text watermarks.
        opacity: Watermark opacity (0.0–1.0).
        color: Text color for text watermarks.
        margin: Distance from the edge, in pixels.

    Returns:
        str: The output file path.
    """
    if text is None and image_path is None:
        raise ValueError("Provide either `text` or `image_path` for the watermark.")
    output_path = output_path or _default_output(input_path, "wm")

    if image_path is not None:
        x, y = _overlay_position(position, margin)
        _run_ffmpeg(
            [
                "-i", str(input_path),
                "-i", str(image_path),
                "-filter_complex",
                f"[1]format=rgba,colorchannelmixer=aa={opacity}[wm];[0][wm]overlay={x}:{y}",
                "-c:a", "copy",
                str(output_path),
            ]
        )
        return str(output_path)

    font = _default_font()
    x, y = _drawtext_position(position, margin)
    drawtext = (
        f"drawtext=text='{_drawtext_escape(text)}'"
        f":x={x}:y={y}"
        f":fontsize={fontsize}"
        f":fontcolor={color}@{opacity}"
    )
    if font:
        drawtext += f":fontfile='{_ffmpeg_filter_path(font)}'"
    _run_ffmpeg(["-i", str(input_path), "-vf", drawtext, "-c:a", "copy", str(output_path)])
    return str(output_path)


def add_title_card(
    input_path: StrPath,
    output_path: Optional[StrPath] = None,
    title: Optional[str] = None,
    subtitle: Optional[str] = None,
    duration: float = 3.0,
    background_color: str = "black",
    title_color: str = "white",
    subtitle_color: str = "0xCCCCCC",
    fontsize: int = 64,
) -> str:
    """Prepend a title screen to the beginning of a video.

    Args:
        input_path: Path to the input video.
        output_path: Optional output path. Defaults to ``<name>_titled.<ext>``.
        title: Main title text. Defaults to the input file stem.
        subtitle: Optional secondary line shown under the title.
        duration: Length of the title screen in seconds.
        background_color: Background color of the title screen.
        title_color: Title text color.
        subtitle_color: Subtitle text color.
        fontsize: Title font size.

    Returns:
        str: The output file path.
    """
    output_path = output_path or _default_output(input_path, "titled")
    title = title or Path(input_path).stem
    width, height, fps = _probe_video_info(input_path)
    font = _default_font()

    text = _drawtext_escape(title)
    drawtext = (
        f"drawtext=text='{text}'"
        f":x=(w-text_w)/2:y=(h-text_h)/2-40"
        f":fontsize={fontsize}:fontcolor={title_color}"
    )
    if subtitle:
        drawtext += (
            f",drawtext=text='{_drawtext_escape(subtitle)}'"
            f":x=(w-text_w)/2:y=(h)/2+60"
            f":fontsize={fontsize // 2}:fontcolor={subtitle_color}"
        )
    if font:
        drawtext = drawtext.replace("fontsize=", f"fontfile='{_ffmpeg_filter_path(font)}':fontsize=")

    with tempfile.TemporaryDirectory() as tmp:
        title_clip = Path(tmp) / "title.mp4"
        has_audio = _has_audio_stream(input_path)

        # 片头音轨状态与原视频保持一致，确保 concat(reencode) 能顺利拼接
        title_args: List[str] = [
            "-f", "lavfi",
            "-i", f"color=c={background_color}:s={width}x{height}:d={duration}:r={fps}",
        ]
        if has_audio:
            title_args += ["-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo"]
        title_args += ["-vf", drawtext, "-c:v", "libx264", "-pix_fmt", "yuv420p"]
        if has_audio:
            title_args += ["-c:a", "aac", "-shortest"]
        else:
            title_args += ["-an"]
        title_args += [str(title_clip)]
        _run_ffmpeg(title_args)

        concat_videos([title_clip, input_path], output_path, reencode=True)
    return str(output_path)


def extract_cover(
    input_path: StrPath,
    output_path: Optional[StrPath] = None,
    time: float = 0.5,
    width: Optional[int] = None,
) -> str:
    """Extract a still frame from a video to use as a cover/thumbnail.

    Args:
        input_path: Path to the input video.
        output_path: Optional output path. Defaults to ``<name>_cover.png``.
        time: Timestamp (in seconds) of the frame to capture.
        width: Optional output width in pixels (height is scaled proportionally).

    Returns:
        str: The output image path.
    """
    if output_path is None:
        output_path = str(Path(input_path).with_name(f"{Path(input_path).stem}_cover.png"))
    args: List[str] = ["-ss", str(time), "-i", str(input_path), "-frames:v", "1"]
    if width is not None:
        args += ["-vf", f"scale={int(width)}:-2"]
    args += [str(output_path)]
    _run_ffmpeg(args)
    return str(output_path)


__all__ = [
    "find_ffmpeg",
    "find_ffprobe",
    "remove_subtitles",
    "add_subtitles",
    "add_background_music",
    "extract_audio",
    "remove_audio",
    "concat_videos",
    "set_quality",
    "trim_video",
    "change_speed",
    "add_watermark",
    "add_title_card",
    "extract_cover",
]
