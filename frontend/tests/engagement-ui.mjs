import assert from 'node:assert/strict'
import { mkdirSync } from 'node:fs'
import { resolve } from 'node:path'
import { chromium } from 'playwright'

const baseURL = process.env.BROWSER_TEST_URL || 'http://127.0.0.1:4173'
const artifacts = resolve('../.pytest_cache/ui/engagement')
mkdirSync(artifacts, { recursive: true })

const badges = [
  ['first-log', 'First Steps', 'consistency', 'bronze', true, 12, 1],
  ['week-streak', 'One Week Strong', 'consistency', 'bronze', false, 4, 7],
  ['century', 'Century Club', 'consistency', 'gold', false, 12, 100],
  ['first-workout', 'Rack Pulled', 'training', 'bronze', true, 9, 1],
  ['workouts-25', 'Regular', 'training', 'silver', false, 9, 25],
  ['first-meal', 'Weighed and Measured', 'nutrition', 'bronze', true, 12, 1],
  ['nights-30', 'Well Rested', 'lifestyle', 'silver', false, 15, 30],
  ['first-study', 'Opened the Book', 'learning', 'bronze', false, 0, 1],
  ['level-10', 'Double Digits', 'mastery', 'gold', false, 3, 10],
].map(([code, name, category, tier, earned, current, threshold]) => ({ code, name, category, tier, earned, current, threshold, progress: Math.min(1, current / threshold), xp_reward: 25, description: `Reach ${threshold} recorded milestones in ${category}.` }))
const targets = { calories: 2200, protein_g: 120, carbs_g: 260, fat_g: 65, fibre_g: 30, water_ml: 2500, steps: 8000, sleep_minutes: 480, weekly_study_minutes: 120, sources: { calories: 'set', protein: 'set' } }
const summary = { level: 3, total_xp: 420, xp_into_level: 20, xp_for_next_level: 100, current_streak: 4, streak_multiplier_pct: 0, badges }
const onboarding = { completed: true, completed_at: '2026-09-01', should_prompt: false, step: 0, steps: [], survey: [], answers: { goal: 'maintain', activity_level: 'moderate' }, baselines: { missing: [], bmi: null, bmr: null, tdee: null, age: null }, targets }
const errors = []
const unexpected = new Set()
const mutations = []
const browser = await chromium.launch({ executablePath: process.env.BROWSER_EXECUTABLE_PATH, headless: true })

async function setup({ username = 'Alex Morgan', empty = false, unavailable = false, ...options } = {}) {
  const context = await browser.newContext(options)
  await context.route('**/api/**', async route => {
    const request = route.request()
    if (request.method() !== 'GET') mutations.push(request.url())
    const path = new URL(request.url()).pathname
    let body
    let status = 200
    if (path === '/api/current-user') body = { user_id: 1, username, is_admin: false, selected_path: 'A balanced everyday', selected_path_id: null, leaderboard_opt_out: false }
    else if (path === '/api/gamification/summary') {
      body = empty ? { ...summary, current_streak: 0, badges: badges.map(badge => ({ ...badge, earned: false, current: 0, progress: 0 })) } : summary
      if (unavailable) { status = 503; body = { error: 'Temporarily unavailable' } }
    }
    else if (path === '/api/gamification/ledger') body = { entries: [], by_source: [], evidence: { measured: 0, claimed: 0 } }
    else if (path === '/api/home') body = { ...summary, date: '2026-09-23', days_logged: empty ? 0 : 12, daily_score: null, discipline_score: null, today: { logged: false, completion_pct: 0, items_total: 10, items_completed: 0 }, attributes: [], trend: [] }
    else if (path === '/api/onboarding') body = onboarding
    else if (path === '/api/attributes') body = { attributes: [] }
    else if (path === '/api/assistant/state') body = { configured: false }
    else { unexpected.add(path); body = {} }
    await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })
  })
  const page = await context.newPage()
  page.on('pageerror', error => errors.push(error.message))
  return { page, context }
}

async function noOverflow(page) {
  const sizes = await page.evaluate(() => ({ width: document.documentElement.clientWidth, content: document.documentElement.scrollWidth }))
  if (sizes.content > sizes.width) {
    console.log(await page.locator('body *').evaluateAll(elements => elements.filter(element => element.getBoundingClientRect().right > document.documentElement.clientWidth + 1).map(element => ({ tag: element.tagName, className: element.getAttribute('class'), width: element.getBoundingClientRect().width })).slice(-10)))
    await page.screenshot({ path: resolve(artifacts, 'overflow.png'), fullPage: true })
  }
  assert.ok(sizes.content <= sizes.width, `Horizontal overflow: ${JSON.stringify(sizes)}`)
}

try {
  const { page, context } = await setup({ viewport: { width: 1440, height: 1050 } })
  await page.goto(`${baseURL}/profile`)
  await page.getByRole('heading', { name: 'Alex Morgan', exact: true }).waitFor()
  await page.getByRole('link', { name: "Alex Morgan's profile" }).first().waitFor()
  assert.equal(await page.getByRole('link', { name: "Alex Morgan's profile" }).count(), 2)
  assert.equal(await page.locator('.profile-medal').count(), 3)
  await page.waitForTimeout(700)
  await noOverflow(page)
  await page.screenshot({ path: resolve(artifacts, 'profile-desktop.png'), fullPage: true })
  const card = page.locator('.profile-identity')
  const box = await card.boundingBox()
  await page.mouse.move(box.x + box.width * .8, box.y + box.height * .3)
  await page.waitForTimeout(300)
  assert.notEqual(await card.evaluate(element => getComputedStyle(element).getPropertyValue('--tilt-y')), '')
  await page.mouse.move(10, 10)
  assert.equal(await card.evaluate(element => element.style.getPropertyValue('--tilt-y')), '')
  await page.getByRole('link', { name: 'Explore your achievements' }).click()
  await page.getByRole('heading', { name: 'Little wins. Lasting reminders.' }).waitFor()
  await page.getByRole('article', { name: 'First Steps' }).waitFor()
  assert.equal(await page.locator('.achievement-card').count(), badges.length)
  const locked = page.getByRole('article', { name: 'Regular', exact: true })
  assert.equal(await locked.getByRole('progressbar').getAttribute('aria-valuenow'), '36')
  assert.equal(await locked.locator('.achievement-copy').evaluate(element => getComputedStyle(element).filter), 'none')
  assert.match(await locked.locator('.achievement-emblem').evaluate(element => getComputedStyle(element).filter), /blur/)
  await page.waitForTimeout(900)
  await page.screenshot({ path: resolve(artifacts, 'achievements-desktop.png'), fullPage: true })
  await page.getByRole('group', { name: 'Achievement category' }).getByRole('button', { name: 'Training', exact: true }).click()
  assert.equal(await page.locator('.achievement-card').count(), 2)
  await page.getByRole('combobox', { name: 'Achievement status' }).selectOption('earned')
  assert.equal(await page.locator('.achievement-card').count(), 1)
  await page.getByRole('article', { name: 'Rack Pulled' }).waitFor()
  await page.getByRole('group', { name: 'Achievement category' }).getByRole('button', { name: 'Learning', exact: true }).click()
  await page.getByText('No badges here yet.', { exact: false }).waitFor()
  await page.getByRole('combobox', { name: 'Achievement status' }).selectOption('locked')
  await page.getByRole('article', { name: 'Opened the Book' }).waitFor()
  await page.goto(baseURL)
  await page.getByRole('heading', { name: 'Small steps. A story worth building.' }).waitFor()
  await page.waitForTimeout(700)
  await page.screenshot({ path: resolve(artifacts, 'home-desktop.png'), fullPage: true })
  assert.equal(await page.getByRole('link', { name: 'Start your day', exact: true }).getAttribute('href'), '/today')
  await context.close()

  for (const width of [390, 320]) {
    const { page: mobile, context: mobileContext } = await setup({ viewport: { width, height: 844 }, isMobile: true, hasTouch: true, username: 'AlexandraMorganWithAnExtraLongName' })
    await mobile.goto(`${baseURL}/profile`)
    await mobile.getByRole('heading', { name: 'AlexandraMorganWithAnExtraLongName' }).waitFor()
    await noOverflow(mobile)
    await mobile.getByRole('button', { name: 'More', exact: true }).click()
    const profileLink = mobile.getByRole('dialog').getByRole('link', { name: "AlexandraMorganWithAnExtraLongName's profile" })
    await profileLink.click()
    await mobile.getByRole('dialog').waitFor({ state: 'hidden' })
    await mobile.waitForTimeout(900)
    await mobile.screenshot({ path: resolve(artifacts, `profile-${width}.png`), fullPage: true })
    await mobile.goto(`${baseURL}/achievements`)
    await mobile.getByRole('article', { name: 'First Steps' }).waitFor()
    await noOverflow(mobile)
    await mobile.getByRole('combobox', { name: 'Achievement status' }).selectOption('locked')
    assert.equal(await mobile.locator('.achievement-earned').count(), 0)
    await mobile.waitForTimeout(900)
    await mobile.screenshot({ path: resolve(artifacts, `achievements-${width}.png`), fullPage: true })
    await mobile.goto(baseURL)
    await mobile.getByRole('heading', { name: 'Small steps. A story worth building.' }).waitFor()
    await noOverflow(mobile)
    await mobile.waitForTimeout(900)
    await mobile.screenshot({ path: resolve(artifacts, `home-${width}.png`), fullPage: true })
    await mobileContext.close()
  }

  const { page: reduced, context: reducedContext } = await setup({ viewport: { width: 1280, height: 900 }, reducedMotion: 'reduce', empty: true })
  await reduced.goto(`${baseURL}/profile`)
  await reduced.getByText('Your collection starts with a first step.').waitFor()
  await reduced.locator('.profile-identity').hover()
  assert.equal(await reduced.locator('.profile-identity').evaluate(element => getComputedStyle(element).transform), 'none')
  assert.equal(await reduced.locator('.profile-spark').evaluate(element => getComputedStyle(element).animationName), 'none')
  await reduced.goto(baseURL)
  await reduced.getByRole('heading', { name: 'Every good story starts somewhere.' }).waitFor()
  assert.equal(await reduced.locator('.illustration-float').evaluate(element => getComputedStyle(element).animationName), 'none')
  await reducedContext.close()

  const { page: unavailablePage, context: unavailableContext } = await setup({ unavailable: true })
  await unavailablePage.goto(`${baseURL}/profile`)
  await unavailablePage.getByText('Your collection is unavailable right now.', { exact: false }).waitFor()
  await unavailablePage.getByRole('heading', { name: 'Alex Morgan', exact: true }).waitFor()
  assert.equal(await unavailablePage.getByText('Your collection starts with a first step.').count(), 0)
  await unavailableContext.close()
  assert.deepEqual([...unexpected], [], 'Unexpected API requests need fixtures')
  assert.deepEqual(mutations, [], 'Visual browsing must not change account data')
  assert.deepEqual(errors, [], 'No browser runtime errors')
  console.log('Engagement UI passed: profile identity, badge filters, locked progress, mobile navigation, long names, empty/error states, reduced motion, and read-only browsing.')
} finally {
  await browser.close()
}
