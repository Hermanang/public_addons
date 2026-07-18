/** @odoo-module **/

/*
 * Tour Story 16.2 — Vérifie que le menu de supervision "Calendriers en
 * pause SAV > 30 j" est accessible à un manager et affiche la vue liste
 * sans erreur JS.
 *
 * Ce tour est le premier de l'initiative optical_crm_followup — il vise
 * un test bout-en-bout léger de navigation + rendu vue, plutôt qu'un
 * scénario métier complet (couvert par les tests unitaires TransactionCase).
 */

import { registry } from "@web/core/registry";

registry.category("web_tour.tours").add("optical_crm_followup.tour_sav_supervision", {
    url: "/odoo",
    steps: () => [
        {
            trigger: 'a[data-menu-xmlid="optical_crm_followup.menu_optical_followup_root"]',
            content: "Ouvrir le menu top-level Fidélisation",
            run: "click",
        },
        {
            trigger: 'a[data-menu-xmlid="optical_crm_followup.menu_optical_followup_supervision"]',
            content: "Ouvrir le sous-menu Vues de supervision",
            run: "click",
        },
        {
            trigger: 'a[data-menu-xmlid="optical_crm_followup.menu_optical_followup_sav_paused_30d"]',
            content: "Ouvrir Calendriers en pause SAV > 30 j",
            run: "click",
        },
        {
            trigger: '.o_list_view, .o_view_nocontent',
            content: "La vue liste ou l'écran vide doit apparaître (rendu sans erreur JS)",
        },
    ],
});
