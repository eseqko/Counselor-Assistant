# Accessing Counselor Assistant from Your iPhone

This guide walks you through one-time setup so you can open the Counselor Assistant
from your iPhone's home screen, like a native app — without exposing anything to
the school network or the public internet.

We use **Tailscale**, a private VPN. It creates a direct, encrypted connection
between just your PC and your iPhone. IT can't see it, students can't find it,
and all student data stays on your PC (FERPA-safe).

---

## What you get

- One icon on your iPhone home screen labeled **Counselor**.
- Tap it → the app opens full-screen, no Safari address bar.
- Works anywhere you have internet (home, school, coffee shop), as long as
  Tailscale is on and your PC is running.

---

## One-time setup (about 10 minutes)

### 1. Install Tailscale on your PC
1. Go to <https://tailscale.com/download> and download for Windows.
2. Run the installer, then open Tailscale from the system tray.
3. Click **Log in** → sign in with a Google or Microsoft account you control
   (a personal account is fine; it does not need to be a school account).

### 2. Install Tailscale on your iPhone
1. Open the App Store, search for **Tailscale**, and install it.
2. Open Tailscale on your iPhone → **Log in** with the **same account** you
   used on the PC.
3. Allow the VPN profile when iOS prompts you.

### 3. Find your PC's Tailscale IP
1. On the PC, click the Tailscale icon in the system tray.
2. At the top you'll see an IP that looks like `100.101.102.103`
   (always starts with `100.`). Write it down.

### 4. Start Counselor Assistant
- Run `start.bat` on your PC the way you always do.
- The app auto-detects your Tailscale IP and binds **only** to the Tailscale
  interface — so the school LAN cannot see the port. The console prints
  something like:
  ```
  Tailscale detected. Server bound to: 100.101.102.103
  On this PC:   http://100.101.102.103:5000
  On iPhone:    http://100.101.102.103:5000 (via Tailscale)
  The school LAN cannot see this port.
  ```
- **On the PC, use the Tailscale URL** (not `127.0.0.1`) — just bookmark
  the address printed in the console.

### 5. Open it on your iPhone
1. Make sure Tailscale on your iPhone shows **Connected**.
2. In Safari (not Chrome — iOS only lets Safari install PWAs), go to
   `http://100.101.102.103:5000` (use your PC's actual Tailscale IP).
3. Log in the same way you do on your PC.

### 6. Add to Home Screen
1. Tap the **Share** icon (square with an up arrow) at the bottom of Safari.
2. Scroll down → tap **Add to Home Screen**.
3. Name it **Counselor** → tap **Add**.
4. Done — there's now a Counselor icon on your home screen.

Tap it any time. It launches full-screen, like a real app.

---

## Daily use

- Tailscale starts automatically on PC and phone; you don't need to do anything.
- If your phone can't reach the app, check:
  1. Tailscale on iPhone shows **Connected** (green).
  2. Your PC is on and Counselor Assistant is running (`start.bat`).

---

## Troubleshooting

**"Safari can't open the page"**
- Double-check the Tailscale IP you typed. It starts with `100.` and has four
  numbers separated by dots.
- On the PC, open `http://<your-tailscale-ip>:5000` in a browser — if that
  doesn't work, Counselor Assistant isn't running. Start it with `start.bat`.

**"IT warned me about the app listening on the network"**
- The app now binds **only to your Tailscale interface** (100.x.x.x) — it
  does NOT listen on the school LAN. If the console at startup says
  "Tailscale detected. Server bound to: 100.x.x.x", you're safe.
- If the console says "Tailscale not detected. Local-only mode.", Tailscale
  isn't running on the PC. Start it before launching the app.

**"I can reach it from the PC but not the phone"**
- Open the Tailscale app on your iPhone. If it says "Not Connected", tap the
  toggle to connect.
- On the PC: Windows Firewall is almost always the culprit — it treats the
  Tailscale virtual adapter as a separate network and blocks unsolicited
  inbound by default. **Fastest fix**: open PowerShell *as Administrator* and
  run:
  ```powershell
  New-NetFirewallRule -DisplayName "Counselor Assistant (Tailscale)" `
      -Direction Inbound -LocalPort 5000 -Protocol TCP -Action Allow `
      -InterfaceAlias "Tailscale"
  ```
  If that errors with "interface not found", list your adapters with
  `Get-NetAdapter | Where-Object Name -like "*Tailscale*"` and substitute the
  exact `Name` it prints. This rule only opens 5000 on the Tailscale adapter
  — the school LAN still can't see it (and the app's request guard also blocks
  anything that isn't a tailnet source IP, so this is defence in depth).
- **GUI alternative**: Windows Defender Firewall → Advanced Settings → Inbound
  Rules → New Rule → Port → TCP 5000. Choose **Private** networks only (not
  Public, not Domain). Name it "Counselor Assistant — Tailscale".
- **If you get a 403 on the phone:** your phone reached the server but came in
  on the LAN instead of through Tailscale (the app refuses non-tailnet sources
  by design — that's the FERPA promise). Confirm the iPhone's Tailscale toggle
  is on, then use the `100.x.x.x` URL, not the LAN `10.x.x.x` / `192.168.x.x`
  one.

**"Add to Home Screen doesn't show my icon"**
- You must use **Safari** on iOS. Chrome and Firefox on iPhone don't support
  Add-to-Home-Screen for PWAs.
- Force-quit Safari (swipe it closed from the app switcher) and try again.

**"It works at school but not at home"**
- Tailscale is connected on the phone but may be sleeping on the PC when the
  PC is locked. Open Tailscale's Windows settings and check **"Run on startup"**
  and **"Unattended mode"** (lets it stay connected when the PC is locked).

---

## Security notes

- **Only your tailnet can reach the server.** Tailscale's firewall blocks the
  port from the school LAN, Wi-Fi hotspots, and the public internet. Only
  devices signed into your Tailscale account can connect.
- **All data stays on your PC.** The phone just shows pages from the PC; no
  student data is stored on the phone.
- **30-minute auto-logout still applies** on the phone, same as desktop.
- **If you lose your phone:** open Tailscale's admin console
  (<https://login.tailscale.com/admin/machines>) and remove the device. The
  phone immediately loses access.

---

## Regenerating icons (optional)

The app ships with simple "CA" icons at `app/static/icons/`:
- `icon-192.png` (192×192) — Android/Chrome PWA
- `icon-512.png` (512×512) — high-res PWA
- `apple-touch-icon.png` (180×180) — iOS home screen

Replace them with your school's logo if you prefer. Keep the same filenames
and sizes.
