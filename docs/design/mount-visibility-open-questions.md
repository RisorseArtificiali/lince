# Visibilità dei mount LINCE — punti da riprendere

## Domanda 4: mount annidati nella workdir e comportamento della home

**Da riprendere in un altro lavoro, non come blocco della v1.** Inizialmente era stata proposta una verifica dei mount annidati nella workdir per evitare che riesponessero contenuti protetti di `Dati`. La verifica del codice installato `~/.local/bin/agent-sandbox` mostra che oggi il builder bwrap maschera `$HOME` con `--tmpfs` e poi rimonta il progetto con `--bind`, ma non controlla i mount annidati nella workdir (sezioni 3 e 6 di `build_bwrap_cmd`). L'utente ha poi chiarito che la feature richiesta deve offrire lo stesso livello di sicurezza attuale della home: **la v1 non aggiunge questo controllo**. Valutare in futuro se rafforzare il trattamento dei mount annidati per tutte le maschere.

La decisione provvisoria della domanda 5 (verificare solo gli aggiramenti di `Dati`, non altri filesystem) è stata superata dalla successiva riduzione del perimetro alla parità con la home.

## Enhancement separato: integrità generale della configurazione LINCE

**Effort successivo, separato dal masking dei mount.** Oggi `agent-sandbox learn` monta l'intera `$HOME` in lettura/scrittura (`build_learn_bwrap_cmd`), rendendo modificabili da un agente sandboxato anche `~/.agent-sandbox/config.toml` e `~/.config/lince/lince.toml`. Anche una workdir che include quei file, o un bind scrivibile esplicito, può riesporli. La protezione dei file di policy e dell'implementazione LINCE contro modifiche capaci di alterare le *esecuzioni future* è un problema generale preesistente. L'utente vuole trattare tutte queste garanzie in un effort dedicato successivo, non nella prima versione del masking. Nella v1 la lista globale dei mount da mascherare non è definibile o sostituibile da un file locale; altri bind seguono però le normali regole di precedenza, come per la home. Nessuna implementazione è stata richiesta ora.

## Enhancement separato: garanzie forti sui mount mascherati, inclusa la home

**Da affrontare in un altro lavoro, non nella feature opt-in attuale.** La maschera `--tmpfs` protegge il percorso su cui è applicata; non scopre automaticamente bind alias completi o parziali dello stesso contenuto, né il percorso sorgente ordinario di un mount creato tramite bind. La home mascherata attualmente ha il medesimo limite. Con propagazione dei mount dall'host, nuovi bind alias possono diventare visibili anche dopo l'avvio. Lo [spike sintetico](../history/mount-visibility-spike-2026-10-19.md) riproduce entrambi i casi e mostra che un namespace privato evita il secondo nella fixture. Valutare eventualmente una garanzia più forte **per tutte le maschere, home inclusa**, con scoperta degli alias e isolamento dei mount futuri. Non è un prerequisito della v1 richiesta dall'utente, che si accontenta della sicurezza di alto livello oggi fornita dalla home.
