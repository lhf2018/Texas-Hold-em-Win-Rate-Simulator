"""服务端德州牌局。public_view 是客户端和分析器唯一的信息边界。"""
import random
from itertools import combinations
from bots import make_profile, choose_action
from poker import get_deck, get_hand_rank, HAND_TYPE_NAMES

STREETS = ['翻牌前', '翻牌', '转牌', '河牌']


def pot_layers(players):
    levels = sorted({p['total'] for p in players if p['total'] > 0})
    previous = 0
    pots = []
    for level in levels:
        contributors = [i for i, p in enumerate(players) if p['total'] >= level]
        eligible = [i for i in contributors if not players[i]['folded']]
        pots.append(((level - previous) * len(contributors), eligible))
        previous = level
    return pots


class Game:
    def __init__(self, seed=None, player_count=4, starting_stack=1000):
        if type(player_count) is not int or not 2 <= player_count <= 10:
            raise ValueError('请选择2至10人局')
        if type(starting_stack) is not int or not 100 <= starting_stack <= 100000:
            raise ValueError('起始筹码须为100至100000的整数')
        self.stats = {i: dict(hands=0, vpip=0, pfr=0, faced=0, folds=0) for i in range(player_count)}
        self.decisions = []
        self.starting_stack = starting_stack
        self.rng = random.Random(seed)
        self.players = [dict(name=n, stack=starting_stack, hole=[], folded=False, bet=0, total=0,
                             last_action='等待发牌', acted_at=None) for n in ['你', '林间客', '晚风', '松石', '星河', '听雨', '青山', '流云', '拾光', '远帆'][:player_count]]
        # 性格只在开桌时生成，发下一手不会重置，也不向客户端泄露。
        self.bot_profiles = {seat: make_profile(self.rng) for seat in range(1, player_count)}
        self.button = -1
        self.small_blind = None
        self.big_blind = None
        self.hand = 0
        self.version = 0
        self.done = True
        self.history = []
        self.board = []
        self.result = []
        self.actor = None
        self.street = 0
        self.current_bet = 0
        self.min_raise = 20
        self.raise_used = False
        self.raised_seats = set()
        self.initial_pending = set()
        self.raises_closed = False
        self.last_pot = 0

    def next_seat(self, seat, seats):
        count = len(self.players)
        return next((seat + offset) % count for offset in range(1, count + 1) if (seat + offset) % count in seats)

    def record(self, seat, action, amount=0):
        p = self.players[seat]
        p['last_action'] = action + (f' {amount}' if amount else '')
        self.history.append(dict(seat=seat, name=p['name'], action=action, amount=amount,
                                 street=self.street, board=list(self.board),
                                 pot=sum(x['total'] for x in self.players), to=p['bet'],
                                 position=self.position(seat)))

    def pay(self, seat, amount):
        p = self.players[seat]
        amount = min(amount, p['stack'])
        p['stack'] -= amount
        p['bet'] += amount
        p['total'] += amount
        return amount

    def start_hand(self):
        if not self.done:
            raise ValueError('请先完成当前牌局')
        seats = [i for i, p in enumerate(self.players) if p['stack'] > 0]
        if 0 not in seats or len(seats) < 2:
            raise ValueError('本场已结束，请重新开桌')
        self.button = self.next_seat(self.button, seats)
        self.decisions = []
        self.voluntary, self.preflop_raised = set(), set()
        for i in seats:
            self.stats[i]['hands'] += 1
        self.hand += 1
        self.version += 1
        self.done = False
        self.board, self.history, self.result = [], [], []
        self.street, self.current_bet, self.min_raise = 0, 20, 20
        self.raise_used = False
        self.last_pot = 0
        self.deck = get_deck()
        self.rng.shuffle(self.deck)
        for i, p in enumerate(self.players):
            p.update(hole=[self.deck.pop(), self.deck.pop()] if i in seats else [],
                     folded=i not in seats, bet=0, total=0, acted_at=None,
                     last_action='等待行动' if i in seats else '已离桌')
        small = self.button if len(seats) == 2 else self.next_seat(self.button, seats)
        big = self.next_seat(small, seats)
        self.small_blind, self.big_blind = small, big
        for seat, amount, label in [(small, 10, '小盲'), (big, 20, '大盲')]:
            paid = self.pay(seat, amount)
            self.record(seat, label, paid)
        self.pending = {i for i in seats if self.players[i]['stack'] > 0}
        self.reset_raise_round()
        self.actor = big
        self.advance()

    def reset_raise_round(self):
        self.raised_seats = set()
        self.initial_pending = set(self.pending)
        self.raises_closed = False

    def legal(self, seat):
        p = self.players[seat]
        call = min(max(0, self.current_bet - p['bet']), p['stack'])
        maximum = p['bet'] + p['stack']
        others = any(i != seat and not q['folded'] and q['stack'] > 0 for i, q in enumerate(self.players))
        minimum = self.current_bet + 1
        reason = ''
        if self.done or p['folded'] or not p['stack']:
            reason = '当前玩家不能行动'
        elif self.raises_closed:
            reason = '本轮首轮行动已结束，现在只能跟齐最高下注或弃牌'
        elif seat not in self.initial_pending:
            reason = '你已完成本轮首次行动，现在只能跟齐最高下注或弃牌'
        elif maximum <= self.current_bet:
            reason = '剩余筹码仅够跟注或全下跟注'
        elif not others:
            reason = '其他未弃牌玩家均已全下，不能继续加注'
        return dict(call=call, min_raise_to=minimum, max_raise_to=maximum,
                    can_raise=not reason, raise_reason=reason,
                    short_allin=maximum < minimum)

    def act(self, seat, action, amount=None):
        if self.done or seat != self.actor:
            raise ValueError('尚未轮到你行动')
        p, legal = self.players[seat], self.legal(seat)
        facing = legal['call'] > 0
        if action == 'fold':
            p['folded'] = True
            self.record(seat, '弃牌')
        elif action == 'check':
            if legal['call']:
                raise ValueError('当前需要跟注，不能过牌')
            self.record(seat, '过牌')
        elif action == 'call':
            if not legal['call']:
                raise ValueError('当前无需跟注，请过牌')
            paid = self.pay(seat, legal['call'])
            self.record(seat, '全下跟注' if p['stack'] == 0 else '跟注', paid)
        elif action == 'raise':
            if not legal['can_raise']:
                raise ValueError(legal['raise_reason'])
            if type(amount) is not int:
                raise ValueError('加注额必须为整数')
            if amount > legal['max_raise_to'] or amount <= self.current_bet or (amount < legal['min_raise_to'] and amount != legal['max_raise_to']):
                raise ValueError('加注额不符合最小加注或全下规则')
            increase = amount - self.current_bet
            self.pay(seat, amount - p['bet'])
            if self.current_bet < 20 and amount >= 20:
                self.min_raise = amount
            elif increase >= self.min_raise:
                self.min_raise = increase
            self.current_bet = amount
            self.raise_used = True
            self.raised_seats.add(seat)
            # 首轮的末位加注后封口，补充行动不再允许加注。
            if self.initial_pending == {seat}:
                self.raises_closed = True
            self.pending.update(i for i, q in enumerate(self.players)
                                if i != seat and not q['folded'] and q['stack'] > 0 and q['bet'] < amount)
            self.record(seat, '全下加注' if p['stack'] == 0 else '加注到', amount)
        else:
            raise ValueError('无效行动')
        if facing:
            self.stats[seat]['faced'] += 1
            self.stats[seat]['folds'] += action == 'fold'
        if self.street == 0 and action in ('call', 'raise'):
            if seat not in self.voluntary:
                self.stats[seat]['vpip'] += 1
                self.voluntary.add(seat)
            if action == 'raise' and seat not in self.preflop_raised:
                self.stats[seat]['pfr'] += 1
                self.preflop_raised.add(seat)
        p['acted_at'] = self.current_bet
        self.pending.discard(seat)
        self.initial_pending.discard(seat)
        if not self.initial_pending:
            self.raises_closed = True
        self.version += 1
        self.advance()

    def advance(self):
        active = [i for i, p in enumerate(self.players) if not p['folded']]
        if len(active) == 1:
            self.finish(active[0])
            return
        self.pending = {i for i in self.pending if not self.players[i]['folded'] and self.players[i]['stack'] > 0}
        # 没有其他可行动玩家时，无需让唯一有筹码者对空气下注。
        able = [i for i in active if self.players[i]['stack'] > 0]
        if len(able) == 1 and self.players[able[0]]['bet'] >= self.current_bet:
            self.pending.clear()
        if self.pending:
            self.actor = self.next_seat(self.actor, self.pending)
            return
        if self.street == 3:
            self.finish()
            return
        self.street += 1
        self.deck.pop()  # 烧牌
        self.board.extend(self.deck.pop() for _ in range(3 if self.street == 1 else 1))
        self.current_bet, self.min_raise = 0, 20
        self.raise_used = False
        for p in self.players:
            p['bet'], p['acted_at'] = 0, None
        self.pending = set(able) if len(able) >= 2 else set()
        self.reset_raise_round()
        self.actor = self.button
        self.advance()

    def finish(self, uncontested=None):
        self.last_pot = sum(p['total'] for p in self.players)
        contributions = [dict(p) for p in self.players]
        ordered = sorted(range(len(self.players)), key=lambda i: contributions[i]['total'], reverse=True)
        first, second = ordered[:2]
        refund = contributions[first]['total'] - contributions[second]['total']
        if refund:
            contributions[first]['total'] -= refund
            self.players[first]['stack'] += refund
        self.result = []
        if uncontested is not None:
            amount = self.last_pot - refund
            self.players[uncontested]['stack'] += amount
            self.result.append(dict(seats=[uncontested], amount=amount, label='无人跟进', payouts={uncontested: amount}))
        else:
            ranks = {i: get_hand_rank(p['hole'] + self.board) for i, p in enumerate(self.players) if not p['folded']}
            for index, (amount, eligible) in enumerate(pot_layers(contributions)):
                best = min(ranks[i] for i in eligible)
                winners = [i for i in eligible if ranks[i] == best]
                # 奇数筹码从庄家左侧开始分配。
                winners.sort(key=lambda i: (i - self.button - 1) % len(self.players))
                share, remainder = divmod(amount, len(winners))
                payouts = {i: share + (n < remainder) for n, i in enumerate(winners)}
                for i, paid in payouts.items():
                    self.players[i]['stack'] += paid
                runner_up = min((ranks[i] for i in eligible if ranks[i] != best), default=())
                kicker = None
                kicker_start = {3: 2, 7: 2, 8: 3, 9: 2, 10: 1}.get(best[0])
                if kicker_start is not None and runner_up[:kicker_start] == best[:kicker_start]:
                    kicker = next(-a for a, b in zip(best, runner_up) if a != b)
                self.result.append(dict(seats=winners, amount=amount, payouts=payouts, kicker=kicker,
                                        high_card=kicker is not None and best[0] == 10,
                                        label='主池' if index == 0 else f'边池 {index}'))
        if refund:
            self.result.append(dict(seats=[first], amount=refund, label='未被跟注退回',
                                    payouts={first: refund}, kind='refund'))
        self.done = True
        self.actor = None
        self.version += 1

    def bot_step(self):
        if self.done or self.actor == 0:
            raise ValueError('当前没有电脑行动')
        seat = self.actor
        p, legal = self.players[seat], self.legal(seat)
        from bots import decide
        action, amount, report = decide(self.decision_view(seat), seat, self.bot_profiles[seat], self.rng)
        self.decisions.append(report)
        self.act(seat, action, amount)

    def position(self, seat):
        able = {i for i, p in enumerate(self.players) if not p['folded'] and p['stack'] > 0} | {seat}
        anchor = self.big_blind if self.street == 0 else self.button
        anchor = self.button if anchor is None else anchor
        order = sorted(able, key=lambda i: (i-anchor-1) % len(self.players))
        return order.index(seat) / max(1,len(order)-1)

    def decision_view(self, seat):
        # 逐字段构建；不传递牌堆、真实对手手牌或可变统计引用。
        fields = ('name', 'stack', 'folded', 'bet', 'total')
        return dict(players=[dict(**{k:p[k] for k in fields}, seat=i,
                                 hole=list(p['hole']) if i == seat else [])
                             for i,p in enumerate(self.players)],
                    board=list(self.board), history=list(self.history),
                    stats={i:dict(v) for i,v in self.stats.items()},
                    street=self.street, current_bet=self.current_bet,
                    pot=sum(p['total'] for p in self.players),
                    legal=self.legal(seat), position=self.position(seat))

    def public_view(self):
        showdown = self.done and len([p for p in self.players if not p['folded']]) > 1
        players = []
        for i, p in enumerate(self.players):
            visible = i == 0 or (showdown and not p['folded'])
            player = {k: p[k] for k in ('name', 'stack', 'folded', 'bet', 'total', 'last_action')}
            best_five = []
            if showdown and not p['folded']:
                # Prefer the board when equivalent five-card combinations exist.
                best_five = min(combinations(self.board + p['hole'], 5), key=get_hand_rank)
            player.update(seat=i, hole=p['hole'] if visible else [], card_count=len(p['hole']),
                          dealer=i == self.button, blind='SB' if i == self.small_blind else 'BB' if i == self.big_blind else None, allin=not p['folded'] and p['stack'] == 0,
                          hand_type=HAND_TYPE_NAMES[get_hand_rank(best_five)[0]] if best_five else None,
                          best_five=[c['code'] for c in best_five])
            players.append(player)
        return dict(stats={i:dict(v) for i,v in self.stats.items()},
                    review=list(self.decisions) if self.done else [], player_count=len(self.players), starting_stack=self.starting_stack, players=players, board=list(self.board), street=self.street, stage=STREETS[self.street],
                    hand=self.hand, version=self.version, done=self.done, actor=self.actor,
                    raise_used=self.raise_used, pot=self.last_pot if self.done else sum(p['total'] for p in self.players),
                    history=list(self.history), result=self.result,
                    legal=self.legal(0) if self.actor == 0 and not self.done else None)
