 
Lite scope change:

Appen är fortfarande ett ticketsystem skrivet i python med bra kommenterad kod per python standard med caddy som frontend och allt i non-root containers om möjligt (helst inte bitnami).


Caddy ska kunna använda acme/letsencrypt, men sidan ska fungera utan HTTPS till att börja med (den kan komma att köras utan internet på scoutlägret)

Användare: två nivåer. Admin ska kunna göra allt och skapa andra inloggningar och välja mellan att kunna skapa och ändra tickets, eller bara läsrättigheter.

ticketstatus: Ny, påbörjad, avslutad, pausad, avvisad.

Bara admin ska kunna se tickets per default, men det ska finnas en checkbox på ticketen där man kan välja "publik och kan utomstående besöka ticketen och se status och kategori samt skapad och eventuellt avslutad.

Formuläret där man fyller i ticketen ska ha fälten

* Skapad: tid och datum
* Prioritet: 1-3 (P1 – Akut — säkerhet, skada, något är trasigt just nu, P2 – Viktig — påverkar aktiviteter men ingen fara, P3 – Låg — önskemål, nice-to-have, kan vänta)
* Kategori: <checkbox> med topp X områden som är relevanta. Om en kategori inte finns kan man skriva in det själv och då ska det sparas ett möjligt framtida val och autokompletteras när man skriver fritext nästa gång. Kategorierna ska sparas i databasen som lowercase så det inte blir dubletter (mellanslag ska strippas om det är i början/slutet). Visa bara en rimlig mängd kategorier, kanske topp fem/tio beroende på hur många som får plats på sidan. De ska visas i bokstavsordning med stor bokstav initialt.
* Fritextfält där man skriver i själva händelsen
* Återkoppling: fritextrad
* Titel: tom, används för dashboard
* Checkbox "publik" enligt tidigare instruktion
* Status: Ny (men går att ändra till valfri ticketstatus)
* Avslutad tid/datum: fylls i automatiskt när man väljer avslutad eller avvisad. Ska gå att fylla direkt om man lägger in tickets i efterhand
* Sparaknapp

Efter man sparas ska systemet visa ticketen och en qr-kod med själva länken till ticketen så den enkelt kan skannas av någon.

Tid/datum för skapad/avslutad ska gå att ändra via dropdown.

Alla ändringar på en ticket ska loggas i databasen och man ska kunna "fälla ut" en historik nederst och se alla ändringar

Hela systemet ska vara bakom login med användarnamn och lösenord

Systemet ska finnas tillgängligt på åtminstonde svenska och engelska, lättast om alla kod/scheman etc är på engelska, sjävla UI't ska vara inställd på browserns språk per default.

Designen ska vara modern för en scoutkår

Det ska finnas en "dashboard" sida för admin för att kunna se ticket statusar, och all viktig data som kan vara relevant för att se och få en överblick över allt tickets, kölängd, prioritet osv.

Det ska oxå finnas en tv-dashboard sida som visar tickets i kolumner med ny, påbörjad, avslutad och i prioritetsordning och ska kunna vissas på en stor tvskärm för att alla ska kunna se vad som hanteras just nu, visa bara ticket id, status och tid/datum, prioritet, en utomstående ska inte kunna se skärmen och veta vad det rör sig om, och den ska inte läcka information. Titel kan dock visas om den är ifylld.
