# dotfiles

One YAML file describes a machine. `./install.sh` makes the machine match it, and it
is safe to rerun at any time: it changes only what differs from the config.

## How it works

```mermaid
%%{init: {"theme": "neutral"}}%%
flowchart LR
    L1["curl -fsSL https://dot.kamal.sh #124; bash"] --> L2[Asks a few questions] --> L3["Saves ~/dotfiles/profile.yaml"] --> L4[Installs and configures] --> L5[Done]
    W1["irm https://dot.kamal.sh #124; iex"] --> W2[Asks a few questions] --> W3["Saves %ProgramData%\dotfiles\profile.json"] --> W4[Installs apps, WSL, hardening] --> W5[Done]
```

## Linux / WSL (Debian 12+, Ubuntu 24.04+, Mint, …)

```bash
curl -fsSL https://dot.kamal.sh | bash
```

It clones this repo to `~/dotfiles`, asks a few questions about the machine, and sets
it up. Run it as your normal user, not with `sudo`. Later runs: `~/dotfiles/install.sh`
(`plan` to preview first, `upgrade` to update everything it installed).

A development server in one line, no questions (personas: `node`, `python`, `k8s`, `ai`,
`azure`; see [USAGE.md](USAGE.md#personas)):

```bash
curl -fsSL https://dot.kamal.sh | bash -s -- --role server --persona node -y
```

## Windows

From an elevated Windows PowerShell:

```powershell
irm https://dot.kamal.sh | iex
```

It installs the apps, sets up WSL with Ubuntu 24.04, and debloats and hardens Windows
(asks first). Then open Ubuntu and run the Linux steps above.

## More

| Doc | What's in it |
| --- | --- |
| [USAGE.md](USAGE.md) | Every command and flag, Linux Mint desktop and hardening, Windows options |
| [FEATURES.md](FEATURES.md) | What each task does, the machine profile questions, commit checks |
| [MANAGING.md](MANAGING.md) | Where each kind of change goes, adding apps and tasks, development |
| [CLOUD.md](CLOUD.md) | Claude Code cloud environments |
| [web/README.md](web/README.md) | How `dot.kamal.sh` serves the installers |

## Supported systems

| System | Status |
| --- | --- |
| Ubuntu 24.04 and 26.04, Debian 12 and 13 | Tested end to end in containers |
| Linux Mint 22+, LMDE, Pop!_OS, Raspberry Pi OS, Kali and other Debian or Ubuntu derivatives, WSL | Supported: mapped to their upstream release (unit-tested detection) |
| Windows 11 | `windows/install.ps1`; linted in CI, not run there |
| Anything older (Ubuntu 22.04, Debian 11) | Refused with a clear message: Python 3.11+ is required |

Licensed under the [MIT License](LICENSE).
