"""Detect Iranian SIM-card rond patterns on the 7-digit subscriber number.

The labels follow the catalog published by rond.ir (the 38 market classes, plus
the extra classes that catalog exposes: separate pairs, first-and-last pair,
and ordinary). A number can match several classes at once. The primary class is
the most specific one; if nothing matches, the class is «معمولی».
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

PERSIAN_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")

# Lower rank is shown as the primary class. Order follows market specificity,
# not the website's filter menu.
SPECIFICITY = {
    "هفت رقم یکی": 1,
    "میلیونی": 2,
    "شش رقم یکی از اول": 3,
    "شش رقم یکی از آخر": 4,
    "ده هزاری از اول": 5,
    "ده هزاری از آخر": 6,
    "پنج رقم یکی از اول": 7,
    "پنج رقم یکی از وسط": 8,
    "پنج رقم یکی از آخر": 9,
    "صد صدی": 10,
    "ترازویی": 11,
    "چهار رقم یکی از اول": 12,
    "چهار رقم یکی از وسط": 13,
    "چهار رقم یکی از آخر": 14,
    "گفتاری": 15,
    "سه جفت از اول": 16,
    "سه جفت از آخر": 17,
    "سه جفت مجزا": 18,
    "آینه‌ای": 19,
    "سه پله": 20,
    "هزاری از اول": 21,
    "هزاری از آخر": 22,
    "متشکل از دو رقم": 23,
    "پنج رقم یکی از وسط": 8,
    "سه رقم یکی از اول": 24,
    "سه رقم یکی از وسط": 25,
    "سه رقم یکی از آخر": 26,
    "گفتاری نزدیک": 27,
    "جفت جفت از اول": 28,
    "جفت جفت از آخر": 29,
    "جفت اول و آخر": 30,
    "جفت جفت مجزا": 31,
    "تکرار ۲ رقم یکی": 32,
    "پله‌ای از اول": 33,
    "پله‌ای از آخر": 34,
    "ترتیبی از اول": 35,
    "ترتیبی از آخر": 36,
    "ده دهی از اول": 37,
    "ده دهی از آخر": 38,
    "تاریخ تولدی": 39,
    "حروفی": 40,
    "تکرار پیش شماره": 41,
    "کد پایین": 42,
    "معمولی": 100,
}

# Operator prefixes dealers treat as "the prefix repeated inside the number".
OPERATOR_PREFIXES = {
    "0910", "0911", "0912", "0913", "0914", "0915", "0916", "0917", "0918", "0919",
    "0990", "0991", "0992", "0993", "0994", "0996", "0998", "0999",
    "0900", "0901", "0902", "0903", "0904", "0905",
    "0930", "0933", "0935", "0936", "0937", "0938", "0939",
    "0920", "0921", "0922",
    "0941",
}

# Words dealers spell on a phone keypad. Matched when their digit image
# (length >= 4) sits inside the subscriber number.
_KEYPAD = {
    "A": "2", "B": "2", "C": "2",
    "D": "3", "E": "3", "F": "3",
    "G": "4", "H": "4", "I": "4",
    "J": "5", "K": "5", "L": "5",
    "M": "6", "N": "6", "O": "6",
    "P": "7", "Q": "7", "R": "7", "S": "7",
    "T": "8", "U": "8", "V": "8",
    "W": "9", "X": "9", "Y": "9", "Z": "9",
}
_WORDS = (
    "MOHAMMAD", "MOHAMAD", "MOHAMMAD", "HOSSEIN", "HOSSEIN", "MARYAM",
    "TALA", "GOLD", "LOVE", "IRAN", "MAMA", "BABA", "SARA", "NIMA",
    "REZA", "AMIR", "ARMAN", "ARASH", "PARSA", "KIANA", "SIMA", "NEDA",
    "HADI", "MAJID", "JAVAD", "SALAM", "TEHRAN", "MOBILE", "BANK",
    "AHMAD", "MEHDI", "SAMAN", "PEYMAN", "SHIRIN", "NASIM", "BARAN",
    "ROYA", "LEILA", "ZAHRA", "FATEME", "MOJTABA", "BEHNAM", "KIANOOSH",
)
WORD_DIGITS = {}
for _word in _WORDS:
    _digits = "".join(_KEYPAD[ch] for ch in _word)
    if len(_digits) >= 4:
        WORD_DIGITS.setdefault(_digits, _word.title())

_SOLAR_YEAR_MIN = 1300
_SOLAR_YEAR_MAX = 1405


@dataclass
class Analysis:
    number: str
    prefix: str
    core: str
    code: int
    block3: str
    block4: str
    middle4: str
    trailing_zeros: int
    unique_digits: int
    max_run: int
    types: list[str] = field(default_factory=list)
    primary: str = "معمولی"
    notes: list[str] = field(default_factory=list)
    sequential_len: int = 0
    sequential_reversed: int = 0
    mirror_pairs: int = 0
    word: str = ""

    @property
    def is_ordinary(self) -> bool:
        return self.primary == "معمولی"


def normalize(raw: str) -> str:
    text = (raw or "").translate(PERSIAN_DIGITS)
    digits = re.sub(r"\D", "", text)
    if digits.startswith("98") and len(digits) == 12:
        digits = "0" + digits[2:]
    if digits.startswith("9") and len(digits) == 10:
        digits = "0" + digits
    return digits


def _runs(core: str) -> list[tuple[str, int, int]]:
    found = []
    i = 0
    while i < len(core):
        j = i + 1
        while j < len(core) and core[j] == core[i]:
            j += 1
        found.append((core[i], i, j - i))
        i = j
    return found


def _pair_step_ok(a: str, b: str) -> bool:
    """Two-digit step used by rond.ir: shared units, or shared tens. Not both changing."""
    if a == b or len(a) != 2 or len(b) != 2:
        return False
    same_tens = a[0] == b[0]
    same_units = a[1] == b[1]
    return same_tens != same_units


def _spoken_rhyme(a: str, b: str) -> bool:
    """Two hundreds said as a pair: same phrase, ten or a hundred apart.

    339 and 349 are «سیصد و سی و نه، سیصد و چهل و نه». Identical triples are
    the catalog class «گفتاری» and are not matched here.
    """
    if len(a) != 3 or len(b) != 3 or a == b:
        return False
    if a == a[0] * 3 or b == b[0] * 3:
        return False
    left, right = int(a), int(b)
    if left < 100 or right < 100:
        return False
    return abs(left - right) in (10, 100)


def _triple_step_ok(a: str, b: str) -> bool:
    if a == b or len(a) != 3 or len(b) != 3:
        return False
    same_tail = a[1:] == b[1:] and a[0] != b[0]
    same_head = a[:2] == b[:2] and a[2] != b[2]
    return same_tail or same_head


def _monotonic_pairs(pairs: list[str]) -> bool:
    if len(pairs) < 2:
        return False
    if any(not _pair_step_ok(pairs[i], pairs[i + 1]) for i in range(len(pairs) - 1)):
        return False
    deltas = [int(pairs[i + 1]) - int(pairs[i]) for i in range(len(pairs) - 1)]
    return all(d > 0 for d in deltas) or all(d < 0 for d in deltas)


def _is_hezar(four: str) -> bool:
    if len(four) != 4 or not four.isdigit():
        return False
    value = int(four)
    return 1000 <= value <= 9500 and value % 500 == 0


def _is_dah_hezar(five: str) -> bool:
    return len(five) == 5 and five[0] in "123456789" and five[1:] == "0000"


def _is_hundred_pair(six: str) -> bool:
    if len(six) != 6 or six[1:3] != "00" or six[4:6] != "00":
        return False
    left, right = int(six[:3]), int(six[3:])
    return abs(left - right) == 100 and left % 100 == 0 and right % 100 == 0


def _is_decimal(four: str) -> bool:
    return (
        len(four) == 4
        and four[1] == "0"
        and four[3] == "0"
        and four[0] in "123456789"
        and four[2] in "123456789"
    )


def _sequential_run(fragment: str, reverse: bool = False) -> int:
    """Longest sequential run touching the outer edge of `fragment`.

    `fragment` is either the core read forward (start) or reversed (end).
    Returns the length of the ascending (or, if reverse, descending) run
    that begins at index 0. 0 when shorter than 3.
    """
    if len(fragment) < 3:
        return 0
    best = 1
    for i in range(1, len(fragment)):
        prev = int(fragment[i - 1])
        cur = int(fragment[i])
        expect = (prev - 1) if reverse else (prev + 1)
        if cur == expect:
            best += 1
        else:
            break
    return best if best >= 3 else 0


def _identical_pairs(core: str) -> list[tuple[int, str]]:
    """Disjoint AA pairs, left to right, that are not part of a longer run."""
    pairs = []
    i = 0
    runs = _runs(core)
    # Walk runs; a run of length 2 is one pair, length 4 is two, length 3 is one pair + leftover.
    for digit, start, length in runs:
        usable = length - (length % 2)
        # A run of 3+ identical digits is a "repeated digit" class, not a pair class.
        if length >= 3:
            continue
        if length == 2:
            pairs.append((start, digit))
    return pairs


def _add(found: set[str], name: str) -> None:
    found.add(name)


def detect(raw: str) -> Analysis | None:
    number = normalize(raw)
    if len(number) != 11 or not number.startswith("09"):
        return None
    prefix, core = number[:4], number[4:]
    if len(core) != 7 or not core.isdigit():
        return None

    runs = _runs(core)
    max_run = max(length for _, _, length in runs)
    trailing = 0
    for ch in reversed(core):
        if ch == "0":
            trailing += 1
        else:
            break

    found: set[str] = set()

    if len(set(core)) == 1:
        _add(found, "هفت رقم یکی")

    if len(set(core[:6])) == 1 and len(set(core)) > 1:
        _add(found, "شش رقم یکی از اول")
    if len(set(core[1:])) == 1 and len(set(core)) > 1:
        _add(found, "شش رقم یکی از آخر")

    def _run_at(start: int, length: int) -> bool:
        return len(set(core[start : start + length])) == 1

    if _run_at(0, 5) and not _run_at(0, 6):
        _add(found, "پنج رقم یکی از اول")
    if _run_at(2, 5) and not _run_at(1, 6):
        _add(found, "پنج رقم یکی از آخر")
    # A 5-run in the middle of a 7-digit core can only sit at index 1,
    # and only when it is not also a 6-run glued to an edge.
    if _run_at(1, 5) and not _run_at(0, 6) and not _run_at(1, 6):
        _add(found, "پنج رقم یکی از وسط")

    if _run_at(0, 4) and not _run_at(0, 5):
        _add(found, "چهار رقم یکی از اول")
    if _run_at(3, 4) and not _run_at(2, 5):
        _add(found, "چهار رقم یکی از آخر")
    for start in (1, 2):
        if _run_at(start, 4) and not _run_at(0, 5) and not _run_at(2, 5) and not _run_at(start, 5):
            # Middle means the run does not touch both edges as a longer classified run.
            if start > 0 and start + 4 < 7:
                _add(found, "چهار رقم یکی از وسط")

    if _run_at(0, 3) and not _run_at(0, 4):
        _add(found, "سه رقم یکی از اول")
    if _run_at(4, 3) and not _run_at(3, 4):
        _add(found, "سه رقم یکی از آخر")
    for start in (1, 2):
        if (
            _run_at(start, 3)
            and not _run_at(0, 4)
            and not _run_at(3, 4)
            and not _run_at(start, 4)
            and start > 0
            and start + 3 < 7
        ):
            _add(found, "سه رقم یکی از وسط")

    if len(set(core)) == 2:
        _add(found, "متشکل از دو رقم")

    if core[1:6] == "00000" or core.endswith("00000"):
        _add(found, "میلیونی")
    if _is_dah_hezar(core[:5]):
        _add(found, "ده هزاری از اول")
    if _is_dah_hezar(core[-5:]):
        _add(found, "ده هزاری از آخر")
    if _is_hezar(core[:4]) and "ده هزاری از اول" not in found:
        _add(found, "هزاری از اول")
    if _is_hezar(core[-4:]) and "ده هزاری از آخر" not in found and "میلیونی" not in found:
        _add(found, "هزاری از آخر")

    if core[:3] == core[3:6] and core[:3] != core[0] * 3:
        _add(found, "گفتاری")
    if core[1:4] == core[4:7] and core[1:4] != core[1] * 3:
        _add(found, "گفتاری")
    # 0912 0339 349 is read as 339 then 349. Same shape at either alignment.
    if _spoken_rhyme(core[:3], core[3:6]) or _spoken_rhyme(core[1:4], core[4:7]):
        _add(found, "گفتاری نزدیک")

    if core[0:2] == core[2:4] == core[4:6] and core[0] != core[1]:
        _add(found, "سه جفت از اول")
    if core[1:3] == core[3:5] == core[5:7] and core[1] != core[2]:
        _add(found, "سه جفت از آخر")
    if core[0:2] == core[2:4] and core[0] != core[1] and "سه جفت از اول" not in found:
        _add(found, "جفت جفت از اول")
    if core[3:5] == core[5:7] and core[3] != core[4] and "سه جفت از آخر" not in found:
        _add(found, "جفت جفت از آخر")
    if core[0:2] == core[5:7] and core[0] != core[1] and core[0:2] != core[2:4]:
        _add(found, "جفت اول و آخر")

    aa_pairs = _identical_pairs(core)
    distinct_pair_digits = {digit for _, digit in aa_pairs}
    if len(aa_pairs) >= 3 and len(distinct_pair_digits) >= 2:
        _add(found, "سه جفت مجزا")
    elif len(aa_pairs) >= 2 and len(distinct_pair_digits) >= 2:
        _add(found, "جفت جفت مجزا")
        covered = 2 * len(aa_pairs)
        if 4 <= covered <= 6:
            _add(found, "تکرار ۲ رقم یکی")

    mirror_pairs = sum(core[i] == core[6 - i] for i in range(3))
    contiguous_mirror = False
    for length in range(4, 8):
        for start in range(0, 8 - length):
            chunk = core[start : start + length]
            if chunk == chunk[::-1] and len(set(chunk)) > 1:
                contiguous_mirror = True
                break
        if contiguous_mirror:
            break
    wings_mirror = core[:3] == core[4:][::-1] and len(set(core[:3])) > 1
    if wings_mirror or contiguous_mirror or mirror_pairs >= 2 and len(set(core)) > 1:
        # Two mirrored pairs are 4 digits. Skip the all-identical case; that is هفت رقم یکی.
        if mirror_pairs >= 2 or wings_mirror or contiguous_mirror:
            _add(found, "آینه‌ای")

    # Wings match and the center digit is the scale's beam. All-identical
    # numbers fail the center check and stay in the repeated-digit classes.
    if core[:3] == core[4:] and core[3] != core[0]:
        _add(found, "ترازویی")

    if _monotonic_pairs([core[0:2], core[2:4], core[4:6]]):
        _add(found, "سه پله")
    elif _monotonic_pairs([core[1:3], core[3:5], core[5:7]]):
        _add(found, "سه پله")

    if _monotonic_pairs([core[0:2], core[2:4]]) or _triple_step_ok(core[0:3], core[3:6]):
        _add(found, "پله‌ای از اول")
    if _monotonic_pairs([core[3:5], core[5:7]]) or _triple_step_ok(core[1:4], core[4:7]):
        _add(found, "پله‌ای از آخر")

    seq_start = _sequential_run(core, reverse=False)
    seq_start_rev = _sequential_run(core, reverse=True)
    # Ascending at the end is a descending run when the core is read backwards.
    seq_end = _sequential_run(core[::-1], reverse=True)
    seq_end_rev = _sequential_run(core[::-1], reverse=False)
    if seq_start or seq_start_rev:
        _add(found, "ترتیبی از اول")
    if seq_end or seq_end_rev:
        _add(found, "ترتیبی از آخر")

    if _is_decimal(core[:4]):
        _add(found, "ده دهی از اول")
    if _is_decimal(core[-4:]):
        _add(found, "ده دهی از آخر")
    if _is_hundred_pair(core[:6]) or _is_hundred_pair(core[-6:]):
        _add(found, "صد صدی")

    head4, tail4 = int(core[:4]), int(core[-4:])
    if _SOLAR_YEAR_MIN <= head4 <= _SOLAR_YEAR_MAX or _SOLAR_YEAR_MIN <= tail4 <= _SOLAR_YEAR_MAX:
        _add(found, "تاریخ تولدی")

    # Low code is a priced class mainly for 0912 code 1, from x00 through x19.
    if prefix == "0912" and core[0] == "1" and int(core[1:3]) <= 19:
        _add(found, "کد پایین")

    for offset in range(1, 8):
        window = number[offset : offset + 4]
        if window in OPERATOR_PREFIXES and window != prefix:
            _add(found, "تکرار پیش شماره")
            break

    matched_word = ""
    for digits, word in WORD_DIGITS.items():
        if digits in core:
            matched_word = word
            _add(found, "حروفی")
            break

    types = sorted(found, key=lambda name: (SPECIFICITY.get(name, 90), name))
    primary = types[0] if types else "معمولی"

    notes = [f"بلوک {prefix} {core[:3]}", f"میانه {core[1:5]}"]
    if trailing:
        notes.append(f"{trailing} صفر در انتها")
    if matched_word:
        notes.append(f"حروفی: {matched_word}")

    seq_len = max(seq_start, seq_start_rev, seq_end, seq_end_rev)
    # Reversed only when the number is not also a forward sequence.
    seq_rev = int(bool(seq_start_rev or seq_end_rev) and not (seq_start or seq_end))

    return Analysis(
        number=number,
        prefix=prefix,
        core=core,
        code=int(core[0]),
        block3=core[:3],
        block4=core[:4],
        middle4=core[1:5],
        trailing_zeros=trailing,
        unique_digits=len(set(core)),
        max_run=max_run,
        types=types,
        primary=primary,
        notes=notes,
        sequential_len=seq_len,
        sequential_reversed=seq_rev,
        mirror_pairs=mirror_pairs,
        word=matched_word,
    )
