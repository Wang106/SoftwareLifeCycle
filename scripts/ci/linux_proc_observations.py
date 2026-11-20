"""Bounded parsing of supplied proc bytes, never live collection or attestation."""
import re


def _text(raw, limit):
    if type(raw) is not bytes or not 0 < len(raw) <= limit:
        raise ValueError('Invalid proc observation')
    try:
        text = raw.decode('ascii')
    except UnicodeDecodeError:
        raise ValueError('Invalid proc observation') from None
    if any(ord(c) < 32 and c not in '\t\n' or ord(c) == 127 for c in text):
        raise ValueError('Invalid proc observation')
    return text


def _number(text, maximum, minimum=0):
    if not re.fullmatch(r'0|[1-9][0-9]{0,19}', text):
        raise ValueError('Invalid proc number')
    value = int(text)
    if not minimum <= value <= maximum:
        raise ValueError('Invalid proc number')
    return value


def parse_stat(raw):
    """Accept only the 52-field Linux stat layout; comm is not returned."""
    text = _text(raw, 4096)
    match = re.fullmatch(r'(0|[1-9][0-9]*) \(([^\n\t]{1,64})\) ([^\n\t]+)\n?', text)
    if match is None:
        raise ValueError('Invalid proc stat')
    fields = match[3].split(' ')
    if len(fields) != 50 or fields[0] not in ('R','S','D','Z','T','t','X','x','K','W','P','I'):
        raise ValueError('Invalid proc stat')
    for token in fields[1:]:
        if not re.fullmatch(r'-?(0|[1-9][0-9]{0,19})', token) or not -(2**63) <= int(token) < 2**64:
            raise ValueError('Invalid proc stat number')
    return {'pid': _number(match[1], 2**31-1, 1),
            'ppid': _number(fields[1], 2**31-1),
            'start_ticks': _number(fields[19], 2**63-1, 1)}


def parse_status(raw):
    """Extract required identity/security fields, rejecting duplicate keys."""
    text = _text(raw, 16384)
    lines = text.splitlines()
    if not 1 <= len(lines) <= 256:
        raise ValueError('Invalid proc status')
    values = {}
    for line in lines:
        match = re.fullmatch(r'([A-Za-z_][A-Za-z0-9_]*):[ \t]+([^\n]*)', line)
        if match is None or match[1] in values:
            raise ValueError('Invalid proc status field')
        values[match[1]] = match[2]
    if not {'Pid','Tgid','PPid','Uid','Seccomp','NoNewPrivs'} <= values.keys():
        raise ValueError('Missing proc status field')
    uids = values['Uid'].split()
    if len(uids) != 4:
        raise ValueError('Invalid proc Uid')
    return {'pid': _number(values['Pid'], 2**31-1, 1),
            'tgid': _number(values['Tgid'], 2**31-1, 1),
            'ppid': _number(values['PPid'], 2**31-1),
            'uids': tuple(_number(v, 2**32-1) for v in uids),
            'seccomp': _number(values['Seccomp'], 2),
            'no_new_privs': _number(values['NoNewPrivs'], 1)}


def adapt(stat_before, status, namespaces, stat_after):
    """Return a partial process fragment, never a complete qualification report.

    All inputs are untrusted observations. Matching snapshots cannot prove live
    ownership, a common boot/proc view, ancestry, authenticity or isolation.
    """
    before, after = parse_stat(stat_before), parse_stat(stat_after)
    observed = parse_status(status)
    if (before != after or observed['pid'] != before['pid'] or
            observed['tgid'] != before['pid'] or observed['ppid'] != before['ppid'] or
            len(set(observed['uids'])) != 1 or observed['uids'][0] == 0):
        raise ValueError('Inconsistent proc identity')
    if type(namespaces) is not dict or set(namespaces) != {'pid','net','user'}:
        raise ValueError('Invalid namespace observations')
    process = {'pid': before['pid'], 'start_ticks': before['start_ticks'],
               'uid': observed['uids'][0]}
    for kind in ('pid','net','user'):
        text = _text(namespaces[kind], 128)
        match = re.fullmatch(kind + r':\[([0-9]+)\]', text)
        if match is None:
            raise ValueError('Invalid namespace observation')
        process[kind + '_ns'] = _number(match[1], 2**63-1, 1)
    process.update(seccomp=observed['seccomp'], no_new_privs=observed['no_new_privs'])
    return {'process': process, 'observed_ppid': before['ppid'],
            'runner_qualified': False, 'publisher_signature_verified': False,
            'input_authenticity_verified': False}
