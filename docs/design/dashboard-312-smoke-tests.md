# Epic #312 — smoke test manuali

Eseguire dopo aver installato il branch della PR. Servono Zellij >= 0.45.1,
un terminale inizialmente di almeno 100×32 e due tipi di agente già configurati.
Non eseguire questi test dalla directory che contiene uno stato `.lince-dashboard`
da ripristinare: usare una directory temporanea per non riaprire gli agenti abituali.

## Preparazione

Dalla checkout della PR:

```bash
bash lince-dashboard/update.sh
zellij --version
```

Aprire un nuovo terminale fuori da una sessione Zellij. Il comando diretto
`lince-dashboard-launch` non richiede di ricaricare gli alias della shell.

```bash
SMOKE_DIR="$(mktemp -d /tmp/lince-312-smoke.XXXXXX)"
cd "$SMOKE_DIR"
lince-dashboard-launch --preset minimal
```

L'aggiornamento mantiene `classic` per le configurazioni precedenti prive di
preset: per provare il nuovo aspetto usare esplicitamente `--preset minimal`.
`update.sh` preserva i valori della configurazione e crea i consueti backup.

## Minimal e sidebar (#292, #293, #313)

- Nessuna tab bar in alto, nessuna striscia di scorciatoie Zellij in basso,
  nessun frame. Una sola riga LINCE in basso, più il footer locale della lista.
- Creare due agenti con `N`, nello stesso progetto: il progetto compare una
  sola volta come intestazione in grassetto, colorata e con una linea di separazione.
  Verificare che a sinistra compaia il numero globale dell’agente, coerente con `Alt+1/2`,
  poi il tipo (`CLA`, `CDX`, ecc.) e lo stato. Il nome non deve comparire nella sidebar:
  deve restare nei dettagli `i` e nella barra in basso.
- `j/k` cambia selezione; Enter apre l'agente. `Alt+1/2` cambia agente anche
  mentre il cursore è nel terminale; `Alt+PageUp/PageDown` scorre gli agenti.
- `Alt+d` apre sempre la lista **espansa** in un popup bordato, anche quando la
  sidebar è visibile. `d` non deve più cambiare la densità. Esc chiude il popup.
- Dal terminale di un agente, `Alt+i` apre direttamente le sue informazioni e
  `Alt+h` l’help, entrambi bordati. PageUp/PageDown scorrono informazioni lunghe.
- `Alt+s` nasconde sidebar e shell/voce: il viewport occupa tutta la larghezza,
  mantenendo la status bar. Ripetere per ripristinare le colonne alla larghezza
  configurata. Ripetere almeno sei toggle consecutivi con tre agenti aperti:
  il controller deve tornare in alto a sinistra, sopra shell/voce, ogni volta.
  L’agente aperto deve restare visibile e mantenere il focus in entrambi i sensi
  del toggle, ridimensionandosi senza doverlo riaprire con `Alt+1/2`.
  Ripetere subito dopo aver scelto `Alt+2` e `Alt+3`: anche il primo toggle
  deve mantenere quell’agente, senza mostrare gli altri pane nascosti.
  Con sidebar nascosta, `Alt+1/2` deve aprire ciascun agente a tutta larghezza
  e altezza disponibile, escludendo solo la status line. Riprovare `Alt+d/i/h`
  con sidebar sia visibile sia nascosta.
- `Alt+n` apre il wizard da qualunque pane, senza creare un pane Zellij.
  Dal primo passo di selezione, premere `n`: deve chiedere solo il nome e usare
  i default configurati. Digitare una `n` nel campo nome e nel percorso: deve
  restare testo. Annullare con Esc; completare poi una creazione normale.
- Provare le scorciatoie anche in modalità locked (`Ctrl+l` per entrarvi/uscirne).
- Creare un agente con sandbox diverso da `normal`, oppure unsandboxed:
  verificare il marcatore `!`, i dettagli su `i` e il livello della voce attiva
  nella riga in basso. `NOSB` deve identificare quello unsandboxed.
- Ridimensionare il terminale e i pane: l'agente deve restare nel viewport,
  senza coprire la sidebar o la riga in basso.
- Dal terminale di un agente, `Alt+q` deve salvare e chiudere la sessione. Riavviare
  dalla stessa directory e verificare il ripristino. Provare anche in modalità locked.
- Modificare la configurazione degli agenti, poi `Alt+d` e `q` minuscola: deve
  uscire senza aggiornare il salvataggio precedente. Riavviare per verificare
  che si ripristini ancora lo stato salvato prima della modifica.
- Usare una nuova directory temporanea per ogni variante successiva se non
  si desidera il restore.

Provare anche una larghezza diversa:

```bash
lince-dashboard-launch --preset minimal --sidebar-width 25
```

## Status line (#295)

```bash
lince-dashboard-launch --preset statusline
```

- Il terminale occupa la vista, con due righe in basso e sidebar inizialmente
  nascosta. `Alt+s` la mostra: è la stessa vista di minimal.
- `Alt+d` apre la lista espansa e bordata; `n`, `N`, `i`, `r`, `s/S` e `?` sono accessibili.
  La barra resta visibile durante i dialoghi. Esc chiude prima il dialogo,
  poi il controller; selezionare un agente riporta al suo terminale.
- Creare un agente bash e un agente con hook. Bash resta `-` quando non è
  disponibile uno stato preciso; non contribuisce al conteggio delle attese.
- Far lavorare un agente con hook: deve passare a `R`, poi `I` quando chiede
  input; per un agente configurato con richieste di permesso, provocarne una
  normalmente e verificare `P`. Non è necessario modificare le policy.
- A destra nella barra, verificare il formato `2 CDX-pippo I`: sigla identica alla
  lista completa, primi cinque caratteri del nome reale (nessuna abbreviazione
  `P-N`). Il nome deve essere rosso per unsandboxed, verde per normal/default,
  giallo per permissive, bianco per paranoid/custom. La lettera finale segue
  invece lo stato: `R` verde, `I` giallo, `P` rosso. Per esempio un agente normal
  in attesa mostra `CDX-pippo` verde e `I` gialla.
- A sinistra devono comparire tutti gli agenti, anche `R`, `S` e `-`, in ordine
  numerico. Con due agenti in attesa verificare per esempio `!2 1R2I3P4S5-`.
  Il conteggio `!2` deve avere un colore distinto dagli stati (ciano nella palette
  default); verificare la distinzione anche con `minimal-mono`.
  Rispondere a uno: il conteggio scende. Fermare un agente: diventa `S` e non
  resta nel conteggio. La pipeline via file può richiedere circa cinque secondi.
- Ridurre a 40 colonne: conteggio e panoramica sintetica di tutti gli slot devono precedere le voci
  ordinarie troncate. Le lettere devono bastare anche senza distinguere i colori.
- Aprire un normale tab Zellij: la barra deve continuare a mostrare lo stesso
  controller. `Alt+d` deve riportare al controller nel suo tab.
- Il fullscreen nativo Zellij può nascondere tutti gli altri pane, inclusa la
  barra: uscirne deve ripristinare la vista gestita.

## Palette (#294)

Da un altro terminale cambiare la palette mentre la dashboard è aperta:

```bash
lince-config set dashboard.theme minimal-mono --target dashboard
lince-config set dashboard.theme dracula --target dashboard
lince-config set dashboard.theme gruvbox --target dashboard
lince-config set dashboard.theme default --target dashboard
```

Attendere circa cinque secondi dopo ogni comando. Verificare lista, selezione,
status line e wizard. `default` eredita i colori Zellij; il tema dell'applicazione
agente non deve cambiare. Con `minimal-mono` attenzione e selezione restano
riconoscibili grazie a lettere, marcatori e sfondo della selezione.

Provare un nome sconosciuto: `lince-config set dashboard.theme typo --target dashboard`.
Aprire il controller: deve comparire l'avviso e la palette deve tornare a default.
Infine ripristinare il valore precedente (oppure usare `unset` se non era impostato).

## Revert e varianti

```bash
lince-dashboard-launch --preset classic
lince-dashboard-launch --preset minimal --frames
lince-dashboard-launch --preset minimal --layout dashboard
# Solo se VoxCode è installato:
lince-dashboard-launch --preset minimal --layout dashboard-tiled-vox
```

`classic` ripristina le barre Zellij e la tabella completa quando `compact` non
è impostato esplicitamente. `--frames` riabilita i frame per la sessione.
La variante floating deve permettere focus/unfocus senza nascondere la barra;
la variante VoxCode deve mantenere il suo pane voce e il corretto viewport.

Ripetere `update.sh`: le scelte esplicite in `config.toml`, le modifiche personalizzate a
`~/.config/lince-dashboard/zellij.kdl` e la configurazione globale Zellij devono
rimanere intatte. Solo i vecchi binding LINCE di Alt+h/i/l/n vengono migrati,
con backup `zellij.kdl.bak-shortcuts`; verificare anche i nuovi binding in `.dist`. I nuovi default sono disponibili nei file `.dist`.

Segnalare eventuali problemi indicando preset, dimensioni del terminale,
azione eseguita, tipo di agente e comportamento atteso/osservato.

## Status bar: ordine, selezione e attenzione

- Creare nove agenti e provare una finestra larga 100 colonne: la barra usa due
  righe e deve mostrare tutte le nove voci brevi, senza spezzare una voce.
- Cambiare con `Alt+1/2/3`: le voci non cambiano ordine né posizione. Solo quella
  selezionata ha `*numero` bianco; gli altri numeri hanno il colore del nome.
  Il nome mantiene il colore sandbox e non compare `[normal]` o un altro livello.
- Conteggio e numeri a sinistra devono restare sulla seconda riga.
- Portare un agente in `R`: solo la `R` rimbalza verticalmente tra le due righe.
- Portare agenti in `I` e `P`: lettere fisse sulla seconda riga e `v` esattamente
  sopra sulla prima. Solo la `v` alterna giallo/rosso; lettere e numeri mantengono
  i colori degli stati. Verificare anche senza agenti in `R`. Nomi fermi.
- `S` e `-` restano fissi sulla seconda riga. Nei passaggi `R → I/P → R`,
  freccia e lettera devono aggiornarsi senza lasciare caratteri residui.

## Sidebar stretta e status bar opzionale

- Avviare senza `sidebar_width` esplicito: sidebar al 15%, agente sul restante 85%.
- Da un agente, `Alt+b` nasconde la barra: il pane recupera le due righe.
  Ripetere: la barra torna in basso e l’agente mantiene il focus.
- Ciclare `Alt+b` tre volte: assente → solo riepilogo sinistro → completa. Alternare anche `Alt+s`. Con entrambe nascoste,
  l’agente riempie il terminale; `Alt+1/2/3`, `Alt+d/i/h/n` restano utilizzabili.
- Provare `Alt+b` anche in modalità locked e verificare che non compaiano nuovi pane.

- In modalità riepilogo verificare che restino numeri/stati e animazioni a sinistra,
  senza nomi a destra. Entrambe le modalità visibili occupano due righe.
- Salvare con `Alt+q` con sidebar nascosta e barra solo riepilogo; rilanciare nella
  stessa directory: deve tornare la stessa disposizione. Ripetere con entrambe
  nascoste e con sidebar visibile. `Alt+d`, poi `q` non deve sovrascrivere la vista salvata.
