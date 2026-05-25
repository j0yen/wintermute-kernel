#!/usr/bin/env python3
"""Apply the agentns vendor changes to a Linux source tree (in-place edits).

Replaces the patches/0001-0009 series with idempotent text insertions
anchored on unique strings. Safer against context drift in the surrounding
kernel sources than unified diffs.

Usage:
    apply-agentns.py <linux_source_root>

Exits 0 on success, non-zero on any failure to locate an anchor.
"""

import re
import sys
from pathlib import Path


def edit(path: Path, *, after: str, insert: str, skip_if: str) -> None:
    """Insert `insert` immediately after the first line matching the regex
    `after`. No-op if `skip_if` already appears anywhere in the file."""
    text = path.read_text()
    if skip_if in text:
        print(f"    SKIP  {path.name} (already applied)")
        return
    pattern = re.compile(rf"({re.escape(after)})", re.MULTILINE)
    m = pattern.search(text)
    if not m:
        raise SystemExit(f"FAIL: anchor not found in {path}:\n  {after!r}")
    end = m.end()
    # Move to end of the matched line (insert AFTER the whole anchor line)
    nl = text.find("\n", end)
    if nl < 0:
        nl = len(text)
    new = text[: nl + 1] + insert + text[nl + 1:]
    path.write_text(new)
    print(f"    EDIT  {path.name}")


def replace_once(path: Path, *, old: str, new: str, skip_if: str = None) -> None:
    """Replace exactly one occurrence of `old` with `new`. Idempotent if
    `skip_if` (defaults to `new`) is already in the file."""
    if skip_if is None:
        skip_if = new
    text = path.read_text()
    if skip_if in text:
        print(f"    SKIP  {path.name} (already applied)")
        return
    if old not in text:
        raise SystemExit(f"FAIL: replace anchor not found in {path}:\n  {old!r}")
    if text.count(old) > 1:
        raise SystemExit(f"FAIL: replace anchor not unique in {path}: {old!r}")
    path.write_text(text.replace(old, new, 1))
    print(f"    EDIT  {path.name}")


def main(root: Path) -> None:
    print(f"==> Applying agentns inline edits to {root}")

    # 0001 — CLONE_NEWAGENT bit
    edit(
        root / "include/uapi/linux/sched.h",
        after="#define CLONE_IO\t\t0x80000000",
        insert="\n#define CLONE_NEWAGENT\t\t0x00000100\t/* New agent namespace (wintermute vendor) */\n",
        skip_if="CLONE_NEWAGENT",
    )

    # 0002 — nsproxy forward decl + field + #include + init + copy + free
    edit(
        root / "include/linux/nsproxy.h",
        after="struct fs_struct;",
        insert="struct agent_namespace;\n",
        skip_if="struct agent_namespace;",
    )
    edit(
        root / "include/linux/nsproxy.h",
        after="\tstruct cgroup_namespace *cgroup_ns;",
        insert="#ifdef CONFIG_AGENT_NS\n\tstruct agent_namespace *agent_ns;\n#endif\n",
        skip_if="agent_namespace *agent_ns",
    )
    edit(
        root / "kernel/nsproxy.c",
        after="#include <linux/perf_event.h>",
        insert="#include <linux/agent_namespaces.h>\n",
        skip_if="linux/agent_namespaces.h",
    )
    edit(
        root / "kernel/nsproxy.c",
        after="\t.cgroup_ns\t\t= &init_cgroup_ns,",
        insert="#ifdef CONFIG_AGENT_NS\n\t.agent_ns\t\t= &init_agent_ns,\n#endif\n",
        skip_if=".agent_ns\t\t= &init_agent_ns",
    )
    # In create_new_namespaces, insert copy_agent_ns just before `return new_nsp;`
    # at the end of the success path. Then add out_agent label between the
    # `return` and `out_time:`.
    replace_once(
        root / "kernel/nsproxy.c",
        old="\tnew_nsp->time_ns = get_time_ns(tsk->nsproxy->time_ns);\n\n\treturn new_nsp;\n",
        new="\tnew_nsp->time_ns = get_time_ns(tsk->nsproxy->time_ns);\n\n"
            "#ifdef CONFIG_AGENT_NS\n"
            "\tnew_nsp->agent_ns = copy_agent_ns(flags, user_ns,\n"
            "\t\t\t\t\t  tsk->nsproxy ? tsk->nsproxy->agent_ns\n"
            "\t\t\t\t\t\t       : &init_agent_ns);\n"
            "\tif (IS_ERR(new_nsp->agent_ns)) {\n"
            "\t\terr = PTR_ERR(new_nsp->agent_ns);\n"
            "\t\tgoto out_agent;\n"
            "\t}\n"
            "#endif\n\n"
            "\treturn new_nsp;\n",
        skip_if="copy_agent_ns",
    )
    replace_once(
        root / "kernel/nsproxy.c",
        old="out_time:\n\tput_net(new_nsp->net_ns);\n",
        new="#ifdef CONFIG_AGENT_NS\nout_agent:\n\tput_time_ns(new_nsp->time_ns);\n#endif\n"
            "out_time:\n\tput_net(new_nsp->net_ns);\n",
        skip_if="out_agent:",
    )
    replace_once(
        root / "kernel/nsproxy.c",
        old="CLONE_NEWCGROUP | CLONE_NEWTIME)))) {",
        new="CLONE_NEWCGROUP | CLONE_NEWTIME | CLONE_NEWAGENT)))) {",
        skip_if="CLONE_NEWAGENT)))) {",
    )
    edit(
        root / "kernel/nsproxy.c",
        after="\tput_cgroup_ns(ns->cgroup_ns);",
        insert="#ifdef CONFIG_AGENT_NS\n\tput_agent_ns(ns->agent_ns);\n#endif\n",
        skip_if="put_agent_ns(ns->agent_ns)",
    )

    # 0003 — fork: count + include
    edit(
        root / "kernel/fork.c",
        after="#include <linux/stackprotector.h>",
        insert="#include <linux/agent_namespaces.h>\n",
        skip_if="linux/agent_namespaces.h",
    )
    # copy_process: insert agent_ns_count_fork() right after the
    # security_task_alloc()/copy_namespaces() success path. The original
    # patch placed it after a `if (retval) goto bad_fork_cleanup_namespaces;`
    # block and before the copy_thread call.
    replace_once(
        root / "kernel/fork.c",
        old="\tretval = copy_thread(p, args);\n\tif (retval)\n\t\tgoto bad_fork_cleanup_io;\n",
        new="\tagent_ns_count_fork();\n\n"
            "\tretval = copy_thread(p, args);\n\tif (retval)\n\t\tgoto bad_fork_cleanup_io;\n",
        skip_if="agent_ns_count_fork()",
    )

    # 0004 — exit: include + task_exit hook
    edit(
        root / "kernel/exit.c",
        after="#include <linux/rethook.h>",
        insert="#include <linux/agent_namespaces.h>\n",
        skip_if="linux/agent_namespaces.h",
    )
    replace_once(
        root / "kernel/exit.c",
        old="\texit_signals(tsk);  /* sets PF_EXITING */\n",
        new="\texit_signals(tsk);  /* sets PF_EXITING */\n\n\tagent_ns_task_exit(tsk);\n",
        skip_if="agent_ns_task_exit(tsk)",
    )

    # 0005 — sys.c: includes + PR_AGENT_* dispatch
    edit(
        root / "kernel/sys.c",
        after="#include <asm/io.h>",
        insert="#include <linux/agent_namespaces.h>\n#include <uapi/linux/agent_namespaces.h>\n",
        skip_if="linux/agent_namespaces.h",
    )
    replace_once(
        root / "kernel/sys.c",
        old="\tunsigned char comm[sizeof(me->comm)];\n\tlong error;\n",
        new="\tunsigned char comm[sizeof(me->comm)];\n\tlong error;\n\n"
            "\tif (option >= PR_AGENT_BASE && option <= PR_AGENT_BASE + 31) {\n"
            "#ifdef CONFIG_AGENT_NS\n"
            "\t\treturn agent_ns_prctl(me, option, arg2, arg3, arg4, arg5);\n"
            "#else\n"
            "\t\treturn -EINVAL;\n"
            "#endif\n"
            "\t}\n",
        skip_if="agent_ns_prctl(me",
    )

    # 0006 — fs/proc/base.c: /proc/$PID/agent_* files
    edit(
        root / "fs/proc/base.c",
        after="#include <linux/resctrl.h>",
        insert="#include <linux/agent_namespaces.h>\n",
        skip_if="linux/agent_namespaces.h",
    )
    # Insert the three proc_pid_agent_* show functions just before
    # the CONFIG_LIVEPATCH block (a well-anchored line in base.c).
    proc_show_funcs = '''#ifdef CONFIG_AGENT_NS
static int proc_pid_agent_session(struct seq_file *m, struct pid_namespace *ns,
				  struct pid *pid, struct task_struct *task)
{
	m->private = task;
	return agent_ns_proc_id_show(m, NULL);
}

static int proc_pid_agent_intent(struct seq_file *m, struct pid_namespace *ns,
				 struct pid *pid, struct task_struct *task)
{
	m->private = task;
	return agent_ns_proc_intent_show(m, NULL);
}

static int proc_pid_agent_counters(struct seq_file *m, struct pid_namespace *ns,
				   struct pid *pid, struct task_struct *task)
{
	m->private = task;
	return agent_ns_proc_counters_show(m, NULL);
}
#endif

'''
    replace_once(
        root / "fs/proc/base.c",
        old="#ifdef CONFIG_LIVEPATCH\nstatic int proc_pid_patch_state",
        new=proc_show_funcs + "#ifdef CONFIG_LIVEPATCH\nstatic int proc_pid_patch_state",
        skip_if="proc_pid_agent_session",
    )
    # Insert the three pid_entry rows in tgid_base_stuff. Anchor on the
    # LIVEPATCH ONE() entry which is stable across kernel versions.
    pid_entries = '''#ifdef CONFIG_AGENT_NS
	ONE("agent_session", S_IRUGO, proc_pid_agent_session),
	ONE("agent_intent",  S_IRUGO, proc_pid_agent_intent),
	ONE("agent_counters",S_IRUGO, proc_pid_agent_counters),
#endif
'''
    # The patch shows agent rows BEFORE STACKLEAK/KSTACK_ERASE_METRICS block;
    # 7.0+ renamed STACKLEAK_METRICS to KSTACK_ERASE_METRICS.
    replace_once(
        root / "fs/proc/base.c",
        old="#ifdef CONFIG_KSTACK_ERASE_METRICS\n\tONE(\"stack_depth\",",
        new=pid_entries + "#ifdef CONFIG_KSTACK_ERASE_METRICS\n\tONE(\"stack_depth\",",
        skip_if='ONE("agent_session"',
    )

    # 0007 — Kconfig + Makefile
    kconfig_block = '''config AGENT_NS
	bool "Agent namespaces (wintermute)"
	default y
	depends on NAMESPACES
	help
	  Vendor-fork namespace type CLONE_NEWAGENT.  Every process belongs
	  to an agent namespace identified by a 128-bit opaque session id.
	  Children inherit; the id is exposed at /proc/$PID/agent_session
	  and /proc/$PID/ns/agent.  Per-namespace counters track syscalls,
	  bytes written, open and connect counts.

	  Out-of-tree.  Not for upstream submission.  Say Y if your build
	  is the wintermute kernel; otherwise N.

'''
    replace_once(
        root / "init/Kconfig",
        old="config SCHED_AUTOGROUP\n",
        new=kconfig_block + "config SCHED_AUTOGROUP\n",
        skip_if="config AGENT_NS",
    )
    edit(
        root / "kernel/Makefile",
        after="obj-y += entry/",
        insert="obj-$(CONFIG_AGENT_NS) += agent_namespaces.o\n",
        skip_if="agent_namespaces.o",
    )

    # 0008 — syscall counter hooks
    edit(
        root / "fs/open.c",
        after="#include <linux/mnt_idmapping.h>",
        insert="#include <linux/agent_namespaces.h>\n",
        skip_if="linux/agent_namespaces.h",
    )
    # do_sys_openat2 (refactored in 7.0+ to a single-line return using
    # CLASS()/FD_ADD()): capture the fd, bump counter on success, then return.
    replace_once(
        root / "fs/open.c",
        old="\tCLASS(filename, name)(filename);\n\treturn FD_ADD(how->flags, do_file_open(dfd, name, &op));\n",
        new="\tCLASS(filename, name)(filename);\n"
            "\t{\n"
            "\t\tint __fd = FD_ADD(how->flags, do_file_open(dfd, name, &op));\n"
            "\t\tif (__fd >= 0)\n"
            "\t\t\tagent_ns_count_openat();\n"
            "\t\treturn __fd;\n"
            "\t}\n",
        skip_if="agent_ns_count_openat()",
    )

    edit(
        root / "fs/read_write.c",
        after="#include <linux/mount.h>",
        insert="#include <linux/agent_namespaces.h>\n",
        skip_if="linux/agent_namespaces.h",
    )
    # ksys_write (7.0+ CLASS(fd_pos, f) form): bump on success right before
    # `return ret;` at the end.
    replace_once(
        root / "fs/read_write.c",
        old="\t\tret = vfs_write(fd_file(f), buf, count, ppos);\n\t\tif (ret >= 0 && ppos)\n\t\t\tfd_file(f)->f_pos = pos;\n\t}\n\n\treturn ret;\n}\n",
        new="\t\tret = vfs_write(fd_file(f), buf, count, ppos);\n\t\tif (ret >= 0 && ppos)\n\t\t\tfd_file(f)->f_pos = pos;\n\t}\n\n"
            "\tif (ret > 0)\n\t\tagent_ns_count_write(ret);\n\treturn ret;\n}\n",
        skip_if="agent_ns_count_write(ret)",
    )
    # ksys_pwrite64: the success path is `return vfs_write(...)`. Wrap it.
    replace_once(
        root / "fs/read_write.c",
        old="\tif (fd_file(f)->f_mode & FMODE_PWRITE)\n\t\treturn vfs_write(fd_file(f), buf, count, &pos);\n\n\treturn -ESPIPE;\n}\n",
        new="\tif (fd_file(f)->f_mode & FMODE_PWRITE) {\n"
            "\t\tssize_t __ret = vfs_write(fd_file(f), buf, count, &pos);\n"
            "\t\tif (__ret > 0)\n\t\t\tagent_ns_count_write(__ret);\n"
            "\t\treturn __ret;\n"
            "\t}\n\n\treturn -ESPIPE;\n}\n",
        skip_if="agent_ns_count_write(__ret)",
    )

    edit(
        root / "fs/namei.c",
        after="#include <linux/init_task.h>",
        insert="#include <linux/agent_namespaces.h>\n",
        skip_if="linux/agent_namespaces.h",
    )
    # 7.0+ renamed do_unlinkat → filename_unlinkat. Bump the unlink counter
    # right before the function's only `return error;` at the end.
    replace_once(
        root / "fs/namei.c",
        old="\t\tlookup_flags |= LOOKUP_REVAL;\n\t\tgoto retry;\n\t}\n\treturn error;\n}\n\nSYSCALL_DEFINE3(unlinkat,",
        new="\t\tlookup_flags |= LOOKUP_REVAL;\n\t\tgoto retry;\n\t}\n"
            "\tif (!error)\n\t\tagent_ns_count_unlink();\n"
            "\treturn error;\n}\n\nSYSCALL_DEFINE3(unlinkat,",
        skip_if="agent_ns_count_unlink()",
    )

    edit(
        root / "net/socket.c",
        after="#include <linux/indirect_call_wrapper.h>",
        insert="#include <linux/agent_namespaces.h>\n",
        skip_if="linux/agent_namespaces.h",
    )
    # 7.0+ __sys_connect uses CLASS(fd,f) and is a short function returning
    # __sys_connect_file directly. Wrap the return to bump the connect counter.
    replace_once(
        root / "net/socket.c",
        old="\tif (ret)\n\t\treturn ret;\n\n\treturn __sys_connect_file(fd_file(f), &address, addrlen, 0);\n}\n",
        new="\tif (ret)\n\t\treturn ret;\n\n"
            "\tret = __sys_connect_file(fd_file(f), &address, addrlen, 0);\n"
            "\tagent_ns_count_connect();\n"
            "\treturn ret;\n}\n",
        skip_if="agent_ns_count_connect()",
    )

    # 0009 — proc/namespaces.c: register agentns_operations
    edit(
        root / "fs/proc/namespaces.c",
        after="#include <net/net_namespace.h>",
        insert="#ifdef CONFIG_AGENT_NS\n#include <linux/agent_namespaces.h>\n#endif\n",
        skip_if="linux/agent_namespaces.h",
    )
    # Insert into ns_entries[] — anchor on the final closing brace.
    # 7.0+ added &timens_for_children_operations as the last TIME_NS entry.
    replace_once(
        root / "fs/proc/namespaces.c",
        old="\t&timens_for_children_operations,\n#endif\n};\n",
        new="\t&timens_for_children_operations,\n#endif\n#ifdef CONFIG_AGENT_NS\n\t&agentns_operations,\n#endif\n};\n",
        skip_if="agentns_operations",
    )

    print("==> agentns inline edits applied")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: apply-agentns.py <linux_source_root>")
    main(Path(sys.argv[1]).resolve())
