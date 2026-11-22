# Ink print skills

Two agent skills plus the Python toolkit they share:

- `ink-print-style/` makes text or images look printed in ink on vintage paper, either fresh or aged. Still images.
- `ink-print-animation/` makes short videos: ink seeping into the paper, the print ageing, or both.
- `aged-ink/` is the shared toolkit (Python), with fonts (SIL Open Font License, see `fonts/OFL.txt`) and examples.

Each `SKILL.md` uses the open Agent Skills format: YAML front matter (`name`, `description`) followed by instructions. Claude Code, Codex, Cursor, Gemini CLI and others read it.

## Install

`aged-ink/` is not a skill. It is the shared code, fonts, paper photo and examples that both skills call. Keep it next to the two skill folders, because each skill finds it at `../aged-ink/`.

Most agents look for skills one level deep (`<skills folder>/<skill name>/SKILL.md`), so clone the repo once, then link the three folders into the agent's skills folder:

```bash
git clone https://github.com/WhitePaper000/ink-print-skills ~/ink-print-skills
SKILLS=~/.claude/skills          # Claude Code (or .claude/skills in a project)
# SKILLS=~/.cursor/skills        # Cursor (or .cursor/skills in a project)
# SKILLS=~/.codex/skills         # Codex CLI
mkdir -p "$SKILLS"
for d in ink-print-style ink-print-animation aged-ink; do ln -sfn ~/ink-print-skills/$d "$SKILLS/$d"; done
```

Copying the folders instead of linking works too. `git pull` in `~/ink-print-skills` updates linked installs.

For any other agent, put the three folders in its workspace and tell it to read `ink-print-style/SKILL.md` or `ink-print-animation/SKILL.md` before the task.

## Requirements

Python 3.9 or newer, `pip install -r aged-ink/requirements.txt` (numpy, scipy, Pillow), and `ffmpeg` on PATH for videos.

## Paper

`aged-ink/papers/user_paper_01.jpg` is the default paper photo. Swap in your own scan with the same name, or the scripts fall back to generated paper if it is missing.
