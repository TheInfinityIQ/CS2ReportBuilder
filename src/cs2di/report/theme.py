"""The one place styling lives. The AI can never touch this: plans have no style fields."""

CSS = """
:root{
  --bg:#f6f5f2; --panel:#ffffff; --ink:#1d2027; --muted:#5b6270; --line:#e2e0da;
  --accent:#2f5d8a; --accent-soft:#e6eef6;
  --t:#8f560a; --t-soft:#fbf1dc; --ct:#2b6cb0; --ct-soft:#e3eefa;
  --good:#2f7d4f; --good-soft:#e4f3ea; --bad:#b03a3a; --bad-soft:#f8e6e6;
  --card:#ffffff;
  --radius:12px; --shadow:0 1px 2px rgba(20,24,32,.06),0 4px 14px rgba(20,24,32,.05);
  --font:system-ui,-apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
}
@media (prefers-color-scheme:dark){
  :root{--bg:#15181d;--panel:#1d2128;--ink:#e8eaee;--muted:#9aa3b2;--line:#2c323c;
    --accent:#7fb0e0;--accent-soft:#22303f;--t:#e0a542;--t-soft:#3a2f1a;--ct:#6cb0f0;--ct-soft:#1c2f44;
    --good:#5fc189;--good-soft:#1c3327;--bad:#e07a7a;--bad-soft:#3a2222;--card:#1d2128;--shadow:none}
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.55 var(--font)}
.wrap{max-width:980px;margin:0 auto;padding:16px 16px 64px}
h1,h2,h3{line-height:1.25;margin:0 0 .4em}
h1{font-size:1.9rem} h2{font-size:1.4rem} h3{font-size:1.1rem}
p{margin:.5em 0}
.muted{color:var(--muted)} .small{font-size:.875rem}
/* folder tabs */
.folder-tabs{display:flex;gap:4px;padding:12px 16px 0;max-width:980px;margin:0 auto;border-bottom:1px solid var(--line)}
.tab-btn{font:inherit;font-weight:600;color:var(--muted);background:transparent;border:1px solid transparent;border-bottom:none;
  padding:10px 20px;border-radius:10px 10px 0 0;cursor:pointer;margin-bottom:-1px}
.tab-btn:hover{color:var(--ink)}
.tab-btn[aria-selected=true]{background:var(--panel);color:var(--ink);border-color:var(--line);border-bottom:1px solid var(--panel)}
.tab-panel{display:none} .tab-panel.active{display:block}
/* shell */
.coverage{display:flex;flex-wrap:wrap;gap:8px 20px;padding:10px 14px;background:var(--accent-soft);border-radius:var(--radius);font-size:.9rem;margin:16px 0}
.coverage b{font-weight:650}
.header{padding:8px 0 4px} .header .sub{color:var(--muted)}
.agenda{background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);padding:16px 20px;margin:16px 0;box-shadow:var(--shadow)}
.agenda .label,.eyebrow{font-size:.78rem;letter-spacing:.06em;text-transform:uppercase;color:var(--muted);font-weight:650}
/* teaching moment */
.moment{background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);padding:22px 24px;margin:22px 0;box-shadow:var(--shadow)}
.moment-head{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-bottom:6px}
.intent{font-size:.72rem;font-weight:700;letter-spacing:.06em;padding:3px 9px;border-radius:99px;background:var(--accent-soft);color:var(--accent)}
.intent.ACTION{background:var(--bad-soft);color:var(--bad)} .intent.REINFORCE{background:var(--good-soft);color:var(--good)}
.question{font-size:1.05rem;color:var(--muted);margin:0 0 14px}
.block{margin:16px 0}
.block.side_by_side{display:grid;grid-template-columns:1fr 1fr;gap:20px;align-items:start}
@media(max-width:720px){.block.side_by_side{grid-template-columns:1fr}}
.takeaway{margin-top:18px;padding:14px 16px;border-left:4px solid var(--accent);background:var(--accent-soft);border-radius:0 var(--radius) var(--radius) 0}
.takeaway .eyebrow{color:var(--accent)}
.notes a{color:var(--accent)}
sup.fn a{text-decoration:none;color:var(--accent);font-weight:650;padding:0 1px}
.summary{background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);padding:18px 22px;margin:22px 0}
.summary ul{margin:.3em 0 .8em;padding-left:1.2em}
.notes{margin:22px 0;font-size:.9rem;color:var(--muted)} .notes ol{padding-left:1.3em}
.footer{margin-top:28px;padding-top:14px;border-top:1px solid var(--line);font-size:.875rem;color:var(--muted)}
.footer a{color:var(--accent)}
/* modules */
.mod{border:1px solid var(--line);border-radius:10px;padding:14px 16px;background:var(--bg)}
.mod-title{font-weight:650;margin-bottom:8px}
.metric-pair{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.metric{padding:10px 12px;border-radius:8px;background:var(--panel);border:1px solid var(--line)}
.metric .val{font-size:2rem;font-weight:700;line-height:1.1}
.metric .cap{font-size:.875rem;color:var(--muted);margin-top:2px}
.metric.good .val{color:var(--good)} .metric.bad .val{color:var(--bad)}
.cluster{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px}
.bars{display:grid;gap:10px}
.bar-row{display:grid;grid-template-columns:110px 1fr;gap:10px;align-items:center}
.bar-label{font-weight:600;font-size:.92rem}
.bar-track{display:grid;gap:3px}
.bar-line{display:grid;grid-template-columns:minmax(0,1fr) 92px;gap:8px;align-items:center}
.bar{height:16px;border-radius:4px;background:var(--accent);min-width:2px}
.bar.k{background:var(--good)} .bar.d{background:var(--bad)}
.bar-num{font-size:.82rem;color:var(--muted);white-space:nowrap}
.contrast{display:grid;grid-template-columns:1fr 1fr;gap:14px}
@media(max-width:720px){.contrast{grid-template-columns:1fr}}
.sit{border:1px solid var(--line);border-radius:10px;padding:12px 14px;background:var(--panel);border-left:4px solid var(--line)}
.sit[data-outcome=win]{border-left-color:var(--good)}
.sit[data-outcome=loss]{border-left-color:var(--bad)}
.sit-head{display:flex;justify-content:space-between;gap:8px;flex-wrap:wrap;margin-bottom:4px}
.tag{font-size:.72rem;font-weight:700;padding:2px 8px;border-radius:99px;background:var(--accent-soft);color:var(--accent)}
.tag.win{background:var(--good-soft);color:var(--good)} .tag.loss{background:var(--bad-soft);color:var(--bad)}
.why{font-size:.9rem;margin:6px 0 8px}
.timeline{list-style:none;margin:0;padding:0;font-size:.9rem}
.timeline li{display:grid;grid-template-columns:48px 1fr;gap:8px;padding:5px 0;border-top:1px dashed var(--line)}
.timeline li.focus{outline:2px solid var(--accent);outline-offset:-2px;border-radius:6px;font-weight:700}
.bar.you{background:var(--ink)}.bar.peer{background:var(--muted);opacity:.55}
.bar-scale{display:flex;justify-content:space-between;font-size:12px;color:var(--muted)}
.verdict{margin:8px 0 0;font-size:14px;font-weight:600;color:var(--muted)}
.verdict.credible{color:var(--ink)}
.moments{display:grid;gap:8px}
.sit[hidden]{display:none}
/* accordion drawers for KeyMoments picks */
.km-accordion{display:grid;gap:6px}
.km-drawer{border:1px solid var(--line);border-radius:var(--radius);background:var(--panel);overflow:hidden}
.km-drawer[data-outcome=win]{border-left:4px solid var(--good)}
.km-drawer[data-outcome=loss]{border-left:4px solid var(--bad)}
.km-drawer[hidden]{display:none}
.km-summary{display:flex;justify-content:space-between;align-items:center;gap:10px;padding:12px 16px;cursor:pointer;list-style:none;user-select:none;font-weight:600}
.km-summary::-webkit-details-marker{display:none}
.km-summary::before{content:'▶';font-size:.7rem;color:var(--muted);margin-right:6px;transition:transform .18s;flex-shrink:0}
.km-drawer[open]>.km-summary::before{transform:rotate(90deg)}
.km-label{flex:1;font-size:.92rem}
.km-res{flex-shrink:0}
.km-drawer>.sit{border:none;border-radius:0;padding:0 16px 16px;background:transparent;border-left:none;margin:0}
.km-drawer[open]>.sit{display:block}
.moments-filters{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:12px;align-items:center}
.moments-filters .filter-label{font-size:.78rem;font-weight:650;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);margin-right:4px}
.filter-btn{font:inherit;font-size:.82rem;font-weight:600;padding:4px 12px;border-radius:99px;border:1px solid var(--line);background:var(--card);color:var(--ink);cursor:pointer;transition:background .1s}
.filter-btn.active,.filter-btn:hover{background:var(--accent-soft);border-color:var(--accent);color:var(--accent)}
.filter-btn.win.active{background:var(--good-soft);border-color:var(--good);color:var(--good)}
.filter-btn.loss.active{background:var(--bad-soft);border-color:var(--bad);color:var(--bad)}
.viewer{margin:10px 0}.viewer canvas{width:100%;max-width:640px;display:block;margin:0 auto;border-radius:8px;background:#1d232b}
.v-ctl{display:flex;flex-wrap:wrap;gap:8px;align-items:center;max-width:640px;margin:8px auto 0}
.v-ctl input[type=range]{flex:1 1 160px}.v-ctl button,.v-ctl select{font:inherit;font-size:14px;padding:6px 12px;border-radius:8px;border:1px solid var(--line);background:var(--card);color:var(--ink);cursor:pointer}
.v-time{font-variant-numeric:tabular-nums;font-size:14px}
.v-quality,.v-utility{max-width:640px;margin:8px auto;font-size:12px}
.v-utility{display:flex;flex-wrap:wrap;gap:4px 8px;font-variant-numeric:tabular-nums}
.v-utility[hidden]{display:none}.v-utility span{background:var(--panel);border:1px solid var(--line);border-radius:6px;padding:3px 7px}
.v-feed{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}
.v-feed b.CT{color:var(--ct)}.v-feed b.T{color:var(--t)}
.v-roster{display:grid;grid-template-columns:1fr 1fr;gap:8px;max-width:640px;margin:8px auto 0;font-size:13px}
.v-roster>*{min-width:0}.rr .wn{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.rt{border:1px solid var(--line);border-radius:8px;padding:6px 10px;background:var(--panel)}
.rt.CT{border-top:3px solid var(--ct)}.rt.T{border-top:3px solid var(--t)}
.rh{display:flex;justify-content:space-between;font-size:12.5px;color:var(--muted);margin-bottom:2px}
.rh b{color:var(--ink)}
.rr{padding:3px 0;border-top:1px dashed var(--line)}
.rr .l1{display:flex;gap:8px;align-items:center}
.rr .nm{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-weight:600}
.rr.me .nm{color:var(--accent)}
.rr .hpb{width:54px;height:6px;border-radius:3px;background:var(--line);overflow:hidden;flex:none}
.rr .hpb i{display:block;height:100%;background:var(--good)}.rr .hpb i.mid{background:#d9a21b}.rr .hpb i.lo{background:var(--bad)}
.rr .hpn{width:30px;text-align:right;font-variant-numeric:tabular-nums;flex:none}
.rr .wn{color:var(--muted);font-size:12.5px;line-height:1.3}
.rr.dead{opacity:.72}.rr.dead .nm{text-decoration:line-through}.rr.dead .hpn{color:var(--bad);font-weight:650}
.observed{background:var(--bg);border:1px solid var(--line);border-radius:8px;padding:8px 12px;margin:8px 0}
.observed li.sub{list-style:none;margin-left:-4px;font-variant-numeric:tabular-nums}
@media (max-width:560px){.moment .mod{padding:10px 8px;margin-left:-8px;margin-right:-8px}.sit{padding:10px 8px;margin-left:-6px;margin-right:-6px}.observed{padding:8px}}
.observed ul{margin:4px 0 0;padding-left:18px;font-size:14px}
.fgroup{margin:14px 0}.fgroup h3{margin:0 0 6px;font-size:15px}
.chip{display:inline-block;padding:1px 8px;border-radius:999px;font-size:12px;font-weight:700;border:1px solid var(--line);white-space:nowrap}
.chip.credible{background:var(--accent-soft);border-color:var(--accent)}
.chip.leaning{border-style:dashed}
.chip.no_difference,.chip.unclear,.chip.too_few{color:var(--muted)}
.table-scroll{overflow-x:auto;-webkit-overflow-scrolling:touch}
.timeline li.me{background:var(--accent-soft);margin:0 -6px;padding:5px 6px;border-radius:6px}
.tm{color:var(--muted);font-variant-numeric:tabular-nums}
.T{color:var(--t);font-weight:650} .CT{color:var(--ct);font-weight:650}
.disc{margin-top:10px;font-size:.875rem}
.disc summary{cursor:pointer;color:var(--accent);font-weight:600}
.disc-body{margin-top:6px;padding:10px 12px;background:var(--panel);border:1px solid var(--line);border-radius:8px}
.disc-body dt{font-weight:650;margin-top:6px} .disc-body dd{margin:0 0 4px;color:var(--muted)}
.placeholder{padding:20px;text-align:center;color:var(--muted);border:1px dashed var(--line);border-radius:10px}
/* analyst desk */
table{border-collapse:collapse;width:100%;font-size:.9rem;background:var(--panel)}
th,td{text-align:left;padding:7px 10px;border-bottom:1px solid var(--line);vertical-align:top}
th{font-size:.78rem;letter-spacing:.04em;text-transform:uppercase;color:var(--muted)}
td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}
.desk-sec{margin:26px 0} .desk-sec h2{margin-bottom:8px}
.pill{font-size:.75rem;padding:1px 8px;border-radius:99px;background:var(--line);color:var(--muted)}
.finding{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:12px 16px;margin:10px 0}
.finding ul{margin:.2em 0 .6em;padding-left:1.2em}

.v-ctl{row-gap:6px}
.v-ctl button[aria-pressed=true]{background:var(--accent-soft);border-color:var(--accent);color:var(--accent)}
.v-lbl{font-size:.78rem;font-weight:650;text-transform:uppercase;letter-spacing:.06em;color:var(--muted)}
.v-layers button{font-size:13px;padding:4px 10px}
.v-track{position:relative;flex:1 1 120px;min-width:110px;padding-bottom:12px}
.v-track input[type=range]{width:100%;margin:0;display:block}
.v-marks{position:absolute;left:8px;right:8px;bottom:0;height:12px;pointer-events:none}
.v-marks .mk{position:absolute;bottom:0;width:10px;height:12px;margin-left:-5px;padding:0;border:none;background:transparent;pointer-events:auto;cursor:pointer}
.v-marks .mk::after{content:"";position:absolute;left:3px;bottom:0;width:4px;height:9px;border-radius:2px;background:#8b95a5}
.v-marks .mk.CT::after{background:#3f8fe0}.v-marks .mk.T::after{background:#e39a35}
.v-marks .mk.b::after{background:#e03434;height:12px}.v-marks .mk.f::after{background:#ffd400;height:12px;width:5px}.v-marks .mk.e::after{background:#c5ccd6;height:12px}
.v-stage{position:relative;max-width:640px;margin:0 auto}.v-stage canvas{width:100%}
.v-expand{position:absolute;right:8px;bottom:8px;font:inherit;font-size:12.5px;padding:4px 10px;border-radius:99px;border:1px solid rgba(255,255,255,.35);background:rgba(10,14,20,.78);color:#fff;cursor:pointer}
.v-ctl .v-expand{display:none}
.v-how{max-width:640px;margin:8px auto 0}
body.v-lock{overflow:hidden}
.viewer.v-full{position:fixed;inset:0;z-index:60;margin:0;padding:10px;background:var(--bg);overflow:auto}
.viewer.v-full .v-stage{max-width:min(100%,calc(100vh - 230px))}.viewer.v-full canvas{max-width:none}
.viewer.v-full .v-ctl,.viewer.v-full .v-roster,.viewer.v-full .v-how{max-width:min(100%,calc(100vh - 230px),900px)}
@media(max-width:480px){.v-roster{grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:6px;font-size:12px}.rr .hpb{width:24px}.rr .hpn{width:24px}.rr .l1{gap:5px}.rr .wn{font-size:11.5px}.rt{padding:5px 7px}}
@media(max-width:560px){.v-ctl [data-step]{display:none}.v-ctl button,.v-ctl select{padding:6px 8px;font-size:13px}.v-ctl{gap:5px}.v-layers button{padding:4px 8px;font-size:12.5px}.v-time{font-size:13px}}
/* local example-replay filters */
.km-filters{display:flex;flex-wrap:wrap;gap:6px 8px;align-items:center;margin:4px 0 10px}
.km-filters .fgrp{display:flex;flex-wrap:wrap;gap:6px;align-items:center}
.km-filters .filter-label{font-size:.78rem;font-weight:650;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);margin-right:2px;white-space:nowrap}
.km-filters .filter-btn[aria-pressed=true]{background:var(--accent-soft);border-color:var(--accent);color:var(--accent)}
.km-filters .filter-btn.win[aria-pressed=true]{background:var(--good-soft);border-color:var(--good);color:var(--good)}
.km-filters .filter-btn.loss[aria-pressed=true]{background:var(--bad-soft);border-color:var(--bad);color:var(--bad)}
.km-empty{padding:12px;border:1px dashed var(--line);border-radius:8px;color:var(--muted);text-align:center;font-size:.9rem}
@media print{.folder-tabs{display:none}.tab-panel{display:block!important}.moment,.summary{box-shadow:none;break-inside:avoid}}
"""
