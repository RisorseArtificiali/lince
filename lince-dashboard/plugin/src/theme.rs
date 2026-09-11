//! Palette shared by every LINCE renderer. Zellij remains responsible for pane frames.
use std::cell::RefCell;
use zellij_tile::prelude::{PaletteColor, Style};
use crate::types::AgentStatus;

#[derive(Clone, Debug)]
pub struct Palette {
    // black, red/permission, green/running, yellow/input, blue/header,
    // magenta/group, cyan/accent, white/text, gray/unknown.
    pub colors: [PaletteColor; 9],
}

impl Palette {
    pub fn resolve(name: &str, inherited: Option<Style>) -> Self {
        use PaletteColor::{EightBit as I, Rgb as R};
        let colors = match name {
            "minimal-mono" => [I(0), I(7), I(7), I(7), I(7), I(7), I(7), I(7), I(8)],
            "dracula" => [R((40,42,54)), R((255,85,85)), R((80,250,123)), R((241,250,140)),
                R((189,147,249)), R((255,121,198)), R((139,233,253)), R((248,248,242)), R((98,114,164))],
            "gruvbox" => [R((40,40,40)), R((251,73,52)), R((184,187,38)), R((250,189,47)),
                R((131,165,152)), R((211,134,155)), R((142,192,124)), R((235,219,178)), R((146,131,116))],
            _ => if let Some(style) = inherited {
                let c = style.colors;
                [c.text_unselected.background, c.exit_code_error.base, c.exit_code_success.base,
                    c.text_unselected.emphasis_0, c.table_title.base, c.text_unselected.emphasis_3,
                    c.text_unselected.emphasis_1, c.text_unselected.base, c.text_unselected.base]
            } else { [I(0), I(1), I(2), I(3), I(4), I(5), I(6), I(7), I(8)] },
        };
        Self { colors }
    }
}

thread_local! {
    // Render-scoped palette: the WASM plugin is single-threaded. Passive surfaces
    // have separate WASM instances and therefore their own palette.
    static CURRENT: RefCell<Palette> = RefCell::new(Palette::resolve("default", None));
}

pub fn known(name: &str) -> bool {
    matches!(name, "default" | "minimal-mono" | "dracula" | "gruvbox")
}
pub fn set(name: &str, inherited: Option<Style>) {
    CURRENT.with(|p| *p.borrow_mut() = Palette::resolve(name, inherited));
}
fn ansi(color: PaletteColor, background: bool) -> String {
    let code = if background { 48 } else { 38 };
    match color {
        PaletteColor::Rgb((r,g,b)) => format!("\x1b[{code};2;{r};{g};{b}m"),
        PaletteColor::EightBit(i) => format!("\x1b[{code};5;{i}m"),
    }
}
fn index(name: &str) -> usize {
    match name { "black" => 0, "red" => 1, "green" => 2, "yellow" => 3,
        "blue" => 4, "magenta" => 5, "cyan" => 6, "gray" => 8, _ => 7 }
}
pub fn color(name: &str) -> String {
    CURRENT.with(|p| ansi(p.borrow().colors[index(name)], false))
}
pub fn selection() -> String {
    CURRENT.with(|p| {
        let p = p.borrow();
        format!("{}{}", ansi(p.colors[0], false), ansi(p.colors[6], true))
    })
}
pub fn group(i: usize) -> String {
    color(["blue", "magenta", "cyan", "green", "yellow", "red"][i % 6])
}
pub fn status(status: &AgentStatus) -> String {
    color(match status {
        AgentStatus::Running => "green", AgentStatus::WaitingForInput => "yellow",
        AgentStatus::PermissionRequired => "red", AgentStatus::Unknown => "gray",
        AgentStatus::Stopped => "gray",
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn presets_and_inheritance() {
        assert!(known("default") && known("minimal-mono") && known("dracula") && known("gruvbox"));
        assert!(!known("typo"));
        let mut style = Style::default();
        style.colors.text_unselected.emphasis_1 = PaletteColor::Rgb((1,2,3));
        assert_eq!(Palette::resolve("default", Some(style)).colors[6], PaletteColor::Rgb((1,2,3)));
        assert_eq!(Palette::resolve("typo", Some(style)).colors[6], PaletteColor::Rgb((1,2,3)));
        let mono = Palette::resolve("minimal-mono", None);
        assert_eq!(mono.colors[1], mono.colors[2]);
        assert_ne!(Palette::resolve("dracula", None).colors[1], Palette::resolve("gruvbox", None).colors[1]);
    }
}
