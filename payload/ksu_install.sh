#!/system/bin/sh
# Ставит управляющее приложение KernelSU Next при первой загрузке.
#
# Почему не системным приложением в /system/app: ядро ищет управляющее
# приложение сканированием каталога /data/app и только его —
# KernelSU-Next, manager/throne_tracker.c:
#
#     search_manager("/data/app", 2, &uid_list);
#
# Приложение из /system/app ядро не найдёт: оно запустится, но останется без
# прав, и выдать root ничему не сможет. Поэтому apk лежит в /system/etc/rg52
# и один раз ставится обычной установкой — после неё он оказывается в
# /data/app, где ядро его и находит.
#
# Ставится только если пакета нет: обновлённую руками версию скрипт не
# трогает. После сброса данных поставит заново.

APK=/system/etc/rg52/KernelSUNext.apk
PKG=com.rifsxd.ksunext

[ -f "$APK" ] || exit 0

i=0
out=""
while [ $i -lt 60 ]; do
  if pm path "$PKG" >/dev/null 2>&1; then
    [ $i = 0 ] && log -t ksu_install "$PKG уже установлен" \
               || log -t ksu_install "установлен с попытки $i"
    exit 0
  fi
  out=$(pm install -r -g "$APK" 2>&1)
  case "$out" in
    *Success*) log -t ksu_install "установлен: $out"; exit 0 ;;
  esac
  out=$(pm install -r "$APK" 2>&1)
  case "$out" in
    *Success*) log -t ksu_install "установлен без -g: $out"; exit 0 ;;
  esac
  sleep 2
  i=$((i + 1))
done

log -t ksu_install "не удалось установить: $out"
