#!/bin/bash
# Проверяет, что в готовом образе присутствуют все внесённые правки.
# Запускать в WSL:  bash /mnt/t/Dump/RG52Mini/android/verify-image.sh [образ.img]
set -u
A=/mnt/t/Dump/RG52Mini/android
# Образ можно указать первым аргументом; по умолчанию — рабочий.
IMG=${1:-$A/SyachOS-RG52Mini-V1.0.317m6.0.img}
B=$A/bt-payload
T=$(mktemp -d); trap "rm -rf $T" EXIT
P3_OFF=16777216;   P3_LEN=103809024
P4_OFF=121634816;  P4_LEN=1577058304
P5_OFF=1698693120; P5_LEN=267046912
OK=0; BAD=0
say() { if [ "$1" = y ]; then printf '  \033[32mOK\033[0m   %s\n' "$2"; OK=$((OK+1)); else printf '  \033[31mНЕТ\033[0m  %s\n' "$2"; BAD=$((BAD+1)); fi; }
chk() { if [ -n "$1" ]; then say y "$2"; else say n "$2"; fi; }

dd if=$IMG of=$T/p3 bs=4M iflag=skip_bytes,count_bytes skip=$P3_OFF count=$P3_LEN status=none
dd if=$IMG of=$T/p4 bs=4M iflag=skip_bytes,count_bytes skip=$P4_OFF count=$P4_LEN status=none
dd if=$IMG of=$T/p5 bs=4M iflag=skip_bytes,count_bytes skip=$P5_OFF count=$P5_LEN status=none
d5() { debugfs -R "dump $1 $2" $T/p5 >/dev/null 2>&1; }
d4() { debugfs -R "dump $1 $2" $T/p4 >/dev/null 2>&1; }
export MTOOLS_SKIP_CHECK=1

echo "== 1. Wi-Fi и Bluetooth (vendor)"
# Модули могут быть из тихой сборки (bt-payload) или из нашей сборки ядра:
# при CONFIG_MODVERSIONS они обязаны совпадать с тем ядром, что лежит в образе.
KBUILD=/home/mamaich/rg52/out-rg52
for m in aic8800_bsp aic8800_fdrv; do
  if d5 /lib/modules/$m.ko $T/m; then
    if cmp -s $T/m $B/$m.ko; then say y "$m.ko — тихая сборка (bt-payload)"
    elif cmp -s $T/m $KBUILD/$m.ko; then say y "$m.ko — наша сборка ядра"
    else say n "$m.ko не совпал ни с одной известной сборкой"; fi
  else say n "$m.ko"; fi
done
d5 /lib64/libbt-vendor.so $T/x;  [ "$(stat -c %s $T/x 2>/dev/null)" = 10056 ] && say y "libbt-vendor.so — наша прослойка" || say n "libbt-vendor.so"
d5 /lib64/libbt-vendor-seekwave.so $T/x; [ "$(stat -c %s $T/x 2>/dev/null)" = 10056 ] && say y "libbt-vendor-seekwave.so — наша прослойка" || say n "libbt-vendor-seekwave.so"
d5 /lib64/libbt-vendor.so.orig $T/x && say y "оригинал сохранён как .orig" || say n ".orig"
chk "$(debugfs -R 'ls /etc/firmware/aic8800' $T/p5 2>/dev/null | grep -o fmacfwbt_8800d80_h_u02.bin)" "блобы D80 на месте (комбо-прошивка BT)"
# Обе строки insmod aic8800 должны быть ЗАКОММЕНТИРОВАНЫ: драйвер выбирается
# по факту железа, иначе на ревизии A оба чипа дерутся за общее питание.
# Старая проверка считала строки не глядя на комментарий и была бесполезна.
d5 /etc/init.insmod.cfg $T/x
chk "$(grep -c '^#insmod .*aic8800_' $T/x | grep 2)" "обе строки insmod aic8800 закомментированы"
if grep -qE '^[^#]*insmod .*aic8800_' $T/x; then say n "незакомментированный insmod aic8800 (сломает ревизию A)"; else say y "незакомментированного insmod aic8800 нет"; fi
d5 /bin/wifi_pick.sh $T/x && chk "$(grep -c 'aic8800_bsp' $T/x)" "wifi_pick.sh — выбор драйвера по факту железа" || say n "wifi_pick.sh"
d5 /etc/init/rg52-wifi.rc $T/x && chk "$(grep -c 'vendor.all.modules.ready' $T/x)" "служба rg52_wifi_pick по готовности модулей" || say n "rg52-wifi.rc"
d4 /system/etc/sysconfig/rg52-no-tv.xml $T/x
if grep -q 'hardware.bluetooth' $T/x; then say n "блокировка возможности BT снята"; else say y "блокировка возможности BT снята"; fi

echo "== 2..7. Остальные правки"
d5 /build.prop $T/bp
chk "$(grep -c '^bluetooth.profile' $T/bp | grep 6)" "шесть свойств bluetooth.profile"
chk "$(grep -o 'flinger_standbytime_ms=3000' $T/bp)" "standbytime = 3000 (усилитель засыпает)"
d5 /etc/fstab.rk30board $T/x
chk "$(grep -o 'zramsize=100%' $T/x)" "zram 100% ОЗУ"
d5 /etc/init/init.tee-supplicant.rc $T/x
if grep -q '^#   start tee-supplicant' $T/x; then say y "tee-supplicant: явный start закомментирован"; else say n "tee-supplicant: start"; fi
# одного комментария мало: class core поднимается через class_start
if grep -q '^    disabled$' $T/x; then say y "tee-supplicant: disabled (иначе поднимет class_start core)"; else say n "tee-supplicant: disabled"; fi
mtype -i $T/p3 ::/extlinux/extlinux.conf > $T/x 2>/dev/null
chk "$(grep -o 'loglevel=5' $T/x)" "loglevel=5 (иначе fbcon гасит логотип)"
if grep -q 'ignore_loglevel' $T/x; then say n "ignore_loglevel убран"; else say y "ignore_loglevel убран"; fi
chk "$(grep -o '^TIMEOUT 10' $T/x)" "TIMEOUT 10 (меню U-Boot 1 с)"
# Единственная console= в строке: U-Boot подменит её на свой ttyFIQ0, и
# экранной консоли не останется — логотип не будет залит текстом.
chk "$(grep -o 'console=tty1' $T/x)" "одна console=tty1 (экранной консоли не будет)"
if grep -q 'ttyFIQ0\|earlycon' $T/x; then say n "ttyFIQ0/earlycon убраны из строки"; else say y "ttyFIQ0/earlycon убраны из строки"; fi
mtype -i $T/p3 ::/rk3562-rg52mini.dtb > $T/dtb 2>/dev/null
mtype -i $T/p3 ::/Image > $T/kimg 2>/dev/null
if strings $T/kimg 2>/dev/null | grep -q "loa filter"; then
  printf '  [36mИНФО[0m ядро нашей сборки: есть фильтр ложного babble в USB
'
  chk "$(dtc -I dtb -O dts -o - $T/dtb 2>/dev/null | grep -o 'loa-filter-en-quirk')" "свойство loa-filter-en-quirk в DTB (парное к ядру)"
  chk "$(dtc -I dtb -O dts -o - $T/dtb 2>/dev/null | grep -o 'rockchip,high-temp')" "защита от перегрева выше 95 C в DTB"
else
  printf '  [36mИНФО[0m ядро авторское, без фильтра babble
'
fi
# Эти два свойства нужны независимо от того, чьё ядро в образе.
chk "$(dtc -I dtb -O dts -o - $T/dtb 2>/dev/null | grep -o 'husb311')" "контроллер Type-C HUSB311 в DTB (без него нет USB host)"
chk "$(dtc -I dtb -O dts -o - $T/dtb 2>/dev/null | grep -o 'spk-mute-delay-ms')" "задержка отключения динамика в DTB (щелчки звука)"

# KernelSU: номер версии не вычисляется сам — у вкопированного KernelSU-Next
# нет своей истории git, и номер зашит запасным значением в
# drivers/kernelsu/Kbuild. Ядро, собранное без него, снаружи выглядит
# нормально, но управляющее приложение видит версию 0.0.1 и прав не даёт.
# Тег рядом с номером — единственный признак, видимый в двоичном файле.
ktag=$(strings $T/kimg 2>/dev/null | grep -oE 'v3\.[0-9]+\.[0-9]+' | sort -u | head -1)
if [ -n "$ktag" ]; then
  say y "KernelSU собран с номером версии ($ktag)"
else
  say n "в ядре нет тега версии KernelSU — приложение увидит 0.0.1 и прав не даст"
fi
# Самая надёжная проверка: ядро в образе — ровно то, что лежит в сборке.
# Именно рассинхрон здесь один раз и вернул версию KernelSU к 0.0.1: правку
# накатили на устройство, а в образ ядро положить забыли.
if [ -f $KBUILD/Image ]; then
  cmp -s $T/kimg $KBUILD/Image && say y "ядро в образе совпадает со сборкой ($KBUILD)"                               || say n "ядро в образе НЕ из текущей сборки — пересоберите образ"
fi

# Детекторы зависаний: khungtaskd — имя потока DETECT_HUNG_TASK, "soft lockup"
# печатает SOFTLOCKUP_DETECTOR. Без них ядро при зависании молчит навсегда.
if strings $T/kimg 2>/dev/null | grep -q "khungtaskd"; then
  say y "ядро умеет замечать зависания (DETECT_HUNG_TASK)"
  # Логотип виден по таблице цветов: 224 записи подряд в .data ядра не
  # отличить надёжно, поэтому смотрим на размер — картинка 1280x720 весит
  # ровно 900 КБ и без неё Image заметно меньше.
  ksz=$(stat -c %s $T/kimg)
  [ "$ksz" -gt 44500000 ] && say y "в ядре есть логотип загрузки (Image $ksz)" \
                          || say n "логотип в ядре (Image $ksz — маловат)"
  # Отключённое оставляет пустоту: строки этих подсистем должны исчезнуть.
  if strings $T/kimg 2>/dev/null | grep -q "CRED: Invalid credentials"; then
    say n "DEBUG_CREDENTIALS выключен"; else say y "DEBUG_CREDENTIALS выключен"; fi
  if strings $T/kimg 2>/dev/null | grep -q "usercopy:"; then
    say n "HARDENED_USERCOPY выключен"; else say y "HARDENED_USERCOPY выключен"; fi
  strings $T/kimg 2>/dev/null | grep -q "soft lockup" \
    && say y "детектор softlockup" || say n "детектор softlockup"
fi

chk "$(dtc -I dtb -O dts -o - $T/dtb 2>/dev/null | grep -o 'spk-mute-delay-ms')" "spk-mute-delay-ms в DTB"
chk "$(dtc -I dtb -O dts -o - $T/dtb 2>/dev/null | grep -o 'hynetek,husb311')" "контроллер Type-C в DTB (USB host)"
d4 /system/bin/anim_fix.sh $T/af && chk "$(grep -c animator_duration_scale $T/af)" "скрипт anim_fix.sh (фризы интерфейса)" || say n "anim_fix.sh"
d4 /system/etc/init/init.perf.rc $T/rc && chk "$(grep -c "start anim_fix" $T/rc)" "запуск anim_fix по sys.boot_completed" || say n "init.perf.rc"
# Важно именно значение: при нуле фризов нет, но пропадает видимый ход
# выполнения — в маркетплейсах не рисуется полоса установки apk.
chk "$(grep -o 'SCALE=0.25' $T/af)" "скорость анимации 0.25 (не ноль — иначе не виден прогресс)"
d4 /system/bin/usbmode $T/usbmode
if [ -s $T/usbmode ] && cmp -s $T/usbmode $A/usbmode; then say y "утилита usbmode"; else say n "usbmode"; fi
d4 /system/product/overlay/RG52MiniBtCodecOverlay.apk $T/ovl.apk
if [ -s $T/ovl.apk ] && cmp -s $T/ovl.apk $A/RG52MiniBtCodecOverlay.apk; then
  say y "оверлей: SBC кодеком по умолчанию"
else
  say n "оверлей SBC"
fi

echo "== Логотип загрузчика"
# U-Boot рисует logo.bmp сам, ядро подхватывает уже включённый экран и своей
# инициализации не делает. Если рядом лежит logo_kernel.bmp, ядро рисует ещё
# и его — и после этого экран гаснет насовсем: подсветка горит, Android
# рисует кадры, а панель тёмная, пока не усыпить и не разбудить устройство.
# Проверено на живом устройстве 21.09.2026 — см. docs/11-boot-logo.md.
mdir -b -i $T/p3 ::/ > $T/p3ls 2>/dev/null
if grep -qi '^::/logo_kernel.bmp$' $T/p3ls; then
  say n "logo_kernel.bmp НЕ должен лежать в образе (гасит экран после загрузки)"
else
  say y "logo_kernel.bmp отсутствует"
fi
chk "$(grep -i '^::/logo.bmp$' $T/p3ls)" "logo.bmp на месте"
n=$(grep -ci '^::/battery_[0-5].bmp$' $T/p3ls)
[ "$n" = 6 ] && say y "шесть кадров battery_0..5.bmp" || say n "кадров battery_*.bmp: $n из 6"
chk "$(grep -i '^::/battery_fail.bmp$' $T/p3ls)" "battery_fail.bmp на месте"

echo "== Загрузчик"
# Область idbloader в авторском образе пуста: карта не была загрузочной сама
# по себе. С загрузчиком, снятым с eMMC, пропало зависание при включении
# с воткнутым USB.
idb=$(dd if=$IMG bs=512 skip=64 count=16320 2>/dev/null | tr -d '\000' | wc -c)
[ "$idb" -gt 100000 ] && say y "SPL на месте ($idb байт данных)" \
                      || say n "SPL (область пуста — карта не загрузится сама)"
# Строка вида: U-Boot 2017.09-g034a996-dirty #lw (Jul 10 2026 - 15:04:24 +0800)
dd if=$IMG bs=512 skip=16384 count=8192 of=$T/ub 2>/dev/null
ub=$(strings $T/ub | grep -m1 -oE 'U-Boot 2[0-9]{3}\.[0-9]{2}[^)]*\)')
# Опознаём загрузчик по модели в его дереве, а не по дате: у нашей сборки
# там «AISLPC RG52 Mini», у заводских — отладочная плата Rockchip. Заводской
# с eMMC ломает выключение, авторский работает — см. docs/12-bootloader.md.
if grep -qa 'AISLPC RG52 Mini' $T/ub; then
  # строки-баннера с версией в нашей сборке нет, опознаём по дереву
  say y "FIT нашей сборки (дерево AISLPC RG52 Mini)"
elif [ -n "$ub" ]; then
  case "$ub" in
    *2026*) say n "в образе FIT с eMMC ($ub) — он ломает выключение" ;;
    *)      say y "FIT авторский: $ub" ;;
  esac
else
  say n "U-Boot в разделе не опознан"
fi

echo "== Выключение"
if d4 /system/etc/init/vold.rc $T/vold; then
  if grep -qa 'reboot_on_failure' $T/vold; then
    say n "у vold убран reboot_on_failure (иначе выключение = перезагрузка)"
  else
    say y "у vold убран reboot_on_failure"
  fi
  chk "$(grep -o 'shutdown critical' $T/vold)" "shutdown critical у vold сохранён"
else
  say n "vold.rc"
fi
chk "$(grep -o '^ro.build.shutdown_timeout=2$' $T/bp)" "таймаут выключения 2 с (умолчание 6)"

echo "== Клавиатура и метод ввода"
d4 /system/app/LeanKeyKeyboard/LeanKeyKeyboard.apk $T/lk
[ "$(stat -c %s $T/lk 2>/dev/null)" = 1485990 ] && say y "LeanKey 6.1.13 в /system/app"                                                 || say n "LeanKey в /system/app"
d4 /system/bin/ime_fix.sh $T/if && chk "$(grep -c default_input_method $T/if)" "скрипт ime_fix.sh (метод ввода слетает при загрузке)" || say n "ime_fix.sh"
d4 /system/etc/init/init.perf.rc $T/rc2 && chk "$(grep -c 'start ime_fix' $T/rc2)" "запуск ime_fix по sys.boot_completed" || say n "init.perf.rc"

echo "== Управляющее приложение KernelSU"
# В /system/app класть нельзя: ядро ищет управляющее приложение только в
# /data/app (throne_tracker.c), оттуда бы оно его не нашло и root не работал
# бы. Поэтому apk лежит в /system/etc/rg52 и ставится при первой загрузке.
d4 /system/etc/rg52/KernelSUNext.apk $T/ksu
[ "$(stat -c %s $T/ksu 2>/dev/null)" = 10209942 ] && say y "KernelSU Next v3.3.0 (33214) в образе"                                                   || say n "apk KernelSU Next"
d4 /system/bin/ksu_install.sh $T/ki && chk "$(grep -c 'com.rifsxd.ksunext' $T/ki)" "скрипт ksu_install.sh" || say n "ksu_install.sh"
chk "$(grep -c 'start ksu_install' $T/rc2)" "запуск ksu_install по sys.boot_completed"

echo "== Мелочи скорости"
if d4 /system/etc/init/atrace.rc $T/at; then
  chk "$(grep -o 'sched_schedstats 0' $T/at)" "счётчики планировщика не включаются при загрузке"
else
  say n "atrace.rc"
fi

echo "== Демон геймпада"
if d5 /bin/rgp2pad $T/rgp && grep -qa 'rgp2pad2:' $T/rgp; then
  say y "наш демон rgp2pad2 стоит вместо авторского"
  d5 /bin/rgp2pad.orig $T/x && say y "авторский сохранён как rgp2pad.orig" \
                            || say n "rgp2pad.orig"
  d5 /bin/rgp2pad-killall.sh $T/x && say y "скрипт rgp2pad-killall.sh на месте" \
                                  || say n "rgp2pad-killall.sh"
else
  printf '  \033[36mИНФО\033[0m демон геймпада авторский\n'
fi

echo "== Целостность файловых систем"
e2fsck -fn $T/p5 >/dev/null 2>&1 && say y "vendor: e2fsck чист" || say n "vendor: e2fsck"
e2fsck -fn $T/p4 >/dev/null 2>&1 && say y "system: e2fsck чист" || say n "system: e2fsck"
fsck.vfat -n $T/p3 >/dev/null 2>&1 && say y "boot: fsck.vfat чист" || say n "boot: fsck.vfat"

echo
echo "Пройдено: $OK, провалено: $BAD"
[ $BAD -eq 0 ] || exit 1
