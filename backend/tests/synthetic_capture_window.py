"""Executable sequencing model ONLY: no production pause/capture implementation.

All writers belong to this closed in-memory world. No operator flag, timestamp,
PID, lock file or external acknowledgement establishes actual writer coverage.
"""
class Refused(Exception):
    pass


class Writer:
    def __init__(self):
        self.blocked=False
        self.active=set()
        self.revision=0

    def start(self):
        if self.blocked:raise Refused('synthetic admission closed')
        token=object();self.active.add(token)
        return token

    def finish(self,token):
        if token not in self.active:raise Refused('unknown synthetic work')
        self.active.remove(token);self.revision+=1


class World:
    # Categories, not an exhaustive or enforceable production discovery result.
    lanes=('http_reserve','http_receive','direct_coordinator','direct_storage',
           'domain_database_writers','operator_database_or_media_writers')
    def __init__(self):
        self.writers=tuple(Writer() for _ in self.lanes)
        self._owner=None


class Window:
    def __init__(self,world):
        if type(world) is not World:raise Refused('only owned synthetic world')
        self._world=world;self._busy=False
        self._writers=world.writers
        self.state='NEW';self.events=[];self._baseline=None

    def _fail(self):
        # Only the fake writer objects owned by this model. Never host actions.
        if self._world._owner is self:
            for writer in self._writers:writer.blocked=True
            if not self._busy:self._world._owner=None
        self.state='FAILED';self._baseline=None
        raise Refused('synthetic window incomplete or changed') from None

    def _state(self,expected):
        if self.state!=expected:self._fail()

    def pause(self,covered):
        self._state('NEW')
        if self._world._owner is not None:self._fail()
        if (type(covered) is not tuple or len(covered)!=len(self._writers)
                or any(a is not b for a,b in zip(covered,self._writers))):
            self.state='FAILED'
            raise Refused('coverage must be exact owned synthetic writers')
        self._world._owner=self
        for writer in self._writers:writer.blocked=True
        self.state='PAUSED';self.events.append('paused')

    def drain(self):
        self._state('PAUSED')
        if self._world._owner is not self:self._fail()
        if any(not w.blocked or w.active for w in self._writers):self._fail()
        self._baseline=tuple(w.revision for w in self._writers)
        self.state='DRAINED';self.events.append('drained')

    def _stable(self):
        if (self._world._owner is not self or self._baseline is None or any(not w.blocked or w.active for w in self._writers)
                or tuple(w.revision for w in self._writers)!=self._baseline):self._fail()

    def _operation(self,expected,next_state,event,operation):
        if self._busy:self._fail()
        self._state(expected);self._stable()
        self._busy=True
        try:
            try:operation()  # synthetic callbacks only; no real I/O adapter
            except BaseException:self._fail()
        finally:
            self._busy=False
            if self.state=='FAILED' and self._world._owner is self:
                self._world._owner=None
        self._stable()
        self.state=next_state;self.events.append(event)

    def capture(self,kind,operation):
        if kind=='database':self._operation('DRAINED','DATABASE','database',operation)
        elif kind=='media':self._operation('DATABASE','MEDIA','media',operation)
        else:self._fail()

    def verify(self,operation):
        self._operation('MEDIA','VERIFIED','verified',operation)

    def release(self):
        self._state('VERIFIED');self._stable()
        for writer in self._writers:writer.blocked=False
        self._world._owner=None
        self.state='RELEASED';self.events.append('released')
        return {'synthetic_sequence_complete':True,'production_pause_verified':False,
                'actual_capture_verified':False,'atomicity_verified':False}
