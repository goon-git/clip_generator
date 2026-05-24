#!/usr/bin/env python3
"""
Music Video Clip Generator
Splits a video into vertical short-form clips with hooks and captions burned in.

Usage:
    python clip_generator.py <video_file> <clips_config> <captions_config> [options]

Example:
    python clip_generator.py song.mp4 clips.yaml captions.yaml
    python clip_generator.py song.mp4 clips.yaml captions.yaml --output-dir ./clips --shuffle
"""

import argparse
import json
import random
import subprocess
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("PyYAML not found. Install it with: pip install pyyaml")
    sys.exit(1)


# ──────────────────────────────────────────────
# Config loading
# ──────────────────────────────────────────────

def load_config(path: Path) -> dict:
    """Load a YAML or JSON config file."""
    suffix = path.suffix.lower()
    with open(path) as f:
        if suffix in (".yaml", ".yml"):
            return yaml.safe_load(f)
        elif suffix == ".json":
            return json.load(f)
        else:
            raise ValueError(f"Unsupported config format: {suffix}. Use .yaml or .json")


def parse_clips(config: dict) -> list[dict]:
    """
    Parse clip definitions from config.
    Each clip must have start and end times (seconds or MM:SS or HH:MM:SS).
    Optional: label for the output filename, effects block for visual effects.
    """
    clips = config.get("clips", [])
    if not clips:
        raise ValueError("No clips defined in clips config. Add a 'clips' list.")

    # Global default effects (applied to all clips unless overridden per-clip)
    global_effects = config.get("default_effects", {})

    parsed = []
    for i, clip in enumerate(clips):
        start = parse_time(clip.get("start", 0))
        end = parse_time(clip.get("end"))
        if end is None:
            raise ValueError(f"Clip {i+1} is missing an 'end' time.")
        if end <= start:
            raise ValueError(f"Clip {i+1}: end time must be after start time.")

        # Merge global defaults with per-clip overrides
        clip_effects = {**global_effects, **clip.get("effects", {})}

        parsed.append({
            "index": i + 1,
            "label": clip.get("label", f"clip_{i+1:02d}"),
            "start": start,
            "end": end,
            "duration": end - start,
            "effects": clip_effects,
        })
    return parsed


def parse_captions(config: dict) -> list[dict]:
    """
    Parse captions from config.
    Each entry can have a 'hook' (top overlay) and/or 'caption' (bottom overlay).
    """
    entries = config.get("captions", [])
    if not entries:
        raise ValueError("No captions defined in captions config. Add a 'captions' list.")
    parsed = []
    for i, entry in enumerate(entries):
        if isinstance(entry, str):
            # Simple string shorthand — treat as caption only
            parsed.append({"hook": "", "caption": entry})
        else:
            parsed.append({
                "hook": entry.get("hook", ""),
                "caption": entry.get("caption", ""),
            })
    return parsed


def parse_time(value) -> float | None:
    """Convert a time value to seconds. Accepts seconds (int/float) or MM:SS / HH:MM:SS strings."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        parts = value.strip().split(":")
        try:
            parts = [float(p) for p in parts]
        except ValueError:
            raise ValueError(f"Cannot parse time value: '{value}'. Use seconds or MM:SS or HH:MM:SS.")
        if len(parts) == 2:
            return parts[0] * 60 + parts[1]
        elif len(parts) == 3:
            return parts[0] * 3600 + parts[1] * 60 + parts[2]
        else:
            raise ValueError(f"Cannot parse time value: '{value}'.")
    raise TypeError(f"Unexpected time type: {type(value)}")


# ──────────────────────────────────────────────
# FFmpeg helpers
# ──────────────────────────────────────────────

def check_ffmpeg():
    """Verify ffmpeg is installed and accessible."""
    try:
        result = subprocess.run(
            ["ffmpeg", "-version"],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            raise RuntimeError
    except (FileNotFoundError, RuntimeError):
        print("ERROR: ffmpeg not found. Install it from https://ffmpeg.org/download.html")
        sys.exit(1)


def get_video_dimensions(video_path: Path) -> tuple[int, int]:
    """Return (width, height) of the video using ffprobe."""
    cmd = [
        "ffprobe", "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height",
        "-of", "json",
        str(video_path)
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe error: {result.stderr}")
    info = json.loads(result.stdout)
    stream = info["streams"][0]
    return stream["width"], stream["height"]


def build_effects_filters(effects: dict) -> list[str]:
    """
    Translate an effects config dict into a list of ffmpeg video filter strings.

    Supported effects:
      vintage        – warm sepia tone + faded blacks (the classic old-school look)
      vignette       – dark edges that draw focus to the center
      grain          – film grain / noise overlay
      contrast       – increase/decrease contrast
      brightness     – increase/decrease brightness
      saturation     – boost or reduce color saturation (0 = grayscale, 1 = normal, 2 = vivid)
      fade_in        – fade from black at the start (duration in seconds)
      fade_out       – fade to black at the end (duration in seconds, requires clip duration)
      blur           – gaussian blur strength (0 = off, 5 = strong)
      sharpen        – unsharp mask strength (0 = off, 1 = subtle, 5 = strong)
      speed          – playback speed multiplier (0.5 = half speed, 2.0 = double speed)
      fps            – output frames per second (e.g. 24 for cinematic, 30 for standard)
    """
    filters = []

    if not effects:
        return filters

    # ── Vintage / sepia ──────────────────────────────────────────────
    if effects.get("vintage"):
        cfg = effects["vintage"] if isinstance(effects["vintage"], dict) else {}
        warmth    = cfg.get("warmth", 0.3)       # 0.0–1.0  how orange/warm the tint is
        fade      = cfg.get("fade", 0.25)         # 0.0–1.0  how washed-out / faded
        sepia     = cfg.get("sepia", 0.6)         # 0.0–1.0  desaturation toward brown
        # Desaturate partially toward sepia
        filters.append(f"hue=s={max(0.0, 1.0 - sepia):.2f}")
        # Warm color curves: lift reds, pull blues
        r_lift = min(1.0, 1.0 + warmth * 0.25)
        b_pull = max(0.0, 1.0 - warmth * 0.35)
        filters.append(
            f"curves=r='0/0 0.5/{0.5 * r_lift:.3f} 1/{r_lift:.3f}'"
            f":b='0/0 0.5/{0.5 * b_pull:.3f} 1/{b_pull:.3f}'"
        )
        # Fade blacks (lift the floor = washed out / faded look)
        if fade > 0:
            floor = fade * 0.25
            filters.append(f"curves=all='0/{floor:.3f} 1/1'")

    # ── Vignette ─────────────────────────────────────────────────────
    if effects.get("vignette"):
        cfg = effects["vignette"] if isinstance(effects["vignette"], dict) else {}
        angle  = cfg.get("angle", 0.8)    # 0.0–PI/2  how strong the darkening is
        x0     = cfg.get("x0", 0.5)       # 0.0–1.0  center X (0.5 = middle)
        y0     = cfg.get("y0", 0.5)       # 0.0–1.0  center Y (0.5 = middle)
        filters.append(
            f"vignette=angle={angle:.3f}:x0={x0:.2f}*w:y0={y0:.2f}*h:mode=forward"
        )

    # ── Film grain ───────────────────────────────────────────────────
    if effects.get("grain"):
        cfg = effects["grain"] if isinstance(effects["grain"], dict) else {}
        strength = cfg.get("strength", 25)   # 0–100 noise strength
        filters.append(f"noise=alls={strength}:allf=t+u")

    # ── Contrast ─────────────────────────────────────────────────────
    contrast = effects.get("contrast")
    if contrast is not None and contrast != 1.0:
        # ffmpeg eq contrast: 0.0–2.0, default 1.0
        filters.append(f"eq=contrast={float(contrast):.3f}")

    # ── Brightness ───────────────────────────────────────────────────
    brightness = effects.get("brightness")
    if brightness is not None and brightness != 0.0:
        # ffmpeg eq brightness: -1.0–1.0, default 0.0
        filters.append(f"eq=brightness={float(brightness):.3f}")

    # ── Saturation ───────────────────────────────────────────────────
    saturation = effects.get("saturation")
    if saturation is not None and saturation != 1.0:
        # ffmpeg eq saturation: 0.0–3.0, default 1.0
        filters.append(f"eq=saturation={float(saturation):.3f}")

    # ── Blur ─────────────────────────────────────────────────────────
    blur = effects.get("blur")
    if blur:
        strength = float(blur) if not isinstance(blur, dict) else float(blur.get("strength", 2))
        filters.append(f"gblur=sigma={strength:.1f}")

    # ── Sharpen ──────────────────────────────────────────────────────
    sharpen = effects.get("sharpen")
    if sharpen:
        strength = float(sharpen) if not isinstance(sharpen, dict) else float(sharpen.get("strength", 1))
        filters.append(f"unsharp=luma_msize_x=5:luma_msize_y=5:luma_amount={strength:.2f}")

    # ── FPS ──────────────────────────────────────────────────────────
    fps = effects.get("fps")
    if fps:
        filters.append(f"fps={int(fps)}")

    return filters


def build_speed_filter(effects: dict) -> tuple[list[str], list[str]]:
    """
    Return (video_filters, audio_filters) for speed adjustment.
    Kept separate because audio and video speed filters are different in ffmpeg.
    """
    speed = effects.get("speed")
    if not speed or float(speed) == 1.0:
        return [], []
    s = float(speed)
    v_filters = [f"setpts={1.0/s:.4f}*PTS"]
    a_filters = [f"atempo={min(2.0, max(0.5, s)):.4f}"]  # atempo range: 0.5–2.0
    return v_filters, a_filters


def build_fade_filters(effects: dict, duration: float) -> list[str]:
    """
    Return fade in/out filters. Needs clip duration for fade_out timing.
    """
    filters = []
    fade_in = effects.get("fade_in")
    if fade_in:
        d = float(fade_in) if not isinstance(fade_in, dict) else float(fade_in.get("duration", 0.5))
        filters.append(f"fade=t=in:st=0:d={d:.2f}")
    fade_out = effects.get("fade_out")
    if fade_out:
        d = float(fade_out) if not isinstance(fade_out, dict) else float(fade_out.get("duration", 0.5))
        start = max(0.0, duration - d)
        filters.append(f"fade=t=out:st={start:.2f}:d={d:.2f}")
    return filters


def build_logo_overlay(style: dict) -> tuple[str | None, str | None, str]:
    """
    Build the logo scale + overlay filter fragment for filter_complex.

    Returns (logo_path, scale_fragment, overlay_expression) where:
      logo_path         — path string to the logo file, or None if no logo configured
      scale_fragment    — filter_complex fragment that scales [logo_in] → [logo]
      overlay_expression — the overlay filter string, e.g. "[prev][logo]overlay=x:y[next]"

    The caller is responsible for wiring [prev] and [next] labels to match
    the surrounding filter_complex chain.
    """
    logo_cfg = style.get("logo")
    if not logo_cfg:
        return None, None, None

    logo_path = logo_cfg.get("file")
    if not logo_path or not Path(logo_path).exists():
        if logo_path:
            print(f"  WARNING: logo file not found: {logo_path} — skipping logo overlay")
        return None, None, None

    logo_w      = int(logo_cfg.get("width", 200))
    opacity     = float(logo_cfg.get("opacity", 1.0))
    margin      = int(logo_cfg.get("margin", 40))
    position    = logo_cfg.get("position", "bottom_right")

    # Scale logo, preserving aspect ratio. Apply opacity via format+colorchannelmixer if < 1.
    if opacity < 1.0:
        scale_frag = (
            f"[logo_in]scale={logo_w}:-1,"
            f"format=rgba,"
            f"colorchannelmixer=aa={opacity:.3f}[logo]"
        )
    else:
        scale_frag = f"[logo_in]scale={logo_w}:-1,format=rgba[logo]"

    # Position expressions (W/H = canvas, w/h = logo)
    positions = {
        "top_left":     (f"{margin}",       f"{margin}"),
        "top_right":    (f"W-w-{margin}",   f"{margin}"),
        "bottom_left":  (f"{margin}",       f"H-h-{margin}"),
        "bottom_right": (f"W-w-{margin}",   f"H-h-{margin}"),
        "top_center":   (f"(W-w)/2",        f"{margin}"),
        "bottom_center":(f"(W-w)/2",        f"H-h-{margin}"),
    }
    x_expr, y_expr = positions.get(position, positions["bottom_right"])

    # Custom x/y override
    custom_x = logo_cfg.get("x")
    custom_y = logo_cfg.get("y")
    if custom_x is not None:
        x_expr = str(custom_x)
    if custom_y is not None:
        y_expr = str(custom_y)

    overlay_expr = f"overlay={x_expr}:{y_expr}"

    return logo_path, scale_frag, overlay_expr


def build_ffmpeg_command(
    video_path: Path,
    output_path: Path,
    start: float,
    duration: float,
    hook: str,
    caption: str,
    video_width: int,
    video_height: int,
    style: dict,
    effects: dict = None,
) -> list[str]:
    """
    Build the ffmpeg command to:
      1. Trim the clip
      2. Crop & scale to 9:16 vertical
      3. Apply visual effects (vintage, grain, vignette, etc.)
      4. Burn in hook text (top) and caption text (bottom)
    """
    if effects is None:
        effects = {}

    # Target output dimensions — default 9:16 vertical.
    # In horizontal (fit_mode="none") we keep the source dimensions.
    fit_mode      = style.get("fit_mode", "crop")
    crop_offset_x = float(style.get("crop_offset_x", 0.5))
    crop_offset_y = float(style.get("crop_offset_y", 0.5))

    if fit_mode == "none":
        # Horizontal passthrough — no crop, no resize. Use source dimensions.
        out_w = video_width
        out_h = video_height
    else:
        out_w = int(style.get("output_width",  1080))
        out_h = int(style.get("output_height", 1920))

    src_ratio    = video_width  / video_height
    target_ratio = out_w / out_h

    if fit_mode == "none":
        # No framing transform — pass video through unchanged
        frame_filters = []

    elif fit_mode == "fit":
        frame_filters = [
            f"scale={out_w}:{out_h}:force_original_aspect_ratio=decrease",
            f"pad={out_w}:{out_h}:(ow-iw)/2:(oh-ih)/2:black",
        ]

    elif fit_mode == "blur_fill":
        frame_filters = [("blur_fill", out_w, out_h)]

    else:
        # crop (default) — also catches any unrecognised mode gracefully
        if src_ratio > target_ratio:
            crop_h = video_height
            crop_w = int(video_height * target_ratio)
        else:
            crop_w = video_width
            crop_h = int(video_width / target_ratio)

        max_crop_x = video_width  - crop_w
        max_crop_y = video_height - crop_h
        crop_x = int(max_crop_x * crop_offset_x)
        crop_y = int(max_crop_y * crop_offset_y)

        frame_filters = [
            f"crop={crop_w}:{crop_h}:{crop_x}:{crop_y}",
            f"scale={out_w}:{out_h}",
        ]

    # ── Text styling ──────────────────────────────────────────────────
    # Values may arrive as strings from the GUI (tk.StringVar), so cast carefully.
    font_file    = style.get("font_file", "")
    hook_size    = int(style.get("hook_font_size",    72))
    caption_size = int(style.get("caption_font_size", 58))
    font_color   = style.get("font_color", "white")
    box_color    = style.get("box_color",  "black@0.5")
    box_border   = int(style.get("box_border", 20))
    hook_y       = str(style.get("hook_y",    "80"))
    caption_y    = str(style.get("caption_y", "h-200"))

    def make_drawtext(text: str, font_size: int, y_pos: str) -> str:
        if not text:
            return None
        # Escape special characters for ffmpeg drawtext
        escaped = (
            text
            .replace("\\", "\\\\")
            .replace("'", "\\'")
            .replace(":", "\\:")
        )
        parts = [
            f"text='{escaped}'",
            f"fontsize={font_size}",
            f"fontcolor={font_color}",
            f"box=1",
            f"boxcolor={box_color}",
            f"boxborderw={box_border}",
            f"x=(w-text_w)/2",   # horizontally centered
            f"y={y_pos}",
            "line_spacing=10",
        ]
        if font_file:
            parts.insert(1, f"fontfile='{font_file}'")
        return "drawtext=" + ":".join(parts)

    # ── Detect blur_fill mode ─────────────────────────────────────────
    is_blur_fill = (
        len(frame_filters) == 1
        and isinstance(frame_filters[0], tuple)
        and frame_filters[0][0] == "blur_fill"
    )

    if is_blur_fill:
        blur_strength = int(style.get("blur_fill_strength", 30))

        # Trim video and audio inside the filter graph so duration is always
        # respected regardless of how many -i inputs are present.
        trim_v = f"[0:v]trim=start={start}:duration={duration},setpts=PTS-STARTPTS[trimmed_v]"
        trim_a = f"[0:a]atrim=start={start}:duration={duration},asetpts=PTS-STARTPTS[trimmed_a]"

        bg = (
            f"[trimmed_v]split[v_bg][v_fg];"
            f"[v_bg]scale={out_w}:{out_h}:force_original_aspect_ratio=increase,"
            f"crop={out_w}:{out_h},"
            f"gblur=sigma={blur_strength}[bg]"
        )
        fg = (
            f"[v_fg]scale={out_w}:{out_h}:force_original_aspect_ratio=decrease[fg]"
        )
        overlay = "[bg][fg]overlay=(W-w)/2:(H-h)/2[composited]"

        post_filters = []
        post_filters += build_effects_filters(effects)
        post_filters += build_fade_filters(effects, duration)
        speed_v, speed_a = build_speed_filter(effects)
        post_filters += speed_v

        hook_filter    = make_drawtext(hook, hook_size, hook_y)
        caption_filter = make_drawtext(caption, caption_size, caption_y)
        if hook_filter:
            post_filters.append(hook_filter)
        if caption_filter:
            post_filters.append(caption_filter)

        if post_filters:
            post_chain  = "[composited]" + ",".join(post_filters) + "[after_fx]"
            current_out = "[after_fx]"
        else:
            post_chain  = None
            current_out = "[composited]"

        fc_parts = [trim_v, trim_a, bg, fg, overlay]
        if post_chain:
            fc_parts.append(post_chain)

        # ── Logo overlay (blur_fill) ──────────────────────────────────
        logo_path, logo_scale, logo_overlay_expr = build_logo_overlay(style)
        extra_inputs = []
        if logo_path:
            logo_scale_frag = logo_scale.replace("[logo_in]", "[1:v]")
            fc_parts.append(logo_scale_frag)
            fc_parts.append(f"{current_out}[logo]{logo_overlay_expr}[out_v]")
            final_v = "[out_v]"
            extra_inputs = ["-i", logo_path]
        else:
            final_v = current_out

        # Audio: apply speed filter inside graph if needed, otherwise pass through
        if speed_a:
            fc_parts.append(f"[trimmed_a]{','.join(speed_a)}[out_a]")
            final_a = "[out_a]"
        else:
            final_a = "[trimmed_a]"

        filter_complex = ";".join(fc_parts)

        cmd = [
            "ffmpeg", "-y",
            "-i", str(video_path),
        ]
        cmd += extra_inputs
        cmd += [
            "-filter_complex", filter_complex,
            "-map", final_v,
            "-map", final_a,
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "18",
            "-c:a", "aac",
            "-b:a", "192k",
            "-movflags", "+faststart",
            str(output_path),
        ]
        return cmd

    # ── Standard path (crop and fit modes) ───────────────────────────
    logo_path, logo_scale, logo_overlay_expr = build_logo_overlay(style)

    filters = list(frame_filters)
    filters += build_effects_filters(effects)
    filters += build_fade_filters(effects, duration)
    speed_v, speed_a = build_speed_filter(effects)
    filters += speed_v

    hook_filter    = make_drawtext(hook, hook_size, hook_y)
    caption_filter = make_drawtext(caption, caption_size, caption_y)
    if hook_filter:
        filters.append(hook_filter)
    if caption_filter:
        filters.append(caption_filter)

    if logo_path:
        trim_v = f"[0:v]trim=start={start}:duration={duration},setpts=PTS-STARTPTS"
        trim_a = f"[0:a]atrim=start={start}:duration={duration},asetpts=PTS-STARTPTS"

        # Build main video chain — only append filters if there are any
        if filters:
            main_chain = trim_v + "," + ",".join(filters) + "[after_fx]"
        else:
            main_chain = trim_v + "[after_fx]"

        logo_scale_frag = logo_scale.replace("[logo_in]", "[1:v]")
        logo_comp       = f"[after_fx][logo]{logo_overlay_expr}[out_v]"

        if speed_a:
            audio_chain = trim_a + "," + ",".join(speed_a) + "[out_a]"
            final_a = "[out_a]"
        else:
            audio_chain = trim_a + "[out_a]"
            final_a = "[out_a]"

        filter_complex = ";".join([main_chain, logo_scale_frag, logo_comp, audio_chain])

        cmd = [
            "ffmpeg", "-y",
            "-i", str(video_path),
            "-i", logo_path,
            "-filter_complex", filter_complex,
            "-map", "[out_v]",
            "-map", final_a,
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "18",
            "-c:a", "aac",
            "-b:a", "192k",
            "-movflags", "+faststart",
            str(output_path),
        ]
        return cmd

    # No logo — simple -vf / -ss / -t path
    cmd = [
        "ffmpeg", "-y",
        "-ss", str(start),
        "-i", str(video_path),
        "-t", str(duration),
    ]
    if filters:
        cmd += ["-vf", ",".join(filters)]
    if speed_a:
        cmd += ["-af", ",".join(speed_a)]
    cmd += [
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "18",
        "-c:a", "aac",
        "-b:a", "192k",
        "-movflags", "+faststart",
        str(output_path),
    ]
    return cmd


# ──────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Generate vertical short-form clips from a music video."
    )
    parser.add_argument("video",        type=Path, help="Input video file (e.g. song.mp4)")
    parser.add_argument("clips_config", type=Path, help="YAML/JSON file defining clip timings")
    parser.add_argument("captions_config", type=Path, help="YAML/JSON file defining hooks and captions")
    parser.add_argument("--output-dir", type=Path, default=Path("output_clips"),
                        help="Directory for output clips (default: ./output_clips)")
    parser.add_argument("--shuffle", action="store_true",
                        help="Randomly assign captions to clips instead of in order")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print ffmpeg commands without running them")
    args = parser.parse_args()

    # ── Validate inputs ──
    check_ffmpeg()

    if not args.video.exists():
        print(f"ERROR: Video file not found: {args.video}")
        sys.exit(1)
    if not args.clips_config.exists():
        print(f"ERROR: Clips config not found: {args.clips_config}")
        sys.exit(1)
    if not args.captions_config.exists():
        print(f"ERROR: Captions config not found: {args.captions_config}")
        sys.exit(1)

    # ── Load configs ──
    clips_cfg    = load_config(args.clips_config)
    captions_cfg = load_config(args.captions_config)

    clips    = parse_clips(clips_cfg)
    captions = parse_captions(captions_cfg)
    style    = captions_cfg.get("style", {})

    print(f"Video:    {args.video}")
    print(f"Clips:    {len(clips)} defined")
    print(f"Captions: {len(captions)} defined")

    # ── Get source video dimensions ──
    print("\nReading video dimensions...")
    vid_w, vid_h = get_video_dimensions(args.video)
    print(f"Source:   {vid_w}x{vid_h}")

    # ── Assign captions to clips ──
    caption_pool = captions.copy()
    if args.shuffle:
        random.shuffle(caption_pool)

    assigned = []
    for i, clip in enumerate(clips):
        # Cycle through captions if there are more clips than captions
        cap = caption_pool[i % len(caption_pool)]
        assigned.append((clip, cap))

    # ── Create output directory ──
    args.output_dir.mkdir(parents=True, exist_ok=True)

    # ── Generate clips ──
    print(f"\nOutput:   {args.output_dir}/\n")
    print("─" * 60)

    success, failed = 0, 0

    for clip, cap in assigned:
        out_filename = f"{clip['label']}.mp4"
        out_path = args.output_dir / out_filename

        hook_preview    = (cap['hook'][:40] + "…") if len(cap['hook']) > 40 else cap['hook']
        caption_preview = (cap['caption'][:40] + "…") if len(cap['caption']) > 40 else cap['caption']

        print(f"Clip {clip['index']:02d}: {clip['label']}")
        print(f"  Time:    {clip['start']:.1f}s → {clip['end']:.1f}s ({clip['duration']:.1f}s)")
        if hook_preview:
            print(f"  Hook:    {hook_preview}")
        if caption_preview:
            print(f"  Caption: {caption_preview}")
        if clip.get("effects"):
            active = [k for k, v in clip["effects"].items() if v]
            if active:
                print(f"  Effects: {', '.join(active)}")

        cmd = build_ffmpeg_command(
            video_path=args.video,
            output_path=out_path,
            start=clip["start"],
            duration=clip["duration"],
            hook=cap["hook"],
            caption=cap["caption"],
            video_width=vid_w,
            video_height=vid_h,
            style=style,
            effects=clip.get("effects", {}),
        )

        if args.dry_run:
            print(f"  CMD:     {' '.join(cmd)}\n")
            continue

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            size_mb = out_path.stat().st_size / (1024 * 1024)
            print(f"  Output:  {out_filename} ({size_mb:.1f} MB) ✓\n")
            success += 1
        else:
            print(f"  ERROR:   ffmpeg failed for {out_filename}")
            print(f"  {result.stderr[-300:]}\n")
            failed += 1

    # ── Summary ──
    print("─" * 60)
    if args.dry_run:
        print(f"Dry run complete. {len(clips)} command(s) printed.")
    else:
        print(f"Done. {success} clip(s) generated, {failed} failed.")
        if success > 0:
            print(f"Clips saved to: {args.output_dir.resolve()}/")


if __name__ == "__main__":
    main()
