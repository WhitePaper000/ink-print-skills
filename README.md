# Ink print skill

One self-contained agent skill, `ink-print/`, that makes text or images look printed in ink on vintage paper:

- **Stills:** fresh print or aged print.
- **Videos:** ink seeping into the paper, the print ageing, or both.

`ink-print/aged-ink/` is the Python toolkit the skill runs, with fonts (SIL Open Font License, see `fonts/OFL.txt`), the paper photo and examples. It is part of the skill, not a skill itself.

The `SKILL.md` uses the open Agent Skills format: YAML front matter (`name`, `description`) followed by instructions. Claude Code, Codex, Cursor, Gemini CLI and others read it.

## Install

Link or copy the `ink-print` folder into the agent's skills folder.

```bash
git clone https://github.com/WhitePaper000/ink-print-skills ~/ink-print-skills
SKILLS=~/.claude/skills          # Claude Code (or .claude/skills in a project)
# SKILLS=~/.cursor/skills        # Cursor (or .cursor/skills in a project)
# SKILLS=~/.codex/skills         # Codex CLI
mkdir -p "$SKILLS"
ln -sfn ~/ink-print-skills/ink-print "$SKILLS/ink-print"
```

Copying the folder instead of linking works too. With links, `git pull` in `~/ink-print-skills` updates every install.

For any other agent, put `ink-print/` in its workspace and tell it to read `ink-print/SKILL.md` before the task.

## Requirements

Python 3.9 or newer, `pip install -r ink-print/aged-ink/requirements.txt` (numpy, scipy, Pillow, scikit-image), and `ffmpeg` on PATH for videos.

## Paper

`ink-print/aged-ink/papers/user_paper_01.jpg` is the default paper photo. Swap in your own scan with the same name, or the scripts fall back to generated paper if it is missing.
