"""Pure image transformation; ownership, storage and job state stay in each service."""

import io
import warnings
from dataclasses import dataclass
from typing import Literal

from PIL import Image, ImageCms, ImageOps, UnidentifiedImageError

MAX_UPLOAD_BYTES = 8 * 1024 * 1024
MAX_DECODED_PIXELS = 24_000_000
_FORMATS = ("JPEG", "PNG", "WEBP")


class InvalidImage(ValueError):
    """Safe stable error code; never expose decoder internals or uploaded metadata."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class ImageOutput:
    target: int
    width: int
    height: int
    content: bytes
    content_type: str = "image/webp"


def _validate_header(image: Image.Image) -> None:
    if image.width * image.height > MAX_DECODED_PIXELS:
        raise InvalidImage("too_many_pixels")
    if getattr(image, "n_frames", 1) != 1 or getattr(image, "is_animated", False):
        raise InvalidImage("animated_image")


def _normalize(image: Image.Image) -> Image.Image:
    oriented = ImageOps.exif_transpose(image)
    has_alpha = "A" in oriented.getbands() or "transparency" in oriented.info
    mode = "RGBA" if has_alpha else "RGB"
    icc = oriented.info.get("icc_profile")
    if icc:
        try:
            profile = ImageCms.ImageCmsProfile(io.BytesIO(icc))
            # Preserve original mode for CMYK/LAB source-profile conversion.
            base = oriented.convert("RGBA") if has_alpha else oriented
            if base.mode == "P":
                base = base.convert("RGB")
            converted = ImageCms.profileToProfile(
                base, profile, ImageCms.createProfile("sRGB"), outputMode=mode
            )
            if converted is None:
                raise InvalidImage("invalid_color_profile")
        except (ImageCms.PyCMSError, TypeError, ValueError, OSError) as exc:
            raise InvalidImage("invalid_color_profile") from exc
    else:
        converted = oriented.convert(mode)
    # Copy pixels only; EXIF, GPS, comments, XMP and source ICC cannot follow outputs.
    clean = Image.new(mode, converted.size)
    clean.paste(converted)
    return clean


def process_image(
    content: bytes, *, purpose: Literal["product", "avatar"]
) -> tuple[ImageOutput, ...]:
    """Decode at most 8 MiB/24 MP and return all variants, without writing files.

    Call only inside a resource/time-limited worker, not an async API event loop.
    Services must bound the incoming stream before constructing these bytes.
    """
    if purpose not in ("product", "avatar"):
        raise ValueError("Unknown image purpose")
    if not content:
        raise InvalidImage("empty_image")
    if len(content) > MAX_UPLOAD_BYTES:
        raise InvalidImage("file_too_large")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(content), formats=list(_FORMATS)) as header:
                _validate_header(header)
                header.verify()
            # verify() does not decode pixels; reopen and load to reject truncation.
            with Image.open(io.BytesIO(content), formats=list(_FORMATS)) as decoded:
                _validate_header(decoded)
                decoded.load()
                normalized = _normalize(decoded)
    except InvalidImage:
        raise
    except (Image.DecompressionBombWarning, Image.DecompressionBombError) as exc:
        raise InvalidImage("too_many_pixels") from exc
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError) as exc:
        raise InvalidImage("invalid_image") from exc

    outputs: list[ImageOutput] = []
    seen: set[tuple[int, int]] = set()
    try:
        for target in (320, 640, 1280) if purpose == "product" else (128, 256):
            if purpose == "avatar":
                variant = ImageOps.fit(
                    normalized, (target, target), method=Image.Resampling.LANCZOS
                )
            else:
                # Width targets with no upscaling; also respect WebP's maximum dimension.
                scale = min(1.0, target / normalized.width, 16383 / normalized.height)
                size = (
                    max(1, int(normalized.width * scale)),
                    max(1, int(normalized.height * scale)),
                )
                if size in seen:
                    continue
                seen.add(size)
                variant = normalized.resize(size, Image.Resampling.LANCZOS)
            with variant:
                stream = io.BytesIO()
                variant.save(stream, format="WEBP", quality=85, method=4)
                outputs.append(
                    ImageOutput(target, variant.width, variant.height, stream.getvalue())
                )
    finally:
        normalized.close()
    return tuple(outputs)
