# Hosting (free, professional) + grassroots campaign start

## Best free professional hosting (recommended order)

| Host | URL quality | Fit |
|------|-------------|-----|
| **1. Cloudflare Pages** | Custom domain free SSL, fast CDN, serious look | **Best free default** |
| **2. Vercel / Netlify** | `yoursite.vercel.app` or custom domain | Excellent for static landing |
| **3. GitHub Pages** | `user.github.io/pcs` or custom domain | Free, trustworthy for open builds |
| **4. Cloudflare Tunnel** to home | Custom domain → `localhost:8787` payments | For full checkout API without public VPS |

### Recommended production-looking setup ($0)

1. Register a clean domain (~$10/yr optional but highest trust): e.g. `getphantomcloak.com` or `phantomcloak.app`  
2. Cloudflare Pages: deploy folder  
   `PCS_Industrial_20260802/landing_v20260802/`  
3. Point DNS to Pages; enable HTTPS  
4. Payments API: run industrial shell on a $0 always-on option:  
   - Cloudflare Tunnel → `pcs_app_shell --serve-payments 8787` on Mac Mini, or  
   - Free tier Railway/Render/Fly for API only (env secrets for Stripe/wallets)

**Do not** use free random subdomains that look like phishing if you care about conversion.

### Local full stack (now)

```bash
cd ~/Desktop/PCS_Industrial_20260802
.venv/bin/python core_product/pcs_app_shell_v20260802.py --serve-payments 8787
# open http://127.0.0.1:8787/
```

---

## Pricing (from Pricing_Referral_Features_Report)

| | Monthly | Annual |
|--|---------|--------|
| **Core** | $11.99 | $59.88 ($4.99/mo) |
| **Pro** | $39 founder | $348 ($29/mo) |

Week-1 math: ~26 Pro sales at $39 ≈ $1,000.

---

## Payments (operational industrial module)

| Method | Status |
|--------|--------|
| BTC / ETH / SOL | Orders + tags + confirm_crypto (needs node/NOWPayments/BTCPay for live chain) |
| XMR | Private model — wallet RPC/processor required for real confirm |
| Card | Stripe PaymentIntent when `STRIPE_SECRET_KEY` set |
| Demo | `POST /api/confirm_demo` local mint only |

Env:

```bash
export STRIPE_SECRET_KEY=sk_live_or_test_...
export PCS_WALLET_BTC=bc1...
export PCS_WALLET_ETH=0x...
export PCS_WALLET_SOL=...
export PCS_WALLET_XMR=...
```

---

## Campaign ethics

Brand/founder voice only. **No fake customer sock accounts.**  
Individualized Core vs Pro angles; emphasize unique fail-closed preflight when true.

See `CAMPAIGN_POSTS_READY_v20260802.md` for copy ready to post.
