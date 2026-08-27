# One Piece Stock Tracker

Surveillance automatisée de produits scellés One Piece Card Game sur huit boutiques : Figurines Goodies, UltraJeux, Premium Bandai US, Parkage, Philibert, Carte One Piece, Oupi et Playin.

Le contrôle principal est déclenché toutes les 30 minutes par un scheduler externe. Le workflow GitHub `Stock Tracker` reste volontairement en `workflow_dispatch` afin d'éviter les doubles passages. Un watchdog GitHub vérifie ensuite qu'un contrôle récent a bien eu lieu et relance le tracker si nécessaire. Chaque boutique commence avec un petit décalage aléatoire : la fréquence ne change pas et aucune requête supplémentaire n'est ajoutée, mais les accès sont moins mécaniques.

## Produits surveillés

La cible prioritaire est définie dans `config.json` par `priority_set` (actuellement `OP17`). Les produits de cette extension passent avant les autres alertes, quel que soit leur statut pertinent : référencement, annonce, précommande, disponibilité ou retour en stock. Une disparition de la cible prioritaire n'est signalée qu'après deux scans consécutifs afin d'éviter les faux positifs liés à une page momentanément incomplète.

Les cartes à l'unité, versions japonaises, coréennes et chinoises, tapis, protège-cartes et autres accessoires ordinaires sont exclus. Un accessoire reste surveillé uniquement lorsque sa fiche indique explicitement qu'il contient une carte promotionnelle ou exclusive. Premium Bandai US constitue une exception contrôlée pour les produits officiels scellés asiatiques.

## Fiabilité

Le tracker applique plusieurs niveaux de protection : validation du format des produits, quarantaine de tout statut inconnu, refus d'un catalogue vide non autorisé, contrôle de la baisse du nombre de produits et du recoupement de leurs identités, puis confirmation sur deux passages distincts lorsqu'une forte modification paraît cohérente. Les boutiques temporairement indisponibles sont relancées et leur ancien stock est conservé en cas d'échec.

Lorsqu'un produit semble devenir commandable, sa fiche détaillée peut être contrôlée avant l'alerte, sans parcourir inutilement toutes les fiches. Les journaux indiquent pour chaque boutique la durée, le nombre de pages consultées, la répartition des statuts et les changements observés.

Les pannes techniques sont mémorisées afin de n'envoyer qu'une alerte à l'entrée en panne puis une alerte de rétablissement, sans spam à chaque passage. Les exceptions de panne connue ont une date de fin obligatoire. L'exception temporaire de Playin expire automatiquement le 17 août 2026 à 00:00, heure française ; le scanner redevient alors soumis aux contrôles normaux.

Les alertes de stock déjà remises à Discord sont elles aussi mémorisées dans `alertes_envoyees.json`. Un redémarrage ne renvoie donc pas la même disponibilité ; une vraie rupture réarme en revanche le prochain retour en stock.

L'historique (`ancien_stock.json`) et les petits fichiers d'état technique ne sont enregistrés qu'après un contrôle global accepté. Les notifications de stock et les alertes techniques utilisent deux webhooks Discord distincts stockés uniquement dans les secrets GitHub Actions.

## Tests et diagnostics

Les tests hors ligne sont regroupés dans `tests/` et exécutés par :

```bash
python -m unittest discover -s tests -v
```

Les diagnostics qui interrogent réellement une boutique ne font pas partie de la CI unitaire. Pour tester une boutique manuellement :

```bash
python diagnostics/scan_store.py premium_bandai
python diagnostics/scan_store.py philibert
```

Le diagnostic applique ensuite les mêmes règles d'intégrité que le tracker de production. Des extraits HTML représentatifs des huit boutiques, stockés dans `tests/fixtures/`, protègent les règles de lecture essentielles contre les régressions.

## Exécution locale

```bash
pip install -r requirements.txt
playwright install chromium
python -m unittest discover -s tests -v
python surveillance.py
```

`DISCORD_WEBHOOK` est requis uniquement lorsqu'une notification stock doit être envoyée. `DISCORD_ERROR_WEBHOOK` est utilisé pour les alertes techniques. Sur GitHub, ces valeurs doivent rester dans les secrets Actions.

## Workflows GitHub

`Stock Tracker` exécute la surveillance lorsqu'il est déclenché par le scheduler externe ou manuellement. `Stock Tracker Watchdog` vérifie à `27` et `57` de chaque heure qu'un passage récent existe et lance un rattrapage si nécessaire. `Unit tests` exécute toute la suite hors ligne sur les pull requests concernées et sur les changements de code de `main`, sans se relancer à chaque simple mise à jour du stock. `Scanner health checks` teste chaque boutique isolément chaque semaine et à la demande avec les mêmes règles d'intégrité que la production.

Les GitHub Actions utilisées par les workflows sont épinglées sur des SHA complets. Dependabot surveille les dépendances Python et les Actions GitHub afin de proposer leurs mises à jour automatiquement.
