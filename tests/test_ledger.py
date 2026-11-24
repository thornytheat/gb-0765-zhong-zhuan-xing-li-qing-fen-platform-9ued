from app.input import sample
from app.pipeline import compute
from app.modules.ledger.service import reconcile


def test_dirty_totals(dirty):
    assert dirty['ledger']['counts'] == dict(manifest=12, loaded=3, pending=8, not_loaded=1, unlisted=1, wrong_bags=2, wrong_legs=2)


def test_clean_totals():
    assert compute(sample('clean'))['ledger']['counts']['loaded'] == 12


def test_leg_subtotals(dirty):
    assert sum(r['manifest'] for r in dirty['ledger']['rows']) == 12


def test_dirty_clearance_handover(dirty):
    handover = dirty['ledger']['handover']
    assert (handover['ready'], handover['blocked']) == (1, 4)
    assert not handover['all_ready']
    jl08 = next(row for row in handover['rows'] if row['leg'] == 'JL-08')
    assert jl08['status'] == 'BLOCKED'
    # 清单外已装件 009999 一件未撤，单独阻断 JL-08
    assert [b['tag'] for b in jl08['blockers'] if b['kind'] == 'UNLISTED'] == ['009999']
    hx42 = next(row for row in handover['rows'] if row['leg'] == 'HX-42')
    assert hx42['status'] == 'READY'


def test_dirty_association_keeps_window_field(dirty):
    assert all('window' in row for row in dirty['legs']['rows'])
    assert {row['window'] for row in dirty['legs']['rows']} == {'IN_WINDOW'}


def test_scan_disagreement_blocks_balance(dirty):
    assert not reconcile(dirty['exceptions'], {}, {'balanced': False}, [])['balanced']


def test_default_stage(desk):
    assert desk.get('/api/stage/ledger').json['difference'] == 0


def test_unknown_stage(desk):
    assert desk.get('/api/stage/nope').json['code'] == 'NO_STAGE'
