{
    'name': 'Optique - Fidélisation & suivi client',
    'version': '18.0.1.7.0',
    'category': 'Optique/CRM',
    'summary': "Moteur de suivi client optique (calendriers, activités J-3, consentement, opt-out, alertes)",
    'description': """
Fidélisation & suivi client optique
====================================

Story 15.0 — Fondations techniques :
* Squelette des 6 modèles (plan, plan.step, schedule, schedule.line, holiday.window, lunar.date)
* Héritage des groupes du module optical (group_optical_user, group_optical_manager)
* ACL par modèle (12 lignes selon matrice architecture V1.1)
* Record rules multi-boutique via optical_warehouse_ids sur res.users
* Menu top-level "Fidélisation" avec sous-menus filtrés par groupe
* Fichier i18n/fr.po (module 100 % français)
* Hook post_init de vérification des rattachements utilisateurs / boutiques

Story 15.1 — Consentement, opt-out et fondations légales :
* Champs optical_followup_consent / optout / consent_by_legal_rep sur res.partner
* Horodatage automatique + cascade opt-out (schedules + activities)
* Helper _can_start_followup() (bool, reason_code)
* Template QWeb mail_footer_legal (Loi 2008-12)
* Bloc consentement dans le rapport bon de commande

Story 15.2 — Moteur calendriers, activités J-3, preset Standard 18m et alerte picking > 7 j :
* Hook stock.picking._action_done → création automatique du calendrier
* Preset "Standard lunettes 18 mois" livré (fallback FR-02, noupdate=1)
* Cron quotidien : matérialisation J-3, marquage overdue, alerte picking > 7 j
* Wizard outcome (Répondu / Injoignable / Refusé / A acheté)
* Digest mail 07h00 aux référents commerciaux
* Smart button vers calendrier de fidélisation sur SO

Story 16.1 — Preset Progressifs 24m et fenêtres de vigilance saisonnière :
* Preset "Progressifs 24 mois adaptation" livré (13 étapes, noupdate=1)
* 6 fenêtres de vigilance par défaut (Ramadan, Aïd, Tabaski, Magal,
  fêtes fin d'année, rentrée scolaire)
* Table lunaire 2026-2030 (20 records, verified=True)
* Enrichissement holiday.window : behavior (postpone_to_end / switch_channel_soft / none),
  ancrage lunaire ou plage civile MM-DD, canal recommandé, description
* Enrichissement lunar.date : source, verified, contrainte unique(year, event)
* Application des fenêtres à la matérialisation (idempotence, priorité,
  chatter partner sur report, note d'activité enrichie)

Story 16.2 — Suspension SAV et réachat anticipé :
* Extension helpdesk.ticket (create + write) — pause automatique du
  calendrier client à l'ouverture d'un ticket SAV, reprise à la clôture
  du dernier ticket (comportement symétrique sur ré-ouverture)
* Champ sav_paused_date + compute sav_pause_duration_days sur schedule
* Recalcul date_planned à la reprise : lignes dépassées → today+1,
  lignes futures inchangées
* Extension _create_from_picking : cas croisé réachat pendant SAV,
  chatter unifié pour éviter le ping-pong de messages
* Vue supervision "Calendriers en pause SAV > 30 j" (mitigation R4)
* Utilise stage_id.closed (helpdesk_mgmt OCA), pas stage.state

Story 17-4 — Refonte UX navigation quotidienne :
* Héritage mail.thread + mail.activity.mixin sur optical.followup.schedule
  (chatter propre au calendrier, double-post avec le chatter partner)
* Vue kanban schedule (groupé par state, records_draggable=0 pour
  préserver la state machine, progressbar 5 valeurs, mobile class,
  avatar référent + partner + boutique + prochaine étape)
* Vue calendar sur schedule.line (date_start=date_planned, mapping
  sémantique state → couleur via champ compute state_color)
* Form enrichie : statusbar clickable=0, 2 ribbon (annulé/abouti),
  smart button « X/N étapes » (fa-tasks), chatter en bas
* Décorations decoration-* sur la vue list schedule
* Action + menu « Mon planning » (calendar,list,form) avec filtre
  utilisateur (referent_user_id = uid + pending/overdue)
* Chatter SAV/réachat désormais posté sur le schedule ET le partner
  (subtype mail.mt_note, pas de notification email supplémentaire)

Story 17-1 — Preset Lentilles 90 j et flag VIP :
* Preset "Lentilles réassort 90 j" livré (noupdate=1, active=True) — 2 étapes
  WhatsApp (J+15 contrôle confort, J+60 rappel réassort), sélectionné par
  FR-02 quand la SO contient un produit optical_type='contact_lens'
  (priorité lentilles > progressive > any)
* Plan plan_vip_extra livré (noupdate=1) — 2 étapes vip_only=True :
  Attention anniversaire (Call, date=next(birthdate) après delivered_date) +
  Bilan personnalisé M+12 (Email, offset_days=365). Référencé par XML ID
  depuis _inject_vip_steps, jamais sélectionné par FR-02
* Champs res.partner : optical_customer_tier (Selection compute stored
  standard/vip) + optical_customer_tier_override (Boolean manager only,
  garde-fou Python write + groups= dans la vue). Compute batch-safe via
  read_group. Chatter bascule override (subtype mt_note).
* Paramètre système optical_crm_followup.vip_threshold_fcfa (défaut
  500 000 FCFA via constante Python, fallback résilient si absent /
  mal formé / ≤ 0 avec warning log). Base de calcul : amount_total (TTC)
  sur sale.order en state ∈ ('sale', 'done').
* Helper module-level _next_birthday_occurrence — repli 28-02 pour un
  anniversaire 29-02 en année non-bissextile (dateutil.relativedelta).
  Cas jour-même retenu comme passé (D-VIP-BIRTHDAY-SAMEDAY).
* Helper _inject_vip_steps sur optical.followup.schedule — garde-fou plan
  absent / inactif silencieux, skip anniversaire silencieux si birthdate
  manquante. Retourne (n_created, n_skipped_birthday).
* Intégration _create_from_picking : injection APRÈS boucle plan principal
  (compteur d'étapes du chatter principal reste len(plan.step_ids) — les
  étapes VIP sont tracées séparément par un chatter dédié). Double-post
  partner + schedule (subtype mt_note) avec motif (override manuel /
  seuil CA dépassé) et mention du skip anniversaire éventuel.
* Cross-check S17-3 : _anonymize_for_followup reset override VIP
* Cross-check S16.2 : lignes VIP suivent le cycle SAV pause / réachat

Story 17-3 — Compliance étendue, continuité RH et pilotage complet :
* 4 champs res.partner : optical_followup_previous_referent_user_id,
  optical_followup_majority_request_date, optical_anonymized,
  optical_anonymized_date + write-once irréversible (AC-B.3, NFR-14)
* Bouton « Confirmer consentement majeur » sur form res.partner
  (manager uniquement, garde-fou Python)
* Cron mensuel d'anonymisation cyclique (livré active=False, dry-run
  obligatoire) — critères opt-out > 12 mois OU inactif > 5 ans
* Rapport QWeb « Extrait droit d'accès » (7 sections) — Loi 2008-12
  art. 65-71, PDF attaché au chatter partner
* Nouveau modèle optical.followup.user.leave : absence programmée
  d'un référent (planned/active/ended) + calendrier + bascule cron
  06 h 00 + bouton manuel + réassignation activités vers suppléant
* Override res.users.write : détection désactivation + snapshot
  before/after + pivot _sync_referent_change_for_user + heuristique
  résolution 4 niveaux (SO récente > warehouse manager > premier
  manager scopé > unlink orphelin avec chatter)
* Cas croisé départ commercial pendant SAV en cours (M6) : reassign
  referent_user_id sur schedules paused (SAV et majority_pending)
* Nouveau wizard optical.followup.reassign.wizard : réattribution en
  masse par manager, 3 clics, preview counts en temps réel, filtre
  warehouse optionnel, 3 scopes (activités / référent / les deux)
* Template mail majority_renew_consent (renouvellement consentement
  à 18 ans, footer légal FR-16)
* Cron RH quotidien 06 h 00 fusionné : leaves planned→active +
  leaves active→ended + majority mail J-18 + majority pause J+90

Story 18-1 — Tiers clients configurables (refonte VIP en modèle paramétrable) :
* Nouveau modèle optical.customer.tier configurable en UI (nom, rang,
  seuil de CA, tier par défaut, couleur, code) — menu Configuration →
  Fidélisation → Tiers clients. Contrainte : exactement un tier par défaut.
* res.partner : optical_customer_tier (Selection standard/vip) remplacé par
  optical_customer_tier_id (Many2one compute stored) — calcul N tiers : le
  tier de plus haut seuil atteint par le CA cumulé TTC (SO sale/done), sinon
  le tier par défaut. Batch-safe (1 search tiers + 1 read_group SO).
* Override manager optical_customer_tier_override (Boolean « forcer VIP »)
  remplacé par optical_customer_tier_override_id (Many2one — forcer un tier
  précis), garde-fou Python write + groups= vue, chatter paramétré (nom du
  tier), reset à l'anonymisation.
* Seuil par tier (tier.threshold_fcfa) remplace le paramètre système global
  optical_crm_followup.vip_threshold_fcfa. Recompute des partners déclenché
  par write sur le tier (seuil/rang/actif/défaut).
* Injection d'étapes généralisée : plan.tier_id (Many2one) remplace le flag
  step.vip_only et le couplage XML ID _VIP_PLAN_XML_ID. _inject_tier_steps
  injecte les étapes de tout plan réservé dont le rang de tier est atteint
  (sémantique cumulative). Exclusion FR-02 par domaine tier_id = False.
* Migration V1 → 18-1 (migrations/18.0.1.7.0, pre + post) : seed des tiers
  standard/vip, reprise du seuil système, mapping partners + override + plan
  VIP, suppression des colonnes orphelines. Idempotente, sans perte.
* Iso-fonctionnalité garantie à config par défaut (2 tiers Standard/VIP,
  seuil 500 000) : comportement V1 identique.
    """,
    'author': 'Luxe Optique',
    'license': 'LGPL-3',
    'depends': [
        'optical',
        'sale_management',
        'stock',
        'mail',
        'helpdesk_mgmt',
    ],
    'data': [
        'security/ir.model.access.csv',
        'security/record_rules.xml',
        'data/mail_template_footer_legal_data.xml',
        'data/mail_activity_type_data.xml',
        'data/optical_customer_tier_data.xml',
        'data/optical_followup_plan_std18m_data.xml',
        'data/optical_followup_plan_progressive24m_data.xml',
        'data/optical_followup_plan_lentilles90j_data.xml',
        'data/optical_followup_plan_vip_extra_data.xml',
        'data/optical_followup_lunar_date_data.xml',
        'data/optical_followup_holiday_window_data.xml',
        'data/mail_template_std18m_data.xml',
        'data/mail_template_digest_overdue_data.xml',
        'data/mail_template_majority_renew_data.xml',
        'data/ir_cron_data.xml',
        'data/ir_cron_rh_data.xml',
        'views/res_users_views.xml',
        'views/res_partner_views.xml',
        'views/optical_customer_tier_views.xml',
        'views/optical_followup_plan_views.xml',
        'views/optical_followup_schedule_views.xml',
        'views/optical_followup_kpi_views.xml',
        'views/optical_followup_holiday_window_views.xml',
        'views/optical_followup_lunar_date_views.xml',
        'views/optical_followup_user_leave_views.xml',
        'views/sale_order_views.xml',
        'views/report_sale_order_consent.xml',
        'views/report_partner_data_export.xml',
        'wizards/optical_followup_line_feedback_wizard_views.xml',
        'wizards/optical_followup_reassign_wizard_views.xml',
        'wizards/optical_followup_assign_referent_wizard_views.xml',
        'views/menu_items.xml',
    ],
    'assets': {
        'web.assets_tests': [
            'optical_crm_followup/static/tests/tours/*.js',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
    'post_init_hook': 'post_init_hook',
}
