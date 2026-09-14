<!-- Часть репозитория доработки SyachOS для AISLPC RG52 Mini.
     Базовый образ: SyachOS-RG52Mini-V1.0.317-20260707 -->

# Wi-Fi и Bluetooth: AIC8800D80

## Причина неработающего Wi-Fi

Ходовая версия «в ядро слинкован старый драйвер RK915» **неверна**. В настоящем
конфиге автора всё правильно:

    CONFIG_RK915=m
    CONFIG_AIC_WLAN_SUPPORT=m
    CONFIG_AIC8800_WLAN_SUPPORT=m
    CONFIG_AIC_FW_PATH="/vendor/etc/firmware/aic8800"     <- уже поправлен под Android

DTS тоже правильный: `wifi_chip_type = "aic8800D80"`, `status = okay`.
Исходники драйвера aic8800 **побайтно совпадают** с проверенными на этом железе
(отличаются лишь 4 файла, которые мы сами патчили под BT-over-SDIO).

**Настоящая причина — в образ не доехали файлы:**

    /vendor/lib/modules/     только rk915.ko
    /vendor/etc/firmware/    только regulatory.db, rk915_fw.bin, rk915_patch.bin

Ни `aic8800_*.ko`, ни блобов D80. Похоже на упущение при упаковке.

### Почему шина SDIO была пуста

У Rockchip **питание Wi-Fi включает сам драйвер** при загрузке модуля
(`rockchip_wifi_power` / `aicbsp_platform_power_on`). Цепочка:

1. `init.insmod.sh` читает `/vendor/etc/init.insmod.cfg` и делает
   `if [ -f $name ]; then insmod $name; fi` — отсутствующие пропускает молча;
2. `rk915.ko` существует, загружается, не находит свой чип, `module_init`
   падает, ядро выгружает модуль;
3. питание так и не включено → `mmc2` (ff890000, SDIO) не видит карту;
4. `lsmod` пуст, `/sys/bus/sdio/devices/` пуст, `wlan0` нет.

То есть не «SDIO сломан» и не «драйвер мешает» — чип некому разбудить.


## Что сделано

Собрано ядро из опубликованных исходников с конфигом, извлечённым из образа.
`Image`, DTB и initrd **не менялись** — нужны только модули.

| Что | Куда |
|---|---|
| `aic8800_bsp.ko` (194 КБ), `aic8800_fdrv.ko` (962 КБ) | `/vendor/lib/modules/` |
| 15 блобов D80 (2.3 МБ), с рабочего EmuELEC | `/vendor/etc/firmware/aic8800/` |
| 2 строки `insmod` **после** `rk915` | `/vendor/etc/init.insmod.cfg` |

Строка `rk915` оставлена — образ остаётся годным и для rev A, драйверы
разбираются по SDIO-идентификаторам. Порядок важен: `bsp` перед `fdrv`.

Правки внесены в раздел vendor через `debugfs -w` (root не нужен), раздел вписан
обратно в образ: `SyachOS-RG52Mini-V1.0.317-aic8800-patched.img`.


## Отладочный вывод драйвера Wi-Fi

Драйвер сыпал в лог ядра каждые 3 секунды (`rwnx_fill_station_info`,
`MM_GET_STA_INFO_CFM`), из-за чего кольцевой буфер жил минуты и вытеснял
полезное, а `audit` жаловался на `audit_lost`.

Умолчания в исходниках изменены:

    rwnx_main.c:     int aicwf_dbg_level = LOGERROR;       (было |LOGINFO|LOGDEBUG|LOGTRACE|LOGFW)
    aic_bsp_main.c:  int aicwf_dbg_level_bsp = LOGERROR;

Результат: **7 строк `AICWFDBG` за загрузку** вместо непрерывного потока.

Пересборка при этом не обязательна — есть параметр модуля `aicwf_dbg_level`
с правами 0660, его можно менять на лету. Но задать постоянно через
`init.insmod.cfg` **нельзя**: `init.insmod.sh` читает строку как
`insmod <путь>` и делает `[ -f $name ]` на всё, что после `insmod`, так что
аргументы модуля сломают проверку. Поэтому правка умолчания — единственный
чистый путь.

---

[к оглавлению](../README.md)
