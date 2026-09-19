---
name: patch-firefox-shift-enter
description: Install, verify, or repair the Windows Firefox AutoConfig patch that makes address-bar Shift+Enter open in the current tab. Windows + WSL host only.
---

# Firefox Shift+Enter AutoConfig patch (Windows)

## 1. Locate the Firefox install

```bash
powershell.exe -NoProfile -Command "Get-Item 'C:\Program Files\Mozilla Firefox\firefox.exe' | Select-Object -ExpandProperty VersionInfo | Select-Object ProductVersion"
```

## 2. Check the installed patch package

```bash
ls -la /mnt/c/Users/$USER/AppData/Local/FirefoxShiftEnterPatch/
sha256sum /mnt/c/Users/$USER/AppData/Local/FirefoxShiftEnterPatch/autoconfig.js
```

## 3. Verify the AutoConfig files are in place

```bash
test -f "/mnt/c/Program Files/Mozilla Firefox/defaults/pref/autoconfig.js" && echo "autoconfig loader present"
test -f "/mnt/c/Program Files/Mozilla Firefox/firefox.cfg" && echo "firefox.cfg present"
```
