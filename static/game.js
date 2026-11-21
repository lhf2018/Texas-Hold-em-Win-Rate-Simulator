'use strict';
const $ = id => document.getElementById(id);
let state = null, busy = false, botTimer = null, analysisEpoch = 0, analysisController = null;
$('analysisToggle').checked = localStorage.getItem('poker-analysis') === 'on';
function escapeHTML(value) { return String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }
function cardHTML(card, back = false) {
  if (back) return '<div class="card back" aria-label="隐藏底牌">♠</div>';
  if (!card) return '<div class="card empty" aria-label="未发公共牌">♧</div>';
  return `<div class="card ${['♥','♦'].includes(card.suit) ? 'red' : ''}" aria-label="${escapeHTML(card.code)}"><span>${escapeHTML(card.rank)}</span><span>${escapeHTML(card.suit)}</span></div>`;
}
function seatHTML(player) {
  const won = state?.done ? (state.result || []).filter(r=>r.seats.includes(player.seat)).reduce((sum,r)=>{
    const ordered = [...r.seats];
    const index = ordered.indexOf(player.seat);
    return sum + Math.floor(r.amount / ordered.length) + (index < r.amount % ordered.length ? 1 : 0);
  },0) : 0;
  const current = state?.actor === player.seat && !state?.done;
  const last = state?.history?.at(-1);
  const latest = last?.seat === player.seat;
  const action = latest ? last.action : player.last_action || '';
  const actionKind = action.includes('弃牌') ? 'fold' : action.includes('加注') ? 'raise' : action.includes('跟注') ? 'call' : action.includes('过牌') ? 'check' : 'blind';
  const cards = player.hole.length ? player.hole.map(c => cardHTML(c)).join('') : Array.from({length: player.card_count}, () => cardHTML(null, true)).join('');
  return `<div class="seat ${current ? 'active' : ''} ${player.folded ? 'folded' : ''} ${latest ? 'latest-action' : ''} ${won ? 'winner' : ''}" data-action-kind="${actionKind}" data-blind="${player.blind || ''}" data-seat="${player.seat}">${player.blind ? `<div class="blind-badge ${player.blind.toLowerCase()}" aria-label="${player.blind === 'SB' ? '小盲 10' : '大盲 20'}"><b>${player.blind}</b><span>${player.blind === 'SB' ? '小盲 10' : '大盲 20'}</span></div>` : ''}<div class="turn-badge">决策中</div><div class="seat-name">${escapeHTML(player.name)}${player.dealer ? '<span class="dealer" title="庄家">D</span>' : ''}</div><div class="stack">◉ ${player.stack.toLocaleString()}</div><div class="seat-action">${escapeHTML(player.hand_type || player.last_action)}${player.allin ? ' · ALL IN' : ''}</div><div class="small-cards">${cards}</div>${won ? `<div class="winner-badge">♛ 获胜 <strong>+${won.toLocaleString()}</strong></div><div class="winner-sparks" aria-hidden="true">${Array.from({length:8},(_,i)=>`<i style="--spark:${i}"></i>`).join('')}</div>` : ''}${latest && !won ? `<div class="action-badge">${escapeHTML(player.last_action)}</div>` : ''}</div>`;
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
    return `<div class="player-bet ${player.folded ? 'bet-folded' : ''}" data-edge="${edge}" style="left:${(felt.left-scene.left)+felt.width*px}px;top:${(felt.top-scene.top)+felt.height*py}px" aria-label="${escapeHTML(player.name)} 本手投入 ${player.total}"><div class="chip-piles">${stacks.slice(0,3).join('')}</div><span class="bet-amount">${player.total.toLocaleString()}</span></div>`;
  }).join('');
}
window.addEventListener('resize',()=>requestAnimationFrame(renderTableBets));
function showError(message) { $('error').textContent = message; $('error').hidden = !message; }
async function api(url, payload, signal) {
  const response = await fetch(url, {method: payload === undefined ? 'GET' : 'POST', headers: {'Content-Type':'application/json'}, body: payload === undefined ? undefined : JSON.stringify(payload), signal});
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || '请求失败，请重试');
  return data;
}
function render() {
  if (!state) return;
  $('handLabel').textContent = `第 ${String(state.hand).padStart(2,'0')} 手 · 庄家 ${state.players.find(p=>p.dealer).name}`;
  $('stageLabel').textContent = state.done ? '本手结束' : state.stage;
  $('turnLabel').textContent = state.done ? '等待下一手' : state.actor === 0 ? '轮到你行动' : `${state.players[state.actor].name} 的回合`;
  $('tableSize').textContent = `${state.player_count} 人局 · ${state.players.filter(p=>p.stack > 0 || (!state.done && !p.folded)).length} 人在桌`;
  $('startingStack').textContent = `起始筹码 ${state.starting_stack.toLocaleString()}`;
  $('opponents').dataset.count = state.players.length - 1;
  $('pot').textContent = state.pot.toLocaleString();
  $('board').innerHTML = Array.from({length:5}, (_,i)=>cardHTML(state.board[i])).join('');
  $('opponents').innerHTML = state.players.slice(1).map(seatHTML).join('');
  arrangeSeats();
  $('hero').innerHTML = seatHTML(state.players[0]);
  document.querySelector('.table-scene').dataset.turn = state.actor ?? '';
  $('tableMessage').textContent = state.done ? '本手已结算 · 筹码已发放' : state.actor === 0 ? '轮到你了，想好再出手。' : `${state.players[state.actor].name} 正在思考…`;
  const yourTurn = !state.done && state.actor === 0;
  $('actions').hidden = false;
  $('raiseControls').hidden = false;
  document.querySelector('.action-area').dataset.mode = state.done ? 'done' : yourTurn ? 'your-turn' : 'waiting';
  $('call').disabled = $('fold').disabled = busy || !yourTurn;
  $('raise').disabled = busy || !yourTurn || !state.legal?.can_raise;
  for (const id of ['raiseAmount','halfPot','potRaise','allin']) $(id).disabled = busy || !yourTurn || !state.legal?.can_raise;
  $('raiseHint').textContent = state.raise_used ? '本轮已加注' : '';
  $('deal').hidden = !state.done;
  $('actionTitle').textContent = state.done ? (state.players[0].stack ? '本手结束' : '本场练习结束') : yourTurn ? '轮到你行动' : '等待对手行动';
  $('callHint').textContent = yourTurn ? `可用筹码 ${state.players[0].stack.toLocaleString()} 点` : '';
  if (yourTurn) {
    const legal = state.legal;
    $('call').textContent = legal.call ? `跟注 ${legal.call}${legal.call === state.players[0].stack ? ' · 全下' : ''}` : '过牌';
    $('call').disabled = $('fold').disabled = busy;
    $('raise').disabled = busy || !legal.can_raise;
    $('raise').textContent = legal.raise_used ? '本轮已加注' : legal.short_allin && legal.can_raise ? `全下至 ${legal.max_raise_to}` : '加注';
    $('raiseAmount').min = Math.min(legal.min_raise_to, legal.max_raise_to);
    $('raiseAmount').max = legal.max_raise_to;
    $('raiseAmount').value = Math.min(legal.min_raise_to, legal.max_raise_to);
    if (legal.can_raise) $('raiseHint').textContent = `最低 ${Math.min(legal.min_raise_to,legal.max_raise_to)} · 最高 ${legal.max_raise_to}`;
  }
  const tableOver = state.players[0].stack === 0 || state.players.filter(p=>p.stack > 0).length < 2;
  $('deal').textContent = tableOver ? '重新开桌 →' : '发下一手 →';
  $('deal').disabled = busy;
  $('result').hidden = true;
  let lastStreet = -1;
  $('history').innerHTML = state.history.map(e=>{
    let label = '';
    if (e.street !== lastStreet) { lastStreet = e.street; label = `<li class="street">${['翻牌前','翻牌','转牌','河牌'][e.street]}</li>`; }
    return label + `<li><span>${escapeHTML(e.name)}</span><b>${escapeHTML(e.action)}${e.amount ? ' '+e.amount : ''}</b></li>`;
  }).join('');
  $('history').scrollTop = $('history').scrollHeight;
  requestAnimationFrame(()=>{ renderTableBets(); celebrateWinners(); });
}
function cancelAnalysis() { analysisEpoch++; analysisController?.abort(); analysisController = null; }
async function updateAnalysis() {
  cancelAnalysis();
  const epoch = analysisEpoch, enabled = $('analysisToggle').checked;
  $('analysisOff').hidden = enabled;
  $('analysisContent').hidden = !enabled;
  $('analysisData').hidden = true;
  if (!enabled) return;
  if (!state || state.done || state.actor !== 0) {
    $('analysisStatus').textContent = !state ? '等待发牌' : state.done ? '本手结束' : '等待你的回合';
    return;
  }
  $('analysisStatus').textContent = '计算中…';
  const version = state.version;
  analysisController = new AbortController();
  try {
    const d = await api('/api/game/analyze', undefined, analysisController.signal);
    if (epoch !== analysisEpoch || !$('analysisToggle').checked || state.version !== version || d.version !== version) return;
    $('analysisStatus').textContent = `你的视角 · ${d.samples.toLocaleString()} 次模拟`;
    $('equity').innerHTML = `${d.equity}<small>%</small>`;
    $('equityBar').style.width = d.equity+'%';
    $('winRate').textContent = d.win_rate+'%'; $('tieRate').textContent = d.tie_rate+'%';
    $('ev').textContent = `${d.ev > 0 ? '+' : ''}${d.ev} 点`; $('potOdds').textContent = d.pot_odds+'%';
    $('handStrength').textContent = `当前牌型 · ${d.hand_strength.type}`;
    $('suggestion').textContent = d.suggestion;
    $('draws').textContent = d.draw_potential.draws.length ? d.draw_potential.draws.map(x=>`${x.type} · ${x.outs} outs · 到河牌成牌 ${x.probability}%`).join('；')+`。去重后共 ${d.draw_potential.total_outs} outs。` : '';
    $('ranges').innerHTML = d.ranges.map(r=>`${escapeHTML(r.name)} · ${escapeHTML(r.range)}`).join('<br>');
    $('assumption').textContent = d.assumption;
    $('analysisData').hidden = false;
  } catch (e) { if (epoch === analysisEpoch && e.name !== 'AbortError') $('analysisStatus').textContent = `分析暂不可用：${e.message}`; }
}
function scheduleBot() {
  clearTimeout(botTimer);
  if (state && !state.done && state.actor !== 0) botTimer = setTimeout(()=>mutate('step'), 650);
}
async function mutate(operation, data = {}) {
  if (busy) return;
  busy = true; showError(''); cancelAnalysis(); clearTimeout(botTimer);
  render();
  try {
    state = await api(`/api/game/${operation}`, operation === 'new' ? data : {version:state.version,...data});
  } catch (e) {
    showError(e.message);
    try { const latest = await api('/api/game'); if (!latest.empty) state = latest; } catch (_) {}
  } finally {
    busy = false; render(); updateAnalysis(); scheduleBot();
  }
}
function setRaise(target) { if (state?.legal) $('raiseAmount').value = Math.round(Math.min(state.legal.max_raise_to, Math.max(Math.min(state.legal.min_raise_to,state.legal.max_raise_to),target))); }
$('fold').onclick = ()=>mutate('action',{action:'fold'});
$('call').onclick = ()=>mutate('action',{action:state.legal.call ? 'call' : 'check'});
$('raise').onclick = ()=>{
  const amount = Number($('raiseAmount').value);
  const l = state.legal;
  if (!Number.isInteger(amount) || amount > l.max_raise_to || amount < Math.min(l.min_raise_to,l.max_raise_to)) { showError('请输入合法的整数加注额。'); return; }
  mutate('action',{action:'raise',amount});
};
$('halfPot').onclick = ()=>setRaise(state.players[0].bet + state.legal.call + Math.floor((state.pot+state.legal.call)/2));
$('potRaise').onclick = ()=>setRaise(state.players[0].bet + state.legal.call + state.pot + state.legal.call);
$('allin').onclick = ()=>setRaise(state.legal.max_raise_to);
$('deal').onclick = ()=> !state || state.players[0].stack === 0 || state.players.filter(p=>p.stack>0).length<2 ? openSettings() : mutate('next');
function openSettings() {
  $('playerCount').value = state?.player_count || 4;
  $('startingChips').value = state?.starting_stack || 1000;
  $('restartDialog').showModal();
}
$('restart').onclick = openSettings;
$('cancelRestart').onclick = ()=>$('restartDialog').close();
$('tableSettings').onsubmit = event=>{
  event.preventDefault();
  if (!$('tableSettings').reportValidity()) return;
  const starting_stack = Number($('startingChips').value);
  if (!Number.isInteger(starting_stack)) return;
  $('restartDialog').close();
  mutate('new', {player_count:Number($('playerCount').value), starting_stack});
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
