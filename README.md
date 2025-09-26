Lake Side Mania – Onderhoudssysteem  
Projectleden
- Bismark Owusu-Ansah  
- Joshua Arends
- Sufiyan Mistry
- Lars brukman
- Dimitri van der Laan

Doel van het project  
Het doel van dit project is het ontwikkelen van een onderhoudssysteem voor attractiepark **Lake Side Mania**.  
De focus ligt op **preventief onderhoud met sensordata**. Door gegevens van sensoren (trillingen, temperatuur, gebruiksuren) te analyseren, kunnen onderhoudstaken tijdig ingepland worden. Dit verhoogt de veiligheid, minimaliseert stilstand en optimaliseert de inzet van personeel.  

---

 Werkwijze proces (OTAP-methodiek)  
Wij hanteren de **OTAP-methodiek** voor versiebeheer en kwaliteitsborging:  

- Ontwikkel (develop): alle nieuwe functionaliteit wordt hier gebouwd.  
- Test:code wordt getest door het team voordat het naar main gaat.  
- Acceptatie: het team controleert of alles voldoet aan de requirements.  
- Productie (main):stabiele en goedgekeurde versie van de code.  

Afspraken: 
- Alle teamleden werken standaard in de *develop*-branch.  
- Nieuwe features worden ontwikkeld in aparte *feature branches
- Elke merge naar develop gaat via een **merge request** en wordt gereviewd door minimaal één ander teamlid.  
- Alleen een stabiele versie mag via een merge naar *main*.  
- Issues en taken worden bijgehouden in GitLab.  

---

Codeconventies  
Wij hanteren de volgende afspraken voor codekwaliteit:  

- Taal: alle variabelen, klassen en functies worden in het Nederlands benoemd.  
- Bestandsnamen: `snake_case.py` (kleine letters met underscores).  
- Klassen: beginnen met een hoofdletter (`Sensor`, `Onderhoudstaak`).  
- Functies & variabelen: in `snake_case`.  
- Documentatie:elke klasse en functie krijgt een korte docstring. 
- **Database:** koppeling met MySQL via een aparte `database.py`.
 Licentie

Wij kiezen voor de MIT-licentie omdat deze eenvoudig, permissief en veelgebruikt is in softwareprojecten.
Deze licentie geeft anderen de vrijheid om de code te gebruiken, aan te passen en te verspreiden, zolang de originele copyrightvermelding aanwezig blijft.

Domeinmodel

Het domeinmodel laat de belangrijkste concepten en relaties zien:

Attractie → bevat meerdere Sensoren

Sensor → levert data voor Onderhoudstaak

Onderhoudstaak → wordt ingepland in een Rapportage

Medewerker → voert de onderhoudstaken uit

Projectstructuur

De projectbestanden worden als volgt gestructureerd:

/src
   /models          # Klassen zoals Sensor, Onderhoudstaak, Attractie, Rapportage
   /controllers     # Logica en koppelingen
   /data            # JSON-bestanden en seed data
   main.py          # Startpunt van de applicatie
/docs
   domeinmodel.png
README.md

Gezamenlijke klassen

Sensor → type, locatie, status, metingen

Attractie → naam, type, gekoppelde sensoren

Onderhoudstaak → beschrijving, urgentie, status, datum

Rapportage → overzicht van geplande/uitgevoerde taken

Medewerker → naam, functie, toegewezen taken

Authenticiteitsverklaring (niveau 2)

Dit document is opgesteld door het projectteam. Voor planning, ideeontwikkeling en onderzoek is AI gebruikt.
De uiteindelijke keuzes, inhoud en uitwerking zijn door het team zelf ontwikkeld en verfijnd


hier is onze domein model
<img width="842" height="678" alt="image" src="https://github.com/user-attachments/assets/2723d491-6c1e-46a1-aea1-518931d517cc" />




