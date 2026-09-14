#!/usr/bin/env python3
"""Вносит в DTS платы то, чего не хватало в опубликованных исходниках.

Семь отличий между DTB из исходников и тем, что реально работает:
  1-3  правки самого автора, сделанные после публикации дерева:
       spk-ctl-gpios перенесён в узел кодека, spk-con-gpios убран
       из звуковой карты, vfront-porch 20 -> 31;
  4-6  наши: контроллер Type-C HUSB311 (чинит USB host),
       usb-role-switch вместо extcon, spk-mute-delay-ms (щелчки динамика);
    7  наша: snps,loa-filter-en-quirk — фильтр ложного babble в USB,
       работает только вместе с правкой drivers/usb/dwc3/core.c.

Всё оформлено переопределениями в DTS платы, общие dtsi не трогаются.
"""
import io, sys, os

K = os.path.expanduser("~/rg52/kernel_rk3562_rg52mini")
DTS = K + "/arch/arm64/boot/dts/rockchip/rk3562-rg52mini.dts"

s = io.open(DTS, encoding="utf-8").read()
if "husb311" in s:
    sys.exit("правки уже внесены")

# заголовок: нужен pd.h для макросов PDO_FIXED
old_inc = '#include "rk3562.dtsi"'
if "dt-bindings/usb/pd.h" not in s:
    s = s.replace(old_inc, '#include <dt-bindings/usb/pd.h>\n' + old_inc, 1)

# кодек: добавить управление усилителем и задержку
old_codec = """/* RK817 codec — RG52 Mini uses higher headphone volume */
&rk817_codec {
	hp-volume = <54>;
};"""
new_codec = """/* RK817 codec — RG52 Mini uses higher headphone volume.
 *
 * spk-ctl-gpios lives here rather than on the sound card: the codec driver
 * gates the external amplifier from rk817_digital_mute_dac(), so it can drop
 * the GPIO before the DAC transition instead of after it.
 *
 * spk-mute-delay-ms is what makes that gating silent. Without it the
 * amplifier switches right up against the DAC transition and every
 * start/stop of playback is audible as a click. hp-mute-delay-ms already
 * existed for the headphone path; the speaker path had been overlooked. */
&rk817_codec {
	hp-volume = <54>;
	spk-ctl-gpios = <&gpio3 RK_PC3 GPIO_ACTIVE_HIGH>;
	spk-mute-delay-ms = <100>;
};

/* The amplifier GPIO is claimed by the codec above, so drop it here. */
&rk817_sound {
	/delete-property/ spk-con-gpios;
};

/* Panel vertical front porch: 31 lines, not the 20 the shared dtsi sets. */
&dsi_timing0 {
	vfront-porch = <31>;
};"""
assert old_codec in s, "не нашёл блок кодека"
s = s.replace(old_codec, new_codec, 1)

# USB host: контроллер Type-C
usb = """
/* ---- USB host: Type-C controller ---------------------------------------- */

/*
 * The USB-C receptacle has no ID pin: the data role is decided from the CC
 * lines by a HUSB311 on i2c2. Without this node dwc3 waits on an extcon fed
 * by the phy's ID detection, that signal never comes, and the port stays a
 * peripheral forever - no root hub, no OTG at all.
 *
 * Values follow the vendor's own configuration for this board.
 */
&i2c2 {
	status = "okay";

	usbc0: husb311@4e {
		compatible = "hynetek,husb311";
		reg = <0x4e>;
		interrupt-parent = <&gpio0>;
		interrupts = <RK_PB7 IRQ_TYPE_LEVEL_LOW>;
		pinctrl-names = "default";
		pinctrl-0 = <&usbc0_int>;
		vbus-supply = <&otg_switch>;
		status = "okay";

		ports {
			#address-cells = <1>;
			#size-cells = <0>;

			port@0 {
				reg = <0>;

				usbc0_role_sw: endpoint@0 {
					remote-endpoint = <&dwc3_role_switch>;
				};
			};
		};

		usb_con: connector {
			compatible = "usb-c-connector";
			label = "USB-C";
			data-role = "dual";
			power-role = "dual";
			try-power-role = "sink";
			op-sink-microwatt = <1000000>;
			sink-pdos = <PDO_FIXED(5000, 3000, PDO_FIXED_USB_COMM)>;
			source-pdos = <PDO_FIXED(5000, 2000, PDO_FIXED_DUAL_ROLE |
						 PDO_FIXED_USB_COMM |
						 PDO_FIXED_DATA_SWAP)>;
		};
	};
};

/* Take the role from the Type-C controller instead of the phy's extcon. */
&usbdrd_dwc3 {
	/delete-property/ extcon;
	usb-role-switch;

	/* Poor cables and ESD can fake a USB2 babble condition during the idle
	 * window between high-speed EOF2 and the next microframe SOF. xHCI then
	 * disables the root hub port outright and the device drops off:
	 *
	 *     usb usb1-port1: disabled by hub (EMI?), re-enabling...
	 *     usb 1-1: USB disconnect, device number 2
	 *
	 * GUCTL1.LOA_FILTER_EN makes the controller require three consecutive
	 * babble detections before killing the port, which filters the
	 * transient false ones out. Needs the matching driver support in
	 * drivers/usb/dwc3/core.c. */
	snps,loa-filter-en-quirk;

	port {
		#address-cells = <1>;
		#size-cells = <0>;

		dwc3_role_switch: endpoint@0 {
			reg = <0>;
			remote-endpoint = <&usbc0_role_sw>;
		};
	};
};
"""

# pinctrl: вывод прерывания контроллера
old_pin = """&pinctrl {
	vcc3v3_lcd_n {
		lcd_pwren_h: lcd-pwren-h {
			rockchip,pins = <0 RK_PB0 RK_FUNC_GPIO &pcfg_pull_up>;
		};
	};
};"""
new_pin = """&pinctrl {
	vcc3v3_lcd_n {
		lcd_pwren_h: lcd-pwren-h {
			rockchip,pins = <0 RK_PB0 RK_FUNC_GPIO &pcfg_pull_up>;
		};
	};

	usb-typec {
		usbc0_int: usbc0-int {
			rockchip,pins = <0 RK_PB7 RK_FUNC_GPIO &pcfg_pull_up>;
		};
	};
};"""
assert old_pin in s, "не нашёл блок pinctrl"
s = s.replace(old_pin, usb + "\n/* ---- Per-device pinctrl additions --------------------------------------- */\n\n" + new_pin, 1)
s = s.replace("/* ---- Per-device pinctrl additions ---------------------------------------- */\n\n" + usb, usb, 1)

io.open(DTS, "w", encoding="utf-8", newline="\n").write(s)
print("DTS обновлён:", DTS, len(s.splitlines()), "строк")
