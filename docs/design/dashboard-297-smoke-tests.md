# Smoke test #297 — VoxCode integrato

Aggiornare con `bash lince-dashboard/update.sh` dal branch della PR e avviare una
nuova sessione. Serve VoxCode installato con il proprio installer; nessuna
modifica al repository VoxCode è necessaria. I test automatici non usano audio reale.

1. Avviare `lince-dashboard-launch --preset minimal`: nessun pane voce fisso.
   Se VoxCode è installato e abilitato, compare `V-??????` (oppure `VP/VA-STOP`
   se già configurato). Il microfono non deve essere attivo.
2. `Alt+v`: scegliere microfono, lingua, modello e CPU/CUDA; `s` salva. `a` avvia:
   attendere LOAD, parlare e verificare il livello. Chiudere con Esc, riaprire
   con Alt+v: nessuna seconda istanza, stesso stato e impostazioni.
3. In PTT, usare Alt+t oppure Ctrl+Space due volte. Provare anche una
   scorciatoia per iniziare e l’altra per terminare. Il testo resta nel buffer se auto-insert è
   disattivato; `i` dal popup o «comando: invia» lo inseriscono nel terminale.
   Riprovare con auto-insert attivo. Non deve essere premuto Enter nell'agente.
4. Ripetere prima con un agente e poi con una shell visibile. Aprire il popup
   non deve cambiare la destinazione. Nascondere/chiudere il destinatario durante
   la trascrizione: il messaggio resta in attesa, errore nel popup, nessun agente
   nascosto viene riaperto. Selezionare un terminale valido: consegna una sola volta.
5. In VA parlare, verificare il livello e le trascrizioni; `m` mette in mute:
   niente acquisizione, livello fermo, indicatore MUTE. Parlare durante il mute
   non deve produrre testo neppure dopo la ripresa. `p` riprende rapidamente.
6. `x` ferma, rilascia microfono e modello. Uscire con Alt+q e rilanciare:
   configurazione conservata ma VoxCode fermo. Anche uscita senza salvataggio
   degli agenti conserva le impostazioni voce già salvate.
7. Ripetere Alt+v/Alt+m/Alt+t/Ctrl+Space in modalità locked (Ctrl+l), con sidebar nascosta e
   tutti gli stati di Alt+b. Voice meter solo nella sezione sinistra visibile;
   R verde e / bianco si alternano sulla seconda riga, senza sovrapposizioni.
8. Selezionare un microfono inesistente: errore leggibile nel popup, nessun crash.
   Impostare `[dashboard] voxcode_enabled=false`: nessun avvio tramite Alt+t o Ctrl+Space.
9. Installer/quickstart: con VoxCode presente compare una domanda di abilitazione;
   --defaults non si ferma sulla domanda. Nessun layout vox viene imposto.
