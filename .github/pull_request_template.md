## What this changes

<!-- What it does, and why it was worth doing. -->

## Decisions worth reviewing

<!--
The part that is hard to recover later. Anything you chose deliberately that a
reader would otherwise assume was arbitrary - a schema shape, a scoring rule, a
trade-off you took knowingly. If there is nothing, say so and delete this.
-->

## Risk

<!--
Be specific about blast radius rather than saying "low risk":
- Does it touch a migration, or write to a table holding real logs?
- Does it change an existing attribute score? (Say which, and by how much.)
- Does it change an API shape the Jinja app, static/js/app.js or the SPA consume?
-->

## Verification

- [ ] `python -m pytest` passes
- [ ] `npm run typecheck && npm run lint && npm run build` pass in `frontend/`
- [ ] `python scripts/check_migrations.py` passes (if migrations changed)
- [ ] Checked in a browser at desktop and 414px width (if UI changed)

<!--
Screenshots for UI changes. The DOM probe comparing documentElement.scrollWidth
against clientWidth catches horizontal overflow in seconds, and has caught it
twice now.
-->
