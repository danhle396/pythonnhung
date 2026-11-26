"""Sinh file STL vỏ trạm hình ngôi nhà (đơn vị mm).

Chạy:  pip install numpy manifold3d trimesh matplotlib
       python gen_enclosure.py

Hệ trục: X = chiều dài, Y = chiều rộng, Z = chiều cao.
Gồm 2 phần rời: đế (hộp + 4 cột) và mái chóp (đặt lên 4 chốt đầu cột).
"""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import trimesh
from manifold3d import Manifold
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

OUT = Path(__file__).parent

# ---- Kích thước tổng thể ----
LENGTH, WIDTH, HEIGHT = 230.0, 200.0, 200.0

# ---- Độ dày (mỏng để tiết kiệm nhựa, bội số của đầu in 0,4 mm) ----
WALL = 1.2
FLOOR = 1.0
ROOF = 1.2

# ---- Đế ----
BOX_L, BOX_W = 138.0, 120.0  # kích thước ngoài của hộp đế
BOX_H = 62.0  # miệng hộp
EAVE_Z = 90.0  # mép mái; khe hở đưa mạch = EAVE_Z - BOX_H
POST = 6.0  # cột vuông ở 4 góc
DRAIN_D = 5.0  # lỗ thoát nước / thông gió ở đáy

# ---- Mối ghép đế - mái ----
BAR_W, BAR_T = 10.0, 2.4  # 2 thanh giằng ở mép mái
PEG, PEG_H = 3.6, 2.0
PEG_HOLE = 4.0  # hở 0,2 mm mỗi bên
TIE_D = 3.5  # lỗ luồn dây rút giữ mái

ROOF_H = HEIGHT - EAVE_Z
POSTS = [
    (sx * (BOX_L - POST) / 2, sy * (BOX_W - POST) / 2)
    for sx in (-1, 1)
    for sy in (-1, 1)
]


def box(x0, y0, z0, x1, y1, z1):
    return Manifold.cube([x1 - x0, y1 - y0, z1 - z0]).translate([x0, y0, z0])


def centered_box(cx, cy, sx, sy, z0, z1):
    return box(cx - sx / 2, cy - sy / 2, z0, cx + sx / 2, cy + sy / 2, z1)


def make_base():
    hl, hw = BOX_L / 2, BOX_W / 2
    base = box(-hl, -hw, 0, hl, hw, BOX_H) - box(
        -hl + WALL, -hw + WALL, FLOOR, hl - WALL, hw - WALL, BOX_H + 1
    )
    for x in (-40, 0, 40):
        for y in (-30, 30):
            hole = Manifold.cylinder(FLOOR + 2, DRAIN_D / 2, circular_segments=48)
            base -= hole.translate([x, y, -1])
    for x, y in POSTS:
        post = centered_box(x, y, POST, POST, 0, EAVE_Z)
        post += centered_box(x, y, PEG, PEG, EAVE_Z, EAVE_Z + PEG_H)
        # lỗ ngang (theo trục Y) cho dây rút
        tie = Manifold.cylinder(
            POST + 2, TIE_D / 2, circular_segments=48, center=True
        ).rotate([90, 0, 0])
        base += post - tie.translate([x, y, EAVE_Z - 6])
    return base


def pyramid(hl, hw, h):
    pts = [[-hl, -hw, 0], [hl, -hw, 0], [hl, hw, 0], [-hl, hw, 0], [0, 0, h]]
    return Manifold.hull_points(pts)


def inner_void(hl, hw, h, t):
    """Lòng mái: 4 mặt nghiêng dịch vào đúng bề dày t theo pháp tuyến."""
    void = box(-hl, -hw, -1, hl, hw, h)
    for axis, half in ((0, hl), (1, hw)):
        norm = np.hypot(h, half)
        for sign in (-1, 1):
            normal = [0.0, 0.0, -half / norm]
            normal[axis] = -sign * h / norm
            # giữ phía normal·p >= offset
            void = void.trim_by_plane(normal, -(half * h / norm - t))
    return void


def make_roof():
    """Mái in đúng tư thế dùng: mép mái và 2 thanh giằng nằm trên bàn in (z=0)."""
    hl, hw = LENGTH / 2, WIDTH / 2
    outer = pyramid(hl, hw, ROOF_H)
    roof = outer - inner_void(hl, hw, ROOF_H, ROOF)
    y_bar = (BOX_W - POST) / 2
    for sy in (-1, 1):
        bar = centered_box(0, sy * y_bar, LENGTH, BAR_W, 0, BAR_T)
        roof += bar ^ outer  # cắt gọn theo mặt ngoài của mái
    for x, y in POSTS:
        roof -= centered_box(x, y, PEG_HOLE, PEG_HOLE, -1, BAR_T + 1)
        tie = Manifold.cylinder(BAR_T + 2, TIE_D / 2, circular_segments=48)
        roof -= tie.translate([x - np.sign(x) * 7, y, -1])
    return roof


def split_roof(roof):
    """Cắt đôi mái cho máy in bàn nhỏ, kèm 2 bản nối dán đè lên thanh giằng."""
    plus = roof.trim_by_plane([1, 0, 0], 0)
    minus = roof.trim_by_plane([-1, 0, 0], 0)
    y_bar = (BOX_W - POST) / 2
    plates = Manifold()
    for sy in (-1, 1):
        plates += centered_box(0, sy * (y_bar - 15), 30, BAR_W - 2, 0, 1.6)
    return plus, minus, plates


def to_mesh(solid):
    m = solid.to_mesh()
    return trimesh.Trimesh(
        vertices=np.asarray(m.vert_properties)[:, :3], faces=np.asarray(m.tri_verts)
    )


def export(solid, name):
    mesh = to_mesh(solid)
    mesh.apply_translation([0, 0, -mesh.bounds[0][2]])
    assert mesh.is_watertight, f"{name}: lưới bị hở"
    mesh.export(OUT / name)
    size = mesh.extents
    grams = solid.volume() / 1000 * 1.24  # PLA 1,24 g/cm3, tính đặc 100 %
    print(
        f"{name:18s} {size[0]:6.1f} x {size[1]:6.1f} x {size[2]:6.1f} mm"
        f"   {solid.volume() / 1000:6.1f} cm3  ~{grams:4.0f} g PLA"
    )


def preview(base, roof):
    """Ảnh xem trước: lắp hoàn chỉnh và 2 phần tách rời."""
    fig = plt.figure(figsize=(14, 7))
    light = np.array([0.3, -0.7, 0.65])
    light /= np.linalg.norm(light)
    for i, (title, lift) in enumerate((("Lắp hoàn chỉnh", 0), ("Nhấc mái", 80))):
        ax = fig.add_subplot(1, 2, i + 1, projection="3d")
        polys, colors = [], []
        for solid, rgb, dz in (
            (base, (0.93, 0.84, 0.45), 0),
            (roof, (0.45, 0.68, 0.38), EAVE_Z + lift),
        ):
            mesh = to_mesh(solid.translate([0, 0, dz]))
            # chia nhỏ tam giác để matplotlib sắp thứ tự che khuất đúng hơn
            v, f = trimesh.remesh.subdivide_to_size(
                mesh.vertices, mesh.faces, max_edge=8, max_iter=20
            )
            mesh = trimesh.Trimesh(v, f, process=False)
            shade = 0.55 + 0.45 * np.abs(mesh.face_normals @ light)
            polys += list(mesh.triangles)
            colors += list(np.outer(shade, rgb))
        ax.add_collection3d(
            Poly3DCollection(polys, facecolors=colors, edgecolors=colors, linewidths=0.2)
        )
        top = HEIGHT + lift
        ax.set(xlim=(-120, 120), ylim=(-120, 120), zlim=(0, top), title=title)
        ax.set_box_aspect((240, 240, top))
        ax.view_init(elev=14, azim=-52)
        ax.set_axis_off()
    fig.tight_layout()
    fig.savefig(OUT / "preview.png", dpi=110)


def main():
    base, roof = make_base(), make_roof()
    placed = roof.translate([0, 0, EAVE_Z])
    assert (base ^ placed).volume() < 1e-3, "đế và mái đè lên nhau"
    total = to_mesh(base + placed).extents
    assert np.allclose(total, [LENGTH, WIDTH, HEIGHT], atol=0.01), total

    export(base, "base.stl")
    export(roof, "roof.stl")
    plus, minus, plates = split_roof(roof)
    export(plus, "roof_half_A.stl")
    export(minus, "roof_half_B.stl")
    export(plates, "roof_splice.stl")
    preview(base, roof)

    gap = EAVE_Z - BOX_H
    print(f"Tổng thể: {total[0]:.0f} x {total[1]:.0f} x {total[2]:.0f} mm")
    print(f"Khe hở đưa mạch: cao {gap:.0f} mm, giữa 2 cột: "
          f"{BOX_L - 2 * POST:.0f} mm (mặt dài), {BOX_W - 2 * POST:.0f} mm (mặt hông)")
    for label, over in (("mặt dài", (WIDTH - BOX_W) / 2), ("mặt hông", (LENGTH - BOX_L) / 2)):
        angle = np.degrees(np.arctan2(over, gap))
        print(f"Mái đua {over:.0f} mm ({label}): che mưa tạt tới {angle:.0f}° so với phương đứng")
    print(f"Lòng hộp: {BOX_L - 2 * WALL:.1f} x {BOX_W - 2 * WALL:.1f} mm")
    print(f"Độ nghiêng mái so với phương ngang: "
          f"{np.degrees(np.arctan(ROOF_H / (LENGTH / 2))):.1f}° / "
          f"{np.degrees(np.arctan(ROOF_H / (WIDTH / 2))):.1f}°")


if __name__ == "__main__":
    main()
