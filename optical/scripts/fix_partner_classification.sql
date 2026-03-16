-- ==========================================================================
-- Nettoyage classification contacts — Odoo Optical
-- Date : 2026-03-16 (mis à jour)
-- Base source : lxprod-cpy
-- À exécuter manuellement en prod
-- Ordre d'exécution : Script 1 → 2 → 3 → 4
-- ==========================================================================


-- ==========================================================================
-- SCRIPT 1 : Corriger is_company sur les personnes physiques mal encodées
-- 48 contacts identifiés comme personnes mais ayant is_company=true
-- (8482 FATIMATA TINE exclue : déjà corrigée dans lxprod-cpy)
-- ==========================================================================

UPDATE res_partner
SET is_company = FALSE
WHERE id IN (
    -- Contacts avec commandes, pas encore marqués patient (25)
    11159, -- AICHA FINDA GISELA BADJI
    11135, -- ALASSANE MBAYE CRATY
    8478,  -- AMINATA BA
    10747, -- AMINATA THIAM
    15326, -- Alioune Cire Kane
    8481,  -- Aminata Dia
    8547,  -- Bamba Dia
    7709,  -- CHAHID ABIOLA LATOUNDJI
    10970, -- CHANTAL BASSENE
    10834, -- Djibril Dia
    6672,  -- EMMANUEL J MUTONJ
    6911,  -- FALL MAMADOU LAMINE
    3035,  -- FALLOU YADE
    15000, -- FATIMATOU BARRY
    12612, -- FATOUMATA NDIAYE
    7903,  -- ISSA GUEYE
    10835, -- KHADY DIENG
    15639, -- KINE NDIAYE
    8518,  -- MODI DIEYE
    8991,  -- Madame Ndeye Drame Ba
    11073, -- NDEYE MBACKE DIOP
    15285, -- Ndeye Nguyen Thi-Thi Diagne Nee Diawara
    15016, -- Oleg Elisse Sambou
    8461,  -- ROKHYA DIABY
    14994, -- Salla MEISSA Fall
    -- Contacts déjà marqués patient mais is_company=true (21)
    15240, -- Aly Gueye
    15386, -- Amadou Dieye
    15220, -- Amina Dalil
    15310, -- Bintou R Samb
    8853,  -- DIAMILATOU THIAM
    15281, -- El Hadji Djabel
    15258, -- Fatima Fall
    15206, -- Fatima Thiam
    15254, -- HABIB KENGNE
    15123, -- Lee Nadia Aicha
    6824,  -- MOUHAMED IBRAHIMA FALL
    15183, -- Madame Mamanana Toure
    15211, -- Mame Couna Ndao
    8521,  -- Mery Ngom
    15154, -- Mouhamed El Khaly Ba
    15365, -- Mr Aboubakri Kane
    15340, -- Mr Lewy Yaniv Henoch Kouassi
    15355, -- NANCY SARAH FAYE
    15391, -- SENE OUSMANE
    15127, -- Yacine Ndoye
    15110, -- WAFA! (personne physique, patiente sous La Fondation BATONGA id=2565)
    -- Hermann (id=7) — personne physique (email: pfranckyves@gmail.com)
    7,     -- Hermann
    -- Vinci Energies — contact personne sous société
    15200  -- Vinci Energies Senegal, Pape T Diankha
);

-- Vérification Script 1 :
SELECT id, name, is_company FROM res_partner
WHERE id IN (11159,11135,8478,10747,15326,8481,8547,7709,10970,10834,
    6672,6911,3035,15000,12612,7903,10835,15639,8518,8991,11073,
    15285,15016,8461,14994,15240,15386,15220,15310,8853,15281,15258,
    15206,15254,15123,6824,15183,15211,8521,15154,15365,15340,15355,
    15391,15127,15110,7,15200)
ORDER BY name;


-- ==========================================================================
-- SCRIPT 2 : Corriger les sociétés marquées patient par erreur
-- GGA GROUPE et NSIA TECHNOLOGIES sont is_company=true ET is_patient=true
-- Ce sont de vraies sociétés, pas des patients
-- ==========================================================================

UPDATE res_partner SET is_patient = FALSE
WHERE id IN (
    15114, -- GGA GROUPE
    15017, -- NSIA TECHNOLOGIES
    15071  -- NSIA TECHNOLOGIES (doublon)
);

-- Vérification Script 2 :
SELECT id, name, is_company, is_patient FROM res_partner
WHERE id IN (15114, 15017, 15071);


-- ==========================================================================
-- SCRIPT 3 : Marquer is_patient=TRUE tous les clients ayant un devis/commande
-- Logique : tout contact client d'une commande = patient
-- Exclut uniquement les comptes systèmes et les sociétés connues
-- 241 contacts à marquer dans lxprod-cpy (au 2026-03-16)
-- ==========================================================================

UPDATE res_partner SET is_patient = TRUE
WHERE id IN (
    SELECT DISTINCT partner_id
    FROM sale_order
    WHERE partner_id IS NOT NULL
)
AND is_patient IS NOT TRUE
AND id NOT IN (
    1,     -- Luxe Optique (société propre)
    4,     -- Public user (compte système, 9 commandes de test)
    434,   -- ABS Bank
    627,   -- AXA (assureur)
    9686,  -- CREDIT DU SENEGAL
    15114, -- GGA GROUPE
    15017, -- NSIA TECHNOLOGIES
    15071  -- NSIA TECHNOLOGIES (doublon)
);

-- Vérification Script 3 :
SELECT
    COUNT(*) AS total_patients_marques,
    SUM(CASE WHEN is_company THEN 1 ELSE 0 END) AS dont_societes
FROM res_partner
WHERE is_patient = TRUE
AND id IN (SELECT DISTINCT partner_id FROM sale_order);


-- ==========================================================================
-- SCRIPT 4 : Vérification finale — aucune société/assureur ne doit être patient
-- ==========================================================================

-- Contrôle : contacts qui seraient patient ET assureur (incohérent)
SELECT id, name, is_patient, is_insurer
FROM res_partner
WHERE is_patient = TRUE AND is_insurer = TRUE;

-- Contrôle : sociétés marquées patient (à revoir si nouvelles apparaissent)
SELECT id, name, is_company, is_patient
FROM res_partner
WHERE is_patient = TRUE AND is_company = TRUE
ORDER BY name;

-- Contrôle : les exclusions sont bien non-patient
SELECT id, name, is_company, is_patient, is_insurer
FROM res_partner
WHERE id IN (1, 4, 434, 627, 9686, 15114, 15017, 15071);
