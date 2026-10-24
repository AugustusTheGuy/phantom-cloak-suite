# Knowledge base: privacy / VPN command-center UX & security

Ingested for PhantomCloak product decisions (Firecrawl search + industry patterns).  
Not legal advice. Re-run research when shipping major UI changes.

## Kill switch (product requirement)

- Automatically blocks clearnet if tunnel dies so real IP does not leak mid-session.  
- Best UX: **on with connect, off with disconnect** (auto mode).  
- Advanced users may want always-on firewall mode — label it clearly (“Paranoid”).  
- macOS implementations commonly use **pf**; store rule files in user-private paths, not world-readable `/tmp`.

## Desktop VPN UX patterns

- One primary CTA; location + protocol status always visible.  
- Favorites / last-used servers.  
- Multi-hop or Double Onion as advanced, not default.  
- Preferences for language, kill switch, auto-connect at login.  
- Linux/macOS GUI parity with mobile mental model (Connect first).

## Security hygiene for local privacy apps

- State dirs `0700`, secrets `0600`.  
- Prefer Argon2id/scrypt/bcrypt over single SHA-256 for password vaults.  
- No `shell=True` with user strings.  
- Explicit sudo only with least privilege; document why.  
- Honest marketing: raise bar against casual tracking; no absolute “undetectable” claims.

## Sources (search session 2026-07-22)

See `~/Desktop/PhantomCloak/.firecrawl/search-*.json` for full result payloads  
(Security.org, Tom’s Guide, PrivacyGuides discussions, Mullvad/Surfshark coverage, pf kill-switch guides).
