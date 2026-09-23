#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <sys/types.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <signal.h>
#include <errno.h>

#define RUNTIME_OFFSET 131072 // 128 KB standard Type 2 AppImage offset

// Magic bytes for AppImage Type 2 at offset 8
__attribute__((section(".rodata")))
const char appimage_magic[3] = {'A', 'I', 0x02};

static char temp_dir_path[256] = {0};
static pid_t child_pid = 0;

void cleanup_temp_dir() {
    if (temp_dir_path[0] != '\0') {
        char cmd[512];
        snprintf(cmd, sizeof(cmd), "rm -rf '%s'", temp_dir_path);
        system(cmd);
        temp_dir_path[0] = '\0';
    }
}

void sig_handler(int sig) {
    if (child_pid > 0) {
        kill(child_pid, sig);
    }
    cleanup_temp_dir();
    _exit(128 + sig);
}

int main(int argc, char **argv) {
    char exe_path[1024];
    ssize_t len = readlink("/proc/self/exe", exe_path, sizeof(exe_path) - 1);
    if (len < 0) {
        perror("readlink /proc/self/exe failed");
        return 1;
    }
    exe_path[len] = '\0';

    // Handle AppImage CLI flags
    for (int i = 1; i < argc; i++) {
        if (strcmp(argv[i], "--appimage-help") == 0) {
            printf("Linux App Manager AppImage\n\n");
            printf("Available options:\n");
            printf("  --appimage-extract      Extract the contents to squashfs-root\n");
            printf("  --appimage-version      Print the version of this AppImage\n");
            printf("  --appimage-help         Print this help message\n");
            return 0;
        } else if (strcmp(argv[i], "--appimage-version") == 0) {
            printf("Linux App Manager 1.0 (x86_64 AppImage)\n");
            return 0;
        } else if (strcmp(argv[i], "--appimage-extract") == 0) {
            printf("Extracting AppImage to squashfs-root/...\n");
            char cmd[2048];
            snprintf(cmd, sizeof(cmd), "unsquashfs -f -o %d -d squashfs-root '%s'", RUNTIME_OFFSET, exe_path);
            int res = system(cmd);
            if (res == 0) {
                printf("Extraction complete: squashfs-root/\n");
                return 0;
            } else {
                fprintf(stderr, "Extraction failed.\n");
                return 1;
            }
        }
    }

    // Create temp mount directory
    char template[] = "/tmp/.mount_appmgr_XXXXXX";
    char *dir = mkdtemp(template);
    if (!dir) {
        perror("mkdtemp failed");
        return 1;
    }
    strncpy(temp_dir_path, dir, sizeof(temp_dir_path) - 1);

    // Register cleanup and signal handlers
    atexit(cleanup_temp_dir);
    signal(SIGINT, sig_handler);
    signal(SIGTERM, sig_handler);
    signal(SIGHUP, sig_handler);

    // Extract payload with unsquashfs
    char extract_cmd[2048];
    snprintf(extract_cmd, sizeof(extract_cmd), "unsquashfs -q -f -o %d -d '%s' '%s'", RUNTIME_OFFSET, temp_dir_path, exe_path);
    int res = system(extract_cmd);
    if (res != 0) {
        fprintf(stderr, "Failed to mount/extract AppImage payload.\n");
        cleanup_temp_dir();
        return 1;
    }

    // Get current working directory
    char cwd[1024];
    if (!getcwd(cwd, sizeof(cwd))) {
        cwd[0] = '\0';
    }

    // Set AppImage environment variables
    setenv("APPDIR", temp_dir_path, 1);
    setenv("APPIMAGE", exe_path, 1);
    setenv("OWD", cwd, 1);
    setenv("ARGV0", argv[0], 1);

    char apprun_path[512];
    snprintf(apprun_path, sizeof(apprun_path), "%s/AppRun", temp_dir_path);

    // Fork and exec
    child_pid = fork();
    if (child_pid < 0) {
        perror("fork failed");
        cleanup_temp_dir();
        return 1;
    }

    if (child_pid == 0) {
        // Child process
        execv(apprun_path, argv);
        perror("execv failed");
        _exit(1);
    }

    // Parent waits for child
    int status = 0;
    while (waitpid(child_pid, &status, 0) < 0) {
        if (errno != EINTR) {
            status = -1;
            break;
        }
    }

    cleanup_temp_dir();

    if (WIFEXITED(status)) {
        return WEXITSTATUS(status);
    } else if (WIFSIGNALED(status)) {
        return 128 + WTERMSIG(status);
    }
    return 0;
}
