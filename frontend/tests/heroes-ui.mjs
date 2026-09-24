import assert from 'node:assert/strict'
import { mkdirSync } from 'node:fs'
import { resolve } from 'node:path'
import { chromium } from 'playwright'

const baseURL = process.env.BROWSER_TEST_URL || 'http://127.0.0.1:4173'
const artifacts = resolve('../.pytest_cache/ui/heroes')
mkdirSync(artifacts, { recursive: true })
const browser = await chromium.launch({ executablePath: process.env.BROWSER_EXECUTABLE_PATH, headless: true })
const errors = []
const targets = { calories: 2200, protein_g: 130, carbs_g: 250, fat_g: 70, fibre_g: 30, water_ml: 2500, steps: 8000, sleep_minutes: 480, sources: { calories: 'estimated', protein: 'estimated', carbs: 'estimated', fat: 'estimated' }, tdee: null }
const routes = ['/training', '/nutrition', '/lifestyle', '/learning', '/goals', '/analytics', '/library', '/feed', '/profile', '/achievements', '/settings', '/today', '/admin']
const buttonColours = { training: '#dcaa7e', nutrition: '#a4c39a', lifestyle: '#b6a5d3', learning: '#9eb7ce', analytics: '#9eb7ce', goals: '#d5bd86', library: '#d5bd86', achievements: '#d5bd86', today: '#d5bd86' }
function rgb(hex) {
  return `rgb(${[1, 3, 5].map(offset => parseInt(hex.slice(offset, offset + 2), 16)).join(', ')})`
}

async function setup(width) {
  const context = await browser.newContext({ viewport: { width, height: 960 }, reducedMotion: 'reduce', hasTouch: width < 768, isMobile: width < 768 })
  await context.route('**/api/**', async route => {
    const path = new URL(route.request().url()).pathname
    let body
    if (path === '/api/current-user') body = { id: 1, username: 'AlexandraMorganWithAnExtraLongName', is_admin: true }
    else if (path === '/api/gamification/summary') body = { level: 3, xp_for_next_level: 100, xp_into_level: 20, current_streak: 0, badges: [] }
    else if (path === '/api/assistant/state') body = { configured: true }
    else if (path === '/api/training') body = { total_sessions: 3, total_volume: 1250, recent: [], volume_trend: [], by_muscle: [], records: [], measurements: [] }
    else if (path === '/api/routines') body = { routines: [] }
    else if (path.startsWith('/api/nutrition/')) body = { date: path.split('/').at(-1), entries: [], by_meal: {}, totals: { calories: 1200, protein_g: 80, carbs_g: 160, fat_g: 40, fibre_g: 18 }, targets, body_weight_kg: null }
    else if (path === '/api/lifestyle') body = { sleep: [], lifestyle: [], targets, averages: { sleep_minutes: 470, schedule_consistency: 85, water_ml: 2100, steps: 7000 } }
    else if (path === '/api/feed/posts') body = { posts: [], configured: false, has_data: false, latest_week_end: '2026-09-20' }
    if (body === undefined) await route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ error: 'No fixture for this section content.' }) })
    else await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) })
  })
  const page = await context.newPage()
  page.on('pageerror', error => errors.push(error.message))
  return { page, context }
}

async function checkHero(page, path, width) {
  console.log(`Checking ${path} at ${width}px`)
  if (path === '/admin') {
    await page.goto(baseURL + '/settings')
    if (width < 1024) {
      await page.getByRole('button', { name: 'More', exact: true }).click()
      await page.getByRole('dialog').getByRole('link', { name: 'Admin', exact: true }).click()
    } else await page.getByRole('link', { name: 'Admin', exact: true }).click()
  } else await page.goto(baseURL + path)
  await page.locator('.page-hero h1').waitFor()
  await page.mouse.move(0, 0)
  const accent = buttonColours[path.split('/')[1]] || '#d0aa97'
  assert.equal(await page.locator('#main').evaluate(element => getComputedStyle(element).getPropertyValue('--button-accent').trim()), accent)
  const primaryColours = await page.locator('#main .app-button.button-primary').evaluateAll(buttons => buttons.map(button => ({ background: getComputedStyle(button).backgroundColor, text: getComputedStyle(button).color })))
  for (const colours of primaryColours) {
    assert.equal(colours.background, rgb(accent), `${path}: primary button should match the page`)
    assert.equal(colours.text, 'rgb(32, 28, 25)', `${path}: primary labels need dark text on pastel backgrounds`)
  }
  const layout = await page.locator('.page-hero').evaluate(hero => {
    const bounds = hero.getBoundingClientRect()
    const outside = [...hero.querySelectorAll('h1, p, button, a, input, .page-hero-anim')].filter(element => {
      const rect = element.getBoundingClientRect()
      return rect.width > 0 && (rect.left < bounds.left || rect.right > bounds.right + 1 || rect.top < bounds.top || rect.bottom > bounds.bottom + 1)
    }).map(element => element.textContent || element.tagName)
    return { outside, width: document.documentElement.clientWidth, content: document.documentElement.scrollWidth }
  })
  assert.deepEqual(layout.outside, [], `${path} at ${width}px: controls must stay inside hero`)
  assert.ok(layout.content <= layout.width, `${path} at ${width}px: horizontal overflow`)
  assert.equal(await page.locator('.page-hero svg.life-illustration').count(), 1)
  assert.equal(await page.locator('.page-hero .illustration-float').evaluate(element => getComputedStyle(element).animationName), 'none')
}

try {
  for (const width of [1440, 768, 390, 320]) {
    const { page, context } = await setup(width)
    for (const path of routes) await checkHero(page, path, width)
    await page.goto(baseURL + '/nutrition')
    await page.getByRole('heading', { name: "Today's totals", exact: true }).waitFor()
    await page.getByRole('button', { name: 'Scan a label', exact: true }).click()
    const scanner = page.getByRole('dialog', { name: 'Scan a nutrition label', exact: true })
    await scanner.getByRole('button', { name: 'Scan automatically', exact: true }).waitFor()
    await scanner.getByRole('button', { name: 'Take a photo', exact: true }).waitFor()
    await page.keyboard.press('Escape')
    await scanner.waitFor({ state: 'hidden' })
    const totals = await page.locator('.nutrition-totals').evaluate(element => {
      const style = getComputedStyle(element)
      const bounds = element.getBoundingClientRect()
      const workspace = element.closest('.book-workspace').getBoundingClientRect()
      return { border: style.borderWidth, background: style.backgroundColor, ratio: bounds.width / workspace.width }
    })
    assert.equal(totals.border, '0px')
    assert.equal(totals.background, 'rgba(0, 0, 0, 0)')
    if (width === 1440) assert.ok(totals.ratio > .4 && totals.ratio < .55)
    await page.screenshot({ path: resolve(artifacts, `nutrition-${width}.png`), fullPage: true })
    await page.goto(baseURL + '/learning')
    await page.locator('.page-hero').waitFor()
    await page.screenshot({ path: resolve(artifacts, `learning-${width}.png`), fullPage: true })
    if (width === 1440) {
      await page.goto(baseURL + '/library')
      await page.getByRole('button', { name: 'Open Recipe book', exact: true }).click()
      const recipeAction = page.getByRole('dialog', { name: 'Recipe book', exact: true }).getByRole('button', { name: 'Add recipe', exact: true })
      await recipeAction.waitFor()
      assert.equal(await recipeAction.evaluate(element => getComputedStyle(element).getPropertyValue('--button-accent').trim()), buttonColours.nutrition)
      await page.getByRole('button', { name: 'Close book', exact: true }).click()
    }
    if (width === 390) {
      let attempts = 0
      await context.addCookies([{ name: 'csrf_token', value: 'test-csrf', url: baseURL }])
      await context.route('**/logout', async route => {
        attempts++
        assert.equal(route.request().method(), 'POST')
        assert.equal(route.request().headers()['x-csrf-token'], 'test-csrf')
        if (attempts === 1) await route.fulfill({ status: 500, contentType: 'application/json', body: JSON.stringify({ error: 'Try again' }) })
        else await route.fulfill({ status: 302, headers: { location: '/login' } })
      })
      await context.route('**/login', route => route.fulfill({ contentType: 'text/html', body: '<h1>Sign in</h1>' }))
      await page.getByRole('button', { name: 'More', exact: true }).click()
      const dialog = page.getByRole('dialog', { name: 'All sections' })
      const signOut = dialog.getByRole('button', { name: 'Sign out', exact: true })
      await signOut.click()
      await dialog.getByRole('alert').filter({ hasText: 'Could not sign out' }).waitFor()
      assert.ok(await signOut.isEnabled())
      await signOut.click()
      await page.waitForURL('**/login')
      assert.equal(attempts, 2)
    }
    await context.close()
  }
  for (const availability of ['loading', 'unconfigured', 'error']) {
    const { page, context } = await setup(390)
    let releaseCheck
    let recovered = false
    const pendingCheck = new Promise(resolveCheck => { releaseCheck = resolveCheck })
    await context.route('**/api/assistant/state', async route => {
      if (availability === 'loading') await pendingCheck
      const failed = availability === 'error' && !recovered
      await route.fulfill({ status: failed ? 503 : 200, contentType: 'application/json', body: JSON.stringify(failed ? { error: 'Unavailable' } : { configured: availability !== 'unconfigured' || recovered }) })
    })
    await page.goto(baseURL + '/nutrition')
    await page.getByRole('button', { name: 'Scan a label', exact: true }).click()
    const scanner = page.getByRole('dialog', { name: 'Scan a nutrition label', exact: true })
    if (availability === 'loading') {
      await scanner.getByRole('status').filter({ hasText: 'Checking label scanner availability' }).waitFor()
      releaseCheck()
    } else if (availability === 'unconfigured') {
      await scanner.getByRole('status').filter({ hasText: 'AI service enabled' }).waitFor()
      await scanner.getByRole('button', { name: 'Enter food manually' }).click()
      await page.getByRole('dialog', { name: 'Custom food', exact: true }).waitFor()
    } else {
      await scanner.getByRole('status').filter({ hasText: 'Could not check' }).waitFor()
      recovered = true
      await scanner.getByRole('button', { name: 'Retry', exact: true }).click()
    }
    if (availability !== 'unconfigured') await scanner.getByRole('button', { name: 'Scan automatically', exact: true }).waitFor()
    await context.close()
  }
  assert.deepEqual(errors, [])
  console.log('Hero layout, nutrition totals, scanner availability/retry, reduced motion and mobile sign-out checks passed.')
} finally {
  await browser.close()
}
