"""Build the 90-second demo video from real captures of the running app."""
import json, pathlib, subprocess, textwrap

S = pathlib.Path(__file__).parent
OUT = S / "out"; OUT.mkdir(exist_ok=True)
SANS = "/usr/share/fonts/liberation/LiberationSans-Regular.ttf"
BOLD = "/usr/share/fonts/liberation/LiberationSans-Bold.ttf"
MONO = "/usr/share/fonts/TTF/FiraCodeNerdFontMono-Light.ttf"
PIPER = [str(S / "tts/bin/piper"), "-m", str(S / "voice/en_US-lessac-medium.onnx"), "--length_scale", "1.05"]
W, H, FPS = 1920, 1080, 30

def run(cmd, **kw):
    subprocess.run(cmd, check=True, capture_output=True, **kw)

def duration(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                       capture_output=True, text=True, check=True)
    return float(r.stdout.strip())

# ---- slides that are not screenshots -------------------------------------------------

def title_slide(path, big, small):
    run(["magick", "-size", f"{W}x{H}", "xc:#1d1d1f",
         "-font", BOLD, "-fill", "white", "-pointsize", "120", "-gravity", "center", "-annotate", "+0-60", big,
         "-font", SANS, "-fill", "#a1a1a6", "-pointsize", "44", "-annotate", "+0+70", small, str(path)])

def terminal_slide(path, heading, body):
    run(["magick", "-size", f"{W}x{H}", "xc:#1d1d1f",
         "-font", SANS, "-fill", "#a1a1a6", "-pointsize", "34", "-gravity", "northwest", "-annotate", "+140+110", heading,
         "-font", MONO, "-fill", "#e8e8ed", "-pointsize", "30", "-interline-spacing", "8",
         "-annotate", "+140+190", body, str(path)])

mcp = json.loads((S / "mcp.json").read_text())
lines = ['generate_revision_checklist("the cell membrane and mitochondria")', ""]
for item in mcp["items"]:
    lines.append(f'{item["n"]}. {item["step"]}')
    lines.append(f'   why: {item["why"]}')
    if item["source"]:
        lines.append(f'   source: {item["source"]}')
lines += ["", f'based on: {", ".join(mcp["based_on"])}   ·   saved to history']
terminal_slide(S / "15-mcp.png", "MCP tool — called by any AI assistant", "\n".join(lines))

pytest_line = (S / "pytest.txt").read_text().strip()
terminal_slide(S / "16-tests.png", "Tests — no model, no network needed",
    "$ cd api && pytest\n" + pytest_line + "\n\n$ cd mcp-server && pytest\n20 passed in 0.5s\n\n"
    "CI: api · mcp · web — green on every push\n\n\ngithub.com/ezitounioussama/recall-study-assistant")
title_slide(S / "00-title.png", "Recall", "Cited answers and spaced repetition from your own notes")
title_slide(S / "17-end.png", "Recall", "github.com/ezitounioussama/recall-study-assistant")

# ---- the script ---------------------------------------------------------------------------
# (frames with relative weights, spoken line, on-screen caption, honesty tag)
SCENES = [
    ([("00-title.png", 1)],
     "Re-reading notes feels like learning, but it's mostly recognition. And chatbots answer from the internet, not from your course.",
     "", ""),
    ([("01-landing.png", 1), ("01b-landing-product.png", 1)],
     "Recall studies with you, using only your own notes.",
     "Answers only from your own material", ""),
    ([("02-library-before.png", 1), ("03-uploading.png", 1), ("04-library-after.png", 2)],
     "Upload a lecture. It is split into passages and embedded on this laptop. Nothing leaves the machine.",
     "Upload → passages → local embeddings (Ollama)", ""),
    ([("05-chat-typed.png", 1.2)] + [(f"06-chat-stream-{i}.png", 0.5) for i in range(1, 7)] + [("07-chat-answer.png", 1.4), ("08-chat-citation.png", 1.6)],
     "Ask a question. The sources appear first, then the answer streams in, and every number links to the exact passage it came from.",
     "Sources first · streamed answer · clickable citations", "sped up"),
    ([("09-chat-refusal.png", 1)],
     "If your notes don't cover it, Recall says so. No model is even called.",
     "Not in your notes? It refuses instead of guessing", ""),
    ([("10-generating.png", 1), ("11-cards-generated.png", 1.4)],
     "One click writes flashcards from the material.",
     "Flashcards generated from each passage", "sped up"),
    ([("12-review-question.png", 1), ("13b-review-buttons.png", 1.6)],
     "The FSRS memory model schedules every card, and each button shows when you will see it again.",
     "FSRS-5 spaced repetition · interval shown before you rate", ""),
    ([("14-email.png", 1)],
     "Every morning, an n8n automation emails the student what is due.",
     "n8n daily reminder, delivered by email", ""),
    ([("15-mcp.png", 1)],
     "And any AI assistant can ask for a revision checklist, through an MCP server.",
     "", ""),
    ([("16-tests.png", 1)],
     "Three hundred and twelve tests, all running locally. One limitation: a small model is slow on a CPU. Next, we fit the memory model to each student.",
     "", ""),
    ([("17-end.png", 1)], "Recall.", "", ""),
]

from PIL import Image, ImageDraw, ImageFont

CAP_FONT = ImageFont.truetype(SANS, 40)
TAG_FONT = ImageFont.truetype(BOLD, 28)

def frame(src, dst, caption, tag):
    canvas = Image.new("RGB", (W, H), "#1d1d1f")
    shot = Image.open(S / src).convert("RGB")
    scale = min(W / shot.width, H / shot.height)
    shot = shot.resize((round(shot.width * scale), round(shot.height * scale)), Image.LANCZOS)
    canvas.paste(shot, ((W - shot.width) // 2, (H - shot.height) // 2))
    draw = ImageDraw.Draw(canvas, "RGBA")
    if caption:
        box = draw.textbbox((0, 0), caption, font=CAP_FONT)
        tw, th = box[2] - box[0], box[3] - box[1]
        pw, ph = tw + 72, th + 44
        x, y = (W - pw) // 2, H - ph - 56
        draw.rounded_rectangle((x, y, x + pw, y + ph), radius=ph // 2, fill=(29, 29, 31, 235))
        draw.text((x + 36 - box[0], y + 22 - box[1]), caption, font=CAP_FONT, fill="white")
    if tag:
        box = draw.textbbox((0, 0), tag, font=TAG_FONT)
        tw, th = box[2] - box[0], box[3] - box[1]
        x, y = W - tw - 48 - 36, 40
        draw.rounded_rectangle((x, y, x + tw + 36, y + th + 24), radius=10, fill="#fdcb63")
        draw.text((x + 18 - box[0], y + 12 - box[1]), tag, font=TAG_FONT, fill="#1d1d1f")
    canvas.save(dst)

segments, audios = [], []
for n, (frames, line, caption, tag) in enumerate(SCENES):
    wav = OUT / f"s{n:02}.wav"
    run(PIPER + ["-f", str(wav)], input=line.encode())
    spoken = duration(wav)
    length = max(spoken + 1.8, 1.9 * len(frames) if len(frames) < 4 else 9.0, 3.0)
    total_w = sum(w for _, w in frames)
    listing = OUT / f"s{n:02}.txt"
    parts = []
    for i, (src, w) in enumerate(frames):
        dst = OUT / f"s{n:02}_{i:02}.png"
        frame(src, dst, caption, tag)
        parts.append(f"file '{dst}'\nduration {length * w / total_w:.3f}")
    parts.append(f"file '{dst}'")  # concat demuxer needs the last file repeated
    listing.write_text("\n".join(parts) + "\n")
    seg = OUT / f"s{n:02}.mp4"
    fade_out = max(length - 0.25, 0)
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(listing),
         "-i", str(wav),
         "-filter_complex",
         f"[0:v]fps={FPS},format=yuv420p,fade=t=in:st=0:d=0.25,fade=t=out:st={fade_out:.3f}:d=0.25[v];"
         f"[1:a]adelay=250|250,apad,atrim=0:{length:.3f},aresample=44100[a]",
         "-map", "[v]", "-map", "[a]", "-t", f"{length:.3f}",
         "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-c:a", "aac", "-b:a", "160k", str(seg)])
    segments.append(seg)
    print(f"scene {n:2}: {length:5.1f}s  {line[:60]}")

concat = OUT / "segments.txt"
concat.write_text("".join(f"file '{s}'\n" for s in segments))
final = S / "recall-demo-90s.mp4"
run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat), "-c", "copy", str(final)])
print("TOTAL", round(duration(final), 1), "s ->", final)
