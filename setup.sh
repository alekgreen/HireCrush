#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-python3}"
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  if command -v python >/dev/null 2>&1; then
    PYTHON_BIN="python"
  else
    echo "Python not found. Install Python 3.10+ and re-run."
    exit 1
  fi
fi

run_cmd() {
  echo "+ $*"
  "$@"
}

run_cmd_maybe_sudo() {
  if command -v sudo >/dev/null 2>&1; then
    run_cmd sudo "$@"
  else
    run_cmd "$@"
  fi
}

detect_linux_pkg_manager() {
  if command -v apt-get >/dev/null 2>&1; then
    echo "apt"
    return
  fi
  if command -v dnf >/dev/null 2>&1; then
    echo "dnf"
    return
  fi
  if command -v yum >/dev/null 2>&1; then
    echo "yum"
    return
  fi
  if command -v pacman >/dev/null 2>&1; then
    echo "pacman"
    return
  fi
  if command -v zypper >/dev/null 2>&1; then
    echo "zypper"
    return
  fi
  echo "unknown"
}

ensure_venv() {
  if [[ ! -d ".venv" ]]; then
    run_cmd "$PYTHON_BIN" -m venv .venv
  fi
  run_cmd .venv/bin/pip install --upgrade pip
  run_cmd .venv/bin/pip install -r requirements.txt
}

is_wsl() {
  grep -qi microsoft /proc/version 2>/dev/null || grep -qi microsoft /proc/sys/kernel/osrelease 2>/dev/null
}

install_linux_keyring_backend() {
  local pkg_manager
  pkg_manager="$(detect_linux_pkg_manager)"
  case "$pkg_manager" in
    apt)
      run_cmd_maybe_sudo apt-get update
      run_cmd_maybe_sudo apt-get install -y dbus-user-session gnome-keyring libsecret-1-0 libsecret-1-dev
      ;;
    dnf)
      run_cmd_maybe_sudo dnf install -y dbus-daemon gnome-keyring libsecret libsecret-devel
      ;;
    yum)
      run_cmd_maybe_sudo yum install -y dbus-daemon gnome-keyring libsecret libsecret-devel
      ;;
    pacman)
      run_cmd_maybe_sudo pacman -S --noconfirm --needed dbus gnome-keyring libsecret
      ;;
    zypper)
      run_cmd_maybe_sudo zypper --non-interactive install dbus-1 gnome-keyring libsecret-1-0 libsecret-1-devel
      ;;
    *)
      echo "No supported Linux package manager found. Skipping system package install."
      ;;
  esac

  run_cmd .venv/bin/pip install --upgrade secretstorage jeepney
}

install_macos_keyring_backend() {
  run_cmd .venv/bin/pip install --upgrade pyobjc-framework-Cocoa pyobjc-framework-Security
}

install_windows_keyring_backend_hint() {
  cat <<'EOF'
Detected Windows shell environment.
For native Windows keyring support, run this from PowerShell/CMD:

  py -m venv .venv
  .\.venv\Scripts\pip install --upgrade pip
  .\.venv\Scripts\pip install -r requirements.txt
  .\.venv\Scripts\pip install --upgrade pywin32

Then start the app from the same environment.
EOF
}

verify_keyring_backend() {
  .venv/bin/python - <<'PY'
import keyring

backend = keyring.get_keyring()
priority = getattr(backend, "priority", 0)
module_name = getattr(getattr(backend, "__class__", None), "__module__", "")
print(f"keyring backend: {backend}")
print(f"backend priority: {priority}")

try:
    ok = float(priority) > 0
except Exception:
    ok = False

if ok and str(module_name).startswith("keyrings.alt"):
    print("keyrings.alt fallback backend is available (not OS-secure keychain storage).")
elif ok:
    print("Secure keyring backend is available.")
else:
    print("No secure keyring backend available yet.")
PY
}

main() {
  echo "Bootstrapping project environment..."
  ensure_venv

  local uname_out
  uname_out="$(uname -s || true)"
  case "$uname_out" in
    Linux*)
      if is_wsl; then
        cat <<'EOF'
WSL detected.
WSL often has no native secure keyring daemon by default.
This script will install Linux keyring dependencies, but you may still need
to start a desktop keyring session manually for persistent secure storage.
EOF
      fi
      install_linux_keyring_backend
      ;;
    Darwin*)
      install_macos_keyring_backend
      ;;
    CYGWIN*|MINGW*|MSYS*)
      install_windows_keyring_backend_hint
      ;;
    *)
      echo "Unknown OS (${uname_out}). Installed Python deps only."
      ;;
  esac

  echo
  echo "Verifying keyring backend..."
  verify_keyring_backend
  echo
  echo "Setup complete."
  echo "Next steps:"
  echo "  1) source .venv/bin/activate"
  echo "  2) flask --app app db-upgrade"
  echo "  3) python app.py"
}

main "$@"
