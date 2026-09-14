#!/bin/bash
# Проверяет, что в готовом образе присутствуют все внесённые правки.
# Запускать в WSL:  bash /mnt/t/Dump/RG52Mini/android/verify-image.sh [образ.img]
set -u
A=/mnt/t/Dump/RG52Mini/android
# Образ можно указать первым аргументом; по умолчанию — рабочий.
IMG=${1:-$A/SyachOS-RG52Mini-V1.0.317m2.0.img}
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
d5 /etc/init.insmod.cfg $T/x; chk "$(grep -c 'aic8800_' $T/x | grep 2)" "две строки insmod aic8800"
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
chk "$(grep -o 'loglevel=4' $T/x)" "loglevel=4"
if grep -q 'ignore_loglevel' $T/x; then say n "ignore_loglevel убран"; else say y "ignore_loglevel убран"; fi
chk "$(grep -o '^TIMEOUT 10' $T/x)" "TIMEOUT 10 (меню U-Boot 1 с)"
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

chk "$(dtc -I dtb -O dts -o - $T/dtb 2>/dev/null | grep -o 'spk-mute-delay-ms')" "spk-mute-delay-ms в DTB"
chk "$(dtc -I dtb -O dts -o - $T/dtb 2>/dev/null | grep -o 'hynetek,husb311')" "контроллер Type-C в DTB (USB host)"
d4 /system/bin/anim_fix.sh $T/af && chk "$(grep -c animator_duration_scale $T/af)" "скрипт anim_fix.sh (фризы интерфейса)" || say n "anim_fix.sh"
d4 /system/etc/init/init.perf.rc $T/rc && chk "$(grep -c "start anim_fix" $T/rc)" "запуск anim_fix по sys.boot_completed" || say n "init.perf.rc"
d4 /system/bin/usbmode $T/usbmode
if [ -s $T/usbmode ] && cmp -s $T/usbmode $A/usbmode; then say y "утилита usbmode"; else say n "usbmode"; fi
d4 /system/product/overlay/RG52MiniBtCodecOverlay.apk $T/ovl.apk
if [ -s $T/ovl.apk ] && cmp -s $T/ovl.apk $A/RG52MiniBtCodecOverlay.apk; then
  say y "оверлей: SBC кодеком по умолчанию"
else
  say n "оверлей SBC"
fi

echo "== Целостность файловых систем"
e2fsck -fn $T/p5 >/dev/null 2>&1 && say y "vendor: e2fsck чист" || say n "vendor: e2fsck"
e2fsck -fn $T/p4 >/dev/null 2>&1 && say y "system: e2fsck чист" || say n "system: e2fsck"
fsck.vfat -n $T/p3 >/dev/null 2>&1 && say y "boot: fsck.vfat чист" || say n "boot: fsck.vfat"

echo
echo "Пройдено: $OK, провалено: $BAD"
[ $BAD -eq 0 ] || exit 1
