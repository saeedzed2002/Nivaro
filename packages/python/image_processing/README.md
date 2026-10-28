# Nivaro image-processing foundation

Pure, narrowly shared pixel processing for the future identity and catalog workers. No service models, credentials, storage paths, task dispatch or publication state are shared. It is not yet called by either running API or a real Celery worker.

`process_image(content, purpose="product" | "avatar")` validates a bounded byte buffer, opens only JPEG/PNG/WebP decoders, rejects animated input and excessive decoded dimensions, verifies and fully loads the raster, applies EXIF orientation and embedded color-profile conversion, then returns WebP byte outputs. Output encoding receives clean pixels only; source EXIF/GPS, comments, XMP and ICC metadata are not carried over. Invalid embedded ICC profiles fail with a safe error code. Without an embedded profile, Pillow's normal conversion is used; no claim of calibrated color fidelity for unprofiled sources.

- Maximum input: 8 MiB and 24 million pixels. Caller must bound the incoming stream before materializing bytes; this function is not a streaming upload endpoint.
- Products: target widths 320/640/1280, preserving aspect ratio, no upscale and no duplicate dimensions for small inputs. Extremely tall images also respect WebP's 16383-pixel dimension limit.
- Avatars: centered square crops at 128 and 256 pixels. User-adjustable crop coordinates are not implemented.
- All variants are produced in memory before returning. No public file or current-image pointer is written here. Replacement/atomic activation, recoverable dispatch, retries, authorization and retention belong to the owning service.
- Run only inside a worker with process memory/time limits. These limits and real worker-loss behavior remain integration work; a pure decoder test is not evidence of them.

Selected Linux checks passed: lint/format, strict mypy and 25 tests. Tests cover accepted/rejected formats, byte/pixel limits, truncation, PNG/WebP animation, orientation and metadata stripping, valid/invalid ICC handling, grayscale normalization, palette transparency, alpha, dimensions and avatar crop. See [Pillow Image](https://pillow.readthedocs.io/en/stable/reference/Image.html), [ImageOps](https://pillow.readthedocs.io/en/stable/reference/ImageOps.html) and [ImageCms](https://pillow.readthedocs.io/en/stable/reference/ImageCms.html) for the checked APIs.

The `uv.lock` fixes versions/hashes. Local preparation uses the existing mirror cache; the CI Dockerfile exports the frozen hashes and installs from an explicit builder index (official PyPI by default), preserving pins without relying on mirror reachability from external runners.

```powershell
docker build --target test -t nivaro-image-processing:test packages/python/image_processing
docker run --rm --network none nivaro-image-processing:test
```

This is a project-built test image, not an additional base image to download. Initial build still needs dependency access/cache. P04 as a whole remains unfinished.
