"""整场保持的电脑性格；所有策略输入仅来自自身手牌估计和公开筹码。"""
import math
from collections import Counter
from poker import get_rank_value


# 松紧、主动性、诈唬倾向、下注底池比例。数值只是练习桌启发式。
STYLES = {
    'tight': (-.07, .32, .025, .60),
    'loose': (.09, .43, .09, .55),
    'aggressive': (.035, .78, .18, .85),
    'calling': (.13, .13, .015, .40),
    'balanced': (.0, .48, .065, .65),
}


def make_profile(rng, style=None):
    style = style or rng.choice(tuple(STYLES))
    looseness, aggression, bluff, sizing = STYLES[style]
    return dict(style=style,
                looseness=looseness + rng.uniform(-.025, .025),
                aggression=max(.05, min(.95, aggression + rng.uniform(-.07, .07))),
                bluff=max(.005, bluff + rng.uniform(-.01, .01)),
                sizing=sizing + rng.uniform(-.10, .10))


def choose_action(profile, strength, street, opponents, pot, stack,
                  current_bet, legal, rng, *, position=.5, hole=(), board=()):
    """混合策略：风格控制概率，单次行动和下注尺寸仍有随机变化。"""
    price = legal['call'] / max(1, pot + legal['call'])
    baseline = 1 / (opponents + 1)
    # 翻牌前不只因为盲注便宜就用所有弱牌入池；人数越多参考权益越低。
    selectivity = baseline * .30 if street == 0 else .015
    commitment = legal['call'] / max(1, stack)
    edge = (strength - price + profile['looseness'] - selectivity + (position - .5) * .07
            - commitment * (1 - strength) * .10)
    fold_probability = 1 / (1 + math.exp(max(-30, min(30, edge / .065))))
    if legal['call'] and rng.random() < fold_probability:
        return 'fold', None

    if legal['can_raise']:
        # 使用相对多人平均权益的优势，避免多人桌几乎没有主动下注。
        value = max(0, min(1, (strength - baseline * 1.10) / max(.15, 1 - baseline)))
        # 多人、面对已有下注和昂贵跟注时减少纯诈唬。
        bluff = profile['bluff'] / max(1, opponents) ** 1.4 * (1 - min(.9, price * 2))
        bluff *= .7 + position * .6
        wet_board = False
        if board:
            suits = Counter(c['suit'] for c in board)
            ranks = {get_rank_value(c['rank']) for c in board}
            wet_board = max(suits.values()) >= 2 or any(
                len(ranks.intersection(range(low, low + 5))) >= 3 for low in range(2, 11)
            )
            if wet_board:
                bluff *= .55
            if street in (1, 2):
                own_suits = Counter(c['suit'] for c in hole)
                has_flush_draw = any(
                    suits[suit] + count == 4 for suit, count in own_suits.items()
                )
                if has_flush_draw:
                    bluff += profile['aggression'] * .13 / max(1, opponents)
        raise_probability = min(.92, profile['aggression'] * value + bluff)
        if rng.random() < raise_probability:
            fraction = profile['sizing'] * rng.uniform(.65, 1.45) * (1.18 if wet_board and value > .35 else 1)
            # 先补齐跟注，再按跟注后的底池计算加注增量。
            increment = max(20, round((pot + legal['call']) * fraction))
            target = min(legal['max_raise_to'],
                         max(legal['min_raise_to'], current_bet + increment))
            return 'raise', target
    return ('call' if legal['call'] else 'check'), None


def decide(view, seat, profile, rng, *, min_samples=128, max_samples=768, time_budget=.35):
    """范围抽样 + 边池收益；只在近似同收益的行动间混合。"""
    import time
    from ranges import distributions, sample_hands, range_strength
    from poker import get_hand_rank
    from game import pot_layers
    if not 1 <= min_samples <= max_samples:
        raise ValueError('无效采样预算')
    started = time.monotonic()
    players, board, legal = view['players'], view['board'], view['legal']
    hero = players[seat]
    opponents = [p['seat'] for p in players if p['seat'] != seat and not p['folded']]
    deck, candidates, weighted = distributions(hero['hole'], board, opponents, view['history'], view.get('stats'))
    call, pot = legal['call'], view['pot']
    options = [('call' if call else 'check', None)]
    if call:
        options.insert(0, ('fold', None))
    if legal['can_raise']:
        targets = {min(legal['max_raise_to'], max(legal['min_raise_to'],
                    view['current_bet'] + round((pot + call)*fraction)))
                   for fraction in (1/3, 2/3, 1)}
        targets.add(legal['max_raise_to'])
        options.extend(('raise', target) for target in sorted(targets))
    totals, squares = [0.]*len(options), [0.]*len(options)
    differences = [[0., 0.] for _ in options]
    equity_total = 0.
    position = view.get('position', .5)
    effective = min(hero['stack'], max((players[i]['stack'] for i in opponents), default=0))
    spr = effective / max(1, pot)
    stop = '样本上限'
    for n in range(1, max_samples+1):
        hands, used = sample_hands(candidates, weighted, rng)
        full_board = board + rng.sample([c for c in deck if c['code'] not in used], 5-len(board))
        ranks = {seat: get_hand_rank(hero['hole'] + full_board)}
        ranks.update({i: get_hand_rank(hand + full_board) for i, hand in hands.items()})
        best = min(ranks.values())
        equity_total += (1 / sum(r == best for r in ranks.values())) if ranks[seat] == best else 0
        uniforms = {i: rng.random() for i in opponents}
        values = []
        for action, target in options:
            if action == 'fold':
                values.append(0.)
                continue
            contribution = call if target is None else target - hero['bet']
            projected = [dict(p) for p in players]
            projected[seat]['total'] += contribution
            if action == 'raise':
                for i in opponents:
                    other = projected[i]
                    cost = min(other['stack'], max(0, target-other['bet']))
                    stats = view.get('stats', {}).get(i, {})
                    fold_rate = (stats.get('folds', 0)+2)/(stats.get('faced', 0)+5)
                    strength = range_strength(hands[i], board)
                    pressure = cost / max(20, pot + contribution)
                    fold_prob = max(.02, min(.94, fold_rate + pressure*.3 + (.5-strength)*.75))
                    if other['stack'] and uniforms[i] < fold_prob:
                        other['folded'] = True
                    else:
                        other['total'] += cost
            returned = discounted_return = 0.
            for amount, eligible in pot_layers(projected):
                if seat not in eligible:
                    continue
                top = min(ranks[i] for i in eligible)
                winners = [i for i in eligible if ranks[i] == top]
                if seat in winners:
                    returned += amount / len(winners)
                    # 无争夺的底池层（含未跟注退回）不折损。
                    if len(eligible) > 1:
                        discounted_return += amount / len(winners)
            ev = returned - contribution
            # 非河牌权益实现折扣：位置差、深筹码时保守估计未来成本。
            realization = 1 - (.045 + (1-position)*.045) * min(2, spr) if len(board) < 5 else 1
            ev -= discounted_return * (1-realization)
            if not board:
                # 起手牌策略随位置、人数、有效筹码变化；浅筹码降低投机牌收益。
                quality = range_strength(hero['hole'], [])
                threshold = .40 + .025*(len(opponents)-1) - .12*position - profile['looseness']
                if quality < threshold:
                    ev -= (threshold-quality) * (pot+contribution) * (1+20/max(20,effective))
            values.append(ev)
        for j, value in enumerate(values):
            totals[j] += value
            squares[j] += value*value
            delta = value-values[0]
            differences[j][0] += delta
            differences[j][1] += delta*delta
        if n >= min_samples and n % 64 == 0:
            means = [t/n for t in totals]
            order = sorted(range(len(options)), key=lambda j: means[j], reverse=True)
            # 配对样本误差的保守界，用于提前停止，不是策略正确性保证。
            first, second = order[:2] if len(order)>1 else (0,0)
            se = sum(math.sqrt(max(0, differences[j][1]/n-(differences[j][0]/n)**2)/n)
                     for j in (first, second))
            if len(order)==1 or means[first]-means[second] > 2*se + max(1,pot*.025):
                stop = '收益差异明显'
                break
            if time.monotonic()-started >= time_budget:
                stop = '响应时间预算'
                break
    means = [t/n for t in totals]
    best_ev = max(means)
    tolerance = max(1., pot*.025)
    close = [j for j, value in enumerate(means) if best_ev-value <= tolerance]
    weights = [(profile['aggression']+.1 if options[j][0]=='raise' else
                1-profile['aggression']+.1) for j in close]
    for k, j in enumerate(close):
        if options[j][0] == 'raise':
            size = (options[j][1]-view['current_bet']) / max(1,pot+call)
            weights[k] *= (1 + profile.get('bluff', .06)) / (1 + abs(size-profile.get('sizing', .65)))
    chosen = rng.choices(close, weights=weights)[0]
    action, target = options[chosen]
    report = dict(seat=seat, street=view['street'], action=action, amount=target,
                  samples=n, equity=round(equity_total/n*100,1),
                  error_95=round(98/math.sqrt(n),2), stop=stop,
                  spr=round(spr,2), position=round(position,2),
                  ranges=[dict(seat=i, actions=sum(e['seat']==i for e in view['history']),
                               range='公开行动、位置与历史频率加权') for i in opponents],
                  candidates=[dict(action=a, amount=t, ev=round(means[j],2),
                                   error_95=round(1.96*math.sqrt(max(0,squares[j]/n-means[j]**2)/n),2))
                              for j,(a,t) in enumerate(options)],
                  assumption='启发式范围及弃牌模型；收益包含边池、有效筹码和权益实现折扣，不是求解器。')
    return action, target, report
