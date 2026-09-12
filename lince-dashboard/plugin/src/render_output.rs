//! Render the same dashboard into a popup without duplicating its controller.
use std::cell::RefCell;
use std::fmt::{Arguments, Write};
thread_local! { static FRAME: RefCell<Option<String>> = const { RefCell::new(None) }; }
pub fn write(args: Arguments<'_>) {
    FRAME.with(|frame| {
        if let Some(frame) = frame.borrow_mut().as_mut() {
            let _ = frame.write_fmt(args);
        } else { print!("{args}"); }
    });
}
pub fn capture(render: impl FnOnce()) -> String {
    FRAME.with(|frame| *frame.borrow_mut() = Some(String::new()));
    render();
    FRAME.with(|frame| frame.borrow_mut().take().unwrap_or_default())
}

/// Draw our own border so popup outlines remain visible with pane_frames=false.
pub fn bordered(rows: usize, cols: usize, title: &str, render: impl FnOnce(usize, usize)) -> String {
    use unicode_width::UnicodeWidthChar;
    if rows < 2 || cols < 2 { return String::new(); }
    let width = cols - 2;
    let content = capture(|| render(rows - 2, width));
    let title = crate::dashboard::clip_cells(&format!(" {title} "), width);
    let title_width = title.chars().map(|c| c.width().unwrap_or(0)).sum::<usize>();
    let color = crate::theme::color("cyan");
    let mut frame = format!("{color}┌{title}{}┐\x1b[0m\n", "─".repeat(width - title_width));
    let mut lines = content.lines();
    for _ in 0..rows - 2 {
        let mut text = String::new();
        let mut used = 0;
        let mut escape = false;
        for c in lines.next().unwrap_or("").chars() {
            if c == '\x1b' { escape = true; text.push(c); continue; }
            if escape {
                text.push(c);
                if c.is_ascii_alphabetic() { escape = false; }
            } else if !c.is_control() {
                let cells = c.width().unwrap_or(0);
                if used + cells > width { break; }
                text.push(c);
                used += cells;
            }
        }
        frame.push_str(&format!("{color}│\x1b[0m{text}\x1b[0m{}{color}│\x1b[0m\n", " ".repeat(width - used)));
    }
    frame.push_str(&format!("{color}└{}┘\x1b[0m", "─".repeat(width)));
    frame
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn borders_surround_colored_unicode_content_without_overflow() {
        let frame = bordered(5, 12, "Info", |_, _| write(format_args!("\x1b[32m界abc\x1b[0m\nsecond")));
        assert!(frame.contains("┌ Info ────┐"));
        assert!(frame.contains("└──────────┘"));
        assert_eq!(frame.lines().count(), 5);
        for line in frame.lines() {
            let mut escape = false;
            let width: usize = line.chars().filter(|c| {
                if *c == '\x1b' { escape = true; return false; }
                if escape { if c.is_ascii_alphabetic() { escape = false; } return false; }
                true
            }).map(|c| unicode_width::UnicodeWidthChar::width(c).unwrap_or(0)).sum();
            assert_eq!(width, 12);
        }
    }
}
