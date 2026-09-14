#!/bin/bash
# Готовит каталог bt-payload/ для tools/patch-bt.sh: три текстовых файла берутся
# из самого образа и правятся, два двоичных — из сборки.
# Что именно меняется и почему — docs/02-wifi-bluetooth.md
#
# Текстовые файлы в репозитории не лежат намеренно: это части прошивки, их
# правильнее брать из своего образа, а не тащить чужую копию.
set -e

A=${A:-/mnt/t/Dump/RG52Mini/android}
IMG=${IMG:-$A/SyachOS-RG52Mini-V1.0.317-aic8800-patched.img}   # выход шага 0
B=${B:-$A/bt-payload}
MOD=${MOD:-/home/mamaich/rg52/out-rg52}      # модули: tools/kbuild.sh
SHIM=${SHIM:-/home/mamaich/rg52/out-syach/libbt-vendor.so}     # tools/build-btvendor.sh

P4_OFF=121634816  ; P4_LEN=1577058304   # system
P5_OFF=1698693120 ; P5_LEN=267046912    # vendor

[ -f "$IMG" ]  || { echo "!! нет образа: $IMG (сначала tools/patch-wifi.sh)"; exit 1; }
[ -f "$SHIM" ] || { echo "!! нет прослойки: $SHIM (сначала tools/build-btvendor.sh)"; exit 1; }

mkdir -p "$B"
T=$(mktemp -d)
dd if="$IMG" of="$T/v.img" bs=4M iflag=skip_bytes,count_bytes skip=$P5_OFF count=$P5_LEN status=none
dd if="$IMG" of="$T/s.img" bs=4M iflag=skip_bytes,count_bytes skip=$P4_OFF count=$P4_LEN status=none

echo "[1/4] модули и прослойка"
cp "$MOD/aic8800_bsp.ko" "$MOD/aic8800_fdrv.ko" "$B/"
cp "$SHIM" "$B/libbt-vendor.so"
# HAL грузит именно -seekwave; кладём ту же самую библиотеку под вторым именем.
cp "$SHIM" "$B/libbt-vendor-seekwave.so"

echo "[2/4] build.prop: шесть свойств профилей"
debugfs -R "dump /build.prop $B/build.prop.image-orig" "$T/v.img" >/dev/null 2>&1
if grep -q 'bluetooth.profile.gatt.enabled' "$B/build.prop.image-orig"; then
  cp "$B/build.prop.image-orig" "$B/build.prop"
  echo "     свойства уже в образе, копирую как есть"
else
  # Только ASCII: файл разбирает init, кириллица в комментарии — лишний риск.
  cp "$B/build.prop.image-orig" "$B/build.prop"
  cat >> "$B/build.prop" <<'EOF'

# Bluetooth profiles for AIC8800 (aic8800_fdrv + libbt-vendor shim).
# Without these the stack starts with GATT only: scanning works, nothing else.
bluetooth.profile.gatt.enabled=true
bluetooth.profile.a2dp.source.enabled=true
bluetooth.profile.avrcp.target.enabled=true
bluetooth.profile.hfp.ag.enabled=true
bluetooth.profile.hid.host.enabled=true
bluetooth.profile.opp.enabled=true
EOF
fi

echo "[3/4] init.insmod.cfg (кладётся шагом 0, здесь только для сверки)"
debugfs -R "dump /etc/init.insmod.cfg $B/init.insmod.cfg" "$T/v.img" >/dev/null 2>&1
grep -c 'aic8800' "$B/init.insmod.cfg" | grep -q '^2$' \
  || echo "     !! в образе нет двух строк insmod — не выполнен шаг 0"

echo "[4/4] rg52-no-tv.xml: убрать две строки unavailable-feature"
debugfs -R "dump /system/etc/sysconfig/rg52-no-tv.xml $B/rg52-no-tv.xml.orig" "$T/s.img" >/dev/null 2>&1
grep -v 'unavailable-feature name="android.hardware.bluetooth' \
     "$B/rg52-no-tv.xml.orig" > "$B/rg52-no-tv.xml"
d=$(( $(wc -l < "$B/rg52-no-tv.xml.orig") - $(wc -l < "$B/rg52-no-tv.xml") ))
echo "     удалено строк: $d (ожидается 2)"

rm -rf "$T"
echo
ls -la "$B"
