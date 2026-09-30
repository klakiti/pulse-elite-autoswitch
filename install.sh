#!/usr/bin/env bash
# Install the versioned GitHub release. Run as your desktop user, not with sudo.
set -euo pipefail

main() {
    local version=0.1.4
    local base="https://github.com/klakiti/pulse-elite-autoswitch/releases/download/v${version}"
    local desktop=true download_only=false arg stage package cleanup
    for arg in "$@"; do
        case "$arg" in
            --cli) desktop=false ;;
            --download-only) download_only=true ;;
            --help|-h)
                printf 'Usage: bash install.sh [--cli] [--download-only]\nInstalls the desktop UI and CLI by default. Requires Ubuntu 22.04+, Debian 12+, or a compatible distribution with PipeWire.\n'
                return ;;
            *) printf 'Unknown option: %s\n' "$arg" >&2; return 2 ;;
        esac
    done
    for arg in curl sha256sum dpkg apt-get python3; do
        command -v "$arg" >/dev/null || { printf 'Required command missing: %s\n' "$arg" >&2; return 1; }
    done
    python3 -c 'import sys; sys.exit(sys.version_info < (3, 10))' || {
        printf 'Python 3.10 or newer is required.\n' >&2; return 1;
    }
    if ! "$download_only"; then
        if (( EUID == 0 )); then
            printf 'Run this installer as your desktop user without sudo; it requests sudo when needed.\n' >&2
            return 1
        fi
        command -v sudo >/dev/null || { printf 'sudo is required to install packages.\n' >&2; return 1; }
        systemctl --user show-environment >/dev/null || {
            printf 'Run from a terminal inside your logged-in desktop session.\n' >&2; return 1;
        }
    fi
    stage=$(mktemp -d)
    printf -v cleanup 'rm -rf -- %q' "$stage"
    trap "$cleanup" EXIT
    # apt's download user needs to read these non-sensitive release artifacts.
    chmod 755 "$stage"
    local packages=("pulse-elite-autoswitch_${version}_all.deb")
    if "$desktop"; then packages+=("pulse-elite-autoswitch-desktop_${version}_all.deb"); fi
    curl --fail --silent --show-error --location --retry 3 "$base/SHA256SUMS" -o "$stage/SHA256SUMS"
    local paths=()
    for package in "${packages[@]}"; do
        printf 'Downloading %s\n' "$package"
        curl --fail --silent --show-error --location --retry 3 "$base/$package" -o "$stage/$package"
        # Verify exactly the requested filenames, ignoring other manifest entries.
        python3 - "$stage/SHA256SUMS" "$package" > "$stage/checksum" <<'PY'
import pathlib, re, sys
lines = pathlib.Path(sys.argv[1]).read_text().splitlines()
matches = [line for line in lines if re.fullmatch(r'[0-9a-f]{64}  ' + re.escape(sys.argv[2]), line)]
if len(matches) != 1:
    raise SystemExit('Release checksum missing or ambiguous: ' + sys.argv[2])
print(matches[0])
PY
        (cd "$stage" && sha256sum --check checksum)
        chmod 644 "$stage/$package"
        paths+=("$stage/$package")
    done
    if "$download_only"; then
        for package in "${packages[@]}"; do cp -- "$stage/$package" ./; done
        printf 'Verified packages downloaded to %s\n' "$PWD"
    else
        local was_active=false
        if systemctl --user is-active --quiet pulse-elite-autoswitch.service; then was_active=true; fi
        sudo apt-get update
        sudo apt-get install -y "${paths[@]}"
        systemctl --user daemon-reload
        if "$was_active"; then systemctl --user restart pulse-elite-autoswitch.service; fi
        if "$desktop"; then
            printf '\nInstalled. Open Pulse Elite AutoSwitch from your applications menu, choose a fallback output, and click Enable.\n'
        else
            printf '\nInstalled. Run pulse-elite-autoswitch configure, then pulse-elite-autoswitch start.\n'
        fi
    fi
    rm -rf -- "$stage"
    trap - EXIT
}

main "$@"
