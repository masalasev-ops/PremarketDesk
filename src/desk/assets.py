"""The desk's stylesheet and application, as strings.

Held here the way core/page.py holds REPORT_CSS: one string with one user, so
there is no asset directory to keep in step with a renderer and nothing to
resolve at runtime. render.py inlines both into site/PremarketDesk.html.

THE TOKENS ARE page.TOKENS_CSS AND NOT A SECOND SET. The desk imports them
rather than restating them, so the conviction green, yellow and red on a
screen are the same three values the emailed report uses, and the 2026-09-04
correction to that trio reached both surfaces at once. Only what the report
has no use for is added below: the amber magnitude ramp the marks plot with,
and the layout.

The magnitude ramp is four steps of one hue, stepped for each surface and
validated against it. More is darker in light and lighter in dark. A chart
that needs a second hue to be readable is the wrong chart.
"""

from __future__ import annotations

DECK_CSS = """
/* premarketdesk desk */
:root {
  --r1: #D9A870; --r2: #C48744; --r3: #AC6820; --r4: #8C460B;
  --sunk: #EFEDE8;
  --shadow: 0 1px 2px rgba(22,25,29,0.05), 0 8px 24px -12px rgba(22,25,29,0.18);
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --r1: #6E4C22; --r2: #996834; --r3: #C08A46; --r4: #E8A254;
    --sunk: #232A34;
    --shadow: 0 1px 2px rgba(0,0,0,0.4), 0 8px 24px -12px rgba(0,0,0,0.7);
  }
}
:root[data-theme="dark"] {
  --r1: #6E4C22; --r2: #996834; --r3: #C08A46; --r4: #E8A254;
  --sunk: #232A34;
  --shadow: 0 1px 2px rgba(0,0,0,0.4), 0 8px 24px -12px rgba(0,0,0,0.7);
}

* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--ink);
  font-family: "Segoe UI", system-ui, -apple-system, sans-serif;
  font-size: 14px; line-height: 1.5; }
.num, .mono { font-variant-numeric: tabular-nums;
  font-family: Consolas, "SF Mono", ui-monospace, monospace; }
h1, h2, h3 { margin: 0; font-weight: 600; letter-spacing: -0.015em; text-wrap: balance; }
button { font: inherit; color: inherit; }
:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; border-radius: 3px; }
a { color: var(--accent); }

.wrap { max-width: 1260px; margin: 0 auto; padding: 0 22px 70px; }

/* header and navigation */
.bar { position: sticky; top: 0; z-index: 40; background: var(--surface);
  border-bottom: 1px solid var(--line); }
.bar-in { max-width: 1260px; margin: 0 auto; padding: 9px 22px;
  display: flex; align-items: center; gap: 16px; flex-wrap: wrap; }
.mark { display: flex; align-items: baseline; gap: 7px; }
.mark b { font-size: 15px; font-weight: 700; letter-spacing: -0.02em; }
.mark span { font-size: 10.5px; letter-spacing: 0.11em; text-transform: uppercase;
  color: var(--accent); font-weight: 600; }
nav { display: flex; gap: 2px; flex-wrap: wrap; }
nav a { padding: 5px 11px; border-radius: 6px; font-size: 13px; color: var(--ink-2);
  text-decoration: none; }
nav a:hover { background: var(--raised); }
nav a[aria-current="page"] { background: var(--accent); color: var(--surface); font-weight: 500; }
.bar-actions { margin-left: auto; display: flex; gap: 7px; align-items: center; }
.btn { border: 1px solid var(--line-strong); background: var(--surface); color: var(--ink);
  padding: 5px 12px; border-radius: 6px; cursor: pointer; font-size: 13px; font-weight: 500; }
.btn:hover { background: var(--raised); }
.btn.primary { background: var(--accent); border-color: var(--accent); color: var(--surface); }
select.btn { padding-right: 6px; }

/* page furniture */
.eyebrow { padding: 18px 0 2px; font-size: 12.5px; color: var(--muted);
  display: flex; gap: 9px; flex-wrap: wrap; align-items: baseline; }
.eyebrow b { color: var(--ink-2); font-weight: 600; }
h1.pagetitle { font-size: 25px; line-height: 1.2; margin: 5px 0 0; }
.dek { color: var(--muted); font-size: 13.5px; margin-top: 5px; max-width: 78ch; }
section { margin-top: 34px; }
.shead { display: flex; align-items: baseline; gap: 11px; flex-wrap: wrap; margin-bottom: 3px; }
.shead h2 { font-size: 17px; }
.shead .note { font-size: 12.5px; color: var(--muted); }
.snote { font-size: 13px; color: var(--muted); margin: 2px 0 14px; max-width: 84ch; }
.card { background: var(--surface); border: 1px solid var(--line); border-radius: 10px; }
.pad { padding: 16px 18px; }
.cols2 { display: grid; grid-template-columns: 1fr 1fr; gap: 15px; }
@media (max-width: 900px) { .cols2 { grid-template-columns: 1fr; } }
.panel-title { font-size: 10.5px; letter-spacing: 0.09em; text-transform: uppercase;
  color: var(--muted); font-weight: 600; margin-bottom: 9px; }
.empty { color: var(--muted); font-size: 13px; padding: 22px 0; text-align: center; }

/* tape */
.tape { display: flex; flex-wrap: wrap; margin: 20px 0 0; border: 1px solid var(--line);
  border-radius: 9px; background: var(--surface); overflow: hidden; }
.tick { flex: 1 1 112px; padding: 8px 12px; border-right: 1px solid var(--line); min-width: 0; }
.tick:last-child { border-right: 0; }
.tick .lbl { font-size: 10px; letter-spacing: 0.09em; text-transform: uppercase;
  color: var(--muted); font-weight: 600; }
.tick .val { font-size: 15.5px; font-weight: 500; margin-top: 1px; }
.tick .chg { font-size: 11.5px; margin-top: 1px; }
.tick .stale { font-size: 10px; color: var(--muted); }
.up { color: var(--good); } .down { color: var(--bad); } .flat { color: var(--muted); }

/* stat tiles */
.kpis { display: grid; grid-template-columns: repeat(auto-fit, minmax(152px, 1fr)); gap: 1px;
  background: var(--line); border: 1px solid var(--line); border-radius: 9px;
  overflow: hidden; margin-top: 15px; }
.kpi { background: var(--surface); padding: 13px 15px; }
.kpi .lbl { font-size: 10px; letter-spacing: 0.09em; text-transform: uppercase;
  color: var(--muted); font-weight: 600; }
.kpi .big { font-size: 28px; font-weight: 600; letter-spacing: -0.02em; line-height: 1.1;
  margin-top: 3px; }
.kpi .sub { font-size: 11.5px; color: var(--muted); margin-top: 3px; }

/* gap spine */
.filters { display: flex; gap: 6px; flex-wrap: wrap; margin: 14px 0 11px; }
.chip { border: 1px solid var(--line-strong); background: var(--surface); border-radius: 999px;
  padding: 4px 12px; font-size: 12.5px; cursor: pointer; color: var(--ink-2); }
.chip[aria-pressed="true"] { background: var(--accent); border-color: var(--accent);
  color: var(--surface); font-weight: 500; }
.spine { border: 1px solid var(--line); border-radius: 9px; background: var(--surface);
  overflow: hidden; }
.spine-axis { position: relative; height: 21px; border-bottom: 1px solid var(--line);
  background: var(--raised); }
.spine-axis .t { position: absolute; top: 4px; transform: translateX(-50%);
  font-size: 10px; color: var(--muted); }
.spine-row { display: grid;
  grid-template-columns: 4px 58px minmax(0,1fr) minmax(0,124px) 1fr 70px 38px;
  align-items: center; gap: 9px; width: 100%; text-align: left; background: transparent;
  border: 0; border-top: 1px solid var(--line); padding: 0 13px 0 0; cursor: pointer;
  min-height: 37px; }
.spine-row:first-of-type { border-top: 0; }
.spine-row:hover, .spine-row[aria-current="true"] { background: var(--active); }
.stripe { height: 100%; min-height: 37px; }
.stripe.green { background: var(--good); }
.stripe.yellow { background: var(--warn); }
.stripe.red { background: var(--bad); }
.stripe.unscored { background: var(--line-strong); }
.spine-row .tk { font-weight: 600; font-size: 13px; padding-left: 9px; }
.spine-row .nm { font-size: 12.5px; color: var(--muted); white-space: nowrap;
  overflow: hidden; text-overflow: ellipsis; }
/* The reason column. The class word is the answer at a glance and the row's
   own tooltip carries the sentence; the selected name's deck carries the
   headlines the class was read from. */
.cat { display: flex; align-items: center; gap: 6px; min-width: 0; }
.cchip { font-size: 10.5px; letter-spacing: 0.04em; text-transform: uppercase;
  font-weight: 600; color: var(--accent); border: 1px solid var(--accent);
  border-radius: 4px; padding: 1px 6px; white-space: nowrap; overflow: hidden;
  text-overflow: ellipsis; }
.cchip.none { color: var(--muted); border-color: var(--line-strong);
  font-weight: 500; letter-spacing: 0.02em; text-transform: none; }
.cat .cn { font-size: 10.5px; color: var(--muted); white-space: nowrap; }
.cat .cn::after { content: " news"; }
@media (max-width: 900px) { .cat { display: none; } }

.plot { position: relative; height: 25px; }
.plot .zero { position: absolute; top: 2px; bottom: 2px; width: 1px; background: var(--line-strong); }
.plot .b { position: absolute; top: 7px; height: 11px; background: var(--r3); }
.plot .b.upb { border-radius: 0 4px 4px 0; }
.plot .b.dnb { border-radius: 4px 0 0 4px; }
.spine-row[aria-current="true"] .plot .b { background: var(--accent); }
.gapval { font-size: 12.5px; text-align: right; }
.scorebox { font-size: 12.5px; text-align: right; color: var(--ink-2); }
.legendrow { display: flex; gap: 15px; flex-wrap: wrap; align-items: center; margin-top: 9px;
  font-size: 12px; color: var(--muted); }
.lg { display: inline-flex; align-items: center; gap: 6px; }
.sw { width: 10px; height: 10px; border-radius: 2px; display: inline-block; }
.sw.green { background: var(--good); } .sw.yellow { background: var(--warn); }
.sw.red { background: var(--bad); }

/* candidate deck */
.deck { margin-top: 15px; border: 1px solid var(--line); border-radius: 10px;
  background: var(--surface); overflow: hidden; }
.deck-head { padding: 13px 17px; border-bottom: 1px solid var(--line);
  display: flex; align-items: baseline; gap: 11px; flex-wrap: wrap; }
.deck-head .tk { font-size: 18px; font-weight: 600; }
.deck-head .nm { font-size: 13.5px; color: var(--ink-2); }
.deck-head .sector { font-size: 12px; color: var(--muted); }
.deck-head .right { margin-left: auto; display: flex; gap: 7px; flex-wrap: wrap; }
.pill { font-size: 11.5px; padding: 2px 9px; border-radius: 999px;
  border: 1px solid var(--line-strong); color: var(--ink-2); white-space: nowrap; }
.pill.green { color: var(--good); border-color: var(--good); font-weight: 600; }
.pill.yellow { color: var(--warn); border-color: var(--warn); font-weight: 600; }
.pill.red { color: var(--bad); border-color: var(--bad); font-weight: 600; }
.pill.on { color: var(--accent); border-color: var(--accent); background: var(--active);
  font-weight: 600; }
.deck-why { padding: 11px 17px; border-bottom: 1px solid var(--line);
  background: var(--raised); font-size: 13px; color: var(--ink-2); line-height: 1.55; }
.deck-why b { font-size: 10.5px; letter-spacing: 0.08em; text-transform: uppercase;
  color: var(--muted); margin-right: 9px; }
.deck-grid { display: grid; grid-template-columns: 320px minmax(0,1.15fr) minmax(0,1fr); }
.deck-grid > div { padding: 15px 17px; border-right: 1px solid var(--line); min-width: 0; }
.deck-grid > div:last-child { border-right: 0; }
@media (max-width: 1020px) { .deck-grid { grid-template-columns: 1fr; }
  .deck-grid > div { border-right: 0; border-bottom: 1px solid var(--line); } }

.facts { display: grid; grid-template-columns: 1fr 1fr; gap: 1px; background: var(--line);
  border: 1px solid var(--line); border-radius: 7px; overflow: hidden; }
.fact { background: var(--surface); padding: 7px 10px; }
.fact.wide { grid-column: 1 / -1; }
.fact .k { font-size: 10px; color: var(--muted); letter-spacing: .04em; }
.fact .v { font-size: 13px; margin-top: 1px; }
.fact .v small { color: var(--muted); font-size: 11px; font-family: "Segoe UI", sans-serif; }

.comp { display: grid; grid-template-columns: 124px minmax(0,1fr) 24px; gap: 8px;
  align-items: center; margin-bottom: 5px; font-size: 12px; }
.comp .cb { height: 9px; background: var(--sunk); border-radius: 2px; overflow: hidden; }
.comp .cb i { display: block; height: 100%; background: var(--r3); border-radius: 0 2px 2px 0; }
.comp .cv { text-align: right; color: var(--ink-2); }

.hl { border-top: 1px solid var(--line); padding-top: 9px; margin-top: 9px; }
.hl:first-of-type { border-top: 0; padding-top: 0; margin-top: 0; }
.hl .t { font-size: 12.5px; line-height: 1.4; }
.hl .m { font-size: 11px; color: var(--muted); margin-top: 3px; display: flex; gap: 8px;
  flex-wrap: wrap; align-items: center; }
.polbar { width: 42px; height: 6px; border-radius: 3px; background: var(--sunk);
  position: relative; overflow: hidden; }
.polbar i { position: absolute; top: 0; bottom: 0; background: var(--r3); }

.chart-wrap { position: relative; }
.tip { position: absolute; pointer-events: none; opacity: 0; transition: opacity .1s;
  background: var(--ink); color: var(--bg); padding: 6px 9px; border-radius: 6px;
  font-family: Consolas, monospace; font-size: 11.5px; line-height: 1.45;
  white-space: nowrap; z-index: 5; box-shadow: var(--shadow); }
svg { display: block; max-width: 100%; }
svg text { font-family: Consolas, "SF Mono", monospace; font-variant-numeric: tabular-nums; }

.outcome { border-top: 1px solid var(--line); padding: 11px 17px; display: flex; gap: 13px;
  align-items: baseline; flex-wrap: wrap; background: var(--raised); }
.outcome .lbl { font-size: 10px; letter-spacing: 0.09em; text-transform: uppercase;
  color: var(--muted); font-weight: 600; }
.outcome .why { font-size: 12.5px; color: var(--ink-2); max-width: 76ch; }

/* pipeline and condition tracks */
.pipe { display: grid; grid-template-columns: repeat(auto-fit, minmax(136px,1fr)); gap: 1px;
  background: var(--line); border: 1px solid var(--line); border-radius: 9px; overflow: hidden; }
.stage { background: var(--surface); padding: 12px 14px; }
.stage .st { font-size: 10px; letter-spacing: .08em; text-transform: uppercase;
  color: var(--muted); font-weight: 600; }
.stage .n { font-size: 24px; font-weight: 500; margin-top: 3px; }
.stage .kept { height: 6px; border-radius: 3px; background: var(--sunk); margin-top: 7px;
  overflow: hidden; }
.stage .kept i { display: block; height: 100%; background: var(--r3); }
.stage .d { font-size: 11.5px; color: var(--muted); margin-top: 6px; line-height: 1.4; }
.cond { display: grid; grid-template-columns: 190px minmax(0,1fr); gap: 11px;
  align-items: center; margin-bottom: 6px; }
.cond .cn { font-size: 12px; color: var(--ink-2); font-family: Consolas, monospace; }
.cond .track { display: flex; gap: 2px; height: 15px; }
.cond .track i { display: block; border-radius: 2px; }
.cond .track i.ok { background: var(--r1); }
.cond .track i.no { background: var(--r4); }
.cond .track i.un { background: var(--sunk); border: 1px dashed var(--line-strong); }
.cond .track span { font-size: 11px; color: var(--muted); align-self: center;
  padding-left: 6px; white-space: nowrap; }

.sbar { display: grid; grid-template-columns: 148px minmax(0,1fr); gap: 11px;
  align-items: center; margin-bottom: 6px; font-size: 12.5px; }
.sbar .sn { color: var(--ink-2); }
.sbar .st2 { display: flex; align-items: center; gap: 8px; }
.sbar .st2 i { display: block; height: 14px; border-radius: 0 3px 3px 0; background: var(--r3); }
.sbar .st2 span { font-size: 11.5px; color: var(--muted); }

/* tables */
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th { text-align: left; font-size: 10px; letter-spacing: .08em; text-transform: uppercase;
  color: var(--muted); font-weight: 600; padding: 0 9px 6px; border-bottom: 1px solid var(--line-strong); }
td { padding: 7px 9px; border-bottom: 1px solid var(--line); vertical-align: middle; }
tr:last-child td { border-bottom: 0; }
td.n { text-align: right; font-variant-numeric: tabular-nums;
  font-family: Consolas, monospace; }
td.tk { font-weight: 600; font-family: Consolas, monospace; }
.scroll { overflow-x: auto; }
.reason { display: grid; grid-template-columns: 62px minmax(0,1fr); gap: 10px;
  align-items: baseline; padding: 6px 0; border-top: 1px solid var(--line);
  font-size: 12.5px; color: var(--ink-2); line-height: 1.45; }
.reason:first-of-type { border-top: 0; }
.reason .rk { font-weight: 600; color: var(--ink); }
.minibar { position: relative; display: inline-block; width: 84px; height: 12px;
  vertical-align: middle; }
.minibar .z { position: absolute; top: 0; bottom: 0; left: 50%; width: 1px;
  background: var(--line-strong); }
.minibar i { position: absolute; top: 2px; height: 8px; background: var(--r3); }
tr.clickable { cursor: pointer; }
tr.clickable:hover td { background: var(--active); }

/* disclosures */
details { border: 1px solid var(--line); border-radius: 8px; background: var(--surface);
  margin-top: 9px; }
summary { padding: 10px 15px; cursor: pointer; font-size: 13px; font-weight: 500;
  color: var(--ink-2); list-style: none; display: flex; align-items: center; gap: 9px; }
summary::-webkit-details-marker { display: none; }
summary::before { content: "+"; color: var(--accent); font-weight: 600;
  font-family: Consolas, monospace; }
details[open] summary::before { content: "\\2013"; }
details .body { padding: 0 15px 15px; }
details .body.prose { font-family: Georgia, "Times New Roman", serif; font-size: 15px;
  line-height: 1.6; color: var(--ink-2); max-width: 68ch; }

.foot { margin-top: 40px; padding-top: 16px; border-top: 1px solid var(--line);
  font-size: 12px; color: var(--muted); line-height: 1.6; max-width: 86ch; }
.printonly { display: none; }

/* the calendar. ONE component with two users: the sessions screen lays every
   month on file side by side, and the header opens a single month in a
   popover. A native date input cannot haze the days the desk holds nothing
   for, only clamp a range, and "the machine did not run that morning" is the
   thing the reader most needs to see. */
.calwrap { display: grid; grid-template-columns: repeat(auto-fit, minmax(272px, 1fr));
  gap: 15px; }
/* Capped, because a month stretched to half a 1260px page reads as a table of
   empty boxes rather than as a calendar. */
.cal { background: var(--surface); border: 1px solid var(--line); border-radius: 10px;
  padding: 13px 14px 14px; max-width: 372px; }
.cal-head { display: flex; align-items: baseline; gap: 7px; margin-bottom: 10px; }
.cal-head .mo { font-size: 13.5px; font-weight: 600; letter-spacing: -0.01em; }
.cal-head .yr { font-size: 12px; color: var(--muted); }
.cal-nav { margin-left: auto; display: flex; gap: 4px; }
.cal-nav button { border: 1px solid var(--line-strong); background: var(--surface);
  border-radius: 5px; width: 25px; height: 24px; cursor: pointer; font-size: 14px;
  line-height: 1; padding: 0; color: var(--ink-2); }
.cal-nav button:hover:not(:disabled) { background: var(--raised); }
.cal-nav button:disabled { opacity: 0.28; cursor: default; }
.cal-grid { display: grid; grid-template-columns: repeat(7, 1fr); gap: 3px; }
.cal-dow { font-size: 9px; letter-spacing: 0.08em; text-transform: uppercase;
  color: var(--muted); font-weight: 600; text-align: center; padding-bottom: 4px; }
.cd { border-radius: 6px; padding: 4px 2px 5px; min-height: 46px; text-align: center;
  border: 1px solid transparent; }
.cd .dn { font-size: 12px; line-height: 1.25; font-variant-numeric: tabular-nums; }
.cd .tk2 { font-size: 8px; letter-spacing: 0.01em; color: var(--muted); line-height: 1.3;
  font-family: Consolas, "SF Mono", ui-monospace, monospace;
  overflow: hidden; white-space: nowrap; }
.cd .gb { height: 3px; border-radius: 2px; background: var(--r3); margin: 2px auto 0; }
.cd.on { background: var(--raised); border-color: var(--line); cursor: pointer; }
.cd.on .dn { font-weight: 600; color: var(--ink); }
.cd.on:hover { border-color: var(--accent); }
.cd.on.sel { background: var(--active); border-color: var(--accent); }
.cd.off .dn { color: var(--muted); opacity: 0.55; }
.cd.void .dn { color: var(--muted); opacity: 0.24; }
.cal-key { display: flex; gap: 16px; flex-wrap: wrap; margin-top: 13px;
  font-size: 11.5px; color: var(--muted); align-items: center; }
.cal-key i { width: 12px; height: 12px; border-radius: 3px; display: inline-block;
  vertical-align: -2px; margin-right: 6px; border: 1px solid var(--line-strong); }
.cal-key i.k-on { background: var(--raised); }
.cal-key i.k-off { background: transparent; opacity: 0.55; }
.cal-key i.k-void { background: transparent; opacity: 0.28; border-style: dashed; }

.picker-wrap { position: relative; }
#session-btn { display: inline-flex; align-items: center; gap: 7px; }
.cal-pop { position: absolute; right: 0; top: calc(100% + 6px); z-index: 60;
  width: 296px; box-shadow: var(--shadow); }
.cal-pop .cal { border-color: var(--line-strong); }

/* the countdown a midday screen shows before its pass has run */
.waiting { text-align: center; padding: 28px 20px 26px; }
.count { display: flex; align-items: baseline; gap: 3px; justify-content: center;
  padding: 14px 0 4px; }
.count b { font-size: 44px; font-weight: 600; letter-spacing: -0.03em; line-height: 1;
  font-variant-numeric: tabular-nums; }
.count span { font-size: 13px; color: var(--muted); margin-right: 9px; }
.waiting .lead { font-size: 13.5px; color: var(--ink-2); max-width: 62ch;
  margin: 14px auto 0; line-height: 1.6; }

/* health, said in sentences */
.check { display: grid; grid-template-columns: 132px minmax(0,1fr); gap: 15px;
  padding: 14px 0; border-top: 1px solid var(--line); align-items: start; }
.check:first-of-type { border-top: 0; padding-top: 2px; }
.check .t { font-size: 13.5px; font-weight: 600; margin-bottom: 3px; }
.check .s { font-size: 13px; color: var(--ink-2); line-height: 1.6; max-width: 80ch; }
.chip { font-size: 10px; letter-spacing: 0.06em; text-transform: uppercase;
  font-weight: 700; display: inline-flex; align-items: center; gap: 6px;
  white-space: nowrap; padding-top: 2px; }
.chip i { width: 8px; height: 8px; border-radius: 999px; display: inline-block; }
.chip.ok { color: var(--good); } .chip.ok i { background: var(--good); }
.chip.watch { color: var(--warn); } .chip.watch i { background: var(--warn); }
.chip.bad { color: var(--bad); } .chip.bad i { background: var(--bad); }
.chip.note { color: var(--muted); } .chip.note i { background: var(--muted); }
.verdict { display: flex; gap: 14px; align-items: center; padding: 0; overflow: hidden; }
.verdict .rule { width: 4px; align-self: stretch; }
.verdict .vin { padding: 15px 4px 15px 0; }
.verdict .vt { font-size: 17px; font-weight: 600; letter-spacing: -0.015em; }
.verdict .vs { font-size: 12.5px; color: var(--muted); margin-top: 2px; }

.seg { display: inline-flex; border: 1px solid var(--line-strong); border-radius: 7px;
  overflow: hidden; }
.seg button { border: 0; background: var(--surface); padding: 4px 13px; font-size: 12.5px;
  cursor: pointer; color: var(--ink-2); }
.seg button[aria-pressed="true"] { background: var(--accent); color: var(--surface);
  font-weight: 500; }

@media (prefers-reduced-motion: reduce) { * { transition: none !important; } }

@media print {
  .bar { position: static; border-bottom: 2px solid var(--ink); }
  .bar-actions, .filters, nav, .noprint, .seg { display: none !important; }
  .cal { break-inside: avoid; }
  .wrap { max-width: none; padding: 0; }
  body { font-size: 10.5pt; }
  .printonly { display: block; }
  section, .deck, .card, .spine, .pipe, .kpis { break-inside: avoid; }
  .interactive-deck { display: none; }
  .print-deck { break-before: page; }
  details { border: 0; } details .body { padding: 0 0 10px; }
  a { color: var(--ink); text-decoration: none; }
  @page { margin: 14mm 12mm; }
}
"""

DECK_JS = r"""
/* premarketdesk desk application.

   One document, eight screens, hash routes. No framework, no library, no
   build step and no network: every session is inlined at render time,
   gzipped and base64 encoded, and inflated in the page on first view.

   The screens and their reasoning are in doc/SCREENS.md. Nothing here
   computes a number. Every value drawn was written by Python into the
   packet and copied by desk/compact.py, so a wrong figure on a screen is a
   wrong figure in the packet and the fix is upstream.
*/
(function () {
  "use strict";

  var INDEX = JSON.parse(document.getElementById("desk-index").textContent);
  var BLOBS = JSON.parse(document.getElementById("desk-payloads").textContent);
  var KNOBS = INDEX.knobs;
  var cache = {};

  var $ = function (id) { return document.getElementById(id); };

  // What a cell says when the packet carries no value for it. Never an em
  // dash, which BUILD_PLAN hard rule 4 forbids anywhere in this tree, and
  // never a bare hyphen, which in a column of signed numbers reads as a
  // minus. A missing measurement and a measured zero must never look alike.
  var NIL = "n/a";
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
      return ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c];
    });
  }

  /* ---------- formatting ---------- */
  function pct(v, d) {
    if (v == null) return NIL;
    d = d == null ? 2 : d;
    return (v > 0 ? "+" : v < 0 ? "−" : "") + Math.abs(v).toFixed(d) + "%";
  }
  function n2(v, d) { return v == null ? NIL : v.toFixed(d == null ? 2 : d); }
  function big(v) {
    if (v == null) return NIL;
    var a = Math.abs(v);
    if (a >= 1e12) return (v / 1e12).toFixed(2) + "T";
    if (a >= 1e9) return (v / 1e9).toFixed(2) + "B";
    if (a >= 1e6) return (v / 1e6).toFixed(1) + "M";
    if (a >= 1e3) return (v / 1e3).toFixed(0) + "K";
    return String(Math.round(v));
  }
  function commas(v) { return v == null ? NIL : Math.round(v).toLocaleString("en-US"); }
  function pad2(n) { return (n < 10 ? "0" : "") + n; }
  function bare(s) { return String(s == null ? "" : s).split(".")[0]; }
  function hhmm(iso) {
    if (!iso) return NIL;
    var m = String(iso).match(/T(\d\d:\d\d)/);
    return m ? m[1] : String(iso).slice(0, 5);
  }
  // The wall clock in New York, whatever zone the reader is sitting in. Every
  // time this project writes down is Eastern, so a countdown read against the
  // browser's own clock would be wrong for most of the world and quietly
  // right here, which is the worst way for it to be wrong.
  function etNow() {
    var parts = {};
    new Intl.DateTimeFormat("en-CA", {
      timeZone: "America/New_York", hour12: false, year: "numeric",
      month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit",
      second: "2-digit"
    }).formatToParts(new Date()).forEach(function (p) { parts[p.type] = p.value; });
    var hh = (+parts.hour) % 24;
    return { date: parts.year + "-" + parts.month + "-" + parts.day,
      mins: hh * 60 + (+parts.minute), secs: +parts.second,
      clock: pad2(hh) + ":" + parts.minute };
  }
  function dirClass(v) { return v > 0 ? "up" : v < 0 ? "down" : "flat"; }
  function convWord(c) {
    return c === "green" ? "Green" : c === "yellow" ? "Yellow"
      : c === "red" ? "Red" : "Unscored";
  }
  function ramp(i, of) {
    var r = ["var(--r1)", "var(--r2)", "var(--r3)", "var(--r4)"];
    return r[Math.min(3, Math.floor(i / Math.max(1, of) * 4))];
  }
  var MID_WORD = {
    triggered: "Entry reached", gapped_through: "Opened past the entry",
    never_triggered: "Entry never reached", skipped: "Skipped"
  };
  // The three legs a notable mover can be ranked on, in words. The packet
  // spells them with underscores and no field name is printed as English on
  // these screens.
  var LEG_WORD = {
    premarket: "moving premarket", prior_session: "the prior session",
    two_session: "over two sessions"
  };

  var TAPE_NAME = {
    spy: "SPY", qqq: "QQQ", iwm: "IWM", dia: "DIA", vix: "VIX",
    "10y": "US 10Y", "3m": "US 3M", uso: "WTI proxy", dxy: "Dollar"
  };

  /* ---------- payload loading ----------
     A session is inflated once and kept. DecompressionStream is native in
     Chrome and Edge and is the reason no library ships here; where it is
     missing the page says so plainly rather than rendering an empty screen
     that looks like a quiet market. */
  function b64bytes(b64) {
    var bin = atob(b64), out = new Uint8Array(bin.length);
    for (var i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
    return out;
  }
  function loadSession(date) {
    if (cache[date]) return Promise.resolve(cache[date]);
    var blob = BLOBS[date];
    if (!blob) return Promise.resolve(null);
    if (typeof DecompressionStream === "undefined") {
      return Promise.reject(new Error(
        "This browser has no DecompressionStream, so the inlined sessions " +
        "cannot be read. Chrome, Edge and Firefox 113 or newer have it."));
    }
    var stream = new Blob([b64bytes(blob)]).stream()
      .pipeThrough(new DecompressionStream("gzip"));
    return new Response(stream).json().then(function (payload) {
      cache[date] = payload;
      return payload;
    });
  }

  /* ---------- the calendar ----------
     Every day the desk holds a morning for is lifted and clickable. A day
     inside the history with no morning is hazed, and a day outside the
     history entirely is hazed further, because "the machine did not run"
     and "this is before anything on file" are different facts and a reader
     deciding where to click needs to tell them apart. */
  var MONTH_NAME = ["January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December"];
  var DOW = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

  var BYDATE = {};
  INDEX.sessions.forEach(function (r) { BYDATE[r.date] = r; });
  var DATES = INDEX.sessions.map(function (r) { return r.date; }).sort();
  var FIRST = DATES[0] || "";
  var LAST = DATES[DATES.length - 1] || "";
  var CAL_MAX = Math.max.apply(null, INDEX.sessions.map(function (r) {
    return Math.abs(r.top_gap_pct || 0); }).concat([1]));

  function monthsOnFile() {
    if (!FIRST) return [];
    var out = [], y = +FIRST.slice(0, 4), m = +FIRST.slice(5, 7) - 1;
    var ey = +LAST.slice(0, 4), em = +LAST.slice(5, 7) - 1;
    while (y < ey || (y === ey && m <= em)) {
      out.push(y + "-" + pad2(m + 1));
      m += 1;
      if (m > 11) { m = 0; y += 1; }
    }
    return out;
  }

  function calMonth(ym, sel, withNav) {
    var y = +ym.slice(0, 4), m = +ym.slice(5, 7) - 1;
    // Constructed local, read only for a weekday and a length, so no zone
    // conversion happens and none is wanted.
    var lead = new Date(y, m, 1).getDay();
    var days = new Date(y, m + 1, 0).getDate();
    var cells = "", i;
    for (i = 0; i < 7; i++) cells += '<div class="cal-dow">' + DOW[i] + "</div>";
    for (i = 0; i < lead; i++) cells += "<div></div>";
    for (var d = 1; d <= days; d++) {
      var iso = ym + "-" + pad2(d);
      var r = BYDATE[iso];
      if (r) {
        var w = Math.max(7, Math.round(Math.abs(r.top_gap_pct || 0) / CAL_MAX * 28));
        cells += '<div class="cd on' + (iso === sel ? " sel" : "") +
          '" data-date="' + iso + '" role="button" tabindex="0" title="' +
          esc(iso + ": " + (r.candidates == null ? NIL : r.candidates) +
            " candidates, largest gap " + (r.top_symbol || NIL) + " " +
            pct(r.top_gap_pct)) + '"><div class="dn">' + d + "</div>" +
          '<div class="tk2">' + esc(bare(r.top_symbol).slice(0, 5)) + "</div>" +
          '<div class="gb" style="width:' + w + 'px"></div></div>';
      } else {
        var outside = (iso < FIRST || iso > LAST);
        cells += '<div class="cd ' + (outside ? "void" : "off") + '" title="' +
          (outside ? "outside the history this desk carries"
            : "no morning on file for this day") + '"><div class="dn">' +
          d + "</div></div>";
      }
    }
    var months = monthsOnFile(), at = months.indexOf(ym), nav = "";
    if (withNav) {
      nav = '<div class="cal-nav">' +
        '<button type="button" aria-label="Previous month" data-mo="' +
        esc(months[at - 1] || "") + '"' + (at <= 0 ? " disabled" : "") +
        ">&lsaquo;</button>" +
        '<button type="button" aria-label="Next month" data-mo="' +
        esc(months[at + 1] || "") + '"' +
        (at < 0 || at >= months.length - 1 ? " disabled" : "") +
        ">&rsaquo;</button></div>";
    }
    return '<div class="cal"><div class="cal-head"><span class="mo">' +
      MONTH_NAME[m] + '</span><span class="yr">' + y + "</span>" + nav +
      '</div><div class="cal-grid">' + cells + "</div></div>";
  }

  function calKey() {
    return '<div class="cal-key">' +
      '<span><i class="k-on"></i>a morning on file, click it</span>' +
      '<span><i class="k-off"></i>no morning that day</span>' +
      '<span><i class="k-void"></i>outside the history on file</span>' +
      '<span>the bar is that morning\'s largest gap, one scale across every ' +
      "month</span></div>";
  }

  function wireCal(root, onPick) {
    root.addEventListener("click", function (e) {
      var mo = e.target.closest("button[data-mo]");
      if (mo) {
        if (!mo.disabled && mo.dataset.mo) {
          root.innerHTML = calMonth(mo.dataset.mo, root.dataset.sel || null, true);
        }
        return;
      }
      var cd = e.target.closest(".cd.on");
      if (cd) onPick(cd.dataset.date);
    });
    root.addEventListener("keydown", function (e) {
      if (e.key !== "Enter" && e.key !== " ") return;
      var cd = e.target.closest(".cd.on");
      if (cd) { e.preventDefault(); onPick(cd.dataset.date); }
    });
  }

  /* ---------- marks ---------- */

  /* 1. gap spine */
  function spineHTML(cands, selected, scale) {
    scale = scale || KNOBS.spine_scale_pct;
    var xp = function (v) { return 50 + (v / scale) * 50; };
    var ticks = [-Math.round(scale * 0.77), -Math.round(scale * 0.38), 0,
                 Math.round(scale * 0.38), Math.round(scale * 0.77)];
    var axis = '<div class="spine-axis">' + ticks.map(function (t) {
      return '<div class="t num" style="left:' + xp(t) + '%">' +
        (t === 0 ? "0" : pct(t, 0)) + "</div>";
    }).join("") + "</div>";
    var rows = cands.map(function (c) {
      var g = c.gap == null ? 0 : c.gap;
      var w = Math.min(50, Math.abs(g) / scale * 50);
      var bar = c.gap == null ? "" : (g >= 0
        ? '<i class="b upb" style="left:50%;width:' + w + '%"></i>'
        : '<i class="b dnb" style="right:50%;width:' + w + '%"></i>');
      return '<button class="spine-row" type="button" data-sym="' + esc(c.sym) + '"' +
        ' aria-current="' + (c.sym === selected) + '"' +
        ' title="' + esc(c.sym + " " + pct(c.gap) + ", score " + n2(c.score, 0) +
          ", " + convWord(c.conv) +
          (hasCatalyst(c) ? ". " + c.catalyst + ": " + (c.catalyst_why || "")
            : ". " + (c.catalyst_why || "nothing explains this move"))) + '">' +
        '<span class="stripe ' + esc(c.conv || "unscored") + '"></span>' +
        '<span class="tk mono">' + esc(c.sym) + "</span>" +
        '<span class="nm">' + esc(c.name) + "</span>" +
        '<span class="cat">' + (hasCatalyst(c)
          ? '<span class="cchip">' + esc(c.catalyst) + "</span>"
          : '<span class="cchip none">nothing found</span>') +
        (c.news ? '<span class="cn">' + c.news + "</span>" : "") + "</span>" +
        '<span class="plot"><span class="zero" style="left:50%"></span>' + bar + "</span>" +
        '<span class="gapval num">' + pct(c.gap) + "</span>" +
        '<span class="scorebox num">' + n2(c.score, 0) + "</span></button>";
    }).join("");
    return axis + (rows ||
      '<div class="pad empty">No candidate matches that filter.</div>');
  }

  // The packet writes the string "none" for a name nothing explains, so a
  // truth test on c.catalyst is not enough: it would print NONE as a class.
  function hasCatalyst(c) {
    return !!c.catalyst && c.catalyst !== "none";
  }

  /* 2. level ladder */
  function ladder(c) {
    var W = 310, H = 430, TOP = 18, BOT = 20, AX = 104;
    var pts = [];
    function add(v, label, kind) { if (v != null) pts.push({ v: v, label: label, kind: kind }); }
    add(c.prior_close, "Prior close", "ref");
    add(c.prior_high, "Prior high", "ref");
    add(c.pm_low, "PM low · stop", "stop");
    add(c.pm_vwap, "VWAP", "mark");
    add(c.price, "Last", "last");
    add(c.pm_high, "PM high · entry", "entry");
    if (!pts.length) return '<div class="empty">No level was measured for this name.</div>';
    var vs = pts.map(function (p) { return p.v; });
    var lo = Math.min.apply(null, vs), hi = Math.max.apply(null, vs);
    var pad = (hi - lo) * 0.10 || 1;
    lo -= pad; hi += pad;
    var y = function (v) { return TOP + (hi - v) / (hi - lo) * (H - TOP - BOT); };

    var s = '<svg viewBox="0 0 ' + W + " " + H + '" width="100%" role="img" aria-label="' +
      esc("Price levels for " + c.sym) + '">';
    if (c.prior_close != null && c.price != null) {
      var ga = y(c.prior_close), gb = y(c.price);
      var gt = Math.min(ga, gb), gm = Math.max(ga, gb), GX = 58;
      s += '<path d="M' + (GX - 5) + " " + gt + " L" + GX + " " + gt + " L" + GX +
        " " + gm + " L" + (GX - 5) + " " + gm +
        '" fill="none" stroke="var(--r2)" stroke-width="1.5"/>';
      if (gm - gt > 26) {
        var mid = (gt + gm) / 2;
        s += '<text x="26" y="' + (mid - 4) +
          '" font-size="9.5" fill="var(--muted)" text-anchor="middle">gap</text>';
        s += '<text x="26" y="' + (mid + 9) +
          '" font-size="10.5" fill="var(--r3)" text-anchor="middle">' + pct(c.gap) + "</text>";
      }
    }
    if (c.pm_low != null && c.pm_high != null) {
      s += '<rect x="' + (AX - 9) + '" y="' + y(c.pm_high) + '" width="18" height="' +
        Math.max(1, y(c.pm_low) - y(c.pm_high)) +
        '" fill="var(--active)" stroke="var(--r2)" stroke-width="1"/>';
    }
    s += '<line x1="' + AX + '" y1="' + TOP + '" x2="' + AX + '" y2="' + (H - BOT) +
      '" stroke="var(--line-strong)" stroke-width="1"/>';

    var ordered = pts.slice().sort(function (a, b) { return y(a.v) - y(b.v); });
    var gap = KNOBS.ladder_label_gap_px, lastY = -99;
    ordered.forEach(function (p) { p.ly = Math.max(y(p.v), lastY + gap); lastY = p.ly; });
    var over = lastY - (H - BOT - 2);
    if (over > 0) {
      for (var i = ordered.length - 1; i >= 0; i--) {
        ordered[i].ly = Math.min(ordered[i].ly,
          i === ordered.length - 1 ? H - BOT - 2 : ordered[i + 1].ly - gap);
      }
    }
    ordered.forEach(function (p) {
      var yy = y(p.v);
      var col = p.kind === "ref" ? "var(--line-strong)"
        : p.kind === "entry" ? "var(--good)" : p.kind === "stop" ? "var(--bad)"
        : p.kind === "last" ? "var(--accent)" : "var(--r3)";
      var dash = p.kind === "ref" ? ' stroke-dasharray="3 3"' : "";
      s += '<line x1="' + (AX - 22) + '" y1="' + yy + '" x2="' + (AX + 14) + '" y2="' + yy +
        '" stroke="' + col + '" stroke-width="' + (p.kind === "ref" ? 1 : 2) + '"' + dash + "/>";
      if (Math.abs(p.ly - yy) > 1.5) {
        s += '<path d="M' + (AX + 14) + " " + yy + " L" + (AX + 20) + " " + p.ly +
          '" stroke="var(--line)" stroke-width="1" fill="none"/>';
      }
      if (p.kind === "entry") {
        s += '<path d="M' + (AX - 30) + " " + (yy + 5) + ' l5 -9 l5 9 z" fill="var(--good)"/>';
      }
      if (p.kind === "stop") {
        s += '<path d="M' + (AX - 30) + " " + (yy - 5) + ' l5 9 l5 -9 z" fill="var(--bad)"/>';
      }
      if (p.kind === "last") {
        s += '<circle cx="' + AX + '" cy="' + yy +
          '" r="4.5" fill="var(--accent)" stroke="var(--surface)" stroke-width="2"/>';
      }
      s += '<text x="' + (AX + 22) + '" y="' + (p.ly + 4) +
        '" font-size="11" fill="var(--ink)">' + n2(p.v) + "</text>";
      s += '<text x="' + (AX + 64) + '" y="' + (p.ly + 4) +
        '" font-size="10" fill="var(--muted)">' + esc(p.label) + "</text>";
    });
    return s + "</svg>";
  }

  /* 3. tape path */
  function toMin(t) { var a = t.split(":"); return +a[0] * 60 + +a[1]; }
  var PATH = { W: 560, H: 232, L: 44, R: 10, T: 12, PB: 152, VT: 166, VB: 198 };
  function pathScales(c) {
    var b = c.bars, xs = b.map(function (d) { return toMin(d.t); });
    var x0 = Math.min.apply(null, xs), x1 = Math.max.apply(null, xs);
    if (x1 === x0) x1 = x0 + 1;
    var cs = b.map(function (d) { return d.c; }).filter(function (v) { return v != null; });
    var lo = Math.min.apply(null, cs), hi = Math.max.apply(null, cs);
    if (c.pm_vwap != null) { lo = Math.min(lo, c.pm_vwap); hi = Math.max(hi, c.pm_vwap); }
    var pad = (hi - lo) * 0.12 || (hi * 0.002) || 1;
    lo -= pad; hi += pad;
    return {
      X: function (m) { return PATH.L + (m - x0) / (x1 - x0) * (PATH.W - PATH.L - PATH.R); },
      Y: function (v) { return PATH.T + (hi - v) / (hi - lo) * (PATH.PB - PATH.T); },
      lo: lo, hi: hi, x0: x0, x1: x1
    };
  }
  function tapePath(c) {
    var b = c.bars || [];
    if (b.length < KNOBS.path_min_bars) {
      return '<div class="empty" style="height:150px;display:flex;align-items:center;' +
        'justify-content:center;padding:0 20px">The collector recorded ' + b.length +
        " minute" + (b.length === 1 ? "" : "s") + " of tape for " + esc(c.sym) +
        ", too few to draw a path. The levels beside this are still measured, " +
        "from those minutes.</div>";
    }
    var sc = pathScales(c), s = "";
    s += '<svg viewBox="0 0 ' + PATH.W + " " + PATH.H + '" width="100%" role="img" aria-label="' +
      esc("Premarket tape for " + c.sym) + '">';
    [sc.lo + (sc.hi - sc.lo) * 0.08, (sc.lo + sc.hi) / 2, sc.hi - (sc.hi - sc.lo) * 0.08]
      .forEach(function (v) {
        s += '<line x1="' + PATH.L + '" y1="' + sc.Y(v) + '" x2="' + (PATH.W - PATH.R) +
          '" y2="' + sc.Y(v) + '" stroke="var(--line)" stroke-width="1"/>';
        s += '<text x="' + (PATH.L - 6) + '" y="' + (sc.Y(v) + 3.5) +
          '" font-size="9.5" fill="var(--muted)" text-anchor="end">' + n2(v) + "</text>";
      });
    var d = b.filter(function (p) { return p.c != null; }).map(function (p, i) {
      return (i ? "L" : "M") + sc.X(toMin(p.t)).toFixed(1) + " " + sc.Y(p.c).toFixed(1);
    }).join(" ");
    s += '<path d="' + d + " L" + sc.X(sc.x1).toFixed(1) + " " + PATH.PB + " L" +
      sc.X(sc.x0).toFixed(1) + " " + PATH.PB + ' Z" fill="var(--active)"/>';
    s += '<path d="' + d + '" fill="none" stroke="var(--accent)" stroke-width="2" ' +
      'stroke-linejoin="round" stroke-linecap="round"/>';
    if (c.pm_vwap != null && c.pm_vwap > sc.lo && c.pm_vwap < sc.hi) {
      s += '<line x1="' + PATH.L + '" y1="' + sc.Y(c.pm_vwap) + '" x2="' + (PATH.W - PATH.R) +
        '" y2="' + sc.Y(c.pm_vwap) +
        '" stroke="var(--r3)" stroke-width="1.5" stroke-dasharray="5 4"/>';
      s += '<text x="' + (PATH.W - PATH.R) + '" y="' + (sc.Y(c.pm_vwap) - 5) +
        '" font-size="9.5" fill="var(--r3)" text-anchor="end">VWAP ' + n2(c.pm_vwap) + "</text>";
    }
    var last = b[b.length - 1];
    s += '<circle cx="' + sc.X(toMin(last.t)) + '" cy="' + sc.Y(last.c) +
      '" r="4" fill="var(--accent)" stroke="var(--surface)" stroke-width="2"/>';
    var vmax = Math.max.apply(null, b.map(function (p) { return p.v || 0; })) || 1;
    var bw = Math.max(1, Math.min(6, (PATH.W - PATH.L - PATH.R) / b.length - 1));
    b.forEach(function (p) {
      var h = Math.max(0.7, (p.v || 0) / vmax * (PATH.VB - PATH.VT));
      s += '<rect x="' + (sc.X(toMin(p.t)) - bw / 2).toFixed(1) + '" y="' +
        (PATH.VB - h).toFixed(1) + '" width="' + bw.toFixed(1) + '" height="' +
        h.toFixed(1) + '" fill="var(--r2)" rx="1"/>';
    });
    s += '<line x1="' + PATH.L + '" y1="' + PATH.VB + '" x2="' + (PATH.W - PATH.R) +
      '" y2="' + PATH.VB + '" stroke="var(--line-strong)" stroke-width="1"/>';
    s += '<text x="' + (PATH.L - 6) + '" y="' + (PATH.VT + 8) +
      '" font-size="9" fill="var(--muted)" text-anchor="end">' + big(vmax) + "</text>";
    s += '<text x="' + (PATH.L - 6) + '" y="' + (PATH.VB + 3) +
      '" font-size="9" fill="var(--muted)" text-anchor="end">0</text>';
    s += '<text x="' + PATH.L + '" y="' + (PATH.H - 4) +
      '" font-size="9.5" fill="var(--muted)">' + esc(b[0].t) + "</text>";
    s += '<text x="' + (PATH.W - PATH.R) + '" y="' + (PATH.H - 4) +
      '" font-size="9.5" fill="var(--muted)" text-anchor="end">' + esc(last.t) + "</text>";
    s += '<text x="' + ((PATH.L + PATH.W - PATH.R) / 2) + '" y="' + (PATH.H - 4) +
      '" font-size="9.5" fill="var(--muted)" text-anchor="middle">' + b.length +
      " minutes with a print</text>";
    s += '<line class="cross" x1="0" y1="' + PATH.T + '" x2="0" y2="' + PATH.VB +
      '" stroke="var(--ink-2)" stroke-width="1" stroke-dasharray="3 3" opacity="0"/>';
    s += '<circle class="hdot" r="4" fill="var(--surface)" stroke="var(--accent)" ' +
      'stroke-width="2" opacity="0"/>';
    s += '<rect class="hit" x="' + PATH.L + '" y="' + PATH.T + '" width="' +
      (PATH.W - PATH.L - PATH.R) + '" height="' + (PATH.VB - PATH.T) + '" fill="transparent"/>';
    return '<div class="chart-wrap">' + s + "</svg>" + '<div class="tip" role="status"></div></div>';
  }
  function wirePath(wrap, c) {
    var svg = wrap.querySelector("svg"); if (!svg) return;
    var hit = svg.querySelector(".hit"); if (!hit) return;
    var cross = svg.querySelector(".cross"), dot = svg.querySelector(".hdot");
    var tip = wrap.querySelector(".tip"), sc = pathScales(c), b = c.bars;
    hit.addEventListener("mousemove", function (ev) {
      var r = svg.getBoundingClientRect();
      var px = (ev.clientX - r.left) / r.width * PATH.W;
      var best = b[0], bd = Infinity;
      b.forEach(function (p) {
        var dd = Math.abs(sc.X(toMin(p.t)) - px);
        if (dd < bd) { bd = dd; best = p; }
      });
      var bx = sc.X(toMin(best.t)), by = sc.Y(best.c);
      cross.setAttribute("x1", bx); cross.setAttribute("x2", bx);
      cross.setAttribute("opacity", "1");
      dot.setAttribute("cx", bx); dot.setAttribute("cy", by); dot.setAttribute("opacity", "1");
      tip.innerHTML = esc(best.t) + " ET<br>" + n2(best.c) + "<br>" + commas(best.v) + " sh";
      tip.style.opacity = "1";
      tip.style.left = Math.min(Math.max(4, bx / PATH.W * r.width + 12), r.width - 96) + "px";
      tip.style.top = (by / PATH.H * r.height - 8) + "px";
    });
    hit.addEventListener("mouseleave", function () {
      cross.setAttribute("opacity", "0"); dot.setAttribute("opacity", "0");
      tip.style.opacity = "0";
    });
  }

  /* 7. diverging row, for a table cell */
  function minibar(v, max) {
    if (v == null) return "";
    var w = Math.min(50, Math.abs(v) / (max || 1) * 50);
    return '<span class="minibar"><span class="z"></span><i style="' +
      (v >= 0 ? "left:50%;border-radius:0 3px 3px 0;" : "right:50%;border-radius:3px 0 0 3px;") +
      "width:" + w + "%;background:" + (v >= 0 ? "var(--r2)" : "var(--r4)") + '"></i></span>';
  }

  /* ---------- shared blocks ---------- */
  function tapeHTML(tape) {
    if (!tape || !tape.length) return "";
    return '<div class="tape">' + tape.map(function (t) {
      var arrow = t.pct > 0 ? "▲" : t.pct < 0 ? "▼" : "";
      return '<div class="tick"><div class="lbl">' +
        esc(TAPE_NAME[t.label] || String(t.label || "").toUpperCase()) + "</div>" +
        '<div class="val num">' + n2(t.last, t.last > 100 ? 2 : 3) + "</div>" +
        '<div class="chg num ' + dirClass(t.pct) + '">' + arrow + " " + pct(t.pct) + "</div>" +
        '<div class="stale">' + (t.stale ? "prior close only" : "&nbsp;") + "</div></div>";
    }).join("") + "</div>";
  }
  function kpisHTML(items) {
    return '<div class="kpis">' + items.map(function (k) {
      return '<div class="kpi"><div class="lbl">' + esc(k.l) + '</div><div class="big num">' +
        esc(k.v) + '</div><div class="sub">' + esc(k.s) + "</div></div>";
    }).join("") + "</div>";
  }
  function deckHTML(c, session) {
    var maxPts = Math.max.apply(null,
      c.components.map(function (x) { return x.p; }).concat([1]));
    var comps = c.components.map(function (x, i) {
      return '<div class="comp"><span class="ct">' + esc(String(x.k).replace(/_/g, " ")) +
        '</span><span class="cb"><i style="width:' + (x.p / maxPts * 100) + "%;background:" +
        ramp(i, c.components.length) + '"></i></span><span class="cv num">' +
        n2(x.p, 0) + "</span></div>";
    }).join("") || '<div class="empty">This name was never scored.</div>';

    var earn = "";
    if (c.earn) {
      var beat = (c.earn.actual != null && c.earn.estimate != null)
        ? c.earn.actual - c.earn.estimate : null;
      earn = '<div class="fact wide"><div class="k">EPS ACTUAL VS ESTIMATE</div>' +
        '<div class="v num">' + (c.earn.actual == null ? "not yet" : n2(c.earn.actual)) +
        " / " + n2(c.earn.estimate) +
        (beat == null ? "" : ' <small>' + (beat >= 0 ? "beat " : "miss ") +
          n2(Math.abs(beat)) + "</small>") + "</div></div>";
    }
    var facts = '<div class="facts">' +
      fact("PREMARKET RVOL", c.rvol == null
        ? NIL + ' <small>never measured</small>' : n2(c.rvol) + "×") +
      fact("MOVE IN SIGMA", c.sigma == null ? NIL : n2(c.sigma, 1) + "σ") +
      fact("PM VOLUME (est)", big(c.pm_vol) + " <small>sh</small>") +
      fact("FLOAT ROTATION", c.float_rot == null ? NIL : (c.float_rot * 100).toFixed(3) + "%") +
      fact("MARKET CAP", big(c.mcap)) +
      fact("20D DOLLAR VOL", big(c.adv)) +
      fact("NEWS IN WINDOW", (c.news == null ? NIL : c.news) + " <small>stories</small>") +
      fact("POOL RANK", (c.rank == null ? NIL : "#" + c.rank) +
        " <small>" + esc(c.tier_why || "") + "</small>") +
      earn + "</div>";

    var heads = (c.headlines || []).map(function (h) {
      var p = h.pol == null ? null : Math.max(-1, Math.min(1, h.pol));
      var bar = p == null ? "" : '<span class="polbar" title="polarity ' + n2(p) +
        '"><i style="left:' + (p >= 0 ? 50 : 50 + p * 50) + "%;width:" +
        Math.abs(p) * 50 + '%"></i></span>';
      return '<div class="hl"><div class="t">' + esc(h.t) + '</div><div class="m">' +
        '<span class="mono">' + esc(h.at) + "</span><span>" + esc(h.pub) + "</span>" +
        (h.about === false ? '<span class="pill">not about this name</span>' : "") +
        bar + "</div></div>";
    }).join("");

    var m = c.mid;
    var outcome = !m ? "" : '<div class="outcome"><span class="lbl">At noon</span>' +
      '<span class="pill ' + (m.state === "never_triggered" ? "" : "on") + '">' +
      esc(MID_WORD[m.state] || m.state) + "</span>" +
      '<span class="num ' + dirClass(m.move) + '">' + pct(m.move) + " from prior close</span>" +
      '<span class="num" style="color:var(--muted)">day RVOL ' + n2(m.day_rvol) + "×</span>" +
      '<span class="why">' + esc(m.why) + "</span></div>";

    var badges = '<span class="pill ' + esc(c.conv || "") + '">' + convWord(c.conv) + " " +
      n2(c.score, 0) + "</span>" +
      '<span class="pill' + (c.day ? " on" : "") + '" title="' +
      esc(c.day ? "clears every day condition" : "fails " + (c.day_failed || []).join(", ")) +
      '">Day ' + (c.day ? "eligible" : "no") + "</span>" +
      '<span class="pill' + (c.swing ? " on" : "") + '" title="' +
      esc(c.swing ? "clears every swing condition" : "fails " + (c.swing_failed || []).join(", ")) +
      '">Swing ' + (c.swing ? "eligible" : "no") + "</span>" +
      (c.trap ? '<span class="pill red">Trap flagged</span>' : "") +
      (c.band && c.band !== "not flagged" ? '<span class="pill yellow">Thin at the level</span>' : "");

    return '<div class="deck"><div class="deck-head">' +
      '<span class="tk mono">' + esc(c.sym) + "</span>" +
      '<span class="nm">' + esc(c.name) + "</span>" +
      '<span class="sector">' + esc(c.sector || "sector not on file") + "</span>" +
      '<span class="right">' + badges +
      '<a class="pill" href="#/name/' + esc(c.sym) + '">Every appearance</a></span></div>' +
      (hasCatalyst(c)
        ? '<div class="deck-why"><b>Why it gapped</b> ' + esc(c.catalyst) + ", " +
          esc(c.catalyst_why || "") + "." +
          (c.news ? " " + c.news + " stor" + (c.news === 1 ? "y is" : "ies are") +
            " quoted below." : " No story carried the name in the window.") + "</div>"
        : '<div class="deck-why"><b>Why it gapped</b> Nothing explains it. ' +
          esc(c.catalyst_why || "") + ", and it is on the list on its move and " +
          "its volume alone. An unexplained gap is a finding and not a gap in " +
          "the data.</div>") +
      '<div class="deck-grid">' +
      '<div><div class="panel-title">Levels</div>' + ladder(c) +
      '<div style="font-size:11.5px;color:var(--muted);margin-top:8px;line-height:1.5">' +
      "Entry is the premarket high, stop the premarket low, both as published at " +
      esc(session.run_at || "08:45") + ".</div></div>" +
      '<div><div class="panel-title">Premarket tape</div>' + tapePath(c) +
      '<div class="panel-title" style="margin-top:18px">Score, ' + n2(c.score, 0) +
      " of 10</div>" + comps + "</div>" +
      '<div><div class="panel-title">Evidence</div>' + facts +
      '<div class="panel-title" style="margin-top:16px">Catalyst</div>' +
      '<div style="font-size:12.5px;color:var(--ink-2);margin-bottom:10px"><strong>' +
      esc(c.catalyst) + "</strong>, " + esc(c.catalyst_why) + "</div>" +
      (heads ? '<div class="panel-title">Headlines, newest first</div>' + heads : "") +
      '<div style="font-size:11.5px;color:var(--muted);margin-top:10px;line-height:1.5">' +
      esc(c.trap_why || "") + "</div></div></div>" + outcome + "</div>";
  }
  function fact(k, v) {
    return '<div class="fact"><div class="k">' + esc(k) + '</div><div class="v num">' +
      v + "</div></div>";
  }

  /* ---------- screens ---------- */
  var state = { selected: null, filter: "all" };

  function fixtureBanner(p) {
    if (!p.fixture) return "";
    return '<div class="card verdict" style="margin-top:18px">' +
      '<div class="rule" style="background:var(--warn)"></div>' +
      '<div class="vin"><div class="vt">This is not a morning that happened</div>' +
      '<div class="vs">' + esc(p.fixture) + ". Every figure below is from that " +
      "packet and none of it describes a market.</div></div></div>";
  }

  function screenMorning(p, root) {
    var C = p.candidates;
    function passes(c) {
      if (state.filter === "day") return !!c.day;
      if (state.filter === "swing") return !!c.swing;
      if (state.filter === "green") return c.conv === "green";
      if (state.filter === "up") return c.dir === "up";
      if (state.filter === "down") return c.dir === "down";
      return true;
    }
    if (!state.selected || !C.some(function (c) { return c.sym === state.selected; })) {
      state.selected = C.length ? C[0].sym : null;
    }
    var greens = C.filter(function (c) { return c.conv === "green"; }).length;
    var top = C[0] || {};
    var tally = p.tally || {};
    var rk = (p.prov.ranking || {});

    var FILTERS = [["all", "All " + C.length], ["day", "Day eligible"],
      ["swing", "Swing eligible"], ["green", "Green conviction"],
      ["up", "Gapped up"], ["down", "Gapped down"]];

    var html = fixtureBanner(p) + tapeHTML(p.tape) + kpisHTML([
      { l: "Candidates kept", v: C.length,
        s: "of " + (rk.subscribed_considered || NIL) + " ranked, cap " + (rk.cap || NIL) },
      { l: "Day eligible", v: (tally.day || {}).eligible == null ? NIL : tally.day.eligible,
        s: C.filter(function (c) { return c.day; }).map(function (c) { return c.sym; }).join(", ") || "none" },
      { l: "Swing eligible", v: (tally.swing || {}).eligible == null ? NIL : tally.swing.eligible,
        s: C.filter(function (c) { return c.swing; }).map(function (c) { return c.sym; }).join(", ") || "none" },
      { l: "Green conviction", v: greens, s: "score 7 or more, either direction" },
      { l: "Largest gap", v: top.sym || NIL,
        s: pct(top.gap) + (top.catalyst ? " on " + top.catalyst : "") }
    ]);

    html += '<section><div class="shead"><h2>The gap spine</h2>' +
      '<span class="note">click a row to load it below</span></div>' +
      '<p class="snote">Every candidate on one axis. Distance from the centre line is the ' +
      "premarket gap against the prior close; the side is direction. Conviction is the " +
      "stripe and the word, never the bar colour, because the score is unsigned: a name " +
      "falling hard and a name rising hard can tie.</p>" +
      '<div class="filters noprint" id="filters">' + FILTERS.map(function (f) {
        return '<button class="chip" type="button" data-f="' + f[0] + '" aria-pressed="' +
          (f[0] === state.filter) + '">' + esc(f[1]) + "</button>";
      }).join("") + "</div>" +
      '<div class="spine" id="spine">' + spineHTML(C.filter(passes), state.selected) + "</div>" +
      '<div class="legendrow"><span class="lg"><span class="sw green"></span> Green, 7 or more</span>' +
      '<span class="lg"><span class="sw yellow"></span> Yellow, 4 to 6</span>' +
      '<span class="lg"><span class="sw red"></span> Red, under 4</span>' +
      '<span class="lg" style="margin-left:auto">Scale fixed at ±' +
      KNOBS.spine_scale_pct + " percent</span></div></section>";

    html += '<section><div class="shead"><h2>The selected name</h2></div>' +
      '<div id="deck" class="interactive-deck"></div>' +
      '<div id="printdeck" class="printonly"></div></section>';

    html += pipelineSection(p) + compositionSection(p) + notableSection(p) +
      calendarSection(p) + comingUpSection(p);
    root.innerHTML = html;
    // The notable movers table routes to the Name screen the way the
    // midday tables do; a mover is often a candidate on another session.
    root.addEventListener("click", function (e) {
      var tr = e.target.closest("[data-goto]");
      if (tr) location.hash = "#/name/" + tr.dataset.goto;
    });

    $("filters").addEventListener("click", function (e) {
      var b = e.target.closest("[data-f]"); if (!b) return;
      state.filter = b.dataset.f;
      Array.prototype.forEach.call($("filters").children, function (ch) {
        ch.setAttribute("aria-pressed", String(ch.dataset.f === state.filter));
      });
      $("spine").innerHTML = spineHTML(C.filter(passes), state.selected);
    });
    $("spine").addEventListener("click", function (e) {
      var r = e.target.closest("[data-sym]"); if (!r) return;
      state.selected = r.dataset.sym;
      $("spine").innerHTML = spineHTML(C.filter(passes), state.selected);
      drawDeck();
    });
    function drawDeck() {
      var c = C.filter(function (x) { return x.sym === state.selected; })[0];
      if (!c) { $("deck").innerHTML = ""; return; }
      $("deck").innerHTML = deckHTML(c, p);
      var w = $("deck").querySelector(".chart-wrap");
      if (w) wirePath(w, c);
    }
    drawDeck();
    window.__buildPrint = function () {
      $("printdeck").innerHTML = C.map(function (c) {
        return '<div class="print-deck">' + deckHTML(c, p) + "</div>";
      }).join("");
    };
  }

  /* Section 5 of the report, which the desk carried in its payload and drew
     nowhere until 2026-09-04. It is the one section about names that are NOT
     candidates, so a screen that omits it answers "what should I look at"
     with the pool only. */
  function notableSection(p) {
    var rows = p.movers || [];
    var lists = p.mover_lists || {};
    var names = Object.keys(lists);
    if (!rows.length && !names.length) return "";
    var max = Math.max.apply(null,
      rows.map(function (r) { return Math.abs(r.move || 0); }).concat([1])) * 1.12;
    var body = rows.length
      ? '<div class="card pad scroll"><table><thead><tr><th>Name</th><th>Company</th>' +
        '<th>Ranked on</th><th style="text-align:right">Move</th><th></th>' +
        '<th style="text-align:right">Sigma</th><th style="text-align:right">Market cap</th>' +
        "</tr></thead><tbody>" + rows.map(function (r) {
          return '<tr class="clickable" data-goto="' + esc(r.sym) + '">' +
            '<td class="tk">' + esc(r.sym) + "</td>" +
            '<td style="color:var(--muted);max-width:230px;overflow:hidden;' +
            'text-overflow:ellipsis;white-space:nowrap">' + esc(r.name || "") +
            (r.watch ? ' <span class="pill on">also a candidate</span>' : "") + "</td>" +
            '<td style="color:var(--muted)">' + esc(LEG_WORD[r.leg] || r.leg || NIL) + "</td>" +
            '<td class="n ' + dirClass(r.move) + '">' + pct(r.move) + "</td>" +
            "<td>" + minibar(r.move, max) + "</td>" +
            '<td class="n">' + (r.sigma == null ? NIL : n2(r.sigma, 1) + "\u03c3") + "</td>" +
            '<td class="n">' + big(r.mcap) + "</td></tr>";
        }).join("") + "</tbody></table></div>"
      : '<div class="card pad empty">No list produced a row this morning.</div>';
    // Every list says its own state and denominator, always, because a short
    // list with nothing beside it reads as a quiet market rather than as a
    // ranking key that was null.
    var states = names.length
      ? '<div class="card pad" style="margin-top:13px">' +
        '<div class="panel-title">How each list came out</div>' +
        names.sort().map(function (k) {
          var l = lists[k];
          return '<div class="reason"><span class="mono rk">' +
            esc((l.state || "unknown").replace(/_/g, " ")) + "</span><span>" +
            esc(l.text || (k.replace(/_/g, " ") + ": nothing recorded")) +
            "</span></div>";
        }).join("") + "</div>"
      : "";
    return '<section><div class="shead"><h2>What else moved</h2>' +
      '<span class="note">not candidates</span></div>' +
      '<p class="snote">Names outside this morning\'s pool that moved anyway, ranked ' +
      "within one leg at a time so a premarket move never displaces a prior session " +
      "one. Nothing here was screened; it is the context the watchlists cannot " +
      "give you.</p>" + body + states + "</section>";
  }

  /* Section 9. Tomorrow's setup, today. */
  function comingUpSection(p) {
    var c = p.coming_up || {};
    if (c.checked == null && !(c.tomorrow || []).length) return "";
    var when = (c.window || []).length === 2
      ? esc(c.window[0]) + " to " + esc(c.window[1]) : "";
    var body;
    if (!c.checked) {
      body = '<div class="card pad empty">The calendar was not checked this ' +
        "morning, so this is not an empty list, it is an unasked question.</div>";
    } else if (!(c.tomorrow || []).length) {
      body = '<div class="card pad empty">The calendar was checked and no ' +
        "notable name reports tomorrow.</div>";
    } else {
      body = '<div class="card pad scroll"><table><thead><tr><th>Name</th>' +
        '<th>Company</th><th>When</th><th style="text-align:right">Estimate</th>' +
        "</tr></thead><tbody>" + c.tomorrow.map(function (r) {
          return '<tr><td class="tk">' + esc(bare(r.symbol || r.code)) + "</td>" +
            '<td style="color:var(--muted)">' + esc(r.name || "") + "</td>" +
            '<td class="mono">' + esc(r.report_date || r.date || NIL) + " " +
            esc(r.timing || r.report_time || "") + "</td>" +
            '<td class="n">' + (r.estimate == null ? NIL : n2(r.estimate)) +
            "</td></tr>";
        }).join("") + "</tbody></table></div>";
    }
    return '<section><div class="shead"><h2>Coming up</h2>' +
      (when ? '<span class="note">' + when + "</span>" : "") + "</div>" +
      '<p class="snote">' + esc(c.definition
        ? "Notable means " + c.definition + "."
        : "Names worth knowing report between these dates.") +
      " Tomorrow's setup, today.</p>" + body + "</section>";
  }

  function pipelineSection(p) {
    var rk = p.prov.ranking || {};
    var tally = p.tally || {};
    var stages = [
      ["Pool assembled", p.prov.pool_size, p.prov.pool_size,
        "earnings, overnight news, prior movers, recent runners"],
      ["Subscribed", p.prov.subscribed, p.prov.pool_size,
        "the socket cannot carry the pool, so discover picks"],
      ["Ranked on gap", rk.subscribed_considered, p.prov.subscribed,
        "measured from the collector, not the tier"],
      ["Cleared floors", rk.cleared_floors, rk.subscribed_considered,
        (rk.below_floor || 0) + " below the price or gap floor"],
      ["Kept", rk.kept, rk.cleared_floors,
        (rk.capped_out || 0) + " cut by the cap of " + (rk.cap || NIL) + ", not by a screen"],
      ["Day eligible", (tally.day || {}).eligible, rk.kept, "cleared every day condition"],
      ["Swing eligible", (tally.swing || {}).eligible, rk.kept, "cleared every swing condition"]
    ].filter(function (s) { return s[1] != null; });
    if (!stages.length) return "";
    var pipe = '<div class="pipe">' + stages.map(function (s, i) {
      var share = s[2] ? Math.max(1.5, s[1] / s[2] * 100) : 100;
      return '<div class="stage"><div class="st">' + esc(s[0]) + '</div><div class="n num">' +
        s[1] + '</div><div class="kept"><i style="width:' + share + "%;background:" +
        ramp(i, stages.length) + '"></i></div><div class="d">' + esc(s[3]) + "</div></div>";
    }).join("") + "</div>";

    var total = (tally.candidates_examined || 0);
    function condBars(t) {
      if (!t || !t.failed_by_condition) return '<div class="empty">Not recorded.</div>';
      var keys = Object.keys(t.failed_by_condition).sort(function (a, b) {
        return t.failed_by_condition[b].failed - t.failed_by_condition[a].failed;
      });
      return keys.map(function (k) {
        var v = t.failed_by_condition[k];
        var un = v.unmeasured || 0, no = v.measured_and_failed || 0, ok = v.cleared || 0;
        var u = function (x) { return (x / total * 100).toFixed(2) + "%"; };
        return '<div class="cond"><span class="cn">' + esc(k.replace(/_/g, " ")) + "</span>" +
          '<span class="track">' +
          (ok ? '<i class="ok" style="width:' + u(ok) + '"></i>' : "") +
          (no ? '<i class="no" style="width:' + u(no) + '"></i>' : "") +
          (un ? '<i class="un" style="width:' + u(un) + '"></i>' : "") +
          "<span>" + (v.failed ? v.failed + " failed" : "all clear") +
          (un ? ", " + un + " unmeasured" : "") + "</span></span></div>";
      }).join("");
    }
    return '<section><div class="shead"><h2>How the list was cut</h2></div>' +
      '<p class="snote">The pipeline from the watchlist to the names that cleared a screen. ' +
      "The bar in each stage is the share carried forward, against that stage's own " +
      "predecessor and not a shared scale.</p>" + pipe +
      '<div class="cols2" style="margin-top:15px">' +
      '<div class="card pad"><div class="panel-title">Day screen, condition by condition</div>' +
      condBars(tally.day) + "</div>" +
      '<div class="card pad"><div class="panel-title">Swing screen, condition by condition</div>' +
      condBars(tally.swing) + "</div></div>" +
      '<div class="legendrow"><span class="lg"><span class="sw" style="background:var(--r1)"></span> cleared</span>' +
      '<span class="lg"><span class="sw" style="background:var(--r4)"></span> measured and failed</span>' +
      '<span class="lg"><span class="sw" style="background:var(--sunk);border:1px dashed var(--line-strong)"></span> never measured</span></div></section>';
  }

  function groupBars(obj) {
    if (!obj) return '<div class="empty">Not recorded.</div>';
    var keys = Object.keys(obj).sort(function (a, b) { return obj[b].length - obj[a].length; });
    if (!keys.length) return '<div class="empty">Not recorded.</div>';
    var max = obj[keys[0]].length;
    return keys.map(function (k, i) {
      return '<div class="sbar"><span class="sn">' + esc(k) + "</span>" +
        '<span class="st2"><i style="width:' + (obj[k].length / max * 46) + "%;background:" +
        ramp(keys.length - 1 - i, keys.length) + '"></i><span class="mono">' +
        obj[k].length + " · " + esc(obj[k].join(", ")) + "</span></span></div>";
    }).join("");
  }
  function compositionSection(p) {
    var sh = p.shape || {};
    return '<section><div class="shead"><h2>What kind of morning this is</h2></div>' +
      '<p class="snote">Concentration is the thing a list of names hides.</p>' +
      '<div class="cols2"><div class="card pad"><div class="panel-title">Sector</div>' +
      groupBars(sh.sectors) + "</div>" +
      '<div class="card pad"><div class="panel-title">Catalyst class</div>' +
      groupBars(sh.catalyst_classes) +
      '<div class="panel-title" style="margin-top:16px">Direction</div>' +
      groupBars(sh.gap_direction) + "</div></div></section>";
  }
  function calendarSection(p) {
    if (!p.econ || !p.econ.length) return "";
    return '<section><div class="shead"><h2>On the calendar</h2></div>' +
      '<div class="card pad scroll"><table><thead><tr><th>When (ET)</th><th>Release</th>' +
      '<th>Period</th><th style="text-align:right">Forecast</th>' +
      '<th style="text-align:right">Previous</th><th style="text-align:right">Actual</th>' +
      "</tr></thead><tbody>" + p.econ.map(function (e) {
        var day = (e.time_et || "").slice(0, 10), t = (e.time_et || "").slice(11, 16);
        return "<tr><td class='mono'>" + (day === p.session ? "today " : day.slice(5) + " ") +
          t + "</td><td>" + esc(e.title) + '</td><td style="color:var(--muted)">' +
          esc(e.period) + '</td><td class="n">' + (e.forecast == null ? NIL : e.forecast) +
          '</td><td class="n" style="color:var(--muted)">' +
          (e.previous == null ? NIL : e.previous) + '</td><td class="n">' +
          (e.actual == null ? "not out" : e.actual) + "</td></tr>";
      }).join("") + "</tbody></table></div></section>";
  }

  /* What noon will grade, shown while the pass has not run. A screen that
     answers "not yet" and nothing else wastes the reader's click; the levels
     below are exactly what the 12:00 pass will read back, so they are the
     most useful thing this screen can hold in the meantime. */
  function pendingLevels(p) {
    var rows = (p.candidates || []).slice().sort(function (a, b) {
      return (a.rank || 99) - (b.rank || 99); });
    if (!rows.length) return "";
    return '<section><div class="shead"><h2>What noon will grade</h2>' +
      '<span class="note">' + rows.length + " published at " +
      esc(p.run_at || "08:45") + "</span></div>" +
      '<p class="snote">The entry and the stop the morning printed, exactly as ' +
      "published. The pass reads each one back against the open and says whether it " +
      "was ever reachable. It grades these levels and never the corrected ones the " +
      "night writes later.</p>" +
      '<div class="card pad scroll"><table><thead><tr><th>Name</th><th>Conviction</th>' +
      '<th style="text-align:right">Gap</th><th style="text-align:right">Prior close</th>' +
      '<th style="text-align:right">Entry</th><th style="text-align:right">Stop</th>' +
      '<th>Screens</th></tr></thead><tbody>' + rows.map(function (c) {
        var screens = [c.day ? "day" : "", c.swing ? "swing" : ""]
          .filter(Boolean).join(" and ");
        return '<tr class="clickable" data-goto="' + esc(c.sym) + '">' +
          '<td class="tk">' + esc(c.sym) + "</td>" +
          '<td><span class="pill ' + esc(c.conv || "") + '">' + convWord(c.conv) +
          "</span></td>" +
          '<td class="n ' + dirClass(c.gap) + '">' + pct(c.gap) + "</td>" +
          '<td class="n">' + n2(c.prior_close) + '</td>' +
          '<td class="n">' + n2(c.entry) + '</td><td class="n">' + n2(c.stop) + "</td>" +
          '<td style="color:var(--muted)">' + (screens || "neither") + "</td></tr>";
      }).join("") + "</tbody></table></div></section>";
  }

  function fmtLeft(total) {
    if (total < 0) total = 0;
    var h = Math.floor(total / 3600);
    var m = Math.floor((total % 3600) / 60);
    var x = total % 60;
    var out = "";
    if (h) out += "<b>" + h + "</b><span>h</span>";
    if (h || m) out += "<b>" + (h ? pad2(m) : m) + "</b><span>m</span>";
    out += "<b>" + ((h || m) ? pad2(x) : x) + "</b><span>s</span>";
    return out;
  }

  function middayWaiting(p, root) {
    var now = etNow();
    var runAt = KNOBS.midday_run_time || "12:00";
    var dueBy = KNOBS.midday_due || "12:20";
    var runM = toMin(runAt), dueM = toMin(dueBy);
    var builtClock = (INDEX.built_at || "").slice(11, 16);
    var builtM = /^\d\d:\d\d$/.test(builtClock) ? toMin(builtClock) : -1;
    var isToday = (p.session === now.date);
    var state, lead, target = null;

    if (!isToday) {
      state = "bad";
      lead = "The 12:00 pass never ran for " + esc(p.session) + ", so nothing was " +
        "read back against the levels that morning published. That is a different " +
        "fact from a session where the pass ran and nothing triggered, and this " +
        "screen will not let the two look alike.";
    } else if (now.mins < runM) {
      state = "note";
      target = runM;
      lead = "The pass fires at " + esc(runAt) + " Eastern and reads today's " +
        (p.candidates || []).length + " published levels back against the open. It " +
        "has not run yet. When it does, this screen fills in on its own next rebuild.";
    } else if (now.mins < dueM) {
      state = "note";
      target = dueM;
      lead = "The pass fired at " + esc(runAt) + " and is expected to have written by " +
        esc(dueBy) + ". This page was built at " + esc(builtClock || NIL) +
        " Eastern, before that, so reload it once the desk has rebuilt.";
    } else if (builtM >= 0 && builtM < dueM) {
      state = "note";
      lead = "It is " + esc(now.clock) + " Eastern and the pass was due by " +
        esc(dueBy) + ", but this page was built at " + esc(builtClock) +
        ", before it. The page is behind the machine, not the other way round. " +
        "Rebuild the desk and the session will carry its midday.";
    } else {
      state = "bad";
      lead = "The pass was due by " + esc(dueBy) + " Eastern and had still not " +
        "written when this page was built at " + esc(builtClock || NIL) +
        ". Something stopped the 12:00 step.";
    }

    var head = state === "bad"
      ? (isToday ? "The 12:00 pass has not written" : "The 12:00 pass never ran")
      : (target === runM && isToday && now.mins < runM ? "Until the 12:00 pass"
        : target ? "Until it is due" : "This page is behind");

    root.innerHTML = '<section><div class="shead"><h2>Midday</h2>' +
      '<span class="note">' + esc(p.session) + "</span></div>" +
      '<div class="card"><div class="waiting">' + chip(state) +
      (target == null ? "" : '<div class="count" id="countdown"></div>') +
      (target == null ? "" : '<div class="panel-title" style="margin-top:9px">' +
        esc(head) + "</div>") +
      '<p class="lead">' + lead + "</p></div></div>" +
      pendingLevels(p) + "</section>";

    root.addEventListener("click", function (e) {
      var tr = e.target.closest("[data-goto]");
      if (tr) location.hash = "#/name/" + tr.dataset.goto;
    });
    if (target == null) return;
    var box = $("countdown");
    function tick() {
      var t = etNow();
      var left = (target - t.mins) * 60 - t.secs;
      if (left <= 0) { box.innerHTML = "<b>0</b><span>s</span>"; return; }
      box.innerHTML = fmtLeft(left);
    }
    tick();
    TIMER = setInterval(tick, 1000);
  }

  function screenMidday(p, root) {
    var mid = p.midday;
    if (!mid) { middayWaiting(p, root); return; }
    var rows = p.candidates.filter(function (c) { return c.mid; });
    var states = {};
    rows.forEach(function (c) { states[c.mid.state] = (states[c.mid.state] || 0) + 1; });
    var maxMove = Math.max.apply(null,
      rows.map(function (c) { return Math.abs(c.mid.move || 0); }).concat([1])) * 1.15;

    var html = kpisHTML([
      { l: "Picks carried", v: rows.length, s: "published at " + esc(p.run_at || "08:45") },
      { l: "Entry reached", v: states.triggered || 0, s: "the level printed was tradeable" },
      { l: "Opened past it", v: states.gapped_through || 0, s: "the open was already through" },
      { l: "Never reached", v: states.never_triggered || 0, s: "the session high fell short" },
      { l: "Read at", v: (mid.generated || "").slice(11, 16) || NIL, s: "ET, from the vendor sweep" }
    ]);

    html += '<section><div class="shead"><h2>Against the levels the morning published</h2>' +
      '<span class="note">' + esc(p.session) + "</span></div>" +
      '<p class="snote">Each bar is the move from the prior close as of noon. The chip says ' +
      "whether the entry the morning printed was ever reachable, and the sentence is the " +
      "packet's own reason.</p>" +
      '<div class="card pad scroll"><table><thead><tr><th>Name</th><th>Entry status</th>' +
      '<th style="text-align:right">Move</th><th></th>' +
      '<th style="text-align:right">Open</th><th style="text-align:right">High</th>' +
      '<th style="text-align:right">Low</th><th style="text-align:right">Last</th>' +
      '<th style="text-align:right">Day RVOL</th></tr></thead><tbody>' +
      rows.map(function (c) {
        var m = c.mid;
        return '<tr class="clickable" data-goto="' + esc(c.sym) + '">' +
          '<td class="tk">' + esc(c.sym) + "</td>" +
          '<td><span class="pill ' + (m.state === "never_triggered" ? "" : "on") + '">' +
          esc(MID_WORD[m.state] || m.state) + "</span></td>" +
          '<td class="n ' + dirClass(m.move) + '">' + pct(m.move) + "</td>" +
          "<td>" + minibar(m.move, maxMove) + "</td>" +
          '<td class="n">' + n2(m.open) + '</td><td class="n">' + n2(m.high) + "</td>" +
          '<td class="n">' + n2(m.low) + '</td><td class="n">' + n2(m.last) + "</td>" +
          '<td class="n">' + n2(m.day_rvol) + "×</td></tr>";
      }).join("") + "</tbody></table></div>" +
      '<div class="card pad" style="margin-top:13px">' +
      '<div class="panel-title">Why, in the packet\'s own words</div>' +
      rows.map(function (c) {
        return '<div class="reason"><span class="mono rk">' + esc(c.sym) + "</span>" +
          "<span>" + esc(c.mid.why || "") +
          (c.mid.fill != null
            ? " Filled at " + n2(c.mid.fill) + ", best against the fill " +
              pct(c.mid.best) + ", now " + pct(c.mid.now) + "."
            : "") + "</span></div>";
      }).join("") + "</div></section>";

    if (mid.movers && mid.movers.length) {
      var mm = Math.max.apply(null,
        mid.movers.map(function (r) { return Math.abs(r.move || 0); }).concat([1])) * 1.12;
      html += '<section><div class="shead"><h2>What moved that the morning never named</h2>' +
        '<span class="note">ranked by ' + esc(mid.rank_by || "move") + "</span></div>" +
        '<div class="card pad scroll"><table><thead><tr><th>Name</th><th>Company</th>' +
        '<th style="text-align:right">Move</th><th></th>' +
        '<th style="text-align:right">Last</th><th style="text-align:right">Day RVOL</th>' +
        "</tr></thead><tbody>" + mid.movers.slice(0, 20).map(function (r) {
          return '<tr><td class="tk">' + esc(r.sym) + '</td>' +
            '<td style="color:var(--muted);max-width:260px;overflow:hidden;' +
            'text-overflow:ellipsis;white-space:nowrap">' + esc(r.name || "") + "</td>" +
            '<td class="n ' + dirClass(r.move) + '">' + pct(r.move) + "</td>" +
            "<td>" + minibar(r.move, mm) + "</td>" +
            '<td class="n">' + n2(r.last) + '</td><td class="n">' +
            (r.rvol == null ? NIL : n2(r.rvol) + "×") + "</td></tr>";
        }).join("") + "</tbody></table></div></section>";
    }

    if (mid.floors) {
      html += '<section><div class="shead"><h2>What the floors turned down</h2></div>' +
        '<p class="snote">The biggest movers each floor refused, which is the only way to ' +
        "ask what a floor costs.</p><div class=\"card pad\"><pre class=\"mono\" " +
        'style="white-space:pre-wrap;font-size:12px;color:var(--ink-2);margin:0">' +
        esc(JSON.stringify(mid.floors, null, 2)) + "</pre></div></section>";
    }
    root.innerHTML = html;
    root.addEventListener("click", function (e) {
      var tr = e.target.closest("[data-goto]");
      if (tr) location.hash = "#/name/" + tr.dataset.goto;
    });
  }

  /* The written report, inlined with its session. This screen IS the
     retired site/PremarketDesk.html archive: that page existed to read old
     mornings' prose across sessions, the desk took its filename on
     2026-09-04, and a filename is not a reason to lose what the page did. */
  function screenReport(p, root) {
    var has = { morning: !!p.report, midday: !!p.report_midday };
    if (!has.morning && !has.midday) {
      root.innerHTML = '<section><div class="shead"><h2>The report</h2></div>' +
        '<div class="card pad empty">No report was written for ' + esc(p.session) +
        ". The morning stopped before the render step, which is a different " +
        "thing from a morning that found nothing.</div></section>";
      return;
    }
    var seg = (has.morning && has.midday)
      ? '<div class="seg noprint" style="margin-left:auto">' +
        '<button type="button" data-rep="morning" aria-pressed="true">Morning</button>' +
        '<button type="button" data-rep="midday" aria-pressed="false">Midday</button>' +
        "</div>"
      : "";
    var first = has.morning ? "morning" : "midday";
    root.innerHTML = '<section><div class="shead"><h2>The report, as written</h2>' +
      '<span class="note">' + esc(p.session) + "</span>" + seg + "</div>" +
      '<p class="snote">The words that were delivered that morning, rendered from ' +
      "the same markdown the email carried and styled by the same stylesheet, so " +
      "this and the copy in your inbox are the same document.</p>" +
      '<div class="card" id="rep-body"><div class="report">' +
      (first === "morning" ? p.report : p.report_midday) + "</div></div></section>";
    root.addEventListener("click", function (e) {
      var b = e.target.closest("button[data-rep]");
      if (!b) return;
      Array.prototype.forEach.call(root.querySelectorAll("button[data-rep]"),
        function (o) { o.setAttribute("aria-pressed", String(o === b)); });
      $("rep-body").innerHTML = '<div class="report">' +
        (b.dataset.rep === "morning" ? p.report : p.report_midday) + "</div>";
      window.scrollTo(0, 0);
    });
  }

  function screenSession(p, root) {
    var d = p.session;
    var tally = p.tally || {};
    var mid = p.midday;
    root.innerHTML = tapeHTML(p.tape) + kpisHTML([
      { l: "Candidates", v: p.candidates.length, s: "examined at " + esc(p.run_at || "08:45") },
      { l: "Day eligible", v: (tally.day || {}).eligible == null ? NIL : tally.day.eligible, s: "" },
      { l: "Swing eligible", v: (tally.swing || {}).eligible == null ? NIL : tally.swing.eligible, s: "" },
      { l: "Midday", v: mid ? "ran" : (p.session === etNow().date ? "due" : NIL),
        s: mid ? "read at " + (mid.generated || "").slice(11, 16)
          : p.session === etNow().date
            ? "at " + (KNOBS.midday_run_time || "12:00") + " ET"
            : "the 12:00 pass never ran" },
      { l: "Vendor calls", v: p.api_calls == null ? NIL : p.api_calls, s: "on the morning pass" }
    ]) +
      '<section><div class="shead"><h2>This session</h2></div>' +
      '<p class="snote">The morning published the levels; the midday pass read them back. ' +
      "Both are below, and the tape the bars were drawn from is recorded as <span " +
      'class="mono">' + esc(p.bars_source || "unknown") + "</span>.</p>" +
      '<div class="cols2">' +
      '<a class="card pad" style="text-decoration:none;display:block" href="#/session/' + esc(d) + '/morning">' +
      '<div class="panel-title">Morning</div><div style="font-size:20px;font-weight:600">' +
      p.candidates.length + " candidates</div>" +
      '<div class="snote" style="margin:6px 0 0">The gap spine, every name\'s levels, the ' +
      "tape, the score and what cut the list.</div></a>" +
      '<a class="card pad" style="text-decoration:none;display:block" href="#/session/' + esc(d) + '/midday">' +
      '<div class="panel-title">Midday</div><div style="font-size:20px;font-weight:600">' +
      (mid ? p.candidates.filter(function (c) { return c.mid; }).length + " carried"
        : p.session === etNow().date ? "due at " + (KNOBS.midday_run_time || "12:00")
        : "not run") +
      "</div>" +
      '<div class="snote" style="margin:6px 0 0">What the open did to the levels the morning ' +
      "printed, and what moved that it never named.</div></a>" +
      '<a class="card pad" style="text-decoration:none;display:block" href="#/session/' + esc(d) + '/report">' +
      '<div class="panel-title">The report</div><div style="font-size:20px;font-weight:600">' +
      (p.report ? "as written" : "not written") + "</div>" +
      '<div class="snote" style="margin:6px 0 0">The words delivered that morning, and ' +
      "the midday one where the 12:00 pass wrote it.</div></a></div></section>" +
      recordSection(p) + healthSection(p);
  }

  function recordSection(p) {
    var R = p.record || {};
    if (!R.picks) return "";
    var vals = [
      { l: "Median best while held", v: R.median_best_while_held },
      { l: "Median booked", v: R.median_booked_pct }
    ].filter(function (x) { return x.v != null; });
    var m = Math.max.apply(null, vals.map(function (x) { return Math.abs(x.v); }).concat([1])) * 1.25;
    var div = vals.map(function (x) {
      var w = Math.abs(x.v) / m * 50;
      return '<div style="display:grid;grid-template-columns:160px minmax(0,1fr) 62px;' +
        'gap:10px;align-items:center;margin-bottom:9px">' +
        '<span style="font-size:12.5px;color:var(--ink-2)">' + esc(x.l) + "</span>" +
        '<span style="position:relative;height:18px"><span style="position:absolute;top:0;' +
        'bottom:0;left:50%;width:1px;background:var(--line-strong)"></span>' +
        '<i style="position:absolute;top:3px;height:12px;background:' +
        (x.v >= 0 ? "var(--r2)" : "var(--r4)") + ";" +
        (x.v >= 0 ? "left:50%;border-radius:0 4px 4px 0;" : "right:50%;border-radius:4px 0 0 4px;") +
        "width:" + w + '%"></i></span>' +
        '<span class="num ' + dirClass(x.v) + '" style="text-align:right;font-size:13px">' +
        pct(x.v) + "</span></div>";
    }).join("");

    var peak = "";
    if (R.peaked_within_10_min != null) {
      var maxN = Math.max(R.peaked_within_10_min, R.peaked_after_100_min || 0) || 1;
      peak = [
        { l: "Peaked within 10 minutes", n: R.peaked_within_10_min,
          k: R.peaked_within_10_min_closed_red, w: "closed red", c: "var(--bad)" },
        { l: "Peaked after 100 minutes", n: R.peaked_after_100_min,
          k: R.peaked_after_100_min_closed_green, w: "closed green", c: "var(--good)" }
      ].map(function (r) {
        return '<div style="margin-bottom:13px"><div style="display:flex;' +
          'justify-content:space-between;align-items:baseline;gap:10px">' +
          '<span style="font-size:12.5px;color:var(--ink-2)">' + esc(r.l) + "</span>" +
          '<span class="num" style="font-size:13px">' + r.n + " picks</span></div>" +
          '<div style="height:14px;background:var(--sunk);border-radius:3px;margin-top:5px;' +
          'overflow:hidden"><i style="display:block;height:100%;width:' +
          (r.n / maxN * 100) + "%;background:" + r.c + '"></i></div>' +
          '<div style="font-size:11.5px;color:var(--muted);margin-top:4px">all ' + r.k +
          " of them " + esc(r.w) + "</div></div>";
      }).join("");
    }
    return '<section><div class="shead"><h2>What the record says</h2>' +
      '<span class="note">' + R.picks.rows + " picks over " + R.picks.sessions +
      " recorded sessions</span></div>" +
      '<div class="cols2"><div class="card pad">' +
      '<div class="panel-title">Where the median pick ends up</div>' + div +
      '<p class="snote" style="margin:12px 0 0">The gap between the two is the whole problem: ' +
      "the move is there, the exit is not taking it.</p></div>" +
      '<div class="card pad"><div class="panel-title">Time to the high, against how it closed</div>' +
      (peak || '<div class="empty">Not recorded yet.</div>') + "</div></div>" +
      kpisHTML([
        { l: "Picks recorded", v: R.picks.rows, s: "over " + R.picks.sessions + " sessions" },
        { l: "Triggered", v: R.triggered_total, s: (R.triggered_within_30_min || 0) + " inside 30 minutes" },
        { l: "Never triggered", v: (R.never_triggered || {}).rows, s: "entry was never reached" },
        { l: "Skipped", v: (R.skipped || {}).rows, s: "a screen or a guard cut them" },
        { l: "Booked", v: (R.booked || {}).rows, s: "closed positions in the paper ledger" }
      ]) + "</section>";
  }

  /* ---------- health, answered rather than dumped ----------
     This screen used to print five blocks of the packet's raw JSON, which is
     the packet talking to itself. Every check below reads the same figures
     and says what they mean; the JSON is still here, folded, because the
     working should be checkable and should not be the first thing read. */
  var CHIP_WORD = { ok: "Fine", watch: "Worth a look", bad: "Fault", note: "Note" };

  function chip(state) {
    return '<span class="chip ' + state + '"><i></i>' + CHIP_WORD[state] + "</span>";
  }

  function healthChecks(p) {
    var h = p.health || {};
    var job = h.job || {}, q = h.quota || {}, cov = h.coverage || {};
    var w = h.window || {}, cap = h.capture || {};
    var out = [];

    var over = job.overdue || [];
    out.push(over.length
      ? { s: "bad", t: "The scheduled steps",
          x: "Steps that should have finished had not when the morning packet was " +
            "written: " + esc(over.join(", ")) + "." }
      : { s: "ok", t: "The scheduled steps",
          x: "Every step the schedule owns had finished by the time the morning " +
            "packet was written, and nothing was overdue." });

    if (q.api_requests != null) {
      out.push({ s: q.refused ? "bad" : q.degraded ? "watch" : "ok",
        t: "The vendor budget",
        x: "The day had spent " + commas(q.api_requests) + " calls of the " +
          commas(q.daily_limit) + " it is allowed when the morning checked at " +
          hhmm(q.read_at) + ", leaving " + commas(q.remaining) + ". " +
          (q.refused
            ? "That was low enough to stand the morning down before it started."
            : q.degraded
              ? "That was low enough to make the morning cut its optional work."
              : "The morning cuts its optional work below " + commas(q.degrade_below) +
                " and stands down entirely below " + commas(q.refuse_below) +
                ", so it was nowhere near either.") });
    }

    if (cov.requested != null) {
      var silent = cov.silent || 0;
      out.push({ s: silent ? "watch" : "ok", t: "What the collector heard",
        x: "It was listening to " + cov.requested + " names and built a minute by " +
          "minute tape for " + cov.produced_bars + " of them. " +
          (silent
            ? silent + " said nothing at all: " +
              esc((cov.silent_symbols || []).map(bare).join(", ")) + "."
            : "None of them went silent.") +
          (cov.peak_trades_per_minute
            ? " At its busiest minute it took " + commas(cov.peak_trades_per_minute) +
              " trades."
            : "") });
    }

    if (w.scheduled_start_et) {
      var late = w.started_late_minutes || 0;
      out.push({ s: late > 2 ? "watch" : "ok", t: "The listening window",
        x: "The socket was meant to run " + esc(w.scheduled_start_et) + " to " +
          esc(w.scheduled_stop_et) + " and started " +
          (late > 0.5 ? n2(late, 1) + " minutes late" : "on time") +
          ". The earliest minute it recorded is " + hhmm(w.first_bar_et) +
          " and the latest is " + hhmm(w.last_bar_et) + ", " +
          n2(w.minutes_since_last_bar, 1) + " minutes before the packet was built." +
          (w.contains_replay
            ? " " + (w.replay_rows || 0) + " rows arrived stamped to the prior " +
              "session rather than this one and were held apart from the premarket " +
              "count rather than added to it."
            : "") });
    }

    if (cap.default_capture_share != null) {
      var measured = (cap.rows || []).filter(function (r) {
        return r.capture_minutes != null; }).length;
      out.push({ s: "note", t: "Premarket volume is an estimate",
        x: "The socket hears roughly " + n2(cap.default_capture_share * 100, 1) +
          " percent of what the consolidated tape prints before the open, so every " +
          "premarket RVOL and float rotation on these screens is scaled up from what " +
          "it heard rather than measured directly. Of the " + (cap.candidates || 0) +
          " names the volume floor was applied to, " + measured +
          " were scaled by that name's own measured share and the rest by the " +
          "standing default. The truth pass writes the measured figure overnight, " +
          "beside these and never over them." });
      var carried = cap.carried_across_the_floor || [];
      if (carried.length) {
        out.push({ s: "watch", t: "Cleared the floor on the estimate",
          x: esc(carried.map(bare).join(", ")) + " cleared the volume floor of " +
            esc(cap.floor || "") + " only once that scaling was applied. On what the " +
            "socket actually heard " + (carried.length === 1 ? "it does" : "they do") +
            " not clear it. This is the one place on these screens where a name is " +
            "present because of a scaling factor and not because of a measurement." });
      }
    }

    out.push(p.bars_source === "run_snapshot"
      ? { s: "ok", t: "The tape behind the pictures",
          x: "Every tape path on this session's screens is drawn from the exact rows " +
            "the morning saw, frozen alongside the packet." }
      : { s: "watch", t: "The tape behind the pictures",
          x: "This session's bars were rebuilt by clipping the collector's whole day " +
            "to the window the packet recorded, which can carry one extra minute at " +
            "the end. The shape is right; the last minute may not be the one the " +
            "morning saw." });
    return out;
  }

  function checksHTML(list) {
    return '<div class="card pad">' + list.map(function (c) {
      return '<div class="check"><div>' + chip(c.s) + "</div><div>" +
        '<div class="t">' + esc(c.t) + '</div><div class="s">' + c.x +
        "</div></div></div>";
    }).join("") + "</div>";
  }

  function verdictHTML(list) {
    function count(k) {
      return list.filter(function (c) { return c.s === k; }).length;
    }
    var bad = count("bad"), watch = count("watch");
    var tone = bad ? "bad" : watch ? "warn" : "good";
    var title = bad
      ? (bad === 1 ? "One thing went wrong" : bad + " things went wrong")
      : watch
        ? (watch === 1 ? "One thing is worth a look"
          : watch + " things are worth a look")
        : "Everything the machine was asked to do, it did";
    var sub = (bad || watch)
      ? "Every other check came back clean."
      : "Every check came back clean. What is marked a note is a standing caveat " +
        "about how the numbers are made, not a fault.";
    return '<div class="card verdict"><div class="rule" style="background:var(--' +
      tone + ')"></div><div class="vin"><div class="vt">' + esc(title) +
      '</div><div class="vs">' + esc(sub) + "</div></div></div>";
  }

  function healthSection(p) {
    return '<section><div class="shead"><h2>Was the machine right</h2>' +
      '<a class="note" href="#/health/' + esc(p.session) +
      '">every check, in full</a></div>' + verdictHTML(healthChecks(p)) + "</section>";
  }

  function screenSessions(root) {
    var rows = INDEX.sessions;
    var months = monthsOnFile();
    var maxGap = CAL_MAX * 1.1;
    // CRITERIA [Screens] sessions_page_size, which was passed into the page
    // from the first build and read by nothing: the list rendered every row.
    // Four sessions hid it. At the inline_sessions ceiling of 400 it is four
    // hundred rows under a calendar the reader came for.
    var PAGE = KNOBS.sessions_page_size || 0;
    function listHTML(limit) {
      var shown = limit ? rows.slice(0, limit) : rows;
      return listTable(shown) + (rows.length > shown.length
        ? '<div class="filters noprint" style="margin-top:11px">' +
          '<button class="chip" type="button" data-more="1">Show all ' +
          rows.length + " sessions</button></div>"
        : "");
    }
    function listTable(rows) {
      return '<div class="card pad scroll"><table><thead><tr><th>Session</th>' +
      '<th style="text-align:right">Cand</th><th style="text-align:right">Day</th>' +
      '<th style="text-align:right">Swing</th><th>Conviction</th><th>Largest gap</th>' +
      '<th></th><th style="text-align:right">Triggered</th><th>Packet</th>' +
      "</tr></thead><tbody>" + rows.map(function (r) {
        var conv = ["green", "yellow", "red"].map(function (k) {
          return r[k] ? '<span class="sw ' + k + '" title="' + r[k] + " " + k +
            '"></span>' : "";
        }).join(" ");
        return '<tr class="clickable" data-date="' + esc(r.date) + '">' +
          '<td class="tk">' + esc(r.date) + "</td>" +
          '<td class="n">' + (r.candidates == null ? NIL : r.candidates) + "</td>" +
          '<td class="n">' + (r.day_eligible == null ? NIL : r.day_eligible) + "</td>" +
          '<td class="n">' + (r.swing_eligible == null ? NIL : r.swing_eligible) + "</td>" +
          "<td>" + conv + "</td>" +
          '<td class="mono">' + esc(r.top_symbol || NIL) + " " +
          '<span class="' + dirClass(r.top_gap_pct) + '">' + pct(r.top_gap_pct) + "</span></td>" +
          "<td>" + minibar(r.top_gap_pct, maxGap) + "</td>" +
          '<td class="n">' + (r.triggered == null ? NIL : r.triggered) + "</td>" +
          '<td style="color:var(--muted);font-size:11.5px">' +
          (r.packet_bytes == null ? NIL
            : big(r.packet_bytes) + (r.packet_compressed ? " gz" : "")) + "</td></tr>";
      }).join("") + "</tbody></table></div>";
    }
    var calHTML = '<div class="calwrap">' + months.map(function (ym) {
      return calMonth(ym, null, false); }).join("") + "</div>" + calKey();

    var NOTE = {
      cal: "A lifted day is a morning the desk holds. The ticker under the date is " +
        "that morning's largest gap and the bar is how large, on one scale across " +
        "every month, so two mornings compare by eye. Everything faint is a day the " +
        "machine did not run: a weekend, a holiday, or a date before the history " +
        "this desk carries.",
      list: "One row a session, newest first. The bar is that morning's largest gap " +
        "on the same shared scale."
    };

    root.innerHTML =
      '<section><div class="shead"><h2>Every session on file</h2>' +
      '<span class="note">' + rows.length + " mornings, " + esc(FIRST) + " to " +
      esc(LAST) + '</span><div class="seg noprint" style="margin-left:auto">' +
      '<button type="button" data-view="cal" aria-pressed="true">Calendar</button>' +
      '<button type="button" data-view="list" aria-pressed="false">List</button>' +
      '</div></div><p class="snote" id="ses-note">' + esc(NOTE.cal) + "</p>" +
      '<div id="ses-view">' + calHTML + "</div></section>";

    var view = $("ses-view");
    wireCal(view, function (date) { location.hash = "#/session/" + date; });
    view.addEventListener("click", function (e) {
      if (e.target.closest("[data-more]")) { view.innerHTML = listHTML(0); return; }
      var tr = e.target.closest("tr[data-date]");
      if (tr) location.hash = "#/session/" + tr.dataset.date;
    });
    root.addEventListener("click", function (e) {
      var b = e.target.closest("button[data-view]");
      if (!b) return;
      var which = b.dataset.view;
      Array.prototype.forEach.call(root.querySelectorAll("button[data-view]"),
        function (o) { o.setAttribute("aria-pressed", String(o === b)); });
      view.innerHTML = which === "cal" ? calHTML : listHTML(PAGE);
      view.dataset.sel = "";
      $("ses-note").textContent = NOTE[which];
    });
  }

  function screenRecord(root) {
    var rows = INDEX.sessions;
    var totals = rows.reduce(function (a, r) {
      a.cand += r.candidates || 0; a.day += r.day_eligible || 0;
      a.swing += r.swing_eligible || 0; a.green += r.green || 0;
      a.trig += r.triggered || 0; a.never += r.never_triggered || 0;
      return a;
    }, { cand: 0, day: 0, swing: 0, green: 0, trig: 0, never: 0 });
    var maxCand = Math.max.apply(null,
      rows.map(function (r) { return r.candidates || 0; }).concat([1]));

    var html = kpisHTML([
      { l: "Sessions on file", v: rows.length, s: "every morning that produced a packet" },
      { l: "Candidates examined", v: totals.cand, s: "across every session" },
      { l: "Day eligible", v: totals.day, s: (totals.cand ? (totals.day / totals.cand * 100).toFixed(1) : "0") + "% of candidates" },
      { l: "Swing eligible", v: totals.swing, s: (totals.cand ? (totals.swing / totals.cand * 100).toFixed(1) : "0") + "% of candidates" },
      { l: "Entries reached", v: totals.trig, s: totals.never + " never reached" }
    ]);

    html += '<section><div class="shead"><h2>Candidates a morning</h2></div>' +
      '<p class="snote">How many names each morning kept, and how many of them cleared a ' +
      "screen. A morning with no eligible name is not a failure; it is the screen doing its job.</p>" +
      '<div class="card pad">' + rows.slice().reverse().map(function (r) {
        var w = (r.candidates || 0) / maxCand * 100;
        var dayW = (r.candidates ? (r.day_eligible || 0) / r.candidates : 0) * w;
        return '<div style="display:grid;grid-template-columns:96px minmax(0,1fr) 130px;' +
          'gap:10px;align-items:center;margin-bottom:5px;font-size:12px">' +
          '<span class="mono" style="color:var(--ink-2)">' + esc(r.date) + "</span>" +
          '<span style="position:relative;height:13px;background:var(--sunk);border-radius:2px">' +
          '<i style="position:absolute;left:0;top:0;bottom:0;width:' + w +
          '%;background:var(--r2);border-radius:2px"></i>' +
          '<i style="position:absolute;left:0;top:0;bottom:0;width:' + dayW +
          '%;background:var(--r4);border-radius:2px"></i></span>' +
          '<span class="mono" style="color:var(--muted)">' + (r.candidates || 0) +
          " kept, " + (r.day_eligible == null ? NIL : r.day_eligible) + " day</span></div>";
      }).join("") +
      '<div class="legendrow"><span class="lg"><span class="sw" style="background:var(--r2)"></span> candidates kept</span>' +
      '<span class="lg"><span class="sw" style="background:var(--r4)"></span> of those, day eligible</span></div>' +
      "</div></section>";

    var newest = INDEX.sessions[0];
    html += '<div id="record-detail"></div>';
    root.innerHTML = html;
    if (newest) {
      var mine = EPOCH;
      loadSession(newest.date).then(function (p) {
        if (p && !stale(mine)) $("record-detail").innerHTML = recordSection(p);
      });
    }
  }

  function screenName(sym, root) {
    root.innerHTML = '<section><div class="shead"><h2><span class="mono">' + esc(sym) +
      "</span></h2><span class=\"note\">reading every session on file</span></div>" +
      '<div id="name-body" class="card pad empty">Reading…</div></section>';
    // ONLY THE SESSIONS THAT CARRY THE NAME. Each session's summary row
    // lists its candidates, so the question is answered off the index and
    // only the matching payloads are inflated. This used to open every
    // inlined session: fine at four, four hundred at the inline_sessions
    // ceiling, each inflated and held. A row written before the column
    // existed carries no symbols and is opened, so an old index degrades
    // to the old behaviour rather than to a wrong answer.
    var needle = "," + sym + ",";
    var dates = INDEX.sessions.filter(function (r) {
      return r.symbols == null || ("," + r.symbols + ",").indexOf(needle) >= 0;
    }).map(function (r) { return r.date; });
    var mine = EPOCH;
    Promise.all(dates.map(function (d) {
      return loadSession(d).catch(function () { return null; });
    })).then(function (all) {
      if (stale(mine)) return;
      var hits = [];
      all.forEach(function (p) {
        if (!p) return;
        p.candidates.forEach(function (c) {
          if (c.sym === sym) hits.push({ p: p, c: c });
        });
      });
      if (!hits.length) {
        $("name-body").innerHTML = esc(sym) +
          " has not been a candidate in any session on file. That is a fact about this " +
          "record, not about the name.";
        return;
      }
      var maxGap = Math.max.apply(null,
        hits.map(function (h) { return Math.abs(h.c.gap || 0); }).concat([1])) * 1.1;
      var body = '<table><thead><tr><th>Session</th><th style="text-align:right">Gap</th>' +
        '<th></th><th style="text-align:right">Score</th><th>Conviction</th>' +
        '<th>Catalyst</th><th>Screens</th><th>At noon</th>' +
        '<th style="text-align:right">Move</th></tr></thead><tbody>' +
        hits.map(function (h) {
          var c = h.c;
          return "<tr><td class='tk'><a href='#/session/" + esc(h.p.session) +
            "/morning'>" + esc(h.p.session) + "</a></td>" +
            '<td class="n ' + dirClass(c.gap) + '">' + pct(c.gap) + "</td>" +
            "<td>" + minibar(c.gap, maxGap) + "</td>" +
            '<td class="n">' + n2(c.score, 0) + "</td>" +
            '<td><span class="pill ' + esc(c.conv || "") + '">' + convWord(c.conv) + "</span></td>" +
            "<td style='color:var(--muted)'>" + esc(c.catalyst || "") + "</td>" +
            "<td style='color:var(--muted)'>" +
            (c.day ? "day " : "") + (c.swing ? "swing" : "") +
            (!c.day && !c.swing ? "neither" : "") + "</td>" +
            "<td>" + (c.mid ? esc(MID_WORD[c.mid.state] || c.mid.state) : NIL) + "</td>" +
            '<td class="n ' + dirClass(c.mid && c.mid.move) + '">' +
            (c.mid ? pct(c.mid.move) : NIL) + "</td></tr>";
        }).join("") + "</tbody></table>";
      $("name-body").className = "card pad scroll";
      $("name-body").innerHTML = body;

      // A deck is a level ladder, a tape path and every headline, so a name
      // that has appeared eighty times used to draw eighty of them before
      // the screen was usable. CRITERIA [Screens] name_decks, newest first,
      // with the rest one click away.
      var decks = document.createElement("div");
      root.appendChild(decks);
      function drawDecks(limit) {
        var shown = limit ? hits.slice(0, limit) : hits;
        decks.innerHTML = shown.map(function (h) {
          return '<section><div class="shead"><h3 style="font-size:15px">' +
            esc(h.p.session) + "</h3></div>" + deckHTML(h.c, h.p) + "</section>";
        }).join("") + (hits.length > shown.length
          ? '<div class="filters noprint"><button class="chip" type="button" ' +
            'data-alldecks="1">Draw the other ' + (hits.length - shown.length) +
            " appearance" + (hits.length - shown.length === 1 ? "" : "s") +
            "</button></div>"
          : "");
        shown.forEach(function (h, i) {
          var w = decks.querySelectorAll(".chart-wrap")[i];
          if (w) wirePath(w, h.c);
        });
      }
      decks.addEventListener("click", function (e) {
        if (e.target.closest("[data-alldecks]")) drawDecks(0);
      });
      drawDecks(KNOBS.name_decks || 0);
    });
  }

  function screenHealth(date, root) {
    root.innerHTML = '<div class="card pad empty" style="margin-top:24px">Reading ' +
      esc(date) + " ...</div>";
    var mine = EPOCH;
    loadSession(date).then(function (p) {
      if (stale(mine)) return;
      if (!p) {
        root.innerHTML = '<div class="card pad empty" style="margin-top:24px">' +
          esc(date) + " is not inlined in this document.</div>";
        return;
      }
      $("stamp-date").textContent = p.session;
      $("stamp-run").textContent = p.run_at || NIL;
      var h = p.health || {};
      var list = healthChecks(p);
      function fold(title, obj) {
        if (!obj || !Object.keys(obj).length) return "";
        return "<details><summary>" + esc(title) + "</summary>" +
          '<div class="body"><pre class="mono" style="white-space:pre-wrap;' +
          'font-size:11.5px;color:var(--ink-2);margin:0">' +
          esc(JSON.stringify(obj, null, 2)) + "</pre></div></details>";
      }
      var out = '<section><div class="shead"><h2>Was the machine right on ' +
        esc(p.session) + "</h2>" +
        '<span class="note">packet at ' + esc(p.run_at || NIL) + " ET</span></div>" +
        '<p class="snote">Every answer below is read out of that morning\'s own ' +
        "packet. This page measures nothing itself, so a wrong figure here is a " +
        "wrong figure in the packet and the fix is upstream of the screen.</p>" +
        verdictHTML(list) + '<div style="margin-top:13px">' + checksHTML(list) +
        "</div></section>";

      var ev = h.evidence || {};
      if (ev.band_thin && ev.band_thin.length) {
        out += '<section><div class="shead"><h2>Thin at the level</h2></div>' +
          '<p class="snote">Names whose published entry sits where very little ' +
          "traded. The level is not wrong; there may be nothing there to fill " +
          "against.</p><div class=\"card pad\">" + ev.band_thin.map(function (r) {
            return '<div class="reason"><span class="mono rk">' +
              esc(bare(r.symbol)) + "</span><span>" + esc(r.why) + "</span></div>";
          }).join("") + "</div></section>";
      }

      out += '<section><div class="shead"><h2>The figures behind the answers</h2>' +
        '</div><p class="snote">Folded away because the sentences above ' +
        "are the point and these are the working. Nothing here is computed by this " +
        "page.</p>" + fold("What the schedule reported", h.job) +
        fold("The vendor budget as the morning read it", h.quota) +
        fold("What the collector was listening to", h.coverage) +
        fold("The window it actually ran", h.window) +
        fold("The scaling applied to premarket volume", h.capture) + "</section>";
      root.innerHTML = out;
    });
  }

  /* ---------- router ---------- */
  function parse() {
    var h = (location.hash || "").replace(/^#\/?/, "");
    var parts = h.split("/").filter(Boolean);
    if (!parts.length) {
      var newest = INDEX.sessions[0];
      return newest ? { screen: "morning", date: newest.date } : { screen: "sessions" };
    }
    if (parts[0] === "sessions") return { screen: "sessions" };
    if (parts[0] === "record") return { screen: "record" };
    if (parts[0] === "health") return { screen: "health", date: parts[1] || LAST };
    if (parts[0] === "name") return { screen: "name", sym: parts[1] };
    if (parts[0] === "session") {
      return { screen: parts[2] || "session", date: parts[1] };
    }
    if (parts[0] === "report") return { screen: "report", date: parts[1] || LAST };
    return { screen: "sessions" };
  }

  function setNav(route) {
    var map = { morning: "morning", midday: "midday", session: "sessions",
      sessions: "sessions", record: "record", health: "health", name: "",
      report: "" };
    Array.prototype.forEach.call(document.querySelectorAll("nav a"), function (a) {
      var key = a.dataset.nav;
      if (key === map[route.screen]) a.setAttribute("aria-current", "page");
      else a.removeAttribute("aria-current");
    });
    // Morning, Midday and Health all resolve against the chosen session, so
    // their links carry it rather than dropping the reader on the newest.
    var at = route.date || LAST;
    var link = { morning: "#/session/" + at + "/morning",
      midday: "#/session/" + at + "/midday", health: "#/health/" + at };
    Array.prototype.forEach.call(document.querySelectorAll("nav a"), function (a) {
      if (link[a.dataset.nav]) a.href = link[a.dataset.nav];
    });
    var scoped = (route.screen === "morning" || route.screen === "midday" ||
      route.screen === "session" || route.screen === "health" ||
      route.screen === "report");
    $("picker-wrap").style.display = scoped ? "" : "none";
    if (route.date) $("session-btn-label").textContent = route.date;
    // The stamp names the session a screen is about. On Sessions, Record,
    // Health and Name it is about all of them, and a dash beside the word
    // "session" reads as a session whose date went missing.
    $("stamp").style.display = scoped ? "" : "none";
  }

  var TIMER = null;

  // The same argument as TIMER, for the other thing a screen leaves behind.
  // Four screens draw from a promise: the session inflates, and only then is
  // there anything to render. A reader who moves on inside that window used
  // to get the OLD route's screen drawn over the new one, stamp and all,
  // under a hash that says something else, or a TypeError from writing into
  // a node the new screen had already replaced. Every render takes a number
  // and a resolution that is not the current one draws nothing.
  var EPOCH = 0;
  function stale(mine) { return mine !== EPOCH; }

  function render() {
    // A screen that started a clock owns it until the route changes. Left
    // running, a countdown keeps writing into a node the next screen has
    // already replaced.
    if (TIMER) { clearInterval(TIMER); TIMER = null; }
    EPOCH += 1;
    var mine = EPOCH;
    var route = parse();
    // A FRESH NODE, not a refilled one. Six screens attach a delegated
    // click handler to this element, and innerHTML replaces an element's
    // CHILDREN while its own listeners stay. Refilling it left one handler
    // per visit, each closed over the session it was created for, so the
    // Report screen's Morning and Midday toggle ran once for every report
    // screen the reader had ever opened. Replacing the node drops them
    // with it, and every screen goes on attaching whatever it needs.
    var root = document.createElement("div");
    root.id = "screen";
    var previous = $("screen");
    previous.parentNode.replaceChild(root, previous);
    setNav(route);
    window.__buildPrint = null;
    if (route.screen === "sessions") { screenSessions(root); return; }
    if (route.screen === "record") { screenRecord(root); return; }
    if (route.screen === "health") { screenHealth(route.date, root); return; }
    if (route.screen === "name") { screenName(route.sym, root); return; }

    root.innerHTML = '<div class="card pad empty" style="margin-top:24px">Reading ' +
      esc(route.date) + "…</div>";
    loadSession(route.date).then(function (p) {
      if (stale(mine)) return;
      if (!p) {
        root.innerHTML = '<div class="card pad empty" style="margin-top:24px">' +
          esc(route.date) + " is not inlined in this document.</div>";
        return;
      }
      $("stamp-date").textContent = p.session;
      $("stamp-run").textContent = p.run_at || NIL;
      if (route.screen === "midday") screenMidday(p, root);
      else if (route.screen === "report") screenReport(p, root);
      else if (route.screen === "session") screenSession(p, root);
      else screenMorning(p, root);
      window.scrollTo(0, 0);
    }).catch(function (err) {
      if (stale(mine)) return;
      root.innerHTML = '<div class="card pad empty" style="margin-top:24px">' +
        esc(err.message) + "</div>";
    });
  }

  /* ---------- chrome ---------- */
  // The session control is the calendar in a popover and not a date input,
  // because a date input can clamp a range but cannot haze the individual
  // days the desk holds no morning for, and those are most of them.
  var pbtn = $("session-btn"), ppop = $("session-pop");
  function closePop() {
    ppop.hidden = true;
    pbtn.setAttribute("aria-expanded", "false");
  }
  function openPop() {
    var sel = parse().date || LAST;
    ppop.dataset.sel = sel;
    ppop.innerHTML = calMonth(sel.slice(0, 7), sel, true) + calKey();
    ppop.hidden = false;
    pbtn.setAttribute("aria-expanded", "true");
  }
  pbtn.addEventListener("click", function (e) {
    e.stopPropagation();
    if (ppop.hidden) openPop(); else closePop();
  });
  wireCal(ppop, function (date) {
    closePop();
    var screen = parse().screen;
    location.hash = screen === "session" ? "#/session/" + date
      : screen === "health" ? "#/health/" + date
      : screen === "midday" ? "#/session/" + date + "/midday"
      : screen === "report" ? "#/session/" + date + "/report"
      : "#/session/" + date + "/morning";
  });
  document.addEventListener("click", function (e) {
    if (!ppop.hidden && !ppop.contains(e.target) && !pbtn.contains(e.target)) closePop();
  });
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && !ppop.hidden) { closePop(); pbtn.focus(); }
  });

  $("theme-btn").addEventListener("click", function () {
    var r = document.documentElement;
    var cur = r.getAttribute("data-theme");
    if (!cur) {
      cur = (window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches)
        ? "dark" : "light";
    }
    var next = cur === "dark" ? "light" : "dark";
    r.setAttribute("data-theme", next);
    try { localStorage.setItem("desk-theme", next); } catch (e) { /* private window */ }
  });
  try {
    var saved = localStorage.getItem("desk-theme");
    if (saved) document.documentElement.setAttribute("data-theme", saved);
  } catch (e) { /* private window */ }

  $("print-btn").addEventListener("click", function () {
    if (window.__buildPrint) window.__buildPrint();
    Array.prototype.forEach.call(document.querySelectorAll("details"), function (d) {
      d.open = true;
    });
    setTimeout(function () { window.print(); }, 60);
  });
  window.addEventListener("beforeprint", function () {
    if (window.__buildPrint) window.__buildPrint();
  });

  window.addEventListener("hashchange", render);
  render();
})();
"""
