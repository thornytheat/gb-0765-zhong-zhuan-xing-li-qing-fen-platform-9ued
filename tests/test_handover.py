"""航班停飞清舱：窗外撤下凭据回放 + 清舱交接结论。"""
from app.clock import utc
from app.modules.legs.service import associate
from app.modules.ledger.handover import handover
from app.pipeline import compute


def grounded_legs():
    return {
        'GX-1': dict(leg='GX-1', flight='GX100', start=utc('2026-11-20T10:00:00Z'),
                     end=utc('2026-11-20T11:00:00Z'), destination='甲站'),
        'GX-2': dict(leg='GX-2', flight='GX100', start=utc('2026-11-20T11:00:00Z'),
                     end=utc('2026-11-20T12:00:00Z'), destination='甲站'),
    }


def scan(line, event, tag, action, effective, hint=None):
    return dict(line=line, event=event, tag=tag, flight='GX100', leg_hint=hint,
                action=action, effective=utc(effective))


# 晚到的撤下记录即使落入续飞段窗口，凭原航段装机凭据仍回放归原段
def test_late_offload_replays_to_original_leg_during_continuation_window():
    rows = [
        scan(1, 'L1', 'A', 'LOAD', '2026-11-20T10:30:00Z'),
        scan(2, 'O1', 'A', 'OFFLOAD', '2026-11-20T11:20:00Z'),
        scan(3, 'L2', 'B', 'LOAD', '2026-11-20T11:30:00Z'),
    ]
    result = associate(rows, grounded_legs())
    picked = {row['event']: (row['leg'], row['window']) for row in result['rows']}
    assert picked == {
        'L1': ('GX-1', 'IN_WINDOW'),
        'O1': ('GX-1', 'OUTSIDE_REPLAY'),
        'L2': ('GX-2', 'IN_WINDOW'),
    }
    assert result['isolated'] == []


# 全部窗口结束后才到达的撤下，同样凭凭据回放，不会因窗外而隔离漏撤
def test_offload_after_all_windows_replays_to_last_closed_credential_leg():
    rows = [
        scan(1, 'L1', 'A', 'LOAD', '2026-11-20T10:30:00Z'),
        scan(2, 'O1', 'A', 'OFFLOAD', '2026-11-20T12:30:00Z'),
    ]
    result = associate(rows, grounded_legs())
    assert [(r['event'], r['leg'], r['window']) for r in result['rows']] == [
        ('L1', 'GX-1', 'IN_WINDOW'), ('O1', 'GX-1', 'OUTSIDE_REPLAY')]


# 全部窗口之外、又没有原航段凭据的撤下不能凭空回放，照旧隔离
def test_offload_without_credential_is_not_replayed():
    rows = [scan(1, 'O1', 'C', 'OFFLOAD', '2026-11-20T12:30:00Z')]
    result = associate(rows, grounded_legs())
    assert result['rows'] == []
    assert result['isolated'][0]['reason'] == 'LEG_MISSING'


# 显式提示的撤下必须自行命中提示窗口，凭据回放不放行过期提示
def test_hinted_offload_skips_replay():
    rows = [
        scan(1, 'L1', 'A', 'LOAD', '2026-11-20T10:30:00Z'),
        scan(2, 'O1', 'A', 'OFFLOAD', '2026-11-20T11:20:00Z', hint='GX-2'),
        scan(3, 'O2', 'A', 'OFFLOAD', '2026-11-20T11:20:00Z', hint='GX-1'),
    ]
    result = associate(rows, grounded_legs())
    by_event = {r['event']: r for r in result['rows']}
    assert (by_event['O1']['leg'], by_event['O1']['window']) == ('GX-2', 'IN_WINDOW')
    assert 'O2' not in by_event
    assert result['isolated'][0]['reason'] == 'LEG_MISSING'


# 续飞段的装机没有原段凭据，绝不被回放逻辑抢走
def test_continuation_load_never_replayed():
    rows = [
        scan(1, 'L1', 'A', 'LOAD', '2026-11-20T10:30:00Z'),
        scan(2, 'L2', 'A', 'LOAD', '2026-11-20T11:30:00Z'),
    ]
    result = associate(rows, grounded_legs())
    assert [(r['event'], r['leg']) for r in result['rows']] == [('L1', 'GX-1'), ('L2', 'GX-2')]


def _files():
    legs = ('leg,flight,start,end,destination\n'
            'GX-1,GX100,2026-11-20T10:00:00Z,2026-11-20T11:00:00Z,甲站\n'
            'GX-2,GX100,2026-11-20T11:00:00Z,2026-11-20T12:00:00Z,甲站\n')
    manifest = 'tag,planned\n000001,GX-1\n000002,GX-2\n'
    scans = ('event,tag,flight,leg_hint,action,effective,received\n'
             'L1,000001,GX100,,LOAD,2026-11-20T10:30:00Z,2026-11-20T10:30:00Z\n'
             'L2,000002,GX100,,LOAD,2026-11-20T11:10:00Z,2026-11-20T11:10:00Z\n'
             'O1,000001,GX100,,OFFLOAD,2026-11-20T11:20:00Z,2026-11-20T11:25:00Z\n')
    return {'scans.csv': scans, 'legs.csv': legs, 'manifest.csv': manifest}


def test_pipeline_replay_keeps_original_offload_and_continuation_load():
    result = compute(_files())
    assert [(r['event'], r['leg'], r['window']) for r in result['legs']['rows']] == [
        ('L1', 'GX-1', 'IN_WINDOW'), ('L2', 'GX-2', 'IN_WINDOW'),
        ('O1', 'GX-1', 'OUTSIDE_REPLAY')]
    states = {(s['tag'], s['leg']): s['state'] for s in result['replay']['states']}
    assert states == {('000001', 'GX-1'): 'OFFLOADED', ('000002', 'GX-2'): 'LOADED'}
    verdict = {d['tag']: d['status'] for d in result['exceptions']['rows']}
    assert verdict == {'000001': 'not_loaded', '000002': 'loaded'}
    assert result['ledger']['handover']['all_ready']


def _decisions(rows):
    return dict(rows=rows, wrong=[])


def test_handover_blocked_by_unlisted_loaded_bag():
    legs = grounded_legs()
    decisions = _decisions([
        dict(tag='000001', planned='GX-1', status='loaded', reason=None),
        dict(tag='000002', planned='GX-2', status='loaded', reason=None),
    ])
    states = [dict(tag='009999', leg='GX-1', state='LOADED')]
    result = handover(legs, decisions, states)
    gx1 = next(row for row in result['rows'] if row['leg'] == 'GX-1')
    gx2 = next(row for row in result['rows'] if row['leg'] == 'GX-2')
    assert (gx1['status'], gx1['unlisted_loaded']) == ('BLOCKED', 1)
    assert gx1['blockers'] == [dict(tag='009999', reason='UNLISTED_LOADED', kind='UNLISTED')]
    assert gx2['status'] == 'READY'
    assert (result['ready'], result['blocked'], result['all_ready']) == (1, 1, False)


# 清单外已装件撤下后不再阻断
def test_unlisted_offload_releases_handover():
    legs = grounded_legs()
    decisions = _decisions([
        dict(tag='000001', planned='GX-1', status='not_loaded', reason='OFFLOADED'),
        dict(tag='000002', planned='GX-2', status='loaded', reason=None),
    ])
    states = [dict(tag='009999', leg='GX-1', state='OFFLOADED')]
    result = handover(legs, decisions, states)
    assert result['all_ready']
    assert all(row['unlisted_loaded'] == 0 for row in result['rows'])


def test_handover_blocked_by_pending_manifest_bag():
    legs = grounded_legs()
    decisions = _decisions([
        dict(tag='000001', planned='GX-1', status='pending', reason='NO_LOAD'),
        dict(tag='000002', planned='GX-2', status='loaded', reason=None),
    ])
    result = handover(legs, decisions, [])
    gx1 = next(row for row in result['rows'] if row['leg'] == 'GX-1')
    assert gx1['status'] == 'BLOCKED'
    assert gx1['blockers'] == [dict(tag='000001', reason='NO_LOAD', kind='PENDING')]


# 错装到其他航段的件不阻断原航段，只在实际所在航段核算
def test_wrong_leg_bag_counts_on_destination_leg():
    legs = grounded_legs()
    decisions = _decisions([
        dict(tag='000001', planned='GX-1', status='loaded', reason=None),
        dict(tag='000002', planned='GX-2', status='loaded', reason=None),
    ])
    states = [dict(tag='000001', leg='GX-2', state='LOADED')]
    result = handover(legs, decisions, states)
    assert all(row['status'] == 'READY' for row in result['rows'])


# 已经交接后重跑缺少撤下记录的旧批，不覆盖原航段的交接结论
def test_rerun_keeps_archived_handover_conclusion(desk):
    first = desk.post('/api/archive', json={'files': _files()}).json
    archived = desk.get(f"/api/archive/{first['id']}").json
    rerun = desk.post(f"/api/archive/{first['id']}/rerun").json
    assert rerun['reused'] is True
    assert rerun['manifest'] == archived['manifest']
    stored = desk.get(f"/api/archive/{first['id']}").json
    assert stored['manifest']['id'] == first['id']
    view = desk.get(f'/desk/ledger?run={first["id"]}')
    assert view.status_code == 200 and '清舱交接结论' in view.get_data(as_text=True)
