set -e
RG=/home/mamaich/rg52
K=$RG/kernel_rk3562_rg52mini
O=$RG/out-rg52; mkdir -p $O
TCBIN=$(echo "$RG"/toolchain/arm-gnu-toolchain-*-x86_64-aarch64-none-linux-gnu/bin)
export PATH="$TCBIN:$PATH" ARCH=arm64 CROSS_COMPILE=aarch64-none-linux-gnu-
cd $K
make syncconfig >/dev/null
echo "=== версия после синхронизации: $(make -s kernelrelease)"
echo "=== CONFIG_LOCALVERSION в auto.conf: $(grep LOCALVERSION include/config/auto.conf 2>/dev/null)"
echo
echo "=== сборка Image и модулей"
# DTB обязательно указывать явно: "make Image modules" device tree НЕ
# собирает, и в out-* остаётся устаревший файл от прошлой сборки.
# Именно наш DTB, а не dtbs — иначе собираются деревья всех плат Rockchip.
make -j"$(nproc)" Image modules rockchip/rk3562-rg52mini.dtb 2>&1 | tail -8
echo
echo "=== собранное"
cp arch/arm64/boot/Image $O/
cp arch/arm64/boot/dts/rockchip/rk3562-rg52mini.dtb $O/
for m in aic8800_bsp aic8800_fdrv rk915; do
  f=$(find drivers -name "$m.ko" | head -1)
  [ -n "$f" ] && { cp $f $O/$m.ko; aarch64-none-linux-gnu-strip --strip-debug $O/$m.ko; }
done
ls -la $O
echo
echo "=== vermagic модулей:"
for m in $O/*.ko; do printf '  %-18s %s\n' "$(basename $m)" "$(modinfo -F vermagic $m)"; done
echo "=== версия в Image:"
strings $O/Image | grep -m1 'Linux version'
