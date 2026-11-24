"""Every text of the program is in the Spanish file, with the same {parts}, and nothing else."""

import ast
import re
from pathlib import Path

from py_slowdown import interface

SOURCE = Path(interface.__file__).parent


def program_texts() -> set[str]:
    texts = set()
    for path in SOURCE.glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if (isinstance(node, ast.Call) and getattr(node.func, "id", None) == "tr"
                    and node.args and isinstance(node.args[0], ast.Constant)):
                texts.add(interface.key_of(node.args[0].value))
    # (los que tr() recibe por nombre: la descripción del programa y los de argparse)
    from py_slowdown import app

    texts.add(interface.key_of(app.USAGE))
    texts.update(interface.key_of(t) for t in interface.ARGPARSE_TEXTS)
    return texts


def test_spanish_is_complete():
    spanish = interface.read("es")
    program = program_texts()
    assert sorted(program - set(spanish)) == []
    assert sorted(set(spanish) - program) == []


def test_same_parts():
    part = re.compile(r"\{(\w+)\}")
    for english, spanish in interface.read("es").items():
        assert set(part.findall(english)) == set(part.findall(spanish)), english


def test_use_and_tr():
    interface.use("es")
    try:
        assert interface.tr("Bookmark at {time}", time="0:05.0") == "Marcador en 0:05.0"
        assert interface.tr("not a known text") == "not a known text"
        assert interface.names()["es"] == "Español"
    finally:
        interface.use("en")
    assert interface.tr("&File") == "&File"


def test_each_text_once():
    text = (interface.FOLDER / "es.xml").read_text(encoding="utf-8")
    keys = re.findall(r"<en>(.*?)</en>", text, re.S)
    assert len(keys) == len(set(keys))
