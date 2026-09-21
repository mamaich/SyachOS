#!/usr/bin/env python3
"""Сокращает выключение с шести с половиной секунд до двух с половиной.

## Куда уходило время

`init` при выключении пытается отмонтировать `/data` и не может: раздел занят
вложенными привязками, которые создаёт `vold` — `/data/user/0` и три в
`/data_mirror`. Сам `vold` к этому моменту уже убит сигналом 9 и разобрать их
не успевает. `init` повторяет попытку каждые сто миллисекунд, пока не упрётся
в общий таймаут `ro.build.shutdown_timeout`, по умолчанию **6 секунд**.

Измерено по журналу прошлой загрузки (`/sys/fs/pstore/console-ramoops-0`):

    таймаут 6:   6473 мс, 54 неудачные попытки
    таймаут 2:   2498 мс, 13 попыток

## Чем это не является

Это **обход, а не лечение**: `/data` по-прежнему не отмонтируется, просто
`init` перестаёт биться об стену лишние четыре секунды. Данным это не
угрожает — `sync()` выполняется до попыток размонтирования и занимает 9 мс,
а в журнале следующей загрузки нет ни одной записи о восстановлении
файловой системы.

Настоящее лечение — разбирать привязки `vold` до того, как его убьют. Это
требует правки порядка выключения в `init.rc` и здесь не делалось.

## Что проверялось и не помогло

Сначала подозрение пало на раздел `cache`: он смонтирован **внутрь** `/data`
(путь `/cache` — символическая ссылка на `/data/cache`) и при этом пуст,
17 КБ служебных папок. Версия выглядела убедительно, но опыт её не
подтвердил: без этого монтирования выключение заняло 6408 мс против 6473 —
в пределах погрешности. Строка в `fstab` возвращена как была.
"""
import subprocess, sys, os, tempfile

A = "/mnt/t/Dump/RG52Mini/android/"
IMG = sys.argv[1] if len(sys.argv) > 1 else A + "SyachOS-RG52Mini-V1.0.317m6.3.img"
P5_OFF, P5_LEN = 1698693120, 267046912
PROP = "/build.prop"
KEY = "ro.build.shutdown_timeout"
VALUE = os.environ.get("SHUTDOWN_TIMEOUT", "2")

if not os.path.exists(IMG):
    sys.exit("нет " + IMG)

tmp = tempfile.mkdtemp()
part = os.path.join(tmp, "p5.img")
with open(IMG, "rb") as f:
    f.seek(P5_OFF)
    open(part, "wb").write(f.read(P5_LEN))

def dump(path, dst):
    subprocess.run(["debugfs", "-R", "dump %s %s" % (path, dst), part],
                   capture_output=True, text=True)
    return open(dst, "rb").read() if os.path.exists(dst) else None

old = dump(PROP, os.path.join(tmp, "prop"))
if old is None:
    sys.exit("не нашёл " + PROP)

lines = old.decode().split("\n")
found = [i for i, l in enumerate(lines) if l.startswith(KEY + "=")]
if not found:
    sys.exit("в build.prop нет %s — образ не тот, что ожидался" % KEY)
if len(found) > 1:
    sys.exit("строка %s встречается %d раз" % (KEY, len(found)))

cur = lines[found[0]].split("=", 1)[1]
if cur == VALUE:
    print("уже %s=%s, правка не нужна" % (KEY, VALUE))
    sys.exit(0)
lines[found[0]] = "%s=%s" % (KEY, VALUE)
print("%s: %s -> %s" % (KEY, cur, VALUE))
new = "\n".join(lines)

p_new = os.path.join(tmp, "build.prop")
open(p_new, "w").write(new)
script = "\n".join(["rm " + PROP, "cd /", "write %s build.prop" % p_new,
                    "sif %s mode 0100644" % PROP, "quit"]) + "\n"
subprocess.run(["debugfs", "-w", "-f", "-", part], input=script,
               capture_output=True, text=True)

r = subprocess.run(["e2fsck", "-fp", part], capture_output=True, text=True)
print("e2fsck:", r.stdout.strip().splitlines()[-1] if r.stdout.strip() else "чисто")
if r.returncode not in (0, 1):
    sys.exit("e2fsck недоволен")

back = dump(PROP, os.path.join(tmp, "back"))
if back.decode() != new:
    sys.exit("build.prop записался неверно")
print("сверено через ФС: %d байт" % len(back))

with open(IMG, "r+b") as f:
    f.seek(P5_OFF)
    f.write(open(part, "rb").read())
    f.flush()
print("образ обновлён")
