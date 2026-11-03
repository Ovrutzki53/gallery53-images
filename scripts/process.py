"""Gallery 53 image pipeline.

Reads every jobs/*.json that has no matching out/<job>/done.json and produces:
  - cutout tiles: object cut from the background, centred on a flat palette colour, square
  - scenes: product photo placed into a styled scene by Gemini (Nano Banana)

Job file format (jobs/<name>.json):
{
  "product": "silver-sculpted-vase",
  "images": ["https://...jpg", ...],          # source photos (CJ)
  "tiles": [{"src": 0, "bg": "#EFEBE4"}],     # cutout tiles to make
  "scenes": [{"src": 0, "prompt": "..."}],    # AI scenes to make (needs GEMINI_API_KEY)
  "size": 2000, "padding": 0.18
}
"""
import base64, io, json, os, pathlib, sys, time
import requests
from PIL import Image

ROOT = pathlib.Path(__file__).resolve().parent.parent
JOBS, OUT = ROOT / "jobs", ROOT / "out"
UA = {"User-Agent": "Mozilla/5.0 (gallery53-image-pipeline)"}
GEMINI_MODELS = [m for m in os.environ.get("GEMINI_MODEL", "").split(",") if m] or [
    "gemini-nano-banana-2.1", "gemini-3.1-flash-image", "gemini-2.5-flash-image"]
MONTHLY_CAP = int(os.environ.get("MONTHLY_IMAGE_CAP", "100"))
USAGE = ROOT / "usage"


def usage_path():
    return USAGE / (time.strftime("%Y-%m") + ".json")


def usage_count():
    p = usage_path()
    return json.loads(p.read_text())["images"] if p.exists() else 0


def usage_add(model):
    USAGE.mkdir(exist_ok=True)
    p = usage_path()
    d = json.loads(p.read_text()) if p.exists() else {"images": 0, "by_model": {}}
    d["images"] += 1
    d["by_model"][model] = d["by_model"].get(model, 0) + 1
    p.write_text(json.dumps(d, indent=2))


def fetch(url):
    r = requests.get(url, headers=UA, timeout=60)
    r.raise_for_status()
    return Image.open(io.BytesIO(r.content)).convert("RGBA")


def hex_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


_session = None
def cutout(img):
    global _session
    from rembg import remove, new_session
    if _session is None:
        _session = new_session("isnet-general-use")
    cut = remove(img, session=_session, alpha_matting=True)
    # bbox on a thresholded alpha so faint matting haze doesn't count as object
    alpha = cut.getchannel("A").point(lambda a: 255 if a > 40 else 0)
    bbox = alpha.getbbox()
    return cut.crop(bbox) if bbox else cut


def tile(obj, bg, size, padding):
    canvas = Image.new("RGB", (size, size), hex_rgb(bg))
    inner = int(size * (1 - 2 * padding))
    scale = inner / max(obj.width, obj.height)   # fit the object to the padded box (up or down)
    o = obj.resize((max(1, round(obj.width * scale)), max(1, round(obj.height * scale))), Image.LANCZOS)
    x, y = (size - o.width) // 2, (size - o.height) // 2
    canvas.paste(o, (x, y), o)
    return canvas


def scene(img, prompt):
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY secret is not set")
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "JPEG", quality=92)
    body = {"contents": [{"parts": [
        {"inline_data": {"mime_type": "image/jpeg", "data": base64.b64encode(buf.getvalue()).decode()}},
        {"text": prompt},
    ]}]}
    if usage_count() >= MONTHLY_CAP:
        raise RuntimeError(f"Monthly cap of {MONTHLY_CAP} generated images reached - not calling Gemini")
    for model in GEMINI_MODELS:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        for attempt in range(3):
            r = requests.post(url, params={"key": key}, json=body, timeout=180)
            if r.status_code == 429:
                time.sleep(20 * (attempt + 1)); continue
            break
        if r.status_code == 404:
            print(f"model {model} not found, trying next"); continue
        r.raise_for_status()
        usage_add(model)  # count every successful (billed) call, even if no image came back
        for cand in r.json().get("candidates", []):
            for part in cand.get("content", {}).get("parts", []):
                data = part.get("inline_data") or part.get("inlineData")
                if data:
                    return Image.open(io.BytesIO(base64.b64decode(data["data"]))).convert("RGB")
        raise RuntimeError(f"Gemini ({model}) returned no image: " + r.text[:500])
    raise RuntimeError("No Gemini image model available: " + ", ".join(GEMINI_MODELS))


def run(job_path):
    job = json.loads(job_path.read_text())
    out = OUT / job_path.stem
    out.mkdir(parents=True, exist_ok=True)
    size, pad = job.get("size", 1600), job.get("padding", 0.18)
    srcs, cuts, log = {}, {}, {"job": job_path.name, "files": [], "errors": []}

    def src(i):
        if i not in srcs:
            srcs[i] = fetch(job["images"][i])
            srcs[i].convert("RGB").save(out / f"source-{i}.jpg", quality=92)
        return srcs[i]

    for n, t in enumerate(job.get("tiles", [])):
        try:
            i = t.get("src", 0)
            if i not in cuts:
                cuts[i] = cutout(src(i))
                cuts[i].save(out / f"cutout-{i}.png")
            name = f"tile-{n}-{t['bg'].lstrip('#')}.jpg"
            tile(cuts[i], t["bg"], size, pad).save(out / name, quality=90, optimize=True)
            log["files"].append(name)
        except Exception as e:
            log["errors"].append(f"tile {n}: {e}")

    for n, s in enumerate(job.get("scenes", [])):
        try:
            name = f"scene-{n}.jpg"
            scene(src(s.get("src", 0)), s["prompt"]).save(out / name, quality=90, optimize=True)
            log["files"].append(name)
        except Exception as e:
            log["errors"].append(f"scene {n}: {e}")

    (out / "done.json").write_text(json.dumps(log, indent=2, ensure_ascii=False))
    print(json.dumps(log, ensure_ascii=False))


if __name__ == "__main__":
    targets = [JOBS / f"{a}.json" for a in sys.argv[1:]] or sorted(JOBS.glob("*.json"))
    for p in targets:
        if (OUT / p.stem / "done.json").exists() and not sys.argv[1:]:
            continue
        run(p)
