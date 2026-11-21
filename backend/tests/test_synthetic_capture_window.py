"""No real processes, files, database or backup commands."""
import pytest
from synthetic_capture_window import World, Window, Refused


def setup():
    world=World(); return world,Window(world)


def complete(window):
    window.drain(); window.capture('database',lambda:None)
    window.capture('media',lambda:None); window.verify(lambda:None)
    return window.release()


def test_ordered_success_is_model_only():
    world,window=setup();window.pause(world.writers)
    result=complete(window)
    assert result=={'synthetic_sequence_complete':True,'production_pause_verified':False,
                    'actual_capture_verified':False,'atomicity_verified':False}
    assert window.events==['paused','drained','database','media','verified','released']
    assert all(not w.blocked for w in world.writers)


def test_missing_writer_coverage_never_pauses_partially():
    world,window=setup()
    with pytest.raises(Refused):window.pause(world.writers[:-1])
    assert window.state=='FAILED' and not window.events


def test_old_writer_must_finish_and_new_arrival_is_refused():
    world,window=setup(); writer=world.writers[0]; token=writer.start()
    window.pause(world.writers)
    with pytest.raises(Refused):writer.start()
    writer.finish(token)
    assert complete(window)['synthetic_sequence_complete']


def test_undrained_writer_fails_closed():
    world,window=setup();world.writers[0].start();window.pause(world.writers)
    with pytest.raises(Refused):window.drain()
    assert window.state=='FAILED' and all(w.blocked for w in world.writers)
    with pytest.raises(Refused):window.release()


@pytest.mark.parametrize('phase',['database','media','verify'])
@pytest.mark.parametrize('fault',['late_write','reopen','error'])
def test_fault_during_any_capture_phase_has_no_success_or_release(phase,fault):
    world,window=setup();window.pause(world.writers);window.drain()
    def inject():
        if fault=='late_write':world.writers[-1].revision+=1
        elif fault=='reopen':world.writers[-1].blocked=False
        else:raise OSError('synthetic capture failure')
    if phase!='database':window.capture('database',lambda:None)
    if phase=='verify':window.capture('media',lambda:None)
    with pytest.raises(Refused):
        if phase=='verify':window.verify(inject)
        else:window.capture(phase,inject)
    assert window.state=='FAILED' and 'released' not in window.events
    assert all(w.blocked for w in world.writers)
    with pytest.raises(Refused):window.release()


@pytest.mark.parametrize('step',['pause','drain','database','media'])
def test_premature_release_refuses(step):
    world,window=setup();window.pause(world.writers)
    if step!='pause':window.drain()
    if step in ('database','media'):window.capture('database',lambda:None)
    if step=='media':window.capture('media',lambda:None)
    with pytest.raises(Refused):window.release()
    assert all(w.blocked for w in world.writers)


def test_wrong_order_and_duplicate_window_refuse():
    world,window=setup();window.pause(world.writers);window.drain()
    with pytest.raises(Refused):window.capture('media',lambda:None)
    with pytest.raises(Refused):window.pause(world.writers)


def test_caller_replacement_does_not_count_as_coverage():
    world,window=setup();other=World()
    with pytest.raises(Refused):window.pause(other.writers)


def test_two_windows_cannot_share_pause_ownership():
    world,a=setup();b=Window(world)
    a.pause(world.writers);a.drain()
    with pytest.raises(Refused):b.pause(world.writers)
    with pytest.raises(Refused):b.release()
    assert a.state=='DRAINED' and all(w.blocked for w in world.writers)
    a.capture('database',lambda:None);a.capture('media',lambda:None);a.verify(lambda:None)
    assert a.release()['synthetic_sequence_complete']


def test_failed_owner_can_be_replaced_without_reopening_admission():
    world,a=setup();a.pause(world.writers);a.drain()
    def broken():raise OSError('synthetic failure')
    with pytest.raises(Refused):a.capture('database',broken)
    assert all(w.blocked for w in world.writers)
    b=Window(world);b.pause(world.writers)
    with pytest.raises(Refused):a.release()
    assert b.state=='PAUSED' and all(w.blocked for w in world.writers)
    assert complete(b)['synthetic_sequence_complete']
    with pytest.raises(Refused):a.release()
    assert all(not w.blocked for w in world.writers)


def test_nonowner_cannot_change_admission_after_owner_releases():
    world,a=setup();b=Window(world);a.pause(world.writers);complete(a)
    with pytest.raises(Refused):b.release()
    assert all(not w.blocked for w in world.writers)


def test_raw_callback_exception_is_not_in_formatted_output():
    import traceback
    world,window=setup();window.pause(world.writers);window.drain()
    marker='synthetic-'+str(id(world))+'-private-payload'
    def broken():raise OSError(marker)
    with pytest.raises(Refused) as caught:window.capture('database',broken)
    rendered=''.join(traceback.format_exception(caught.value))
    assert marker not in rendered
    assert 'OSError' not in rendered and caught.value.__suppress_context__


def test_failed_callback_cannot_transfer_ownership_before_unwind():
    world,a=setup();a.pause(world.writers);a.drain()
    def callback():
        with pytest.raises(Refused):a.release()
        with pytest.raises(Refused):Window(world).pause(world.writers)
    with pytest.raises(Refused):a.capture('database',callback)
    b=Window(world);b.pause(world.writers)
    assert complete(b)['synthetic_sequence_complete']


def test_nested_capture_cannot_release_outer_callback_ownership():
    world,a=setup();a.pause(world.writers);a.drain()
    def callback():
        with pytest.raises(Refused):a.capture('database',lambda:None)
        with pytest.raises(Refused):Window(world).pause(world.writers)
    with pytest.raises(Refused):a.capture('database',callback)
    b=Window(world);b.pause(world.writers)
    assert complete(b)['synthetic_sequence_complete']
