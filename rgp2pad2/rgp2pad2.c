// rgp2pad2 — переписанная замена /vendor/bin/rgp2pad для RG52 Mini.
//
// Что делает исходный демон и что здесь воспроизведено:
//
//   * перехватывает сырой геймпад retrogame_joypad через EVIOCGRAB и вместо
//     него показывает системе виртуальный "Xbox Wireless Controller"
//     (045e:02fd) — Android опознаёт его по VID/PID и берёт готовую раскладку;
//   * второе виртуальное устройство "rgp2pad-mouse" — курсор и колесо;
//   * аккорд L3+R3 (нажать оба в пределах 80 мс) включает и выключает режим
//     мыши, с миганием экрана негативом как обратной связью;
//   * в режиме мыши правый стик двигает курсор, короткое нажатие R3 — щелчок,
//     удержание R3 — режим колеса;
//   * свойство persist.sys.btn_layout меняет раскладку кнопок: "nintendo"
//     меняет местами A/B и X/Y, любое другое значение оставляет как есть.
//     Свойство выставляет меню по длинному нажатию выключателя;
//   * двойной аккорд Select+Start за 800 мс закрывает посторонние приложения;
//   * триггеры (ABS_GAS/ABS_BRAKE) дополнительно отдаются как кнопки
//     BTN_TR2/BTN_TL2.
//
// Отличия от оригинала, сделанные намеренно:
//
//   1. Кривая скорости курсора вынесена в свойства и перечитывается на ходу,
//      без пересборки: persist.sys.mouse_max, mouse_pow, mouse_dead,
//      mouse_axis. В оригинале это были зашитые константы 24.0, 1.5, 2500 и
//      30267.
//   2. Показатель степени по умолчанию 2.5 вместо 1.5: на половине отклонения
//      курсор идёт вдвое медленнее, на четверти вчетверо, максимальная
//      скорость на упоре не меняется.
//   3. Диапазоны осей копируются с самого геймпада, а не зашиты числами.
//   4. Скрипт "закрыть всё" вынесен в отдельный файл рядом с двоичным.
//
// Сборка: см. build.sh (NDK, статически, aarch64).

#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <math.h>
#include <poll.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>
#include <linux/input.h>
#include <linux/uinput.h>
#include <sys/ioctl.h>
#include <sys/system_properties.h>
#include <sys/time.h>

// ---------------------------------------------------------------- настройки

#define POLL_MS        16     // шаг опроса и выдачи движения курсора
#define CHORD_MS       80     // окно аккорда L3+R3
#define R3_CLICK_MS    150    // короче — щелчок, дольше — режим колеса
#define CLICK_HOLD_MS  60     // сколько держать нажатой левую кнопку
#define KILL_WINDOW_MS 800    // окно двойного аккорда Select+Start
#define KILL_COOLDOWN  3000   // не чаще раза в три секунды
#define STALL_WARN_MS  40     // предупредить, если цикл задержался
#define PROP_POLL_MS   500    // как часто искать ещё не появившееся свойство
#define TRIG_THRESHOLD 64     // выше этого триггер считается нажатым

// значения по умолчанию для кривой скорости
#define DEF_MOUSE_MAX  24.0f  // пикселей за опрос на полном отклонении
#define DEF_MOUSE_POW  2.5f   // показатель степени; 1.5 — как было у автора
#define DEF_MOUSE_DEAD 2500.0f
#define DEF_MOUSE_AXIS 32767.0f
#define WHEEL_RATE     0.1f   // тиков колеса за опрос на полном отклонении

static const char *KILLALL_SCRIPT = "/vendor/bin/rgp2pad-killall.sh";
static const char *INVERT_FLASH =
    "settings put secure accessibility_display_inversion_enabled 1 && sleep 0.5"
    " && settings put secure accessibility_display_inversion_enabled 0 &";

// --------------------------------------------------------------------- лог

static int kmsg_fd = -1;

static void klog(const char *fmt, ...)
{
    char buf[512];
    int n = snprintf(buf, sizeof(buf), "rgp2pad2: ");
    va_list ap;
    va_start(ap, fmt);
    n += vsnprintf(buf + n, sizeof(buf) - (size_t)n - 2, fmt, ap);
    va_end(ap);
    if (n > (int)sizeof(buf) - 2) n = (int)sizeof(buf) - 2;
    buf[n++] = 10;              // перевод строки
    if (kmsg_fd >= 0) {
        ssize_t r = write(kmsg_fd, buf, (size_t)n);
        (void)r;
    }
}

static long long now_ms(void)
{
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (long long)ts.tv_sec * 1000 + ts.tv_nsec / 1000000;
}

// --------------------------------------------------------- свойства Android

// Дескриптор свойства не меняется, а серийный номер растёт при каждой записи,
// поэтому опрос обходится без обращения к файловой системе.
//
// В NDK нет __system_property_serial, зато есть __system_property_read_callback:
// он отдаёт значение и серийный номер разом, читая общую память без блокировок.
struct prop {
    const char *name;
    const prop_info *pi;
    uint32_t serial;
    uint32_t seen;                 // заполняет обратный вызов
    char value[PROP_VALUE_MAX];
    long long last_retry;
};

static void prop_cb(void *cookie, const char *name, const char *value,
                    uint32_t serial)
{
    (void)name;
    struct prop *p = (struct prop *)cookie;
    snprintf(p->value, sizeof(p->value), "%s", value ? value : "");
    p->seen = serial;
}

// Возвращает 1, если значение изменилось (или прочитано впервые).
static int prop_poll(struct prop *p, long long now)
{
    if (!p->pi) {
        if (now - p->last_retry < PROP_POLL_MS)
            return 0;
        p->last_retry = now;
        p->pi = __system_property_find(p->name);
        if (!p->pi)
            return 0;
        p->seen = 0;
        __system_property_read_callback(p->pi, prop_cb, p);
        p->serial = p->seen;
        return 1;
    }
    p->seen = p->serial;
    __system_property_read_callback(p->pi, prop_cb, p);
    if (p->seen == p->serial)
        return 0;
    p->serial = p->seen;
    return 1;
}

static float prop_float(const char *name, float dflt)
{
    char v[PROP_VALUE_MAX] = {0};
    if (__system_property_get(name, v) <= 0 || !v[0])
        return dflt;
    char *end = NULL;
    float f = strtof(v, &end);
    if (end == v || !(f > 0.0f))
        return dflt;
    return f;
}

// --------------------------------------------------------- кривая скорости

struct curve {
    float max;    // пикселей за опрос на полном отклонении
    float pw;     // показатель степени
    float dead;   // мёртвая зона
    float span;   // (axis - dead), делитель нормировки
};

static void curve_load(struct curve *c)
{
    c->max  = prop_float("persist.sys.mouse_max",  DEF_MOUSE_MAX);
    c->pw   = prop_float("persist.sys.mouse_pow",  DEF_MOUSE_POW);
    c->dead = prop_float("persist.sys.mouse_dead", DEF_MOUSE_DEAD);
    float axis = prop_float("persist.sys.mouse_axis", DEF_MOUSE_AXIS);
    c->span = axis - c->dead;
    if (c->span < 1.0f)
        c->span = 1.0f;
    klog("кривая: max=%.2f pow=%.2f dead=%.0f axis=%.0f",
         (double)c->max, (double)c->pw, (double)c->dead, (double)axis);
}

// Нормированное отклонение оси, 0..1 за пределами мёртвой зоны.
static float curve_norm(const struct curve *c, int v)
{
    float a = (float)(v < 0 ? -v : v);
    if (a <= c->dead)
        return 0.0f;
    float n = (a - c->dead) / c->span;
    return n > 1.0f ? 1.0f : n;
}

// Скорость по оси: знак от направления, величина по степенной кривой.
static float curve_speed(const struct curve *c, int v)
{
    float n = curve_norm(c, v);
    if (n == 0.0f)
        return 0.0f;
    float s = c->max * powf(n, c->pw);
    return v < 0 ? -s : s;
}

// ------------------------------------------------------------ ввод и вывод

static int emit(int fd, uint16_t type, uint16_t code, int32_t value)
{
    struct input_event ev;
    memset(&ev, 0, sizeof(ev));
    gettimeofday(&ev.time, NULL);
    ev.type = type;
    ev.code = code;
    ev.value = value;
    return write(fd, &ev, sizeof(ev)) == (ssize_t)sizeof(ev) ? 0 : -1;
}

static void emit_syn(int fd)
{
    emit(fd, EV_SYN, SYN_REPORT, 0);
}

// Пропустить событие насквозь, при необходимости подменив код. Своего
// SYN_REPORT не добавляем: границы отчётов задаёт сам геймпад, его SYN
// приходит следом и пересылается тем же путём. Ломать это нельзя — иначе
// диагональное движение стика распадается на два отдельных отчёта.
static void forward_ev(int fd, const struct input_event *ev, uint16_t code)
{
    struct input_event out = *ev;
    out.code = code;
    ssize_t r = write(fd, &out, sizeof(out));
    (void)r;
}

static int uinput_open(void)
{
    int fd = open("/dev/uinput", O_WRONLY | O_NONBLOCK | O_CLOEXEC);
    if (fd < 0)
        klog("не открылся /dev/uinput: %s", strerror(errno));
    return fd;
}

// ------------------------------------------------------- виртуальная мышь

static int mouse_create(void)
{
    int fd = uinput_open();
    if (fd < 0)
        return -1;

    ioctl(fd, UI_SET_EVBIT, EV_REL);
    ioctl(fd, UI_SET_RELBIT, REL_X);
    ioctl(fd, UI_SET_RELBIT, REL_Y);
    ioctl(fd, UI_SET_RELBIT, REL_WHEEL);
    ioctl(fd, UI_SET_EVBIT, EV_KEY);
    ioctl(fd, UI_SET_KEYBIT, BTN_LEFT);
    ioctl(fd, UI_SET_KEYBIT, BTN_RIGHT);
    ioctl(fd, UI_SET_EVBIT, EV_SYN);

    struct uinput_user_dev d;
    memset(&d, 0, sizeof(d));
    snprintf(d.name, UINPUT_MAX_NAME_SIZE, "rgp2pad-mouse");
    d.id.bustype = 6;               // как у оригинала
    d.id.vendor  = 0x0BEE;
    d.id.product = 0xFA11;
    d.id.version = 0x0100;

    if (write(fd, &d, sizeof(d)) != (ssize_t)sizeof(d)) {
        klog("мышь: не записался uinput_user_dev: %s", strerror(errno));
        close(fd);
        return -1;
    }
    if (ioctl(fd, UI_DEV_CREATE) < 0) {
        klog("мышь: UI_DEV_CREATE не прошёл: %s", strerror(errno));
        close(fd);
        return -1;
    }
    klog("мышь создана (rgp2pad-mouse)");
    return fd;
}

// ---------------------------------------------- виртуальный геймпад Xbox

// Оси виртуального геймпада и то, с какой оси сырого устройства брать для
// каждой диапазон. Правый стик переезжает с RX/RY на Z/RZ — так его ждёт
// раскладка Xbox в Android.
struct axis_map { int out; int src; };

static const struct axis_map AXES[] = {
    { ABS_X,     ABS_X     },
    { ABS_Y,     ABS_Y     },
    { ABS_Z,     ABS_RX    },   // правый стик по горизонтали
    { ABS_RZ,    ABS_RY    },   // правый стик по вертикали
    { ABS_GAS,   ABS_GAS   },
    { ABS_BRAKE, ABS_BRAKE },
    { ABS_HAT0X, ABS_HAT0X },
    { ABS_HAT0Y, ABS_HAT0Y },
};
#define NAXES ((int)(sizeof(AXES) / sizeof(AXES[0])))

// Кнопки, объявляемые всегда, даже если сырое устройство их не имеет.
static const int PAD_KEYS[] = {
    BTN_SOUTH, BTN_EAST, BTN_NORTH, BTN_WEST,
    BTN_TL, BTN_TR, BTN_TL2, BTN_TR2,
    BTN_SELECT, BTN_START, BTN_MODE, BTN_THUMBL, BTN_THUMBR,
    BTN_DPAD_UP, BTN_DPAD_DOWN, BTN_DPAD_LEFT, BTN_DPAD_RIGHT,
    BTN_TRIGGER_HAPPY, KEY_VOLUMEUP, KEY_VOLUMEDOWN, KEY_POWER, 278,
};
#define NPAD_KEYS ((int)(sizeof(PAD_KEYS) / sizeof(PAD_KEYS[0])))

static int pad_create(int raw_fd)
{
    int fd = uinput_open();
    if (fd < 0)
        return -1;

    ioctl(fd, UI_SET_EVBIT, EV_KEY);
    ioctl(fd, UI_SET_EVBIT, EV_ABS);
    ioctl(fd, UI_SET_EVBIT, EV_SYN);

    for (int i = 0; i < NPAD_KEYS; i++)
        ioctl(fd, UI_SET_KEYBIT, PAD_KEYS[i]);

    // плюс всё, что умеет само устройство, чтобы ничего не потерять
    unsigned char bits[KEY_MAX / 8 + 1];
    memset(bits, 0, sizeof(bits));
    if (ioctl(raw_fd, EVIOCGBIT(EV_KEY, sizeof(bits)), bits) >= 0) {
        for (int c = 0; c <= KEY_MAX; c++)
            if (bits[c / 8] & (1 << (c % 8)))
                ioctl(fd, UI_SET_KEYBIT, c);
    }

    struct uinput_user_dev d;
    memset(&d, 0, sizeof(d));
    snprintf(d.name, UINPUT_MAX_NAME_SIZE, "Xbox Wireless Controller");
    d.id.bustype = BUS_USB;
    d.id.vendor  = 0x045E;
    d.id.product = 0x02FD;
    d.id.version = 0x0003;

    for (int i = 0; i < NAXES; i++) {
        int out = AXES[i].out;
        ioctl(fd, UI_SET_ABSBIT, out);
        struct input_absinfo ai;
        memset(&ai, 0, sizeof(ai));
        if (ioctl(raw_fd, EVIOCGABS(AXES[i].src), &ai) < 0)
            continue;
        d.absmin[out]  = ai.minimum;
        d.absmax[out]  = ai.maximum;
        d.absfuzz[out] = ai.fuzz;
        d.absflat[out] = ai.flat;
    }

    if (write(fd, &d, sizeof(d)) != (ssize_t)sizeof(d)) {
        klog("геймпад: не записался uinput_user_dev: %s", strerror(errno));
        close(fd);
        return -1;
    }
    if (ioctl(fd, UI_DEV_CREATE) < 0) {
        klog("геймпад: UI_DEV_CREATE не прошёл: %s", strerror(errno));
        close(fd);
        return -1;
    }
    klog("геймпад создан: Xbox Wireless Controller (045e:02fd)");
    return fd;
}

// --------------------------------------------------------- поиск геймпада

static int find_raw_pad(void)
{
    for (int i = 0; i < 32; i++) {
        char path[64];
        snprintf(path, sizeof(path), "/dev/input/event%d", i);
        int fd = open(path, O_RDONLY | O_NONBLOCK | O_CLOEXEC);
        if (fd < 0)
            continue;
        char name[256] = {0};
        if (ioctl(fd, EVIOCGNAME(sizeof(name) - 1), name) < 0
            || strstr(name, "Xbox Wireless Controller")
            || strstr(name, "flydigi")
            || !strstr(name, "retrogame_joypad")) {
            close(fd);
            continue;
        }
        klog("найден геймпад: %s (%s)", path, name);
        return fd;
    }
    return -1;
}

// ------------------------------------------------ раскладка кнопок A/B/X/Y

// Защёлка нужна, чтобы отпускание пришло тем же кодом, что и нажатие, даже
// если раскладку переключили между ними.
static int abxy_index(int code)
{
    switch (code) {
    case BTN_SOUTH: return 0;
    case BTN_EAST:  return 1;
    case BTN_NORTH: return 2;
    case BTN_WEST:  return 3;
    default:        return -1;
    }
}

static int abxy_swap(int code)
{
    switch (code) {
    case BTN_SOUTH: return BTN_EAST;
    case BTN_EAST:  return BTN_SOUTH;
    case BTN_NORTH: return BTN_WEST;
    default:        return BTN_NORTH;
    }
}

// --------------------------------------------------------------- состояние

struct state {
    int mouse_mode;
    int scroll_mode;

    int l3_down, r3_down;
    long long l3_time, r3_time;
    int chord_used;                  // аккорд сработал, ждём отпускания
    int l3_forwarded, r3_forwarded;  // нажатие ушло в геймпад — и отпускание должно

    int rx, ry;                      // правый стик
    float acc_x, acc_y, acc_wheel;   // дробные остатки

    long long click_until;           // до какого времени держать левую кнопку

    int gas_btn, brake_btn;          // триггеры, отданные как кнопки

    int sel_down, start_down;        // двойной аккорд Select+Start
    int kill_armed, kill_used;
    long long kill_arm_time, kill_last;

    int latched[4], latch_active[4];
};

static void neutralize_sticks(int pad_fd)
{
    emit(pad_fd, EV_ABS, ABS_Z, 0);
    emit(pad_fd, EV_ABS, ABS_RZ, 0);
    emit_syn(pad_fd);
    klog("стики обнулены (Z/RZ=0)");
}

static void mouse_toggle(struct state *st, int pad_fd)
{
    st->mouse_mode = !st->mouse_mode;
    st->scroll_mode = 0;
    st->acc_x = st->acc_y = st->acc_wheel = 0.0f;
    st->click_until = 0;
    if (st->mouse_mode)
        neutralize_sticks(pad_fd);
    klog("мышь: %s", st->mouse_mode ? "ON" : "OFF");
    int r = system(INVERT_FLASH);   // мигнуть экраном как подтверждение
    (void)r;
}

static void kill_all(void)
{
    char cmd[256];
    if (access(KILLALL_SCRIPT, X_OK) == 0)
        snprintf(cmd, sizeof(cmd), "%s &", KILLALL_SCRIPT);
    else
        snprintf(cmd, sizeof(cmd), "input keyevent 3 &");
    klog("закрыть всё: запускаю %s", cmd);
    int r = system(cmd);
    (void)r;
}

// ----------------------------------------------------- обработка нажатий

// Select и Start: два аккорда подряд за 800 мс закрывают приложения.
static void handle_kill_chord(struct state *st, int code, int value,
                              long long now)
{
    if (!value)
        st->kill_used = 0;
    if (code == BTN_SELECT)
        st->sel_down = value != 0;
    else
        st->start_down = value != 0;

    if (!st->sel_down || !st->start_down || st->kill_used)
        return;
    st->kill_used = 1;

    if (st->kill_armed) {
        if (now - st->kill_arm_time <= KILL_WINDOW_MS) {
            if (now - st->kill_last <= KILL_COOLDOWN - 1) {
                klog("закрыть всё: слишком часто, пропускаю");
            } else {
                st->kill_last = now;
                kill_all();
            }
        }
        st->kill_armed = 0;
    } else {
        st->kill_armed = 1;
        st->kill_arm_time = now;
    }
}

// L3 и R3: аккорд переключает режим мыши, одиночное нажатие в режиме мыши —
// щелчок или колесо, вне режима мыши — обычная кнопка.
static void handle_thumb(struct state *st, int pad_fd, int mouse_fd,
                         const struct input_event *ev, long long now)
{
    int code = ev->code;
    int value = ev->value;
    int is_r3 = (code == BTN_THUMBR);
    int *self_down  = is_r3 ? &st->r3_down : &st->l3_down;
    int *other_down = is_r3 ? &st->l3_down : &st->r3_down;
    long long *self_time  = is_r3 ? &st->r3_time : &st->l3_time;
    long long *other_time = is_r3 ? &st->l3_time : &st->r3_time;
    int *self_fwd = is_r3 ? &st->r3_forwarded : &st->l3_forwarded;

    if (value) {
        *self_down = 1;
        *self_time = now;

        long long gap = now - *other_time;
        if (gap < 0)
            gap = -gap;
        if (*other_down && gap <= CHORD_MS && !st->chord_used) {
            st->chord_used = 1;
            mouse_toggle(st, pad_fd);
            return;
        }
        if (!st->mouse_mode) {
            forward_ev(pad_fd, ev, (uint16_t)code);
            *self_fwd = 1;
        }
        return;
    }

    // отпускание
    *self_down = 0;
    if (!st->l3_down && !st->r3_down)
        st->chord_used = 0;

    if (*self_fwd) {
        forward_ev(pad_fd, ev, (uint16_t)code);
        *self_fwd = 0;
        return;
    }
    if (!is_r3 || !st->mouse_mode)
        return;

    if (st->scroll_mode) {
        st->scroll_mode = 0;
        st->acc_wheel = 0.0f;
        klog("режим колеса выключен");
        return;
    }
    if (now - st->r3_time <= R3_CLICK_MS) {
        emit(mouse_fd, EV_KEY, BTN_LEFT, 1);
        emit_syn(mouse_fd);
        st->click_until = now + CLICK_HOLD_MS;
        klog("мышь: щелчок (удержание %lld мс)", now - st->r3_time);
    }
}

// ------------------------------------------------------------- одно событие

static void handle_event(struct state *st, const struct input_event *ev,
                         int pad_fd, int mouse_fd, int layout_nintendo,
                         long long now)
{
    if (ev->type == EV_KEY) {
        int code = ev->code;

        if (code == BTN_SELECT || code == BTN_START) {
            handle_kill_chord(st, code, ev->value, now);
            forward_ev(pad_fd, ev, (uint16_t)code);
            return;
        }
        if (code == BTN_THUMBL || code == BTN_THUMBR) {
            handle_thumb(st, pad_fd, mouse_fd, ev, now);
            return;
        }

        int idx = abxy_index(code);
        if (idx >= 0) {
            int out = code;
            if (ev->value == 1) {
                if (layout_nintendo)
                    out = abxy_swap(code);
                st->latched[idx] = out;
                st->latch_active[idx] = 1;
            } else if (st->latch_active[idx]) {
                out = st->latched[idx];
                if (ev->value == 0)
                    st->latch_active[idx] = 0;
            } else if (layout_nintendo) {
                out = abxy_swap(code);
            }
            forward_ev(pad_fd, ev, (uint16_t)out);
            return;
        }

        forward_ev(pad_fd, ev, (uint16_t)code);
        return;
    }

    if (ev->type != EV_ABS) {
        forward_ev(pad_fd, ev, ev->code);   // включая SYN_REPORT
        return;
    }

    switch (ev->code) {
    case ABS_RX:                       // правый стик по горизонтали
        st->rx = ev->value;
        if (!st->mouse_mode)
            forward_ev(pad_fd, ev, ABS_Z);
        return;
    case ABS_RY:                       // правый стик по вертикали
        st->ry = ev->value;
        if (!st->mouse_mode)
            forward_ev(pad_fd, ev, ABS_RZ);
        return;
    case ABS_GAS: {
        // триггер дополнительно отдаём как кнопку — своим отчётом
        int on = ev->value > TRIG_THRESHOLD;
        if (on != st->gas_btn) {
            st->gas_btn = on;
            emit(pad_fd, EV_KEY, BTN_TR2, on);
            emit_syn(pad_fd);
        }
        forward_ev(pad_fd, ev, ABS_GAS);
        return;
    }
    case ABS_BRAKE: {
        int on = ev->value > TRIG_THRESHOLD;
        if (on != st->brake_btn) {
            st->brake_btn = on;
            emit(pad_fd, EV_KEY, BTN_TL2, on);
            emit_syn(pad_fd);
        }
        forward_ev(pad_fd, ev, ABS_BRAKE);
        return;
    }
    default:
        forward_ev(pad_fd, ev, ev->code);
        return;
    }
}

// ------------------------------------------------ выдача движения курсора

static void mouse_tick(struct state *st, const struct curve *c, int mouse_fd,
                       long long now)
{
    // отпустить левую кнопку, если её срок вышел
    if (st->click_until && now >= st->click_until) {
        emit(mouse_fd, EV_KEY, BTN_LEFT, 0);
        emit_syn(mouse_fd);
        st->click_until = 0;
        klog("мышь: левая кнопка отпущена");
    }
    if (!st->mouse_mode)
        return;

    // удержание R3 дольше порога — переходим в режим колеса
    if (!st->scroll_mode && st->r3_down && st->r3_time
        && now - st->r3_time >= R3_CLICK_MS) {
        st->scroll_mode = 1;
        st->acc_wheel = 0.0f;
        klog("режим колеса включён");
    }

    if (st->scroll_mode) {
        float n = curve_norm(c, st->ry);
        if (n > 0.0f) {
            float step = n * n * WHEEL_RATE;
            st->acc_wheel += (st->ry <= 0) ? step : -step;
        }
        if (st->acc_wheel >= 1.0f) {
            emit(mouse_fd, EV_REL, REL_WHEEL, 1);
            emit_syn(mouse_fd);
            st->acc_wheel -= 1.0f;
        } else if (st->acc_wheel <= -1.0f) {
            emit(mouse_fd, EV_REL, REL_WHEEL, -1);
            emit_syn(mouse_fd);
            st->acc_wheel += 1.0f;
        }
        return;
    }

    st->acc_x += curve_speed(c, st->rx);
    st->acc_y += curve_speed(c, st->ry);

    int dx = (int)st->acc_x;
    int dy = (int)st->acc_y;
    st->acc_x -= (float)dx;
    st->acc_y -= (float)dy;

    if (!dx && !dy)
        return;
    if (dx)
        emit(mouse_fd, EV_REL, REL_X, dx);
    if (dy)
        emit(mouse_fd, EV_REL, REL_Y, dy);
    emit_syn(mouse_fd);
}

// -------------------------------------------------------------------- main

int main(void)
{
    kmsg_fd = open("/dev/kmsg", O_WRONLY | O_CLOEXEC);
    klog("запуск");

    struct prop layout = { .name = "persist.sys.btn_layout" };
    prop_poll(&layout, now_ms());
    int layout_nintendo = strcmp(layout.value, "nintendo") == 0;
    klog("btn_layout=%s (%s)", layout.value[0] ? layout.value : "xbox",
         layout_nintendo ? "A/B и X/Y переставлены" : "без перестановки");

    // Следим за всеми четырьмя настройками кривой, а не за одной: иначе
    // правка только max или dead осталась бы незамеченной до перезапуска.
    struct curve curve;
    curve_load(&curve);
    struct prop curve_props[] = {
        { .name = "persist.sys.mouse_max"  },
        { .name = "persist.sys.mouse_pow"  },
        { .name = "persist.sys.mouse_dead" },
        { .name = "persist.sys.mouse_axis" },
    };
    const int NCURVE = (int)(sizeof(curve_props) / sizeof(curve_props[0]));
    for (int i = 0; i < NCURVE; i++)
        prop_poll(&curve_props[i], now_ms());

    int mouse_fd = mouse_create();
    if (mouse_fd < 0) {
        close(kmsg_fd);
        return 1;
    }

    for (;;) {
        int raw_fd = find_raw_pad();
        if (raw_fd < 0) {
            sleep(1);
            continue;
        }
        if (ioctl(raw_fd, EVIOCGRAB, 1) < 0)
            klog("EVIOCGRAB не прошёл: %s", strerror(errno));
        else
            klog("EVIOCGRAB на сыром геймпаде");

        int pad_fd = pad_create(raw_fd);
        if (pad_fd < 0) {
            close(raw_fd);
            sleep(1);
            continue;
        }

        struct state st;
        memset(&st, 0, sizeof(st));
        long long last_tick = now_ms();
        long long last_loop = 0;

        for (;;) {
            struct pollfd pfd = { .fd = raw_fd, .events = POLLIN };
            int pr = poll(&pfd, 1, POLL_MS);
            if (pr < 0) {
                if (errno == EINTR)
                    continue;
                klog("ошибка poll: %s", strerror(errno));
                break;
            }
            if (pr > 0 && (pfd.revents & (POLLERR | POLLHUP)))
                break;

            long long now = now_ms();
            if (last_loop && now - last_loop >= STALL_WARN_MS)
                klog("задержка цикла %lld мс", now - last_loop);
            last_loop = now;

            if (pr > 0 && (pfd.revents & POLLIN)) {
                struct input_event ev;
                int broken = 0;
                for (;;) {
                    ssize_t n = read(raw_fd, &ev, sizeof(ev));
                    if (n == (ssize_t)sizeof(ev)) {
                        handle_event(&st, &ev, pad_fd, mouse_fd,
                                     layout_nintendo, now_ms());
                        continue;
                    }
                    if (n < 0 && (errno == EAGAIN || errno == EINTR))
                        break;
                    broken = 1;
                    break;
                }
                if (broken)
                    break;
            }

            now = now_ms();

            // окно двойного аккорда истекло
            if (st.kill_armed && now - st.kill_arm_time > KILL_WINDOW_MS) {
                st.kill_armed = 0;
                st.kill_used = 0;
            }

            if (prop_poll(&layout, now)) {
                int was = layout_nintendo;
                layout_nintendo = strcmp(layout.value, "nintendo") == 0;
                if (was != layout_nintendo)
                    klog("btn_layout -> %s (%s)",
                         layout.value[0] ? layout.value : "xbox",
                         layout_nintendo ? "A/B и X/Y переставлены"
                                         : "без перестановки");
            }
            int curve_changed = 0;
            for (int i = 0; i < NCURVE; i++)
                if (prop_poll(&curve_props[i], now))
                    curve_changed = 1;
            if (curve_changed)
                curve_load(&curve);

            if (now - last_tick >= POLL_MS) {
                last_tick = now;
                mouse_tick(&st, &curve, mouse_fd, now);
            }
        }

        klog("геймпад отключился (мышь:%s), ищу заново",
             st.mouse_mode ? "ON" : "OFF");
        close(pad_fd);
        ioctl(raw_fd, EVIOCGRAB, 0);
        close(raw_fd);
    }
}
