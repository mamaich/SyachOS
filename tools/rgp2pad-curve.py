#!/usr/bin/env python3
"""Меняет кривую скорости курсора в /vendor/bin/rgp2pad.

Демон rgp2pad перехватывает сырой геймпад (retrogame_joypad) и создаёт два
виртуальных устройства: "Xbox Wireless Controller" и "rgp2pad-mouse". Аккорд
L3+R3 переключает режим мыши. Скорость курсора считается так:

    если |ось| >= 2501:
        norm  = (|ось| - 2500) / 30267        , не больше 1.0
        шаг   = ±MAX * norm ** POW            , пикселей за опрос (16 мс)
    накопитель хранит дробную часть, поэтому медленное движение возможно

MAX и POW зашиты как непосредственные операнды FMOV, по три штуки на каждую
из двух осей. Их и правим — по месту, длина файла не меняется.

    python3 rgp2pad-curve.py <вход> <выход> --pow 2.5 [--max 24]

Значения ограничены тем, что кодируется в FMOV: ±(1 + n/16) * 2**e,
n = 0..15, e = -3..4. Скрипт проверит и подскажет ближайшее.
"""
import struct, sys, argparse

# адреса инструкций (виртуальные, imagebase 0x200000)
SITES_POW = [0x21c198, 0x21c1e4]                       # показатель степени
SITES_MAX = [(0x21c174, +1), (0x21c1c0, +1),           # максимум, знак +
             (0x21c184, -1), (0x21c1d0, -1)]           # максимум, знак -
SITE_DIV_LO = 0x21ace4                                 # MOVZ W8, #младшие 16
SITE_DIV_HI = 0x21acec                                 # MOVK W8, #старшие 16, LSL#16

def fmov_decode(imm8):
    """Значение по 8-битному полю FMOV (одинарная точность)."""
    sign = (imm8 >> 7) & 1
    b    = (imm8 >> 6) & 1
    cd   = (imm8 >> 4) & 3
    frac = imm8 & 0xF
    exp8 = ((0 if b else 1) << 7) | ((0x1F if b else 0) << 2) | cd
    return (-1.0) ** sign * 2.0 ** (exp8 - 127) * (1.0 + frac / 16.0)

def fmov_encode(value):
    """8-битное поле FMOV для значения, или None если не кодируется."""
    for imm8 in range(256):
        if abs(fmov_decode(imm8) - value) < 1e-9:
            return imm8
    return None

def fmov_options():
    seen = sorted({round(fmov_decode(i), 6) for i in range(256) if fmov_decode(i) > 0})
    return seen

def elf_vaddr_to_off(data, vaddr):
    """Смещение в файле по виртуальному адресу, через таблицу сегментов."""
    if data[:4] != b"\x7fELF" or data[4] != 2:
        sys.exit("не 64-битный ELF")
    phoff  = struct.unpack_from("<Q", data, 0x20)[0]
    phentsz, phnum = struct.unpack_from("<HH", data, 0x36)
    for i in range(phnum):
        p = phoff + i * phentsz
        p_type = struct.unpack_from("<I", data, p)[0]
        if p_type != 1:            # PT_LOAD
            continue
        p_off, p_va, _, p_filesz = struct.unpack_from("<QQQQ", data, p + 8)
        if p_va <= vaddr < p_va + p_filesz:
            return p_off + (vaddr - p_va)
    sys.exit("адрес 0x%x не попал ни в один загружаемый сегмент" % vaddr)

def read_fmov(data, off):
    insn = struct.unpack_from("<I", data, off)[0]
    if (insn & 0xFF800000) != 0x1E200000 or (insn & 0x1F) == 0 and False:
        pass
    if (insn & 0x1F001C00) != 0x1E001000 and (insn >> 24) != 0x1E:
        sys.exit("по смещению 0x%x не FMOV: 0x%08x" % (off, insn))
    return insn, (insn >> 13) & 0xFF

def write_fmov(data, off, insn, imm8):
    new = (insn & ~(0xFF << 13)) | (imm8 << 13)
    struct.pack_into("<I", data, off, new)
    return new

ap = argparse.ArgumentParser()
ap.add_argument("src"); ap.add_argument("dst")
ap.add_argument("--pow", type=float, default=None, help="новый показатель степени")
ap.add_argument("--max", type=float, default=None, help="новая максимальная скорость, px за опрос")
ap.add_argument("--div", type=float, default=None,
                help="делитель нормировки; ставить (реальный максимум оси - 2500), "
                     "чтобы полная скорость достигалась на упоре стика")
ap.add_argument("--list", action="store_true", help="показать кодируемые значения")
a = ap.parse_args()

if a.list:
    print("кодируется FMOV:", ", ".join("%g" % v for v in fmov_options()))
    sys.exit(0)

data = bytearray(open(a.src, "rb").read())
print("исходный файл: %d байт" % len(data))

def apply(sites, value, what):
    if value is None:
        return
    imm8 = fmov_encode(abs(value))
    if imm8 is None:
        opts = [v for v in fmov_options() if 0.5 <= v <= 40]
        near = min(opts, key=lambda v: abs(v - abs(value)))
        sys.exit("%g не кодируется в FMOV; ближайшее %g\nдопустимые: %s"
                 % (value, near, ", ".join("%g" % v for v in opts)))
    for item in sites:
        addr, sign = item if isinstance(item, tuple) else (item, +1)
        off = elf_vaddr_to_off(data, addr)
        insn, old = read_fmov(data, off)
        imm = imm8 | (0x80 if sign < 0 else 0)
        new = write_fmov(data, off, insn, imm)
        print("  0x%x (файл 0x%x): %s %g -> %g   [0x%08x -> 0x%08x]"
              % (addr, off, what, fmov_decode(old), fmov_decode(imm), insn, new))

apply(SITES_POW, a.pow, "показатель")
apply(SITES_MAX, a.max, "максимум")

if a.div is not None:
    bits = struct.unpack("<I", struct.pack("<f", a.div))[0]
    for addr, imm16, kind, base in ((SITE_DIV_LO, bits & 0xFFFF, "MOVZ", 0x52800000),
                                    (SITE_DIV_HI, bits >> 16,    "MOVK", 0x72A00000)):
        off = elf_vaddr_to_off(data, addr)
        insn = struct.unpack_from("<I", data, off)[0]
        # маска 0xFFE00000: включает биты сдвига hw, иначе MOVK LSL#16 не отличить
        if (insn & 0xFFE00000) != base:
            sys.exit("по 0x%x ожидался %s, а там 0x%08x" % (addr, kind, insn))
        rd = insn & 0x1F
        new_insn = base | (imm16 << 5) | rd
        struct.pack_into("<I", data, off, new_insn)
        print("  0x%x (файл 0x%x): %s #0x%04x -> #0x%04x   [0x%08x -> 0x%08x]"
              % (addr, off, kind, (insn >> 5) & 0xFFFF, imm16, insn, new_insn))
    print("  делитель -> %g (полная скорость на |оси| = %g)" % (a.div, a.div + 2500))

open(a.dst, "wb").write(data)
print("записан %s, %d байт" % (a.dst, len(data)))

# таблица скоростей для наглядности
p = a.pow if a.pow is not None else 1.5
m = a.max if a.max is not None else 24.0
print()
print("отклонение стика -> пикселей за опрос (16 мс) -> точек в секунду")
for frac in (0.1, 0.25, 0.5, 0.75, 1.0):
    old = 24.0 * frac ** 1.5
    new = m * frac ** p
    print("  %3.0f%%   было %6.2f (%5.0f/с)   стало %6.2f (%5.0f/с)"
          % (frac * 100, old, old * 62.5, new, new * 62.5))
