"""Fin, the friendly guide: an original little fish with a sprout on its head (growth).
Drawn as inline SVG. It blinks, bobs, wags its tail, and TALKS: the mouth moves while a speech bubble
types the line out, and (optionally) the browser's own text-to-speech reads it aloud.
Frontend only. No AI, no network, no cost."""
import base64
import html
import json

import streamlit as st
import streamlit.components.v1 as components


def _svg(static=False) -> str:
    mouth_open = "" if static else ('<g class="open"><ellipse cx="100" cy="130" rx="10" ry="8" fill="#7A2E3B"/>'
                                    '<ellipse cx="100" cy="135" rx="6" ry="3.5" fill="#FF8FA3"/></g>')
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 210 190" role="img" aria-label="Fin the fish">
<g class="bob">
  <path d="M100 52 L100 28" stroke="#2E9E5B" stroke-width="5" fill="none" stroke-linecap="round"/>
  <path d="M100 30 C88 12 70 16 70 16 C72 32 88 36 100 30Z" fill="#4ADE80"/>
  <path d="M100 28 C112 8 132 12 132 12 C130 30 112 34 100 28Z" fill="#22C55E"/>
  <g class="tail"><path d="M160 112 L196 86 Q204 112 196 140 Z" fill="#38B2CC"/></g>
  <ellipse cx="42" cy="126" rx="15" ry="9" fill="#38B2CC" transform="rotate(-25 42 126)"/>
  <ellipse cx="100" cy="112" rx="68" ry="62" fill="#5CCBE0"/>
  <ellipse cx="100" cy="134" rx="44" ry="36" fill="#C9F2F9"/>
  <g class="eye"><ellipse cx="74" cy="100" rx="14" ry="16" fill="#fff"/><circle cx="76" cy="102" r="8" fill="#1B2433"/><circle cx="79" cy="98" r="3" fill="#fff"/></g>
  <g class="eye"><ellipse cx="126" cy="100" rx="14" ry="16" fill="#fff"/><circle cx="128" cy="102" r="8" fill="#1B2433"/><circle cx="131" cy="98" r="3" fill="#fff"/></g>
  <ellipse cx="56" cy="124" rx="9" ry="6" fill="#FF9BB0" opacity=".75"/>
  <ellipse cx="144" cy="124" rx="9" ry="6" fill="#FF9BB0" opacity=".75"/>
  <path class="smile" d="M88 124 Q100 138 112 124" stroke="#1B2433" stroke-width="3.5" fill="none" stroke-linecap="round"/>
  {mouth_open}
</g></svg>"""


def avatar_html(size=44) -> str:
    """A small still picture of Fin for cards (an <img> with a data URI)."""
    b64 = base64.b64encode(_svg(static=True).encode()).decode()
    return f'<img alt="Fin" width="{size}" height="{size}" style="vertical-align:middle" src="data:image/svg+xml;base64,{b64}">'


_PAGE = """<!doctype html><meta charset="utf-8"><style>
html,body{margin:0;background:transparent;font-family:-apple-system,"Segoe UI",system-ui,sans-serif;color:#1B2433}
.wrap{display:flex;flex-direction:column;align-items:center}
.fin{width:150px;height:135px}.fin svg{width:100%;height:100%;overflow:visible}
.bob{animation:bob 3s ease-in-out infinite;transform-origin:100px 112px}
.tail{animation:wag 1.6s ease-in-out infinite;transform-origin:160px 112px}
.eye{animation:blink 4.6s infinite;transform-box:fill-box;transform-origin:center}
.open{display:none;transform-box:fill-box;transform-origin:center}
.talking .open{display:block;animation:talk .24s ease-in-out infinite alternate}
.talking .smile{display:none}
@keyframes bob{50%{transform:translateY(-5px)}}
@keyframes wag{50%{transform:rotate(9deg)}}
@keyframes blink{0%,94%,100%{transform:scaleY(1)}97%{transform:scaleY(.1)}}
@keyframes talk{from{transform:scaleY(.35) scaleX(.9)}to{transform:scaleY(1.15) scaleX(1.05)}}
.bubble{position:relative;width:calc(100% - 28px);box-sizing:border-box;background:#fff;border:1px solid #D5DEEC;border-radius:18px;
 padding:14px 16px;margin-top:12px;font-size:16px;line-height:1.45;box-shadow:0 1px 4px rgba(16,24,40,.08)}
.bubble:before{content:"";position:absolute;top:-9px;left:calc(50% - 9px);width:16px;height:16px;background:#fff;
 border-left:1px solid #D5DEEC;border-top:1px solid #D5DEEC;transform:rotate(45deg)}
.ghost{visibility:hidden}.type{position:absolute;left:16px;right:16px;top:14px}
button{margin-top:8px;border:1px solid #D5DEEC;background:#fff;border-radius:999px;padding:6px 14px;font-size:13px;color:#23314A;cursor:pointer}
@media (prefers-reduced-motion:reduce){.bob,.tail,.eye,.talking .open{animation:none}}
</style>
<div class="wrap"><div class="fin" id="fin">__SVG__</div>
<div class="bubble"><div class="ghost">__TEXT__</div><div class="type" id="t" aria-live="polite"></div></div>
<button id="hear" type="button">🔊 Hear Fin</button></div>
<script>
const TEXT=__JSON__, VOICE=__VOICE__, fin=document.getElementById("fin"), out=document.getElementById("t");
let timer=null, speaking=false, typing=false;
const mouth=()=>fin.classList.toggle("talking", typing||speaking);
function speak(){
  try{
    if(!("speechSynthesis" in window)) return;
    speechSynthesis.cancel();
    const u=new SpeechSynthesisUtterance(TEXT); u.rate=1.02; u.pitch=1.35;
    const v=speechSynthesis.getVoices().find(x=>/^en/i.test(x.lang)&&/female|samantha|zira|aria|google us english/i.test(x.name));
    if(v) u.voice=v;
    u.onstart=()=>{speaking=true;mouth()}; u.onend=u.onerror=()=>{speaking=false;mouth()};
    speechSynthesis.speak(u);
  }catch(e){}
}
function type(){
  clearInterval(timer); out.textContent=""; let i=0; typing=true; mouth();
  const step=VOICE?55:28;
  timer=setInterval(()=>{ out.textContent=TEXT.slice(0,++i); if(i>=TEXT.length){clearInterval(timer);typing=false;mouth()} },step);
}
document.getElementById("hear").onclick=()=>{type();speak()};
type(); if(VOICE) speak();
</script>"""


def stage(text: str, voice: bool = False):
    """Fin says `text`: moving mouth + typed speech bubble (+ spoken aloud if `voice`)."""
    lines = max(1, -(-len(text) // 34))
    page = (_PAGE.replace("__SVG__", _svg()).replace("__TEXT__", html.escape(text))
            .replace("__JSON__", json.dumps(text).replace("</", "<\\/")).replace("__VOICE__", "true" if voice else "false"))
    components.html(page, height=150 + 12 + lines * 23 + 36 + 46)
