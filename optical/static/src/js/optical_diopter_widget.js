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
        placeholder: { type: String, optional: true },
    };
    static defaultProps = {
        step: 0.25,
    };

    setup() {
        this.state = useState({
            hasFocus: false,
        });
        this.inputRef = useInputField({
            getValue: () => this.formattedValue,
            refName: "numpadDecimal",
            parse: (v) => parseFloat(v),
        });
        useNumpadDecimal();
    }

    onFocusIn() {
        this.state.hasFocus = true;
    }

    onFocusOut() {
        this.state.hasFocus = false;
    }

    onKeyDown(ev) {
        if (ev.key === "ArrowUp" || ev.key === "ArrowDown") {
            ev.preventDefault();
            const currentValue = this.props.record.data[this.props.name] || 0;
            const delta = ev.key === "ArrowUp" ? this.step : -this.step;
            const precision = this.props.digits?.[1] ?? 2;
            const factor = Math.pow(10, precision);
            const newValue = Math.round((currentValue + delta) * factor) / factor;
            this.props.record.update({ [this.props.name]: newValue });
        }
    }

    get formattedValue() {
        const value = this.props.record.data[this.props.name];
        if (this.state.hasFocus) {
            if (value === false || value === null || value === undefined) {
                return "";
            }
            const precision = this.props.digits?.[1] ?? 2;
            const decimalPoint = localization.decimalPoint || ",";
            const parts = value.toFixed(precision).split(".");
            return parts.length > 1 ? parts[0] + decimalPoint + parts[1] : parts[0];
        }
        return formatDiopter(value, { digits: this.props.digits });
    }

    get displayValue() {
        return formatDiopter(this.props.record.data[this.props.name], {
            digits: this.props.digits,
        });
    }

    get step() {
        return this.props.step;
    }
}

export const opticalDiopterField = {
    component: OpticalDiopterField,
    displayName: _t("Diopter"),
    supportedTypes: ["float"],
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
            placeholder: attrs.placeholder,
        };
    },
};

registry.category("fields").add("optical_diopter", opticalDiopterField);
