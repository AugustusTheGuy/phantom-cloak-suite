/* PhantomCloak Suite — Tier & Entitlement Gate (additive layer)
   Reads get_tier_info() from the Python bridge, sets the active tier on
   <body> so CSS can lock Pro-only controls in Core, and shows a lock
   overlay when the subscription/tier entitlement is not active.
   Fail-safe: if no bridge is present (e.g. opened in a plain browser),
   it does nothing rather than locking the user out. */
(function () {
  'use strict';
  var tries = 0, MAX = 40;

  function ready() {
    return window.pywebview && window.pywebview.api && window.pywebview.api.get_tier_info;
  }

  function boot() {
    if (!ready()) {
      if (tries++ < MAX) { setTimeout(boot, 150); }
      return;
    }
    Promise.resolve(window.pywebview.api.get_tier_info())
      .then(applyTier)
      .catch(function () { /* leave app usable if bridge errors */ });
  }

  function applyTier(info) {
    if (!info) return;
    document.body.setAttribute('data-tier', info.tier || 'core');
    if (info.unlocked) { removeLock(); } else { showLock(); }
  }

  function removeLock() {
    var el = document.getElementById('pc-entitlement-lock');
    if (el) el.remove();
  }

  function showLock() {
    if (document.getElementById('pc-entitlement-lock')) return;
    var o = document.createElement('div');
    o.id = 'pc-entitlement-lock';
    o.innerHTML =
      '<div class="pc-lock-card">' +
        '<div class="pc-lock-dot"></div>' +
        '<h2>Subscription required</h2>' +
        '<p>Your PhantomCloak subscription isn’t active on this device yet. ' +
        'Sign in or start a plan to unlock protection.</p>' +
        '<div class="pc-lock-actions">' +
          '<button class="pc-lock-btn" data-pc="signin">Sign in</button>' +
          '<button class="pc-lock-btn primary" data-pc="subscribe">Choose a plan</button>' +
        '</div>' +
        '<p class="pc-lock-note">Core &amp; Pro plans · cancel anytime · no renewal traps</p>' +
      '</div>';
    document.body.appendChild(o);
    var si = o.querySelector('[data-pc="signin"]');
    if (si) si.onclick = function () { if (window.showLogin) window.showLogin(); };
    // "Choose a plan" is intentionally a placeholder: the owner wires this to
    // the checkout URL once a payment processor is configured.
    var sub = o.querySelector('[data-pc="subscribe"]');
    if (sub) sub.onclick = function () {
      sub.textContent = 'Connect a checkout URL to enable';
      setTimeout(function () { sub.textContent = 'Choose a plan'; }, 2200);
    };
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else { boot(); }
})();
