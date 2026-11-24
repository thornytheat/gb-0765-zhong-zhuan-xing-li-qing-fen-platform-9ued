from collections import defaultdict


def associate(rows, legs):
    by_flight = defaultdict(list)
    for leg in legs.values():
        by_flight[leg['flight']].append(leg)

    # 第一遍：窗内采信的装机构成“原航段凭据”，供停飞后的晚到撤下回放。
    credentials = defaultdict(dict)
    for row in rows:
        if row['action'] == 'LOAD':
            match = window_match(row, by_flight[row['flight']])
            if match is not None:
                credentials[(row['flight'], row['tag'])][match['end']] = match['leg']

    linked, isolated = [], []
    for row in rows:
        flight_legs = by_flight[row['flight']]
        evidence = dict(row, candidates=window_candidates(row, flight_legs))
        if row['leg_hint'] is None and row['action'] == 'OFFLOAD':
            replayed = replay_leg(row, flight_legs, credentials.get((row['flight'], row['tag']), {}))
            if replayed is not None:
                linked.append(dict(evidence, leg=replayed, window='OUTSIDE_REPLAY'))
                continue
        chosen = [leg for leg in evidence['candidates'] if row['leg_hint'] in (None, leg)]
        if len(chosen) == 1:
            linked.append(dict(evidence, leg=chosen[0], window='IN_WINDOW'))
        else:
            isolated.append(dict(evidence, reason='LEG_AMBIGUOUS' if chosen else 'LEG_MISSING'))
    return dict(rows=linked, isolated=isolated, counts=dict(linked=len(linked), unresolved=len(isolated)))


def window_candidates(row, flight_legs):
    return sorted(
        leg['leg'] for leg in flight_legs
        if leg['start'] <= row['effective'] < leg['end']
    )


def window_match(row, flight_legs):
    candidates = window_candidates(row, flight_legs)
    if len(candidates) == 1 and row['leg_hint'] in (None, candidates[0]):
        return next(leg for leg in flight_legs if leg['leg'] == candidates[0])
    return None


def replay_leg(row, flight_legs, credential):
    # 原航段凭据：停飞清舱期间，晚到撤下即使落入续飞段窗口，也归到该牌已装机且
    # 已关闭的原航段；续飞段的装机没有此凭据，照常按窗口归续飞段。
    # 显式提示的撤下须自行命中提示窗口，不走凭据回放。
    closed = [leg for leg in flight_legs
              if leg['end'] <= row['effective'] and leg['leg'] in credential.values()]
    if not closed:
        return None
    return max(closed, key=lambda leg: leg['end'])['leg']
