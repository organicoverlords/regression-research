# Keskustelumuistio: Ponytail, swarm ja Nexus

Päivä: 2026-09-13
Lähde: tämä ChatGPT-keskustelu; ei koko Vault-historian rekonstruktio.

## Mitä ideoita tässä keskustelussa palloteltiin

### Ponytail / YAGNI
- Ponytail-ajatus ei tarkoita "tee vähemmän ajattelua" tai "tee mahdollisimman lyhyt vastaus".
- Ensin ymmärretään tavoite ja oikea end-to-end flow, sitten tehdään pienin oikeasti riittävä muutos.
- Uutta mekanismia/orchestratoria/kerrosta ei lisätä vain siksi, että se kuulostaa siistiltä. Ensin katsotaan voiko nykyistä omistajaa, stdlibia, alustaa tai olemassa olevaa mekanismia käyttää.
- Bugissa korjataan juurisyy, ei viereistä oiretta.

### Manual swarm
- Oikea malli: **same goal -> sibling output -> next useful contribution**.
- Parallelismi on hyvä; duplikaattityö on huono.
- Tarkoitus ei ole vähentää workereita vaan vähentää sitä, että usea worker ratkaisee saman acceptance-kohdan toisistaan tietämättä.
- Workerien pitäisi täydentää toisiaan saman tavoitteen ympärillä, ei muodostaa jäykkiä rooleja tai yhtä workeria per tavoite.
- Uutta keskitettyä orchestratoria ei pidä rakentaa ilman näyttöä, että nykyinen coordination/ownership-malli ei riitä.

### Nexus suhteessa stackiin/swarmiin
- Tässä keskustelussa Nexus hahmotettiin ennen kaikkea **cockpitiksi / näkyväksi ohjauspinnaksi**, ei uudeksi truth storeksi, scheduleriksi tai orchestration-moottoriksi.
- Atlas/find, Git/GitHub, MCP/runtime, Vault ja worker-reportit säilyttävät omat roolinsa; Nexus näyttäisi ja yhdistäisi niitä, ei korvaisi niitä.
- Keskustelun aikana todettiin myös, että Nexus ei ollut sillä hetkellä varsinainen live production/operator surface.

## Mitä tässä keskustelussa oikeasti muutettiin

Seuraavat shared-agent muutokset tehtiin ja landattiin tämän keskustelun aikana:

1. **#377 / PR #378**: ELI5 ei tarkoita automaattista analogiaa. Shared contract nousi v77:ään.
2. **#379 / PR #380**: ELI5 täsmennettiin tarkoittamaan tiivistä ydinasiaa normaaleilla sanoilla, ei infantilisoivaa yksinkertaistusta tai bullet-seinää. Shared contract nousi v78:aan.
3. **#384 / PR #385**: yleinen direct-reply gate: taustalla saa tutkia syvästi, mutta käyttäjälle palautetaan vain ydintulos ja välttämätön selitys. Muuttuvat faktat pitää ankkuroida current/live evidenssiin. Shared contract nousi v79:ään.

Lisäksi tehtiin durable memory -merkintöjä näistä response-quality korjauksista.

## Mitä EI tehty tässä keskustelussa

- **Ponytail/YAGNI-periaatteesta ei tehty tässä keskustelussa uutta shared-swarm implementaatiota, PR:ää tai Nexus-muutosta.** Sitä käytettiin ajattelumallina ja olemassa olevan swarm-mallin arviointiin.
- **Manual swarmille ei rakennettu uutta orchestratoria, roolijakoa tai uutta queue-järjestelmää.** Päinvastoin keskustelun suunta oli välttää sellaista ilman tarvetta.
- **Nexusta ei tässä keskustelussa muutettu yhdistämään swarmia tai shared directionia.** Nexuksen tilaa tarkistettiin ja sen roolia kuvattiin, mutta Nexus-repoon ei tämän keskustelun perusteella tehty muutosta.
- Käyttäjän ennen tätä keskustelua mainitsema **#375 / PR #376 / commit 2ec39f40...** oli jo tehty shared-swarm korjaus, jonka tässä keskustelussa tarkistin; en ollut sen alkuperäinen toteuttaja tässä chatissa.

## Keskustelun tärkein yhteinen suunta

Pidä swarm mahdollisimman yksinkertaisena mutta evidence-grounded:

**yksi tavoite -> nykyinen yhteinen tila -> seuraava puuttuva hyödyllinen kontribuutio.**

Nexus voi toimia tämän näkyvänä käyttöliittymänä, mutta ei uutena rinnakkaisena totuutena tai orchestration-kerroksena. Ponytail/YAGNI tarkoittaa, että tällainen yhdistäminen tehdään vain olemassa olevien ownerien päälle ja vain siinä määrin kuin oikea käyttötarve vaatii.

