"""Fail CI when a complete backend run omits its PostgreSQL evidence."""
import sys
import xml.etree.ElementTree as ET


def validate_report(path):
    cases = list(ET.parse(path).getroot().iter("testcase"))
    if not cases:
        raise ValueError("Backend report contains no test cases")
    for case in cases:
        for outcome in ("failure", "error", "skipped"):
            if case.find(outcome) is not None:
                raise ValueError(f"Backend {outcome}: {case.get('classname')}.{case.get('name')}")
    postgres = [case for case in cases if "_postgres" in case.get("classname", "")]
    if not postgres:
        raise ValueError("Backend report contains no real PostgreSQL tests")
    print(f"Backend evidence: {len(cases)} passed, {len(postgres)} PostgreSQL-module cases, no skips")


if __name__ == "__main__":
    try:
        validate_report(sys.argv[1])
    except (IndexError, OSError, ET.ParseError, ValueError) as exc:
        sys.exit(f"Invalid backend evidence: {exc}")
