# Panier assisté Premium Bandai US — version de validation 0.1

Extension locale pour Chrome ou Edge sur ordinateur. Elle complète le tracker
sans attendre les passages GitHub Actions et sans transmettre la session à un
serveur. Aucun identifiant, cookie ou moyen de paiement n'est lu par l'extension.
Les contrôles d'interface utilisent la session déjà ouverte dans le navigateur.

## Installation

1. Décompresser l'archive dans un dossier permanent.
2. Ouvrir `chrome://extensions` (Chrome) ou `edge://extensions` (Edge).
3. Activer **Mode développeur**, puis **Charger l'extension non empaquetée**.
4. Sélectionner le dossier **extension** contenant `manifest.json`.
5. Se connecter normalement sur Premium Bandai US et ouvrir la fiche voulue.
6. Vérifier que l'article est absent du panier et que la quantité est **1**.
7. Cliquer sur l'extension, vérifier le plafond de prix en USD, cocher la case,
   puis cliquer sur **Démarrer les tentatives**.

L'installation reste à faire dans le navigateur de l'utilisateur. La version
n'est pas activée par la création du fichier ou de la pull request.
Ne pas communiquer les cookies ou le mot de passe pour l'installer.

## Fonctionnement

- Un produit choisi explicitement à la fois ; aucun ciblage par défaut.
- Quantité de 1 ; plafond du prix du produit, hors livraison et taxes.
- Quand la fiche indique une rupture ou une disponibilité à venir, nouvelle
  lecture après un rechargement programmé cinq secondes plus tard.
- Quand le bouton produit devient actif, tentative d'ajout. Le site nomme ce
  bouton **PLACE ORDER** (`msg.placeOrder`) sur la fiche ; l'extension ne clique
  jamais un bouton du panier, du paiement ou d'une autre page.
- Après un nouveau refus explicite d'ajout pour rupture de stock, nouvelle
  tentative après cinq secondes, sans nombre maximum d'essais.
- Si la réponse ne permet pas de conclure, ouverture du panier dans l'onglet
  suivi pour rechercher la ligne du produit avec quantité 1. Aucun nouvel ajout
  n'est envoyé pendant cette vérification.
- Si la ligne est reconnue, notification et arrêt. Sinon, arrêt demandant une
  vérification manuelle : une absence apparente ne prouve pas que la première
  requête n'aboutira pas tardivement.
- Déconnexion, prix supérieur au plafond, quantité modifiée, contrôle humain
  ou blocage : arrêt. Aucun contournement et aucune nouvelle tentative à l'aveugle.
- Le bouton **Arrêter** coupe les nouvelles tentatives. Une requête déjà envoyée
  au site peut encore aboutir ; vérifier le panier avant de relancer.

Laisser le PC éveillé, le navigateur et l'onglet ouverts. Le délai réel comprend
le chargement de la page ; les onglets en arrière-plan peuvent être ralentis par
le navigateur. Ce module ne tourne pas sur un PC éteint et ne constitue pas un
service disponible en permanence. Il ne découvre pas les nouvelles fiches :
le tracker Discord reste utile pour les repérer, puis choisir celles à surveiller.

Le paiement reste manuel. La présence dans le panier ne garantit pas à elle
seule une réservation de stock. La synchronisation avec un autre appareil et
la durée éventuelle de réservation restent à vérifier sur le compte réel.

## Validation effectuée et limites

Structure de la fiche vérifiée sur le site public le 19 novembre 2026 (Tahiti) :
`.o-items__sidebar--inner`, titre, prix, quantité, bouton `msg.placeOrder` sur
une fiche en stock et bouton `msg.sorryOutOfStock` sur une fiche épuisée.
Aucun ajout réel ni achat n'a été effectué sur le compte de l'utilisateur.
Les messages de refus et la structure d'une ligne de panier ne sont pas encore
validés sur son compte ; une structure inconnue provoque un arrêt, jamais un
message de succès supposé. Un premier essai accompagné reste nécessaire avant
utilisation pour une sortie importante.

Tests hors ligne (Node.js 22 ou supérieur, aucune dépendance à installer) :

```sh
node --test tools/bandai-cart/tests/*.test.cjs
```

Dans l'archive autonome, depuis son dossier racine :

```sh
node --test tests/*.test.cjs
```

Les tests vérifient les prix et identités, les tentatives concurrentes, le délai
entre les essais, la reprise après un échec explicite, les réponses ambiguës,
l'arrêt manuel et l'absence de clic sur le panier. Les scénarios d'interface
emploient un DOM simulé, et ne prouvent pas une réussite sur le site réel.
