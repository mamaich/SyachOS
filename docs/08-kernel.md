<!-- Часть репозитория доработки SyachOS для AISLPC RG52 Mini.
     Базовый образ: SyachOS-RG52Mini-V1.0.317-20260707 -->

# Ядро

## Что за ядро и откуда

    Linux version 5.10.226 (syahmi@chira) (aarch64-linux-gnu-gcc 16.1.0) #10 Thu Jul 2 2026
    vermagic: 5.10.226 SMP mod_unload modversions aarch64

`CONFIG_MODVERSIONS=y` — CRC символов проверяются, модули из чужой сборки
не загрузятся.

### Выложенный defconfig не собирается

`rg52mini_defconfig` **не воспроизводит сборку автора**: в нём нет
`CONFIG_AUDIT=y`, а `SECURITY_SELINUX` от него зависит. Kconfig молча
выбрасывает весь SELinux, после чего KernelSU (он подключает
`security/selinux/ss/sidtab.h`) валит сборку с `CONFIG_SECURITY_SELINUX_SID2STR_CACHE_SIZE
is not defined` и `CONFIG_SECURITY_SELINUX_SIDTAB_HASH_BITS undeclared`.

**Решение: в ядре включён `CONFIG_IKCONFIG_PROC`, конфиг зашит в сам `Image`.**

    scripts/extract-ikconfig .../boot/Image > shipped-kernel.config    # 7319 строк

Лежит в `android/shipped-kernel.config`. Собирать надо им.

При сборке снять `CONFIG_LOCALVERSION_AUTO=y`: у автора дерево было без `.git`
и vermagic чистый `5.10.226`, а наш клон добавил бы суффикс `-g<hash>`.


## Сверка с официальным ядром Rockchip

Проверялось: `github.com/rockchip-linux/kernel`, ветка `develop-5.10`.
Там 5.10.252, у нас 5.10.226 — но разница почти целиком в базовом Linux, а не
в драйверах Rockchip. Дерево автора оказалось свежим: снимок сделан в конце
июня 2026, и правки Rockchip от 2026-06-05, 2026-05-11 и 2026-04-21 в нём уже
есть.

| Подсистема | Итог |
|---|---|
| Драйвер дисплея (`drm/rockchip`) | брать нечего: самая новая правка от 2026-06-12 касается PX30/RK3326 |
| Mali | у нас `g25p0-00eac0` — новейшая версия DDK в репозитории Rockchip |
| Звук | три правки, ни одна не применима (см. ниже) |
| Карта памяти | одна защита от разыменования нулевого указателя |
| Wi-Fi / Bluetooth | **драйвера AIC8800 в репозитории Rockchip нет вообще** |
| Ошибки процессора | правка `TLBI errata` касается Cortex-A76 и новее, у нас A53 |
| **USB** | **фильтр ложного babble — единственное, что взято** |

Device tree на уровне чипа практически совпадает: `rk3562-pinctrl.dtsi`,
`rk3562-linux.dtsi` и `rk3562-android.dtsi` — байт в байт, в `rk3562.dtsi`
ровно одна добавленная строка (тот самый quirk), а в `rk3562-rk817.dtsi` у нас
даже богаче — добавлены спящие состояния выводов контроллера питания.

### Почему звуковые правки не подошли

Полезно как образец того, что заголовок коммита ещё ничего не значит.

* `trcm: Fix capture pointer with fifo compensation` — тракт TRCM здесь не
  используется вовсе: у платы `rockchip,cpu = <&sai0>`, то есть SAI.
* `ASoC: rockchip: drop jiffies conversion of substream wait_time` вместе с
  `ALSA: pcm: fix wait_time calculations` — **парные**. Сначала в ядре ALSA
  поменяли смысл поля `wait_time` с тактов на миллисекунды, потом в драйверах
  Rockchip убрали ставшее лишним преобразование. У нас нет **ни одной** из
  них, то есть старая пара согласована сама с собой. Применить только вторую
  означало бы ужать таймаут в 300 раз (`CONFIG_HZ=300`) и получить ошибки
  ввода-вывода на звуке. К тому же поле выставляется, только если задано
  свойство `rockchip,*-wait-time-ms`, а в нашем дереве его нет — так что обе
  правки для нас пустые.

### Драйвер Wi-Fi берётся не оттуда

`drivers/net/wireless/aic8800/` — не от Rockchip: в официальном
`rockchip_wlan` лежат 17 драйверов, и AIC8800 среди них нет. Автор порта
добавил его из SDK производителя чипа, версия у нас
`RWNX_VERS_REV = "241c091M (master)"`. Публичные форки на GitHub — под
USB-донглы для настольного Linux на ядрах 6.x; переход на любой из них означал
бы заново поднимать SDIO-транспорт и Bluetooth. Искать обновления надо в SDK
AICSemi, а не у Rockchip.

---

[к оглавлению](../README.md)
