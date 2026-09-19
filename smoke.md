# Smoke: conversazione tra pane

1. Aggiorna dashboard e sandbox, poi abilita esplicitamente le skill desiderate:

   ```bash
   bash sandbox/update.sh
   bash lince-dashboard/update.sh
   bash lince-messages/install.sh --enable claude codex pi opencode
   ```

   Per Bob aggiungi `bob`. Puoi usare anche Pi e OpenCode nella coppia di prova. L'abilitazione installa `lince-converse` per quegli
   agenti e consente loro di inviare testo e Invio ai rispettivi pane.
   Non installa hook aggiuntivi; devono funzionare quelli di stato della dashboard.

2. Apri una nuova sessione Lince, crea due agenti e chiamali `mittente` e `revisore`.
   Porta entrambi al normale prompt libero, senza testo parzialmente scritto.
   Non ci sono gruppi da creare o intake da attivare.

3. Scrivi al mittente:

   > Usa la skill lince-converse per chiedere al revisore quanto fa 17+25. Dopo l'invio scrivi una breve frase e termina il turno, senza aspettare né controllare l'inbox.

4. Il revisore deve ricevere automaticamente il prompt, incluso mittente e ID di
   conversazione, e rispondere con `lince-msg send` mantenendo `--conversation`.
   Il mittente deve ricevere la risposta nel suo pane e riportare **42**.
   Se il mittente sta ancora lavorando, la risposta aspetta il suo stato idle.
   Nessun invio deve cambiare il focus o rivelare un pane nascosto.

5. Apri `Alt+d` → `m`: verifica domanda e risposta con lo stesso ID e stato
   `submitted`. Invio mostra il testo completo; Esc torna indietro.
   Nella seconda riga a sinistra della status line del mittente cerca `← … #ID`: indica l'ultimo messaggio
   ricevuto, non un incarico in corso.

6. Ripeti chiedendo una risposta multilinea e lasciando il mittente impegnato
   per circa 15 secondi. Verifica che la risposta resti `pending` fino alla fine
   del turno, poi venga sottomessa una sola volta.

7. Per disabilitare e rimuovere la skill gestita da Lince:

   ```bash
   bash lince-messages/install.sh --disable claude codex
   ```

   Apri pane nuovi: la comunicazione deve risultare non abilitata. Le skill
   modificate localmente sono conservate. Gli aggiornamenti non abilitano nuovi agenti.

`submitted` conferma testo + Invio, non lettura o completamento. Errori o stati
`uncertain` richiedono di guardare il pane prima di reinviare. Gli invii pendenti
scadono dopo cinque minuti e non vengono riprodotti dopo il riavvio del servizio.

## Gemini, Amp e Goose

Aggiorna Lince con `bash lince-dashboard/update.sh`, abilita le skill desiderate
con `bash lince-messages/install.sh --enable gemini amp goose` e apri pane nuovi.
Servono versioni degli agenti con le API di hook/plugin attuali: Gemini 0.1.7 e
Goose 1.20.1 non bastano. In Gemini verifica `/hooks`; non disabilitare gli hook
`lince-status`. Amp deve caricare il plugin di sistema `lince-status.js`; apri un
thread o invia un primo prompt per inizializzarne lo stato. In Goose deve essere
abilitato il plugin `lince-status`.

Ripeti domanda e risposta verso ognuno dei tre: mentre lavora il messaggio resta
pending, quando torna libero riceve testo e Invio senza spostare il focus.
In Gemini/Amp verifica anche una richiesta di permesso lasciata aperta: nessuna
iniezione finché l'agente non torna libero. Goose mantiene R durante il tool,
anche se aspetta un permesso. Controlla la correlazione nella risposta e il log
con `Alt+d` → `m`.

## Primo messaggio a Bob

Apri un nuovo pane Bob senza scrivergli nulla. Dopo login/eventuali dialoghi,
quando appare il prompt vuoto deve passare da `-` a `I`. Mandagli una domanda
da un altro agente: deve riceverla subito. Durante login o scelta del team deve
restare `-`; dopo il primo prompt gli stati continuano a seguire gli hook normali.

## Rinomina e status bar

Rinomina un destinatario con `Alt+r`, poi esegui `lince-msg peers` dal mittente:
il nome deve aggiornarsi e un invio al nuovo nome deve funzionare. Una risposta
con lo stesso ID conversazione deve continuare a funzionare. Nella status bar
verifica voce sulla prima riga a sinistra, ultimo mittente sulla seconda, e
`Alt+d details` / `Alt+h help` in coda ai tab, senza area destra riservata.
