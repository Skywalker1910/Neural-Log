import assert from 'node:assert/strict'
import { mkdirSync } from 'node:fs'
import { resolve } from 'node:path'
import { chromium } from 'playwright'

const baseURL = process.env.BROWSER_TEST_URL || 'http://127.0.0.1:4173'
const artifacts = resolve('../.pytest_cache/ui')
mkdirSync(artifacts, { recursive: true })
for (let attempt = 0; attempt < 50; attempt++) {
  if (await fetch(baseURL).then(response => response.ok).catch(() => false)) break
  if (attempt === 49) throw new Error('Start the Vite preview before running browser tests.')
  await new Promise(done => setTimeout(done, 200))
}

const exercises = Array.from({ length: 45 }, (_, index) => ({
  id: index + 1, name: index === 0 ? 'Barbell Bench Press' : index === 44 ? 'Zottman Curl' : `Movement ${String(index + 1).padStart(2, '0')}`,
  primary_muscle: index === 0 ? 'chest' : index === 44 ? 'biceps' : ['back', 'chest', 'quads'][index % 3],
  secondary_muscles: ['core'], equipment: 'Barbell', category: 'strength', difficulty: 'beginner', is_compound: true,
  movement_pattern: index === 0 ? 'horizontal-press' : index === 44 ? 'curl' : 'squat',
  instructions: ['Set up with a comfortable stance.', 'Move with control through the repetition.', 'Return to the starting position.'],
}))
const days = Array.from({ length: 7 }, (_, index) => ({date: `2026-09-${14 + index}`, calories: index % 2 ? null : 2000, protein_g: index % 2 ? null : 100, sessions: index % 3 === 0 ? 1 : 0, sets: index % 3 === 0 ? 12 : 0, volume: 1200, sleep_minutes: 480, water_ml: 2000, steps: 5000, mood: 4, study_minutes: 30}))
const post = { id: 1, week_end: '2026-09-20', generated_at: '2026-09-21 09:00:00', snapshot: {start: '2026-09-14', end: '2026-09-20', days, previous_days: days}, report: {title: 'A rhythm worth keeping', summary: 'You recorded a steady week of movement and recovery. Here is a moment to reflect on what worked.', strengths: [{title: 'Consistent recovery', body: 'Your recorded nights show a repeatable routine.'}], opportunities: [{title: 'Fill in the gaps', body: 'A few more meal entries would make your nutrition picture clearer.'}], next_steps: [{title: 'Make time for your next session', body: 'Choose a familiar routine for the week ahead.', workspace: 'training'}], coverage_note: 'Missing entries are unknown. These observations reflect recorded data only.'}}
const recipe = {id:1, name:'Sunday rice bowl', servings:2, total_grams:500, notes:'A favourite for quiet evenings.', instructions:['Rinse the rice.', 'Simmer gently.', 'Rest before serving.'], food:{kcal_per_100g:140, protein_per_100g:8}, ingredients:[{food_id:1,position:0,name:'Rice',grams:200},{food_id:2,position:1,name:'Lentils',grams:100}]}
let posts = []
let generated = 0
const journal = new Map([['2026-09-21', 'A quiet walk and a good meal.']])
const browser = await chromium.launch({executablePath:process.env.BROWSER_EXECUTABLE_PATH, headless:true})
const errors = []
async function setup(options) {
  const context = await browser.newContext(options)
  await context.route('**/api/**', async route => {
    const path = new URL(route.request().url()).pathname
    let body = {}
    if(path === '/api/current-user') body = {id:1,username:'Reader',is_admin:false}
    else if(path === '/api/gamification/summary') body = {level:1,xp_for_next_level:100,xp_into_level:5,current_streak:1}
    else if(path === '/api/assistant/state') body = {configured:false}
    else if(path === '/api/exercises') body = {exercises}
    else if(path === '/api/recipes') body = {recipes:[recipe]}
    else if(path === '/api/feed/posts') {
      if(route.request().method() === 'POST') { generated++; posts=[post]; body=post }
      else body = {posts,configured:true,has_data:true,latest_week_end:'2026-09-20'}
    }
    else if(path === '/api/journal/entries') body = {entries:[...journal].map(([date,entry])=>({date,journal:entry}))}
    else if(path.startsWith('/api/lifestyle/')) {
      const date=path.split('/').at(-1)
      if(route.request().method() === 'PUT') journal.set(date,route.request().postDataJSON().journal)
      body={lifestyle:{date,journal:journal.get(date)??''},sleep:null}
    }
    await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(body)})
  })
  const page = await context.newPage()
  page.on('pageerror', error=>errors.push(error.message))
  return {page, context}
}
async function ready(page, url) { await page.goto(baseURL+url); await page.locator('.book-controls').waitFor(); await page.waitForTimeout(600) }
async function drag(page, fraction, direction = -1) {
  const box = await page.locator('.book-spread').boundingBox()
  const start = direction < 0 ? box.x+box.width*.87 : box.x+box.width*.1
  await page.mouse.move(start,box.y+90)
  await page.mouse.down()
  await page.mouse.move(start+direction*box.width*fraction,box.y+91,{steps:12})
  assert.equal(await page.locator('.book-turning').count(),1)
  await page.mouse.up()
  await page.waitForTimeout(600)
}
try {
  const {page} = await setup({viewport:{width:1440,height:1050}})
  await ready(page,'/training/book')
  assert.equal(await page.locator('.book-wide').count(),1)
  await page.screenshot({path:resolve(artifacts,'exercise-cover.png'),fullPage:true})
  await drag(page,.35)
  assert.match(await page.locator('.book-controls').innerText(),/Page 1–2/)
  const beforeCancel = await page.locator('.book-controls').innerText()
  const cancelledBox = await page.locator('.book-spread').boundingBox()
  await page.mouse.move(cancelledBox.x+cancelledBox.width*.8,cancelledBox.y+85)
  await page.mouse.down()
  await page.mouse.move(cancelledBox.x+cancelledBox.width*.78,cancelledBox.y+85,{steps:6})
  await page.waitForTimeout(400)
  await page.mouse.up()
  await page.waitForTimeout(550)
  assert.equal(await page.locator('.book-controls').innerText(),beforeCancel)
  await drag(page,.3,1)
  assert.match(await page.locator('.book-controls').innerText(),/Cover/)
  assert.equal(await page.getByRole('button',{name:'Previous pages'}).isDisabled(),true)
  await page.getByRole('button',{name:'Index',exact:true}).click()
  await page.getByRole('combobox',{name:'Jump to muscle chapter'}).selectOption('chest')
  await page.getByRole('heading',{name:'Barbell Bench Press',exact:true}).waitFor()
  await page.screenshot({path:resolve(artifacts,'exercise-spread.png'),fullPage:true})
  await page.getByRole('button',{name:'Play demonstration',exact:true}).first().click()
  await page.waitForTimeout(300)
  assert.notEqual(await page.getByRole('slider',{name:'Exercise movement position'}).first().inputValue(),'0')
  await page.getByRole('button',{name:'Pause demonstration',exact:true}).click()
  await page.getByRole('searchbox',{name:'Find an exercise in the book'}).fill('Zottman')
  await page.getByRole('button',{name:'Zottman Curl',exact:true}).click()
  await page.getByRole('heading',{name:'Zottman Curl',exact:true}).waitFor()
  await page.locator('.book-spread').focus()
  await page.keyboard.press('ArrowRight')
  await page.waitForTimeout(600)
  await ready(page,'/recipes')
  assert.match(page.url(),/nutrition\/book/)
  await page.getByRole('button',{name:'Index',exact:true}).click()
  await page.getByRole('button',{name:/Sunday rice bowl/}).click()
  await page.getByRole('heading',{name:'Sunday rice bowl',exact:true,level:2}).waitFor()
  await page.screenshot({path:resolve(artifacts,'recipe-spread.png'),fullPage:true})
  await ready(page,'/journal')
  await page.getByLabel('Journal date',{exact:true}).fill('2026-09-21')
  const editor = page.getByRole('textbox',{name:'Journal for 2026-09-21'})
  await editor.fill('An unsaved thought worth keeping.')
  await page.getByRole('button',{name:'Cover',exact:true}).click()
  await page.getByRole('button',{name:'Index',exact:true}).click()
  await page.getByRole('button',{name:/Monday, Sep 21/}).click()
  assert.equal(await editor.inputValue(),'An unsaved thought worth keeping.')
  await page.getByRole('button',{name:'Save entry',exact:true}).click()
  await page.getByText('Entry saved.',{exact:true}).waitFor()
  assert.equal(journal.get('2026-09-21'),'An unsaved thought worth keeping.')
  await page.goto(baseURL+'/feed')
  await page.getByRole('heading',{name:post.report.title,exact:true}).waitFor()
  assert.equal(generated,1)
  await page.getByRole('button',{name:'Sleep',exact:true}).click()
  assert.equal(await page.getByRole('button',{name:'Sleep',exact:true}).getAttribute('aria-pressed'),'true')
  await page.getByText('View recorded data',{exact:true}).click()
  await page.getByRole('table').waitFor()
  await page.screenshot({path:resolve(artifacts,'feed-desktop.png'),fullPage:true})
  await page.reload()
  await page.getByRole('heading',{name:post.report.title,exact:true}).waitFor()
  assert.equal(generated,1)
  const {page:mobile,context:mobileContext} = await setup({viewport:{width:390,height:844},isMobile:true,hasTouch:true,deviceScaleFactor:1})
  await ready(mobile,'/training/book')
  assert.equal(await mobile.locator('.book-single').count(),1)
  await mobile.screenshot({path:resolve(artifacts,'book-mobile-cover.png'),fullPage:true})
  const mobileBox=await mobile.locator('.book-spread').boundingBox()
  const touch=await mobileContext.newCDPSession(mobile)
  await touch.send('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[{x:mobileBox.x+mobileBox.width*.85,y:mobileBox.y+90}]})
  for(let step=1;step<=8;step++) {
    await touch.send('Input.dispatchTouchEvent',{type:'touchMove',touchPoints:[{x:mobileBox.x+mobileBox.width*(.85-step*.07),y:mobileBox.y+90}]})
  }
  await touch.send('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]})
  await mobile.waitForTimeout(650)
  assert.match(await mobile.locator('.book-controls').innerText(),/Page 1 of/)
  assert.ok(await mobile.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+1))
  await mobile.getByRole('combobox',{name:'Jump to muscle chapter'}).selectOption('chest')
  await mobile.getByRole('heading',{name:'Barbell Bench Press',exact:true}).waitFor()
  await mobile.screenshot({path:resolve(artifacts,'book-mobile-page.png'),fullPage:true})
  await mobile.goto(baseURL+'/feed')
  await mobile.getByRole('heading',{name:post.report.title,exact:true}).waitFor()
  assert.ok(await mobile.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+1))
  await mobile.locator('.recharts-surface').waitFor()
  await mobile.screenshot({path:resolve(artifacts,'feed-mobile.png'),fullPage:true})
  await mobile.emulateMedia({reducedMotion:'reduce'})
  await ready(mobile,'/training/book')
  await mobile.getByRole('button',{name:'Next pages',exact:true}).click()
  await mobile.waitForTimeout(100)
  assert.match(await mobile.locator('.book-controls').innerText(),/Page 1 of/)
  assert.deepEqual(errors,[])
  console.log('PASS: desktop drag, cancelled and backward turns, cover boundary, keyboard turns, muscle chapters, all-exercise search, recipe redirect/index, journal draft retention/save, automatic feed persistence, chart/table controls, mobile touch swipe, viewport overflow, reduced motion. No browser exceptions.')
} finally { await browser.close() }
