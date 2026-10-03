# Déclenchement externe Premium Bandai

Le scanner et le contrôle de fraîcheur doivent être déclenchés par deux tâches
cron-job.org distinctes. Les programmes GitHub restent des secours : leur cadence
réelle n'est pas garantie. Un succès HTTP 204 du service de planification confirme
uniquement l'acceptation de la demande, pas l'achèvement du scan.

## Tâche de scan, toutes les cinq minutes

- URL : `https://api.github.com/repos/fiiindus/catalog-monitor/actions/workflows/premium-bandai.yml/dispatches`
- Méthode : `POST`
- Corps JSON : `{"ref":"main"}`
- En-têtes : `Accept: application/vnd.github+json`, `Content-Type: application/json`,
  `X-GitHub-Api-Version: 2022-11-28`, et l'authentification existante.
- Programmation : `*/5 * * * *`.

## Renfort quotidien de 16 h à 19 h, heure de Papeete

La plage critique est 16:00 inclus à 19:00 exclus dans `Pacific/Tahiti` (UTC−10).
La tâche de base conserve ses passages toutes les cinq minutes. Une tâche de
renfort ajoute les quatre minutes intermédiaires, sans doublonner ces passages.
Les deux tâches réunies demandent donc un scan chaque minute de 16:00 à 18:59,
puis reviennent à cinq minutes à 19:00.

- Tâche de renfort cron-job.org : `8568470`, titre
  `Premium Bandai US — renfort 16h–19h Papeete`.
- Même URL, méthode, corps et authentification que la tâche de scan.
- Fuseau conservé : `Atlantic/Reykjavik` (UTC). La plage correspond à
  02:00–05:00 UTC le lendemain, chaque jour.
- Programmation :
  `1-4,6-9,11-14,16-19,21-24,26-29,31-34,36-39,41-44,46-49,51-54,56-59 2-4 * * *`.
- État préparé : désactivé, comme la tâche de base.

Cette cadence concerne les demandes de déclenchement. Le scan réel observé
dure environ trois minutes et le verrou partagé limite les exécutions simultanées.
Il faut résoudre les délais des recherches et de la fiche anniversaire, puis
mesurer les intervalles réels, avant de promettre une vérification chaque minute.

## Tâche de fraîcheur, toutes les cinq minutes avec décalage

- URL : `https://api.github.com/repos/fiiindus/catalog-monitor/actions/workflows/premium-bandai-health.yml/dispatches`
- Même méthode, corps et en-têtes.
- Programmation : `2-59/5 * * * *`.

Réutiliser les réglages du cron existant sans publier son jeton. Si GitHub retourne
401 ou 403, le propriétaire doit vérifier l'expiration et l'accès au dépôt
`catalog-monitor`. Ne pas placer le jeton dans le code ni dans les journaux.
Activer le contrôle de fraîcheur seulement après un premier scan du correctif.

Les deux workflows partagent le verrou du tracker et rechargent les états les plus
récents après l'attente. Un scan général long peut donc encore retarder un scan
dédié ou le contrôle technique. Si ces retards persistent, exécuter directement le
scanner sur un service permanent plutôt que promettre une cadence stricte sur Actions.

## Validation sur 24 heures

Vérifier les heures de départ et de fin des scans dédiés, leur origine
`workflow_dispatch`, les erreurs de sources et les incidents de fraîcheur. Mesurer
les intervalles réels entre scans complets : la simple réception des demandes
cron-job.org ne suffit pas. Un intervalle dépassant quinze minutes doit déclencher
une alerte technique Discord, une seule fois par incident, puis un rétablissement.

## Diagnostic sans notifications

`python premium_bandai_watch.py --dry-run` ne remet aucune notification et n'écrit
aucun historique. Les recherches en échec, paginations répétées et limites atteintes
sont signalées. La fiche du Japanese 4th Anniversary Set est vérifiée à chaque
passage ; trois références connues absentes des catalogues sont contrôlées par
rotation. Les références absentes et les états temporairement inconnus restent
mémorisés pour éviter un nouveau référencement ou une fausse réouverture.

En production, les références récupérées continuent à déclencher leurs alertes
même lors d'un scan incomplet. Le passage est alors marqué en échec après
enregistrement des alertes déjà remises et de l'historique ; il ne rafraîchit pas
`last_complete_at` dans `premium_bandai_health.json`. La première dégradation et
son rétablissement sont envoyés au webhook technique existant.
