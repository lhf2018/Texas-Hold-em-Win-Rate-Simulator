'use strict';
const $ = id => document.getElementById(id);
let state = null, busy = false, botTimer = null, analysisEpoch = 0, analysisController = null;
$('analysisToggle').checked = localStorage.getItem('poker-analysis') === 'on';
function escapeHTML(value) { return String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }
let selectedPot = 0;
let lastRaiseAmount = Number(localStorage.getItem('poker-last-raise'));
const fixedRaiseButtons = document.querySelectorAll('[data-raise-to]');
function cardHTML(card, back = false, bestCards = [], kicker = null) {
  if (back) return '<div class="card back" aria-label="隐藏底牌">♠</div>';
  if (!card) return '<div class="card empty" aria-label="未发公共牌">♧</div>';
  const used = bestCards.includes(card.code);
  const rank = ['2','3','4','5','6','7','8','9','10','J','Q','K','A'].indexOf(card.rank) + 2;
  const decisive = used && rank === kicker;
  const highlight = used ? (decisive ? 'best-card kicker-card' : 'best-card') : bestCards.length ? 'unused-card' : '';
  const description = decisive ? '，决定胜负的牌' : used ? '，最佳五张之一' : '';
  return `<div class="card ${['♥','♦'].includes(card.suit) ? 'red' : ''} ${highlight}" aria-label="${escapeHTML(card.code)}${description}"><span>${escapeHTML(card.rank)}</span><span>${escapeHTML(card.suit)}</span></div>`;
}
function payout(pot, seat) {
  if (pot.payouts) return pot.payouts[seat] || 0;
  const index = pot.seats.indexOf(seat);
  return index < 0 ? 0 : Math.floor(pot.amount / pot.seats.length) + (index < pot.amount % pot.seats.length ? 1 : 0);
}
function seatHTML(player) {
  const pot = state?.done ? state.result?.[selectedPot] : null;
  const won = pot && pot.kind !== 'refund' ? payout(pot, player.seat) : 0;
  const current = state?.actor === player.seat && !state?.done;
  const last = state?.history?.at(-1);
  const latest = last?.seat === player.seat;
  const action = latest ? last.action : player.last_action || '';
  const actionKind = action.includes('弃牌') ? 'fold' : action.includes('加注') ? 'raise' : action.includes('跟注') ? 'call' : action.includes('过牌') ? 'check' : 'blind';
  const best = won ? player.best_five || [] : [];
  const cards = player.hole.length ? player.hole.map(c => cardHTML(c, false, best, won ? pot.kicker : null)).join('') : Array.from({length: player.card_count}, () => cardHTML(null, true)).join('');
  const roundBet = !state?.done && player.card_count ? (player.bet || 0) : 0;
  const roundBadge = !state?.done && player.card_count ? `<div class="round-bet ${roundBet ? 'has-bet' : ''}" aria-label="${escapeHTML(player.name)} 本轮投入 ${roundBet} 点"><span class="round-bet-chips" aria-hidden="true"><i></i><i></i><i></i></span><span>本轮 <b>${roundBet.toLocaleString()}</b></span></div>` : '';
  const blindLabel = {SB: '小盲 10', BB: '大盲 20'}[player.blind];
  const blindBadge = blindLabel
    ? `<span class="blind-badge ${player.blind.toLowerCase()}">${blindLabel}</span>`
    : '';
  const handType = state?.done && !player.folded ? player.hand_type : null;
  const prize = won ? `<small>获胜 +${won.toLocaleString()}</small>` : '';
  const showdownBadge = handType
    ? `<div class="showdown-badge" aria-label="${escapeHTML(player.name)}的摊牌牌型">
        <strong>${escapeHTML(handType)}</strong>${prize}
      </div>`
    : '';
  const markers = blindBadge + (player.seat === 0 ? showdownBadge : '');
  const seatMarkers = markers ? `<div class="seat-markers">${markers}</div>` : '';
  const lastAction = player.last_action || '';
  const seatAction = handType || player.folded || lastAction.startsWith('等待') || lastAction.includes('弃牌') ? '' : lastAction;
  return `<div class="seat ${current ? 'active' : ''} ${player.folded ? 'folded' : ''} ${latest ? 'latest-action' : ''} ${won ? 'winner' : ''}" data-action-kind="${actionKind}" data-blind="${player.blind || ''}" data-seat="${player.seat}">${seatMarkers}<div class="seat-name">${escapeHTML(player.name)}${player.dealer ? '<span class="dealer" title="庄家">D</span>' : ''}</div><div class="stack">◉ ${player.stack.toLocaleString()}</div><div class="small-cards">${cards}</div><div class="seat-action">${escapeHTML(seatAction)}${player.allin && !state?.done ? `${seatAction ? ' · ' : ''}ALL IN` : ''}</div>${roundBadge}${player.seat === 0 ? '' : showdownBadge}${won && !handType ? `<div class="winner-badge">♛ 获胜 <strong>+${won.toLocaleString()}</strong></div>` : ''}${won ? `<div class="winner-sparks" aria-hidden="true">${Array.from({length:8},(_,i)=>`<i style="--spark:${i}"></i>`).join('')}</div>` : ''}</div>`;
}
function arrangeSeats() {
  const seats = [...$('opponents').children];
  const count = seats.length;
  // 顺时针：左边、上边、右边；多人的时候下方两角也安排座位。
  const layouts = {
    1:[[50,16,'top']],
    2:[[12,44,'left'],[88,44,'right']],
    3:[[12,44,'left'],[50,16,'top'],[88,44,'right']],
    4:[[12,44,'left'],[33,16,'top'],[67,16,'top'],[88,44,'right']],
    5:[[12,44,'left'],[27,16,'top'],[50,16,'top'],[73,16,'top'],[88,44,'right']],
    6:[[12,53,'left'],[12,29,'left'],[35,16,'top'],[65,16,'top'],[88,29,'right'],[88,53,'right']],
    7:[[12,53,'left'],[12,29,'left'],[27,16,'top'],[50,16,'top'],[73,16,'top'],[88,29,'right'],[88,53,'right']],
    8:[[12,58,'left'],[12,36,'left'],[20,16,'top'],[40,16,'top'],[60,16,'top'],[80,16,'top'],[88,36,'right'],[88,58,'right']],
    9:[[12,59,'left'],[12,38,'left'],[12,17,'left'],[32,16,'top'],[50,16,'top'],[68,16,'top'],[88,17,'right'],[88,38,'right'],[88,59,'right']]
  };
  $('opponents').dataset.dense = count >= 6 ? 'true' : 'false';
  seats.forEach((seat,i)=>{
    const [x,y,edge] = layouts[count][i];
    seat.style.setProperty('--seat-x', x+'%');
    seat.style.setProperty('--seat-y', y+'%');
    seat.dataset.edge = edge;
  });
}
let celebratedHand = null;
function celebrateWinners() {
  if (!state?.done || !state.result?.length) return;
  const key = state.hand + ':' + state.version;
  if (celebratedHand === key) return;
  celebratedHand = key;
  const scene = document.querySelector('.table-scene');
  const bounds = scene.getBoundingClientRect();
  const felt = document.querySelector('.felt').getBoundingClientRect();
  for (const seat of scene.querySelectorAll('.seat.winner')) {
    const rect = seat.getBoundingClientRect();
    for (let i=0;i<9;i++) {
      const chip = document.createElement('span');
      chip.className = 'winning-chip';
      chip.setAttribute('aria-hidden','true');
      chip.style.left = (felt.left + felt.width/2 - bounds.left)+'px';
      chip.style.top = (felt.top + felt.height/2 - bounds.top)+'px';
      chip.style.setProperty('--fly-x',(rect.left+rect.width/2-felt.left-felt.width/2+(i%3-1)*9)+'px');
      chip.style.setProperty('--fly-y',(rect.top+rect.height/2-felt.top-felt.height/2+Math.floor(i/3)*4)+'px');
      chip.style.animationDelay = (i*.075)+'s';
      scene.appendChild(chip);
      chip.addEventListener('animationend',()=>chip.remove(),{once:true});
    }
  }
}
function renderTableBets() {
  const layer = $('tableBets');
  if (!state || state.done) { layer.innerHTML = ''; return; }
  const felt = document.querySelector('.felt').getBoundingClientRect();
  const scene = document.querySelector('.table-scene').getBoundingClientRect();
  const denominations = [1000, 500, 100, 25, 10, 5, 1];
  layer.innerHTML = state.players.map((player,i)=>{
    if (!player.total) return '';
    const seat = document.querySelector(`.seat[data-seat="${i}"]`);
    if (!seat) return '';
    const rect = seat.getBoundingClientRect();
    const x = rect.left + rect.width/2;
    const y = rect.top + rect.height/2;
    let px, py, edge;
    if (i === 0) {
      px = Math.max(.18, Math.min(.82, (x-felt.left)/felt.width)); py=.86; edge='bottom';
    } else if (seat.dataset.edge === 'top') {
      px = Math.max(.12,Math.min(.88,(x-felt.left)/felt.width)); py=.13; edge='top';
    } else {
      px = seat.dataset.edge === 'right' ? .91 : .09;
      py = Math.max(.18,Math.min(.82,(y-felt.top)/felt.height)); edge=seat.dataset.edge;
    }
    let remainder = player.total;
    const stacks = [];
    for (const denomination of denominations) {
      const count = Math.floor(remainder / denomination);
      remainder %= denomination;
      if (!count) continue;
      stacks.push(`<span class="chip-stack" style="--chip-count:${Math.min(count,4)}" title="${denomination} × ${count}">${Array.from({length:Math.min(count,4)},(_,n)=>`<i class="poker-chip chip-${denomination}" style="--chip-level:${n}"><span>${denomination >= 1000 ? '1k' : denomination}</span></i>`).join('')}</span>`);
    }
    return `<div class="player-bet ${player.folded ? 'bet-folded' : ''}" data-edge="${edge}" data-bet-seat="${i}" style="left:${(felt.left-scene.left)+felt.width*px}px;top:${(felt.top-scene.top)+felt.height*py}px" aria-label="${escapeHTML(player.name)} 本手投入 ${player.total}"><div class="chip-piles">${stacks.slice(0,3).join('')}</div><span class="bet-amount">${player.total.toLocaleString()}</span></div>`;
  }).join('');
}
window.addEventListener('resize',()=>requestAnimationFrame(renderTableBets));
let tableExpired = false;
function showError(message) {
  if (message.includes('牌桌已过期')) {
    tableExpired = true;
    clearTimeout(botTimer);
    cancelAnalysis();
    $('error').hidden = true;
    if (!$('expiredDialog').open) $('expiredDialog').showModal();
    return;
  }
  $('error').textContent = message;
  $('error').hidden = !message;
}
async function api(url, payload, signal) {
  const response = await fetch(url, {method: payload === undefined ? 'GET' : 'POST', headers: {'Content-Type':'application/json'}, body: payload === undefined ? undefined : JSON.stringify(payload), signal});
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || '请求失败，请重试');
  return data;
}

function animateContributions(previous) {
  if (!previous || previous.hand !== state.hand || state.done ||
      matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  const scene = document.querySelector('.table-scene');
  const bounds = scene.getBoundingClientRect();
  state.players.forEach((player, i) => {
    const added = player.total - previous.players[i].total;
    if (added <= 0) return;
    const from = scene.querySelector('.seat[data-seat="' + i + '"]')?.getBoundingClientRect();
    const to = scene.querySelector('[data-bet-seat="' + i + '"]')?.getBoundingClientRect();
    if (!from || !to) return;
    const x = from.left + from.width / 2;
    const y = from.top + from.height / 2;
    for (let n = 0; n < Math.min(3, 1 + Math.floor(added / 50)); n++) {
      const chip = document.createElement('span');
      chip.className = 'contribution-chip';
      chip.setAttribute('aria-hidden', 'true');
      chip.style.left = (x - bounds.left) + 'px';
      chip.style.top = (y - bounds.top) + 'px';
      chip.style.setProperty('--fly-x', (to.left + to.width / 2 - x + n * 3) + 'px');
      chip.style.setProperty('--fly-y', (to.top + to.height / 2 - y) + 'px');
      chip.style.animationDelay = (n * 55) + 'ms';
      scene.appendChild(chip);
      chip.addEventListener('animationend', () => chip.remove(), {once:true});
    }
  });
}

function renderSettlement() {
  const summary = $('settlement');
  summary.hidden = !state.done;
  if (!state.done) return;
  let won = 0, returned = 0;
  for (const pot of state.result) {
    if (pot.kind === 'refund') returned += payout(pot, 0);
    else won += payout(pot, 0);
  }
  const net = won + returned - state.players[0].total;
  const signed = (net > 0 ? '+' : '') + net.toLocaleString();
  summary.innerHTML = `<strong>你分得 ${won.toLocaleString()} · 净收益 ${signed}</strong>` +
    state.result.map((pot, i) => {
      const winners = pot.seats.map(seat =>
        `${escapeHTML(state.players[seat].name)} ${payout(pot, seat).toLocaleString()}`).join('、');
      const label = `${escapeHTML(pot.label)} ${pot.amount.toLocaleString()} · ${winners}`;
      if (pot.kind === 'refund') return `<div class="refund-row">${label}</div>`;
      const kicker = pot.kicker ? (pot.high_card ? ' · 高牌决胜' : ' · 踢脚牌决胜') : '';
      return `<button type="button" data-pot="${i}" aria-pressed="${i === selectedPot}">${label}${kicker}</button>`;
    }).join('');
}

function render(previous) {
  if (!state) return;
  $('tableSize').textContent = `${state.player_count} 人局 · ${state.players.filter(p=>p.stack > 0 || (!state.done && !p.folded)).length} 人在桌`;
  $('startingStack').textContent = `起始筹码 ${state.starting_stack.toLocaleString()}`;
  $('opponents').dataset.count = state.players.length - 1;
  $('pot').textContent = state.pot.toLocaleString();
  const pot = state.done ? state.result[selectedPot] : null;
  const boardBest = pot?.seats.flatMap(i => state.players[i].best_five || []) || [];
  $('board').innerHTML = Array.from({length:5}, (_,i)=>cardHTML(state.board[i], false, boardBest, pot?.kicker)).join('');
  $('opponents').innerHTML = state.players.slice(1).map(seatHTML).join('');
  arrangeSeats();
  $('hero').innerHTML = seatHTML(state.players[0]);
  document.querySelector('.table-scene').dataset.turn = state.actor ?? '';
  const yourTurn = !state.done && state.actor === 0;
  $('actions').hidden = false;
  $('raiseControls').hidden = false;
  document.querySelector('.action-area').dataset.mode = state.done ? 'done' : yourTurn ? 'your-turn' : 'waiting';
  $('call').disabled = $('fold').disabled = busy || !yourTurn;
  $('raise').disabled = busy || !yourTurn || !state.legal?.can_raise;
  for (const id of ['raiseAmount','halfPot','potRaise','allin']) $(id).disabled = busy || !yourTurn || !state.legal?.can_raise;
  for (const button of fixedRaiseButtons) {
    button.disabled = busy || !yourTurn || !isLegalRaise(Number(button.dataset.raiseTo));
  }
  $('raiseHint').textContent = state.raise_used && state.rule_mode === 'practice' ? '本轮已加注' : '';
  $('deal').hidden = !state.done;
  if (yourTurn) {
    const legal = state.legal;
    const callAmount = legal.call.toLocaleString();
    $('call').textContent = legal.call ? `跟注 ${callAmount}${legal.call === state.players[0].stack ? ' · 全下' : ''}` : '过牌';
    $('call').disabled = $('fold').disabled = busy;
    $('raise').disabled = busy || !legal.can_raise;
    $('raise').textContent = legal.can_raise ? (legal.short_allin ? `全下至 ${legal.max_raise_to}` : '加注') : '不可加注';
    $('raise').title = legal.raise_reason || '';
    $('raiseHint').textContent = legal.raise_reason || '';
    $('raiseAmount').min = Math.min(legal.min_raise_to, legal.max_raise_to);
    $('raiseAmount').max = legal.max_raise_to;
    if ($('raiseAmount').dataset.version !== String(state.version)) {
      $('raiseAmount').value = fitRaiseAmount(lastRaiseAmount);
      $('raiseAmount').dataset.version = state.version;
    }
    updateRaisePreview();
  }
  const tableOver = state.players[0].stack === 0 || state.players.filter(p=>p.stack > 0).length < 2;
  $('deal').textContent = tableOver ? '重新开桌 →' : '发下一手 →';
  $('deal').disabled = busy;
  renderSettlement();
  $('ruleLabel').textContent = ({per_player:'每人每轮一次加注', standard:'标准再加注桌', practice:'单次加注练习桌'})[state.rule_mode];
  $('reviewPanel').hidden = !state.done || !state.review?.length;
  $('review').innerHTML = (state.done ? state.review || [] : []).map(d =>
    `<p>${escapeHTML(state.players[d.seat].name)} · ${['翻牌前','翻牌','转牌','河牌'][d.street]} · ${escapeHTML(d.action)} ${d.amount ?? ''}<br>权益 ${d.equity}% ±${d.error_95} 个百分点 · ${d.samples} 样本<br>${d.candidates.map(c => `${escapeHTML(c.action)} ${c.amount ?? ''}: EV ${c.ev} ±${c.error_95}`).join(' / ')}<br>${d.ranges.map(r => `${escapeHTML(state.players[r.seat].name)}：${escapeHTML(r.range)}（${r.actions} 次公开行动）`).join('；')}<br>${escapeHTML(d.assumption)}</p>`
  ).join('');
  let lastStreet = -1;
  $('history').innerHTML = state.history.map(e=>{
    const startsStreet = lastStreet !== -1 && e.street !== lastStreet;
    lastStreet = e.street;
    return `<li class="${startsStreet ? 'starts-street' : ''}"><span>${escapeHTML(e.name)}</span><b>${escapeHTML(e.action)}${e.amount ? ' '+e.amount : ''}</b></li>`;
  }).join('');
  $('history').scrollTop = $('history').scrollHeight;
  const renderedState = state;
  requestAnimationFrame(() => {
    if (state !== renderedState) return;
    renderTableBets();
    animateContributions(previous);
    celebrateWinners();
  });
}
function cancelAnalysis() { analysisEpoch++; analysisController?.abort(); analysisController = null; }
async function updateAnalysis() {
  cancelAnalysis();
  const epoch = analysisEpoch, enabled = $('analysisToggle').checked && !tableExpired;
  $('analysisOff').hidden = enabled;
  $('analysisContent').hidden = !enabled;
  $('analysisData').hidden = true;
  if (!enabled) return;
  if (!state || state.done || state.actor !== 0) {
    $('analysisStatus').textContent = '';
    return;
  }
  $('analysisStatus').textContent = '计算中…';
  const version = state.version;
  analysisController = new AbortController();
  try {
    const d = await api('/api/game/analyze', undefined, analysisController.signal);
    if (epoch !== analysisEpoch || !$('analysisToggle').checked || state.version !== version || d.version !== version) return;
    $('analysisStatus').textContent = `你的视角 · ${d.samples.toLocaleString()} 次模拟 · 约95%抽样误差 ±${d.error_95} 个百分点`;
    $('equity').innerHTML = `${d.equity}<small>%</small>`;
    $('equityBar').style.width = d.equity+'%';
    $('winRate').textContent = d.win_rate+'%'; $('tieRate').textContent = d.tie_rate+'%';
    $('ev').textContent = `${d.ev > 0 ? '+' : ''}${d.ev} 点`; $('potOdds').textContent = d.pot_odds+'%';
    $('handStrength').innerHTML = `<span class="hand-strength-icon" aria-hidden="true">♠</span><div><span class="hand-strength-label">当前牌型</span><strong>${escapeHTML(d.hand_strength.type)}</strong></div>`;
    $('suggestion').textContent = d.suggestion;
    $('draws').textContent = d.draw_potential.draws.length ? d.draw_potential.draws.map(x=>`${x.type} · ${x.outs} outs · 到河牌成牌 ${x.probability}%`).join('；')+`。去重后共 ${d.draw_potential.total_outs} outs。` : '';
    $('ranges').innerHTML = d.ranges.map(r=>`${escapeHTML(r.name)} · ${escapeHTML(r.range)}`).join('<br>');
    $('assumption').textContent = d.assumption;
    $('analysisData').hidden = false;
  } catch (e) {
    if (epoch === analysisEpoch && e.name !== 'AbortError') {
      if (e.message.includes('牌桌已过期')) showError(e.message);
      else $('analysisStatus').textContent = `分析暂不可用：${e.message}`;
    }
  }
}
function scheduleBot() {
  clearTimeout(botTimer);
  if (!tableExpired && state && !state.done && state.actor !== 0) botTimer = setTimeout(()=>mutate('step'), 650);
}
async function mutate(operation, data = {}) {
  if (busy || (tableExpired && operation !== 'new')) return;
  busy = true; showError(''); cancelAnalysis(); clearTimeout(botTimer);
  render();
  const previous = state;
  try {
    state = await api(`/api/game/${operation}`, operation === 'new' ? data : {version:state.version,...data});
    if (operation === 'action' && data.action === 'raise') {
      lastRaiseAmount = data.amount;
      localStorage.setItem('poker-last-raise', String(lastRaiseAmount));
    }
    selectedPot = 0;
    if (operation === 'new') {
      tableExpired = false;
      celebratedHand = null;
      delete $('raiseAmount').dataset.version;
    }
  } catch (e) {
    showError(e.message);
    try { const latest = await api('/api/game'); if (!latest.empty) state = latest; } catch (_) {}
  } finally {
    busy = false; render(operation === 'action' || operation === 'step' ? previous : null); updateAnalysis(); scheduleBot();
  }
}

function isLegalRaise(amount) {
  const legal = state?.legal;
  return Boolean(legal?.can_raise && Number.isInteger(amount) &&
    amount >= Math.min(legal.min_raise_to, legal.max_raise_to) && amount <= legal.max_raise_to);
}

function fitRaiseAmount(amount) {
  const {min_raise_to: minimum, max_raise_to: maximum} = state.legal;
  return Math.round(Math.min(maximum, Math.max(minimum, amount || minimum)));
}

function updateRaisePreview() {
  const legal = state?.legal;
  if (!legal?.can_raise) {
    $('raiseHint').textContent = legal?.raise_reason || '';
    return;
  }
  const amount = $('raiseAmount').valueAsNumber;
  const minimum = Math.min(legal.min_raise_to, legal.max_raise_to);
  const valid = isLegalRaise(amount);
  $('raise').disabled = busy || !valid;
  $('raise').textContent = valid && amount === legal.max_raise_to ? '全下' : '加注';
  $('raiseHint').textContent = valid
    ? `本次再付 ${(amount - state.players[0].bet).toLocaleString()} · 加注到 ${amount.toLocaleString()}`
    : `请输入 ${minimum.toLocaleString()}–${legal.max_raise_to.toLocaleString()} 的整数`;
}
function setRaise(target) {
  const legal = state?.legal;
  if (!legal?.can_raise) return;
  $('raiseAmount').value = fitRaiseAmount(target);
  updateRaisePreview();
}
$('raiseAmount').oninput = updateRaisePreview;
$('settlement').onclick = event => {
  const button = event.target.closest('[data-pot]');
  if (!button) return;
  selectedPot = Number(button.dataset.pot);
  render();
  $('settlement').querySelector('[aria-pressed="true"]')?.focus();
};

$('fold').onclick = ()=>mutate('action',{action:'fold'});
$('call').onclick = ()=>mutate('action',{action:state.legal.call ? 'call' : 'check'});
$('raise').onclick = ()=>{
  const amount = Number($('raiseAmount').value);
  if (!isLegalRaise(amount)) { showError('请输入合法的整数加注额。'); return; }
  mutate('action',{action:'raise',amount});
};
for (const button of fixedRaiseButtons) {
  button.onclick = () => {
    const amount = Number(button.dataset.raiseTo);
    if (isLegalRaise(amount)) setRaise(amount);
  };
}
$('halfPot').onclick = ()=>setRaise(state.players[0].bet + state.legal.call + Math.floor((state.pot+state.legal.call)/2));
$('potRaise').onclick = ()=>setRaise(state.players[0].bet + state.legal.call + state.pot + state.legal.call);
$('allin').onclick = ()=>setRaise(state.legal.max_raise_to);
$('deal').onclick = ()=> !state || state.players[0].stack === 0 || state.players.filter(p=>p.stack>0).length<2 ? openSettings() : mutate('next');
function openSettings() {
  $('playerCount').value = state?.player_count || 4;
  $('ruleMode').value = 'per_player';
  $('startingChips').value = state?.starting_stack || 1000;
  $('restartDialog').showModal();
}
$('expiredRestart').onclick = () => {
  $('expiredDialog').close();
  openSettings();
};
$('restart').onclick = openSettings;
$('cancelRestart').onclick = ()=>$('restartDialog').close();
$('tableSettings').onsubmit = event=>{
  event.preventDefault();
  if (!$('tableSettings').reportValidity()) return;
  const starting_stack = Number($('startingChips').value);
  if (!Number.isInteger(starting_stack)) return;
  $('restartDialog').close();
  mutate('new', {player_count:Number($('playerCount').value), starting_stack, rule_mode:$('ruleMode').value});
};
for (const button of document.querySelectorAll('[data-stack]')) button.onclick = ()=>{ $('startingChips').value = button.dataset.stack; };
$('analysisToggle').onchange = ()=>{ localStorage.setItem('poker-analysis', $('analysisToggle').checked ? 'on' : 'off'); updateAnalysis(); };
async function initialize() {
  try { const d = await api('/api/game'); if (!d.empty) state = d; render(); updateAnalysis(); scheduleBot(); }
  catch(e) { showError(e.message); }
}
document.querySelector('.action-area').dataset.mode = 'done';
$('actions').hidden = false;
$('raiseControls').hidden = false;
$('board').innerHTML = Array.from({length:5},()=>cardHTML(null)).join('');
const lobby = ['你','林间客','晚风','松石'].map((name,seat)=>({name,seat,stack:1000,hole:[],card_count:2,last_action:'等待发牌'}));
$('opponents').innerHTML = lobby.slice(1).map(seatHTML).join('');
$('hero').innerHTML = seatHTML(lobby[0]);
arrangeSeats();
initialize();
