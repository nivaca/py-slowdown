#!/bin/sh
# py-slowdown @VERSION@: the installer for Linux (x86_64), made by tools/bundle-run.py.
#
#     sh py-slowdown-@VERSION@-linux-x86_64.run            install (it asks first)
#     sh py-slowdown-@VERSION@-linux-x86_64.run --yes      install without asking
#     sh py-slowdown-@VERSION@-linux-x86_64.run --check    only check the file
#
# For you alone, it installs py-slowdown (with its own Python, Qt, FFmpeg,
# Rubber Band and PortAudio, as the AppImage) in ~/.local/share/py-slowdown/app,
# the command py-slowdown in ~/.local/bin, an entry in the menu of applications
# and its icons. Run as root (sudo), it installs it for everyone: /opt/py-slowdown,
# /usr/local/bin and /usr/local/share. It needs a Linux with glibc 2.34 or later.
# The uninstaller is uninstall.sh, in the folder of the program; the settings
# and the bookmarks are never touched.
#
# py-slowdown: Copyright (C) 2026 Nicolas Vaughan <nicolasvaughan@proton.me>
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

VERSION=@VERSION@
PAYLOAD_LINE=@PAYLOAD_LINE@
PAYLOAD_SHA256=@PAYLOAD_SHA256@
NAME=py-slowdown
SELF=$0

say() { printf '%s\n' "$*"; }
die() { printf 'py-slowdown installer: %s\n' "$*" >&2; exit 1; }

usage() {
    sed -n '2,14s/^# \{0,1\}//p' "$SELF"
}

YES=0
CHECK=0
for arg in "$@"; do
    case $arg in
        -y | --yes) YES=1 ;;
        --check) CHECK=1 ;;
        -h | --help) usage; exit 0 ;;
        *) die "unknown option: $arg (see --help)" ;;
    esac
done

# El contenido: lo que sigue a la línea PAYLOAD_LINE, comprobado con su suma
payload() { tail -n "+$PAYLOAD_LINE" "$SELF"; }
command -v sha256sum >/dev/null 2>&1 || die "sha256sum is needed"
found=$(payload | sha256sum | cut -d' ' -f1)
[ "$found" = "$PAYLOAD_SHA256" ] || die "this file is damaged (incomplete download?): download it again"
if [ "$CHECK" = 1 ]; then
    say "py-slowdown $VERSION: the installer is whole."
    exit 0
fi

[ "$(uname -m)" = x86_64 ] || die "this installer is for x86_64 computers"

if [ "$(id -u)" = 0 ]; then
    APPDIR=/opt/$NAME
    BIN=/usr/local/bin
    SHARE=/usr/local/share
    WHO="for everyone"
    PARENT=""
else
    DATA=${XDG_DATA_HOME:-$HOME/.local/share}
    APPDIR=$DATA/$NAME/app
    BIN=$HOME/.local/bin
    SHARE=$DATA
    WHO="for you ($(id -un))"
    PARENT=$DATA/$NAME  # (se quita al desinstalar solo si queda vacía: allí están los marcadores)
fi

say "py-slowdown $VERSION will be installed $WHO:"
say "  the program:  $APPDIR"
say "  the command:  $BIN/$NAME"
say "  the menu entry and the icons, in $SHARE"
if [ "$YES" = 0 ]; then
    printf 'Install it? [y/N] '
    read -r answer || answer=
    case $answer in
        y | Y | yes | s | S | si | sí) ;;
        *) say "Nothing done."; exit 1 ;;
    esac
fi

# Lo de una versión anterior se quita antes (con su propio desinstalador)
if [ -x "$APPDIR/uninstall.sh" ]; then
    "$APPDIR/uninstall.sh" --yes --quiet || true
fi

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
payload | tar -xzf - -C "$tmp"
mkdir -p "$(dirname "$APPDIR")"
rm -rf "$APPDIR"
mv "$tmp/app" "$APPDIR"

# Lo que se instala fuera de la carpeta del programa, para el desinstalador
made="$APPDIR/installed-files"
: > "$made"
put() {  # put SOURCE TARGET: copy, and remember it
    mkdir -p "$(dirname "$2")"
    cp -f "$1" "$2"
    printf '%s\n' "$2" >> "$made"
}

mkdir -p "$BIN"
cat > "$tmp/launcher" <<LAUNCHER
#!/bin/sh
# py-slowdown, installed in $APPDIR
exec "$APPDIR/AppRun" "\$@"
LAUNCHER
chmod 755 "$tmp/launcher"
put "$tmp/launcher" "$BIN/$NAME"
chmod 755 "$BIN/$NAME"

sed "s|^Exec=.*|Exec=\"$BIN/$NAME\" %f|" "$APPDIR/$NAME.desktop" > "$tmp/$NAME.desktop"
put "$tmp/$NAME.desktop" "$SHARE/applications/$NAME.desktop"
for icon in "$APPDIR"/usr/share/icons/hicolor/*/apps/$NAME.*; do
    size=$(basename "$(dirname "$(dirname "$icon")")")
    put "$icon" "$SHARE/icons/hicolor/$size/apps/$(basename "$icon")"
done
mime="$APPDIR/usr/share/mime/packages/$NAME.xml"
[ -f "$mime" ] && put "$mime" "$SHARE/mime/packages/$NAME.xml"
for page in "$APPDIR"/man/*.1 "$APPDIR"/man/*/*.1; do
    [ -f "$page" ] || continue
    lang=$(basename "$(dirname "$page")")
    case $lang in man) folder=man1 ;; *) folder=$lang/man1 ;; esac
    put "$page" "$SHARE/man/$folder/$NAME.1"
done
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database -q "$SHARE/applications" 2>/dev/null || true
command -v gtk-update-icon-cache >/dev/null 2>&1 && gtk-update-icon-cache -q -t "$SHARE/icons/hicolor" 2>/dev/null || true
command -v update-mime-database >/dev/null 2>&1 && update-mime-database "$SHARE/mime" >/dev/null 2>&1 || true

cat > "$APPDIR/uninstall.sh" <<UNINSTALL
#!/bin/sh
# Removes py-slowdown $VERSION, installed in $APPDIR by its installer. The settings
# and the bookmarks are kept.
quiet=0; yes=0
for arg in "\$@"; do case \$arg in --yes) yes=1 ;; --quiet) quiet=1 ;; esac; done
if [ "\$yes" = 0 ]; then
    printf 'Remove py-slowdown from $APPDIR? [y/N] '
    read -r answer || answer=
    case \$answer in y | Y | yes | s | S | si | sí) ;; *) echo "Nothing done."; exit 1 ;; esac
fi
while IFS= read -r file; do rm -f "\$file"; done < "$made"
rm -rf "$APPDIR"
[ -z "$PARENT" ] || rmdir "$PARENT" 2>/dev/null || true
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database -q "$SHARE/applications" 2>/dev/null || true
command -v update-mime-database >/dev/null 2>&1 && update-mime-database "$SHARE/mime" >/dev/null 2>&1 || true
[ "\$quiet" = 1 ] || echo "py-slowdown was removed (its settings and bookmarks were kept)."
UNINSTALL
chmod 755 "$APPDIR/uninstall.sh"

say "Installed. Run it from the menu of applications, or with: $NAME [FILE]"
case ":$PATH:" in
    *":$BIN:"*) ;;
    *) say "($BIN is not on your PATH: add it, or run $BIN/$NAME)" ;;
esac
say "To remove it: $APPDIR/uninstall.sh"
exit 0
