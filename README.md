# FlowKey Manager

**English** · [Русский](README.ru.md)

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Python 3.8+](https://img.shields.io/badge/Python-3.8%2B-blue.svg)](https://www.python.org/)
[![Flow Launcher](https://img.shields.io/badge/Flow%20Launcher-plugin-8250df.svg)](https://flowlauncher.com)
[![Build](https://github.com/RADiant-Git/FlowKey-Manager/actions/workflows/publish-release.yml/badge.svg)](https://github.com/RADiant-Git/FlowKey-Manager/actions/workflows/publish-release.yml)

A [Flow Launcher](https://flowlauncher.com) plugin that turns a key press or a short text formula into an
[AutoHotkey v2](https://www.autohotkey.com/) remap:

```text
key new alt + shift + !c -> esc
```

Type the formula → press `Enter` → the rule is compiled into an AutoHotkey v2 script, parsed with
`AutoHotkey.exe /validate` and applied on the fly. No `.ahk` file to write, no script to restart, no
settings window.

```text
🎯 Записать переназначение        capture a remap
🔒 Записать в режиме удержания    capture with hold mode
➕ Собрать правило из каталога…    build from the key catalog or a formula
❓ Справка и управление хуками     help and hook management
```

*The dashboard exactly as the plugin returns it: one card per action, then one per rule.*

The interface is currently Russian only; pull requests adding translations are welcome.

---

## Highlights

- ⌨️ **Capture by pressing** — press the key, combination or mouse button and it is recorded exactly,
  `XButton1` and `Ctrl + Alt + Shift + Win` included.
- 🔒 **Hold mode** — a native AutoHotkey remap: the target key behaves like the real one, with
  auto-repeat and modifier combinations.
- 🔓 **Transparency** — by default a rule swallows the original press; per rule you can let it through
  to the active window as well.
- 🌍 **Per-app scope** — a rule applies everywhere or only inside one process (`Code.exe`,
  `chrome.exe`, …).
- ✅ **Validated before applied** — `/validate` parses without executing, so a broken script never
  replaces a working one.
- 🔄 **Drift detection** — the plugin stores the hash of the applied script and tells you when the
  running hooks lag behind the rules.
- 🧩 **Plain data** — rules live in one readable JSON file, not in an opaque settings blob.
- 📦 **No dependencies** — standard library Python only; AutoHotkey v2 is the single thing you install
  separately.

---

## Requirements

| | |
| :--- | :--- |
| OS | Windows 10 / 11 |
| [Flow Launcher](https://github.com/Flow-Launcher/Flow.Launcher) | 1.11+ (developed and verified on 2.1.4) |
| [AutoHotkey](https://www.autohotkey.com/) | **v2.0** — v1 is not supported |

Python does not need to be installed: Flow Launcher deploys its own embedded Python for plugins
written in it.

---

## Installation

**From the plugin store**

```text
pm install FlowKey Manager
```

**Manually** — download `FlowKeyManager.zip` from the
[latest release](https://github.com/RADiant-Git/FlowKey-Manager/releases/latest) and either run
`pm install <path to the zip>` or unpack it into `%APPDATA%\FlowLauncher\Plugins\FlowKeyManager\`.

**From source**

```cmd
git clone https://github.com/RADiant-Git/FlowKey-Manager.git "%APPDATA%\FlowLauncher\Plugins\FlowKeyManager"
```

Restart Flow Launcher afterwards (`Ctrl + R` in its search bar). The action keyword is `key`; you can
change it in the plugin settings.

---

## Syntax

```text
[@process] <trigger> [ + <trigger> ... ] -> <action>
```

The formula goes after `key new`, so a complete query looks like `key new alt + shift + !c -> esc`.

| Formula | Result |
| :--- | :--- |
| `w -> esc` | `W` presses `Escape` |
| `alt + shift + c -> esc` | `Alt + Shift + C` presses `Escape` |
| `alt + !c -> esc` | **Hold mode**: `Alt + C` behaves as `Escape` |
| `@Code.exe alt + c -> esc` | Only inside VS Code |
| `w -> ^ew` | Action as a raw Send sequence |
| `w -> Media_Play_Pause` | Media key |

Modifiers are `ctrl`, `alt`, `shift` and `win`, with `l`/`r` variants. A `!` before the last key name
switches to hold mode.

### Action modes

| Mode | Generated | When |
| :--- | :--- | :--- |
| `send` | `*w::Send('{Escape}')` | A single press of the target key |
| `remap` | `*w::Escape` | The target key behaves as the real one: auto-repeat, modifiers |

`remap` accepts a single key name only. Given a sequence, the plugin falls back to `send` and says so.

### Key names and Send strings

Catalog names (`esc`, `F5`, `Volume_Up`) are canonicalised and wrapped in braces: without them
AutoHotkey types the word `Volume_Up`. Combinations are parsed the same way — a captured `^AppsKey`
becomes `Send('^{AppsKey}')`. This matters, because `^` in Send applies to the **next character**, so
`Send('^AppsKey')` would press `Ctrl + Shift + A` and type the remaining `ppsKey` as text. The same
holds for any modifier: `+PgUp`, `#e`. Aliases after a modifier are canonicalised too:
`^apps` → `^AppsKey`.

Everything else is passed to `Send` verbatim: `^ew`, `{LCtrl down}e{LCtrl up}w`, plain text.

A lone modifier as an action (`w -> ctrl`) is rejected: `Send('{LCtrl}')` presses and immediately
releases, which does nothing. Hold mode is how you express that intent.

### Who gets the key press

By default a rule **swallows** the original press: AutoHotkey does not pass it on, so `XButton1` will
not navigate back in the browser — only your remap fires. **Transparency** changes that: the press
also reaches the active window, so both the remap and the key's normal function run. Such rules are
marked 🔓 in the list.

Remap output consists of ordinary synthetic key presses, and other AutoHotkey scripts do react to
them. Transparency is incompatible with hold mode: a remap turns the source key into the target key,
so there is nothing left to pass through.

---

## Examples

| Goal | Command |
| :--- | :--- |
| Remap `W` to `Escape` | `key new w -> esc` |
| Hold `Alt + C` as `Escape` | `key new alt + !c -> esc` |
| Only inside VS Code | `key new @Code.exe alt + c -> esc` |
| Play/pause on `Ctrl + Alt + T` | `key new ctrl + alt + t -> Media_Play_Pause` |
| Raw Send sequence | `key new w -> ^ew` |
| Capture a key without typing its name | `key` → 🎯 Записать переназначение |
| Record a rule from scratch, mouse button included | `key` → 🎯, press `XButton1`, pick an action |

---

## Search and management

| Input | Result |
| :--- | :--- |
| `key` | dashboard: three actions, then every rule |
| `key ?` | help and hook management |
| `key new` | the builder |
| `key new w -> esc` | the builder with a ready "✅ Apply" card |
| `key <text>` | filter actions and rules by name, trigger, action or scope |
| `key target: …` | jump to the action step of the wizard |
| `key app: …` | pick the scope process |

`Enter` on a rule row toggles it; the subtitle says which way. The context menu
(`Shift + Enter`, `Ctrl + O`, or right-click a result) holds:

- **Enable / disable the rule** — the same as pressing `Enter` on it.
- **Transparency** — let the original press through as well.
- **Delete the rule** — deliberately the last entry.

The help screen (`key ?`) pauses every hook, re-applies them, toggles autostart at Windows logon,
opens the plugin folder and clears all rules.

---

## How it works

```text
Flow Launcher -> main.py -> core/rpc.py -> core/services.py -> core/ahk/codegen.py -> runtime.ahk
```

- `core/rpc.py` is the JSON-RPC boundary. It normalises every shape of `argv`, dispatches through an
  explicit table and never lets the process die: an exception becomes a card carrying the reason.
- `core/model.py` owns validation, so an invalid or conflicting rule is rejected *before* anything is
  written. You never end up with a rule that silently does nothing.
- `core/ahk/codegen.py` is a pure function from `RuleSet` to script text, which is why the domain is
  testable with no AutoHotkey installed.
- Applying is ordered: generate → `AutoHotkey.exe /validate` (parse, no execution) → write
  `runtime.ahk` → launch. `#SingleInstance Force` replaces the previous process.
- An empty rule set generates no hotkeys at all, so no resident AutoHotkey process with a global
  keyboard hook is left behind.

Layer boundaries and the reasoning behind the current design: [ARCHITECTURE.md](ARCHITECTURE.md)
(in Russian).

### Data

Rules and state live **outside the plugin folder**, in Flow Launcher's plugin settings directory:

```text
%APPDATA%\FlowLauncher\Settings\Plugins\FlowKey Manager\
    modules.json      rules — the single source of truth
    session.json      wizard stage, pause flag, notices, applied script hash
    runtime.ahk       the generated hook script
```

A portable Flow Launcher installation uses
`<program folder>\UserData\Settings\Plugins\FlowKey Manager\` instead.

This is not cosmetic. Flow Launcher updates a plugin by unpacking the new version into a sibling
folder and deleting the old one outright, so anything inside the plugin folder dies on every update.
The settings directory survives updates, and survives uninstalling the plugin with settings kept.

`modules.json` is versioned and human-editable; [`modules.json.example`](modules.json.example) is a
template:

```json
{
  "format_version": 2,
  "rules": [
    {
      "id": "0f1c2b3a",
      "name": "Ctrl + Alt + T ➔ Media_Play_Pause",
      "trigger": "^!t",
      "action": "Media_Play_Pause",
      "scope": "*",
      "mode": "send",
      "enabled": true,
      "transparent": false
    }
  ]
}
```

| Field | Meaning |
| :--- | :--- |
| `id` | short label used for UI navigation only |
| `name` | row caption; does not affect behaviour |
| `trigger` | AHK specifier **without** `*`: `^!t`, `w`, `XButton1` |
| `action` | a catalog key name or a ready Send sequence |
| `scope` | `*` (everywhere) or a process name: `Code.exe` |
| `mode` | `send` or `remap` |
| `enabled` | whether the rule takes part in script generation |
| `transparent` | `~`: the original press also reaches the active window |

A v1 file (flat list with `trigger_ahk` / `target` / `app` / `hold`) is migrated on first read, and a
single corrupt entry is skipped without losing the rest. Both files are written atomically under a
file lock, because Flow Launcher starts a new process for every interaction.

---

## Troubleshooting

- **A rule is listed but does nothing.** Look at the ⚠️ card at the top of the dashboard: it names the
  reason, for example a trigger already taken by another rule. If it says 🔄 Хуки отстают от правил,
  press `Enter` on it.
- **Typing a formula does nothing.** A bare formula is treated as a filter. The builder needs the
  `new` prefix: `key new w -> esc`.
- **Keys got stuck.** `key ?` → ⏸️ Приостановить все перехваты, then 🔄 Перезапустить рантайм AHK.
- **Nothing happens in a game or an elevated app.** AutoHotkey cannot send input to a window with
  higher privileges than the script, and some games use raw input and ignore synthetic presses. Run
  AutoHotkey as administrator for elevated applications.
- **Autostart stopped working after an update.** The registry value points at one specific version's
  folder. Re-enable it once: `key ?` → 🚀.
- **Why is input blocked while capturing?** So that the combination you press does not leak into the
  active window. `Escape` cancels. Bind `Escape` itself through the catalog or a formula
  (`esc -> ...`), or with a modifier (`Ctrl + Esc`) by pressing.

---

## Development

```cmd
git clone https://github.com/RADiant-Git/FlowKey-Manager.git
cd FlowKey-Manager
python -m unittest discover -s tests -t .
```

202 unit tests cover the domain (validation, trigger conflicts, v1→v2 migration), the DSL, code
generation, capture, storage (atomicity, rollback, BOM), the RPC boundary (every argv shape, including
a list in `context_menu`), the data directory resolution and the consistency of the release files.
AutoHotkey is not needed to run them: the single test that requires it skips itself.

The plugin speaks plain JSON-RPC on stdout, so you can run it directly:

```cmd
python main.py "{\"method\":\"query\",\"parameters\":[\"new w -> esc\"]}"
```

**Releases.** The version comes from `plugin.json`. A push to `main` triggers
[`publish-release.yml`](.github/workflows/publish-release.yml), which runs the tests, builds
`FlowKeyManager.zip`, verifies its layout and publishes a GitHub Release tagged `v<version>`. The Flow
Launcher store picks the new release up automatically.

**Store submission** (one-off): fork
[Flow-Launcher/Flow.Launcher.PluginsManifest](https://github.com/Flow-Launcher/Flow.Launcher.PluginsManifest),
copy [`store/…json`](store/) into its `plugins/` directory and open a pull request. The file name must
stay `<Name>-<ID>.json`, matching `plugin.json`.

---

## License

[MIT](LICENSE) © RADiant-Git

---

## Changelog

**1.0.0**
First public release. Capture by pressing, hold mode, transparency, per-app scope, the DSL and the
builder; rules moved out of the plugin folder, so updates no longer wipe them; the vendored
`flowlauncher` package dropped — the plugin now has no external dependencies.
