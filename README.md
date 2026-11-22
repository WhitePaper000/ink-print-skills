# Ink print skills

Two agent skills plus the Python toolkit they share:

- `ink-print-style/` makes text or images look printed in ink on vintage paper, either fresh or aged. Still images.
- `ink-print-animation/` makes short videos: ink seeping into the paper, the print ageing, or both.
- `aged-ink/` is the shared toolkit (Python), with fonts (SIL Open Font License, see `fonts/OFL.txt`) and examples.

Each `SKILL.md` uses the open Agent Skills format: YAML front matter (`name`, `description`) followed by instructions. Claude Code, Codex, Cursor, Gemini CLI and others read it.

## Install

Keep the three folders side by side, because the skills find the toolkit at `../aged-ink/`.

- **Claude Code**: copy all three folders into `~/.claude/skills/`, or `.claude/skills/` in a project.
- **Cursor**: copy them into `.cursor/skills/` in a project, or `~/.cursor/skills/`.
- **Codex CLI**: copy them into `~/.codex/skills/`.
- **Any other agent**: put the folders in its workspace and tell it to read `ink-print-style/SKILL.md` or `ink-print-animation/SKILL.md` before the task.

Requirements: Python 3.9 or newer, `pip install -r aged-ink/requirements.txt`, and `ffmpeg` on PATH for videos.

`aged-ink/papers/user_paper_01.jpg` is the default paper photo. Swap in your own scan with the same name, or the scripts fall back to generated paper if it is missing.
