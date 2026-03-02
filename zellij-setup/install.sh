#!/bin/bash

set -e

# Colori per output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FILES_DIR="$SCRIPT_DIR/configs"

echo -e "${BLUE}================================================${NC}"
echo -e "${BLUE}   Setup Zellij Configuration di Stefano${NC}"
echo -e "${BLUE}================================================${NC}"
echo ""

# Funzione per pause interattive
pause() {
    echo -e "${YELLOW}$1${NC}"
    read -p "Premi INVIO per continuare..."
    echo ""
}

# Funzione per conferma
confirm() {
    read -p "$1 (y/n): " -n 1 -r
    echo
    [[ $REPLY =~ ^[Yy]$ ]]
}

# Step 1: Controllo/Installazione Zellij
echo -e "${GREEN}[1/7] Controllo installazione Zellij...${NC}"

if command -v zellij >/dev/null 2>&1; then
    ZELLIJ_VERSION=$(zellij --version | awk '{print $2}')
    echo -e "${GREEN}✓ Zellij già installato (versione $ZELLIJ_VERSION)${NC}"
else
    echo -e "${YELLOW}⚠ Zellij non trovato${NC}"
    echo ""
    echo "Zellij non è installato. Vuoi installarlo ora?"
    echo ""
    echo "Metodi disponibili:"
    echo "  1) Da Fedora repos (dnf install zellij)"
    echo "  2) Da Cargo (cargo install --locked zellij) - RACCOMANDATO"
    echo "  3) Binary precompilato (scarica da GitHub)"
    echo "  4) Manualmente (esco e lo installi tu)"
    echo ""
    read -p "Scegli (1/2/3/4): " -n 1 -r INSTALL_METHOD
    echo ""
    echo ""
    
    case $INSTALL_METHOD in
        1)
            echo "Installazione da dnf..."
            # Target: Fedora/RHEL
            # Per Ubuntu/Debian usa: sudo apt-get install -y zellij
            if ! sudo dnf install -y zellij; then
                echo -e "${RED}✗ Installazione fallita${NC}"
                echo "Prova un altro metodo o installa manualmente"
                exit 1
            fi
            ;;
        2)
            echo "Installazione da Cargo..."
            echo ""
            
            # Step 2a: Installa Cargo se necessario
            if ! command -v cargo >/dev/null 2>&1; then
                echo -e "${YELLOW}Cargo non trovato. Installo Rust toolchain...${NC}"
                
                # Installa rustup
                curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
                
                # Carica l'ambiente cargo
                source "$HOME/.cargo/env"
                
                if command -v cargo >/dev/null 2>&1; then
                    echo -e "${GREEN}✓ Rust/Cargo installato${NC}"
                else
                    echo -e "${RED}✗ Installazione Rust fallita${NC}"
                    exit 1
                fi
            else
                echo -e "${GREEN}✓ Cargo già presente${NC}"
            fi
            echo ""
            
            # Step 2b: Installa dipendenze per compilazione
            echo "Installazione dipendenze di compilazione..."
            
            # Target: Fedora/RHEL
            # perl-IPC-Cmd: Modulo Perl necessario per zellij build
            # perl-core: Core Perl modules
            # openssl-devel: OpenSSL development files
            if sudo dnf install -y perl-IPC-Cmd perl-core openssl-devel; then
                echo -e "${GREEN}✓ Dipendenze installate (Fedora/RHEL)${NC}"
            else
                echo -e "${RED}✗ Errore installazione dipendenze${NC}"
                echo ""
                echo "Se sei su Ubuntu/Debian, prova manualmente:"
                echo "  sudo apt-get install -y perl libssl-dev build-essential"
                echo ""
                if ! confirm "Vuoi continuare comunque con la compilazione?"; then
                    exit 1
                fi
            fi
            
            # Alternative per Ubuntu/Debian (commento per riferimento):
            # sudo apt-get install -y perl libssl-dev build-essential
            
            echo ""
            
            # Step 2c: Compila e installa Zellij
            echo "Compilazione Zellij in corso..."
            echo "⚠ Questo può richiedere 5-10 minuti..."
            echo ""
            
            if cargo install --locked zellij; then
                echo -e "${GREEN}✓ Zellij compilato e installato${NC}"
                
                # Verifica che sia nel PATH
                if ! command -v zellij >/dev/null 2>&1; then
                    echo ""
                    echo -e "${YELLOW}⚠ Zellij installato ma non nel PATH${NC}"
                    echo "Aggiungi questa linea al tuo ~/.bashrc o ~/.zshrc:"
                    echo "  export PATH=\"\$HOME/.cargo/bin:\$PATH\""
                    echo ""
                    echo "Oppure ricarica l'ambiente:"
                    source "$HOME/.cargo/env"
                fi
            else
                echo -e "${RED}✗ Compilazione fallita${NC}"
                echo ""
                echo "Suggerimenti:"
                echo "  1. Verifica connessione internet"
                echo "  2. Prova il binary precompilato (opzione 3)"
                echo "  3. Controlla i log sopra per errori specifici"
                exit 1
            fi
            ;;
        3)
            echo "Download binary precompilato..."
            cd /tmp
            curl -L https://github.com/zellij-org/zellij/releases/latest/download/zellij-x86_64-unknown-linux-musl.tar.gz -o zellij.tar.gz
            tar -xzf zellij.tar.gz
            sudo mv zellij /usr/local/bin/
            sudo chmod +x /usr/local/bin/zellij
            rm zellij.tar.gz
            cd "$SCRIPT_DIR"
            echo -e "${GREEN}✓ Binary installato in /usr/local/bin/zellij${NC}"
            ;;
        4)
            echo -e "${YELLOW}Ok, installa Zellij manualmente e poi rilancia questo script${NC}"
            echo ""
            echo "Comandi suggeriti:"
            echo ""
            echo "Metodo 1 - Cargo (raccomandato):"
            echo "  curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh"
            echo "  source \$HOME/.cargo/env"
            echo "  # Fedora/RHEL:"
            echo "  sudo dnf install -y perl-IPC-Cmd perl-core openssl-devel"
            echo "  # Ubuntu/Debian:"
            echo "  # sudo apt-get install -y perl libssl-dev build-essential"
            echo "  cargo install --locked zellij"
            echo ""
            echo "Metodo 2 - Package manager:"
            echo "  # Fedora:"
            echo "  sudo dnf install zellij"
            echo "  # Ubuntu (22.04+):"
            echo "  # sudo apt-get install zellij"
            echo ""
            exit 0
            ;;
        *)
            echo -e "${RED}Opzione non valida${NC}"
            exit 1
            ;;
    esac
    
    # Verifica installazione finale
    # Ricarica environment per cargo
    if [ -f "$HOME/.cargo/env" ]; then
        source "$HOME/.cargo/env"
    fi
    
    if command -v zellij >/dev/null 2>&1; then
        ZELLIJ_VERSION=$(zellij --version | awk '{print $2}')
        echo -e "${GREEN}✓ Zellij installato con successo! (versione $ZELLIJ_VERSION)${NC}"
    else
        echo -e "${RED}✗ Zellij non trovato nel PATH dopo l'installazione${NC}"
        echo ""
        echo "Prova:"
        echo "  source ~/.cargo/env"
        echo "  zellij --version"
        echo ""
        exit 1
    fi
fi
echo ""

# Step 2: Backup configurazione esistente
echo -e "${GREEN}[2/7] Backup configurazione esistente...${NC}"

if [ -d ~/.config/zellij ]; then
    BACKUP_DIR=~/.config/zellij.backup.$(date +%Y%m%d_%H%M%S)
    echo "Trovata configurazione esistente, creo backup..."
    cp -r ~/.config/zellij "$BACKUP_DIR"
    echo -e "${GREEN}✓ Backup salvato in: $BACKUP_DIR${NC}"
else
    echo "Nessuna configurazione esistente trovata"
fi
echo ""

# Step 3: Crea directory
echo -e "${GREEN}[3/7] Creazione directory...${NC}"
mkdir -p ~/.config/zellij/layouts
echo -e "${GREEN}✓ Directory create${NC}"
echo ""

# Step 4: Copia file di configurazione
echo -e "${GREEN}[4/7] Installazione file di configurazione...${NC}"

# Config principale
cp "$FILES_DIR/config.kdl" ~/.config/zellij/config.kdl
echo -e "${GREEN}✓ config.kdl installato${NC}"

# Layouts
cp "$FILES_DIR/three-pane.kdl" ~/.config/zellij/layouts/three-pane.kdl
echo -e "${GREEN}✓ three-pane.kdl installato${NC}"

cp "$FILES_DIR/three-pane-zai.kdl" ~/.config/zellij/layouts/three-pane-zai.kdl
echo -e "${GREEN}✓ three-pane-zai.kdl installato${NC}"

cp "$FILES_DIR/three-pane-mm.kdl" ~/.config/zellij/layouts/three-pane-mm.kdl
echo -e "${GREEN}✓ three-pane-mm.kdl installato${NC}"

cp "$FILES_DIR/three-pane-vertex.kdl" ~/.config/zellij/layouts/three-pane-vertex.kdl
echo -e "${GREEN}✓ three-pane-vertex.kdl installato${NC}"

# Verifica sintassi
echo "Verifico sintassi configurazione..."
if zellij setup --check >/dev/null 2>&1; then
    echo -e "${GREEN}✓ Configurazione valida${NC}"
else
    echo -e "${RED}✗ Errore nella configurazione${NC}"
    echo "Controlla manualmente con: zellij setup --check"
    exit 1
fi
echo ""

# Step 5: Verifica comandi utilizzati nei layout
echo -e "${GREEN}[5/7] Verifica comandi nei layout...${NC}"

MISSING_COMMANDS=()

if ! command -v claude >/dev/null 2>&1; then
    MISSING_COMMANDS+=("claude")
fi

if ! command -v zai-claude >/dev/null 2>&1; then
    MISSING_COMMANDS+=("zai-claude")
fi

if ! command -v backlog >/dev/null 2>&1; then
    MISSING_COMMANDS+=("backlog")
fi

if [ ${#MISSING_COMMANDS[@]} -gt 0 ]; then
    echo -e "${YELLOW}⚠ Comandi non trovati nel PATH:${NC}"
    for cmd in "${MISSING_COMMANDS[@]}"; do
        echo "  - $cmd"
    done
    echo ""
    echo "I layout li usano ma non sono installati."
    echo "Puoi:"
    echo "  1. Installarli prima di usare i layout"
    echo "  2. Modificare i layout in ~/.config/zellij/layouts/"
    echo "  3. Ignorare (i pannelli mostreranno errore ma Zellij funzionerà)"
    echo ""
    
    if ! confirm "Vuoi continuare comunque?"; then
        echo "Setup interrotto. Installa i comandi mancanti e rilancia lo script."
        exit 0
    fi
else
    echo -e "${GREEN}✓ Tutti i comandi trovati${NC}"
fi
echo ""

# Step 6: Setup aliases
echo -e "${GREEN}[6/7] Configurazione aliases...${NC}"

# Bash
if [ -f ~/.bashrc ]; then
    if grep -q "# Zellij aliases" ~/.bashrc 2>/dev/null; then
        echo -e "${YELLOW}⚠ Aliases già presenti in .bashrc${NC}"
    else
        echo "" >> ~/.bashrc
        cat "$FILES_DIR/zellij-aliases.sh" >> ~/.bashrc
        echo -e "${GREEN}✓ Aliases aggiunti a .bashrc${NC}"
    fi
else
    echo -e "${YELLOW}⚠ .bashrc non trovato${NC}"
fi

# Zsh (se presente)
if [ -f ~/.zshrc ]; then
    if confirm "Rilevato .zshrc. Vuoi aggiungere gli aliases anche lì?"; then
        if ! grep -q "# Zellij aliases" ~/.zshrc; then
            echo "" >> ~/.zshrc
            cat "$FILES_DIR/zellij-aliases.sh" >> ~/.zshrc
            echo -e "${GREEN}✓ Aliases aggiunti a .zshrc${NC}"
        else
            echo -e "${YELLOW}⚠ Aliases già presenti in .zshrc${NC}"
        fi
    fi
fi
echo ""

# Step 7: Test configurazione
echo -e "${GREEN}[7/7] Test configurazione...${NC}"

echo "Testo avvio Zellij..."
# Test avvio/chiusura veloce
if timeout 5 zellij -s test-install --layout default 2>&1 | grep -q "Welcome" || true; then
    # Killa la sessione di test
    zellij delete-session test-install 2>/dev/null || true
    echo -e "${GREEN}✓ Zellij si avvia correttamente${NC}"
else
    echo -e "${YELLOW}⚠ Test non conclusivo (potrebbe essere OK comunque)${NC}"
fi

# Lista layouts disponibili
echo ""
echo "Layouts disponibili:"
ls -1 ~/.config/zellij/layouts/ | sed 's/^/  - /'
echo ""

# Installazione completata
echo -e "${BLUE}================================================${NC}"
echo -e "${BLUE}   Installazione Completata!${NC}"
echo -e "${BLUE}================================================${NC}"
echo ""
echo -e "${GREEN}Configurazione installata:${NC}"
echo "  ~/.config/zellij/config.kdl"
echo "  ~/.config/zellij/layouts/three-pane.kdl"
echo "  ~/.config/zellij/layouts/three-pane-zai.kdl"
echo "  ~/.config/zellij/layouts/three-pane-mm.kdl"
echo "  ~/.config/zellij/layouts/three-pane-vertex.kdl"
echo ""
echo -e "${GREEN}Aliases disponibili (riavvia terminale o source ~/.bashrc):${NC}"
echo "  z       - Avvia Zellij"
echo "  z3      - Avvia con layout three-pane"
echo "  zz3     - Avvia con layout three-pane-zai"
echo "  zn      - Attach a sessione esistente o crea nuova"
echo ""
echo -e "${GREEN}Caratteristiche della configurazione:${NC}"
echo "  ✓ Keybindings personalizzati (Ctrl+O disabilitato)"
echo "  ✓ Theme Dracula"
echo "  ✓ Copy-on-select attivo"
echo "  ✓ Scrollback buffer: 10000 linee"
echo "  ✓ Layout default: three-pane"
echo ""
echo -e "${GREEN}Layout three-pane:${NC}"
echo "  - Pane superiore (50%): lancia 'claude'"
echo "  - Pane inferiore sx (25%): lancia 'backlog board'"
echo "  - Pane inferiore dx (25%): shell libera"
echo ""
echo -e "${GREEN}Layout three-pane-zai:${NC}"
echo "  - Pane superiore (50%): lancia 'zai-claude'"
echo "  - Pane inferiore sx (25%): lancia 'backlog board'"
echo "  - Pane inferiore dx (25%): shell libera"
echo ""
echo -e "${YELLOW}Note importanti:${NC}"
echo "  • Ctrl+O è disabilitato (per focus-mode)"
echo "  • Per session mode usa: Ctrl+g poi i comandi session"
echo "  • Alt+frecce per navigare tra panes"
echo "  • Ctrl+t per tab mode, Ctrl+p per pane mode"
echo ""
echo -e "${GREEN}Quick test:${NC}"
echo "  # Ricarica shell"
echo "  source ~/.bashrc"
echo ""
echo "  # Prova i layout"
echo "  z3         # Layout con claude"
echo "  zz3        # Layout con zai-claude"
echo ""
echo -e "${YELLOW}Se i comandi (claude, zai-claude, backlog) non sono disponibili:${NC}"
echo "  I layout mostreranno un errore ma Zellij funzionerà."
echo "  Puoi modificare i layout in: ~/.config/zellij/layouts/"
echo "  Oppure installare i comandi mancanti."
echo ""

if [ ${#MISSING_COMMANDS[@]} -gt 0 ]; then
    echo -e "${YELLOW}⚠ Reminder: Questi comandi non sono installati:${NC}"
    for cmd in "${MISSING_COMMANDS[@]}"; do
        echo "  - $cmd"
    done
    echo ""
fi

echo -e "${GREEN}Happy terminal multiplexing! 🚀${NC}"
