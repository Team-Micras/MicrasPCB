"""The firmware's view of the main board, as a committed contract the board is tested against.

MicrasFirmware (github.com/Team-Micras/MicrasFirmware) configures the MCU from a CubeMX project
and a target header; CI cannot read that repository, so `snapshot` extracts what the board must
agree with and writes it to `boards/main/firmware.toml`. `tests/test_firmware.py` checks the board
against that file.

    MICRAS_FIRMWARE=~/codes/MicrasFirmware micras-pcb firmware snapshot          # (re)write
    MICRAS_FIRMWARE=~/codes/MicrasFirmware micras-pcb firmware snapshot --check  # fail if stale

Contract (`firmware.toml`):

    [source]   repository, commit and the files read
    [pins.<PIN>]   every MCU pin the firmware assigns (cube/micras_v1.ioc): label (GPIO_Label, the
                   name the firmware uses for the signal), signal (peripheral function), pull
    [supply]   source: RCC.SupplySource of the .ioc (the PWR supply configuration)
    [battery]  channel: "VBAT" when the firmware reads the battery through the internal VBAT/4
               channel (an ADC3 VBAT virtual pin in the .ioc); divider: the ratio it applies
    [drive]    duty cycles the firmware drives loads with, where the board's ratings depend on them:
               wall_emitter (config/targets/v1/target.hpp emitter_duty_cycle) and buzzer
               (micras-lib Buzzer::play, set_duty_cycle)

Firmware changes the board needs (`boards/<board>/firmware_changes.toml`). A board change can
need the firmware to follow (a new ADC pin, a new input). Until MicrasFirmware has it, the change
is declared here, and the board is tested against the contract with the declared changes applied
(`apply_changes`). A declared change the snapshot already contains is stale (`stale_changes`), so
the entry is dropped when firmware.toml is regenerated.

    [[change]]
    id = "C1"                                  # required, unique: the board change it follows
    summary = "Battery voltage on PA5"         # required
    pins = { "PA5" = { signal = "ADCx_INP19", label = "Battery_Voltage" } }   # pins set or replaced
    battery = { channel = "pin", divider = 4.7037 }                          # sections merged key by key

Sections other than pins (supply, battery, drive, behaviour) merge key by key into the contract.
`behaviour` names what the firmware must do differently where no pin or number captures it (a
driver mode, an ADC trigger, a protocol timing), one sentence per key:

    behaviour = { motor_drive = "PH/EN: PWM on EN, direction on PH" }

A board that follows another board's firmware changes (main2 on top of main) lists its own in its
own file; tests apply both in order.
"""

from __future__ import annotations

import os
import re
import tomllib
from pathlib import Path

from .paths import BOARDS, ROOT

IOC = "cube/micras_v1.ioc"
TARGET = "config/targets/v1/target.hpp"
BUZZER = "external/micras-lib/micras_proxy/src/buzzer.cpp"
REPOSITORY = "github.com/Team-Micras/MicrasFirmware"


def contract_path(board: str = "main") -> Path:
    return BOARDS / board / "firmware.toml"


def default_source() -> Path:
    env = os.environ.get("MICRAS_FIRMWARE")
    return Path(env).expanduser() if env else ROOT.parent / "MicrasFirmware"


def load(board: str = "main") -> dict:
    return tomllib.loads(contract_path(board).read_text())


def changes_path(board: str = "main") -> Path:
    return BOARDS / board / "firmware_changes.toml"


CHANGE_SECTIONS = ("pins", "supply", "battery", "drive", "behaviour")


def load_changes(board: str = "main", path: Path | None = None) -> list[dict]:
    """The declared firmware changes, checked for shape (id, summary, known sections, unique ids)."""
    path = path or changes_path(board)
    if not path.is_file():
        return []
    raw = tomllib.loads(path.read_text())
    if set(raw) - {"change"}:
        raise ValueError(f"{path.name}: unknown top-level keys {sorted(set(raw) - {'change'})}")
    seen = set()
    for i, c in enumerate(raw.get("change", []), 1):
        where = f"{path.name} change #{i} ({c.get('id', 'no id')})"
        if not c.get("id") or not c.get("summary"):
            raise ValueError(f"{where}: needs id and summary")
        if c["id"] in seen:
            raise ValueError(f"{where}: duplicate id")
        seen.add(c["id"])
        extra = set(c) - {"id", "summary", *CHANGE_SECTIONS}
        if extra or not any(c.get(s) for s in CHANGE_SECTIONS):
            raise ValueError(f"{where}: unknown keys {sorted(extra)} or no change ({', '.join(CHANGE_SECTIONS)})")
    return raw.get("change", [])


def apply_changes(contract: dict, changes: list[dict]) -> dict:
    """The contract the board must meet: the firmware's, with the declared changes applied in order."""
    out = {k: dict(v) if isinstance(v, dict) else v for k, v in contract.items()}
    for c in changes:
        for section in CHANGE_SECTIONS:
            for key, value in (c.get(section) or {}).items():
                out.setdefault(section, {})[key] = value
    return out


def stale_changes(contract: dict, changes: list[dict]) -> list[str]:
    """Declared changes (or parts of them) the firmware snapshot already has."""
    stale = []
    for c in changes:
        for section in CHANGE_SECTIONS:
            for key, value in (c.get(section) or {}).items():
                if contract.get(section, {}).get(key) == value:
                    stale.append(f"{c['id']}: {section}.{key} is already in firmware.toml")
    return stale


def _commit(repo: Path) -> str:
    """HEAD's commit, read from .git without running git."""
    git = repo / ".git"
    head = (git / "HEAD").read_text().strip()
    if not head.startswith("ref: "):
        return head
    ref = head[5:]
    if (git / ref).is_file():
        return (git / ref).read_text().strip()
    for line in (git / "packed-refs").read_text().splitlines():
        if line.endswith(" " + ref):
            return line.split()[0]
    raise ValueError(f"cannot resolve {ref} in {git}")


def _pin_name(key: str) -> str:
    """'PA13(JTMS/SWDIO)' -> 'PA13'; 'PC14-OSC32_IN' stays (the symbol's pin name)."""
    return key.split("(", 1)[0]


def parse_ioc(text: str) -> dict:
    props = {}
    for line in text.splitlines():
        if "=" in line and not line.startswith("#"):
            k, _, v = line.partition("=")
            props[k.strip()] = v.strip()
    pins: dict[str, dict] = {}
    virtual = []
    for k, v in props.items():
        if re.fullmatch(r"Mcu\.Pin\d+", k):
            if v.startswith("VP_"):
                virtual.append(v)
                continue
            name = _pin_name(v)
            pin = {"signal": props.get(f"{v}.Signal", "")}
            if f"{v}.GPIO_Label" in props:
                pin["label"] = props[f"{v}.GPIO_Label"]
            pull = props.get(f"{v}.GPIO_PuPd")
            if pull:
                pin["pull"] = {"GPIO_PULLUP": "up", "GPIO_PULLDOWN": "down", "GPIO_NOPULL": "none"}[pull]
            pins[name] = pin
    return {"pins": pins, "virtual": sorted(virtual), "supply": props.get("RCC.SupplySource", "")}


def _number(pattern: str, text: str, what: str) -> float:
    m = re.search(pattern, text)
    if not m:
        raise ValueError(f"{what} not found")
    return float(m.group(1))


def build(source: Path) -> dict:
    ioc = parse_ioc((source / IOC).read_text())
    target = (source / TARGET).read_text()
    buzzer = (source / BUZZER).read_text()
    battery_channel = "VBAT" if any("Vbat" in v for v in ioc["virtual"]) else "pin"
    divider = _number(r"battery_config\s*=.*?\.voltage_divider\s*=\s*([\d.]+)F?", _flat(target), "battery divider")
    return {
        "source": {"repository": REPOSITORY, "commit": _commit(source), "files": [IOC, TARGET, BUZZER]},
        "supply": {"source": ioc["supply"]},
        "battery": {"channel": battery_channel, "divider": divider},
        "drive": {
            "wall_emitter": _number(r"emitter_duty_cycle\s*=\s*([\d.]+)F?", target, "emitter duty") / 100,
            "buzzer": _number(r"play\(.*?set_duty_cycle\(([\d.]+)F?\)", _flat(buzzer), "buzzer duty") / 100,
        },
        "pins": dict(sorted(ioc["pins"].items(), key=lambda kv: _natural(kv[0]))),
    }


def _flat(text: str) -> str:
    return " ".join(text.split())


def _natural(s: str) -> list:
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", s)]


def _value(v) -> str:
    if isinstance(v, str):
        return '"' + v.replace("\\", "\\\\").replace('"', '\\"') + '"'
    if isinstance(v, list):
        return "[" + ", ".join(_value(x) for x in v) + "]"
    if isinstance(v, float):
        return repr(round(v, 6))
    return str(v)


def dumps(contract: dict) -> str:
    out = [
        "# Generated by `micras-pcb firmware snapshot` from MicrasFirmware: do not edit.",
        "# Format: tools/micras_pcb/firmware.py. Checked by tests/test_firmware.py.",
        "",
    ]
    for section in ("source", "supply", "battery", "drive"):
        out.append(f"[{section}]")
        out += [f"{k} = {_value(v)}" for k, v in contract[section].items()]
        out.append("")
    out.append("[pins]")
    for pin, fields in contract["pins"].items():
        inner = ", ".join(f"{k} = {_value(v)}" for k, v in fields.items())
        out.append(f'"{pin}" = {{ {inner} }}')
    return "\n".join(out) + "\n"


def snapshot(source: Path | None = None, board: str = "main", check: bool = False) -> int:
    source = (source or default_source()).resolve()
    out = contract_path(board)
    text = dumps(build(source))
    if check:
        if not out.is_file() or out.read_text() != text:
            print(f"{out.relative_to(ROOT)} is stale: run micras-pcb firmware snapshot")
            return 1
        print(f"{out.relative_to(ROOT)} matches {source}")
        return 0
    out.write_text(text)
    print(f"wrote {out.relative_to(ROOT)}: {len(tomllib.loads(text)['pins'])} pins")
    return 0
