from PIL import Image

from parkwild.pano import _crop_wrapped, slice_equirectangular, slice_path_for, slices_dir_for, variant_name, variant_yaw


def test_variant_names():
    assert variant_name(90) == "yaw090" and variant_name(360) == "yaw000"
    assert variant_yaw("yaw270") == 270.0 and variant_yaw("full") is None


def test_paths(tmp_path):
    pano_dir = tmp_path / "lamar_valley_pano"
    assert slices_dir_for(pano_dir) == tmp_path / "lamar_valley_pano_slices"
    assert slice_path_for(pano_dir / "1.jpg", "1", "yaw090") == tmp_path / "lamar_valley_pano_slices" / "1__yaw090.jpg"


def test_crop_wrapped_stitches_across_the_seam():
    im = Image.new("RGB", (100, 10), "white")
    im.paste((255, 0, 0), (0, 0, 10, 10))       # red at the left edge
    im.paste((0, 0, 255), (90, 0, 100, 10))     # blue at the right edge
    out = _crop_wrapped(im, 90, 110, 0, 10)     # window straddling the seam
    assert out.size == (20, 10)
    assert out.getpixel((5, 5)) == (0, 0, 255) and out.getpixel((15, 5)) == (255, 0, 0)


def test_slice_equirectangular_geometry(tmp_path):
    W, H = 720, 360   # 2 px per degree
    im = Image.new("RGB", (W, H), "white")
    im.paste((255, 0, 0), (W // 2 - 2, H // 2 - 2, W // 2 + 2, H // 2 + 2))   # red dot at frame centre = yaw 0, pitch 0
    src = tmp_path / "pano.jpg"
    im.save(src)
    paths = slice_equirectangular(src, "p", tmp_path / "out", hfov_deg=90, vfov_deg=60)
    assert [p.name for p in paths] == ["p__yaw000.jpg", "p__yaw090.jpg", "p__yaw180.jpg", "p__yaw270.jpg"]
    s0 = Image.open(paths[0])
    assert s0.size == (180, 120)                             # 90 deg x 2 px, 60 deg x 2 px
    r, g, b = s0.getpixel((90, 60))
    assert r > 200 and g < 80                                # the centre dot sits at the centre of yaw000
    s180 = Image.open(paths[2])
    assert s180.getpixel((90, 60)) == (255, 255, 255)        # and not in the opposite window
    assert slice_equirectangular(src, "p", tmp_path / "out") == paths   # idempotent
