# ha_jsy — notes pour la v1.1.1

Corrections des écritures de registres, à la suite des premiers essais sur un
JSY-MK-194G réel.

Base : v1.1.0.

`jsy_modbusdecoder.py` n'est pas modifié. Les corrections ont été validées dans
Home Assistant 2026.2.3 contre le simulateur, qui reproduit maintenant les deux
comportements observés sur le module. Sur le matériel, le changement d'ID
Modbus, le changement de vitesse et l'écriture des compteurs d'énergie sont
validés, les deux premiers en trames brutes avec `tools/jsy_write_test.py`.

---

## 1. Constats sur le matériel

- Une écriture au registre 0004H (ID / vitesse) en un seul mot est acceptée
  et s'applique immédiatement. Le module répond avec ses nouveaux réglages
  environ 0,2 s plus tard.
- **Changement d'ID** : le module acquitte avec son **nouvel** ID
  (`tx 0A 10 00 04 …` → `rx 63 10 00 04 00 01 …`). Un client Modbus rejette
  cette réponse, venue d'un autre ID que celui interrogé : pymodbus rapporte
  « No response received ».
- **Changement de vitesse** : le module acquitte à l'ancienne vitesse, puis
  bascule.
- L'écriture d'un compteur d'énergie est acquittée, pour une valeur nulle
  comme non nulle.
- **Un compteur écrit est conservé au pas de 0,01 kWh** : le module tronque le
  reste (250471 écrit → 250400 relu), alors qu'il compte et se relit ensuite
  au pas de 0,001 kWh.
- Le module **ignore une requête qui suit une écriture de trop près**. En
  trames brutes, il répond de nouveau en moins de 0,2 s.

## 2. Corrections

### Entités « indisponible » après une écriture

L'intégration relisait le module 0,5 s après l'écriture, sans obtenir de
réponse : toutes les entités passaient « indisponible » jusqu'à la lecture
périodique suivante. Chaque écriture est maintenant suivie d'une pause de
0,3 s, qui espace aussi deux écritures consécutives (remise à zéro d'un
canal), puis le module est relu, avec jusqu'à cinq tentatives. Les entités
conservent leur état entre-temps.

### Pas des compteurs d'énergie

Les entités « Energy … (Set) » ont maintenant un pas de 0,01 kWh (0,02 kWh
pour un canal en ligne–ligne), au lieu de 0,0001 kWh : c'est ce que le module
conserve réellement. La valeur est tronquée de la même façon avant l'écriture,
de sorte que le journal montre ce qui est enregistré.

### Erreur trompeuse au changement d'ID

À l'ajout d'un module, le journal affichait
`write at 0x0004 failed: ModbusIOException ... No response received` alors que
le changement d'ID avait réussi. La trame est maintenant envoyée une seule
fois, avec un délai court, et ce « No response » attendu n'est plus journalisé
comme une erreur. Le résultat est vérifié, comme avant, en interrogeant le
module avec ses nouveaux réglages.

### Options : réglages de connexion vérifiés

L'ID Modbus et la vitesse de l'écran d'options (⚙️) indiquent les réglages que
le module **a déjà** ; ils n'y écrivent rien. En v1.1.0, y entrer un nouvel ID
était accepté tel quel, et l'intégration perdait le module. Des réglages
auxquels le module ne répond pas sont maintenant refusés, avec un message qui
renvoie aux entités « Modbus Device ID (Set) » et « Baud Rate (Set) », qui
sont la façon de changer les réglages du module lui-même. Les libellés et la
description de l'écran ont été précisés.

### Lecture périodique

Une trame perdue ne rend plus les entités indisponibles : la question est
posée une seconde fois avant de déclarer l'échec.

## 3. Outils

- **Nouveau : `tools/jsy_write_test.py`.** Essais d'écriture en trames brutes
  sur un module réel (pyserial seulement) : compteur d'énergie, ID, vitesse.
  Affiche chaque trame envoyée et reçue, mesure le silence après écriture,
  remet le module dans son état initial. L'option `--scan` retrouve un module
  dont l'ID ou la vitesse ne sont plus connus.
- **`tools/jsy_simulator.py`** reproduit l'acquittement avec le nouvel ID à
  0004H, la troncature des compteurs écrits à 0,01 kWh et le silence qui suit
  une écriture (option `--deaf`, 0,15 s par défaut).

## 4. Mise à jour depuis la v1.1.0

Mettre à jour l'intégration, puis redémarrer Home Assistant. Aucun changement
de configuration, aucune entité renommée.

## Fichiers modifiés

| Fichier | Changement |
|---|---|
| `coordinator.py` | Relecture après écriture, sondes répétées au changement d'ID / vitesse |
| `jsy_reader.py` | Sonde répétable (`attempts`), deux tentatives à la lecture périodique |
| `jsy_writer.py` | Pause après écriture, énergie tronquée à 0,01 kWh, écriture à 0004H sans reprise |
| `number.py`, `const.py` | Pas de 0,01 kWh des compteurs d'énergie |
| `config_flow.py` | Options : vérification des réglages de connexion |
| `translations/en.json`, `fr.json` | Textes de l'écran d'options |
| `manifest.json` | Version 1.1.1 |
| `tools/jsy_write_test.py` | Nouveau |
| `tools/jsy_simulator.py`, `tools/README.md` | Comportements observés, documentation |
| `README.md` | État des fonctions d'écriture, options |
