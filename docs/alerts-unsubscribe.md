# Sichtbare Abmeldung in öffentlichen Alerts

Prüfung am 2026-10-06, Basis main `b0ddfe50f88c6f69896b948e8dba78bbd5c426d3`,
Branch `codex/alerts-unsubscribe`. Kein Versand, keine Kontaktänderung,
kein Merge oder Deployment. Monitoringdaten und Trackingeinstellungen unverändert.

## Befund und Zuordnungsgrenze

- Belegt: `notifications.notify_changes` rendert ohne `unsubscribe=True`.
  Bei konfiguriertem Impressum enthält dieser Footer nur Impressum und
  Datenschutz. Versand über `/v3/smtp/email`, Empfänger ausschließlich aus
  `DIGA_MONITOR_EMAIL_TO`; ohne diese Einstellung kein Versand und kein
  Rückgriff auf die öffentliche Liste. Diese interne Mail kann die beschriebene
  Darstellung erklären. Sie erhält keine wirkungslose Newsletter-Abmeldung.
- Belegt: `subscriber_alerts.build_alert_html_body` rendert stets mit
  `unsubscribe=True`. Bereits auf main war ein Link „Abmelden“ mit dem nativen
  `{{ unsubscribe }}` vorhanden. Er erbte die kleine 13px-Footerschrift.
  `string.Template` verarbeitet Dollar-Platzhalter und lässt Brevos Token intakt.
  Die Campaign API erhält das vollständige HTML unmittelbar als `htmlContent`.
  Es wird kein entferntes Alert-Template per ID verwendet oder aktualisiert.
- Der interne Versand ist eine plausible Erklärung, keine bewiesene Zuordnung:
  Original-EML, vollständiger Screenshot und Versandprotokoll liegen dieser
  Prüfung nicht vor. Ein abgeschnittener Footer oder ein anderer Deploymentstand
  sind ebenfalls nicht ausgeschlossen. Betreff intern: „DiGA Tracker: …
  Änderung(en) erkannt“; öffentlich: „Es gibt Updates im DiGA Verzeichnis“.
  Zur sicheren Zuordnung Message-ID/Zeitpunkt mit Brevo-Logs abgleichen und den
  vollständigen MIME-Inhalt prüfen; keine personenbezogenen Header veröffentlichen.

## Änderung und erhaltene Versandgrenzen

Öffentliche HTML-Mails enthalten nun „Alerts abbestellen“ in einer eigenen Zeile,
16px, dunkel, fett und unterstrichen, mit 48px hoher Klickfläche. Die lokale
Textvorschau verwendet denselben Wortlaut und nativen Token. Keine eigene URL,
kein Kontaktparameter und kein generischer Abmeldelink werden erzeugt.

Campaign-Payload unverändert: `type=classic`, `htmlContent`, ausschließlich
`recipients.listIds=[BREVO_NEWSLETTER_LIST_ID]`. Kein Transactional-Fallback,
keine Kontaktmutation und kein Überschreiben von Headern/Trackingoptionen.
Brevo bleibt für die persönliche Auflösung und den Marketing-Sperrstatus
zuständig. Gesperrte Kontakte werden auch bei fortbestehender Listenmitgliedschaft
von Kampagnen ausgeschlossen. `subscribers.py`, Einwilligung und DOI bleiben
unverändert. Explizite Wiederanmeldung entfernt einen gesperrten Kontakt zuerst
aus der bestätigten Liste und erfordert erneut DOI, bevor er wieder zur
Alert-Zielgruppe gehört. Ein Marketing-Opt-out ist nicht automatisch ein
Transactional-Opt-out: öffentliche Abonnenten gehören nicht in die interne
Empfängerkonfiguration. Deren aktuelle produktive Werte wurden nicht eingesehen.

## Offizielle Brevo-Verifikation

Am Prüftag gelesen:

- [Nativer HTML-Platzhalter](https://help.brevo.com/hc/en-us/articles/209553645-Insert-a-custom-unsubscribe-link-in-your-emails):
  `<a href="{{ unsubscribe }}">…</a>` führt zur Brevo-Abmeldeseite.
- [Campaign API](https://developers.brevo.com/reference/create-email-campaign):
  HTML wird als `htmlContent` übergeben; kein `textContent`-Eingabefeld.
- [Textversion](https://help.brevo.com/hc/en-us/articles/360000486460-How-do-I-create-edit-the-plain-text-version-of-HTML-emails):
  Brevo erzeugt die Textalternative aus HTML. `build_alert_text_body` ist nur
  eine lokale Vorschau, kein Beweis für den tatsächlich gelieferten MIME-Teil.
- [List-Unsubscribe](https://help.brevo.com/hc/en-us/articles/19100260472850-FAQs-About-list-unsubscribe-and-list-help-headers-in-emails):
  Brevo fügt den Header automatisch ein. Er ersetzt den sichtbaren Footerlink
  nicht. Tatsächlicher Header und One-Click-Verhalten erfordern eine empfangene Mail.
- [Sperrstatus](https://help.brevo.com/hc/en-us/articles/209458705-What-is-a-blacklisted-contact-):
  Marketing-gesperrte Kontakte sind von weiteren Kampagnen ausgeschlossen.

## Prüfergebnisse und Selbstprüfung

- 69 gezielte Tests bestanden: `test_notification_email.py` (16),
  `test_subscriber*.py` (32), `test_notifications.py` (21).
  Neue Prüfungen untersuchen den tatsächlichen JSON-Request: genau ein sichtbarer
  Link mit exaktem Token/Text, Campaign-Endpunkte, bestätigte Liste, keine interne
  Adresse, keine zusätzlichen Versandoptionen. Interner Dispatch und fehlende
  interne Konfiguration sind separat getestet. DOI/Sperrstatus-Tests bestehen.
- Vier synthetische HTML/Text-Fixtures mit
  `python -m scripts.preview_notification_email` erzeugt. Lokales Edge/Playwright
  bei 1000/390/320px: alle zwölf Kombinationen ohne horizontalen Überlauf,
  sichtbarer Link mit unverändertem href und 48px Höhe. Desktop- und
  320px-Screenshots einschließlich langer DiGA-Namen visuell geprüft.
  Vorschauen liegen lokal unter `work/email-previews/`; keine Links angeklickt,
  HTTP-Anfragen beim Layouttest blockiert. Kein echter Mailclient-Test.
- `git diff --check` bestanden. Umfang bewusst auf Renderer, Regressionstests
  und Dokumentation begrenzt; vollständige Projektsuite nicht erneut ausgeführt.
- Claude Review: null Runden, `ANTHROPIC_API_KEY` lokal nicht verfügbar;
  kein persönlicher OAuth-Fallback. Explizite Codex-Selbstprüfung: nativen Token
  bis zum serialisierten Request verfolgt, internen Empfängerpfad und fehlende
  Konfiguration geprüft, bestätigte Liste/DOI/Sperrstatus unverändert,
  keine PII-Abmelde-URL, keine Versand-/Tracking-/Datenänderungen.
  Keine substanziellen offenen Codebefunde; Provider-Nachweise unten offen.
- Auch `BREVO_API_KEY` ist lokal nicht verfügbar. Deshalb kein authentifizierter
  Produktionscheck; keine Aussage über den aktuellen Brevo-Kontostand oder
  produktive Konfiguration. Kein API-Workaround eingeführt.

## Späterer Testplan – gesonderte Autorisierung erforderlich

1. Eine neue, eigens autorisierte Testadresse und eine isolierte Brevo-Testliste
   festlegen; sie darf keine bestehenden Kontakte enthalten. Autorisierung muss
   DOI, eine reguläre Testkampagne, Abmeldung dieser Adresse und einen zweiten
   Versandversuch zur Ausschlussprüfung umfassen. Keine produktiven Variablen
   oder Trackingoptionen ändern. Testadresse nicht intern konfigurieren.
2. Vorab mit dem für diesen isolierten Lauf vorgesehenen Schlüssel den kleinsten
   authentifizierten Read-only-Check durchführen (z. B. `GET /v3/account`);
   Status, Sender und Testlisten-ID prüfen, keine Secrets/PII protokollieren.
3. Mit expliziter Einwilligung über den bestehenden DOI-Pfad anmelden, dabei nur
   im isolierten Testprozess `BREVO_NEWSLETTER_LIST_ID` auf die Testliste setzen.
   Vor Bestätigung muss die Adresse außerhalb dieser Liste bleiben; danach
   bestätigte Mitgliedschaft und nicht gesperrten Status prüfen.
4. Mit dem geprüften Code eine reguläre Campaign-API-Kampagne ausschließlich an
   diese Liste senden. Synthetisches Ereignis nur im Speicher; Protokollziel in
   einem separaten temporären Testverzeichnis. Kein Produktionsscan, keine
   persistierte Simulation und keine Brevo-„Send test“-Funktion als Ersatz:
   Letztere beweist weder persönliche Auflösung noch normale Suppression.
   Vor `sendNow` die alleinige Testzielgruppe prüfen, keine automatischen Retries.
5. Empfang und vollständiges EML sichern, vertraulich behandeln. Auf Desktop
   und Mobilgerät „Alerts abbestellen“ vollständig sichtbar und bedienbar prüfen.
   HTML-href muss eine persönliche Brevo-HTTPS-URL statt des Tokens enthalten;
   keine ungeschützte E-Mail-Adresse im Link. Text/plain muss ebenfalls einen
   funktionierenden persönlichen Abmeldelink enthalten. `List-Unsubscribe` und
   `List-Unsubscribe-Post: List-Unsubscribe=One-Click` im Rohheader prüfen und
   Abweichungen festhalten. Diese URLs nicht in PR/Logs kopieren.
6. Ausschließlich den Footerlink dieser Testmail öffnen und die Abmeldung
   abschließen. Anschließend Brevos Marketing-Sperrstatus (`emailBlacklisted`)
   read-only prüfen. Bestehende Kontakte bleiben unberührt. Ein Header-POST
   erfordert einen separat autorisierten Testfall, wenn er zusätzlich zur
   Footer-Abmeldung end-to-end geprüft werden soll.
7. Ohne erneute Anmeldung, Entsperrung oder Kontaktänderung eine zweite reguläre
   Kampagne an dieselbe isolierte Liste versuchen. Erwartung: keine Zustellung
   an den gesperrten Testkontakt; Brevo-Report/Ausschlussstatus oder Ablehnung
   wegen leerer berechtigter Zielgruppe dokumentieren. Nichtempfang allein ist
   kein Beweis. Keine zweite Adresse ohne zusätzliche Autorisierung hinzufügen.
8. Ergebnis anhand Kampagnen-IDs, Zeitpunkten, redigierten Headern und
   Sperr-/Ausschlussnachweis dokumentieren. Bei unverarbeitetem Token, fehlendem
   Textlink/Header oder weiterer Zustellung stoppen und Ursache prüfen.
   Testkontakt gesperrt belassen; kein automatisches Merge/Deployment.
