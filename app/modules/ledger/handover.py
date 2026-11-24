def handover(legs, decisions, states):
    """清舱交接结论：逐航段判定原航段能否向续飞/地面交接。

    阻断条件有二：
    1. 该段清单件仍有去向待证（pending），末态未钉死；
    2. 清单外已装件仍有一件未撤（末态 LOADED），人在舱里不能交接。
    错装到其他航段的件随其实际所在航段核算，不阻断本航段。
    """
    manifest_tags = {row['tag'] for row in decisions['rows'] if row['planned'] is not None}
    loaded_unlisted = {}
    for state in states:
        if state['state'] == 'LOADED' and state['tag'] not in manifest_tags:
            loaded_unlisted.setdefault(state['leg'], []).append(state['tag'])

    rows, ready = [], 0
    for leg in sorted(legs):
        plan = [row for row in decisions['rows'] if row['planned'] == leg]
        pending = [dict(tag=row['tag'], reason=row['reason']) for row in plan if row['status'] == 'pending']
        unlisted = sorted(loaded_unlisted.get(leg, []))
        blockers = [dict(tag=item['tag'], reason=item['reason'] or 'UNCERTAIN', kind='PENDING') for item in pending]
        blockers += [dict(tag=tag, reason='UNLISTED_LOADED', kind='UNLISTED') for tag in unlisted]
        can_handover = not blockers
        ready += can_handover
        rows.append(dict(leg=leg, destination=legs[leg]['destination'], manifest=len(plan),
                         pending=len(pending), unlisted_loaded=len(unlisted),
                         status='READY' if can_handover else 'BLOCKED',
                         conclusion='可交接' if can_handover else '不可交接',
                         blockers=blockers))
    return dict(rows=rows, ready=ready, blocked=len(rows) - ready,
                all_ready=bool(rows) and ready == len(rows))
