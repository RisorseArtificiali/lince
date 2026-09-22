# Handover: MCP per progetto e stato iniziale Codex in LINCE

Data: 19 settembre 2026. Documento destinato a un agente eseguito **fuori dalla sandbox**, sullo stesso host e con lo stesso utente.

## Esito dell'esecuzione (completata il 19 settembre 2026)

Il lavoro descritto sotto è stato completato e verificato sull'host. Questa sezione è il verbale finale; le sezioni successive conservano diagnosi e requisiti originali come traccia.

### Installato e configurato

- QMD MCP condiviso: `~/.local/share/qmd/node_modules/.bin/qmd`, pacchetto `@tobilu/qmd` 2.8.3 (`facd35e`). Il precedente symlink `~/.bun/bin/qmd` non è stato usato perché nella sandbox puntava a `~/node_modules`, nascosto dal relativo tmpfs.
- Serena condivisa: `~/.local/bin/serena`; la CLI riporta 1.7.0, mentre l'handshake MCP riporta server 1.28.1.
- Configurazioni Codex locali in `<repo>/.codex/config.toml` e Claude Code locali in `<repo>/.mcp.json`, per OneRing e langchain4j. Le definizioni QMD/Serena specifiche di OneRing sono state rimosse dalle configurazioni globali.
- QMD usa per ogni repository `.qmd/cache` come `XDG_CACHE_HOME` e `.qmd/config` come `QMD_CONFIG_DIR`; Serena usa `.serena/cache` come `SERENA_HOME`. Entrambi i server hanno `cwd` fissata al repository e Serena usa `--project-from-cwd --language-backend LSP`.
- Serena conserva la dashboard web ma non apre più il browser: tutte e quattro le definizioni locali includono `--open-web-dashboard false`. Questo evita nove finestre all'avvio simultaneo degli agenti senza disabilitare l'interfaccia HTTP.
- OneRing conserva le raccolte QMD per `.serena/memories`, `.reviews`, `untracked_doc` e `docs`, ora con percorsi relativi. Langchain4j indicizza `docs/**/*.md` e i Markdown nella root.
- Plugin, hook, observer, registry e runtime messaggi LINCE sono stati installati con `lince-dashboard/update.sh` e `lince-messages/install.sh --runtime-only`. È stato inoltre aggiunto `codex.PromptReady` agli eventi idle accettati da `lince-msg`: il test live aveva individuato che il dashboard mostrava `I`, ma il trasporto lasciava ancora il messaggio in coda.

Backup pre-migrazione: `~/.local/state/lince/backups/mcp-20260919T143236Z`. Contiene le configurazioni globali e locali precedenti, inclusi `~/.codex/config.toml`, `~/.claude.json`, configurazioni e indice OneRing, e gli exclude Git interessati.

### Matrice verificata

Versioni client: Codex CLI 0.155.1, Claude Code 2.1.278. Zellij 0.45.1.

| Repository | Client | Serena: progetto e simboli | QMD: indice e ricerca nota | Avvio da LINCE senza errori readonly |
| --- | --- | --- | --- | --- |
| OneRing | Codex | `LoopEngine` trovato nel modulo `onering-core` | `ADR-0028` restituisce `reviews/plans/issue-417-normalize-session-notions.md` | Sì, sandbox normale |
| OneRing | Claude Code | `LoopEngine` trovato nel progetto corretto | Stesso indice locale e stesso risultato noto | Sì, `--safe` |
| langchain4j | Codex | `AiMessage` trovato tramite backend Java LSP | `AI Services` restituisce `docs/docs/tutorials/ai-services.md` | Sì, sandbox normale |
| langchain4j | Claude Code | `AiMessage` trovato nel progetto corretto | Stesso indice locale; nessun risultato proveniente da OneRing | Sì, `--safe` |

Sono stati verificati handshake e tool call reali da entrambi i client. Due server QMD simultanei per repository hanno eseguito ricerche senza errori SQLite. Le quattro prove attraverso LINCE hanno confermato root in sola lettura, solo progetto corrente scrivibile, e nessun errore readonly di QMD o Serena.

### Stato iniziale Codex e messaggistica live

Su nuove sessioni Zellij isolate, sia in OneRing sia in langchain4j:

1. lo stato è passato da `codex.Starting` a `codex.PromptReady`, visualizzato come `I`, senza input manuale;
2. un peer ha inviato `Reply exactly LINCE_STARTUP_OK and nothing else.` tramite `lince-msg`;
3. Codex ha ricevuto il testo, eseguito la richiesta e risposto `LINCE_STARTUP_OK`;
4. gli hook hanno registrato `UserPromptSubmit`, `PreToolUse`/`PostToolUse`, `Stop` e `agent-turn-complete`, con ritorno allo stato `I`.

I file `.lince-dashboard` usati per le prove erano temporanei: quello originale di OneRing è stato ripristinato con hash identico e quello temporaneo di langchain4j è stato rimosso. Sono state chiuse solo le sessioni Zellij create per il test.

### Limiti residui non bloccanti

- OneRing ha embedding QMD già presenti ma anche chunk orfani; non è stato eseguito alcun cleanup distruttivo. Langchain4j ha ricerca lessicale funzionante ma non ha ancora embedding vettoriali: eseguire `qmd embed` solo se serve ricerca semantica e si accetta il download dei modelli.
- Un hook della shell esterno a LINCE tenta `python <repo>/ugv_ctl.py` a ogni login e stampa un errore perché il file manca. Non influenza MCP o dashboard.
- Il server Claude globale `tavily` osservato sull'host non si connette; è estraneo a Serena/QMD.

### Procedura per aggiungere un terzo repository

1. Creare `<repo>/.codex/config.toml` e `<repo>/.mcp.json`, usando gli stessi eseguibili condivisi indicati sopra e impostando `cwd` al nuovo repository.
2. Per QMD impostare `XDG_CACHE_HOME=<repo>/.qmd/cache` e `QMD_CONFIG_DIR=<repo>/.qmd/config`; inizializzare `.qmd/index.yml` con raccolte relative pertinenti e indicizzarle. Verificare una ricerca che restituisca un documento noto del nuovo repository.
3. Per Serena usare `start-mcp-server --project-from-cwd --context codex --language-backend LSP --open-web-dashboard false` in Codex e sostituire il contesto con `claude-code` in Claude. Impostare `SERENA_HOME=<repo>/.serena/cache` e creare/verificare `.serena/project.yml` con il linguaggio corretto.
4. Aggiungere `.codex/`, `.mcp.json`, `.qmd/` e `.serena/` a `.git/info/exclude` se la configurazione deve restare solo locale; usare `.gitignore` e commit soltanto se il team intende condividerla.
5. Rendere attendibile il progetto in Codex e approvare i due MCP di progetto in Claude Code. Controllare con `codex mcp list`, `claude mcp get serena` e `claude mcp get qmd`.
6. Provare un simbolo reale con Serena e un documento noto con QMD, prima direttamente e poi da una nuova istanza LINCE con il livello sandbox normale. Infine inviare un messaggio `lince-msg` alla nuova istanza mentre mostra `I`.

<details>
<summary>Handover originario precedente all'esecuzione (archivio)</summary>

> **Nota storica:** tutto ciò che segue descrive lo stato precedente al lavoro. Le formule “da verificare”, “non installato” e le istruzioni al futuro sono obsolete; il solo stato operativo corrente è nel verbale finale sopra.

## Obiettivo e ambito

Rendere Serena e QMD utilizzabili da più progetti, con configurazioni e dati appropriati al progetto corrente, ed eliminare gli errori di avvio MCP dovuti a directory in sola lettura. Completare inoltre la correzione dello stato iniziale Codex in LINCE: deve diventare `I` quando il prompt è pronto, così da ricevere messaggi tramite `lince-msg` senza un primo intervento manuale.

Repository su cui configurare e verificare entrambi gli MCP:

- `~/project/Prince/OneRing`
- `~/project/langchain4j`

Verificare entrambi i client, **Codex e Claude Code**, su entrambi i repository. Verificare anche l'avvio attraverso LINCE con il livello sandbox effettivamente usato: il fatto che un MCP funzioni direttamente dall'host non dimostra che funzioni nella sandbox.

Il repository del codice LINCE è `~/project/lince`. Non sono stati inviati messaggi ad altri agenti: questo file è il passaggio di consegne.

## Diagnosi già confermata

La configurazione globale `~/.codex/config.toml` contiene questi riferimenti specifici a OneRing:

```toml
[mcp_servers.qmd]
command = "/home/maeste/project/Prince/OneRing/.qmd/tool/node_modules/.bin/qmd"
args = ["mcp"]

[mcp_servers.qmd.env]
XDG_CACHE_HOME = "/home/maeste/project/Prince/OneRing/.qmd/cache"

[mcp_servers.serena]
command = "/home/maeste/.local/bin/serena"
args = ["start-mcp-server", "--project", "/home/maeste/project/Prince/OneRing", "--context", "codex"]

[mcp_servers.serena.env]
SERENA_HOME = "/home/maeste/project/Prince/OneRing/.serena/cache"
```

Nella sessione LINCE sul repository `lince`, `/proc/self/mountinfo` mostrava:

- `~/project` in sola lettura, con il solo progetto corrente `~/project/lince` rimontato scrivibile;
- `~/.codex` già scrivibile;
- `~/.local` e `~/.cache` in sola lettura.

Quindi la precedente correzione che rende `.codex` scrivibile è ancora presente. Gli errori qui riguardano dati MCP collocati in un **altro progetto**, OneRing.

Avviando direttamente i comandi MCP con gli stessi argomenti e variabili della configurazione Codex, sono stati riprodotti:

- QMD: `SqliteError: unable to open database file`, codice `SQLITE_CANTOPEN`.
- Serena: `OSError: [Errno 30] Read-only file system` durante la creazione di `/home/maeste/project/Prince/OneRing/.serena/cache/logs/2026-09-19`.

Nessuna configurazione MCP globale o dei due repository è stata modificata durante questa diagnosi.

## Configurazione MCP da realizzare

Codex supporta configurazioni locali `<repository>/.codex/config.toml` per i progetti attendibili, oltre a `~/.codex/config.toml`. Sono disponibili le opzioni MCP `command`, `args`, `env`, `cwd`, `enabled` e i timeout. Riferimento ufficiale verificato: <https://developers.openai.com/codex/mcp/>.

1. Fare un inventario e un backup delle configurazioni esistenti prima della migrazione, conservando impostazioni, hook e server estranei a questo lavoro.
2. Separare **installazione degli eseguibili**, condivisa, da **configurazione, indici, cache e log**, con percorsi scrivibili e corretti per ciascun progetto.
3. Rimuovere dalla configurazione globale Codex il vincolo a OneRing, trasferendo le definizioni specifiche nelle configurazioni locali dei due repository. Controllare la configurazione effettivamente risultante: un override parziale non deve lasciare variabili o argomenti globali diretti a OneRing.
4. Allineare le configurazioni locali Claude e Codex per usare gli stessi dati di progetto dove compatibile, mantenendo eventuali differenze necessarie negli argomenti del client.
5. Evitare di rendere scrivibili indiscriminatamente la home o tutti i repository. Per gli altri repository senza configurazione locale, Codex non deve più avviare accidentalmente i server dedicati a OneRing.
6. Lasciare una breve procedura ripetibile per abilitare Serena e QMD su un nuovo repository.

### Serena

- L'eseguibile già installato è `~/.local/bin/serena`.
- `serena start-mcp-server --help` conferma il supporto a `--project-from-cwd`: cerca il progetto nell'antenato più vicino con `.serena/project.yml` o `.git`. È una possibilità per una configurazione riutilizzabile; verificare sempre la directory di lavoro effettiva del processo MCP.
- In alternativa usare un percorso esplicito nella configurazione locale di ciascun repository.
- Per Codex è attualmente usato `--context codex`. Claude OneRing usa `--context ide-assistant`; valutare la compatibilità prima di uniformare.
- `SERENA_HOME` controlla anche la posizione di configurazione e log. Verificare inoltre cache e download dei language server, in particolare quello Java: il solo handshake MCP non basta.
- Accertarsi che il progetto Java sia configurato con il backend/language server corretto e che le operazioni sui simboli funzionino realmente.

### QMD: attenzione all'omonimia degli eseguibili

- Il QMD usato attualmente come MCP è quello JavaScript in `OneRing/.qmd/tool/node_modules/.bin/qmd`, pacchetto `@tobilu/qmd`.
- `command -v qmd` restituisce invece `~/.cargo/bin/qmd`: il suo `--help` mostra un'altra CLI, senza sottocomando `mcp`. **Non sostituire il percorso del server con il semplice nome `qmd` senza verificare quale eseguibile venga risolto.**
- Installare o individuare una versione MCP compatibile in una posizione condivisa leggibile dalla sandbox, senza dipendere dall'installazione interna a OneRing. Registrare versione e percorso scelti.
- Nel codice della versione JavaScript esistente, `XDG_CACHE_HOME` determina il percorso predefinito `<cache>/qmd/index.sqlite`; esistono anche `INDEX_PATH` e `QMD_CONFIG_DIR`. Queste sono osservazioni sulla versione installata: confermarle sulla versione scelta.
- OneRing contiene sia `.qmd/index.sqlite` sia `.qmd/cache/`, oltre a `.qmd/index.yml`. Identificare quale indice venga realmente usato e preservare i dati prima di spostare o ricostruire qualcosa.
- `.qmd/index.yml` elenca raccolte per `.serena/memories`, `.reviews`, `untracked_doc` e `docs`, con percorsi assoluti di OneRing. Conservare la copertura utile esistente.
- Definire raccolte pertinenti a langchain4j senza ereditare i percorsi di OneRing. Indicizzare i documenti scelti e verificare una ricerca con un risultato noto; un server che parte con un indice vuoto non soddisfa l'obiettivo.
- Se entrambi i client condividono lo stesso indice, verificare il funzionamento concorrente e l'assenza di errori SQLite.

### Configurazione Claude osservata

`OneRing/.mcp.json` contiene:

- QMD: eseguibile sotto `.qmd/tool`, argomento `mcp`, `XDG_CACHE_HOME` sotto `.qmd/cache`.
- Serena: `~/.local/bin/uvx --from git+https://github.com/oraios/serena serena start-mcp-server --context ide-assistant --project /home/maeste/project/Prince/OneRing`, senza variabili `env` specifiche.

Quindi Claude e Codex potrebbero usare versioni/installazioni Serena diverse. Verificare e rendere la scelta riproducibile.

Alla lettura effettuata durante l'handover non risultavano presenti `.mcp.json`, `.codex`, `.serena` o `.qmd` in langchain4j, né `.codex` in OneRing. Ricontrollare sul filesystem host e ispezionare anche eventuali configurazioni Claude globali prima di dedurre che manchino integrazioni.

## Correzione dello stato iniziale Codex già preparata

Le modifiche seguenti sono **nel working tree di `~/project/lince`, non installate e non committate**:

- Nuovo `lince-dashboard/hooks/lince-codex-startup`, derivato dall'osservatore iniziale Bob.
- `lince-dashboard/plugin/src/agent.rs`: avvio dell'osservatore anche per Codex, prima del comando agente/sandbox.
- `lince-dashboard/hooks/codex-status-hook.sh`: scrittura dello stato coordinata con l'osservatore tramite lock, prima dell'invio della pipe.
- `lince-dashboard/hooks/install-codex-hooks.sh` e `lince-dashboard/uninstall.sh`: installazione/rimozione del nuovo eseguibile.
- `lince-dashboard/agents-defaults.toml` e `registry.d/codex.toml`: `codex.Starting → unknown`, `codex.PromptReady → input`.
- Nuovo `lince-dashboard/tests/test_codex_startup.py`, aggiornamento di `test_codex_hooks.py` e del README dashboard.

L'osservatore riconosce una sola volta il composer vuoto, quindi lascia gli stati successivi agli hook nativi. Un hook nativo già arrivato prevale sull'osservazione del prompt. Il parser è basato sul prompt **Codex 0.155.1** osservato realmente in PTY (`› Ask Codex to do anything`): per layout sconosciuti resta conservativamente `-` finché non arriva un hook.

Prima di installare, revisionare anche il comportamento in pane piccoli, con footer personalizzato e durante l'avvio MCP: il parser dipende dal testo visibile. L'integrazione completa con Zellij e `lince-msg` **non è ancora stata verificata dal vivo**.

Verifiche già superate:

```bash
python3 -m unittest discover -s lince-dashboard/tests -p 'test_codex*.py'
python3 -m unittest discover -s lince-dashboard/tests -p 'test_bob_startup.py'
python3 -m unittest discover -s lince-dashboard/tests -p 'test_peer_status_hooks.py'
python3 -m unittest discover -s scripts/tests -p 'test_registry_sync.py'
cargo check --manifest-path lince-dashboard/plugin/Cargo.toml --tests
git diff --check
```

Totale: 21 test Python superati. Il controllo Rust è passato; non equivale all'esecuzione dei test Rust.

Tentativi non riusciti nell'ambiente sandbox:

- Test Rust sul target nativo: linker senza simbolo Zellij `host_run_plugin_command`. Il repository dispone della procedura corretta `bash lince-dashboard/tests/run-plugin-tests.sh`, basata su WASI, wasmtime e stub host.
- Build `bash lince-dashboard/plugin/build.sh`: rustup non aveva una toolchain predefinita accessibile e mancava il target WASM in quell'ambiente. Verificare prima la toolchain già presente sull'host.
- Installazione non effettuata: `~/.local` era montata readonly e la sessione Zellij host non era raggiungibile dal comando di prova nella sandbox.

Fuori dalla sandbox, completare build e test con la procedura del repository, aggiornare plugin, hook e registry insieme (vedere `lince-dashboard/update.sh`), quindi ricaricare il dashboard e avviare nuove istanze. Non basta copiare solo lo script dell'osservatore. Verificare inoltre in Codex lo stato di trust degli hook aggiornati tramite `/hooks`; l'installer preserva la configurazione ma non equivale alla loro autorizzazione.

Il working tree contiene anche modifiche preesistenti al backlog, estranee a questo lavoro. Non ripristinarle e non includerle in eventuali commit dedicati.

## Verifiche di accettazione

Compilare questa matrice con versione dei client/server, configurazione effettiva, percorsi dati e risultati:

| Repository | Client | Serena: progetto e simboli | QMD: indice e ricerca nota | Avvio da LINCE senza errori readonly |
| --- | --- | --- | --- | --- |
| OneRing | Codex | Da verificare | Da verificare | Da verificare |
| OneRing | Claude Code | Da verificare | Da verificare | Da verificare |
| langchain4j | Codex | Da verificare | Da verificare | Da verificare |
| langchain4j | Claude Code | Da verificare | Da verificare | Da verificare |

Per ciascuna combinazione:

1. Controllare il caricamento della configurazione locale, l'avvio e l'handshake di entrambi i server.
2. Verificare con Serena il progetto attivo e una ricerca/lettura di un simbolo noto; su langchain4j deve funzionare l'analisi Java.
3. Cercare con QMD un documento noto del repository e verificare il percorso restituito. I risultati di langchain4j non devono provenire accidentalmente dall'indice OneRing.
4. Verificare dove vengono scritti cache, log e database, compreso l'avvio dei language server.
5. Ripetere attraverso LINCE nella sandbox d'uso normale dell'utente e verificare eventuale uso simultaneo dei due client.

Per lo stato Codex, su entrambi i repository:

1. Aprire una nuova istanza senza inviarle prompt. Lo stato può essere `-` durante l'inizializzazione; deve diventare `I` quando il composer è pronto.
2. Inviare un messaggio di prova tramite `lince-msg` a **quella nuova istanza** e verificare ricezione ed elaborazione senza intervento manuale preliminare.
3. Controllare il passaggio allo stato di lavoro e il ritorno a `I`; verificare che l'osservatore iniziale non sovrascriva uno stato nativo successivo.
4. Controllare che dialoghi iniziali, caricamento e prompt già compilati non producano un falso `I`.

Riportare alla fine modifiche effettivamente installate, risultati della matrice, eventuali limiti residui, riavvii necessari e istruzioni per aggiungere un terzo repository. Distinguere sempre configurazione preparata, installazione completata e verifica dal vivo.

</details>
