#!/usr/bin/env bash
# Compile the Tailwind + DaisyUI stylesheet and vendor it (no CDN at runtime —
# the browser is inside the no-egress story too). Requires node; installs the
# toolchain into a throwaway dir, never into the repo.
set -e
cd "$(dirname "$0")/.."
BUILD_DIR="${TMPDIR:-/tmp}/labelcheck-twbuild"
mkdir -p "$BUILD_DIR"
cd "$BUILD_DIR"
[ -d node_modules/daisyui ] || {
  npm init -y >/dev/null 2>&1
  npm i -D tailwindcss @tailwindcss/cli daisyui
}
cd - >/dev/null
# the CSS import resolves relative to the input file — link the toolchain in
ln -sfn "$BUILD_DIR/node_modules" api/web/node_modules
"$BUILD_DIR/node_modules/.bin/tailwindcss" \
  -i api/web/tailwind.input.css \
  -o api/web/vendor/tailwind-daisyui.css --minify
rm api/web/node_modules
echo "built: api/web/vendor/tailwind-daisyui.css ($(du -h api/web/vendor/tailwind-daisyui.css | cut -f1))"
