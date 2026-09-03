# Recall

An AI study assistant that turns your own notes into a spaced-repetition
practice loop. Built to the Apple design language, against the
[iPhone Air page](https://www.apple.com/ma/iphone-air/) as the visual reference.

![the landing page](docs/screens/landing.png)

## Try it

Two processes. The API first, because the web app calls it.

```bash
# terminal 1 — API on :8100
cd api
uv venv --python 3.12 && uv pip install -r requirements.txt
cp .env.example .env      # then put a real SESSION_SECRET in it:
                          # python -c "import secrets; print(secrets.token_urlsafe(48))"
.venv/bin/python -m app.seed          # creates the demo account
.venv/bin/python -m uvicorn app.main:app --port 8100

# terminal 2 — web on :3100
cd web
pnpm install
cp .env.example .env.local
pnpm dev --port 3100
```

Then open **http://localhost:3100** and sign in:

| | |
|---|---|
| Email | `demo@recall.study` |
| Password | `study-out-loud-2026` |

Seeded by [`api/app/seed.py`](api/app/seed.py), which is idempotent — running it
again resets that password rather than failing.

## What works today

| | |
|---|---|
| Landing page | the reference page's grammar: two-tone product name, 40px/400 claims, grey lead copy with ink emphasis, one dark band |
| Auth | registration, login, logout, `/auth/me` — argon2id hashing, signed HttpOnly session cookies, server-side session records |
| Design system | 76 assertions that the CSS still matches the specification |
| Tests | 15 auth tests, all passing |

`/library`, `/chat` and `/review` are styled placeholders that name the pull
request which builds them. See [`docs/roadmap.md`](docs/roadmap.md).

## Design

The visual reference is the iPhone Air product page.
[`docs/design-language.md`](docs/design-language.md) is the token specification;
[`docs/design-divergences.md`](docs/design-divergences.md) records the four
places the live page contradicts it — chrome carrying a shadow, 40px headings at
weight 400 rather than 600, two-tone body copy, and a white top bar instead of
black. The code follows the live page and says so.

`pnpm test:tokens` parses the specification's front matter and fails if the CSS
drifts from it, including any hex literal outside the token layer.

## Security notes

- **argon2id**, not bcrypt. bcrypt silently truncates at 72 bytes, which turns a
  long passphrase into a shorter one without telling anyone. There is a test
  proving argon2 does not.
- **Sessions are server-side rows**; the cookie carries only a signed row id.
  That is what makes logout real — deleting the row ends the session, where a
  self-contained token stays valid until it expires no matter what the server
  thinks. There is a test that a copied cookie stops working after logout.
- **HttpOnly**, so an XSS bug cannot read the session. This is why the token is
  not in `localStorage`.
- **Login failures are indistinguishable.** A wrong password and an unknown
  address return the same status and the same body, so the form is not an
  account-enumeration oracle. There is a test asserting the two responses are
  byte-identical.
- **`SESSION_SECRET` has no default.** A signing key with a default is a signing
  key everyone knows, and every cookie the service ever issued would be
  forgeable.

## Tests

```bash
cd api && .venv/bin/python -m pytest      # 15 passed
cd web && pnpm test:tokens                # 76 checks
cd web && pnpm build                      # TypeScript strict, no errors
```

---

Author: **Oussama Ezitouni**
