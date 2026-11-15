---
name: add-app
description: Add or change an application, CLI tool, package or persona in this dotfiles repo. Use whenever asked to install something, add a tool or app, or move one to a better source. Picks the most native package source, verifies it exists, and edits config.yaml only.
---

# Adding software

Edit `config.yaml` only. Never write a new task or put a package name in Python.

## 1. Who gets it

| Who | Where |
| --- | --- |
| Every machine | `packages` (apt) or `tools` (mise) |
| Machines doing one kind of work | a `personas` entry: `packages`, `tools`, or `apps` naming an app with `when: [persona]` |
| Some machines, by profile | `apps` with `when`: GUI apps always `desktop`; big or RAM-hungry `heavy`; needs Docker `docker`; needs NVIDIA `gpu` |

## 2. Source: the first of these that exists

Verify before adding. Say in your reply which sources you checked and why the earlier
ones were ruled out.

1. **`apt`**: in the archive of Ubuntu 24.04 *and* Debian 12, in a usable version.
   `curl -sI https://packages.ubuntu.com/noble/<pkg>` and
   `https://packages.debian.org/bookworm/<pkg>` return 200. Watch for renamed binaries
   (`batcat`, `fdfind`) and versions too old for how the dotfiles use the tool.
2. **`apt_repo`**: the vendor's own apt repo, from the vendor's install docs. Check that
   the key URL and `<url>/dists/<suite>/Release` return 200.
3. **`deb`**: a stable "latest" URL that redirects to a `.deb` (`curl -sIL`). `package`
   is the dpkg name.
4. **`mise`**: the tool is in <https://mise.jdx.dev/registry.html>.
5. **`script`**: the vendor's official installer only. Read the whole script first. Set
   `apt: <pkg>` when newer distro releases package it.
6. **`flatpak`**: last resort, when nothing above exists.
   `https://flathub.org/api/v2/appstream/<id>` returns 200. Say that it is a last resort.

## 3. Write and verify

- Short trailing comment when the name doesn't say what it is.
- `python3 -m pytest -q` (tests load the real `config.yaml`), then `./install.sh plan`
  if a machine is available.
- New persona: also add its row to the table in `USAGE.md#personas`.
- Not wanted: kitty.
