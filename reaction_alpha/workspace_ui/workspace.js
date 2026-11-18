"use strict";
const $=id=>document.getElementById(id), esc=x=>String(x??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const money=new Intl.NumberFormat("en-IN",{style:"currency",currency:"INR",maximumFractionDigits:2}), px=x=>x!=null&&Number.isFinite(+x)?money.format(+x):"Not available";
const prefix=/^\/demo(?:\/|$)/.test(location.pathname)?"/demo":"", home=prefix||"/", api="/api"+prefix, hist=prefix+"/history";
const path=location.pathname.slice(prefix.length), isHistory=/history|journal|archive/.test(path);
const params=new URLSearchParams(location.search), tab=path.includes("analytics")?"performance":path.includes("journal")?"trades":params.get("tab")||"forecasts";
const target=params.get("setup")||location.hash.match(/^#setup-(\d+)$/)?.[1];
const bands={"trade-ready":"Trade ready","near-trigger":"Near trigger","high-edge watch":"High-edge watch",watchlist:"Watchlist",avoid:"Avoid"};
let setups=[],selected="",filter=params.get("band")||"all",sort=params.get("sort")||"rank",loading=false;
let queuedRefresh=false,scanStarted=0,ticker={};
const direction=s=>["BULLISH","LONG","BUY"].includes(String(s.side||s.direction||s.trade_direction).toUpperCase())?"Bullish":["BEARISH","SHORT","SELL"].includes(String(s.side||s.direction||s.trade_direction).toUpperCase())?"Bearish":"Neutral";
const condition=s=>s.scanner_band==="avoid"?"Avoid: no entry":s.entered_at?"Entry recorded; tracking exits":s.trigger_price==null?"Entry not published":(direction(s)==="Bearish"?"Tick at or below ":"Tick at or above ")+px(s.trigger_price);
const fmtTime=d=>new Date(d).toLocaleTimeString("en-IN",{timeZone:"Asia/Kolkata",hour12:false})+" IST";
async function get(url,options={}){const r=await fetch(url,{cache:"no-store",signal:AbortSignal.timeout(30000),...options});if(!r.ok)throw Error("Request failed");return r.json()}
function table(head,rows,empty){return rows.length?'<table class="grid"><thead><tr>'+head.map(x=>'<th>'+esc(x)+'</th>').join("")+'</tr></thead><tbody>'+rows.map(r=>'<tr>'+r.map((x,i)=>'<td data-label="'+esc(head[i])+'">'+x+'</td>').join("")+'</tr>').join("")+'</tbody></table>':'<p class="empty">'+esc(empty)+'</p>'}
function note(title,msg){$("notice").innerHTML='<div class="note"><b>'+esc(title)+'</b><small>'+esc(msg)+'</small></div>'}
function nav(id,url,active){$(id).href=url;if(active)$(id).setAttribute("aria-current","page")}
nav("brand",home,false);nav("scannerNav",home,!isHistory);nav("historyNav",hist,isHistory);$("mode").value=prefix;
$("mode").onchange=()=>{location.href=($("mode").value||"")+(location.pathname.slice(prefix.length)||"/")+location.search+location.hash};
function scanUrl(symbol){const u=new URL(symbol?prefix+"/stock/"+encodeURIComponent(symbol):home,location.origin);if(filter!=="all")u.searchParams.set("band",filter);if(sort!=="rank")u.searchParams.set("sort",sort);return u.pathname+u.search}
function scanner(){
 const actionable=setups.filter(s=>s.scanner_band==="trade-ready");
 if(!actionable.length){const candidates=setups.filter(s=>s.scanner_band!=="avoid"&&s.trigger_price>0&&s.ltp>0);
 const distance=s=>Math.abs(s.trigger_price/s.ltp-1);candidates.sort((a,b)=>distance(a)-distance(b));
 note("No actionable setups",candidates.length?"Nearest candidate: "+candidates[0].symbol+" | "+condition(candidates[0]):"No eligible candidate with a published trigger.");}else $("notice").replaceChildren();
 const rows=setups.filter(s=>filter==="all"?s.scanner_band!=="avoid":s.scanner_band===filter);
 if(sort==="symbol")rows.sort((a,b)=>a.symbol.localeCompare(b.symbol));
 $("tools").innerHTML='<div class="toolbar"><b>Ranked setups <small> / '+rows.length+'</small></b><div class="controls"><select aria-label="Readiness filter" id="band"><option value="all">All except Avoid</option>'+Object.entries(bands).map(([k,v])=>'<option value="'+k+'">'+v+'</option>').join("")+'</select><select id="sort" aria-label="Sort setups"><option value="rank">Rank order</option><option value="symbol">Symbol A-Z</option></select></div></div>';
 $("band").value=filter;$("sort").value=sort;
 $("band").onchange=$("sort").onchange=()=>{filter=$("band").value;sort=$("sort").value;history.replaceState(null,"",scanUrl());scanner()};
 $("content").innerHTML=table(["Stock","Outlook","Readiness","Last price","Entry condition","Invalidation"],rows.map(s=>[
 '<a data-stock="'+esc(s.symbol)+'" href="'+esc(scanUrl(s.symbol))+'">'+esc(s.symbol)+'</a><small>'+esc(s.sector)+'</small>',
 '<b class="'+(direction(s)==="Bearish"?"down":"up")+'">'+direction(s)+'</b><small>30 min</small>',
 '<span class="badge '+(s.scanner_band==="trade-ready"?"ready":s.scanner_band==="near-trigger"?"warn":"")+'">'+esc(bands[s.scanner_band]||"Watching")+'</span>','<span data-price="'+esc(s.symbol)+'">'+px(s.ltp)+'</span><small data-quote-time>Scan snapshot</small>',esc(condition(s)),px(s.stop_loss)]),"No setups match this filter.");
 paintTicker();
 if(selected)document.querySelector('a[data-stock="'+CSS.escape(selected)+'"]')?.closest("tr").classList.add("selected");
}
function outcome(r){if(r.first_barrier==="T1"&&r.result==="SL_HIT")return "T1 before stop";return ({INVALIDATED:"Invalidated",UNRESOLVED:"Insufficient data",MISSED_ENTRY:"Never entered",OPEN:r.entered_at?"Entry recorded":"Waiting for entry",T2_HIT:"T2 reached",SL_HIT:"Stop reached"})[r.result]||r.result}
async function historyView(){
 $("title").textContent="Research history";
 $("tools").innerHTML='<div class="tabs">'+[["forecasts","Forecasts"],["trades","Paper trades"],["performance","Performance"]].map(([k,v])=>'<a '+(k===tab?'aria-current="page"':'')+' href="'+hist+'?tab='+k+'">'+v+'</a>').join("")+'</div>';
 if(tab==="forecasts"){
 const data=await get(api+"/pretrade/archive"+(target?"?setup_id="+encodeURIComponent(target):""));
 $("content").innerHTML=table(["Forecast","Direction","Lifecycle","Entry","Stop","Targets"],data.recent.map(r=>[
 '<b>'+esc(r.symbol)+'</b><small>#'+esc(r.id)+' | '+esc(r.setup_type)+'</small>',esc(r.direction)+'<small>30 min: '+esc(r.direction_30m||"Not measured")+'</small>',
 '<b>'+esc(outcome(r))+'</b><details '+(String(r.id)===target?"open":"")+'><summary>Timeline</summary>'+[["Published",r.timeline_ist?.created_at],["Entry",r.timeline_ist?.entered_at],["T1",r.timeline_ist?.t1_at],["Exit",r.timeline_ist?.exited_at],["Deadline",r.timeline_ist?.expires_at]].map(([k,v])=>'<small>'+k+': '+esc(v||"Not observed")+'</small>').join("")+'</details>',px(r.entry_trigger),px(r.stop_loss),px(r.target1)+' / '+px(r.target2)]),target?"Forecast not found in this workspace.":"No forecasts published this session.");
 }else{const d=await get(api+"/paper-trades"),a=d.analytics||{};
 if(tab==="trades")$("content").innerHTML=table(["Paper trade","Direction","State","Entry fill","Stop","Result"],d.trades.map(t=>[esc(t.symbol),esc(t.direction),esc(t.state),px(t.trigger_price),px(t.stop_loss),esc(t.result||"Open")]),"No paper entries this session.")+'<h2>Pending triggers</h2>'+table(["Stock","Entry","Status"],d.pending_triggers.map(t=>[esc(t.symbol),px(t.entry_trigger),esc(t.status)]),"No pending paper triggers.");
 else {const f=await get(api+"/pretrade/archive");$("content").innerHTML='<h2>Paper execution</h2><div class="summary">'+[["Open",a.open_trades],["Closed",a.closed_trades],["Average P&L (points)",a.closed_trades?a.avg_pnl_points:"Not measured"]].map(([k,v])=>'<div>'+esc(k)+'<b>'+esc(v)+'</b></div>').join("")+'</div><h2>30-minute direction</h2>'+table(["Source","Published","Measured","Paired","Scanner correct","Market correct"],(f.direction_30m_by_source||[]).map(r=>[r.source,r.published,r.measured,r.paired,r.scanner_correct,r.market_correct].map(esc)),"No measured forecast comparisons yet.");const m=f.experience;if(m)$("content").insertAdjacentHTML("beforeend","<h2>Experience memory</h2><p>"+esc(m.storage)+" | Pending uploads: "+esc(m.pending_upload??"Not connected")+" | Last model refresh: "+esc(m.last_sync||"None")+"</p>"+table(["Source","Setup","Original direction","Earlier outcomes","Sessions","Paired","Shadow correct","Original correct"],m.groups.map(g=>[g.source,g.setup,g.direction,g.n,g.days,g.paired,g.learned_correct,g.original_correct].map(esc)),"No earlier measured sessions yet."));}}
}
async function detail(symbol){selected=symbol;const s=setups.find(x=>x.symbol===symbol),dlg=$("detail");if(!dlg.open)dlg.showModal();
 $("detailBody").innerHTML='<div class="eyebrow">STOCK DETAIL</div><h2 id="detailTitle">'+esc(symbol)+'</h2>';
 if(!s){const d=await get(api+"/signals/"+encodeURIComponent(symbol));if(selected===symbol)$("detailBody").insertAdjacentHTML("beforeend",'<p>No ranked setup for this symbol.</p><dl><dt>Signal state</dt><dd>'+esc(d.state||"Not active")+'</dd><dt>Last observation</dt><dd>'+esc(d.observation_ist||"Not recorded")+'</dd><dt>Last price</dt><dd>'+px(d.last_price)+'</dd></dl>');return}
 const fields=[["Outlook",direction(s)+" / 30 min"],["Setup",s.setup_type],["Entry condition",condition(s)],["Invalidation",px(s.stop_loss)],["T1 / T2",px(s.target1)+" / "+px(s.target2)],["Last observation",s.price_as_of_ist],["Deadline",s.expires_at_ist],["Selector score",s.final_selector_score??s.score],["Counter-evidence",[s.why_not_higher,s.missing_confirmation].flat().filter(Boolean)[0]||"Not recorded"]];
 if(s.shadow)fields.push(["Learning forecast (shadow)",(s.shadow.direction||"Insufficient evidence")+" | "+s.shadow.examples+" examples across "+s.shadow.sessions+" earlier sessions"]);
 $("detailBody").insertAdjacentHTML("beforeend",'<span class="badge">'+esc(bands[s.scanner_band])+'</span><dl>'+fields.map(([k,v])=>'<dt>'+esc(k)+'</dt><dd>'+esc(v??"Not recorded")+'</dd>').join("")+'</dl>'+(s.setup_id?'<a class="link" href="'+hist+'?setup='+encodeURIComponent(s.setup_id)+'">Forecast #'+esc(s.setup_id)+' timeline &rarr;</a>':""))}
function closeDetail(){if(history.state?.drawer)history.back();else{history.replaceState(null,"",scanUrl());syncDetail()}}
function syncDetail(){const sym=location.pathname.match(/\/stock\/([^/]+)/)?.[1];if(sym)detail(decodeURIComponent(sym)).catch(()=>note("Stock data unavailable","Refresh to retry."));else{if($("detail").open)$("detail").close();if(!isHistory){scanner();document.querySelector('a[data-stock="'+CSS.escape(selected)+'"]')?.focus({preventScroll:true})}}}
$("close").onclick=closeDetail;$("detail").oncancel=e=>{e.preventDefault();closeDetail()};window.onpopstate=syncDetail;
$("content").onclick=e=>{const a=e.target.closest("a[data-stock]");if(!a||e.ctrlKey||e.metaKey)return;e.preventDefault();history.pushState({drawer:true},"",a.href);syncDetail()};
$("brokerForm").onsubmit=async event=>{
 event.preventDefault();
 const form=event.currentTarget,button=form.querySelector("button"),fields=new FormData(form);
 if(button.disabled)return;
 button.disabled=true;form.reset();$("brokerResult").textContent="Reconnecting to Kotak...";
 try{
 const headers={"Content-Type":"application/json"};
 if(fields.get("secret"))headers["X-Reaction-Alpha-Secret"]=fields.get("secret");
 const response=await fetch("/api/kotak/totp",{method:"POST",headers,body:JSON.stringify({totp_code:fields.get("code")})});
 const ok=response.ok&&(await response.json()).ok;
 $("brokerResult").textContent=ok?"Login accepted. Waiting for a fresh verified trade.":"Login failed. Check the current TOTP and admin secret.";
 if(ok)void load(false,true);
 }catch{$("brokerResult").textContent="Could not confirm login. Check feed status before retrying."}
 finally{button.disabled=false}
};
async function load(force=false,healthOnly=false){if(loading){if(force){queuedRefresh=true;$("refreshStatus").textContent="Refresh queued";$("refresh").disabled=true}return}loading=true;
 if(force){$("refresh").disabled=true;$("refreshStatus").textContent=isHistory?"Refreshing history...":"Running scan..."}
 try{
 try{
 const h=await get(prefix?api+"/snapshot":"/api/health"),f=h.feed_connection||{},sim=prefix||h.mode==="simulated",t=f.last_verified_trade_epoch,age=Date.now()/1000-t;
 const verified=!sim&&f.status==="live"&&t&&age>=0&&age<=15;
 $("brokerReconnect").hidden=!!sim||!!verified;
 $("connection").textContent=sim?"Demo / simulated prices":verified?"Live / verified trades":f.status==="live"?"Live / stale or unverified":"Live / disconnected";
 $("connection").className=verified?"good":"";$("tradeTime").textContent=t?indexStamp.format(t*1000)+" IST":"None verified";
 if(!prefix&&h.mode!=="simulated"&&(await get("/api/kotak/login-state")).state==="totp_required"){location.reload();return}
 }catch{$("connection").textContent="Feed status unavailable";$("connection").className=""}
 if(healthOnly)return;
 if(isHistory)await historyView();else{const d=await get(api+"/pretrade/top"+(force?"?force=true":""));setups=d.setups||[];scanStarted=d.scan_started_epoch||0;scanner();if(d.status==="fallback")$("connection").textContent="Cached snapshot / unverified";const sym=location.pathname.match(/\/stock\/([^/]+)/)?.[1];if(sym)await detail(decodeURIComponent(sym))}
 $("refreshTime").textContent=fmtTime(Date.now())
 if(force)$("refreshStatus").textContent="Updated "+$("refreshTime").textContent;
 }catch{if(force)$("refreshStatus").textContent="Refresh failed. Retry." ;note("Data unavailable","The latest request failed. Previously displayed values are not verified.");$("connection").textContent="Connection unavailable";$("connection").className=""}finally{loading=false;$("refresh").disabled=false;if(queuedRefresh){queuedRefresh=false;void load(true)}}}
$("refresh").onclick=()=>{load(true);loadEditions()};load();setInterval(()=>{if(!document.hidden)load(false,$("detail").open||!!document.querySelector("details[open]")||document.activeElement?.matches("select"))},15000);

const levelFmt=new Intl.NumberFormat("en-IN",{minimumFractionDigits:2,maximumFractionDigits:2});
const signedFmt=new Intl.NumberFormat("en-IN",{minimumFractionDigits:2,maximumFractionDigits:2,signDisplay:"exceptZero"});
const indexStamp=new Intl.DateTimeFormat("en-GB",{timeZone:"Asia/Kolkata",day:"2-digit",month:"short",year:"numeric",hour:"2-digit",minute:"2-digit",second:"2-digit",hour12:false});
let stripBusy=false,lastQuotes=new Map();
function paintTicker(){
 document.querySelectorAll("[data-price]").forEach(el=>{
   const q=ticker[el.dataset.price];if(!q||q.epoch<scanStarted)return;
   const value=px(q.price),label=q.status+" | "+fmtTime(q.epoch*1000)+(q.status==="live"&&q.has_book===false?" | No verified bid/ask":"");
   if(el.textContent!==value)el.textContent=value;
   if(el.nextElementSibling.textContent!==label)el.nextElementSibling.textContent=label;
 });
}
function paintQuotes(rows){
 $("indexRows").innerHTML=rows.map(r=>{
   const prev=lastQuotes.get(r.name),changed=r.status==="live"&&prev&&r.epoch>prev.epoch&&r.level!==prev.level;
   return '<div class="index-quote"><div class="index-head"><b>'+esc(r.name)+'</b><span class="badge '+(r.status==="live"?"ready":"")+'">'+esc(r.status)+'</span></div><div class="index-values"><b class="'+(changed?"price-update":"")+'">'+(r.level==null?"&mdash;":levelFmt.format(r.level))+'</b><span class="'+(r.change>0?"up":r.change<0?"down":"")+'">'+(r.change==null?"Change unavailable":signedFmt.format(r.change)+" ("+signedFmt.format(r.percent)+"%)")+'</span></div><small>'+(r.epoch?esc(indexStamp.format(r.epoch*1000))+" IST":"No timestamped quote")+'</small></div>';
 }).join("");lastQuotes=new Map(rows.map(r=>[r.name,r]));
}
function renderStrip(d){
 const bias=d.market_read||{};
 $("marketBias").textContent=bias.label||"Direction unconfirmed";
 $("marketBias").className=bias.label?.endsWith("Bearish")?"down":bias.label?.endsWith("Bullish")?"up":"";
 $("marketWhy").textContent=bias.reason||"Waiting for verified index changes.";
 $("cashSession").textContent="NSE cash session: "+d.session;
 $("scanActivity").textContent=d.scan?"Last scan: "+indexStamp.format(d.scan.epoch*1000)+" IST | "+d.scan.symbols+" symbols":"No completed scan yet";
 paintQuotes(d.indices);ticker=d.quotes||{};paintTicker();
}
let quoteStream=null,streamReady=false;
function connectQuoteStream(){
 if(!("EventSource" in window)||document.hidden||quoteStream)return;
 const stream=quoteStream=new EventSource(api+"/market-strip/stream");
 stream.onmessage=e=>{if(stream!==quoteStream)return;renderStrip(JSON.parse(e.data));streamReady=true};
 stream.onerror=()=>{if(stream===quoteStream){streamReady=false;updateStrip()}};
}
async function updateStrip(){
 if(streamReady)return;
 if(stripBusy||document.hidden)return;stripBusy=true;
 try{const d=await get(api+"/market-strip",{signal:AbortSignal.timeout(5000)});
   if(!streamReady)renderStrip(d);
 }catch{
   if(streamReady)return;
   $("cashSession").textContent="Session unknown | index feed unavailable";
   $("marketBias").textContent="Direction unconfirmed";$("marketBias").className="";$("marketWhy").textContent="Index feed unavailable.";
   Object.values(ticker).forEach(q=>q.status="stale");paintTicker();
   const rows=[...lastQuotes.values()];paintQuotes(rows.map(r=>({...r,status:r.level==null?"unavailable":"last known"})));
 }finally{stripBusy=false}
}
if(!isHistory){
 $("marketStrip").hidden=false;paintQuotes(["NIFTY 50","SENSEX","BANK NIFTY"].map(name=>({name,status:"unavailable"})));
 connectQuoteStream();updateStrip();setInterval(updateStrip,1000);
 document.addEventListener("visibilitychange",()=>{
   if(document.hidden){quoteStream?.close();quoteStream=null;streamReady=false}
   else{connectQuoteStream();updateStrip()}
 });
}
$("editionSlot").onchange=paintEdition;
if(!prefix){loadEditions();setInterval(loadEditions,10000)}
