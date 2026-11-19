from io import BytesIO
from pathlib import Path
import hashlib
import re
from PIL import Image, ImageDraw
from rescuelink.protocol.application import Message

MAX_IMAGE = 512 * 1024
MAX_PIXELS = 4_000_000

def inspect_image(data):
    if not data or len(data) > MAX_IMAGE:
        raise ValueError("image must be 1..524288 bytes")
    try:
        with Image.open(BytesIO(data)) as image:
            if image.format not in ("PNG", "JPEG") or image.width*image.height > MAX_PIXELS:
                raise ValueError("only PNG/JPEG, at most 4 million pixels")
            image.load()
            return image.convert("RGB"), image.format
    except (OSError, Image.DecompressionBombError) as exc:
        raise ValueError("invalid image") from exc

def prepare_image(data, image_id):
    image, fmt = inspect_image(data)
    size = image.size
    image.thumbnail((48, 36))
    buf = BytesIO()
    image.save(buf, "JPEG", quality=35, optimize=True)
    return dict(image_id=image_id, sha256=hashlib.sha256(data).hexdigest(), size=len(data),
                width=size[0], height=size[1], format=fmt, preview_size=len(buf.getvalue()),
                text="现场图像：先预览，再接收完整证据"), buf.getvalue()

def receive_image(network, frame, m):
    host = network.hosts[frame.dst]
    key = (frame.src, m.request_id)
    try:
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", m.request_id):
            raise ValueError("unsafe image id")
        if m.type == "IMAGE_META":
            if not (1 <= m.meta["size"] <= MAX_IMAGE and re.fullmatch(r"[a-f0-9]{64}", m.meta["sha256"])):
                raise ValueError("invalid image metadata")
            if m.meta["format"] not in ("PNG", "JPEG") or not 1 <= m.meta["width"]*m.meta["height"] <= MAX_PIXELS:
                raise ValueError("image dimensions/format")
            host.images[key] = dict(meta=m.meta, preview=None, original=None, verified=False,
                                    metadata_time=network.now, preview_time=None, full_time=None)
            return Message("READY", m.request_id, {"next": "preview"})
        if key not in host.images:
            raise ValueError("metadata required")
        state = host.images[key]
        if m.type == "IMAGE_PREVIEW":
            inspect_image(m.body)
            if len(m.body) != state["meta"]["preview_size"]:
                raise ValueError("preview size mismatch")
            state.update(preview=m.body, preview_time=network.now)
            network.log("preview_available", image_id=m.request_id, host=frame.dst, bytes=len(m.body))
            return Message("READY", m.request_id, {"next": "original"})
        if m.type == "IMAGE_ORIGINAL":
            meta = state["meta"]
            if len(m.body) != meta["size"] or hashlib.sha256(m.body).hexdigest() != meta["sha256"]:
                raise ValueError("SHA-256/length mismatch")
            image, fmt = inspect_image(m.body)
            if list(image.size) != [meta["width"], meta["height"]] or fmt != meta["format"]:
                raise ValueError("image identity mismatch")
            network.output_dir.mkdir(parents=True, exist_ok=True)
            dest = network.output_dir / f"host{frame.dst}_src{frame.src}_{m.request_id}.{'png' if fmt == 'PNG' else 'jpg'}"
            if dest.resolve().parent != network.output_dir.resolve():
                raise ValueError("unsafe output path")
            dest.write_bytes(m.body)
            state.update(original=m.body, full_time=network.now, verified=True, path=str(dest.resolve()))
            network.log("image_complete", image_id=m.request_id, host=frame.dst, sha256=meta["sha256"], bytes=len(m.body))
            return Message("IMAGE_RECEIVED", m.request_id, {"sha256": meta["sha256"], "verified": True})
    except (ValueError, KeyError, TypeError) as exc:
        network.log("image_error", image_id=m.request_id, reason=str(exc))
        return Message("ERROR", m.request_id, {"reason": str(exc)})

def demo_image(path=None):
    image = Image.new("RGB", (192, 128), "#172e3d")
    d = ImageDraw.Draw(image)
    for x in range(0, 192, 16):
        for y in range(0, 128, 16):
            d.rectangle((x, y, x+14, y+14), fill=(35+x//3, 65+y//2, 85))
    d.polygon([(0,110),(45,50),(82,90),(130,25),(192,105)], fill="#738e7f")
    d.rectangle((105,60,140,93), fill="#f0e4cc")
    d.rectangle((118,51,126,102), fill="#e45545")
    d.rectangle((103,72,142,81), fill="#e45545")
    d.text((8,8), "RESCUELINK / SECTOR 04", fill="white")
    buf = BytesIO()
    image.save(buf, "PNG")
    data = buf.getvalue()
    if path:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_bytes(data)
    return data
