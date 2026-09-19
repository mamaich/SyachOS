#!/usr/bin/env python3
"""Возвращает экран, если мост RK628 молчит: выключает его в дереве устройств.

**Применять по необходимости, в обычную сборку образа не входит.** Мост даёт
выход HDMI, и отключение его отбирает.

## Зачем

Симптом: логотип загрузчика виден, а как только стартует ядро — экран гаснет.
Панель и подсветка при этом исправны. В журнале ядра:

    rk628 4-0050: failed to access register: -110
    rk628: probe of 4-0050 failed with error -110
    rockchip-rgb ...: [drm:rockchip_rgb_bind] *ERROR* failed to find panel
                      or bridge: -517

Мост на шине i2c4 (адрес 0x50) не подтверждает адрес — это таймаут. Из-за
этого `rockchip-rgb` бесконечно отвечает `-517` («повторите позже»), и в
компонентной модели DRM незавершённый компонент **блокирует сборку всей
подсистемы**. Поэтому не выводится ничего, хотя панель DSI в полном порядке:
у неё `-517` разовый, это штатная отложенная инициализация.

Ошибка `-517` сама по себе безвредна. Гасит экран не она, а то, что компонент
так и не завершает сборку.

## Что делает

Переводит в `status = "disabled"` три узла:

    rk628@50     сам мост (в i2c@ffa30000)
    rgb          выход RGB (в syscon@ff060000)
    route-rgb    маршрут к нему в display-subsystem

Путь к экрану не трогается: `dsi`, `panel@0`, `route-dsi` и `vop` остаются
включёнными. Основной звук тоже не затрагивается — за него отвечает
`rk817-sound`, а не `rk628-sound` (звук по HDMI).

## Откат

Запустить с ключом `--вернуть`: мост включается обратно. Раздел с деревом
под Windows не смонтировать (в GPT выставлен признак, скрывающий том), так
что откат делается пересборкой образа, а не переименованием файлов.

## Если понадобится проверить сам мост

Отдельный опыт: оставить `rk628@50` включённым, а выключить только `rgb` и
`route-rgb`. Тогда экран работает, но драйвер моста по-прежнему пробуется —
подаёт питание, снимает сброс, включает опорные 24 МГц на GPIO0_A0 — и в
журнале видно, отвечает ли чип. Сканировать шину при выключенном мосте
бесполезно: он просто не запитан.

Выводы моста: i2c4 на GPIO3_B6/B7, enable-gpios GPIO3_C0 (активный высокий),
reset-gpios GPIO3_C1 (активный низкий), опорные 24 МГц на GPIO0_A0.
"""
import subprocess, sys, os, tempfile

A = "/mnt/t/Dump/RG52Mini/android/"
args = [a for a in sys.argv[1:] if not a.startswith("--")]
BACK = "--вернуть" in sys.argv or "--restore" in sys.argv
IMG = args[0] if args else A + "SyachOS-RG52Mini-V1.0.317m6.0.img"
P3_OFF = 16777216
DTB = "rk3562-rg52mini.dtb"
NODES = ["rk628@50", "rgb", "route-rgb"]

if not os.path.exists(IMG):
    sys.exit("нет " + IMG)

tmp = tempfile.mkdtemp()
env = dict(os.environ, MTOOLS_SKIP_CHECK="1")
at = "%s@@%d" % (IMG, P3_OFF)

def run(cmd, **kw):
    r = subprocess.run(cmd, capture_output=True, text=True, env=env, **kw)
    if r.returncode != 0:
        sys.exit("сбой %s%s%s" % (" ".join(cmd), chr(10), r.stderr))
    return r

cur = os.path.join(tmp, "cur.dtb")
run(["mcopy", "-o", "-i", at, "::/" + DTB, cur])
print("дерево из образа: %d байт" % os.path.getsize(cur))

dts = run(["dtc", "-I", "dtb", "-O", "dts", "-o", "-", cur]).stdout
lines = dts.split("\n")

want = "okay" if BACK else "disabled"
было = "disabled" if BACK else "okay"
changed = []
for name in NODES:
    idx = None
    for i, l in enumerate(lines):
        s = l.strip()
        if s == name + " {" or s.startswith(name + " {"):
            idx = i
            break
    if idx is None:
        sys.exit("не найден узел " + name)
    depth = 0
    for j in range(idx, min(idx + 400, len(lines))):
        s = lines[j].strip()
        if s.endswith("{"):
            depth += 1
        elif s == "};":
            depth -= 1
            if depth == 0:
                sys.exit("в узле %s нет status" % name)
        elif s.startswith("status =") and depth == 1:
            if want in s:
                print("  %-12s уже %s" % (name, want))
            else:
                lines[j] = lines[j].replace('"%s"' % было, '"%s"' % want)
                changed.append(name)
            break

if not changed:
    print("правка не нужна")
    sys.exit(0)

new_dts = os.path.join(tmp, "new.dts")
new_dtb = os.path.join(tmp, "new.dtb")
open(new_dts, "w").write("\n".join(lines))
run(["dtc", "-I", "dts", "-O", "dtb", "-o", new_dtb, new_dts])
print("  %s: %s" % ("включено" if BACK else "выключено", ", ".join(changed)))

run(["mcopy", "-o", "-i", at, new_dtb, "::/" + DTB])
back = os.path.join(tmp, "back.dtb")
run(["mcopy", "-o", "-i", at, "::/" + DTB, back])
if open(back, "rb").read() != open(new_dtb, "rb").read():
    sys.exit("дерево записалось неверно")
print("сверено через ФС: %d байт" % os.path.getsize(back))

# экран должен остаться на месте
chk = run(["dtc", "-I", "dtb", "-O", "dts", "-o", "-", back]).stdout
for node in ("dsi@", "panel@0", "route-dsi", "vop@"):
    if node not in chk:
        sys.exit("потерян узел экрана: " + node)
print("путь к экрану цел: dsi, panel, route-dsi, vop")
