-- ==========================================================================
-- Affectation des taxes par type de produit optique
-- Date : 2026-03-14
-- Base source : lxprod-cpy
--
-- Méthode recommandée : exécuter via odoo shell (ORM, plus sûr)
-- docker exec -it <odoo-container> odoo shell -d lxprod-cpy --no-http
--
-- Puis coller le script Python ci-dessous dans le shell :
-- ==========================================================================

-- """
-- tax_0 = env.ref('account.1_tva_exempt_0')       # 0% Exonéré
-- tax_18 = env.ref('account.1_tva_sale_18')        # 18% Vente
--
-- # Verres (lens + contact_lens) → 0% exonéré
-- verres = env['product.template'].search([('optical_type', 'in', ['lens', 'contact_lens'])])
-- verres.write({'taxes_id': [(6, 0, [tax_0.id])]})
-- print(f"{len(verres)} verres → taxe 0% exonérée")
--
-- # Montures → 18% vente
-- montures = env['product.template'].search([('optical_type', '=', 'frame')])
-- montures.write({'taxes_id': [(6, 0, [tax_18.id])]})
-- print(f"{len(montures)} montures → taxe 18%")
--
-- env.cr.commit()
-- """

-- ==========================================================================
-- Vérification post-exécution (SQL) :
-- ==========================================================================

-- Résumé par type optique et taxe
SELECT
    pt.optical_type,
    at.name AS taxe,
    at.amount AS taux,
    COUNT(*) AS nb_produits
FROM product_template pt
JOIN product_taxes_rel ptr ON ptr.prod_id = pt.id
JOIN account_tax at ON at.id = ptr.tax_id
WHERE pt.optical_type IN ('lens', 'contact_lens', 'frame')
GROUP BY pt.optical_type, at.name, at.amount
ORDER BY pt.optical_type, at.amount;

-- Contrôle : aucun verre avec taxe > 0%
SELECT pt.id, pt.name, at.amount
FROM product_template pt
JOIN product_taxes_rel ptr ON ptr.prod_id = pt.id
JOIN account_tax at ON at.id = ptr.tax_id
WHERE pt.optical_type IN ('lens', 'contact_lens')
  AND at.amount > 0;

-- Contrôle : aucune monture avec taxe 0%
SELECT pt.id, pt.name, at.amount
FROM product_template pt
JOIN product_taxes_rel ptr ON ptr.prod_id = pt.id
JOIN account_tax at ON at.id = ptr.tax_id
WHERE pt.optical_type = 'frame'
  AND at.amount = 0;
