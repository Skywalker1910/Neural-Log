import { useId } from 'react'

export type IllustrationKind = 'training' | 'nutrition' | 'lifestyle' | 'journey'

export function LifeIllustration({ kind }: { kind: IllustrationKind }) {
  const id = useId()

  return <svg viewBox="0 0 360 260" className={`life-illustration illustration-${kind}`} aria-hidden="true" focusable="false">
    <defs>
      <linearGradient id={`${id}-metal`} x1="0" y1="0" x2="1" y2="1">
        <stop stopColor="#fff1d5" /><stop offset=".45" stopColor="#dfae74" /><stop offset="1" stopColor="#865333" />
      </linearGradient>
      <linearGradient id={`${id}-surface`} x1="0" y1="0" x2="0" y2="1">
        <stop stopColor="currentColor" stopOpacity=".6" /><stop offset="1" stopColor="currentColor" stopOpacity=".12" />
      </linearGradient>
      <radialGradient id={`${id}-glow`}>
        <stop stopColor="currentColor" stopOpacity=".23" /><stop offset="1" stopColor="currentColor" stopOpacity="0" />
      </radialGradient>
    </defs>
    <ellipse cx="180" cy="138" rx="168" ry="120" fill={`url(#${id}-glow)`} />
    <ellipse cx="180" cy="218" rx="118" ry="17" fill="black" opacity=".35" />
    <g fill="none" stroke="currentColor" opacity=".2">
      <ellipse cx="180" cy="212" rx="140" ry="28" />
      <path d="M42 150V106M20 128H64M294 68V44M282 56H306" />
      <circle cx="305" cy="171" r="5" /><circle cx="80" cy="55" r="3" />
    </g>
    {kind === 'training' ? <>
      <path d="M77 200L211 164L290 191L156 232Z" fill={`url(#${id}-surface)`} stroke="currentColor" strokeOpacity=".35" />
      <g className="illustration-float" transform="rotate(-24 180 125)">
        <rect x="100" y="116" width="160" height="18" rx="8" fill={`url(#${id}-metal)`} />
        <path d="M153 118V132M161 118V132M169 118V132M177 118V132M185 118V132M193 118V132M201 118V132" stroke="#72533e" />
        <rect x="93" y="84" width="34" height="82" rx="9" fill="#824330" stroke="#df8c62" strokeWidth="2" />
        <rect x="112" y="76" width="26" height="98" rx="8" fill={`url(#${id}-metal)`} />
        <rect x="222" y="76" width="34" height="98" rx="9" fill="#824330" stroke="#df8c62" strokeWidth="2" />
        <rect x="243" y="84" width="24" height="82" rx="8" fill={`url(#${id}-metal)`} />
      </g>
      <path d="M66 196L66 172L82 172M288 109V133H272" fill="none" stroke="currentColor" strokeWidth="2" />
    </> : kind === 'nutrition' ? <>
      <g className="illustration-float">
        <path d="M87 141Q93 215 180 217Q267 215 273 141Z" fill={`url(#${id}-metal)`} />
        <ellipse cx="180" cy="141" rx="93" ry="29" fill="#644e33" stroke="#edd6af" strokeWidth="5" />
        <path d="M132 148Q79 92 115 64Q161 80 153 145M171 146Q153 71 204 51Q225 95 193 148M205 144Q239 77 271 96Q274 132 232 151" fill="#76ab73" stroke="#b3ce9a" strokeWidth="2" />
        <path d="M139 132L117 82M182 126L200 71M224 131L252 106" stroke="#355d42" strokeWidth="3" fill="none" />
        <circle cx="140" cy="149" r="19" fill="#d86c4e" /><circle cx="213" cy="150" r="20" fill="#edb551" />
        <path d="M132 146L140 139L148 145M204 148L214 142L221 149" stroke="#fff0bd" strokeOpacity=".6" strokeWidth="3" fill="none" />
        <ellipse cx="178" cy="156" rx="20" ry="10" fill="#e1d3a6" />
        <path d="M121 187Q144 204 170 202" fill="none" stroke="#fff0d5" strokeOpacity=".6" strokeWidth="3" />
      </g>
      <path className="illustration-drift" d="M141 85Q132 74 142 62M161 69Q149 51 163 40" fill="none" stroke="currentColor" strokeWidth="2" />
    </> : kind === 'lifestyle' ? <>
      <path d="M242 44A42 42 0 1 0 286 99A38 38 0 0 1 242 44Z" fill={`url(#${id}-metal)`} />
      <g className="illustration-float">
        <path d="M70 113Q122 92 178 113Q229 90 282 112V200Q231 181 177 207Q123 186 70 203Z" fill="#e5d3b6" />
        <path d="M70 203Q123 186 177 207Q231 181 282 200V207Q232 190 178 216Q121 194 70 211Z" fill="#a7846d" />
        <path d="M178 116V204M90 134Q126 122 158 134M90 154Q126 142 158 154M90 175Q126 163 146 170M198 134Q229 121 261 132M198 154Q229 141 261 152" fill="none" stroke="#af987c" strokeWidth="2" />
        <path d="M207 177Q235 106 285 93Q275 137 220 170L207 189Z" fill="#a989b9" /><path d="M209 184L270 109" stroke="#5e436c" strokeWidth="2" />
      </g>
      <g className="illustration-drift" fill="currentColor"><path d="M108 63L112 74L124 78L112 82L108 94L104 82L93 78L104 74Z" /><circle cx="204" cy="57" r="3" /></g>
    </> : <>
      <circle cx="235" cy="76" r="35" fill={`url(#${id}-metal)`} opacity=".85" />
      <path d="M49 190L133 68L215 191Z" fill="#526f6c" /><path d="M133 68L215 191H154Z" fill="#304743" />
      <path d="M108 105L133 68L158 105L141 98L130 112L120 100Z" fill="#d6dece" />
      <path d="M166 194L232 102L310 198Z" fill="#858568" /><path d="M232 102L310 198H258Z" fill="#565c4b" />
      <path d="M55 208Q94 169 161 190T304 211" fill="none" stroke="#b8ac86" strokeWidth="15" />
      <path d="M54 208Q98 177 160 198T305 214" fill="none" stroke="#ede0ba" strokeWidth="2" strokeDasharray="2 9" />
      <g className="illustration-drift" fill="none" stroke="#e2ccab" strokeWidth="2"><path d="M66 66L76 61L86 66M83 52L93 47L103 52" /></g>
      <g className="illustration-float"><path d="M144 164V115" stroke="#d1c3a5" strokeWidth="3" /><path d="M146 116L181 124L146 138Z" fill="#e5484d" /></g>
    </>}
  </svg>
}
