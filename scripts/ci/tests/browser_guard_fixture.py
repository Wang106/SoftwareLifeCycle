"""Extract the checked-in diagnostic only; never execute its download/setup code."""
import ast
from pathlib import Path
import sys
import textwrap

WORKFLOW = Path(__file__).resolve().parents[3] / '.github/workflows/ci.yml'
if not __debug__:
    raise RuntimeError('Contract assertions require Python without -O')


def install_io_guard():
    """Fail closed if a fixture accidentally tries any native command or network."""
    def guard(event, args):
        if event in ('subprocess.Popen', 'os.system', 'os.posix_spawn', 'os.exec',
                     'socket.connect', 'socket.getaddrinfo', 'socket.bind'):
            raise RuntimeError('External I/O forbidden by browser contract fixtures')
    sys.addaudithook(guard)


def guard_code(text=None):
    text = WORKFLOW.read_text() if text is None else text
    marker = "          python3 - <<'PYTHON' | tee browser-results/runner-browser.txt\n"
    if text.count(marker) != 1:
        raise AssertionError('Expected exactly one diagnostic Python heredoc')
    tail = text.split(marker, 1)[1]
    end = '\n          PYTHON\n'
    if end not in tail:
        raise AssertionError('Missing diagnostic heredoc terminator')
    code = textwrap.dedent(tail.split(end, 1)[0])
    ast.parse(code)
    return code
