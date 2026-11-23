# Déclenchement externe Premium Bandai

Le scanner et le contrôle de fraîcheur doivent être déclenchés par deux tâches
cron-job.org distinctes. Les programmes GitHub restent des secours : leur cadence
réelle n'est pas garantie. Un succès HTTP 204 du service de planification confirme
uniquement l'acceptation de la demande, pas l'achèvement du scan.

## Tâche de scan, toutes les trois minutes

- URL : `https://api.github.com/repos/fiiindus/catalog-monitor/actions/workflows/premium-bandai.yml/dispatches`
- Méthode : `POST`
- Corps JSON : `{"ref":"main"}`
- En-têtes : `Accept: application/vnd.github+json`, `Content-Type: application/json`,
  `X-GitHub-Api-Version: 2022-11-28`, et l'authentification existante.
- Tâche cron-job.org : `8568221`, titre `Premium Bandai US — toutes les 3 minutes`.
- Programmation : `*/3 * * * *`.
- Cadence enregistrée et vérifiée le 23 novembre 2026. Le secours GitHub conserve
  sa programmation toutes les cinq minutes.

## Renfort quotidien de 16 h à 19 h, heure de Papeete

La plage critique est 16:00 inclus à 19:00 exclus dans `Pacific/Tahiti` (UTC−10).
La tâche de base conserve ses passages toutes les trois minutes. Une tâche de
renfort ajoute les deux minutes intermédiaires, sans doublonner ces passages.
Les deux tâches réunies demandent donc un scan chaque minute de 16:00 à 18:59,
puis reviennent à trois minutes à 19:00.

- Tâche de renfort cron-job.org : `8568470`, titre
  `Premium Bandai US — renfort 16h–19h Papeete`.
- Même URL, méthode, corps et authentification que la tâche de scan.
- Fuseau conservé : `Atlantic/Reykjavik` (UTC). La plage correspond à
  02:00–05:00 UTC le lendemain, chaque jour.
- Programmation :
  `1-2,4-5,7-8,10-11,13-14,16-17,19-20,22-23,25-26,28-29,31-32,34-35,37-38,40-41,43-44,46-47,49-50,52-53,55-56,58-59 2-4 * * *`.
- État enregistré et vérifié le 23 novembre 2026 : actif. Avec la tâche de base, les demandes de
  déclenchement couvrent chaque minute de 16:00 à 18:59, heure de Papeete.

Cette cadence concerne les demandes de déclenchement. Après initialisation de la
session Premium Bandai, le scan réel validé le 4 octobre 2026 a analysé 104
références en environ 29 secondes ; le workflow complet a duré environ 51
secondes. Le verrou partagé continue de limiter les exécutions simultanées.

## Tâche de fraîcheur, toutes les cinq minutes avec décalage

- URL : `https://api.github.com/repos/fiiindus/catalog-monitor/actions/workflows/premium-bandai-health.yml/dispatches`
- Même méthode, corps et en-têtes.
- Programmation : `2-59/5 * * * *`.

Réutiliser les réglages du cron existant sans publier son jeton. Si GitHub retourne
401 ou 403, le propriétaire doit vérifier l'expiration et l'accès au dépôt
`catalog-monitor`. Ne pas placer le jeton dans le code ni dans les journaux.
Activer le contrôle de fraîcheur seulement après un premier scan du correctif.

## Concurrence et annulations (correctif du 23 novembre 2026)

Les scans dédiés et généraux conservent le verrou `stock-tracker-${{ github.ref }}`
et rechargent les états récents après l'attente. Ils écrivent les mêmes historiques :
les exécuter en parallèle risquerait de perdre des changements ou de doubler les alertes.
Le réglage `queue: max`, avec `cancel-in-progress: false`, conserve jusqu'à 100
exécutions en attente au lieu de remplacer la seule demande en attente à chaque
nouveau déclenchement. La file pleine peut encore provoquer des annulations.

Le contrôle de fraîcheur dispose désormais du groupe indépendant
`premium-bandai-freshness-${{ github.ref }}`, également avec `queue: max`.
Il peut vérifier le dernier scan même si un scanner est long ou bloqué. Il lit
`premium_bandai_health.json` sans l'écrire et sauvegarde uniquement son accusé
d'incident dans `premium_bandai_freshness_incident.json`. Le scanner reste seul
propriétaire des horodatages et des incidents de sources. À la première exécution,
le contrôle reprend l'ancien accusé `stale_notified`, sans renvoyer une alerte déjà remise.

Un scan général long peut encore retarder un scan dédié. Cette file ne garantit
pas une priorité stricte de Bandai ni un départ exact chaque minute : vérifier les
intervalles réels et l'absence d'accumulation en particulier sur 16 h–19 h. Si la
charge dépasse durablement la capacité, exécuter directement le scanner sur un
service permanent plutôt qu'allonger davantage la file sur Actions.

## Validation sur 24 heures

Vérifier les heures de départ et de fin des scans dédiés, leur origine
`workflow_dispatch`, les erreurs de sources et les incidents de fraîcheur. Mesurer
les intervalles réels entre scans complets : la simple réception des demandes
cron-job.org ne suffit pas. Un intervalle dépassant quinze minutes doit déclencher
une alerte technique Discord, une seule fois par incident, puis un rétablissement.

## Diagnostic sans notifications

`python premium_bandai_watch.py --dry-run` ne remet aucune notification et n'écrit
aucun historique. La page officielle de la série One Piece est la source
principale ; les recherches génériques restent des compléments et leur blocage ne
rend pas le passage incomplet. Jusqu'à trois références connues absentes du
catalogue sont contrôlées par rotation lorsque leur fiche reste accessible. Les
références absentes et les états temporairement inconnus restent mémorisés pour
éviter un nouveau référencement ou une fausse réouverture.

En production, les références récupérées continuent à déclencher leurs alertes
même lors d'un scan incomplet. Le passage est alors marqué en échec après
enregistrement des alertes déjà remises et de l'historique ; il ne rafraîchit pas
`last_complete_at` dans `premium_bandai_health.json`. La première dégradation et
son rétablissement sont envoyés au webhook technique existant.
