# ha_jsy — notes pour la v1.1.0

Nom des canaux, correction des circuits 240 V sur panneau à phase auxiliaire,
identifiants d'entités indépendants de l'emplacement, et installation par le
Marketplace de Home Assistant 2026.11.

Base : v1.0.0 (première version publiée sur GitHub).

`jsy_modbusdecoder.py` n'est pas modifié. Les nouveautés ont été validées dans
Home Assistant 2026.2.3 contre le simulateur (`tools/jsy_simulator.py`). Sur un
JSY-MK-194G réel, la lecture, le changement d'ID Modbus et l'écriture des
compteurs d'énergie sont validés ; **le changement de vitesse reste à
confirmer** (voir la section 7).

---

## 1. Nom des canaux

Chaque canal peut recevoir un nom décrivant ce qu'il mesure (`Thermopompe`,
`Fournaise`). Le nom remplace le numéro du canal dans les entités :

| Sans nom | Canal 1 nommé `Thermopompe` |
|---|---|
| Voltage 1 | Thermopompe Voltage |
| Power 1 (signed) | Thermopompe Power (signed) |
| Energy Positive 1 (Set) | Thermopompe Energy Positive (Set) |
| Reset Energy Channel 1 | Thermopompe Reset Energy |

Les entités communes aux deux canaux (fréquence, informations du module) ne
changent pas.

## 2. Circuit mesuré : ligne–neutre ou ligne–ligne

Le module n'a qu'une seule entrée de tension, utilisée pour les deux canaux et
normalement branchée ligne–neutre (120 V). Pour une charge alimentée
ligne-à-ligne (disjoncteur bipolaire 240 V, sans neutre), le module calcule
donc la puissance avec 120 V au lieu de 240 V : la puissance et l'énergie
valent la moitié de la réalité.

Nouveau réglage par canal, « Circuit mesuré » :

| Choix | Effet |
|---|---|
| Ligne–neutre (défaut) | Valeurs telles que mesurées |
| Ligne–ligne, phase auxiliaire | Tension, puissance et énergie ×2 |

| Valeur | Correction en ligne–ligne |
|---|---|
| `Voltage`, `Power`, `PowerSigned` | ×2 |
| `EnergyPositive`, `EnergyNegative`, `EnergyNet` | ×2 |
| `Current`, `PowerFactor` | inchangé |

La correction est appliquée au dictionnaire décodé, dans le coordinateur. Les
compteurs du module ne sont pas modifiés ; les entités « (Set) » d'énergie
affichent et acceptent des valeurs corrigées et font la conversion à
l'écriture.

**À faire avant de changer ce réglage : remettre à zéro les compteurs
d'énergie du canal** (bouton *Reset Energy*). Sinon l'énergie double d'un coup
et les statistiques de Home Assistant enregistrent ce saut comme de la
consommation.

La correction suppose une charge purement 240 V. Une partie de charge qui
revient par le neutre (circuit de commande 120 V) est surestimée.

## 3. Identifiants d'entités

Les identifiants sont maintenant imposés par l'intégration, comme dans
`ha_midnite_classic`, pour ne plus dépendre de l'emplacement (pièce) de
l'appareil :

| Entité | Nom affiché | Identifiant |
|---|---|---|
| Canal nommé | `Thermopompe Voltage` | `sensor.thermopompe_voltage` |
| Canal sans nom | `<appareil> Voltage 1` | `sensor.<appareil>_voltage_1` |
| Commune aux deux canaux | `<appareil> Frequency` | `sensor.<appareil>_frequency` |

Les entités d'un canal nommé ne portent plus le nom de l'appareil : un module
mesure souvent deux circuits sans rapport (chauffe-eau et réfrigérateur), et
le nom du canal suffit à les identifier. Le nom de l'appareil ne sert plus
qu'aux entités communes et à la page de l'appareil.

Une entité déjà créée conserve l'identifiant enregistré dans Home Assistant.

## 4. Configuration

- **Nouvelle étape « Canaux »** à l'ajout d'un module, entre l'ID Modbus et la
  sélection des paramètres : nom et circuit de chaque canal.
- **Options (⚙️)** : les mêmes quatre champs, modifiables après coup.
- Nouvelles clés dans l'entrée de configuration : `channel_1_name`,
  `channel_2_name`, `channel_1_circuit`, `channel_2_circuit`. Une entrée créée
  en v1.0.0 fonctionne sans migration (aucun nom, ligne–neutre).

## 5. Écritures : corrections issues des essais sur le matériel

Constats sur un JSY-MK-194G réel :

- une écriture au registre 0004H (ID / vitesse) s'applique immédiatement et
  **n'est pas acquittée** par le module ;
- après une écriture, le module reste **muet un court moment**.

Corrections :

- **Relecture après écriture.** L'intégration relisait le module 0,5 s après
  l'écriture, sans réponse : toutes les entités passaient « indisponible »
  jusqu'à la lecture suivante. Elle attend maintenant 1 s, relit, et recommence
  jusqu'à cinq fois ; les entités conservent leur état entre-temps.
- **Écriture à 0004H.** La trame est envoyée une seule fois, avec un délai
  court, et l'absence d'acquittement n'est plus journalisée comme une erreur.
  Le résultat est vérifié en interrogeant le module avec ses nouveaux réglages.
- **Lecture périodique.** Une trame perdue ne rend plus les entités
  indisponibles : la question est posée une seconde fois.
- **Options.** L'ID et la vitesse de l'écran d'options indiquent les réglages
  que le module a déjà ; ils n'y écrivent rien. Des réglages auxquels le module
  ne répond pas sont maintenant refusés, avec un message qui renvoie aux
  entités « Modbus Device ID (Set) » et « Baud Rate (Set) ». Auparavant,
  l'intégration les acceptait et perdait le module.
- **Nouvel outil `tools/jsy_write_test.py`** : essais d'écriture en trames
  brutes sur un module réel, avec mesure du silence après écriture.
- **Simulateur** : reproduit l'absence d'acquittement à 0004H et le silence
  après écriture (`--deaf`).

## 6. Documentation

- Installation : section réécrite pour le **Marketplace** de Home Assistant
  2026.11 (Paramètres → Marketplace → *Add from link*), HACS conservé pour
  2026.10 et antérieures.
- Nouvelles sections « Channel names » et « Split-phase panels (120 / 240 V) ».

## 7. Mise à jour depuis la v1.0.0

1. Mettre à jour l'intégration, puis redémarrer Home Assistant.
2. Pour un canal sur un circuit 240 V : presser *Reset Energy* du canal, puis
   choisir « Ligne–ligne » dans les options.
3. Pour les noms de canaux, deux façons :
   - **par les options** : les noms affichés changent, les identifiants
     existants restent (historique et tableaux de bord préservés) ;
   - **en supprimant l'appareil puis en le rajoutant** : les identifiants
     suivent les nouveaux noms, l'historique repart de zéro. Le module conserve
     son ID Modbus, que l'intégration repropose à l'ajout.

Toujours à confirmer sur le matériel : le changement de vitesse par l'entité
« Baud Rate (Set) ».

## Fichiers modifiés

| Fichier | Changement |
|---|---|
| `const.py` | Clés de configuration des canaux, multiplicateurs, `channel_of()` |
| `coordinator.py` | Correction ligne–ligne, conversion à l'écriture des énergies, relecture après écriture |
| `config_flow.py` | Étape « Canaux », champs ajoutés aux options, validation des réglages de connexion |
| `jsy_reader.py`, `jsy_writer.py` | Sondes répétées, écriture à 0004H sans reprise |
| `tools/` | `jsy_write_test.py` (nouveau), simulateur |
| `entity.py` | Nom et identifiant des entités (`_set_name`) |
| `sensor.py`, `number.py`, `select.py`, `button.py` | Utilisent `_set_name` |
| `translations/en.json`, `fr.json` | Textes de l'étape et des options |
| `manifest.json` | Version 1.1.0 |
| `README.md` | Installation, canaux, phase auxiliaire |
