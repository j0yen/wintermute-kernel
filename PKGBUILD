# Maintainer: Joe Yen <jyen.tech@gmail.com>
# Derived from Jan Alexander Steffens (heftig)'s linux PKGBUILD,
# with agentns + memlog + provfs LSM patched in. Installs in parallel
# with the stock linux package; does not replace it.

pkgbase=linux-wintermute
pkgver=7.0.10.arch1
pkgrel=5
pkgdesc='Linux (wintermute: agentns + memlog + provfs LSM)'
url='https://github.com/j0yen/wintermute-kernel'
arch=(x86_64)
license=(GPL-2.0-only)
makedepends=(
  bc binutils cpio gettext glibc libelf libgcc openssl pahole perl python
  rust rust-bindgen rust-src tar xxhash xz zlib zstd
)
options=(!debug !strip)
_srcname=linux-${pkgver%.*}
_srctag=v${pkgver%.*}-${pkgver##*.}
source=(
  https://cdn.kernel.org/pub/linux/kernel/v${pkgver%%.*}.x/${_srcname}.tar.{xz,sign}
  https://github.com/archlinux/linux/releases/download/$_srctag/linux-$_srctag.patch.zst{,.sig}
)
source_x86_64=(config.x86_64)
validpgpkeys=(
  ABAF11C65A2970B130ABE3C479BE3E4300411886
  647F28654894E3BD457199BE38DBBDC86092693E
  83BC8889351B5DEBBB68416EB8AC08600F108CDF
)
b2sums=('08dc26e2247186fbfee32ee3251174f8a2e68c6ed6118c0713cb87bb66d427c85b6ae2367af053b158d9ad0d9aaf0846bdebddf84c30558fec89e68ba0dc0957'
        'SKIP'
        '0701e826f811a79123f89c0d034cb753d3a6237ee5e387c8c927efc1114dbeac6ef095e88eedecf18b9d69fcefa605b2425ffb119c5e40026e388464f75c350e'
        'SKIP')
b2sums_x86_64=('7cfb1d47ea2ea1568934f2c6765d5d095f521cd7ca5e141941bd27ce8f6859c16ebdcd2fc9760f4953cf31f52daa9dd50aecee1f7af771c77ddb70131e260a5c')
sha256sums=('094977eb62c20e3d1939fe81a92958a1f987f339446e532fa86963b2804e32dc'
            'SKIP'
            '5aa17c8f41de0cfe212cdbaf97be5cddf304f08bd558b6763c41611cd73c3698'
            'SKIP')

# Source dirs for our three changesets (absolute paths to the local repos).
# Override via env if your wintermute checkout lives elsewhere.
_WINTERMUTE="${WINTERMUTE:-$HOME/wintermute}"
_AGENTNS="$_WINTERMUTE/agentns"
_MEMLOG="$_WINTERMUTE/memlog"
_PROVFS_LSM="$_WINTERMUTE/provfs/lsm"

export KBUILD_BUILD_HOST=wintermute
export KBUILD_BUILD_USER=$pkgbase
export KBUILD_BUILD_TIMESTAMP="$(date -Ru${SOURCE_DATE_EPOCH:+d @$SOURCE_DATE_EPOCH})"

_apply_agentns() {
  echo "==> Installing agentns new files..."
  install -Dm644 "$_AGENTNS/kernel/agent_namespaces.c"             kernel/agent_namespaces.c
  install -Dm644 "$_AGENTNS/include/linux/agent_namespaces.h"      include/linux/agent_namespaces.h
  install -Dm644 "$_AGENTNS/include/uapi/linux/agent_namespaces.h" include/uapi/linux/agent_namespaces.h
  install -Dm644 "$_AGENTNS/include/trace/events/agent_ns.h"       include/trace/events/agent_ns.h
  # Inline-edit the rest of the kernel tree (replaces patches/0001-0009).
  # Idempotent — safe to re-run.
  "${srcdir}/../apply-agentns.py" "$PWD"
}

_apply_memlog() {
  echo "==> Installing memlog driver..."
  install -Dm644 "$_MEMLOG/driver/memlog.c"                  drivers/char/memlog/memlog.c
  install -Dm644 "$_MEMLOG/driver/Kconfig"                   drivers/char/memlog/Kconfig
  cat > drivers/char/memlog/Makefile <<'EOF'
obj-$(CONFIG_MEMLOG) += memlog.o
EOF
  install -Dm644 "$_MEMLOG/include/uapi/linux/memlog.h"      include/uapi/linux/memlog.h

  # Wire into drivers/char/{Kconfig,Makefile}.
  if ! grep -q 'memlog/Kconfig' drivers/char/Kconfig; then
    sed -i '/^endmenu/i source "drivers/char/memlog/Kconfig"' drivers/char/Kconfig
  fi
  if ! grep -q 'memlog/' drivers/char/Makefile; then
    echo 'obj-$(CONFIG_MEMLOG) += memlog/' >> drivers/char/Makefile
  fi
}

_apply_provfs_lsm() {
  echo "==> Installing provfs LSM..."
  install -Dm644 "$_PROVFS_LSM/provfs_lsm.c" security/provfs/provfs_lsm.c
  install -Dm644 "$_PROVFS_LSM/Kconfig"      security/provfs/Kconfig
  install -Dm644 "$_PROVFS_LSM/Makefile"     security/provfs/Makefile

  if ! grep -q 'provfs/Kconfig' security/Kconfig; then
    sed -i '/^endmenu/i source "security/provfs/Kconfig"' security/Kconfig
  fi
  if ! grep -q 'provfs/' security/Makefile; then
    echo 'obj-$(CONFIG_SECURITY_PROVFS) += provfs/' >> security/Makefile
  fi
}

prepare() {
  cd $_srcname

  echo "Setting version..."
  echo "-$pkgrel" > localversion.10-pkgrel
  echo "${pkgbase#linux}" > localversion.20-pkgname

  local src
  for src in "${source[@]}"; do
    src="${src%%::*}"
    src="${src##*/}"
    src="${src%.zst}"
    [[ $src = *.patch ]] || continue
    echo "Applying upstream patch $src..."
    patch -Np1 < "../$src"
  done

  # Wintermute additions.
  _apply_agentns
  _apply_memlog
  _apply_provfs_lsm

  echo "Setting config..."
  cp ../config.$CARCH .config
  # Enable our three configs.
  scripts/config --enable AGENT_NS
  scripts/config --module MEMLOG
  scripts/config --enable SECURITY_PROVFS
  # Stamp the localversion so /proc/version is unambiguous.
  yes "" | make olddefconfig

  make -s kernelrelease > version
  echo "Prepared $pkgbase version $(<version)"
}

build() {
  cd $_srcname
  make all
  make -C tools/bpf/bpftool vmlinux.h feature-clang-bpf-co-re=1
}

_package() {
  pkgdesc="The $pkgdesc kernel and modules"
  depends=(coreutils initramfs kmod)
  optdepends=(
    "$pkgbase-headers: headers and scripts for building modules"
    'linux-firmware: firmware images needed for some devices'
  )

  cd $_srcname
  local modulesdir="$pkgdir/usr/lib/modules/$(<version)"

  echo "Installing boot image..."
  install -Dm644 "$(make -s image_name)" "$modulesdir/vmlinuz"
  echo "$pkgbase" | install -Dm644 /dev/stdin "$modulesdir/pkgbase"

  echo "Installing modules..."
  ZSTD_CLEVEL=19 make INSTALL_MOD_PATH="$pkgdir/usr" INSTALL_MOD_STRIP=1 \
    DEPMOD=/doesnt/exist modules_install
  rm "$modulesdir"/build
}

_package-headers() {
  pkgdesc="Headers and scripts for building modules for the $pkgdesc kernel"
  depends=(binutils glibc libelf libgcc openssl pahole xxhash zlib zstd)
  provides=(LINUX-HEADERS)

  cd $_srcname
  local builddir="$pkgdir/usr/lib/modules/$(<version)/build"
  local karch=x86

  echo "Installing build files..."
  install -Dt "$builddir" -m644 .config Makefile Module.symvers System.map \
    localversion.* version vmlinux tools/bpf/bpftool/vmlinux.h
  install -Dt "$builddir/kernel" -m644 kernel/Makefile
  install -Dt "$builddir/arch/$karch" -m644 arch/$karch/Makefile
  cp -t "$builddir" -a scripts
  ln -srt "$builddir" "$builddir/scripts/gdb/vmlinux-gdb.py"

  if [[ $(scripts/config -s CONFIG_HAVE_STACK_VALIDATION) = y ]]; then
    install -Dt "$builddir/tools/objtool" tools/objtool/objtool
  fi
  if [[ $(scripts/config -s CONFIG_DEBUG_INFO_BTF_MODULES) = y ]]; then
    install -Dt "$builddir/tools/bpf/resolve_btfids" tools/bpf/resolve_btfids/resolve_btfids
  fi

  echo "Installing headers..."
  cp -t "$builddir" -a include
  cp -t "$builddir/arch/$karch" -a arch/$karch/include
  install -Dt "$builddir/arch/$karch/kernel" -m644 arch/$karch/kernel/asm-offsets.s
  install -Dt "$builddir/drivers/md" -m644 drivers/md/*.h
  install -Dt "$builddir/net/mac80211" -m644 net/mac80211/*.h
  install -Dt "$builddir/drivers/media/i2c" -m644 drivers/media/i2c/msp3400-driver.h
  install -Dt "$builddir/drivers/media/usb/dvb-usb" -m644 drivers/media/usb/dvb-usb/*.h
  install -Dt "$builddir/drivers/media/dvb-frontends" -m644 drivers/media/dvb-frontends/*.h
  install -Dt "$builddir/drivers/media/tuners" -m644 drivers/media/tuners/*.h
  install -Dt "$builddir/drivers/iio/common/hid-sensors" -m644 drivers/iio/common/hid-sensors/*.h

  echo "Installing Kconfig files..."
  find . -name 'Kconfig*' -exec install -Dm644 {} "$builddir/{}" \;

  if [[ $(scripts/config -s CONFIG_RUST) = y ]]; then
    install -Dt "$builddir/rust" -m644 rust/*.rmeta
    install -Dt "$builddir/rust" rust/*.so
  fi

  echo "Installing unstripped VDSO..."
  make INSTALL_MOD_PATH="$pkgdir/usr" vdso_install link=

  echo "Removing unneeded architectures..."
  local arch
  for arch in "$builddir"/arch/*/; do
    [[ $arch = */$karch/ ]] && continue
    rm -r "$arch"
  done
  rm -r "$builddir/Documentation"
  find -L "$builddir" -type l -printf 'Removing %P\n' -delete
  find "$builddir" -type f -name '*.o' -printf 'Removing %P\n' -delete

  local file
  while read -rd '' file; do
    case "$(file -Sib "$file")" in
      application/x-sharedlib\;*)      strip -v $STRIP_SHARED "$file" ;;
      application/x-archive\;*)        strip -v $STRIP_STATIC "$file" ;;
      application/x-executable\;*)     strip -v $STRIP_BINARIES "$file" ;;
      application/x-pie-executable\;*) strip -v $STRIP_SHARED "$file" ;;
    esac
  done < <(find "$builddir" -type f -perm -u+x ! -name vmlinux -print0)
  strip -v $STRIP_STATIC "$builddir/vmlinux"

  mkdir -p "$pkgdir/usr/src"
  ln -sr "$builddir" "$pkgdir/usr/src/$pkgbase"
}

pkgname=(
  "$pkgbase"
  "$pkgbase-headers"
)
for _p in "${pkgname[@]}"; do
  eval "package_$_p() {
    $(declare -f "_package${_p#$pkgbase}")
    _package${_p#$pkgbase}
  }"
done

# vim:set ts=8 sts=2 sw=2 et:
