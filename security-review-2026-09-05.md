# LINCE: revisione di sicurezza, architettura e utilità

> Documento storico: risultati riferiti alla revisione e alla data indicate qui sotto.
> La pubblicazione non costituisce una nuova verifica del codice corrente né
> attesta che ciascun problema sia ancora presente o sia stato risolto.

**Data:** 5 settembre 2026
**Revisione analizzata:** `6ff12f27c2e89d9673f134c1fef2f21d5b485890`, con lo stato locale del workspace. Le modifiche preesistenti dell’utente non sono state alterate.
**Ambito:** launcher `agent-sandbox`, profili bwrap/Seatbelt, Landlock, proxy credenziali, dashboard Zellij, risoluzione della configurazione e broker opzionale `lince-lab`.

## Giudizio

**LINCE ha un’utilità concreta come postazione multiagente, ma nella versione analizzata non lo considererei un confine di sicurezza affidabile per agenti YOLO che possano diventare avversari a causa di prompt injection.** La ragione principale non è un’ipotetica vulnerabilità del kernel: ho riprodotto un’uscita dalla sandbox attraverso un’interfaccia dell’host che il launcher espone intenzionalmente.

Il caso più grave riguarda il socket di Zellij. Un processo avviato con il percorso completo `agent-sandbox run --sandbox-level paranoid`, con namespace di rete, isolamento PID, proxy e Landlock attivi, è riuscito a chiedere a Zellij di avviare un processo sull’host. Quel processo ha scritto un marcatore innocuo fuori dal progetto autorizzato. **Il livello `paranoid` non impedisce questa catena.**

La base tecnica merita di essere sviluppata: bwrap applica un isolamento reale, il progetto incorpora difese utili e dispone di test. Tuttavia, le aperture per integrare dashboard, desktop e laboratorio attraversano proprio il confine che si vorrebbe proteggere. Il README promette più di quanto il codice garantisca: espressioni come «zero host risk» e l’impossibilità di raggiungere credenziali cloud vanno corrette subito.

## Metodo e limiti

Ho letto implementazione, configurazioni distribuite, registro degli agenti, test e documentazione; ho inoltre confrontato alcuni aspetti con la documentazione primaria di bubblewrap, Landlock e Zellij.

Le verifiche dinamiche hanno usato una home fittizia, repository temporanei, credenziali inventate e una sessione Zellij dedicata. Non ho interrogato metadata cloud, inviato segreti a servizi esterni, modificato sessioni Zellij dell’utente, avviato VM reali o eseguito prove distruttive. Il programma Python di prova ha sostituito il coding agent: è sufficiente per verificare i privilegi disponibili a qualsiasi comando eseguito da un agente YOLO.

Ambiente osservato: Linux `7.1.10-200.fc44.x86_64`, Zellij `0.44.0`, Landlock ABI `9`. **Non ho eseguito Seatbelt su macOS**: per quel backend le conclusioni derivano dal generatore di profili e dai test disponibili, non da un attacco eseguito su un Mac. Non è un penetration test esaustivo, né un audit completo delle dipendenze o di tutti gli installer.

Nel seguito distinguo:

- **Riprodotto:** comportamento osservato con una prova innocua.
- **Verificato nel codice:** il percorso e la policy sono espliciti, ma manca una prova completa sul backend interessato.
- **Rischio condizionato:** dipende da servizi, credenziali o altre caratteristiche dell’installazione.

## Che cosa costruisce il progetto

La dashboard è un plugin Rust/WASM di Zellij: gestisce pannelli, selezione degli agenti, livelli di sandbox, provider, stato, ripristino della sessione e relay dei messaggi. Il launcher Python traduce configurazioni e profili in comandi bwrap oppure profili Seatbelt. `lince-config` e `registry.d` cercano di centralizzare definizioni e policy; `lince-lab` aggiunge un broker sull’host per pilotare VM di test.

Il confine rilevante è questo:

```text
HOST: dashboard, Zellij server, launcher, proxy, eventuale broker lab
                         |
             avvio del processo isolato
                         |
SANDBOX: agente + shell + build + dipendenze + strumenti MCP locali
                         |
        progetto scrivibile, configurazioni/cache esposte
                         |
        socket Zellij / Wayland / eventuale broker lab
                         |
           ritorno a servizi eseguiti sull’HOST
```

WASM protegge l’esecuzione del plugin secondo i permessi concessi da Zellij; non rende automaticamente sicuri i comandi host richiesti dal plugin. Analogamente, il namespace protegge il processo agente, ma non trasforma un server host raggiungibile via socket in un servizio confinato.

Bubblewrap stesso precisa che è uno strumento per costruire sandbox e che la sicurezza dipende dalla policy e dagli argomenti scelti dal chiamante. La tecnologia è adeguata allo scopo; la sua presenza non certifica il risultato. [Documentazione bubblewrap](https://github.com/containers/bubblewrap), [modello di sicurezza upstream](https://github.com/containers/bubblewrap/security).

## Risultati prioritari

| ID | Gravità | Problema | Evidenza |
|---|---|---|---|
| S1 | Critica | Socket Zellij: esecuzione di comandi sull’host anche da `paranoid` | Riproduzione completa Linux |
| S2 | Critica | Configurazione locale può allargare accesso a home, ambiente e policy | Merge e accesso host riprodotti |
| S3 | Critica, se lab attivo | `bisect.run`: hook Git eseguiti sull’host e output fuori dall’area consentita | Dispatcher reale, Git reale, VM simulata |
| S4 | Alta | Relay: shell injection nel percorso del transcript | Template di produzione riprodotto; flusso UI non eseguito |
| S5 | Alta | Seatbelt consente letture quasi globali, segnali e tutto il loopback host | Generatore verificato; nessun runtime macOS |
| S6 | Alta | Segreti leggibili e stato persistente condiviso tra agenti/sessioni | gcloud riprodotto; altre esposizioni nel codice |
| S7 | Alta/Media secondo configurazione | Proxy e rete non costituiscono una barriera generale contro esfiltrazione e SSRF | Bypass della blocklist riprodotto su loopback |
| S8 | Media | Stato e attestazioni di policy scrivibili dagli agenti | Mount e lettura dashboard verificati |
| S9 | Media | Blocco Git push inefficace; wrapper predefinito non visibile | Visibilità e selezione del binario riprodotte |
| S10 | Media | Hardening incompleto: terminale, IPC, GPU, risorse | Configurazione e launcher verificati |

Le gravità riguardano il modello richiesto: un agente può eseguire comandi arbitrari e non va considerato fidato. Non sono punteggi CVSS e non implicano che ogni installazione abbia tutte le condizioni necessarie.

### S1 — Il socket Zellij permette di uscire dalla sandbox

**Riferimento:** [sandbox/agent-sandbox](../sandbox/agent-sandbox), righe 3042–3047; applicazione Landlock nelle righe 3887–3992.

`build_bwrap_cmd()` rimonta in lettura/scrittura l’intera directory dei socket Zellij, se presente, per consentire agli hook di usare `zellij pipe`. Il mount non è limitato a un canale di aggiornamento dello stato e non viene rimosso dal profilo `paranoid`.

Il protocollo di Zellij permette anche di aprire pannelli ed eseguire programmi. Ho creato una sessione di test sull’host e, dall’interno della sandbox, usato `zellij --session <sessione-test> run -- <comando-marcatore>`. Il comando è stato eseguito dal server Zellij sull’host e ha scritto nella home fittizia dell’host, fuori dal progetto. Il successo è stato verificato dall’esterno della sandbox.

La prova è riuscita sia con il builder bwrap e Landlock sia con **l’intero percorso `cmd_run` del profilo Claude `paranoid` distribuito**, sostituendo esclusivamente il comando dell’agente con Python e usando una chiave API inventata. Il proxy era attivo, ma la prova non richiedeva chiamate API. La home e il runtime directory erano temporanei; la variabile runtime nel client era adattata al percorso di destinazione del bind.

```text
zellij normal: terminal_1
zellij host marker persisted normal: True
zellij paranoid-network: terminal_2
zellij host marker persisted paranoid-network: True
FULL cmd_run paranoid host marker persisted: True
```

Il namespace di rete non risolve il problema: questa connessione usa un socket Unix con pathname esposto dal filesystem. Landlock viene applicato al processo agente e ai suoi figli, non al server Zellij già esistente che esegue la richiesta.

**Impatto:** esecuzione con i privilegi del processo Zellij, normalmente quelli dell’utente desktop, senza exploit del kernel. La CLI ufficiale documenta proprio l’avvio di comandi in nuovi pannelli. [Zellij CLI](https://zellij.dev/documentation/controlling-zellij-through-cli), [azioni CLI](https://zellij.dev/documentation/cli-actions.html?highlight=fullscreen).

**Correzione:** non esporre il socket di controllo Zellij agli agenti. Sostituirlo con un canale ristretto per eventi di stato, con identità dell’agente assegnata dal supervisore, formato validato e nessuna possibilità di scegliere azioni Zellij. Un bind read-only del socket non è una soluzione: il problema sono le operazioni del protocollo.

### S2 — Il repository può scegliere una policy più permissiva

**Riferimenti:** [sandbox/agent-sandbox](../sandbox/agent-sandbox), `load_config()` a riga 1261, `_find_fragment_path()` a riga 1305 e merge a riga 1418; [lince-config/lince-config](../lince-config/lince-config), righe 2261–2310.

Il launcher carica `.agent-sandbox/config.toml` dalla directory corrente e lo fonde sopra la configurazione globale: i valori scalari locali prevalgono, le liste si aggiungono. Anche i frammenti di profilo del progetto hanno precedenza su quelli installati. Non c’è, su questo percorso, un controllo che impedisca al progetto di ampliare i privilegi.

Una configurazione locale di prova contenente:

```toml
[sandbox]
extra_rw = ["~"]

[env.extra]
AUDIT_EXPOSED = "$AUDIT_FAKE_SECRET"
```

ha reso leggibile e scrivibile la home host fittizia, e ha importato una variabile segreta fittizia dall’ambiente del launcher. Il bind della home reale arriva dopo il tmpfs e lo ricopre. Ho verificato una scrittura persistente dall’esterno.

Ci sono due scenari distinti: un repository appena acquisito contiene già la configurazione; oppure un agente modifica la configurazione nel proprio progetto e l’allargamento si applica **al successivo lancio**. Non sto affermando che cambiare il TOML rimuova retroattivamente le restrizioni del processo corrente.

Il frammento `paranoid` aggiunge controlli di rete ma non azzera gli `extra_rw` ereditati. Inoltre, un frammento locale può sostituire quello distribuito. Il nome del livello non è una garanzia di policy immutabile. Il caricamento usa `cwd`, non necessariamente il progetto passato con `-p`: anche questa differenza va eliminata dalla semantica di sicurezza.

**Nota positiva ma insufficiente:** il resolver v2 gestisce `.lince/lince.toml` con `trust.projects.<percorso>.allow_loosening` e limita alcune modifiche locali. È la direzione corretta, ma il launcher mantiene il percorso legacy descritto sopra. La protezione del resolver non basta a rendere sicuro il caricamento effettivo.

**Correzione:** una sola policy risolta e applicata dal launcher; gli overlay non fidati possono solo restringere. Autorizzazioni ad ampliare mount, ambiente, upstream, backend e profili devono vivere fuori dal progetto e non essere scrivibili dagli agenti. Non basta proteggere la scelta nominale `normal`/`paranoid`.

### S3 — Il broker lab riesegue operazioni controllabili sull’host

**Riferimenti:** [sandbox/agent-sandbox](../sandbox/agent-sandbox), righe 3229–3238; [broker.py](../lince-lab/lince_lab/broker.py), righe 423–436; [policy.py](../lince-lab/lince_lab/policy.py), `check()` a riga 282; [bisect.py](../lince-lab/lince_lab/bisect.py), righe 125–129, 161 e 238.

Se il socket `~/.agent-sandbox/lince-lab.sock` esiste, viene esposto automaticamente anche agli agenti `paranoid`. Il broker fa controlli utili per `vm.copy_in` e `vm.copy_out`, ma `bisect.run` inoltra direttamente `repo_dir` e `out` forniti dal chiamante.

Nel percorso del bisect:

1. il broker esegue `git checkout` sull’host nella directory indicata;
2. Git può eseguire un hook `post-checkout` controllato dall’agente;
3. il risultato JSON viene scritto nel percorso `out`, senza confinarlo alla directory degli artefatti.

Ho inviato una richiesta al dispatcher di produzione, con un vero repository Git temporaneo e un vero hook innocuo. Solo il backend delle VM è stato sostituito con `FakeBackend`, così non è stata avviata alcuna VM. Il broker ha risposto `ok: true`; l’hook ha scritto un marcatore host e il JSON è stato scritto fuori dall’area degli artefatti.

```text
broker hook executes on host: True
broker output outside artifacts: True
```

Il commento che descrive `repo_dir` come copia di staging non è una verifica: quel percorso viene dal client. Il difetto permane anche eliminando Zellij, se il broker rimane raggiungibile.

**Correzione:** staging creato e identificato dal broker, senza accettare directory host arbitrarie; output solo sotto una radice controllata con difesa da symlink e race; Git del bisect eseguito in isolamento con configurazioni, hook e filtri del repository trattati come codice non fidato. Disabilitare soltanto gli hook riduce una via, ma non rende affidabile l’esecuzione host di tool su un repository ostile.

Inoltre, l’accesso al laboratorio dovrebbe essere una capability esplicita per sessione. Il prefisso `lince-lab-` limita il gruppo di VM, ma non separa le risorse appartenenti ad agenti diversi.

### S4 — Shell injection nell’estrazione dei transcript

**Riferimenti:** [config.rs](../lince-dashboard/plugin/src/config.rs), righe 537–569; [main.rs](../lince-dashboard/plugin/src/main.rs), righe 1667–1673 e 1714–1745.

`extract_transcript_async()` inserisce il percorso del transcript dentro un programma Python racchiuso tra doppi apici per `sh -c`. Applica `shell_escape()`, che protegge gli apici singoli per un altro contesto di quoting. Non neutralizza le sostituzioni della shell come `$()` all’interno di quei doppi apici.

Ho estratto dal sorgente il template esatto, applicato le stesse sostituzioni e usato come percorso una sostituzione shell che creava un marcatore temporaneo. **La shell ha eseguito il comando sull’host**, prima che Python tentasse di aprire il file.

Il percorso arriva da `transcript_path` nei messaggi di stato degli hook. La catena applicativa richiede quindi che l’attaccante possa fornire quell’evento e che venga avviata la funzione di relay. Non ho eseguito l’interazione completa nel plugin WASM; il sink vulnerabile è riprodotto, mentre la provenienza e il trigger sono verificati nel codice. Il normale polling dei file `.state` non imposta quel campo.

**Correzione:** lanciare Python con un vettore di argomenti e passare il percorso come `sys.argv[1]`, oppure usare un helper dedicato. Validare anche la provenienza degli eventi e confinare i transcript leggibili: eliminare la shell injection non deve lasciare una lettura arbitraria di file host tramite relay.

### S5 — Seatbelt ha una policy molto più ampia di quella suggerita dai livelli

**Riferimento:** [sandbox/agent-sandbox](../sandbox/agent-sandbox), `generate_seatbelt_profile()` a riga 2304, in particolare righe 2351–2368, 2455–2458 e 2472.

Il profilo generato contiene:

```scheme
(allow file-read* (subpath "/"))
(allow signal)
```

Le letture vengono negate esplicitamente solo per alcuni percorsi Git e SSH. Non vedo una allowlist delle letture che nasconda, per esempio, `.aws`, `.kube`, `.netrc`, `.agent-sandbox/config.toml`, altri file di configurazione o documenti privati. Restano i permessi ordinari del sistema e le eventuali protezioni macOS, ma LINCE non introduce una restrizione generale della riservatezza. Il proxy non può tenere segreti fuori dalla sandbox se questi sono leggibili anche nei file host.

Con `unshare_net = true`, il profilo consente **tutte le porte del loopback host**, non solo quella del proprio proxy. Database locali, altri proxy credenziali e API amministrative eventualmente presenti rimangono quindi raggiungibili. Il codice lo documenta come rischio residuo; non equivale alla rete privata di bwrap `paranoid`.

La regola globale sui segnali non limita esplicitamente le operazioni ai propri figli. Il backend non ha un namespace PID: la protezione dai segnali verso processi dello stesso utente non è quella del backend Linux. Questa concessione è una scelta della policy, non una ragione per presumere che qualunque profilo Seatbelt debba consentirla.

Ulteriore problema di costruzione: i percorsi vengono interpolati direttamente nelle S-expression, compreso `project_dir` a riga 2568, senza escaping dedicato. Percorsi con apici o newline possono alterare la sintassi del profilo. Non classifico come riprodotto un allargamento della policy tramite questo vettore: richiede una prova su macOS.

**Correzione:** allowlist delle letture, limitazione dei segnali, rete limitata al proxy specifico, costruzione parametrizzata/escaped dei profili e test negativi reali su macOS. Fino ad allora renderei evidente nell’interfaccia che i livelli Seatbelt e bwrap offrono garanzie differenti.

### S6 — Credenziali e stato non sono isolati quanto sembra

**Riferimenti:** [sandbox/agent-sandbox](../sandbox/agent-sandbox), righe 100, 2782–2802, 3077–3121, 3154–3204 e 4702–4769; [registro Codex](../registry.d/codex.toml), sezione `[sandbox]`; [profili](../sandbox/profiles/).

Le esposizioni più rilevanti sono:

- **gcloud è read-only per default:** `.config/gcloud` è in `home_ro_dirs`. La prova con un token fittizio ne ha confermato la visibilità. Read-only impedisce di modificare il file, non di estrarne un segreto. Il frammento paranoid non rimuove questa voce globale.
- **PATH allarga il filesystem visibile:** viene montata la directory di primo livello della home che contiene un eseguibile. Una voce `~/.local/bin` espone quindi l’intera `~/.local`, non solo `bin`. A seconda dell’installazione, può includere dati e credenziali di applicazioni.
- **Gli scratch sono copie, non bonifiche:** paranoid copia con `rsync -a` directory come `.claude` e `.codex`. File di autenticazione, configurazioni MCP e cronologia presenti nella sorgente vengono copiati senza selezione dei soli elementi necessari. Effimerità delle scritture e segretezza sono proprietà diverse.
- **Alcuni agenti usano configurazioni host scrivibili:** per esempio Codex ha `.codex` in `home_rw_dirs` al livello normale. Può alterare configurazioni consumate da sessioni successive, anche esterne a LINCE.
- **Cache e configurazioni persistenti non sono per istanza:** più agenti possono condividere directory di toolchain e configurazione. Un agente può avvelenare file che un altro eseguirà in seguito. I frammenti paranoid esaminati non disattivano globalmente `persist_toolchains`.

Il progetto di lavoro stesso può contenere `.env`, credenziali Git, chiavi, dati di test reali e informazioni proprietarie. L’accesso al progetto non implica che tutti quei file siano innocui.

**Correzione:** montare solo le risorse necessarie, autenticazione fuori dalla sandbox quando supportata, configurazioni private per istanza, scratch filtrati e cache separabili per dominio di fiducia. Esporre gcloud o una configurazione host scrivibile dovrebbe essere una scelta esplicita e visibile.

### S7 — La rete e il proxy hanno limiti sostanziali

**Riferimenti:** [sandbox/agent-sandbox](../sandbox/agent-sandbox), righe 580–666, 687–769, 938–980, 1143–1222, 3938–3983 e 4779–4803.

**Normal/permissive.** La rete è condivisa quando non è richiesto `unshare_net`. Normal senza proxy non limita l’egress. Normal con proxy può limitare le connessioni TCP tramite Landlock, ma il controllo è per porta, non per destinazione, e il proxy applica l’allowlist dei domini solo se `unshare_net` è attivo. Variabili `HTTP_PROXY` non obbligano da sole un processo arbitrario a usare il proxy.

**Paranoid Linux.** Namespace di rete e proxy con allowlist sono una difesa utile contro l’egress diretto, una volta chiusi i canali host descritti sopra. Non impediscono però di inviare contenuti ai servizi consentiti. Aggiungere domini di hosting generico amplia anche la possibilità di esfiltrazione; l’accesso a un dominio non identifica il repository, l’account o l’operazione autorizzati.

**Blocklist SSRF insufficiente.** `_is_blocked()` confronta stringhe di hostname senza verificare gli indirizzi IP effettivamente contattati. Ho configurato un proxy di prova per bloccare `127.0.0.1`: `CONNECT 127.0.0.1:<porta>` ha restituito `403`, mentre `CONNECT 127.1:<porta>` ha raggiunto lo stesso listener locale e restituito `200`. Nessun endpoint cloud è stato contattato. Questo dimostra il difetto del controllo testuale; alias DNS, indirizzi alternativi e risoluzione verso reti riservate richiedono una protezione sul vero indirizzo di connessione. Nel paranoid standard una destinazione non in allowlist rimane comunque rifiutata: non è un bypass universale della sua allowlist.

**Proxy come delega di credenziali.** Il listener TCP non autentica il chiamante e inoltra vari metodi HTTP con le credenziali configurate. Un processo che lo raggiunge può utilizzare quella delega anche senza leggere la chiave. Mancano limiti applicativi di operazioni, consumo e concorrenza. Su macOS, dove il loopback è condiviso anche in paranoid, il rischio tra agenti è particolarmente evidente.

**Copertura delle chiavi parziale.** Il collector scansiona chiavi riconosciute in `env.extra`, provider e configurazione agente; non è un secret broker generale, non ripulisce i file copiati e non include automaticamente ogni variabile passata tramite `env.passthrough`. Inoltre `upstream_base` proviene dalla configurazione: con il problema S2, un upstream locale ostile può diventare destinatario dell’iniezione di credenziali.

La distinzione per porta di Landlock non va presentata come firewall per host o URL; l’implementazione usa qui i diritti TCP e non attiva gli scope Unix/segnali più recenti. La documentazione kernel descrive separatamente queste capacità. [Landlock: userspace API](https://www.kernel.org/doc/html/latest/userspace-api/landlock.html).

**Correzione:** egress forzato verso un mediatore, controllo IP dopo risoluzione e sulla connessione effettiva, vincoli su dominio/porta/operazione, autenticazione per sessione e limiti di utilizzo. Gli upstream che ricevono chiavi devono essere parte della policy host fidata.

### S8 — Le attestazioni non sono una fonte indipendente dall’agente

**Riferimenti:** [sandbox/agent-sandbox](../sandbox/agent-sandbox), righe 3050–3054, 3701–3710 e 4031–4044; [config.rs](../lince-dashboard/plugin/src/config.rs), righe 509–525.

Tutti gli agenti vedono `/tmp/lince-dashboard` scrivibile. Lo stesso spazio contiene gli eventi `.state` e i record `.policy.json`; anche lo shim Landlock aggiorna il record dopo l’applicazione delle regole. Il processo agente, che vede il medesimo filesystem, può alterare questi file, compresi quelli degli altri agenti.

L’hash degli argomenti o del profilo è utile per diagnostica, ma un JSON riscrivibile dal soggetto controllato non è un’attestazione resistente a manipolazioni. La dashboard legge quei record tramite comandi host. Mancano inoltre, in questi percorsi, aperture protette da symlink e un namespace di stato privato per sessione.

**Correzione:** il supervisore host deve possedere lo stato autorevole della policy. Lo shim può riportare l’esito tramite un canale dedicato prima dell’exec, chiuso prima di consegnare il controllo all’agente. Gli aggiornamenti operativi non fidati devono restare distinti dall’attestazione della sandbox.

### S9 — «Git push bloccato» non è una garanzia effettiva

**Riferimento:** [sandbox/agent-sandbox](../sandbox/agent-sandbox), righe 2870–2941, 3150–3152 e 3263–3265.

Ci sono due problemi:

1. Il wrapper controlla soltanto se il primo argomento è `push`. Si aggira con il binario assoluto o con opzioni prima del sottocomando. Git config e wrapper non impediscono chiamate dirette a API remote o altri client.
2. Nella configurazione standard analizzata, la directory `~/.agent-sandbox/bin` viene aggiunta al PATH ma non è rimontata dopo che la home è nascosta. Ho creato il wrapper tramite `ensure_git_wrapper()` e verificato dentro bwrap: `wrapper_visible=False`, `git_path=/usr/bin/git`.

Non ho eseguito push reali. Il secondo test dimostra che il wrapper non viene selezionato nel caso predefinito; non pretende di coprire configurazioni personalizzate che riespongano quella directory.

L’assenza di autenticazione può impedire un push in una particolare installazione. Non è garantita: token possono trovarsi nel progetto, nei file esposti o nell’ambiente, e permissive passa esplicitamente variabili GitHub.

**Correzione:** considerare il wrapper un aiuto contro errori accidentali, non un controllo di sicurezza. Per impedire modifiche remote servono credenziali prive di capacità di scrittura o un mediatore che autorizzi operazioni precise.

### S10 — Hardening e disponibilità da completare

**Riferimenti:** [sandbox/agent-sandbox](../sandbox/agent-sandbox), righe 222, 3033–3064, 3241–3246, 3938 e 7136–7154.

- **Terminale:** `new_session` è disabilitato per default e non vedo un filtro seccomp per `TIOCSTI`. La sfruttabilità dipende da kernel, sysctl e terminale; non l’ho provata. Upstream bubblewrap richiede `--new-session` quando quel vettore non è filtrato. [README bubblewrap](https://github.com/containers/bubblewrap).
- **Wayland:** il socket viene riesposto automaticamente per supportare la clipboard. Le operazioni disponibili dipendono dal compositor e dai protocolli; non equivale a poter fare keylogging universale, ma riapre l’interazione con il desktop. Il mount read-only non rende read-only le richieste al compositor.
- **Altri socket:** viene nascosto `/run/user/<uid>`, non tutto `/run`. Eventuali socket amministrativi accessibili all’utente in altri percorsi, ad esempio API di container, devono entrare nel modello di minaccia. Non ho verificato la presenza o l’utilizzabilità di tali servizi sull’host reale.
- **IPC e syscall:** non vedo `--unshare-ipc` né un filtro seccomp nel percorso bwrap. Non affermo che questa sola assenza consenta un escape: amplia ciò che va valutato e testato.
- **GPU:** `expose_gpu` ha default effettivo `true` a normal/permissive; paranoid lo disattiva salvo override esplicito. Esporre i device amplia l’interfaccia del kernel e il rischio di consumo delle risorse GPU. Il banner li descrive come opt-in, ma il default del codice non lo è.
- **Disponibilità:** non vedo cgroup, quote disco o limiti coerenti su memoria, CPU e numero di processi. Un agente può saturare risorse senza violare i mount. Non ho lanciato fork bomb o stress test.

## Quanto proteggono davvero i livelli

| Modalità | Utilità reale | Limite decisivo oggi |
|---|---|---|
| Linux normal | Blocca molte scritture accidentali sull’host; nasconde parte della home; isola i PID | Socket host, segreti esposti, rete normalmente aperta, config/stato condivisi |
| Linux paranoid | Aggiunge rete privata, proxy con allowlist e Landlock; scratch per alcune configurazioni | Escape Zellij riprodotto; broker lab opzionale; policy locale e letture ereditate |
| Linux permissive | Ambiente di lavoro pratico con più strumenti e autenticazione | Pensato per fiducia più alta; non lo userei per contenere un agente ostile |
| Seatbelt normal/permissive | Restrizioni sulle scritture secondo il profilo | Letture globali e rete ampia; niente equivalenza con tmpfs home/PID namespace |
| Seatbelt paranoid | Restringe l’egress diretto al loopback e usa il proxy | Loopback host completo, letture quasi globali e segnali consentiti |
| Backend deprecated/non sandboxed | Compatibilità e casi d’uso espliciti | Non sono una scorciatoia per ottenere le garanzie del paranoid Linux |

Anche dopo le correzioni, nessuna modalità dovrebbe promettere di proteggere il contenuto scrivibile del progetto da un agente autorizzato a modificarlo. L’agente può cancellarlo, introdurre una backdoor nel codice, alterare test o preparare un hook che verrà eseguito successivamente sull’host. Separare il lavoro su clone/volume dedicato e rivedere le modifiche prima di eseguirle sull’host rimane utile.

Gli snapshot aiutano il recupero, ma il default ha `auto_project=false`; `.git` è esclusa dagli snapshot del progetto e Seatbelt non usa il percorso di auto-snapshot del ramo bwrap. Non sono una barriera preventiva né un rollback completo garantito. La deduplicazione con `--link-dest` è fra snapshot: non ho trovato evidenza che la directory di lavoro venga direttamente hardlinkata agli snapshot.

Landlock è un’aggiunta valida, ma qui deriva le regole dai mount, incluse concessioni ampie come il tmpfs della home, e consente letture da `/`. Rafforza il meccanismo; non corregge una policy troppo larga, una copia contenente segreti o un server host che esegue comandi per conto dell’agente.

## Utilità e qualità del progetto

### Aspetti riusciti

- **Problema d’uso reale:** avvio di agenti eterogenei, stato uniforme, focus, raggruppamento per progetto e ripristino delle sessioni riducono lavoro manuale. La scelta terminale/Zellij è coerente con il pubblico tecnico.
- **Controlli esterni all’agente:** non si affida soltanto alla promessa del modello di rispettare regole. Mount, clearenv, namespace PID, rete privata opzionale e Landlock sono meccanismi concreti.
- **Registro dichiarativo degli agenti:** evita di integrare ogni nuovo CLI soltanto con logica ad hoc. Provider e livello di isolamento sono concetti distinti: è una buona separazione.
- **Test e diagnostica presenti:** schema, merge, registro, policy, proxy, Landlock e broker hanno test; i record di policy e i messaggi di degrado sono una buona idea, purché se ne corregga la fiducia.
- **Lab progettato con una policy server:** template forzati, assenza di mount host nei template, restrizioni sui trasferimenti e backend sostituibile sono scelte positive. La lacuna del bisect è grave proprio perché aggira un’impostazione altrimenti sensata.
- **Documentazione dei rischi in alcuni punti:** il codice Seatbelt ammette il loopback condiviso, i profili permissive descrivono una fiducia maggiore e il backend nono è marcato come deprecato.

### Aspetti che riducono la fiducia tecnica

**Il componente di sicurezza è troppo concentrato.** `agent-sandbox` ha circa 8.000 righe e combina proxy HTTP, configurazione, generazione dei profili, namespace, syscall Landlock, snapshot, migrazioni e learn mode. La distribuzione come file unico è comoda, ma rende più difficile isolare invarianti e verificare tutti i percorsi. Si può mantenere un eseguibile unico distribuibile senza sviluppare tutto in un solo modulo.

**La migrazione della configurazione è incompleta come confine di fiducia.** Registro v2, resolver, configurazioni legacy, frammenti per livello, alias e override sperimentali convivono. Ci sono test contro il drift, ma rimangono più interpretazioni della policy: il caso S2 ne mostra un effetto di sicurezza, non soltanto manutentivo. Il prossimo investimento dovrebbe essere una rappresentazione di policy unica consumata dal launcher.

**I commenti non sono sempre allineati al codice.** In `main.rs` intorno a riga 249 si afferma che il socket Zellij non è bind-mountato; il launcher lo rimonta esplicitamente. README e schema del filesystem descrivono socket nascosti e credenziali cloud irraggiungibili, mentre il codice li riespone. I commenti dei profili talvolta promettono cache effimere che non derivano dai valori effettivamente ereditati.

**Il codice tipizzato non elimina i confini fragili.** La dashboard usa Rust e strutture chiare, ma molte operazioni sull’host passano per stringhe shell/Python. Il difetto del relay mostra che il quoting deve essere corretto per ciascun livello di interpretazione. Preferire argomenti strutturati è una semplificazione architetturale oltre che una difesa.

**Manca una dimostrazione automatica del confine completo.** I test delle singole funzioni sono utili, ma non bastano quando più componenti si delegano operazioni. Non ho trovato una pipeline `.github/workflows` nel checkout; sono presenti script di verifica e CI locale/VM. Non ho verificato eventuali pipeline esterne al repository.

La mia valutazione è quindi: **buon progetto pratico, con sviluppo sostanziale e attenzione alla sicurezza, ma non ancora maturità da prodotto di contenimento avversariale**. I problemi trovati suggeriscono una revisione concentrata dei confini di fiducia, più che l’aggiunta indiscriminata di altri strati o una riscrittura in un linguaggio diverso.

## Verifiche eseguite

| Verifica | Esito | Portata |
|---|---|---|
| `python3 -m pytest scripts/tests lince-lab/tests -q` | **366 passed, 16 skipped** | Le integrazioni con VM reali hanno gate dedicati e non sono state abilitate |
| `python3 -m unittest discover -s scripts/tests -q` | **120 test passati** | Sottoinsieme sovrapposto alla suite precedente, non da sommare |
| `sandbox/tests/test-credential-proxy.sh` | **40 assertion passate** | Principalmente costruzione e precedenza delle regole credenziali |
| `sandbox/tests/test-landlock-exec.sh` | **11 check passati**, ABI 9 | Filesystem, TCP, degrado/fail-closed e record dello shim |
| `sandbox/tests/test-seatbelt-profile-network.sh` | Passato | Generazione policy e verifiche proxy; non esegue Seatbelt su macOS in questa prova |
| Home nascosta / gcloud esposto | Riprodotto | File esclusivamente fittizi |
| Configurazione locale che espone home/ambiente | Riprodotto | Merge reale e bwrap reale |
| Escape via Zellij normal/paranoid | Riprodotto | Server dedicato, bwrap/Landlock reali, anche launcher completo paranoid |
| Relay shell injection | Riprodotto sul template reale | Non provata l’interazione UI completa |
| Broker bisect: hook host e output arbitrario | Riprodotto | Dispatcher e Git reali; VM simulata |
| Proxy blocklist con alias IP | Riprodotto | Listener solo su loopback, nessun metadata cloud |
| Test Rust del plugin | Non completabili con la toolchain disponibile | Target host non linka gli import Zellij; runner ufficiale bloccato da rustup senza default; Cargo di sistema senza target WASI |

Il warning pytest riguarda la cache non scrivibile nella directory superiore; non è un errore dei test. Non ho installato toolchain o modificato la configurazione Rust dell’utente per completare la suite WASM. Quei problemi dell’ambiente non sono classificati come bug del progetto.

Ho inoltre eseguito `sandbox/test-sandbox.sh` dentro una sandbox di prova: termina con codice 1 prima di completare i controlli. Usa `set -e` e contatori come `((PASS++))`: quando il valore iniziale è zero, l’espressione restituisce stato 1 e interrompe lo script. Anche l’indisponibilità di `mount` produrrebbe il ramo `warn` con lo stesso difetto. Il risultato non costituisce una prova di fallimento dell’isolamento: è un problema del verificatore.

Artefatti locali delle prove: `/tmp/lince-security-review.Ns9qg5/`, con `probe.py`, `probe_more.py` e log; i primi tre log delle suite sono `/tmp/lince-review-unit-tests.log`, `/tmp/lince-review-proxy-tests.log` e `/tmp/lince-review-landlock-tests.log`. Sono temporanei. Le sessioni Zellij di prova sono state chiuse. Questo report non dipende dalla conservazione di tali file per descrivere risultati e limiti.

## Interventi consigliati, in ordine

### P0 — Chiudere le deleghe di esecuzione host

1. Rimuovere il socket Zellij dai mount degli agenti, incluso learn mode; introdurre un canale minimo per lo stato.
2. Rendere opzionale e per sessione l’accesso al broker lab; confinare `repo_dir`/`out` e spostare le operazioni Git su input non fidati in isolamento.
3. Eliminare il quoting annidato dal relay e verificare l’origine dei transcript.
4. Impedire agli overlay del progetto di ampliare la policy effettiva del launcher, anche tramite il percorso legacy e i profili locali.
5. Correggere subito le promesse del README e il significato dei badge: `paranoid` oggi non equivale a host protetto da un agente avversario.

### P1 — Rendere coerenti isolamento e segreti

1. Allowlist delle letture per Seatbelt; segnali e loopback ristretti; test negativi su un Mac reale.
2. Rimuovere l’esposizione predefinita di gcloud e delle directory PATH troppo ampie; rendere esplicite le capability desktop, GPU e credenziali.
3. Stato e policy record gestiti dal supervisore, configurazioni private per istanza e cache separate secondo il livello di fiducia.
4. Unificare resolver e applicazione della policy; fallimento chiuso determinato dalle capacità richieste, non soltanto dal nome esatto `paranoid`. Oggi alcuni controlli confrontano letteralmente quel nome e meritano test anche per livelli derivati.
5. Irrobustire proxy, autenticazione per sessione, controllo SSRF e limiti sulle operazioni/risorse.

### P2 — Verificare continuamente il prodotto completo

Servono test di regressione che partano dal vero launcher e provino a raggiungere un server host innocuo, scrivere fuori dal progetto, leggere segreti fittizi, modificare lo stato di un altro agente e alterare la configurazione del lancio successivo. Per Zellij e lab, il test deve verificare **che il marcatore host non venga creato**, non soltanto che sia presente un flag di isolamento.

Per le prove di segnali, rete e disponibilità usare processi/listener dedicati e limiti stretti. Aggiungere una matrice Linux/macOS, chiarire i test saltati e correggere il verificatore shell. Separare nel codice policy, backend, proxy e supervisione renderebbe queste verifiche più semplici.

## Come lo userei oggi

Userei LINCE come dashboard per lavoro controllato su copie recuperabili dei progetti. **Non affiderei all’attuale `paranoid` la protezione di una workstation contenente segreti importanti davanti a repository o agenti potenzialmente ostili.**

Per quel caso, nell’attesa delle correzioni, eseguirei l’intero ambiente di lavoro — inclusi Zellij e gli eventuali broker raggiungibili dall’agente — in una VM dedicata, con credenziali limitate, senza socket di controllo dell’host e con export selettivo dei risultati. Mettere solo il processo agente in una VM e poi restituirgli un’interfaccia che esegue comandi sull’host riproporrebbe lo stesso difetto.

Dopo la chiusura dei problemi P0, bwrap con una policy minima, namespace di rete, proxy ristretto e difese aggiuntive può offrire un contenimento utile e robusto contro molti comportamenti indesiderati. Rimarranno il kernel condiviso, il danno al workspace autorizzato, l’uso delle API consentite e il rischio di eseguire sull’host codice prodotto dall’agente. Sono limiti da rendere espliciti, non motivi per rinunciare al progetto.
