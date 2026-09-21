#!/system/bin/sh
# Удерживает выбранный метод ввода после перезагрузки.
#
# Система при каждой загрузке возвращает `default_input_method` на свою
# штатную клавиатуру (`com.android.inputmethod.leanback`). Список включённых
# методов при этом сохраняется — слетает только выбор по умолчанию.
#
# По умолчанию выбирается LeanKey — она лежит в образе системным приложением
# (tools/patch-leankey.py). Если её удалить, скрипт молча ничего не сделает:
# перед каждой попыткой он проверяет, установлен ли пакет.
#
# Другую клавиатуру можно закрепить своим свойством:
#
#     setprop persist.rg52.ime <имя>
#
# Узнать имена установленных:
#
#     ime list -a -s
#
# Свойство `persist.*` живёт на разделе данных и переживает перезагрузку,
# но не перепрошивку — как и сама установленная клавиатура.
#
# Значение удерживается минуту: система выставляет своё не сразу, а когда
# поднимется служба ввода, и однократной записи в начале загрузки не хватает.

IME=$(getprop persist.rg52.ime 2>/dev/null)
[ -z "$IME" ] && IME=com.liskovsoft.leankeyboard/.ime.LeanbackImeService

PKG=${IME%%/*}

set_it() {
  pm path "$PKG" >/dev/null 2>&1 || return 1
  cur=$(settings get secure default_input_method 2>/dev/null)
  [ "$cur" = "$IME" ] && return 0
  ime enable "$IME" >/dev/null 2>&1
  ime set "$IME" >/dev/null 2>&1 || return 1
  log -t ime_fix "default_input_method $cur -> $IME"
  return 0
}

i=0
while [ $i -lt 30 ]; do
  set_it
  sleep 2
  i=$((i + 1))
done

log -t ime_fix "готово, метод=$(settings get secure default_input_method 2>/dev/null)"
