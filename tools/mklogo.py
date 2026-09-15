#!/usr/bin/env python3
"""Делает из BMP логотип для ядра (CONFIG_LOGO, формат clut224).

Зачем: U-Boot на этой прошивке ничего нарисовать не может — его дерево
устройств не знает об экране, — поэтому первым, что включает дисплей,
оказывается ядро. Логотип, встроенный в ядро, рисует `fbcon` сразу после
инициализации кадрового буфера, и чёрный экран с мигающим курсором пропадает.
Разбор: docs/11-boot-logo.md

Две тонкости, которые легко проглядеть:

**Поворот.** Панель физически 720x1280, консоль развёрнута `fbcon=rotate:1`,
то есть по часовой стрелке. Ядро поворачивает логотип тем же преобразованием,
значит на вход ему нужна картинка, повёрнутая **против** часовой: 1280x720.
Отсюда и проверка размеров в ядре — ширина логотипа должна помещаться в
`yres` панели, а высота в `xres`.

**224 цвета.** Формат clut224 держит палитру из 224 цветов, а в исходном
логотипе их две тысячи — почти все от сглаживания краёв. Палитра строится по
самым частым цветам, остальные притягиваются к ближайшему; для картинки из
фона и знака это незаметно.

    python3 tools/mklogo.py logo.bmp logo_linux_clut224.ppm
"""
import sys, os, struct, collections

MAX_COLORS = 224

def read_bmp24(path):
    d = open(path, "rb").read()
    if d[:2] != b"BM":
        sys.exit("не BMP: " + path)
    off = struct.unpack("<I", d[10:14])[0]
    w, h = struct.unpack("<ii", d[18:26])
    bpp = struct.unpack("<H", d[28:30])[0]
    if bpp != 24:
        sys.exit("ожидается 24 бита на пиксель, а не %d" % bpp)
    bottom_up = h > 0
    h = abs(h)
    stride = (w * 3 + 3) & ~3
    rows = []
    for y in range(h):
        base = off + y * stride
        line = d[base:base + w * 3]
        rows.append([(line[x*3+2], line[x*3+1], line[x*3]) for x in range(w)])
    if bottom_up:
        rows.reverse()
    return w, h, rows

def rotate_ccw(w, h, rows):
    """Против часовой: (w,h) -> (h,w). Ядро повернёт обратно по часовой."""
    out = []
    for y in range(w):            # новая высота = старая ширина
        out.append([rows[x][w - 1 - y] for x in range(h)])
    return h, w, out

def quantize(rows, max_colors=MAX_COLORS):
    cnt = collections.Counter()
    for r in rows:
        cnt.update(r)
    if len(cnt) <= max_colors:
        return rows, len(cnt)
    palette = [c for c, _ in cnt.most_common(max_colors)]
    # соответствие считаем один раз на каждый исходный цвет, а не на пиксель
    table = {}
    for c in cnt:
        best, bd = palette[0], None
        for p in palette:
            d = (c[0]-p[0])**2 + (c[1]-p[1])**2 + (c[2]-p[2])**2
            if bd is None or d < bd:
                best, bd = p, d
                if d == 0:
                    break
        table[c] = best
    return [[table[c] for c in r] for r in rows], max_colors

def write_ppm(path, w, h, rows):
    """Только текстовый P3: pnmtologo в ядре 5.10 двоичный PNM не принимает
    («Binary PNM is not supported»). Файл выходит большой, но в сборке он промежуточный."""
    with open(path, "w") as f:
        f.write("P3\n# SyachOS boot logo\n%d %d\n255\n" % (w, h))
        for r in rows:
            f.write(" ".join("%d %d %d" % px for px in r))
            f.write("\n")

if __name__ == "__main__":
    src = sys.argv[1] if len(sys.argv) > 1 else "/home/mamaich/rg52/logo/logo.bmp"
    dst = sys.argv[2] if len(sys.argv) > 2 else "/home/mamaich/rg52/logo/logo_linux_clut224.ppm"
    rotate = "--no-rotate" not in sys.argv

    w, h, rows = read_bmp24(src)
    print("исходник: %dx%d" % (w, h))
    if rotate:
        w, h, rows = rotate_ccw(w, h, rows)
        print("после поворота против часовой: %dx%d" % (w, h))
    rows, ncolors = quantize(rows)
    print("цветов после приведения к палитре: %d" % ncolors)
    write_ppm(dst, w, h, rows)
    print("записано: %s (%d байт)" % (dst, os.path.getsize(dst)))
