## Verantwortlicher und Kontakt
Leevsten GmbH, Sustenweg 1, 8048 Zürich, Schweiz. Geschäftsführer: Hauke Rienhoff.
Für Datenschutzanliegen: [datenschutz@diga-tracker.de](mailto:datenschutz@diga-tracker.de).

## Website, Hosting und Protokolle
Der DiGA Tracker wird mit Streamlit auf Railway bereitgestellt. Beim Abruf werden
IP-Adresse und technische Verbindungsdaten an den Hostingdienst übermittelt, damit
Seiten ausgeliefert und Verbindungen abgesichert werden können. Betriebs- und
Fehlerprotokolle dienen der Fehleranalyse und Sicherheit. Die Anwendung protokolliert
auch technische Statusmeldungen des Newsletterformulars, ohne dort die eingegebene
E-Mail-Adresse auszugeben. Umfang und Aufbewahrungsdauer der Infrastrukturprotokolle
sind noch nicht abschließend dokumentiert; wir nennen deshalb keine feste Löschfrist.

## Newsletter und Double Opt In
Wenn du DiGA Tracker Alerts bestellst, verarbeitet die Anwendung deine E-Mail-Adresse
und übermittelt sie an Brevo. Erst der Bestätigungslink aktiviert das Abonnement.
Brevo verwaltet Anmeldung, Bestätigung, Versand und Abmeldung; die Anwendung führt
keine eigene Abonnentendatenbank. Die Adresse wird während der Verarbeitung auch
im serverseitigen Sitzungszustand des Formulars gehalten.

Du kannst deine Einwilligung jederzeit für die Zukunft über den Abmeldelink in den
Alerts widerrufen. Brevo verwaltet auch Sperrinformationen, die weitere Sendungen
verhindern. Ein Löschungsbegehren kannst du an die oben genannte Kontaktadresse richten.
Abonnements bestehen bis zur Abmeldung. Erforderliche Einwilligungsnachweise und
Sperrinformationen können darüber hinaus aufbewahrt werden; konkrete Fristen dafür
sind noch zu bestätigen.

## Brevo und E-Mail-Auswertung
Brevo verarbeitet Empfänger- und Zustelldaten für den Versand. In den verwendeten
Kampagnen kommen personalisierte Weiterleitungslinks zum Einsatz. Brevo unterstützt
auch Öffnungsmessung über ein Zählpixel; die Standardkonfiguration sieht Öffnungs-
und Klickmessung vor. Dabei können Zeitpunkt, IP-Adresse und technische Angaben
zum E-Mail-Programm verarbeitet werden. Die genaue kontoabhängige Konfiguration,
Aufbewahrung und Einwilligung für diese Auswertung sind noch zu klären. Eine
Newsletteranmeldung wird hier nicht als pauschale Zustimmung zu jeder Auswertung dargestellt.

## Technische Speicherung und externe Inhalte
Der Anwendungscode bindet keine Werbenetzwerke, Analyse-Skripte, Drittanbieter-Embeds
oder extern geladenen Webfonts ein. Die optionale Streamlit-Nutzungsstatistik ist
in der Anwendungskonfiguration deaktiviert. Streamlit nutzt technischen Sitzungszustand
und kann einen Schutz-Cookie gegen gefälschte Anfragen setzen. Es gibt keinen eigenen
Code zur Speicherung von Trackingkennungen in localStorage oder sessionStorage.
Dies ist keine Aussage über Cookies auf verlinkten fremden Websites oder in E-Mails.

Cloudflare R2 dient serverseitig als Archiv für Snapshots des öffentlichen BfArM-
Verzeichnisses, nicht als Abonnentenspeicher. Der Browser lädt daraus keine eingebetteten
Inhalte. Quellmaterial kann veröffentlichte Kontaktangaben enthalten; Rechte daran
bleiben unberührt. Eine zusätzliche Cloudflare-Proxy- oder Analysefunktion für
Websitebesuche ist aus dem Anwendungscode nicht belegt.

## Rechtsrahmen, Empfänger und Ausland
Für die Schweizer Betreiberin gilt das Schweizer Datenschutzrecht. Soweit die DSGVO
anwendbar ist, sind auch deren Anforderungen zu beachten. Der Newsletterversand
beruht auf deiner Einwilligung (soweit anwendbar Art. 6 Abs. 1 lit. a DSGVO).
Die konkrete DSGVO-Einordnung des technischen Betriebs und der E-Mail-Auswertung
sowie eine mögliche Pflicht zu einer EU-Vertretung sind noch zu prüfen.

Railway, Brevo und Cloudflare verarbeiten Daten im Rahmen der beschriebenen Leistungen.
Eine europäische Hostingregion schließt Zugriffe aus anderen Ländern nicht aus.
Railway und Brevo sehen in ihren veröffentlichten Datenschutzvereinbarungen
Regelungen zu internationalen Übermittlungen, insbesondere Standardvertragsklauseln,
vor. Die tatsächlich vereinbarten Verarbeitungsorte, Unterauftragnehmer und Garantien
einschließlich der R2-Konfiguration sind noch vollständig zu bestätigen.

## Deine Rechte
Je nach anwendbarem Recht kannst du Auskunft, Berichtigung und Löschung verlangen;
soweit vorgesehen auch Einschränkung, Datenübertragbarkeit und Widerspruch.
Einwilligungen kannst du für die Zukunft widerrufen. Kontaktiere uns dafür per E-Mail
oder an der oben genannten Anschrift. Du kannst dich an den
[Eidgenössischen Datenschutz- und Öffentlichkeitsbeauftragten](https://www.edoeb.admin.ch/de/kontakt)
wenden; soweit die DSGVO gilt, besteht ein Beschwerderecht bei einer zuständigen
Datenschutzaufsichtsbehörde, insbesondere am gewöhnlichen Aufenthaltsort.

Stand: 24. September 2026.
