"""Macro FreeCAD dựng vỏ trạm hình ngôi nhà (mm), cùng kích thước với gen_enclosure.py.

Cách chạy: mở file này trong FreeCAD (File > Open) rồi bấm nút Execute macro (Ctrl+F6).
Kết quả: 2 khối "De" (đế) và "Mai" (mái), lưu thêm house.FCStd và house.step cạnh file này.
"""

import math
import os

import FreeCAD as App
import Part

V = App.Vector

LENGTH, WIDTH, HEIGHT = 230.0, 200.0, 200.0  # tổng thể
WALL, FLOOR, ROOF = 1.2, 1.0, 1.2  # độ dày
BOX_L, BOX_W, BOX_H = 138.0, 120.0, 62.0  # hộp đế
EAVE_Z = 90.0  # mép mái; khe hở = EAVE_Z - BOX_H
POST = 6.0
DRAIN_D = 5.0
BAR_W, BAR_T = 10.0, 2.4  # thanh giằng ở mép mái
PEG, PEG_H, PEG_HOLE = 3.6, 2.0, 4.0
TIE_D = 3.5  # lỗ dây rút

ROOF_H = HEIGHT - EAVE_Z
POSTS = [
    (sx * (BOX_L - POST) / 2, sy * (BOX_W - POST) / 2)
    for sx in (-1, 1)
    for sy in (-1, 1)
]


def centered_box(cx, cy, sx, sy, z0, z1):
    return Part.makeBox(sx, sy, z1 - z0, V(cx - sx / 2, cy - sy / 2, z0))


def make_base():
    base = centered_box(0, 0, BOX_L, BOX_W, 0, BOX_H).cut(
        centered_box(0, 0, BOX_L - 2 * WALL, BOX_W - 2 * WALL, FLOOR, BOX_H + 1)
    )
    for x in (-40, 0, 40):
        for y in (-30, 30):
            base = base.cut(Part.makeCylinder(DRAIN_D / 2, FLOOR + 2, V(x, y, -1)))
    for x, y in POSTS:
        post = centered_box(x, y, POST, POST, 0, EAVE_Z).fuse(
            centered_box(x, y, PEG, PEG, EAVE_Z, EAVE_Z + PEG_H)
        )
        tie = Part.makeCylinder(
            TIE_D / 2, POST + 2, V(x, y - POST / 2 - 1, EAVE_Z - 6), V(0, 1, 0)
        )
        base = base.fuse(post.cut(tie))
    return base.removeSplitter()


def face(points):
    return Part.Face(Part.makePolygon(points + [points[0]]))


def pyramid(hl, hw, h):
    corners = [V(-hl, -hw, 0), V(hl, -hw, 0), V(hl, hw, 0), V(-hl, hw, 0)]
    apex = V(0, 0, h)
    faces = [face(corners)]
    faces += [face([corners[i], corners[(i + 1) % 4], apex]) for i in range(4)]
    return Part.Solid(Part.Shell(faces))


def inner_void(hl, hw, h, t):
    """Lòng mái = giao của 2 lăng trụ tam giác, các mặt dịch vào đúng bề dày t."""
    prisms = []
    for axis, half, other in ((0, hl, hw), (1, hw, hl)):
        norm = math.hypot(h, half)
        foot = half - (t * norm - half) / h  # nửa bề rộng tại z = -1
        top = h - t * norm / half
        reach = other + 5
        if axis == 0:
            tri = [V(-foot, -reach, -1), V(foot, -reach, -1), V(0, -reach, top)]
            prisms.append(face(tri).extrude(V(0, 2 * reach, 0)))
        else:
            tri = [V(-reach, -foot, -1), V(-reach, foot, -1), V(-reach, 0, top)]
            prisms.append(face(tri).extrude(V(2 * reach, 0, 0)))
    return prisms[0].common(prisms[1])


def make_roof():
    """Mái đặt tại z = 0 (đúng tư thế in)."""
    hl, hw = LENGTH / 2, WIDTH / 2
    outer = pyramid(hl, hw, ROOF_H)
    roof = outer.cut(inner_void(hl, hw, ROOF_H, ROOF))
    y_bar = (BOX_W - POST) / 2
    for sy in (-1, 1):
        bar = centered_box(0, sy * y_bar, LENGTH, BAR_W, 0, BAR_T)
        roof = roof.fuse(bar.common(outer))
    for x, y in POSTS:
        roof = roof.cut(centered_box(x, y, PEG_HOLE, PEG_HOLE, -1, BAR_T + 1))
        tie_x = x - math.copysign(7, x)
        roof = roof.cut(Part.makeCylinder(TIE_D / 2, BAR_T + 2, V(tie_x, y, -1)))
    return roof.removeSplitter()


def main():
    doc = App.newDocument("NhaTram")
    objects = []
    for name, shape, z, color in (
        ("De", make_base(), 0.0, (0.93, 0.84, 0.45)),
        ("Mai", make_roof(), EAVE_Z, (0.45, 0.68, 0.38)),
    ):
        obj = doc.addObject("Part::Feature", name)
        obj.Shape = shape
        obj.Placement.Base = V(0, 0, z)
        if App.GuiUp:
            obj.ViewObject.ShapeColor = color
        objects.append(obj)
        App.Console.PrintMessage(
            f"{name}: hợp lệ={shape.isValid()}, số khối={len(shape.Solids)}, "
            f"thể tích={shape.Volume / 1000:.1f} cm3\n"
        )
    doc.recompute()

    folder = os.path.dirname(os.path.abspath(__file__))
    doc.saveAs(os.path.join(folder, "house.FCStd"))
    Part.export(objects, os.path.join(folder, "house.step"))

    if App.GuiUp:
        import FreeCADGui as Gui

        Gui.activeDocument().activeView().viewIsometric()
        Gui.SendMsgToActiveView("ViewFit")


main()
