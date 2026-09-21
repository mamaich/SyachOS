#!/usr/bin/env python3
"""Кладёт в образ экранную клавиатуру LeanKey как системное приложение.

Штатная клавиатура (`com.android.inputmethod.leanback`) на консоли без
сенсорного экрана неудобна: раскладка рассчитана на пульт телевизора. LeanKey
заметно удобнее в управлении крестовиной и кнопками.

Кладётся в `/system/app/LeanKeyKeyboard/`, то есть ставится системным
приложением при первой загрузке — иначе после перепрошивки её пришлось бы
ставить руками каждый раз. Выбранной по умолчанию её делает
`tools/patch-imefix.py`: одного присутствия в образе мало, метод ввода нужно
ещё включить и выбрать.

Сам apk в репозитории не лежит: это чужая сборка. Берётся с устройства, где
клавиатура уже поставлена, или со страницы её выпусков:

    adb shell pm path com.liskovsoft.leankeyboard
    adb pull <путь> /mnt/t/Dump/RG52Mini/android/LeanKey.apk

Проверено на версии 6.1.13 (versionCode 183, minSdk 14, targetSdk 29),
размер 1 485 990 байт.
"""
import subprocess, sys, os, tempfile, zipfile

A = "/mnt/t/Dump/RG52Mini/android/"
IMG = sys.argv[1] if len(sys.argv) > 1 else A + "SyachOS-RG52Mini-V1.0.317m6.3.img"
APK = os.environ.get("LEANKEY_APK", A + "LeanKey.apk")
P4_OFF, P4_LEN = 121634816, 1577058304
DIR = "/system/app/LeanKeyKeyboard"
DST = DIR + "/LeanKeyKeyboard.apk"

if not os.path.exists(APK):
    sys.exit("нет %s — см. заголовок файла" % APK)
if not os.path.exists(IMG):
    sys.exit("нет " + IMG)

# простая проверка, что это вообще apk и он про эту клавиатуру
with zipfile.ZipFile(APK) as z:
    names = z.namelist()
    if "AndroidManifest.xml" not in names:
        sys.exit("это не apk")
    manifest = z.read("AndroidManifest.xml")
if b"leankeyboard" not in manifest.replace(b"\x00", b""):
    sys.exit("в манифесте нет имени пакета leankeyboard — файл не тот")
print("apk: %d байт" % os.path.getsize(APK))

tmp = tempfile.mkdtemp()
part = os.path.join(tmp, "p4.img")
with open(IMG, "rb") as f:
    f.seek(P4_OFF)
    open(part, "wb").write(f.read(P4_LEN))

free_before = subprocess.run(["dumpe2fs", "-h", part], capture_output=True, text=True).stdout
blocks = [l for l in free_before.splitlines() if "Free blocks" in l]
if blocks:
    print("в разделе system " + blocks[0].split(":")[1].strip() + " свободных блоков")

script = "\n".join([
    "mkdir " + DIR,
    "sif %s mode 040755" % DIR,
    "cd " + DIR,
    "rm " + DST,
    "write %s LeanKeyKeyboard.apk" % APK,
    "sif %s mode 0100644" % DST,
    "quit"]) + "\n"
subprocess.run(["debugfs", "-w", "-f", "-", part], input=script,
               capture_output=True, text=True)

r = subprocess.run(["e2fsck", "-fp", part], capture_output=True, text=True)
print("e2fsck:", r.stdout.strip().splitlines()[-1] if r.stdout.strip() else "чисто")
if r.returncode not in (0, 1):
    sys.exit("e2fsck недоволен")

back = os.path.join(tmp, "back.apk")
subprocess.run(["debugfs", "-R", "dump %s %s" % (DST, back), part],
               capture_output=True, text=True)
if not os.path.exists(back) or open(back, "rb").read() != open(APK, "rb").read():
    sys.exit("apk записался неверно")
print("сверено через ФС: %d байт" % os.path.getsize(back))

with open(IMG, "r+b") as f:
    f.seek(P4_OFF)
    f.write(open(part, "rb").read())
    f.flush()
print("образ обновлён")
