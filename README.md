# Ink print skills

Two self-contained agent skills:

- `ink-print-style/` makes text or images look printed in ink on vintage paper, either fresh or aged. Still images.
- `ink-print-animation/` makes short videos: ink seeping into the paper, the print ageing, or both.

Each skill carries its own copy of `aged-ink/`, the Python toolkit that does the ink and paper effects, with fonts (SIL Open Font License, see `fonts/OFL.txt`), the paper photo and examples. It is part of the skill, not a skill itself.

Each `SKILL.md` uses the open Agent Skills format: YAML front matter (`name`, `description`) followed by instructions. Claude Code, Codex, Cursor, Gemini CLI and others read it.

## Install

Each skill folder works on its own. Install one or both.

```bash
git clone https://github.com/WhitePaper000/ink-print-skills ~/ink-print-skills
SKILLS=~/.claude/skills          # Claude Code (or .claude/skills in a project)
# SKILLS=~/.cursor/skills        # Cursor (or .cursor/skills in a project)
# SKILLS=~/.codex/skills         # Codex CLI
mkdir -p "$SKILLS"
for d in ink-print-style ink-print-animation; do ln -sfn ~/ink-print-skills/$d "$SKILLS/$d"; done
```

Copying the folders instead of linking works too. With links, `git pull` in `~/ink-print-skills` updates every install.

For any other agent, put the skill folder in its workspace and tell it to read that folder's `SKILL.md` before the task.

## Requirements

Python 3.9 or newer, `pip install -r ink-print-style/aged-ink/requirements.txt` (numpy, scipy, Pillow), and `ffmpeg` on PATH for videos.

## Paper

`<skill>/aged-ink/papers/user_paper_01.jpg` is the default paper photo. Swap in your own scan with the same name, or the scripts fall back to generated paper if it is missing.
