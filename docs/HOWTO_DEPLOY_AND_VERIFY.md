# Delphi Anti-Detection — How to Deploy Server Templates & Use Verification

## 1. How to Copy Server Templates to Your VPSes

### Step-by-step

1. **Choose a VPS provider** with good presence in your target country (Vultr, Hetzner, Linode, Oracle Cloud, etc.).
   - Recommended locations with clean IPs: Vancouver/Toronto, Singapore, Frankfurt, Hong Kong, Tallinn.

2. **Provision the VPS** (Ubuntu 22.04 or 24.04 recommended).

3. **Copy the template**:
   ```bash
   # From your Mac
   scp server/templates/sing-box-dubai-reality.json user@YOUR_VPS_IP:/tmp/config.json
   ```

4. **On the VPS**, install sing-box:
   ```bash
   # One-liner from official docs (or use the deploy.sh script)
   bash <(curl -fsSL https://sing-box.sagernet.org/deb-install.sh)
   ```

5. **Edit the config** on the VPS:
   ```bash
   sudo nano /etc/sing-box/config.json
   # Paste the contents of the template and replace:
   # - UUID / password
   # - private_key (generate with sing-box generate reality-keypair)
   # - short_id values
   ```

6. **Enable and start**:
   ```bash
   sudo systemctl enable --now sing-box
   sudo sing-box check -c /etc/sing-box/config.json
   sudo systemctl restart sing-box
   ```

7. **Firewall** (ufw example):
   ```bash
   sudo ufw allow 443/tcp
   sudo ufw allow 443/udp
   sudo ufw allow 22/tcp
   sudo ufw --force enable
   ```

8. **Test from your Mac** using the verification tools before trusting the exit for sensitive work.

**Pro tip**: Use different shortIDs and passwords per client. Rotate Reality private keys every 30-90 days.

## 2. What the Verification Script Accomplishes

Running `python scripts/verify/full_verification_suite.py` (or the individual checkers) does the following:

- **IP Leak Detection**: Queries multiple independent services (ipify, ipinfo, ipleak, ifconfig.me) to confirm your public IP matches the chosen exit location.
- **DNS Leak Detection**: Checks resolver paths. You should not see your real ISP's DNS servers.
- **WebRTC Check**: Guides you to browserleaks.com/webrtc to ensure no local LAN IPs are leaking.
- **Browser Fingerprint Validation**: Points you to creepjs.com, coveryourtracks.eff.org, etc., so you can verify that the Camoufox profile + sing-box Reality combination produces believable signals for a real resident of the target city.
- **Mimicry Quality Guidance**: Teaches you how to do basic traffic analysis to confirm the connection does not look like a VPN.

Run this suite:
- After first connecting to a new VPS
- After switching locations
- Periodically (weekly) as a health check
- After any major system update on macOS

If anything fails, do not use that exit for high-stakes work until fixed.

## 3. Recommended Workflow

1. Generate profiles: `python client/generate_profiles.py`
2. Deploy server config to VPS
3. On Mac: `./bin/delphi start` (or the rich dashboard)
4. Launch protected browser: `./bin/delphi launch-browser dubai`
5. Run verification: `python scripts/verify/full_verification_suite.py`
6. Use the rich dashboard for ongoing monitoring of the Top 30 techniques

This combination gives you extremely strong coverage of the full 300+ method list.