"""The interactive eye-scan page: one self-contained HTML file (no libraries, no network). The eye builds up point by point in capture order (replay) or live from a
running scan (`serve`); a BER-depth selector (one decade a step) re-reads every point at that depth; hovering a point shows its raw counts; two captures can sit side by
side; and a 3-D bathtub (log10 BER over horizontal and vertical offset) rotates with the pointer. Every number on the page comes from flow/eyescan/api.py `page_data`;
the page only draws.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from flow.eyescan import api
from flow.eyescan import capture as C

TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>RX Eye Scan Viewer</title>
<meta name="description" content="On-chip eye scan of a 10G GTH receiver: statistical eye after the equaliser, BER depth, bathtub and 3-D surface, replayed from raw counts.">
<style>
:root{--paper:#fff;--ink:#111;--mute:#5a5a5a;--rule:#d4d4d4;--panel:#f6f6f6;--warn:#111}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--paper:#0e0e0e;--ink:#eee;--mute:#a0a0a0;--rule:#333;--panel:#171717;--warn:#eee}}
:root[data-theme="dark"]{--paper:#0e0e0e;--ink:#eee;--mute:#a0a0a0;--rule:#333;--panel:#171717;--warn:#eee}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--paper);color:var(--ink);font:16px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:1180px;margin:0 auto;padding:20px 16px 56px}
h1{font-size:1.5rem;margin:0 0 4px;font-weight:600}
h2{font-size:1.05rem;margin:28px 0 8px;font-weight:600}
p{margin:6px 0}.mute{color:var(--mute)}
.banner{border:1px solid var(--ink);padding:8px 12px;margin:12px 0;font-size:.92rem}
.bar{display:flex;flex-wrap:wrap;gap:10px 18px;align-items:center;padding:10px 0;border-top:1px solid var(--rule);border-bottom:1px solid var(--rule);margin:14px 0}
.bar label{display:flex;align-items:center;gap:8px;font-size:.92rem}
button,select{font:inherit;color:var(--ink);background:var(--paper);border:1px solid var(--ink);padding:5px 12px;border-radius:0;min-height:36px;cursor:pointer}
button[aria-pressed="true"]{background:var(--ink);color:var(--paper)}
input[type=range]{accent-color:var(--ink);min-width:150px}
.grid{display:grid;grid-template-columns:minmax(0,1fr) 300px;gap:18px}
@media (max-width:860px){.grid{grid-template-columns:minmax(0,1fr)}}
.two{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:14px}
@media (max-width:700px){.two{grid-template-columns:minmax(0,1fr)}}
canvas{width:100%;display:block;border:1px solid var(--rule);background:var(--paper);touch-action:none}
.panel{background:var(--panel);border:1px solid var(--rule);padding:10px 12px;font-size:.9rem}
.panel h3{font-size:.95rem;margin:0 0 6px}
dl{margin:0;display:grid;grid-template-columns:auto 1fr;gap:3px 10px}dt{color:var(--mute)}dd{margin:0;font-variant-numeric:tabular-nums}
table{border-collapse:collapse;width:100%;font-size:.9rem}th,td{border-bottom:1px solid var(--rule);padding:4px 8px;text-align:left;font-variant-numeric:tabular-nums}
.tabs{display:flex;gap:0;flex-wrap:wrap}.tabs button{border-right-width:0}.tabs button:last-child{border-right-width:1px}
.hide{display:none}
code{font-family:ui-monospace,Menlo,Consolas,monospace;font-size:.88em}
.legend span{display:inline-block;margin-right:14px;font-size:.85rem}
.sw{display:inline-block;width:14px;height:14px;vertical-align:-2px;border:1px solid var(--ink);margin-right:5px}
</style>
</head>
<body>
<main>
<h1>RX Eye Scan Viewer</h1>
<p class="mute" id="sub"></p>
<div class="banner" id="synthetic" hidden><strong>SYNTHETIC.</strong> This capture comes from an offline model (flow/eyescan/fake.py), not from a board. It is not a measurement.</div>
<div class="banner" id="what"><strong>What this eye is.</strong> The GTH receiver compares a second, offset sampler with its data sampler <em>after the equaliser</em> (LPM or DFE). The plot is a statistical eye of the
margin inside the receiver, built from the transceiver's own error counters. It is not the eye a scope would show at the pins. Each point examined a stated number of bits; a point with no errors only
says its BER is below 3/bits, so a depth deeper than a point's bits can vouch for is shown hatched, not open.</div>

<div class="bar" role="group" aria-label="Controls">
  <div class="tabs" role="tablist" aria-label="View">
    <button role="tab" id="t-eye" aria-pressed="true">Eye</button>
    <button role="tab" id="t-bath" aria-pressed="false">Bathtub</button>
    <button role="tab" id="t-3d" aria-pressed="false">3-D bathtub</button>
    <button role="tab" id="t-cmp" aria-pressed="false" hidden>Compare</button>
  </div>
  <label>BER depth <input type="range" id="depth" min="3" max="12" step="1" value="9" aria-label="BER depth decade"><output id="depth-out">1e-9</output></label>
  <label id="cap-sel-wrap">Capture <select id="cap-sel"></select></label>
  <span id="replay-wrap"><button id="play">Replay</button> <label>points <input type="range" id="prog" min="0" max="100" value="100" aria-label="Points shown"><output id="prog-out"></output></label></span>
  <span id="live-note" class="mute" hidden></span>
</div>

<section id="v-eye">
  <div class="grid">
    <div>
      <canvas id="c-eye" width="900" height="620" aria-label="Eye heat map"></canvas>
      <p class="legend"><span><i class="sw" style="background:#fff"></i>low BER (open where outlined)</span><span><i class="sw" style="background:#000"></i>BER near 0.3</span>
      <span><i class="sw" style="background:repeating-linear-gradient(45deg,#888 0 2px,transparent 2px 5px)"></i>too few bits for this depth</span><span>bold outline: the depth boundary</span></p>
    </div>
    <div>
      <div class="panel" aria-live="polite"><h3>At the chosen depth</h3><dl id="eye-dl"></dl></div>
      <div class="panel" style="margin-top:12px" aria-live="polite"><h3>Point under the pointer</h3><dl id="hover-dl"><dt>hover</dt><dd>over the eye</dd></dl></div>
      <div class="panel" style="margin-top:12px"><h3>Scan</h3><dl id="set-dl"></dl></div>
    </div>
  </div>
</section>
<section id="v-bath" class="hide"><canvas id="c-bath" width="900" height="460" aria-label="Horizontal bathtub"></canvas>
<p class="mute">Horizontal bathtub along the row nearest 0 mV. A circle is a BER from errors seen; a triangle is a point with no errors, drawn at its 3/bits bound (the BER is <em>below</em> it).</p></section>
<section id="v-3d" class="hide"><canvas id="c-3d" width="900" height="560" aria-label="3-D bathtub surface"></canvas>
<p class="mute">log10 BER over horizontal and vertical offset; the valley is the eye. Drag to rotate. Zero-error points sit at their 3/bits bound, so the floor of the valley is set by the scan depth, not by the link.
 A point that was not measured is a hole in the surface and a gap in the slices below: nothing is interpolated across it. <button id="reset3d">Reset view</button></p>
<div class="bar" role="group" aria-label="Slices"><label>Horizontal offset <input type="range" id="sl-h" min="0" max="0" step="1" aria-label="Horizontal offset of the vertical slice"><output id="sl-h-out"></output></label>
 <label>Vertical offset <input type="range" id="sl-v" min="0" max="0" step="1" aria-label="Vertical offset of the horizontal slice"><output id="sl-v-out"></output></label></div>
<div class="two"><div><h3>Vertical bathtub at the chosen horizontal offset</h3><canvas id="c-sl-v" width="600" height="320" aria-label="Vertical bathtub slice"></canvas></div>
<div><h3>Horizontal bathtub at the chosen vertical offset</h3><canvas id="c-sl-h" width="600" height="320" aria-label="Horizontal bathtub slice"></canvas></div></div>
<p class="mute">Circle: a BER from errors seen. Triangle: no errors, drawn at its 3/bits bound (the BER is below it). Cross on the floor: not measured. The slices are the lines drawn bold on the surface.</p></section>
<section id="v-cmp" class="hide"><div class="two"><div><h3 id="cmp-a-t"></h3><canvas id="c-cmp-a" width="600" height="440"></canvas></div><div><h3 id="cmp-b-t"></h3><canvas id="c-cmp-b" width="600" height="440"></canvas></div></div>
<canvas id="c-cmp-bath" width="900" height="360" style="margin-top:14px" aria-label="Bathtubs overlaid"></canvas>
<h3 style="margin-top:14px">Difference: B minus A</h3><canvas id="c-cmp-diff" width="900" height="420" aria-label="Difference of the two eyes"></canvas>
<p class="mute">Each cell is log10 BER of B minus log10 BER of A, over the points both captures measured (zero-error points at their 3/bits bound): lighter is a lower BER in B, darker is a higher BER in B, mid grey is no change (full scale is a factor of 10^4). Hatched: measured in only one capture. A bound against a bound is a comparison of scan depths, so read it with the table below.</p>
<table id="cmp-table" style="margin-top:14px"></table></section>

<h2>Conditions and checks</h2>
<div class="panel"><dl id="cond-dl"></dl></div>
<h2>How to read the numbers</h2>
<p>Bits per point = <code>samples x 2^(1+prescale) x 32</code>; BER = errors / bits. Width is the span of open points along the row nearest 0 mV; height is the span along the column nearest 0 UI, converted with
UG576's nominal mV per code. Both carry one grid step of uncertainty. The scan runs deeper only where a point shows no errors, so the number of bits differs from point to point.</p>
</main>
<script type="application/json" id="data">__DATA__</script>
<script>
"use strict";
(function(){
var DATA=JSON.parse(document.getElementById('data').textContent);
var LIVE=(window.EYE_LIVE_URL||new URLSearchParams(location.search).get('live'));
var THEME=new URLSearchParams(location.search).get('theme'); if(THEME==='dark'||THEME==='light')document.documentElement.setAttribute('data-theme',THEME);   // the navigator (brief 103) passes its own theme
function esc(v){return String(v).replace(/[&<>"']/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];});}
function isDark(){var t=document.documentElement.getAttribute('data-theme');return t==='dark'||(t!=='light'&&window.matchMedia&&window.matchMedia('(prefers-color-scheme: dark)').matches);}
var cur=0, depthN=null, view='eye', shown=null, playing=false, rot={yaw:-0.7,pitch:0.9}, hoverCell=null, sl={i:null,j:null};
function css(n){return getComputedStyle(document.documentElement).getPropertyValue(n).trim()||'#111';}
function $(id){return document.getElementById(id);}
function fmtB(x){if(x===null||x===undefined)return 'not measured';var e=Math.floor(Math.log10(x)); var m=x/Math.pow(10,e);return m.toFixed(1)+'e'+e;}
function fmtBits(b){return b>=1e9?(b/1e9).toFixed(2)+' Gbit':b>=1e6?(b/1e6).toFixed(1)+' Mbit':b>=1e3?(b/1e3).toFixed(1)+' kbit':b+' bit';}
function zOf(c){if(!c.m)return null; return c.err>0?Math.log10(c.ber):Math.log10(c.ub);}
function shade(z){if(z===null)return '#c8c8c8'; var f=(z+12)/(11.5); f=Math.min(1,Math.max(0,f)); var g=Math.round(255*(1-Math.pow(f,0.8)));
  if(isDark())g=255-g; return 'rgb('+g+','+g+','+g+')';}
function D(){return DATA[cur];}
function depthRec(d,n){for(var i=0;i<d.depths.length;i++){if(d.depths[i].n===n)return d.depths[i];}return d.depths[0];}
function setup(c,w,h){var r=window.devicePixelRatio||1;c.width=Math.round(w*r);c.height=Math.round(h*r);var x=c.getContext('2d');x.setTransform(r,0,0,r,0,0);return x;}
function fit(c,aspect){var w=c.clientWidth||600;return {w:w,h:Math.round(w*aspect)};}

function drawEye(c,d,opts){
  opts=opts||{}; var s=fit(c,opts.aspect||0.68); var x=setup(c,s.w,s.h); var W=s.w,H=s.h;
  var padL=56,padR=12,padT=12,padB=40; var pw=W-padL-padR, ph=H-padT-padB;
  var nH=d.h.length,nV=d.v.length,cw=pw/nH,ch=ph/nV;
  x.fillStyle=css('--paper');x.fillRect(0,0,W,H);
  var dep=depthRec(d,opts.n||depthN); var idx={}; d.cells.forEach(function(q){idx[q.h+','+q.v]=q;});
  var lim=opts.shown===undefined?Infinity:opts.shown;
  var geo=[];
  for(var r=0;r<nV;r++){for(var cI=0;cI<nH;cI++){
    var q=idx[d.h[cI]+','+d.v[r]]; var px=padL+cI*cw, py=padT+(nV-1-r)*ch;
    if(!q||q.i>=lim){x.fillStyle=css('--panel');x.fillRect(px,py,cw+0.5,ch+0.5);continue;}
    x.fillStyle=shade(zOf(q)); x.fillRect(px,py,cw+0.5,ch+0.5);
    var k=dep.rows[r][cI];
    if(k==='s'){x.save();x.beginPath();x.rect(px,py,cw,ch);x.clip();x.strokeStyle=css('--mute');x.lineWidth=1;x.beginPath();
      for(var t=-ch;t<cw+ch;t+=5){x.moveTo(px+t,py+ch);x.lineTo(px+t+ch,py);}x.stroke();x.restore();}
    geo.push([cI,r,k]);
  }}
  // boundary of the open region
  x.strokeStyle=css('--ink');x.lineWidth=2.2;x.beginPath();
  function isOpen(cI,r){if(cI<0||r<0||cI>=nH||r>=nV)return false;var q=idx[d.h[cI]+','+d.v[r]];if(!q||q.i>=lim)return false;return dep.rows[r][cI]==='o';}
  for(var r2=0;r2<nV;r2++){for(var c2=0;c2<nH;c2++){ if(!isOpen(c2,r2))continue; var px2=padL+c2*cw, py2=padT+(nV-1-r2)*ch;
    if(!isOpen(c2-1,r2)){x.moveTo(px2,py2);x.lineTo(px2,py2+ch);} if(!isOpen(c2+1,r2)){x.moveTo(px2+cw,py2);x.lineTo(px2+cw,py2+ch);}
    if(!isOpen(c2,r2+1)){x.moveTo(px2,py2);x.lineTo(px2+cw,py2);} if(!isOpen(c2,r2-1)){x.moveTo(px2,py2+ch);x.lineTo(px2+cw,py2+ch);} }}
  x.stroke();
  x.strokeStyle=css('--ink');x.lineWidth=1;x.strokeRect(padL,padT,pw,ph);
  x.fillStyle=css('--ink');x.font='12px system-ui,sans-serif';x.textAlign='center';
  [-0.5,-0.25,0,0.25,0.5].forEach(function(u){var h0=d.h[0],h1=d.h[nH-1];var hc=u/d.settings.ui_per_count; if(hc<h0||hc>h1)return; var xx=padL+(hc-h0)/(h1-h0)*(pw-cw)+cw/2; x.fillText((u>0?'+':'')+u.toFixed(2),xx,padT+ph+16);});
  x.fillText('horizontal offset (UI)',padL+pw/2,padT+ph+34);
  x.textAlign='right';[0,0.25,0.5,0.75,1].forEach(function(f){var vv=d.mv[0]+f*(d.mv[nV-1]-d.mv[0]);var yy=padT+ph-(f*(ph-ch)+ch/2);x.fillText((vv>0?'+':'')+vv.toFixed(0),padL-6,yy+4);});
  x.save();x.translate(14,padT+ph/2);x.rotate(-Math.PI/2);x.textAlign='center';x.fillText('vertical offset (mV, nominal)',0,0);x.restore();
  if(d.synthetic){x.save();x.translate(W/2,H/2);x.rotate(-0.31);x.font='bold '+Math.round(W/9)+'px system-ui';x.textAlign='center';x.globalAlpha=0.13;x.fillStyle=css('--ink');x.fillText('SYNTHETIC',0,0);x.restore();}
  return {padL:padL,padT:padT,cw:cw,ch:ch,nH:nH,nV:nV,idx:idx,lim:lim};
}

function drawBath(c,list,depth){
  var s=fit(c,(c.clientWidth||600)<600?0.85:0.5); var x=setup(c,s.w,s.h); var W=s.w,H=s.h; var padL=64,padR=14,padT=14,padB=44,pw=W-padL-padR,ph=H-padT-padB;
  x.fillStyle=css('--paper');x.fillRect(0,0,W,H);
  var allz=[];list.forEach(function(d){d.bath_h.forEach(function(r){if(r.ber!==null)allz.push(r.err>0?Math.log10(r.ber):Math.log10(r.ber_ub));});});
  var ymin=Math.min(-12,Math.floor(Math.min.apply(null,allz.length?allz:[-12]))),ymax=0;
  var x0=-0.5,x1=0.5;list.forEach(function(d){d.bath_h.forEach(function(r){x0=Math.min(x0,r.ui);x1=Math.max(x1,r.ui);});});
  function X(u){return padL+(u-x0)/(x1-x0)*pw;} function Y(l){return padT+(ymax-l)/(ymax-ymin)*ph;}
  x.font='12px system-ui,sans-serif';x.textAlign='right';x.fillStyle=css('--ink');x.strokeStyle=css('--rule');x.lineWidth=1;
  for(var l=ymin;l<=0;l++){x.beginPath();x.moveTo(padL,Y(l));x.lineTo(padL+pw,Y(l));x.stroke();x.fillText('1e'+l,padL-6,Y(l)+4);}
  list.forEach(function(d,k){x.strokeStyle=css('--ink');x.fillStyle=css('--ink');x.lineWidth=1.6;x.setLineDash(k?[6,4]:[]);x.beginPath();var first=true;
    d.bath_h.forEach(function(r){if(r.ber===null)return;var z=r.err>0?Math.log10(r.ber):Math.log10(r.ber_ub);if(first){x.moveTo(X(r.ui),Y(z));first=false;}else x.lineTo(X(r.ui),Y(z));});x.stroke();x.setLineDash([]);
    d.bath_h.forEach(function(r){if(r.ber===null)return;var xx=X(r.ui);if(r.err>0){var yy=Y(Math.log10(r.ber));x.beginPath();x.arc(xx,yy,2.6,0,6.3);x.fill();}
      else{var y2=Y(Math.log10(r.ber_ub));x.beginPath();x.moveTo(xx,y2);x.lineTo(xx-3.5,y2-7);x.lineTo(xx+3.5,y2-7);x.closePath();if(k){x.stroke();}else x.fill();}});});
  x.setLineDash([5,4]);x.strokeStyle=css('--ink');x.beginPath();x.moveTo(padL,Y(-depth));x.lineTo(padL+pw,Y(-depth));x.stroke();x.setLineDash([]);
  x.textAlign='right';x.fillText('depth 1e-'+depth,padL+pw-4,Y(-depth)-5);
  x.strokeRect(padL,padT,pw,ph);x.textAlign='center';[-0.5,-0.25,0,0.25,0.5].forEach(function(u){if(u>=x0&&u<=x1)x.fillText((u>0?'+':'')+u.toFixed(2),X(u),padT+ph+16);});x.fillText('horizontal offset (UI)',padL+pw/2,padT+ph+36);
  if(list.length>1){x.textAlign='left';x.fillText('solid: '+(list[0].label||'A')+'   dashed: '+(list[1].label||'B'),padL+8,padT+16);}
  if(list[0].synthetic){x.save();x.translate(W/2,H/2);x.rotate(-0.2);x.font='bold '+Math.round(W/9)+'px system-ui';x.textAlign='center';x.globalAlpha=0.13;x.fillText('SYNTHETIC',0,0);x.restore();}
}

function draw3d(c,d){
  var s=fit(c,0.62); var x=setup(c,s.w,s.h); var W=s.w,H=s.h; x.fillStyle=css('--paper');x.fillRect(0,0,W,H);
  var S=d.surface,nH=S.h.length,nV=S.v.length; var cy=Math.cos(rot.yaw),sy=Math.sin(rot.yaw),cp=Math.cos(rot.pitch),sp=Math.sin(rot.pitch);
  function P(i,j){var z=S.log10_ber[j][i]; if(z===null)z=-0.5; z=Math.max(-12,Math.min(-0.5,z));
    var X0=(i/(nH-1)-0.5)*2, Y0=(j/(nV-1)-0.5)*2, Z0=((z+12)/11.5-0.5)*1.3;
    var a=X0*cy-Y0*sy, b=X0*sy+Y0*cy; var yy=b*cp-Z0*sp, zz=b*sp+Z0*cp; var sc=Math.min(W,H*1.3)*0.36; return [W/2+a*sc, H*0.52+yy*sc*0.55-zz*sc*0.55, zz];}
  var quads=[];for(var j=0;j<nV-1;j++)for(var i=0;i<nH-1;i++){var p=[P(i,j),P(i+1,j),P(i+1,j+1),P(i,j+1)];var zs=[S.log10_ber[j][i],S.log10_ber[j][i+1],S.log10_ber[j+1][i+1],S.log10_ber[j+1][i]];
    if(zs.some(function(v){return v===null;}))continue;var m=(zs[0]+zs[1]+zs[2]+zs[3])/4;quads.push({p:p,m:m,d:(p[0][2]+p[1][2]+p[2][2]+p[3][2])/4});}
  quads.sort(function(a,b){return a.d-b.d;});
  x.lineWidth=0.5;quads.forEach(function(q){x.beginPath();x.moveTo(q.p[0][0],q.p[0][1]);for(var k=1;k<4;k++)x.lineTo(q.p[k][0],q.p[k][1]);x.closePath();x.fillStyle=shade(q.m);x.fill();x.strokeStyle=css('--mute');x.stroke();});
  if(sl.i!==null&&sl.j!==null){x.strokeStyle=css('--ink');x.lineWidth=3;x.beginPath();var st1=false;for(var jj=0;jj<nV;jj++){if(S.log10_ber[jj][sl.i]===null){st1=false;continue;}var pp=P(sl.i,jj);if(!st1){x.moveTo(pp[0],pp[1]);st1=true;}else x.lineTo(pp[0],pp[1]);}x.stroke();
    x.beginPath();st1=false;for(var ii=0;ii<nH;ii++){if(S.log10_ber[sl.j][ii]===null){st1=false;continue;}var pq=P(ii,sl.j);if(!st1){x.moveTo(pq[0],pq[1]);st1=true;}else x.lineTo(pq[0],pq[1]);}x.stroke();}
  x.fillStyle=css('--ink');x.font='12px system-ui,sans-serif';x.textAlign='left';x.fillText('height = log10 BER ('+(d.synthetic?'SYNTHETIC; ':'')+'high at the edges, low in the eye)',12,18);
  x.fillText('x: horizontal offset -0.5 .. +0.5 UI   y: vertical offset '+d.mv[0].toFixed(0)+' .. +'+d.mv[nV-1].toFixed(0)+' mV',12,36);
}

function eyeDl(d){var dep=depthRec(d,depthN),e=dep.eye;var rows=[['depth','BER '+fmtB(dep.depth)],['width',e.width_ui===null?'no open row':e.width_ui.toFixed(3)+' UI (grid +/-'+((e.width_ui_hi-e.width_ui_lo)/2).toFixed(3)+')'],
  ['height',e.height_mv===null?'no open column':e.height_mv.toFixed(0)+' mV (grid +/-'+((e.height_mv_hi-e.height_mv_lo)/2).toFixed(0)+')'],['open points',e.counts.open],['closed points',e.counts.closed],['too shallow',e.counts.shallow]];
  if(e.shallow_note)rows.push(['note',e.shallow_note]);
  $('eye-dl').innerHTML=rows.map(function(r){return '<dt>'+esc(r[0])+'</dt><dd>'+esc(r[1])+'</dd>';}).join('');}
function setDl(d){var s=d.settings,t=s.tx||{};var rows=[['line rate',s.line_rate_gbps+' Gb/s'],['equaliser',s.equaliser+' (eye is after it)'],['target depth','BER '+fmtB(s.target_ber)],['grid',d.h.length+' x '+d.v.length+' points, step '+s.hstep+' / '+s.vstep],
  ['bits per sample','x '+s.data_width],['TX drive','diff '+(t.diff===undefined?'-':t.diff)+' pre '+(t.pre===undefined?'-':t.pre)+' post '+(t.post===undefined?'-':t.post)],['created',d.created||'-']];
  if(d.ppm!==null&&d.ppm!==undefined)rows.push(['ppm offset',d.ppm]);
  $('set-dl').innerHTML=rows.map(function(r){return '<dt>'+esc(r[0])+'</dt><dd>'+esc(r[1])+'</dd>';}).join('');}
function condDl(d){var c=d.conditions||{},a=c.start||{},b=c.end||{};function f(o){if(!o||!Object.keys(o).length)return 'not recorded';var k=['temp_c','vccint_v','vccaux_v','vccbram_v'];return k.filter(function(n){return o[n]!==undefined&&o[n]!==null;}).map(function(n){return n+' '+o[n];}).join(', ')+(o.inside_roc===undefined?'':(o.inside_roc?' (inside ROC)':' (OUTSIDE ROC)'));}
  var rows=[['start',f(a)],['end',f(b)],['DRP words restored',d.restore_ok===null||d.restore_ok===undefined?'not recorded':(d.restore_ok?'yes, read back':'NO')],['link locked throughout',d.link_ok_throughout===null||d.link_ok_throughout===undefined?'not recorded':(d.link_ok_throughout?'yes':'NO')],
  ['run time',(d.run&&d.run.seconds!==undefined)?d.run.seconds+' s, '+d.run.points_done+' points, '+d.run.register_ops+' register operations':'-']];
  $('cond-dl').innerHTML=rows.map(function(r){return '<dt>'+esc(r[0])+'</dt><dd>'+esc(r[1])+'</dd>';}).join('');}


function drawSlice(c,xs,zs,bs,xlabel,fmt){
  var s=fit(c,0.53); var x=setup(c,s.w,s.h); var W=s.w,H=s.h,padL=52,padR=12,padT=10,padB=40,pw=W-padL-padR,ph=H-padT-padB;
  x.fillStyle=css('--paper');x.fillRect(0,0,W,H);
  var x0=xs[0],x1=xs[xs.length-1]; function X(v){return padL+(v-x0)/((x1-x0)||1)*pw;} function Y(l){return padT+(0-l)/12*ph;}
  x.font='11px system-ui,sans-serif';x.textAlign='right';x.fillStyle=css('--ink');x.strokeStyle=css('--rule');x.lineWidth=1;
  for(var l=0;l>=-12;l-=2){x.beginPath();x.moveTo(padL,Y(l));x.lineTo(padL+pw,Y(l));x.stroke();x.fillText('1e'+l,padL-5,Y(l)+4);}
  x.strokeStyle=css('--ink');x.lineWidth=1.6;x.beginPath();var pen=false;
  for(var k=0;k<xs.length;k++){if(zs[k]===null){pen=false;continue;}var yy=Y(Math.max(-12,zs[k]));if(!pen){x.moveTo(X(xs[k]),yy);pen=true;}else x.lineTo(X(xs[k]),yy);}x.stroke();
  for(var m=0;m<xs.length;m++){var xx=X(xs[m]);
    if(zs[m]===null){x.beginPath();x.moveTo(xx-3,padT+ph-3);x.lineTo(xx+3,padT+ph+3);x.moveTo(xx+3,padT+ph-3);x.lineTo(xx-3,padT+ph+3);x.stroke();continue;}
    var y2=Y(Math.max(-12,zs[m]));x.fillStyle=css('--ink');
    if(bs[m]){x.beginPath();x.moveTo(xx,y2);x.lineTo(xx-3.5,y2-7);x.lineTo(xx+3.5,y2-7);x.closePath();x.stroke();}else{x.beginPath();x.arc(xx,y2,2.6,0,6.3);x.fill();}}
  x.strokeStyle=css('--ink');x.strokeRect(padL,padT,pw,ph);x.fillStyle=css('--ink');x.textAlign='center';
  [0,0.25,0.5,0.75,1].forEach(function(f){var v=x0+f*(x1-x0);x.fillText(fmt(v),X(v),padT+ph+15);});x.fillText(xlabel,padL+pw/2,padT+ph+32);
}
function sliceSetup(d){var S=d.surface,nH=S.h.length,nV=S.v.length;
  if(sl.i===null||sl.i>=nH)sl.i=Math.max(0,S.h.indexOf(0)>=0?S.h.indexOf(0):Math.floor(nH/2));
  if(sl.j===null||sl.j>=nV)sl.j=Math.max(0,S.v.indexOf(0)>=0?S.v.indexOf(0):Math.floor(nV/2));
  $('sl-h').max=nH-1;$('sl-h').value=sl.i;$('sl-v').max=nV-1;$('sl-v').value=sl.j;
  $('sl-h-out').textContent=S.ui[sl.i].toFixed(3)+' UI';$('sl-v-out').textContent=(S.mv[sl.j]>0?'+':'')+S.mv[sl.j].toFixed(0)+' mV';}
function drawSlices(d){var S=d.surface,nH=S.h.length,nV=S.v.length;sliceSetup(d);
  var col=[],colb=[];for(var j=0;j<nV;j++){col.push(S.log10_ber[j][sl.i]);colb.push(S.zero_error_bound[j][sl.i]);}
  drawSlice($('c-sl-v'),S.mv,col,colb,'vertical offset (mV, nominal)',function(v){return (v>0?'+':'')+v.toFixed(0);});
  drawSlice($('c-sl-h'),S.ui,S.log10_ber[sl.j],S.zero_error_bound[sl.j],'horizontal offset (UI)',function(v){return (v>0?'+':'')+v.toFixed(2);});}
function drawDiff(c,a,b){
  var s=fit(c,0.47); var x=setup(c,s.w,s.h); var W=s.w,H=s.h,padL=56,padR=12,padT=10,padB=38,pw=W-padL-padR,ph=H-padT-padB;
  x.fillStyle=css('--paper');x.fillRect(0,0,W,H);
  var hs={},vs={};[a,b].forEach(function(d){d.surface.h.forEach(function(v){hs[v]=1;});d.surface.v.forEach(function(v){vs[v]=1;});});
  var H1=Object.keys(hs).map(Number).sort(function(p,q){return p-q;}),V1=Object.keys(vs).map(Number).sort(function(p,q){return p-q;});
  function idx(d){var m={};d.surface.h.forEach(function(h0,i){d.surface.v.forEach(function(v0,j){m[h0+','+v0]=d.surface.log10_ber[j][i];});});return m;}
  var ia=idx(a),ib=idx(b),cw=pw/H1.length,ch=ph/V1.length;
  for(var r=0;r<V1.length;r++)for(var k=0;k<H1.length;k++){var za=ia[H1[k]+','+V1[r]],zb=ib[H1[k]+','+V1[r]];if(za===undefined)za=null;if(zb===undefined)zb=null;
    var px=padL+k*cw,py=padT+(V1.length-1-r)*ch;
    if(za===null&&zb===null){x.fillStyle=css('--panel');x.fillRect(px,py,cw+0.5,ch+0.5);continue;}
    if(za===null||zb===null){x.fillStyle=css('--panel');x.fillRect(px,py,cw+0.5,ch+0.5);x.save();x.beginPath();x.rect(px,py,cw,ch);x.clip();x.strokeStyle=css('--mute');x.beginPath();for(var t=-ch;t<cw+ch;t+=5){x.moveTo(px+t,py+ch);x.lineTo(px+t+ch,py);}x.stroke();x.restore();continue;}
    var f=Math.max(-1,Math.min(1,(zb-za)/4)),g=Math.round(128-127*f);x.fillStyle='rgb('+g+','+g+','+g+')';x.fillRect(px,py,cw+0.5,ch+0.5);}
  x.strokeStyle=css('--ink');x.lineWidth=1;x.strokeRect(padL,padT,pw,ph);x.fillStyle=css('--ink');x.font='12px system-ui,sans-serif';x.textAlign='center';
  var ui=a.settings.ui_per_count;[-0.5,-0.25,0,0.25,0.5].forEach(function(u){var hc=u/ui;if(hc<H1[0]||hc>H1[H1.length-1])return;x.fillText((u>0?'+':'')+u.toFixed(2),padL+(hc-H1[0])/((H1[H1.length-1]-H1[0])||1)*(pw-cw)+cw/2,padT+ph+16);});
  x.fillText('horizontal offset (UI)',padL+pw/2,padT+ph+32);x.textAlign='right';var mvc=a.settings.mv_per_code;
  [0,0.5,1].forEach(function(f2){var vv=V1[0]+f2*(V1[V1.length-1]-V1[0]);x.fillText((vv>0?'+':'')+(vv*mvc).toFixed(0),padL-6,padT+ph-(f2*(ph-ch)+ch/2)+4);});
  x.save();x.translate(14,padT+ph/2);x.rotate(-Math.PI/2);x.textAlign='center';x.fillText('vertical offset (mV, nominal)',0,0);x.restore();
  if(a.synthetic||b.synthetic){x.save();x.translate(W/2,H/2);x.rotate(-0.25);x.font='bold '+Math.round(W/9)+'px system-ui';x.textAlign='center';x.globalAlpha=0.13;x.fillStyle=css('--ink');x.fillText('SYNTHETIC',0,0);x.restore();}
}

function hoverText(d,q){if(!q)return [['point','none']];var s=d.settings;var dep=depthRec(d,depthN);var cI=d.h.indexOf(q.h),r=d.v.indexOf(q.v);var k=dep.rows[r][cI];
  var cls={o:'open',c:'closed',s:'too few bits for this depth',u:'not measured'}[k];
  return [['offset',q.h+' counts = '+(q.h*s.ui_per_count).toFixed(3)+' UI'],['vertical',q.v+' codes = '+(q.v*s.mv_per_code).toFixed(0)+' mV'],['errors',q.err],['bits',fmtBits(q.bits)],
    ['BER',q.m?(q.err>0?fmtB(q.ber):'below '+fmtB(q.ub)+' (95 %)'):'not measured'],['at depth '+fmtB(dep.depth),cls]];}

function render(){
  var d=D(); if(depthN===null)depthN=d.default_n; $('depth').value=depthN; $('depth-out').textContent='1e-'+depthN;
  $('synthetic').hidden=!DATA.some(function(x){return x.synthetic;});
  $('sub').textContent=(d.label?d.label+' - ':'')+d.settings.line_rate_gbps+' Gb/s, '+d.settings.equaliser+', '+d.cells.length+' points'+(LIVE?' (live)':'');
  var total=d.cells.length?Math.max.apply(null,d.cells.map(function(q){return q.i;}))+1:0; if(shown===null||shown>total)shown=total; $('prog').max=total; $('prog').value=shown; $('prog-out').textContent=shown+' / '+total;
  eyeDl(d);setDl(d);condDl(d);
  if(view==='eye'){var g=drawEye($('c-eye'),d,{shown:shown});window._g=g;}
  if(view==='bath')drawBath($('c-bath'),[d],depthN);
  if(view==='3d'){sliceSetup(d);draw3d($('c-3d'),d);drawSlices(d);}
  if(view==='cmp'&&DATA.length>1){var a=DATA[0],b=DATA[1];$('cmp-a-t').textContent=(a.label||'A');$('cmp-b-t').textContent=(b.label||'B');drawEye($('c-cmp-a'),a,{aspect:0.73});drawEye($('c-cmp-b'),b,{aspect:0.73});drawBath($('c-cmp-bath'),[a,b],depthN);drawDiff($('c-cmp-diff'),a,b);
    var ea=depthRec(a,depthN).eye,eb=depthRec(b,depthN).eye;function n(v,u,p){return v===null?'-':v.toFixed(p)+' '+u;}
    $('cmp-table').innerHTML='<tr><th>at BER 1e-'+depthN+'</th><th>'+(a.label||'A')+'</th><th>'+(b.label||'B')+'</th><th>B - A</th></tr>'+
     '<tr><td>width</td><td>'+n(ea.width_ui,'UI',3)+'</td><td>'+n(eb.width_ui,'UI',3)+'</td><td>'+((ea.width_ui!==null&&eb.width_ui!==null)?(eb.width_ui-ea.width_ui).toFixed(3)+' UI':'-')+'</td></tr>'+
     '<tr><td>height</td><td>'+n(ea.height_mv,'mV',0)+'</td><td>'+n(eb.height_mv,'mV',0)+'</td><td>'+((ea.height_mv!==null&&eb.height_mv!==null)?(eb.height_mv-ea.height_mv).toFixed(0)+' mV':'-')+'</td></tr>'+
     '<tr><td>open points</td><td>'+ea.counts.open+'</td><td>'+eb.counts.open+'</td><td>'+(eb.counts.open-ea.counts.open)+'</td></tr>'+
     '<tr><td>equaliser</td><td>'+a.settings.equaliser+'</td><td>'+b.settings.equaliser+'</td><td></td></tr>'; }
}
function showView(v){view=v;['eye','bath','3d','cmp'].forEach(function(k){$('v-'+k).classList.toggle('hide',k!==v);$('t-'+(k==='3d'?'3d':k)).setAttribute('aria-pressed',k===v?'true':'false');});render();}
['eye','bath','3d','cmp'].forEach(function(k){$('t-'+k).addEventListener('click',function(){showView(k);});});
$('depth').addEventListener('input',function(){depthN=parseInt(this.value,10);render();});
$('prog').addEventListener('input',function(){shown=parseInt(this.value,10);playing=false;$('play').textContent='Replay';render();});
$('play').addEventListener('click',function(){if(playing){playing=false;this.textContent='Replay';return;}var d=D();var total=parseInt($('prog').max,10);if(shown>=total)shown=0;playing=true;this.textContent='Pause';
  var step=Math.max(1,Math.round(total/160));(function tick(){if(!playing)return;shown=Math.min(total,shown+step);render();if(shown>=total){playing=false;$('play').textContent='Replay';return;}requestAnimationFrame(tick);})();});
$('cap-sel').addEventListener('change',function(){cur=parseInt(this.value,10);shown=null;render();});
$('reset3d').addEventListener('click',function(){rot={yaw:-0.7,pitch:0.9};render();});
$('sl-h').addEventListener('input',function(){sl.i=parseInt(this.value,10);render();});
$('sl-v').addEventListener('input',function(){sl.j=parseInt(this.value,10);render();});
var drag=null,c3=$('c-3d');c3.addEventListener('pointerdown',function(e){drag=[e.clientX,e.clientY,rot.yaw,rot.pitch];c3.setPointerCapture(e.pointerId);});
c3.addEventListener('pointermove',function(e){if(!drag)return;rot.yaw=drag[2]+(e.clientX-drag[0])*0.01;rot.pitch=Math.max(0.1,Math.min(1.5,drag[3]+(e.clientY-drag[1])*0.01));draw3d(c3,D());});
c3.addEventListener('pointerup',function(){drag=null;});
var ce=$('c-eye');ce.addEventListener('pointermove',function(e){var g=window._g;if(!g)return;var rc=ce.getBoundingClientRect();var mx=e.clientX-rc.left,my=e.clientY-rc.top;var cI=Math.floor((mx-g.padL)/g.cw),r=g.nV-1-Math.floor((my-g.padT)/g.ch);var d=D();
  var q=(cI>=0&&cI<g.nH&&r>=0&&r<g.nV)?g.idx[d.h[cI]+','+d.v[r]]:null;if(q&&q.i>=g.lim)q=null;$('hover-dl').innerHTML=hoverText(d,q).map(function(r2){return '<dt>'+esc(r2[0])+'</dt><dd>'+esc(r2[1])+'</dd>';}).join('');});
DATA.forEach(function(d,i){var o=document.createElement('option');o.value=i;o.textContent=(d.label||('capture '+(i+1)));$('cap-sel').appendChild(o);});
if(DATA.length>1){$('t-cmp').hidden=false;} else {$('cap-sel-wrap').hidden=true;}
if(LIVE){$('replay-wrap').hidden=true;$('live-note').hidden=false;var poll=function(){fetch(LIVE).then(function(r){return r.json();}).then(function(j){DATA=[j];shown=null;$('live-note').textContent='live: '+j.cells.length+' points'+(j.run&&j.run.error?' ('+j.run.error+')':'');render();}).catch(function(e){$('live-note').textContent='live feed: '+e;});};poll();setInterval(poll,2000);}
window.addEventListener('resize',render);render();
function postH(){if(window.parent!==window)parent.postMessage({eyeHeight:Math.ceil(document.body.getBoundingClientRect().height)},'*');}
if(window.ResizeObserver)new ResizeObserver(postH).observe(document.body);postH();
})();
</script>
</body>
</html>
"""


def build_page(caps: list[dict[str, Any]], labels: list[str] | None = None) -> str:
    """The interactive page for one or two captures (two enables the Compare tab)."""
    if not 1 <= len(caps) <= 2:
        raise ValueError("one or two captures")
    data = []
    for i, c in enumerate(caps):
        d = api.page_data(c)
        if labels and i < len(labels):
            d["label"] = labels[i]
        elif not d.get("label"):
            d["label"] = f"{c['settings']['equaliser']} {c.get('created', '')}".strip()
        data.append(d)
    return TEMPLATE.replace("__DATA__", json.dumps(data, separators=(",", ":")).replace("</", "<\\/"))


def write_page(paths: list[Path | str], out: Path | str, labels: list[str] | None = None) -> Path:
    caps = [C.load(p) for p in paths]
    p = Path(out)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(build_page(caps, labels))
    return p
