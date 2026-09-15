#!/usr/bin/env python3
"""Собирает образ раздела resource: логотип загрузки и кадры зарядки.

Зачем: в образе SyachOS раздел `resource` пуст (4 МБ нулей), поэтому U-Boot
нечего показать ни при загрузке, ни в режиме зарядки — отсюда чёрный экран
с мигающим курсором и «зависание» при включении с воткнутым кабелем.
Разбор: docs/11-boot-logo.md

Формат RSCE описан в `scripts/resource_tool.c` ядра Rockchip:

    заголовок (1 блок):  "RSCE", версия, размеры в блоках, число записей
    таблица (N блоков):  "ENTR", имя[220], hash[32], hash_size, блок, размер
    содержимое:          файлы, выровненные по блокам 512 байт

Свой сборщик, а не сам `resource_tool`, нужен ради одной вещи: `logo.bmp`
и `logo_kernel.bmp` побайтно одинаковы, и две записи указывают на **одну**
копию данных. Иначе 5,5 МБ не влезут в раздел на 4 МБ.

Первый логотип показывает U-Boot, второй он же передаёт ядру через
зарезервированную область `drm-logo`, чтобы картинка не мигала при передаче
управления.
"""
import sys, os, struct, hashlib

BLK = 512
HDR_MAGIC = b"RSCE"
ENTRY_TAG = b"ENTR"
NAME_LEN = 220
HASH_LEN = 32

def blocks(n):
    return (n + BLK - 1) // BLK

def build(files, dedup=None):
    """files: список (имя_в_образе, путь_к_файлу). dedup: имя -> имя-источник."""
    dedup = dedup or {}
    names = [n for n, _ in files] + list(dedup)
    nentries = len(names)
    data_start = 1 + nentries          # заголовок + таблица, в блоках

    content = bytearray()
    where = {}                         # имя -> (блок, размер, sha1)
    for name, path in files:
        raw = open(path, "rb").read()
        where[name] = (data_start + blocks(len(content)), len(raw),
                       hashlib.sha1(raw).digest())
        content += raw
        content += b"\x00" * (blocks(len(raw)) * BLK - len(raw))

    hdr = bytearray(BLK)
    hdr[0:4] = HDR_MAGIC
    struct.pack_into("<HH", hdr, 4, 0, 0)      # версии
    hdr[8] = 1                                 # размер заголовка, блоков
    hdr[9] = 1                                 # смещение таблицы, блоков
    hdr[10] = 1                                # размер записи, блоков
    struct.pack_into("<I", hdr, 12, nentries)  # число записей

    table = bytearray()
    for name in names:
        src = dedup.get(name, name)
        blk, size, sha = where[src]
        e = bytearray(BLK)
        e[0:4] = ENTRY_TAG
        e[4:4+len(name)] = name.encode()
        e[224:224+20] = sha                    # sha1, как кладёт resource_tool
        struct.pack_into("<III", e, 256, 20, blk, size)
        table += e

    return bytes(hdr) + bytes(table) + bytes(content)

def parse(img):
    """Разбор обратно — для сверки."""
    nentries = struct.unpack("<I", img[12:16])[0]
    out = []
    for i in range(nentries):
        e = img[(1 + i) * BLK:(2 + i) * BLK]
        name = e[4:4+NAME_LEN].split(b"\x00")[0].decode()
        hash_size, blk, size = struct.unpack("<III", e[256:268])
        out.append((name, blk, size, img[blk*BLK:blk*BLK+size]))
    return out

if __name__ == "__main__":
    src = sys.argv[1] if len(sys.argv) > 1 else "/home/mamaich/rg52/logo"
    out = sys.argv[2] if len(sys.argv) > 2 else os.path.join(src, "resource.img")
    PART_SIZE = 4 * 1024 * 1024        # раздел resource в образе

    files = [("logo.bmp", os.path.join(src, "logo.bmp"))]
    for n in ("battery_0.bmp", "battery_1.bmp", "battery_2.bmp", "battery_3.bmp",
              "battery_4.bmp", "battery_5.bmp", "battery_fail.bmp"):
        files.append((n, os.path.join(src, n)))
    for _, p in files:
        if not os.path.exists(p):
            sys.exit("нет файла " + p)

    img = build(files, dedup={"logo_kernel.bmp": "logo.bmp"})
    if len(img) > PART_SIZE:
        sys.exit("образ %d байт, а раздел %d" % (len(img), PART_SIZE))
    open(out, "wb").write(img)
    print("собрано: %s, %d байт из %d доступных" % (out, len(img), PART_SIZE))

    print("сверка обратным разбором:")
    ok = True
    by_name = dict((n, p) for n, p in files)
    for name, blk, size, data in parse(img):
        ref = by_name.get(name) or by_name["logo.bmp"]
        same = data == open(ref, "rb").read()
        ok = ok and same
        kind = ""
        if data[:2] == b"BM":
            w, h = struct.unpack("<ii", data[18:26])
            kind = "BMP %dx%d" % (w, abs(h))
        print("  %-20s блок %5d  %8d байт  %-12s %s"
              % (name, blk, size, kind, "совпадает" if same else "РАСХОЖДЕНИЕ"))
    sys.exit(0 if ok else 1)
