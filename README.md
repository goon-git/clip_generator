# Music Video Clip Generator

A local, no-subscription Python tool for turning a full-length music video into short-form vertical clips — complete with text hooks, captions, and visual effects like vintage film grain and vignette. Everything runs on your machine using FFmpeg. No API keys, no monthly fees.

---

## Requirements

- Python 3.10+
- FFmpeg **full build** (includes `ffprobe`) — [download from ffmpeg.org](https://ffmpeg.org/download.html) or [gyan.dev](https://www.gyan.dev/ffmpeg/builds/) on Windows
- PyYAML

Install the Python dependency:

```bash
pip install pyyaml
```

Verify FFmpeg is installed:

```bash
ffmpeg -version
```

---

## Files

| File | Purpose |
|---|---|
| `clip_generator.py` | The main script |
| `clips.yaml` | Defines clip timings and visual effects |
| `captions.yaml` | Defines hooks, captions, and text styling |

---

## GUI

A desktop GUI is available as `clip_gui.py`. It requires `clip_generator.py` in the same directory.

### Additional dependency

```bash
pip install pillow
```

### Launch

```bash
python clip_gui.py
```

### Layout

The GUI has three columns:

**Left — Settings**
- Source video file picker (shows detected resolution)
- Output folder picker
- Orientation toggle — `vertical` (9:16) or `horizontal (keep original)`
- Fit mode — `crop`, `fit`, or `blur_fill`
- Crop X offset slider (for off-center subjects)
- Blur strength slider
- Text style settings (font size, color, position)
- Logo overlay (enable/disable, file, position, width, opacity, margin)
- Shuffle captions and dry run toggles

**Center — Clips & Captions**
- Clips panel — add/remove clip rows, each with start time, end time, label, effect checkboxes, and an expandable effect sliders panel (vintage, vignette, grain, fade in/out, contrast, brightness, saturation, FPS)
- Hooks & Captions panel — add/remove hook/caption pairs
- Both panels support loading and saving YAML files directly

**Right — Preview & Log**
- Preview panel — renders a single still frame at the midpoint of a clip so you can check framing, crop, and text position before a full render
- Live render log with color-coded output (green = success, red = error, amber = info)

### Render

Click **▶ RENDER CLIPS** to start. A progress bar tracks rendering clip by clip. All rendering runs on a background thread so the UI stays responsive. Output clips are saved to the configured output folder.

---

```bash
python clip_generator.py <video> <clips_config> <captions_config> [options]
```

### Arguments

| Argument | Description |
|---|---|
| `video` | Path to the input video file (e.g. `song.mp4`) |
| `clips_config` | Path to the clips YAML/JSON config |
| `captions_config` | Path to the captions YAML/JSON config |

### Options

| Flag | Description |
|---|---|
| `--output-dir PATH` | Where to save the output clips (default: `./output_clips`) |
| `--shuffle` | Randomly assign captions to clips instead of in order |
| `--dry-run` | Print the FFmpeg commands without executing them |

### Examples

Basic run:
```bash
python clip_generator.py song.mp4 clips.yaml captions.yaml
```

Custom output folder with shuffled captions:
```bash
python clip_generator.py song.mp4 clips.yaml captions.yaml --output-dir ./reels --shuffle
```

Preview what FFmpeg commands would run, without rendering:
```bash
python clip_generator.py song.mp4 clips.yaml captions.yaml --dry-run
```

---

## How It Works

1. The script reads your clips config to get the time ranges and effects for each clip.
2. It reads your captions config to get the list of hooks and captions to assign.
3. Captions are assigned to clips in order (or randomly with `--shuffle`). If you have more clips than captions, the list cycles.
4. For each clip, FFmpeg trims the segment, crops and scales to 9:16 vertical (centered crop), applies any visual effects, and burns in the hook and caption as text overlays.
5. Output clips are saved to the output directory as individual `.mp4` files, named by the clip's `label`.

---

## clips.yaml

Defines the time ranges for each clip, a global `default_effects` block that applies to all clips, and optional per-clip `effects` overrides.

### Time formats

Times can be specified in any of these formats:

```yaml
start: 90          # plain seconds
start: "1:30"      # MM:SS
start: "0:01:30"   # HH:MM:SS
```

### Clip fields

```yaml
clips:
  - label: intro        # optional — becomes the output filename (intro.mp4)
    start: 0
    end: "0:30"
    effects:            # optional — overrides default_effects for this clip only
      vintage:
        warmth: 0.4
```

If `label` is omitted, clips are named `clip_01.mp4`, `clip_02.mp4`, etc.

### default_effects

Defined at the top level of `clips.yaml`. Applied to every clip automatically. A per-clip `effects` block replaces the defaults entirely for that clip. Use `effects: {}` to explicitly apply no effects to a clip.

```yaml
default_effects:
  vintage:
    warmth: 0.35
    sepia:  0.55
    fade:   0.25
  vignette:
    angle: 0.8
  grain:
    strength: 20
  fade_in:  0.4
  fade_out: 0.4
  fps: 24
```

---

## Effects Reference

All effects can be placed in `default_effects` or in a per-clip `effects` block.

### `vintage` — warm sepia tone with faded blacks

```yaml
vintage:
  warmth: 0.35    # 0.0–1.0  how orange/amber the tint is (0 = neutral, 1 = very warm)
  sepia:  0.55    # 0.0–1.0  color drained toward brown (0 = full color, 1 = full sepia)
  fade:   0.25    # 0.0–1.0  how washed-out the blacks are (0 = deep, 1 = very faded)
```

### `vignette` — dark edges that draw focus to the center

```yaml
vignette:
  angle: 0.8    # 0.0–1.57  edge darkness (0 = none, 1.57 = very heavy)
  x0:    0.5    # 0.0–1.0   center X position (0.5 = middle)
  y0:    0.5    # 0.0–1.0   center Y position (0.5 = middle)
```

### `grain` — analog film noise overlay

```yaml
grain:
  strength: 20    # 0–100  (10 = subtle, 40 = heavy)
```

### `contrast`, `brightness`, `saturation`

```yaml
contrast:   1.2    # 0.0–2.0   (1.0 = normal)
brightness: 0.05   # -1.0–1.0  (0.0 = normal)
saturation: 0.8    # 0.0–3.0   (1.0 = normal, 0.0 = grayscale)
```

Setting `saturation: 0.0` with a raised `contrast` creates a black-and-white film look.

### `blur` and `sharpen`

```yaml
blur:
  strength: 2.0    # 0–10

sharpen:
  strength: 1.5    # 0–5
```

### `fade_in` and `fade_out`

```yaml
fade_in:  0.5    # seconds — fade from black at the start
fade_out: 0.5    # seconds — fade to black at the end
```

Can also be written as plain numbers: `fade_in: 0.5`

### `fps` — output frame rate

```yaml
fps: 24    # 24 = cinematic film feel, 30 = standard
```

### `speed` — slow or fast motion

```yaml
speed: 0.5    # 0.5 = half speed (slow motion), 2.0 = double speed
```

Audio pitch is adjusted automatically. Note: FFmpeg's `atempo` filter supports a range of 0.5–2.0.

---

## captions.yaml

Defines your hooks and captions, plus text styling options.

### Caption entries

Each entry can have a `hook` (top of frame) and/or a `caption` (bottom of frame). Either can be left blank or omitted.

```yaml
captions:
  - hook: "This one hits different 🌙"
    caption: "Follow for more instrumentals"

  - hook: "No words needed 🔥"
    caption: "Drop a 🔥 if you felt that"

  - caption: "Link in bio for the full track"    # hook omitted — bottom text only
```

Simple string shorthand (caption only, no hook):

```yaml
captions:
  - "Follow for more instrumentals"
  - "Drop a 🔥 if you felt that"
```

### `style` block

Controls the visual appearance of the text overlays and how the horizontal source is framed into the vertical canvas. All fields are optional — defaults are shown below.

```yaml
style:
  output_width:      1080          # output frame width in pixels
  output_height:     1920          # output frame height (1080×1920 = 9:16 vertical)

  # ── Framing ──────────────────────────────────────────────────────
  fit_mode:          crop          # how to map horizontal video to vertical canvas:
                                   #   crop       — crop to 9:16 (default)
                                   #   fit        — full frame scaled to fit, black bars fill rest
                                   #   blur_fill  — full frame scaled to fit, blurred video fills background

  crop_offset_x:     0.5           # (crop mode only) 0.0–1.0 — where the crop window sits horizontally
                                   #   0.5 = center (default), 0.3 = shifted left (shows more right side)
                                   #   0.7 = shifted right (shows more left side)
  crop_offset_y:     0.5           # (crop mode only) 0.0–1.0 — vertical crop position (0.5 = center)

  blur_fill_strength: 30           # (blur_fill mode only) blur intensity of the background (default: 30)

  # ── Logo overlay ─────────────────────────────────────────────────
  # Optional. Works in all three fit modes (crop, fit, blur_fill).
  # PNG with transparency recommended.
  logo:
    file:     "logo.png"      # path to your logo image
    width:    200             # width in pixels (height scales automatically)
    position: bottom_right    # top_left | top_right | bottom_left | bottom_right
                              # top_center | bottom_center
    margin:   40              # pixels from the nearest edges
    opacity:  0.85            # 0.0–1.0 (1.0 = fully opaque)
    # x: 100                 # optional: override exact X pixel position
    # y: 100                 # optional: override exact Y pixel position

  # ── Text ─────────────────────────────────────────────────────────
  hook_font_size:    72            # font size for hook text (top)
  caption_font_size: 58            # font size for caption text (bottom)
  font_color:        white         # any FFmpeg color name or hex (e.g. "#FFDD00")
  box_color:         "black@0.5"   # text background — color@opacity (0.0–1.0)
  box_border:        20            # padding around text in pixels
  hook_y:            "80"          # hook Y position — pixels from top
  caption_y:         "h-200"       # caption Y position — "h-200" = 200px from bottom
  # font_file: "/path/to/font.ttf" # optional custom font
```

### Framing mode examples

**`crop` with offset** — useful when the subject is off-center (e.g. left hand cut off):
```yaml
style:
  fit_mode: crop
  crop_offset_x: 0.35   # shift the crop window left to capture more of the right side
```

**`fit`** — shows the full horizontal frame, black bars above and below:
```yaml
style:
  fit_mode: fit
```

**`blur_fill`** — shows the full horizontal frame, blurred version of the video fills the background:
```yaml
style:
  fit_mode: blur_fill
  blur_fill_strength: 25   # lower = less blur, higher = more
```

---

## Example Workflows

**All clips with the same vintage look (set in `default_effects`, no per-clip overrides):**
```bash
python clip_generator.py song.mp4 clips.yaml captions.yaml
```

**Mix of looks — some clips vintage, one grayscale, one clean:**
Define per-clip `effects` blocks in `clips.yaml` for the clips that differ, leave the rest to inherit from `default_effects`.

**Randomize which caption goes to which clip:**
```bash
python clip_generator.py song.mp4 clips.yaml captions.yaml --shuffle
```

**Test your config without waiting for renders:**
```bash
python clip_generator.py song.mp4 clips.yaml captions.yaml --dry-run
```

---

## Output

Clips are saved to `./output_clips/` by default (or the path given with `--output-dir`). Each clip is a self-contained `.mp4` named after its `label`:

```
output_clips/
  intro.mp4
  verse1.mp4
  chorus1.mp4
  verse2.mp4
  chorus2.mp4
  outro.mp4
```

Files are encoded as H.264 video + AAC audio, optimized for streaming (`faststart`), and ready to upload directly to TikTok, Instagram Reels, or YouTube Shorts.

---

## Troubleshooting

**`ffmpeg not found`** — Make sure FFmpeg is installed and on your system PATH. You need the **full version** (not the headless/minimal build) to ensure all filters and codecs are available.

- macOS: `brew install ffmpeg`
- Ubuntu/Debian: `sudo apt install ffmpeg`
- Windows: Download a full build from [gyan.dev/ffmpeg/builds](https://www.gyan.dev/ffmpeg/builds/) (use the `ffmpeg-release-full.7z` build) and add the `bin/` folder to your system PATH.

**`ffprobe error`** — FFprobe ships with FFmpeg. If it's missing, reinstall FFmpeg.

**Clip renders but text is missing** — FFmpeg's default font may not be available on all systems. Add `font_file: "/path/to/font.ttf"` to the `style` block in `captions.yaml` pointing to any `.ttf` font on your machine.

**Effects look too strong/subtle** — Use `--dry-run` to inspect the FFmpeg filter chain, then adjust the values in your config. All effect parameters are described in the Effects Reference above.

**Audio and video are out of sync after using `speed`** — This can happen with certain source files. Try re-encoding the source first with `ffmpeg -i input.mp4 -c:v libx264 -c:a aac normalized.mp4` before running the script.
