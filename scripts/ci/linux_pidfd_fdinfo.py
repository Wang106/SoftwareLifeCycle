"""Pure bounded Linux pidfd fdinfo profile; no collection or authenticity proof."""
import re


class FdinfoRejected(ValueError):
    pass


def _reject():
    raise FdinfoRejected('Unsupported or inconsistent fdinfo record') from None


def _decimal(value, maximum):
    if not re.fullmatch(r'0|[1-9][0-9]{0,19}', value):
        _reject()
    number = int(value)
    if number > maximum:
        _reject()
    return number


def _pid(value):
    return -1 if value == '-1' else _decimal(value, 2**31 - 1)


def parse_fdinfo(raw):
    """Parse supplied bytes for the six-field x64 CONFIG_PID_NS profile.

    Reject unknown/missing fields rather than silently adopting another format.
    `visible` means a positive supplied PID, NOT a live or authentic process.
    The caller must establish complete fresh reads and a trusted procfs view.
    """
    if type(raw) is not bytes or not 0 < len(raw) <= 4096 or not raw.endswith(b'\n'):
        _reject()
    try:
        text = raw.decode('ascii')
    except UnicodeDecodeError:
        _reject()
    lines = text[:-1].split('\n')
    if len(lines) != 6:
        _reject()
    fields = {}
    for line in lines:
        parts = line.split(':\t')
        if len(parts) != 2 or parts[0] in fields:
            _reject()
        fields[parts[0]] = parts[1]
    if set(fields) != {'pos', 'flags', 'mnt_id', 'ino', 'Pid', 'NSpid'}:
        _reject()
    pos = _decimal(fields['pos'], 2**63 - 1)
    mount = _decimal(fields['mnt_id'], 2**31 - 1)
    inode = _decimal(fields['ino'], 2**64 - 1)
    flag_text = fields['flags']
    if not re.fullmatch(r'0[0-7]{1,11}', flag_text):
        _reject()
    flags = int(flag_text, 8)
    if flags >= 2**32 or flag_text != '0' + format(flags, 'o'):
        _reject()
    pid = _pid(fields['Pid'])
    tokens = fields['NSpid'].split('\t')
    # Linux MAX_PID_NS_LEVEL=32 includes levels 0..32, hence up to 33 IDs.
    if not 1 <= len(tokens) <= 33:
        _reject()
    chain = tuple(_pid(token) for token in tokens)
    if chain[0] != pid:
        _reject()
    if pid <= 0:
        if chain != (pid,):
            _reject()
    elif any(number <= 0 for number in chain):
        _reject()
    return {'pos':pos, 'flags':flags, 'mnt_id':mount, 'ino':inode,
            'pid':pid, 'nspid':chain,
            'visibility':'visible' if pid > 0 else 'not_visible' if pid == 0 else 'detached'}


def match_expected_proc_pid(raw, expected_pid):
    """Compare numbers only; expected_pid must use the same external proc view.

    No token/boolean can establish that prerequisite here. Freshness, ownership,
    pidfd liveness and true common-view provenance need the future trusted broker.
    Parsing is repeated from bytes; a caller-edited parsed dict is not accepted.
    """
    if type(expected_pid) is not int or not 0 < expected_pid < 2**31:
        _reject()
    parsed = parse_fdinfo(raw)
    if parsed['pid'] <= 0 or parsed['pid'] != expected_pid:
        _reject()
    return {'observed_pid':parsed['pid'], 'numeric_match':True,
            'common_view_verified':False, 'input_authenticity_verified':False,
            'live_binding_verified':False, 'atomic_snapshot':False,
            'runner_qualified':False}
