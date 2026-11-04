// Opening chat: Fin, a friendly guide, asks four quick questions so the app can fit the person.
// Ported from the Streamlit app (mystocks_frontend-/app/chat.py and mascot.py), words unchanged.
//
// SCRIPTED, not AI: no API key, no cost, and it can never say anything off-script (so it can't
// drift into financial advice). Answers are tappable buttons, which also suits a phone.
// Answers are kept only in this visitor's browser (localStorage). Nothing is sent to the server.
import { useEffect, useRef, useState } from 'react'

export const GUIDE = 'Fin' // the character's name: change it here

type Question = {
  key: string
  ask: string
  options: [string, string][]
  reply: Record<string, string>
}

export const QUESTIONS: Question[] = [
  {
    key: 'experience',
    ask: `Hi, I'm ${GUIDE}! I'll ask 4 quick questions so this app fits you. First: how long have you been investing?`,
    options: [['new', 'Just starting out'], ['some', '1 to 3 years'], ['long', 'More than 3 years']],
    reply: {
      new: "Welcome! I'll explain the words as we go.",
      some: "Nice, you've seen a few ups and downs by now.",
      long: "Great, you'll know a lot of this already. I'll keep it light.",
    },
  },
  {
    key: 'goal',
    ask: 'What are you mainly after?',
    options: [['grow', 'Growing my money over the long run'], ['trade', 'Making money on stock moves'],
      ['protect', 'Not losing what I have'], ['learn', 'Learning how it all works']],
    reply: {
      grow: 'Got it: the long game.',
      trade: "Plenty of people treat stocks a bit like a bet. I'll help you see the risks behind each one.",
      protect: "Understood. I'll point you to the risk checks.",
      learn: 'Perfect. Every screen explains itself.',
    },
  },
  {
    key: 'drop',
    ask: 'Imagine your portfolio fell 20% in a month. What would you most likely do?',
    options: [['sell', 'Sell some to stop the pain'], ['hold', 'Worry, but hold on'], ['buy', "Buy more while it's cheaper"]],
    reply: {
      sell: "Honest answer, and very human. I'll compare it with how bumpy your portfolio has really been.",
      hold: "That takes nerve. I'll compare it with how bumpy your portfolio has really been.",
      buy: "Bold! I'll compare it with how bumpy your portfolio has really been.",
    },
  },
  {
    key: 'decide',
    ask: 'Last one: how do you usually decide what to buy?',
    options: [['tips', 'Tips from friends or social media'], ['news', "News and what's trending"],
      ['research', 'My own research'], ['plan', 'A set plan or index funds']],
    reply: {
      tips: "Thanks for being straight about it. Tips are one of the most common traps, so I'll watch for it.",
      news: 'Fair. News moves prices fast, which is worth knowing about.',
      research: "Good. I'll give you more to research with.",
      plan: "A plan is a strong habit. I'll help you check it.",
    },
  },
]

// The visitor's answers, e.g. { experience: 'new', goal: 'grow', ... }. {} means they skipped.
export type Profile = Record<string, string>

const PROFILE_KEY = 'mystocks.profile.v1'
const VOICE_KEY = 'mystocks.finVoice.v1'

export function loadProfile(): Profile | null {
  try {
    const raw = localStorage.getItem(PROFILE_KEY)
    return raw ? JSON.parse(raw) as Profile : null
  } catch {
    return null
  }
}

export function storeProfile(profile: Profile | null) {
  try {
    if (profile) localStorage.setItem(PROFILE_KEY, JSON.stringify(profile))
    else localStorage.removeItem(PROFILE_KEY)
  } catch { /* private window: Fin will just ask again next time */ }
}

function loadVoice() {
  try { return localStorage.getItem(VOICE_KEY) === 'on' } catch { return false }
}

function storeVoice(on: boolean) {
  try { localStorage.setItem(VOICE_KEY, on ? 'on' : 'off') } catch { /* not remembered */ }
}

// Fin: an original little fish with a sprout on its head (growth). Blinks, bobs, wags its tail,
// and opens its mouth while talking.
export function FinFace({ talking = false, size = 150 }: { talking?: boolean; size?: number }) {
  return (
    <svg className={`fin-face${talking ? ' talking' : ''}`} width={size} height={size * 190 / 210} viewBox="0 0 210 190" role="img" aria-label="Fin the fish">
      <g className="fin-bob">
        <path d="M100 52 L100 28" stroke="#2E9E5B" strokeWidth="5" fill="none" strokeLinecap="round" />
        <path d="M100 30 C88 12 70 16 70 16 C72 32 88 36 100 30Z" fill="#4ADE80" />
        <path d="M100 28 C112 8 132 12 132 12 C130 30 112 34 100 28Z" fill="#22C55E" />
        <g className="fin-tail"><path d="M160 112 L196 86 Q204 112 196 140 Z" fill="#38B2CC" /></g>
        <ellipse cx="42" cy="126" rx="15" ry="9" fill="#38B2CC" transform="rotate(-25 42 126)" />
        <ellipse cx="100" cy="112" rx="68" ry="62" fill="#5CCBE0" />
        <ellipse cx="100" cy="134" rx="44" ry="36" fill="#C9F2F9" />
        <g className="fin-eye"><ellipse cx="74" cy="100" rx="14" ry="16" fill="#fff" /><circle cx="76" cy="102" r="8" fill="#1B2433" /><circle cx="79" cy="98" r="3" fill="#fff" /></g>
        <g className="fin-eye"><ellipse cx="126" cy="100" rx="14" ry="16" fill="#fff" /><circle cx="128" cy="102" r="8" fill="#1B2433" /><circle cx="131" cy="98" r="3" fill="#fff" /></g>
        <ellipse cx="56" cy="124" rx="9" ry="6" fill="#FF9BB0" opacity=".75" />
        <ellipse cx="144" cy="124" rx="9" ry="6" fill="#FF9BB0" opacity=".75" />
        <path className="fin-smile" d="M88 124 Q100 138 112 124" stroke="#1B2433" strokeWidth="3.5" fill="none" strokeLinecap="round" />
        <g className="fin-mouth"><ellipse cx="100" cy="130" rx="10" ry="8" fill="#7A2E3B" /><ellipse cx="100" cy="135" rx="6" ry="3.5" fill="#FF8FA3" /></g>
      </g>
    </svg>
  )
}

function speak(text: string, onTalking: (on: boolean) => void) {
  try {
    if (!('speechSynthesis' in window)) return
    speechSynthesis.cancel()
    const u = new SpeechSynthesisUtterance(text)
    u.rate = 1.02
    u.pitch = 1.35
    const v = speechSynthesis.getVoices().find((x) => /^en/i.test(x.lang) && /female|samantha|zira|aria|google us english/i.test(x.name))
    if (v) u.voice = v
    u.onstart = () => onTalking(true)
    u.onend = u.onerror = () => onTalking(false)
    speechSynthesis.speak(u)
  } catch { /* no voice: the bubble still shows the words */ }
}

// Fin says `text`: moving mouth + typed speech bubble (+ spoken aloud if `voice`).
function Stage({ text, voice }: { text: string; voice: boolean }) {
  const [shown, setShown] = useState(0)
  const [speaking, setSpeaking] = useState(false)
  const [replay, setReplay] = useState(0)
  const reduced = useRef(typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches)

  useEffect(() => {
    if (reduced.current) { setShown(text.length); return }
    setShown(0)
    const step = voice ? 55 : 28
    const timer = window.setInterval(() => setShown((n) => {
      if (n + 1 >= text.length) window.clearInterval(timer)
      return Math.min(n + 1, text.length)
    }), step)
    return () => window.clearInterval(timer)
  }, [text, voice, replay])

  useEffect(() => {
    if (voice) speak(text, setSpeaking)
    return () => { try { speechSynthesis.cancel() } catch { /* nothing to stop */ } }
  }, [text, voice, replay])

  function hear() {
    setReplay((n) => n + 1)
    if (!voice) speak(text, setSpeaking)
  }

  return (
    <div className="fin-stage">
      <FinFace talking={shown < text.length || speaking} />
      <div className="fin-bubble">
        <div className="fin-ghost" aria-hidden="true">{text}</div>
        <div className="fin-typed" aria-live="polite">{text.slice(0, shown)}</div>
      </div>
      <button type="button" className="fin-hear" onClick={hear}>🔊 Hear {GUIDE}</button>
    </div>
  )
}

// Fin asks the questions, one at a time. Calls onDone with the answers ({} if skipped).
export function FinChat({ onDone }: { onDone: (profile: Profile) => void }) {
  const [answers, setAnswers] = useState<Profile>({})
  const [voice, setVoice] = useState(loadVoice)
  const index = QUESTIONS.findIndex((q) => !(q.key in answers))
  const q = QUESTIONS[index]
  if (!q) return null

  const last = [...QUESTIONS].reverse().find((x) => x.key in answers)
  const reply = last ? last.reply[answers[last.key]] + ' ' : ''
  const said = QUESTIONS.filter((x) => x.key in answers).map((x) => Object.fromEntries(x.options)[answers[x.key]])

  function answer(value: string) {
    const next = { ...answers, [q.key]: value }
    setAnswers(next)
    if (index + 1 >= QUESTIONS.length) onDone(next)
  }

  return (
    <main className="setup-page fin-page">
      <div className="fin-card">
        <p className="setup-kicker">QUESTION {index + 1} OF {QUESTIONS.length}</p>
        <Stage text={reply + q.ask} voice={voice} />
        <label className="fin-toggle">
          <input type="checkbox" checked={voice} onChange={(e) => { setVoice(e.target.checked); storeVoice(e.target.checked) }} />
          <span>🔊 Let {GUIDE} talk out loud</span>
        </label>
        {said.length > 0 && <p className="fin-said">You said: {said.join('  ·  ')}</p>}
        <div className="fin-options">
          {q.options.map(([value, label]) => <button type="button" key={value} onClick={() => answer(value)}>{label}</button>)}
        </div>
        <button type="button" className="fin-skip" onClick={() => onDone({})}>Skip the questions</button>
      </div>
    </main>
  )
}
