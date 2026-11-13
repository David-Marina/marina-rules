/* marina-ops — a single-purpose launcher for Marina's scheduled jobs on macOS.
 *
 * Why it exists: launchd-started /bin/bash is denied reading ~/Documents by macOS privacy protection
 * (TCC: "Operation not permitted"). Granting /bin/bash (or a general interpreter) access would let every
 * script on the machine inherit it. Instead this tiny binary is the one thing granted access to the
 * Documents folder; it can only run two fixed scripts in one fixed checkout, and passes no arguments
 * except an optional --dry-run.
 *
 * It posix_spawn()s bash and waits (it must NOT exec): TCC attributes a child's file access to the
 * responsible (parent) process, so the grant given to marina-ops covers the bash child. After exec() the
 * process identity would become /bin/bash and the grant would not apply.
 *
 * Build (REPO is baked in at compile time; nothing is read from the environment to pick the script):
 *   cc -O2 -Wall -DMARINA_REPO='"/abs/path/to/marina-rules"' -o marina-ops marina-ops.c
 *   codesign -s - -i org.marina-rules.ops -f marina-ops
 * Usage: marina-ops daily|weekly [--dry-run]
 */
#include <spawn.h>
#include <stdio.h>
#include <string.h>
#include <sys/wait.h>

#ifndef MARINA_REPO
#error "build with -DMARINA_REPO='\"/abs/path/to/marina-rules\"'"
#endif

extern char **environ;

int main(int argc, char **argv) {
    const char *script = NULL;
    if (argc >= 2 && strcmp(argv[1], "daily") == 0) script = MARINA_REPO "/ops/daily_audit.sh";
    if (argc >= 2 && strcmp(argv[1], "weekly") == 0) script = MARINA_REPO "/ops/weekly.sh";
    int dry = (argc == 3 && strcmp(argv[2], "--dry-run") == 0);
    if (!script || argc > 3 || (argc == 3 && !dry)) {
        fprintf(stderr, "usage: marina-ops daily|weekly [--dry-run]\n");
        return 64;
    }
    char *child[] = {"/bin/bash", (char *)script, dry ? "--dry-run" : NULL, NULL};
    pid_t pid;
    int rc = posix_spawn(&pid, "/bin/bash", NULL, NULL, child, environ);
    if (rc != 0) { fprintf(stderr, "marina-ops: spawn failed: %s\n", strerror(rc)); return 71; }
    int st = 0;
    if (waitpid(pid, &st, 0) < 0) { perror("marina-ops: waitpid"); return 71; }
    return WIFEXITED(st) ? WEXITSTATUS(st) : 70;
}
