import sys

from keel.cli.app import app


def _normalize_json_flag(argv: list[str]) -> list[str]:
    if "--json" not in argv[1:]:
        return argv
    normalized = [argv[0], "--json"]
    seen_json = False
    for arg in argv[1:]:
        if arg == "--json":
            if seen_json:
                continue
            seen_json = True
            continue
        normalized.append(arg)
    return normalized


def main() -> None:
    sys.argv = _normalize_json_flag(list(sys.argv))
    app()


if __name__ == "__main__":
    main()
