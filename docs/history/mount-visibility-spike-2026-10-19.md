# Spike sintetico bwrap — masking dei mount

**Ambiente:** Linux su una macchina diversa da quella dove si trova `Dati`; bubblewrap 0.11.0. Prove su un albero temporaneo sotto `/tmp/opencode/lince-mount-spike`, con bind e mount creati esclusivamente dentro namespace `unshare -Urnm`. `Dati` e la configurazione LINCE dell'altro host non sono stati testati.

## Maschera e workdir

Allestiti un mount di prova, un alias bind completo, un alias bind di una sua sottodirectory e un symlink verso il mount originale. Usando `bwrap --ro-bind / /`, `--tmpfs` su ciascuno dei tre punti di mount e infine `--bind <mount>/project <mount>/project`:

- il file del progetto era leggibile e una scrittura nella workdir arrivava alla directory sorgente;
- una directory sorella non era visibile né nel mount originale né nell'alias completo o parziale;
- l'alias completo **non** esponeva una seconda copia della workdir;
- il symlink verso il percorso originale seguiva la vista mascherata e vedeva soltanto la workdir.

**Controesempio importante:** la sorgente del bind (`.../source/private/secret.txt`) è rimasta leggibile in bwrap pur avendo mascherato `disk`, `alias` e `partial`. La sorgente è una directory ordinaria del filesystem genitore, non un punto di mount separato. Un filtro che scandisca solo gli alias elencati come mount point non basta per un mount configurato che sia a sua volta un bind.

Aggiungendo una maschera esplicita anche su `.../source`, il segreto non era più leggibile da quel percorso, mentre il progetto riesposto sotto `disk/project` restava accessibile. Questo verifica la possibilità meccanica di chiudere quel caso, **non** la capacità di rilevare automaticamente ogni sorgente equivalente.

**Conclusione limitata:** l'ordine delle operazioni bwrap consente la vista desiderata *ai percorsi mascherati*, ma la garanzia completa non è ancora dimostrata. In questa fixture `findmnt` riportava la stessa coppia `MAJ:MIN` e `FSROOT` per l'alias completo, e un `FSROOT` discendente per quello parziale. Per individuare anche la sorgente ordinaria occorre ragionare sulla radice del filesystem e sugli antenati, non solo confrontare l'elenco dei punti di mount. Vanno valutati inoltre mount annidati e filesystem diversi.

## Mount successivi all'avvio

Con un mount genitore marcato `shared` nell'host sintetico, bwrap mostrava il suo corrispondente come `private,slave`. Dopo l'avvio della sandbox, un nuovo bind alias del contenuto protetto, montato altrove sotto quel genitore, diventava **visibile** dentro bwrap nonostante il punto originale fosse mascherato. Questo riproduce una violazione del requisito sui mount aggiunti successivamente.

Una maschera `--tmpfs` già presente *sullo stesso percorso* rimaneva invece opaca nel test quando l'host montava lì dopo l'avvio: questo da solo non basta, perché un alias nuovo su un altro percorso resta visibile.

Ripetendo il caso dell'alias nuovo con un namespace di mount reso `private` **prima** di bwrap (`unshare -m --propagation private` dentro il namespace di test), l'alias non compariva. Su questa macchina funzionava anche `unshare -Urm --propagation private bwrap --ro-bind / / -- ...`, che mostrava `/` come `private` dentro la sandbox.

**Conclusione limitata:** congelare la vista dei mount sembra fattibile su questa macchina, ma il bwrap corrente da solo non la garantisce. Prima di implementare vanno verificate compatibilità con i wrapper LINCE (incluso paranoid e Landlock), permessi/user namespace, ordinamento e integrazione con i mount configurabili.

## Verifica sull'host `Dati` e lavoro separato

Per la v1 semplificata, sull'host reale verificare: radice del mount e symlink `/dati`, lavoro nella directory del progetto su quel mount, directory sorelle nascoste dal percorso configurato, mount assente, `learn` e backend non supportato. La v1 si limita alla garanzia attuale della home: **non** richiede scoperta degli alias o isolamento dai mount futuri. Le prove e i limiti su alias bind completi/parziali, sorgenti ordinarie, mount successivi e bind configurati in conflitto sono materiale per l'enhancement separato. Un risultato sintetico positivo non sostituisce le verifiche sull'host reale.
