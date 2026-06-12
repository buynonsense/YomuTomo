"""Patch MeloTTS 0.1.2 setup.py so it works on pip 22+.

Original setup.py does:
    from pip.req import parse_requirements
    install_reqs = parse_requirements('requirements.txt')
    reqs = [str(ir.req) for ir in install_reqs]

`pip.req` was removed in pip 22. We rewrite that block to use the
always-available `packaging.requirements.Requirement` API.
"""
from pathlib import Path


SETUP_PY = Path("setup.py")


def main() -> None:
    src = SETUP_PY.read_text()
    before = src

    src = src.replace(
        "from pip.req import parse_requirements\n",
        "from pathlib import Path\n"
        "from packaging.requirements import Requirement\n",
    )
    src = src.replace(
        "install_reqs = parse_requirements('requirements.txt')",
        "install_reqs = [Requirement(l) for l in Path('requirements.txt').read_text().splitlines() if l.strip() and not l.startswith('#')]",
    )
    src = src.replace(
        "reqs = [str(ir.req) for ir in install_reqs]",
        "reqs = [str(ir) for ir in install_reqs]",
    )

    if src == before:
        raise SystemExit("setup.py did not match expected pattern; patch needs updating")

    SETUP_PY.write_text(src)
    print("setup.py patched ok")


if __name__ == "__main__":
    main()
