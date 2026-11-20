"use strict";
let deskData={}, editionBusy=false, deskDefault=null;
const slotTime=t=>new Date(t*1000).toLocaleTimeString("en-IN",{timeZone:"Asia/Kolkata",hour:"2-digit",minute:"2-digit",hour12:false});
const deskStamp=t=>t?indexStamp.format(t*1000)+" IST":"Not recorded";

function sourceLine(ctx={}){
 const fx=ctx.fx, fed=ctx.fed;
 return '<details class="context-sources"><summary>External context <span class="badge">Not a stock catalyst signal</span></summary><div class="source-grid">'+
 '<div><a href="https://www.ecb.europa.eu/stats/policy_and_exchange_rates/euro_reference_exchange_rates/html/index.en.html" target="_blank" rel="noopener">ECB daily reference</a><p>'+(fx?'USD/INR '+esc(fx.usd_inr)+'<small>As of '+esc(fx.date)+'</small>':'Unavailable')+'</p></div>'+
 '<div><a href="https://www.federalreserve.gov/feeds/feeds.htm" target="_blank" rel="noopener">Federal Reserve</a><p>'+(fed?esc(fed.title)+'<small>'+esc(deskStamp(fed.published))+'</small>':'Unavailable')+'</p></div></div></details>';
}

function reasoning(p,e,provisional){
 const v=p.evidence, id=p.id||e.slot+":"+p.symbol;
 const filing=e.context?.filings?.[p.symbol];
 const timeline=(p.timeline||[]).map(t=>'<li><b>'+esc(t.state)+'</b><span>'+esc(deskStamp(t.at))+(t.price?' | '+px(t.price):'')+'</span>'+(t.reason?'<small>'+esc(t.reason)+'</small>':'')+'</li>').join('');
 return '<details class="pick-reason" data-reason="'+esc(id)+'"><summary>Why these levels?</summary>'+
 (v?'<dl><dt>Evidence window</dt><dd>'+esc(deskStamp(v.window_start))+' to '+esc(slotTime(p.observed))+' IST; '+esc(v.observations)+' observations</dd>'+
 '<dt>Price pressure</dt><dd>'+esc(v.drift_percent)+'% across the window. Directional efficiency '+esc(v.efficiency)+' / 1 (not a probability).</dd>'+
 '<dt>Observed range</dt><dd>'+px(v.range_low)+' to '+px(v.range_high)+'</dd>'+
 '<dt>Entry rule</dt><dd>Verified price touch '+(p.direction==="Bearish"?'below':'above')+' the observed range at '+px(p.entry)+'. No entry at or beyond T1.</dd>'+
 '<dt>Risk distance</dt><dd>'+px(v.risk_points)+' = max(half the observed range, four spreads, '+px(.05)+'). Spread '+px(v.spread)+'.</dd>'+
 '<dt>Target basis</dt><dd>T1: 1 risk unit from entry. T2: 2 risk units. These are testable barriers, not predicted fair values.</dd>'+
 '<dt>Market confirmation</dt><dd>'+(e.nifty_move==null?'NIFTY five-minute context unavailable; not a confirmed tailwind.':esc(signedFmt.format(e.nifty_move*100))+'% five-minute NIFTY move. Opposing moves beyond 0.1% filter published candidates.')+'</dd>'+
 '<dt>Against the call</dt><dd>'+esc(v.counter_evidence)+'</dd></dl>':'<p>Detailed price evidence was not saved by this older version.</p>')+
 (filing?'<p>SEC '+esc(filing.form)+' published '+esc(deskStamp(filing.published))+'. Financial figures and earnings surprise have not been verified.</p>':'')+
 '<div class="evidence-gaps"><strong>Unverified company evidence</strong><p>News sentiment, profit/results surprise, company order book and full market depth are unavailable. They do not contribute to this rank.</p></div>'+
 (!provisional?'<h3>Recorded timeline</h3><ol class="event-line">'+(timeline||'<li>Timeline unavailable for this older record.</li>')+'</ol><a class="link" href="'+hist+'?edition='+e.slot+'&pick='+encodeURIComponent(p.symbol)+'">Open archived edition</a>':'<p class="muted">Provisional levels can change until publication. No entry is being tracked yet.</p>')+'</details>';
}

function paintEdition(){
 const selection=Number($("editionSlot").value), schedule=deskData.schedule||{}, editions=deskData.editions||[];
 let e=editions.find(r=>r.slot===selection);
 const window=(schedule.slots||[]).find(r=>r.slot===selection);
 const preview=deskData.preview||{}, provisional=!e&&selection===preview.for_slot&&preview.picks?.length>0;
 if(!e&&provisional)e={slot:selection,picks:preview.picks,connected:preview.connected,nifty_move:preview.nifty_move};
 const opened=new Set([...document.querySelectorAll('.pick-reason[open]')].map(x=>x.dataset.reason));
 const focused=document.activeElement?.closest('.pick-reason')?.dataset.reason;
 const keepExclusions=$("savedExclusions")?.open && $("savedExclusions").dataset.slot===String(selection);
 const phase=provisional?'Provisional':window?.phase||(e?'Archived':'No scheduled session');
 let html='<div class="window-status"><b>'+esc(phase)+'</b><span>'+esc(schedule.date||'')+' · All times IST</span>'+(isHistory?'':'<a href="'+hist+'?tab=forecasts">Past editions &rarr;</a>')+'</div>';
 if(selection){
 const t1=e?.t1_deadline||window?.t1_deadline||selection+600, t2=e?.t2_deadline||window?.t2_deadline||selection+1200;
 html+='<div class="window-stages">'+[['01','Entry watch',selection],['02','T1 deadline',t1],['03','T2 deadline',t2]].map(([n,label,t])=>'<div><span>'+n+'</span><p>'+label+'<strong>'+slotTime(t)+' <small>IST</small></strong></p></div>').join('')+'</div>';
 }
 if(provisional)html+='<p class="desk-callout">Developing candidates. Publication is at '+slotTime(selection)+' IST; qualification and levels can still change.</p>';
 else if(e)html+='<p class="desk-caption">Frozen at publication · Price observations, not order fills · Ranked by price efficiency, not certainty</p>';
 if(e){
 html+=table(['Rank / stock','Direction / waiting for','Entry / invalidation','T1 / T2','Evidence'],e.picks.map((p,i)=>[
 '<b class="rank-number">'+String(i+1).padStart(2,'0')+'</b><b>'+esc(p.symbol)+'</b><small>'+esc(p.state)+'</small>',
 '<b class="'+(p.direction==='Bearish'?'down':'up')+'">'+esc(p.direction)+'</b><small>'+(p.entered?'Entry '+esc(deskStamp(p.entered)):p.state==='Waiting'||provisional?'Verified trade '+(p.direction==='Bearish'?'at or below ':'at or above ')+px(p.entry):esc(p.state))+'</small>',
 px(p.entry)+'<small>Stop '+px(p.stop)+'</small>',px(p.t1)+'<small>T2 '+px(p.t2)+'</small>',
 '<small>'+(p.prior_calls?esc(p.prior_t1)+' / '+esc(p.prior_calls)+' prior calls reached T1 in time; '+esc(p.prior_days)+' sessions':'No comparable prior-session evidence')+'</small>'+reasoning(p,e,provisional)
 ]),e.connected?'No picks published for this window.':'Feed disconnected at publication.');
 if(!provisional){
 const d=e.diagnostics;
 html+=d?'<div class="window-status"><b>At publication</b><span>'+esc(d.subscribed)+' subscribed → '+esc(d.usable)+' with usable quotes → '+esc(d.qualified)+' qualified → '+esc(d.published)+' published</span></div>'+
 (d.excluded.length?'<details class="context-sources" id="savedExclusions"><summary>Why stocks were excluded ('+esc(d.excluded.length)+')</summary>'+table(['Stock','Verified observations','First reason'],d.excluded.map(r=>[esc(r.symbol),esc(r.observations??'Unknown'),esc(r.reason)]),'')+'</details>':''):
 '<p class="desk-caption">This older window did not record rejection reasons.</p>';
 }
 }else{
 const msg=!selection?(schedule.session==='unknown'?'Calendar unavailable for this date. No trade windows published.':'No supported trading windows today.'):
 window?.phase==='Not recorded'?'This window was not published. It will not be reconstructed using later prices.':
 preview.connected===false?'Broker disconnected. Scheduled times remain visible; no live candidate can be verified.':
 selection===preview.for_slot?'Waiting for five minutes of fresh observations and a qualifying setup.':'Candidate assessment starts in the 20 minutes before this window.';
 html+='<div class="window-empty"><strong>No actionable setup for this window</strong><p>'+esc(msg)+'</p></div>';
 }
 if(!isHistory&&selection===preview.for_slot&&preview.excluded?.length){
 html+='<details class="context-sources"><summary>Why other stocks did not qualify <span class="badge">'+preview.checked+' checked</span></summary>'+
 table(['Stock','Missing condition'],preview.excluded.map(p=>[esc(p.symbol),esc(p.reason)]),'')+'</details>';
 }
 html+=sourceLine(e?.context||deskData.context);
 $("editionReport").innerHTML=html;
 if($("savedExclusions")){ $("savedExclusions").dataset.slot=String(selection); $("savedExclusions").open=!!keepExclusions; }
 document.querySelectorAll('.pick-reason').forEach(x=>{
 if(opened.has(x.dataset.reason)||params.get('pick')===x.dataset.reason.split(':')[1])x.open=true;
 if(x.dataset.reason===focused)x.querySelector('summary').focus({preventScroll:true});
 });
 paintLearning();
}

function paintLearning(){
 const r=deskData.research;if(!r){$("learningReport").replaceChildren();return}
 const wasOpen=$("learningReport").querySelector('details')?.open;
 $("learningReport").innerHTML='<details class="learning-ledger" '+(wasOpen?'open':'')+'><summary>Learning ledger <span>'+esc(r.sessions)+' earlier sessions · '+esc(r.calls)+' calls</span></summary>'+
 '<p class="desk-caption">'+esc(r.version)+' · Prior 90 days only · '+esc(r.policy)+'</p>'+
 '<div class="learning-metrics"><div>Evaluated entries<strong>'+r.evaluated_entries+'</strong></div><div>On-time T1 after entry<strong>'+r.on_time_t1+'</strong></div><div>Insufficient data<strong>'+(r.states?.['Insufficient data']||0)+'</strong></div><div>Never entered<strong>'+((r.states?.['No entry']||0)+(r.states?.['Invalidated']||0)+(r.states?.['Missed move']||0))+'</strong></div></div>'+
 '<p>'+(r.entry_hit_interval?'Observed entry-hit rate: 95% uncertainty interval '+r.entry_hit_interval.join(' to ')+'%. Not a probability for the next call.':'Too little measured evidence to estimate an entry-hit rate.')+'</p>'+
 '<p>'+(r.median_winner_seconds!=null?'Among '+r.winner_timing_samples+' successful entries only, median time to T1 was '+Math.round(r.median_winner_seconds)+' seconds. This excludes failures and is not an ETA.':'No measured timing estimate yet. Deadlines are evaluation windows, not promises.')+'</p>'+
 '<p>Paired top-pick comparisons: '+r.paired_editions+'. Original T1 hits: '+r.baseline_top1_hits+'. Shadow T1 hits: '+r.shadow_top1_hits+'.</p>'+
 '<p class="muted">'+esc(r.news_model)+'. No rule is promoted automatically from these totals.</p></details>';
}

async function loadEditions(){
 if(prefix||editionBusy||document.hidden)return;editionBusy=true;
 try{
 const requested=isHistory&&/^\d+$/.test(params.get('edition')||'')?'?slot='+params.get('edition'):'';
 const compare=isHistory&&tab==="performance";
 const d=await get('/api/timed-editions'+requested+(compare?(requested?'&':'?')+'horizons=true':''));if(d.mode!=='live')return;
 if(compare){
 const panel=$("horizonTrials");panel.hidden=false;
 panel.innerHTML='<h2>T1 after entry: 10, 20 or 30 minutes?</h2><p>Same entered setups, frozen target and stop. Research only.</p>'+
 table(['From entry','T1 first / stop first','Timed exit','Missing / tracking','Too near close','Comparable entries / sessions','Mean net return'],(d.horizon_trials||[]).map(r=>[
 r.minutes+' min',r.hits+' / '+r.stops,r.timed,r.missing+' / '+r.tracking,r.late,r.paired+' / '+r.sessions,r.avg_net_bps==null?'Not measured':esc(r.avg_net_bps)+' bps'
 ]),'No new timed entries measured yet.')+'<small>Net return compares only entries with verified bid/ask exits for all three horizons, less an assumed 10 bps round trip. Not actual fees or fills. Entries without 30 minutes before close are excluded from comparison.</small>';
 }
 const study=d.mover_sweep?.news_trial;
 if(compare&&study){
 const fmt=v=>v==null?'Not measured':Number(v).toFixed(1)+' bps';
 $("horizonTrials").insertAdjacentHTML("beforeend",'<h2>Does news improve the forecast?</h2><p>Fixed eight-stock watchlist · Morning observation to first fresh quote after 15:00 IST · Shadow only</p>'+
 table(['Paired outcomes','Sessions','News changed direction','Missing past outcomes','Price alone','Price + news'],[[study.measured,study.sessions,study.changed,study.missing,fmt(study.price_net),fmt(study.news_net)]],'')+
 '<small>Mean simulated return after an assumed 10 bps per directional call; flat calls earn zero. Spread, slippage and actual fees are not modeled. No automatic promotion.</small>');
 }
 const old=$("editionSlot").value;deskData=d;
 paintMovers(d.daily_movers,d.mover_sweep);
 const options=isHistory?(d.editions||[]).map(e=>({slot:e.slot,phase:'Archived'})):(d.schedule?.slots||[]);
 $("editions").hidden=false;$("editionTitle").textContent=isHistory?'Timed forecast archive':"Today's trade windows";
 $("editionSlot").innerHTML=options.map(r=>'<option value="'+r.slot+'">'+esc(isHistory?indexStamp.format(r.slot*1000):slotTime(r.slot))+' · '+esc(r.phase)+'</option>').join('');
 const next=String(isHistory?(params.get('edition')||options[0]?.slot||''):(d.schedule?.selected_slot||''));
 const retain=old&&old!==deskDefault&&options.some(r=>String(r.slot)===old);
 $("editionSlot").value=retain?old:next;deskDefault=next;
 paintEdition();
 }catch{
 $("editions").hidden=false;
 const report=$("editionReport");
 if(!report.querySelector('.desk-error'))report.insertAdjacentHTML('afterbegin','<p class="desk-error" role="status">Timed research update failed. Any displayed data is from the previous successful request.</p>');
 }finally{editionBusy=false}
}

function moverReason(n){
 if(!n||!n.checked)return 'News lookup queued';
 const items=(n.items||[]).filter(a=>/^https:\/\//i.test(a.url));
 return '<b>'+esc(n.status)+'</b><small>Checked '+esc(deskStamp(n.checked))+'</small>'+items.map(a=>
 '<small>'+esc(a.kind)+' · <a target="_blank" rel="noopener noreferrer" href="'+esc(a.url)+'">'+esc(a.title)+'</a> · '+esc(a.publisher)+
 ' · Published '+esc(deskStamp(a.published))+' · '+(a.published>n.detected?'After scanner detection':'Before scanner detection; exact move time unknown')+'</small>').join('');
}
function paintMovers(d,sweep){
 const box=$("dailyMovers");if(!d){box.hidden=true;return}
 const expanded=box.querySelector('details')?.open;
 const previous=box.querySelector('.eq-discovery-scroll');
 const top=previous?.scrollTop||0,left=previous?.scrollLeft||0,focused=previous===document.activeElement;
 box.hidden=false;
 box.innerHTML='<h2>Today’s ±4% movers</h2>'+
 (sweep?'<h3>NSE EQ discovery</h3><p>'+esc(sweep.covered)+' stocks verified today / '+esc(sweep.universe||"unknown")+' in broker universe · '+esc(sweep.status)+'</p>'+
 '<div class="eq-discovery-scroll" role="region" aria-label="NSE EQ discovery stocks" tabindex="0">'+table(['Stock','Reached today','Latest snapshot','Quote as of (IST)','Why this move?'],sweep.movers.map(r=>[esc(r.symbol),
 [r.up?'High '+esc(signedFmt.format(r.high_pct))+'%':'',r.down?'Low '+esc(signedFmt.format(r.low_pct))+'%':''].filter(Boolean).join(' / '),
 px(r.price)+' ('+esc(signedFmt.format(r.current_pct))+'%)',esc(deskStamp(r.trade)),moverReason(r.news)]),sweep.covered?'No threshold reached in verified coverage.':'No dated EQ snapshots verified yet.')+
 '</div><p class="desk-caption">Session highs and lows can reveal an earlier move. Exact touch time and news cause are unknown.</p>':'')+
 '<h3>Live research sample</h3><p class="desk-caption">'+esc(d.day)+' IST · '+esc(d.covered)+' monitored stocks with a verified reference close · First observed touches, not closing returns</p>'+
 table(['Stock','First move','At touch / previous close','Market context','Company evidence'],d.movers.map(r=>{
 const f=r.filing;
 return [esc(r.symbol),'<b class="'+(r.side==='Up'?'up':'down')+'">'+esc(signedFmt.format(r.percent))+'%</b><small>'+esc(deskStamp(r.at))+'</small>',
 px(r.price)+' / '+px(r.close)+(r.first_observation===r.at?'<small>Already beyond threshold at first observation</small>':r.first_observation?'<small>First seen '+esc(signedFmt.format(r.initial_pct))+'% at '+esc(slotTime(r.first_observation))+' IST</small>':''),
 r.nifty_pct==null?'No fresh NIFTY comparison':'NIFTY '+esc(signedFmt.format(r.nifty_pct))+'%; stock minus index '+esc(signedFmt.format(r.percent-r.nifty_pct))+' points',
 f?(/^https:\/\/www\.sec\.gov\/Archives\/edgar\//.test(f.url)?'<a href="'+esc(f.url)+'" target="_blank" rel="noopener">SEC '+esc(f.form)+'</a>':'SEC '+esc(f.form))+' filed '+esc(deskStamp(f.published))+'. Cause unconfirmed.':'No verified company-specific cause.'];
 }),d.covered?'No ±4% move observed in this coverage.':'No verified stock observations with previous closes today.')+
 '<details '+(expanded?'open':'')+'><summary>Before the move: research forecasts</summary><p>First observed stock move and half-hour compared with earlier sessions. '+esc(d.training_examples)+' eligible historical examples. No live ranking changes.</p><p>Measured prior forecasts: '+esc(d.paired)+'. Model correct: '+esc(d.correct)+'. Always predict neither: '+esc(d.neither_correct)+'. Incomplete coverage can bias these counts.</p>'+
 table(['Stock','Observed at start','Shadow forecast','Earlier examples','Measured outcome'],d.forecasts.map(r=>[esc(r.symbol),esc(signedFmt.format(r.start_pct))+'%<small>'+esc(deskStamp(r.start))+'</small>',
 esc(r.prediction||'Insufficient evidence'),Object.entries(r.prior_counts).map(([k,v])=>esc(k)+': '+esc(v)).join(', ')||'None',esc(r.outcome||'Not measured')]),'No pre-threshold observations yet.')+'</details>';
 const region=box.querySelector('.eq-discovery-scroll');
 if(region&&previous){region.scrollTo(left,top);if(focused)region.focus({preventScroll:true})}
}
