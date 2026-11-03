"""Contact sheets for reviewing product images: audit/<name>.json -> out/audit-<name>/<n>.jpg"""
import io, json, pathlib, sys, requests
from PIL import Image, ImageDraw, ImageFont
ROOT = pathlib.Path(__file__).resolve().parent.parent
T = 220  # thumb size
def thumb(url):
    r = requests.get(url, timeout=60, headers={"User-Agent": "Mozilla/5.0"}); r.raise_for_status()
    im = Image.open(io.BytesIO(r.content)).convert("RGB"); im.thumbnail((T, T)); return im
for src in (sys.argv[1:] or [p.stem for p in (ROOT/"audit").glob("*.json")]):
    data = json.loads((ROOT/"audit"/f"{src}.json").read_text())
    out = ROOT/"out"/f"audit-{src}"; out.mkdir(parents=True, exist_ok=True)
    font = ImageFont.load_default(size=16) if hasattr(ImageFont, "load_default") else None
    rows = list(data.items()); per = 12  # products per sheet
    for s in range(0, len(rows), per):
        chunk = rows[s:s+per]; cols = 8
        sheet = Image.new("RGB", (T*cols + 10, (T+30)*len(chunk)), "white"); d = ImageDraw.Draw(sheet)
        for r, (handle, info) in enumerate(chunk):
            y = r*(T+30)
            d.text((5, y+5), f"{s+r+1}. {handle} [{info['status']}] ({len(info['images'])} imgs)", fill="black", font=font)
            for c, u in enumerate(info["images"][:cols]):
                try: sheet.paste(thumb(u), (5+c*T, y+28))
                except Exception as e: d.text((5+c*T, y+60), "ERR", fill="red", font=font)
        sheet.save(out/f"sheet-{s//per+1:02d}.jpg", quality=80)
        print("sheet", s//per+1)
