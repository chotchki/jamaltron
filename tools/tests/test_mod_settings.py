"""D.3: every mod setting has its locale, and every dropdown value has its label.

Headless Factorio loads a setting with no [mod-setting-name] entry without a word -- the
settings GUI then shows "Unknown key: mod-setting-name.jamaltron-..." to every player, which
no gate here would otherwise see. Same for a string setting's allowed values, which read their
labels from [string-mod-setting] as <setting>-<value>.

Reads settings.lua as TEXT, literal names only, the way lint_sprites reads Lua: a setting
whose name is computed is one this check cannot vouch for, and it says so rather than passing.
"""

import pathlib
import re

REPO = pathlib.Path(__file__).resolve().parents[2]
SETTINGS = REPO / "mod" / "jamaltron" / "settings.lua"
LOCALE = REPO / "mod" / "jamaltron" / "locale" / "en" / "jamaltron.cfg"


def locale_sections(text: str) -> dict:
    out, section = {}, None
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith(("#", ";")):
            continue
        if line.startswith("[") and line.endswith("]"):
            section = out.setdefault(line[1:-1], {})
        elif "=" in line and section is not None:
            key, _, value = line.partition("=")
            section[key] = value
    return out


def declared_settings(text: str) -> list:
    """[(name, type, allowed values or None), ...] off the literal table constructors."""
    out = []
    for block in re.findall(r"\{[^{}]*?type\s*=\s*\"[a-z]+-setting\"[^{}]*?(?:\{[^{}]*\}[^{}]*?)*\}",
                            text, re.S):
        name = re.search(r'name\s*=\s*"([^"]+)"', block)
        kind = re.search(r'type\s*=\s*"([a-z]+-setting)"', block).group(1)
        allowed = re.search(r"allowed_values\s*=\s*\{([^}]*)\}", block)
        values = re.findall(r'"([^"]+)"', allowed.group(1)) if allowed else None
        out.append((name.group(1) if name else None, kind, values))
    return out


def test_every_setting_is_prefixed_named_and_described():
    settings = declared_settings(SETTINGS.read_text())
    assert len(settings) == 8, settings
    loc = locale_sections(LOCALE.read_text())
    for name, kind, _ in settings:
        assert name and name.startswith("jamaltron-"), (name, kind)
        assert loc["mod-setting-name"].get(name), name
        assert loc["mod-setting-description"].get(name), name


def test_every_dropdown_value_has_a_label():
    loc = locale_sections(LOCALE.read_text())
    strings = [(n, v) for n, k, v in declared_settings(SETTINGS.read_text())
               if k == "string-setting"]
    assert strings
    for name, values in strings:
        assert values, name
        for value in values:
            assert loc["string-mod-setting"].get(f"{name}-{value}"), (name, value)


def test_verbosity_is_the_catalogs_own_tiers():
    """The speech code compares the setting's value with a row's TIER directly, so the two
    vocabularies must be the same strings -- a renamed tier would silently match nothing."""
    import gen_lines
    verbosity = dict((n, v) for n, _, v in declared_settings(SETTINGS.read_text()))
    assert tuple(verbosity["jamaltron-verbosity"]) == gen_lines.TIERS
