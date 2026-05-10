from __future__ import annotations

import random
import re
import string

_WORDS = [
    "alpha",
    "bravo",
    "charlie",
    "delta",
    "echo",
    "foxtrot",
    "golf",
    "hotel",
    "india",
    "juliet",
    "kilo",
    "lima",
    "mike",
    "november",
    "oscar",
    "papa",
    "quebec",
    "romeo",
    "sierra",
    "tango",
    "uniform",
    "victor",
    "whiskey",
    "xray",
    "yankee",
    "zulu",
]


def expand(template: str, *, name: str = "", phone: str = "", username: str = "") -> str:
    result = template
    result = result.replace("{name}", name)
    result = result.replace("{phone}", phone)
    result = result.replace("{username}", username.lstrip("@"))
    result = result.replace("{random:word}", random.choice(_WORDS))

    def _rand_n(m: re.Match[str]) -> str:
        n = max(1, int(m.group(1)))
        return "".join(random.choices(string.ascii_letters + string.digits, k=n))

    result = re.sub(r"\{random:(\d+)\}", _rand_n, result)
    result = result.replace(
        "{random}", "".join(random.choices(string.ascii_letters + string.digits, k=8))
    )
    return result
