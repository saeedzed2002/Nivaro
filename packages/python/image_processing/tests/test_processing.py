import io
import struct
import zlib

import pytest
from PIL import Image, ImageCms, PngImagePlugin

from nivaro_image_processing import MAX_UPLOAD_BYTES, InvalidImage, process_image


def image_bytes(fmt="PNG", size=(1800, 900), mode="RGB", **kwargs):
    output = io.BytesIO()
    with Image.new(mode, size, (20, 80, 200, 90) if mode == "RGBA" else (20, 80, 200)) as image:
        image.save(output, format=fmt, **kwargs)
    return output.getvalue()


@pytest.mark.parametrize("fmt", ["PNG", "JPEG", "WEBP"])
def test_real_formats_make_three_decodable_product_variants(fmt):
    outputs = process_image(image_bytes(fmt), purpose="product")
    assert [(item.width, item.height) for item in outputs] == [(320, 160), (640, 320), (1280, 640)]
    for item in outputs:
        with Image.open(io.BytesIO(item.content)) as decoded:
            decoded.load()
            assert decoded.format == "WEBP"
            assert decoded.size == (item.width, item.height)
            assert not decoded.getexif()


@pytest.mark.parametrize(
    "content",
    [
        b"<svg></svg>",
        b"%PDF-1.7",
        b"PK\x03\x04archive",
        b"not an image",
        image_bytes("GIF"),
        image_bytes("BMP"),
    ],
)
def test_rejects_disallowed_content_even_if_upload_claims_jpeg(content):
    with pytest.raises(InvalidImage, match="invalid_image"):
        process_image(content, purpose="product")


@pytest.mark.parametrize(
    "content,code", [(b"", "empty_image"), (b"x" * (MAX_UPLOAD_BYTES + 1), "file_too_large")]
)
def test_compressed_byte_limit(content, code):
    with pytest.raises(InvalidImage, match=code):
        process_image(content, purpose="avatar")


def test_pixel_limit_checked_before_large_image_decode():
    # Valid PNG header claiming 24,006,000 pixels, without allocating that raster.
    content = bytearray(image_bytes(size=(1, 1)))
    content[16:24] = struct.pack(">II", 6000, 4001)
    content[29:33] = struct.pack(">I", zlib.crc32(content[12:29]))
    with pytest.raises(InvalidImage, match="too_many_pixels"):
        process_image(bytes(content), purpose="product")


@pytest.mark.parametrize("fmt", ["PNG", "JPEG", "WEBP"])
def test_truncated_pixel_stream_is_not_accepted(fmt):
    content = image_bytes(fmt)
    with pytest.raises(InvalidImage, match="invalid_image"):
        process_image(content[: len(content) // 2], purpose="product")


@pytest.mark.parametrize("fmt", ["PNG", "WEBP"])
def test_rejects_animated_allowed_containers(fmt):
    output = io.BytesIO()
    with Image.new("RGB", (20, 20), "red") as first, Image.new("RGB", (20, 20), "blue") as second:
        first.save(output, format=fmt, save_all=True, append_images=[second], duration=100, loop=0)
    with pytest.raises(InvalidImage, match="animated_image"):
        process_image(output.getvalue(), purpose="avatar")


def test_small_product_is_not_upscaled_or_duplicated():
    outputs = process_image(image_bytes(size=(100, 50)), purpose="product")
    assert [(item.width, item.height) for item in outputs] == [(100, 50)]


def test_orientation_corrected_before_dimensions_and_metadata_removed():
    exif = Image.Exif()
    exif[274] = 6
    exif[270] = "private source description"
    content = image_bytes("JPEG", size=(100, 50), exif=exif)
    result = process_image(content, purpose="product")[0]
    with Image.open(io.BytesIO(result.content)) as decoded:
        assert decoded.size == (50, 100)
        assert not decoded.getexif()
        assert "exif" not in decoded.info


def test_png_text_and_icc_are_not_copied_to_output():
    text = PngImagePlugin.PngInfo()
    text.add_text("Description", "private source location")
    icc = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
    content = image_bytes(size=(40, 20), pnginfo=text, icc_profile=icc)
    result = process_image(content, purpose="product")[0]
    with Image.open(io.BytesIO(result.content)) as decoded:
        assert "Description" not in decoded.info
        assert "icc_profile" not in decoded.info
        assert decoded.mode == "RGB"


def test_invalid_embedded_profile_has_controlled_error():
    content = image_bytes(size=(40, 20), icc_profile=b"invalid-profile")
    with pytest.raises(InvalidImage, match="invalid_color_profile"):
        process_image(content, purpose="product")


def test_alpha_survives_color_conversion():
    icc = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
    content = image_bytes(size=(40, 20), mode="RGBA", icc_profile=icc)
    result = process_image(content, purpose="product")[0]
    with Image.open(io.BytesIO(result.content)) as decoded:
        assert decoded.mode == "RGBA"
        assert decoded.getpixel((10, 10))[3] == 90


def test_avatar_has_fixed_square_variants_and_center_crop():
    output = io.BytesIO()
    with Image.new("RGB", (600, 300), "red") as image:
        image.paste("blue", (150, 0, 450, 300))
        image.save(output, format="PNG")
    results = process_image(output.getvalue(), purpose="avatar")
    assert [(item.width, item.height) for item in results] == [(128, 128), (256, 256)]
    with Image.open(io.BytesIO(results[1].content)) as decoded:
        r, g, b = decoded.getpixel((128, 128))
        assert b > 220 and r < 20
