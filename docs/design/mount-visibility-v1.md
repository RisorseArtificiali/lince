# Masking opt-in dei mount LINCE — accordo per la v1

Definito nel brainstorming del 19 ottobre 2026, poi semplificato su richiesta dell'utente: aggiungere il masking opt-in di un altro punto di mount **con le stesse garanzie di alto livello attualmente offerte dalla home**, senza estenderle in questa feature.

## Ambito e configurazione

- Il comportamento predefinito resta invariato: nessun mount escluso automaticamente.
- L'utente elenca esplicitamente i **punti di mount su directory** da nascondere nella configurazione globale LINCE. Sono ammessi sia il Config v2 globale (`~/.config/lince/lince.toml`) sia il formato globale precedente (`~/.agent-sandbox/config.toml`), con la precedenza già prevista da LINCE quando coesistono. I file locali del progetto non possono definire o sostituire questa lista: se provano a definirla, errore esplicito.
- Si configura il percorso reale del punto di mount, non un symlink. Nel caso discusso: `/run/media/alessio/Dati`, non `/dati`. Il symlink deve comunque seguire la vista mascherata.
- La regola vale per ogni agente bwrap avviato dal dashboard o direttamente tramite `agent-sandbox`, a tutti i livelli e anche in `learn`. Con un backend che non può applicarla, l'avvio fallisce invece di ignorarla.

## Vista della sandbox

- LINCE maschera **il percorso del punto di mount configurato** con lo stesso schema usato per la home: `--tmpfs` dopo il root read-only, poi bind della workdir in lettura/scrittura. Il symlink `/dati` segue il percorso reale mascherato. Non c'è scoperta automatica di altri bind alias: se lo stesso contenuto è montato anche altrove, quell'altro percorso mantiene la visibilità che ha oggi nella sandbox.
- Una workdir ampia può comprendere anche l'intero mount escluso: è una scelta dell'utente e LINCE non la vieta. Sono visibili i componenti del percorso necessari a raggiungere la workdir.
- Fuori dalla workdir, la vista mascherata è un `tmpfs` vuoto ma scrivibile: le scritture lì sono effimere, come per la home attualmente mascherata. Le scritture nella workdir persistono.
- Un filesystem distinto montato **dentro** il mount protetto è nascosto attraverso il percorso protetto, ma un suo punto di mount esterno non è nascosto automaticamente: occorre configurarlo esplicitamente. I mount annidati nella workdir conservano il comportamento attuale; un eventuale controllo generale degli alias è annotato come effort separato.
- La garanzia riguarda l'accesso ai percorsi del filesystem nella sandbox, non copie dei dati già presenti nella workdir o dati forniti da servizi esterni.

## Conflitti e durata

- Come per la home, i bind configurabili successivi possono riesporre contenuti se l'utente li configura; questa v1 non introduce una verifica generale dei conflitti o degli alias. Gli `raw_bwrap_args` sperimentali conservano il loro comportamento e il relativo avviso.
- Se un punto configurato non è montato, LINCE avvisa con precisione (non afferma che il volume fisico sia assente) e maschera comunque quel percorso. La policy è basata su punti di mount, non sull'identità dei volumi; non introduce garanzie aggiuntive contro nuovi mount o alias creati sull'host durante la sessione.
- Le modifiche alla configurazione si applicano ai nuovi avvii; gli agenti già attivi richiedono un riavvio.
- Con la regola attiva, il banner di avvio riepiloga percorsi mascherati, workdir riesposta, punti non montati e override sperimentali, senza promettere che tutti gli alias del contenuto siano nascosti.
- Il ciclo di vita del disco (smontaggio o rimozione mentre l'agente lavora) non fa parte di questa feature.

## Verifiche della v1

Primi risultati su una macchina senza `Dati`: [mount-visibility-spike-2026-10-19.md](../history/mount-visibility-spike-2026-10-19.md). Confermano la fattibilità meccanica del mask del percorso e della riesposizione della workdir. Le prove sugli alias e sui mount futuri riguardano l'effort più forte e separato, non bloccano la v1.

1. Provare su un host con il mount reale: percorso `/run/media/alessio/Dati` mascherato, `/dati` che segue la stessa vista, workdir sul mount accessibile e scrivibile, directory sorella invisibile dal percorso configurato.
2. Verificare il comportamento quando il mount è assente (warning, avvio e vista mascherata), quando il backend è non supportato (errore) e in `learn`.
3. Documentare esplicitamente la parità con i limiti della home: altri bind alias e nuovi mount dall'host non sono coperti da questa feature.

## Fuori ambito, annotato a parte

La protezione della configurazione e degli eseguibili LINCE contro modifiche che influenzano **avvii futuri** è un effort separato. In questa v1 la configurazione locale non può sostituire la lista globale dei punti da mascherare, ma gli altri bind mantengono le normali regole di precedenza. Vedere [mount-visibility-open-questions.md](mount-visibility-open-questions.md) per la questione dei mount annidati nella home e l'hardening generale del masking.
