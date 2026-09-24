import { useId } from 'react'
import { Compass, type LucideIcon } from 'lucide-react'

export type SectionArt = 'analytics' | 'goals' | 'learning' | 'library' | 'feed' | 'achievements' | 'today' | 'identity'

export function SectionIllustration({ kind = 'identity', icon: Icon = Compass }: { kind?: SectionArt; icon?: LucideIcon }) {
  const id = useId()
  const metal = `url(#${id}-metal)`
  const paper = `url(#${id}-paper)`
  return <svg viewBox="0 0 360 260" className={`life-illustration section-art art-${kind}`} aria-hidden="true" focusable="false">
    <defs>
      <linearGradient id={`${id}-metal`} x2="1" y2="1"><stop stopColor="#fae8c7" /><stop offset=".5" stopColor="currentColor" /><stop offset="1" stopColor="#685747" /></linearGradient>
      <linearGradient id={`${id}-paper`} x2=".3" y2="1"><stop stopColor="#f4e5c9" /><stop offset="1" stopColor="#b7a182" /></linearGradient>
      <radialGradient id={`${id}-halo`}><stop stopColor="currentColor" stopOpacity=".22" /><stop offset="1" stopColor="currentColor" stopOpacity="0" /></radialGradient>
    </defs>
    <ellipse cx="180" cy="136" rx="165" ry="118" fill={`url(#${id}-halo)`} />
    <ellipse cx="180" cy="217" rx="112" ry="17" fill="#000" opacity=".3" />
    <ellipse cx="180" cy="213" rx="140" ry="28" fill="none" stroke="currentColor" opacity=".2" />
    <g className="illustration-drift" fill="none" stroke="currentColor" opacity=".6">
      <path d="M55 89V111M44 100H66M294 59V77M285 68H303" /><circle cx="288" cy="169" r="4" /><circle cx="88" cy="49" r="3" />
    </g>
    <g className="illustration-float">
      {kind === 'analytics' ? <>
        <path d="M77 203L226 176L284 205L134 232Z" fill={metal} opacity=".4" />
        {[{ x: 98, y: 150, height: 50 }, { x: 158, y: 114, height: 78 }, { x: 218, y: 68, height: 115 }].map(bar => <g key={bar.x}><rect x={bar.x} y={bar.y} width="36" height={bar.height} rx="5" fill={metal} /><path d={`M${bar.x + 36} ${bar.y}l12 -8v${bar.height}l-12 8Z`} fill="currentColor" opacity=".4" /></g>)}
        <path className="art-trace" d="M92 124L162 83L233 42M211 43L234 41L230 64" fill="none" stroke="#e9cf99" strokeWidth="4" strokeLinecap="round" />
      </> : kind === 'goals' ? <>
        <path d="M153 184L134 218M207 184L226 218" stroke={metal} strokeWidth="10" strokeLinecap="round" />
        <circle cx="180" cy="124" r="79" fill="#424d48" stroke={metal} strokeWidth="9" />
        <circle cx="180" cy="124" r="54" fill="none" stroke="currentColor" strokeWidth="14" />
        <circle cx="180" cy="124" r="26" fill={metal} />
        <path d="M180 124L271 48M253 64L254 43L280 29L273 54L253 64Z" fill="#dbb280" stroke="#f4dfba" strokeWidth="3" strokeLinejoin="round" />
      </> : kind === 'learning' || kind === 'library' ? <>
        <path d="M79 180L226 165L275 193L129 215Z" fill="#557a72" stroke="currentColor" strokeWidth="2" />
        <path d="M82 180V195L129 225L274 203V193L129 215Z" fill={paper} />
        <path d="M88 143Q128 126 178 151Q223 119 269 131V183Q221 173 178 200Q132 178 88 188Z" fill={paper} stroke="#a78b6a" strokeWidth="2" />
        <path d="M178 151V198M105 152L154 168M105 166L154 182M199 150L250 143M199 163L250 157" fill="none" stroke="#958064" strokeWidth="2" />
        {kind === 'learning' ? <><path d="M153 71A28 28 0 1 1 205 85L199 99H167L162 87Z" fill={metal} /><path d="M169 107H197M173 115H193M179 98V78L170 70M179 78L191 68" fill="none" stroke="#f2d39c" strokeWidth="4" strokeLinecap="round" /><path className="art-trace" d="M135 52L124 43M181 32V18M222 51L236 42" stroke="currentColor" strokeWidth="3" /></> : <><path d="M108 113V62Q178 38 249 62V114Q178 88 108 113Z" fill="#6a7479" stroke={metal} strokeWidth="3" /><path d="M179 51V100M126 74Q146 69 160 74M198 74Q216 70 233 77M126 87Q146 82 160 87" fill="none" stroke="#e6ceb0" strokeWidth="2" /></>}
      </> : kind === 'feed' || kind === 'today' ? <>
        <rect x="100" y="51" width="158" height="161" rx="10" fill="#75624f" transform="rotate(8 180 130)" />
        <rect x="91" y="44" width="158" height="162" rx="9" fill={paper} />
        <path d="M111 72H228" stroke="#776954" strokeWidth="3" />
        {kind === 'feed' ? <><rect x="110" y="87" width="56" height="51" rx="3" fill="#5f8075" /><path d="M116 129L130 105L142 118L151 110L161 129" fill="none" stroke="#e4d3ad" strokeWidth="3" /><path d="M181 93H228M181 110H220M181 128H228M111 154H228M111 171H228M111 187H184" stroke="#968166" strokeWidth="4" strokeLinecap="round" /></> : <><path d="M122 36V56M216 36V56" stroke="#e7c896" strokeWidth="9" strokeLinecap="round" />{[100, 139, 178].map(position => <g key={position}><rect x="111" y={position - 9} width="17" height="17" rx="4" fill="#52766a" /><path d={`M115 ${position}l4 4 7 -10`} fill="none" stroke="#eee0bf" strokeWidth="2" /><path d={`M144 ${position}H225`} stroke="#988267" strokeWidth="4" /></g>)}</>}
      </> : kind === 'achievements' ? <>
        <path d="M143 133L129 219L158 204L178 225L185 153M182 155L205 223L224 202L251 210L221 128" fill="#8d5852" stroke="#c69275" strokeWidth="2" />
        <circle cx="181" cy="111" r="70" fill={metal} /><circle cx="181" cy="111" r="56" fill="#55463a" stroke="#f4d49c" strokeWidth="2" />
        <path d="M181 71L193 96L221 100L201 119L206 148L181 134L156 148L161 119L141 100L169 96Z" fill={metal} />
      </> : <>
        <path d="M109 177L180 213L253 176V92L181 51L109 92Z" fill="#373b3f" stroke={metal} strokeWidth="3" />
        <circle cx="181" cy="129" r="57" fill="#242b2d" stroke="currentColor" strokeOpacity=".5" />
        <Icon x="148" y="95" width="66" height="66" stroke="currentColor" strokeWidth="1.25" />
        <path d="M126 183L181 210L236 183" fill="none" stroke="#e6c99b" strokeWidth="3" />
      </>}
    </g>
  </svg>
}
