#!/usr/bin/env python3
"""gi - offline .gitignore generator from bundled templates.

Usage:
    gi python node > .gitignore      merge templates, write to stdout
    gi python node -o .gitignore     same, but write directly to a file
    gi --list                        show all bundled template names
    gi --show python                 print one template verbatim

Fully offline: templates ship inside the package, so this works on planes,
in containers, and in locked-down CI. Zero third-party dependencies.
"""

import argparse
import difflib
import sys
from pathlib import Path
from typing import List, Optional

try:
    from gi import __version__
except Exception:  # gi/cli.py executed directly, outside an installed package
    __version__ = "1.0.0"

TEMPLATE_SUFFIX = ".gitignore"


def templates_dir() -> Path:
    """Directory holding the bundled ``*.gitignore`` template files.

    Resolved relative to this module file, so the CLI works from any
    current working directory.
    """
    return Path(__file__).resolve().parent / "templates"


def available_templates() -> List[str]:
    """Sorted names of all bundled templates (without the .gitignore suffix)."""
    d = templates_dir()
    if not d.is_dir():
        return []
    return sorted(p.stem for p in d.glob("*" + TEMPLATE_SUFFIX) if p.is_file())


def load_template(name: str) -> Optional[str]:
    """Return the template text, or None if the template does not exist.

    Line endings are normalized and the text is guaranteed to end with
    exactly one trailing newline.
    """
    path = templates_dir() / (name + TEMPLATE_SUFFIX)
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8")
    return text.replace("\r\n", "\n").rstrip("\n") + "\n"


def normalize_name(raw: str) -> str:
    return raw.strip().lower()


def render(names: List[str]) -> str:
    """Merge templates into one .gitignore.

    Each template gets a ``# ----- name -----`` header. Identical lines are
    emitted only once (first occurrence wins), so shared entries like
    ``.DS_Store`` are never duplicated. The result ends with exactly one
    trailing newline.
    """
    seen = set()
    sections = []
    for name in names:
        text = load_template(name)
        if text is None:  # guarded by the caller; defensive only
            raise ValueError("unknown template: %s" % name)
        lines = []
        for line in text.splitlines():
            if line in seen:
                continue
            seen.add(line)
            lines.append(line)
        sections.append((name, lines))

    out: List[str] = []
    for i, (name, lines) in enumerate(sections):
        if i:
            out.append("")
        out.append("# ----- %s -----" % name)
        out.extend(lines)
    return "\n".join(out).rstrip("\n") + "\n"


def unknown_template_message(name: str, known: List[str]) -> str:
    suggestions = difflib.get_close_matches(name, known, n=3, cutoff=0.6)
    msg = "unknown template %r." % name
    if suggestions:
        msg += " Did you mean: %s?" % ", ".join(suggestions)
    msg += " Run `gi --list` to see all %d bundled templates." % len(known)
    return msg


def _fail(msg: str, code: int = 2) -> int:
    print("gi: error: %s" % msg, file=sys.stderr)
    return code


def _emit(text: str, output: Optional[str]) -> None:
    if output:
        try:
            Path(output).write_text(text, encoding="utf-8")
        except OSError as exc:
            print("gi: error: cannot write to %r: %s" % (output, exc),
                  file=sys.stderr)
            raise SystemExit(1)
    else:
        sys.stdout.write(text)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gi",
        description="Offline .gitignore generator: merge bundled templates, zero network.",
    )
    parser.add_argument(
        "templates",
        nargs="*",
        metavar="TEMPLATE",
        help="template names to merge, e.g. gi python node macos",
    )
    parser.add_argument("--list", action="store_true",
                        help="list all bundled template names")
    parser.add_argument("--show", metavar="TEMPLATE",
                        help="print one template verbatim")
    parser.add_argument("-o", "--output", metavar="FILE",
                        help="write to FILE instead of stdout")
    parser.add_argument("--version", action="version",
                        version="%%(prog)s %s" % __version__)
    return parser


def _run(args: argparse.Namespace) -> int:
    known = available_templates()
    if not known:
        return _fail("bundled templates directory not found: %s" % templates_dir(), 1)

    if args.list:
        print("\n".join(known))
        return 0

    if args.show is not None:
        name = normalize_name(args.show)
        if name not in known:
            return _fail(unknown_template_message(args.show, known), 2)
        _emit(load_template(name), args.output)
        return 0

    if not args.templates:
        return _fail("no templates given. Usage: gi python node > .gitignore", 2)

    names = [normalize_name(t) for t in args.templates]
    bad = [t for t in names if t not in known]
    if bad:
        return _fail(unknown_template_message(bad[0], known), 2)

    _emit(render(names), args.output)
    return 0


def main(argv=None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
        return _run(args)
    except BrokenPipeError:
        # Downstream closed the pipe (e.g. `gi python | head`): exit quietly,
        # no traceback.
        try:
            sys.stdout.close()
        except Exception:
            pass
        return 0


if __name__ == "__main__":
    sys.exit(main())
