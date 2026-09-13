/**
 * Authenticated screenshot helper for the SPA.
 *
 * Headless Chrome/Edge can't fill in a login form from the CLI, and the app is
 * session-cookie authenticated, so this drives the browser over the DevTools
 * Protocol instead: inject the session cookie, navigate, screenshot. Node 24's
 * built-in WebSocket means there are no dependencies to install.
 *
 * Usage:
 *   node scripts/shoot.mjs <url> <out.png> [width] [height] [sessionCookie]
 *
 * Get a session cookie with:
 *   curl -s -c jar.txt -H 'Content-Type: application/json' \
 *     -d '{"username":"...","password":"..."}' http://127.0.0.1:5000/login
 */
import { spawn } from 'node:child_process'
import { writeFileSync } from 'node:fs'
import { setTimeout as sleep } from 'node:timers/promises'

const [url, out, width = '1440', height = '900', sessionCookie] = process.argv.slice(2)

if (!url || !out) {
  console.error('usage: node scripts/shoot.mjs <url> <out.png> [width] [height] [sessionCookie]')
  process.exit(1)
}

const EDGE = 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'
const PORT = 9333

const browser = spawn(EDGE, [
  '--headless=new',
  '--disable-gpu',
  '--no-sandbox',
  `--remote-debugging-port=${PORT}`,
  `--window-size=${width},${height}`,
  '--user-data-dir=' + process.env.TEMP + '/neurallog-shoot-profile',
  'about:blank',
])
browser.on('error', (error) => {
  console.error('failed to launch browser:', error.message)
  process.exit(1)
})

/** The debug endpoint takes a moment to start listening. */
async function targets() {
  for (let attempt = 0; attempt < 50; attempt += 1) {
    try {
      const res = await fetch(`http://127.0.0.1:${PORT}/json/list`)
      const list = await res.json()
      const page = list.find((target) => target.type === 'page')
      if (page) return page
    } catch {
      /* not up yet */
    }
    await sleep(200)
  }
  throw new Error('DevTools endpoint never became ready')
}

const page = await targets()
const socket = new WebSocket(page.webSocketDebuggerUrl)
await new Promise((resolve, reject) => {
  socket.addEventListener('open', resolve, { once: true })
  socket.addEventListener('error', reject, { once: true })
})

let nextId = 1
const pending = new Map()

socket.addEventListener('message', (event) => {
  const message = JSON.parse(event.data)
  const resolver = pending.get(message.id)
  if (resolver) {
    pending.delete(message.id)
    resolver(message.result)
  }
})

function send(method, params = {}) {
  const id = nextId++
  socket.send(JSON.stringify({ id, method, params }))
  return new Promise((resolve) => pending.set(id, resolve))
}

await send('Page.enable')
await send('Network.enable')

if (sessionCookie) {
  const { hostname } = new URL(url)
  await send('Network.setCookie', {
    name: 'session',
    value: sessionCookie,
    domain: hostname,
    path: '/',
    httpOnly: true,
  })
}

await send('Page.navigate', { url })
// Let the bundle boot, queries resolve and charts animate in.
await sleep(3500)

const { data } = await send('Page.captureScreenshot', { format: 'png', captureBeyondViewport: true })
writeFileSync(out, Buffer.from(data, 'base64'))
console.log(`wrote ${out}`)

socket.close()
browser.kill()
process.exit(0)
