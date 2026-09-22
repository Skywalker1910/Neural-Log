export function BookCover({ kind, title, subtitle }: {
  kind: 'recipe' | 'exercise' | 'journal'; title: string; subtitle: string
}) {
  return <div className={`book-cover-art cover-${kind}`}>
    <span className="cover-edition">Neural Log · Personal collection</span>
    <svg viewBox="0 0 300 260" aria-hidden className="cover-illustration">
      <circle cx="150" cy="130" r="100" fill="none" stroke="currentColor" opacity=".25" />
      <circle cx="150" cy="130" r="88" fill="none" stroke="currentColor" opacity=".12" strokeDasharray="2 7" />
      {kind === 'recipe' ? <>
        <ellipse cx="150" cy="194" rx="78" ry="12" fill="currentColor" opacity=".12" />
        <path d="M77 143 Q88 215 150 212 Q212 215 223 143Z" fill="#ecc393" />
        <ellipse cx="150" cy="143" rx="73" ry="21" fill="#d29d63" stroke="#f5ddbb" strokeWidth="5" />
        <g className="cover-float"><path d="M128 147 Q89 106 111 77 Q151 91 128 147M153 147 Q143 72 180 59 Q208 100 153 147M170 152 Q197 99 224 111 Q218 147 170 152" fill="#8dac82" />
          <path d="M126 138L113 95M155 136L180 78M173 145L211 119" stroke="#324b39" fill="none" strokeWidth="2" />
          <circle cx="134" cy="142" r="15" fill="#bd6249" /><circle cx="177" cy="144" r="13" fill="#d9ad59" /></g>
        <g className="cover-steam" fill="none" stroke="currentColor" strokeWidth="2"><path d="M134 91 Q118 74 135 58" /><path d="M153 65 Q145 46 160 35" /></g>
      </> : kind === 'exercise' ? <>
        <path d="M63 208H239" stroke="currentColor" opacity=".35" />
        <g className="cover-lift" fill="none" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="145" cy="61" r="14" fill="#f2d9b2" stroke="none" />
          <path d="M142 88L154 136M144 94L111 114L86 94M144 94L178 115L205 93" stroke="#e1c19d" strokeWidth="13" />
          <path d="M154 136L118 163L106 204M154 136L185 165L200 204" stroke="#718c85" strokeWidth="15" />
          <path d="M65 91H228" stroke="#e1c19d" strokeWidth="5" />
          <path d="M72 77V105M84 73V109M210 73V109M222 77V105" stroke="#ac9b73" strokeWidth="9" />
        </g>
        <path d="M45 142L55 132L65 142M55 132V176M236 165L246 175L256 165M246 131V175" fill="none" stroke="currentColor" opacity=".5" />
      </> : <>
        <g className="cover-float"><path d="M91 188V82Q122 74 151 87Q180 74 210 82V188Q180 180 151 194Q122 180 91 188Z" fill="#efe1c6" />
          <path d="M151 88V193" stroke="#bba990" strokeWidth="2" /><path d="M105 105L139 108M105 123L139 127M105 141L139 145M165 108L198 105M165 127L198 123M165 145L190 142" stroke="#b3a48d" strokeWidth="2" />
          <path d="M173 161Q193 86 240 56Q239 104 195 151L173 177Z" fill="#bfa1b8" /><path d="M176 168L228 76" stroke="#624963" strokeWidth="2" /></g>
        <path d="M64 73L68 62L72 73L83 77L72 81L68 92L64 81L53 77Z" fill="currentColor" opacity=".6" />
        <circle cx="224" cy="205" r="3" fill="currentColor" /><circle cx="86" cy="213" r="2" fill="currentColor" />
      </>}
    </svg>
    <div><p className="cover-volume">{kind === 'recipe' ? 'THE KITCHEN COLLECTION' : kind === 'exercise' ? 'THE MOVEMENT COLLECTION' : 'THE EVERYDAY COLLECTION'}</p><h2>{title}</h2><p className="cover-subtitle">{subtitle}</p></div>
    <span className="cover-imprint">Collected one day at a time</span>
  </div>
}
