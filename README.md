# linux-wintermute — Arch Linux kernel package with agentns + memlog + provfs LSM

Parallel-install package; does not replace the stock `linux` package.
Boot entry sits alongside; pick at boot time.

## Build

```sh
cd ~/wintermute/wintermute-kernel/pkg
# downloads ~140 MB of sources, builds in ~/wintermute/wintermute-kernel/pkg/src/,
# takes ~30-90 min depending on the box
makepkg -s --skippgpcheck
```

`-s` auto-installs missing makedeps. The `--skippgpcheck` skips PGP
verification of the upstream tarball signature — Arch installs verify the
b2sum already, so this is only a convenience for first-time builds without
the kernel.org keys in your keyring.

If your wintermute checkout isn't at `~/wintermute/`, override the path:

```sh
WINTERMUTE=/path/to/wintermute makepkg -s --skippgpcheck
```

## Install

```sh
sudo pacman -U linux-wintermute-7.0.10.arch1-1-x86_64.pkg.tar.zst \
                linux-wintermute-headers-7.0.10.arch1-1-x86_64.pkg.tar.zst
```

This drops:
- `/boot/vmlinuz-linux-wintermute`
- `/boot/initramfs-linux-wintermute.img`
- `/usr/lib/modules/7.0.10-wintermute-arch1-1/`

If your boot loader is `systemd-boot`, mkinitcpio's install hook adds
`/boot/loader/entries/<machine-id>-linux-wintermute.conf` automatically.
If GRUB, run `sudo grub-mkconfig -o /boot/grub/grub.cfg`.

## Boot

Pick `Linux wintermute` (or similar) from the boot menu. The stock
`linux` package is still your default — wintermute kernel is opt-in
per boot until you decide it's stable enough to set as default.

## Verify after boot

```sh
uname -r                                # 7.0.10-wintermute-arch1-1 (or similar)
ls /proc/self/agent_session             # agentns: present
ls /dev/memlog                          # memlog: present (after `sudo modprobe memlog`)
cat /sys/kernel/security/lsm            # should include "provfs"

# run the per-feature smoke tests
bash ~/wintermute/memlog/tests/test_basic.sh
bash ~/wintermute/provfs/lsm/tests/test_basic.sh
sudo bash ~/wintermute/agentns/tests/test_inheritance.sh
sudo bash ~/wintermute/agentns/tests/test_budget_enforce.sh
```

## Roll back

Reboot, pick the stock `linux` entry. Optionally:

```sh
sudo pacman -R linux-wintermute linux-wintermute-headers
```

The stock kernel and its modules are untouched.

## What changed vs the stock `linux` PKGBUILD

- `pkgbase=linux-wintermute` (parallel install)
- `prepare()` additions: apply agentns patches 0001-0009; install
  agentns + memlog + provfs LSM new files; patch
  `drivers/char/{Kconfig,Makefile}` and `security/{Kconfig,Makefile}` to
  wire them in; enable `CONFIG_AGENT_NS=y`, `CONFIG_MEMLOG=m`,
  `CONFIG_SECURITY_PROVFS=y`
- `build()` drops `make htmldocs` (no texlive dep)
- Docs subpackage removed
