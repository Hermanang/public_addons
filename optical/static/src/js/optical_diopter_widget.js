/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useInputField } from "@web/views/fields/input_field_hook";
import { useNumpadDecimal } from "@web/views/fields/numpad_decimal_hook";
import { parseFloat } from "@web/views/fields/parsers";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { localization } from "@web/core/l10n/localization";

import { Component, useState } from "@odoo/owl";

/**
 * Format a diopter value with explicit sign (+/-) and locale decimal separator.
 * Examples (French locale): 1.25 -> "+1,25", -0.75 -> "-0,75", 0 -> "0,00"
 */
function formatDiopter(value, options = {}) {
    if (value === false || value === null || value === undefined) {
        return "";
    }
    const precision = options.digits?.[1] ?? 2;
    const decimalPoint = localization.decimalPoint || ",";
    const formatted = Math.abs(value).toFixed(precision);
    const parts = formatted.split(".");
    const result = parts.length > 1 ? parts[0] + decimalPoint + parts[1] : parts[0];
    if (value > 0) {
        return "+" + result;
    } else if (value < 0) {
        return "-" + result;
    }
    return "0" + decimalPoint + "0".repeat(precision);
}

export class OpticalDiopterField extends Component {
    static template = "optical.OpticalDiopterField";
    static props = {
        ...standardFieldProps,
        digits: { type: Array, optional: true },
        step: { type: Number, optional: true },
        min: { type: Number, optional: true },
        max: { type: Number, optional: true },
        placeholder: { type: String, optional: true },
    };
    static defaultProps = {
        step: 0.25,
    };

    setup() {
        this.state = useState({
            hasFocus: false,
            showDropdown: false,
            activeIndex: 0,
            filter: "",
        });
        this.inputRef = useInputField({
            getValue: () => this.formattedValue,
            refName: "numpadDecimal",
            parse: (v) => this.snapValue(parseFloat(v)),
        });
        useNumpadDecimal();
    }

    // --- Type / precision helpers ---

    get isInteger() {
        return this.props.record.fields[this.props.name].type === "integer";
    }

    get precision() {
        return this.isInteger ? 0 : this.props.digits?.[1] ?? 2;
    }

    /** A bounded value list (combobox) is offered only when both min and max are set. */
    get hasOptions() {
        return (
            this.props.min !== undefined &&
            this.props.min !== null &&
            this.props.max !== undefined &&
            this.props.max !== null
        );
    }

    get step() {
        return Math.abs(this.props.step || (this.isInteger ? 1 : 0.25));
    }

    // --- Value formatting ---

    formatValue(value) {
        if (value === false || value === null || value === undefined) {
            return "";
        }
        if (this.isInteger) {
            return String(value);
        }
        return formatDiopter(value, { digits: this.props.digits });
    }

    get formattedValue() {
        const value = this.props.record.data[this.props.name];
        if (this.state.hasFocus) {
            if (value === false || value === null || value === undefined) {
                return "";
            }
            if (this.isInteger) {
                return String(value);
            }
            const decimalPoint = localization.decimalPoint || ",";
            const parts = value.toFixed(this.precision).split(".");
            return parts.length > 1 ? parts[0] + decimalPoint + parts[1] : parts[0];
        }
        return this.formatValue(value);
    }

    get displayValue() {
        return this.formatValue(this.props.record.data[this.props.name]);
    }

    // --- Snap to a valid value within [min, max] on the configured step ---

    snapValue(value) {
        if (
            value === false ||
            value === null ||
            value === undefined ||
            Number.isNaN(value)
        ) {
            return value;
        }
        if (!this.hasOptions) {
            // Free numeric input (e.g. prism): keep the raw value.
            return value;
        }
        const step = this.step;
        const min = Math.min(this.props.min, this.props.max);
        const max = Math.max(this.props.min, this.props.max);
        let v = Math.round(value / step) * step;
        v = Math.min(max, Math.max(min, v));
        const factor = Math.pow(10, this.precision);
        return Math.round(v * factor) / factor;
    }

    // --- Options (predefined valid values) ---

    get allOptions() {
        if (!this.hasOptions) {
            return [];
        }
        const step = this.step;
        const min = Math.min(this.props.min, this.props.max);
        const max = Math.max(this.props.min, this.props.max);
        const factor = Math.pow(10, this.precision);
        const options = [];
        for (let v = min; v <= max + 1e-9; v += step) {
            const value = Math.round(v * factor) / factor;
            options.push({
                value,
                label: this.formatValue(value),
                key: String(value),
            });
        }
        return options;
    }

    get filteredOptions() {
        const raw = (this.state.filter || "").trim();
        if (!raw) {
            return this.allOptions;
        }
        const normalized = raw.replace(",", ".");
        return this.allOptions.filter(
            (o) => o.key.includes(normalized) || o.label.includes(raw)
        );
    }

    get activeOption() {
        return this.filteredOptions[this.state.activeIndex];
    }

    currentIndex() {
        const value = this.props.record.data[this.props.name];
        const idx = this.filteredOptions.findIndex((o) => o.value === value);
        return idx >= 0 ? idx : 0;
    }

    // --- Events ---

    onFocusIn() {
        this.state.hasFocus = true;
        if (this.hasOptions) {
            this.state.filter = "";
            this.state.showDropdown = true;
            this.state.activeIndex = this.currentIndex();
        }
    }

    onFocusOut() {
        this.state.hasFocus = false;
        this.state.showDropdown = false;
    }

    onInput(ev) {
        if (this.hasOptions) {
            this.state.filter = ev.target.value;
            this.state.showDropdown = true;
            this.state.activeIndex = 0;
        }
    }

    moveActive(delta) {
        if (!this.state.showDropdown) {
            this.state.showDropdown = true;
            this.state.activeIndex = this.currentIndex();
            return;
        }
        const len = this.filteredOptions.length;
        if (!len) {
            return;
        }
        let i = this.state.activeIndex + delta;
        if (i < 0) {
            i = 0;
        } else if (i > len - 1) {
            i = len - 1;
        }
        this.state.activeIndex = i;
    }

    selectOption(option) {
        this.props.record.update({ [this.props.name]: option.value });
        this.state.showDropdown = false;
        this.state.filter = "";
    }

    onKeyDown(ev) {
        if (this.hasOptions) {
            if (ev.key === "ArrowDown") {
                ev.preventDefault();
                this.moveActive(1);
            } else if (ev.key === "ArrowUp") {
                ev.preventDefault();
                this.moveActive(-1);
            } else if (ev.key === "Enter") {
                if (this.state.showDropdown && this.activeOption) {
                    ev.preventDefault();
                    this.selectOption(this.activeOption);
                }
            } else if (ev.key === "Escape") {
                this.state.showDropdown = false;
            }
            return;
        }
        // Free numeric input (prism): arrow keys step the value.
        if (ev.key === "ArrowUp" || ev.key === "ArrowDown") {
            ev.preventDefault();
            const currentValue = this.props.record.data[this.props.name] || 0;
            const delta = ev.key === "ArrowUp" ? this.step : -this.step;
            const factor = Math.pow(10, this.precision);
            const newValue = Math.round((currentValue + delta) * factor) / factor;
            this.props.record.update({ [this.props.name]: newValue });
        }
    }
}

export const opticalDiopterField = {
    component: OpticalDiopterField,
    displayName: _t("Diopter"),
    supportedTypes: ["float", "integer"],
    isEmpty: () => false,
    extractProps: ({ attrs, options }) => {
        let digits;
        if (attrs.digits) {
            digits = JSON.parse(attrs.digits);
        } else if (options.digits) {
            digits = options.digits;
        }
        return {
            digits,
            step: options.step,
            min: options.min,
            max: options.max,
            placeholder: attrs.placeholder,
        };
    },
};

registry.category("fields").add("optical_diopter", opticalDiopterField);
