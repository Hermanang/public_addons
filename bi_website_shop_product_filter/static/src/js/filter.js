/** @odoo-module **/

import publicWidget from "@web/legacy/js/public/public_widget";
import '@website_sale/js/website_sale'
import VariantMixin from "@website_sale/js/sale_variant_mixin";
import { registry } from "@web/core/registry";

    

    publicWidget.registry.WebsiteSaleFilter = publicWidget.Widget.extend(VariantMixin, {
        selector: '.oe_website_sale',
        read_events: {   
            'change form.js_filtervalue input, form.js_filtervalue select': '_onChangeFilter',
        },

        _onChangeFilter: function (ev) {
            
            if (!ev.isDefaultPrevented()) {

                ev.preventDefault();
                $(ev.currentTarget).closest("form").submit();
            }
        },
    });
