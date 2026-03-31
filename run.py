import subprocess
import sys
import os
import time
import signal

def main():
    processes = []

    api_proc = subprocess.Popen(
        [sys.executable, "api.py"],
        env={**os.environ, "PORT": os.getenv("PORT", "8080")},
    )
    processes.append(("api", api_proc))
    print(f"API started (PID {api_proc.pid})")

    bot_proc = subprocess.Popen(
        [sys.executable, "main.py"],
    )
    processes.append(("bot", bot_proc))
    print(f"Bot started (PID {bot_proc.pid})")

    def handle_signal(signum, frame):
        print(f"\nSignal {signum} received, shutting down...")
        for name, proc in processes:
            if proc.poll() is None:
                proc.terminate()
        for name, proc in processes:
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        sys.exit(0)

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    while True:
        for name, proc in processes:
            if proc.poll() is not None:
                print(f"Process '{name}' exited with code {proc.returncode}")
                for n, p in processes:
                    if p.poll() is None:
                        p.terminate()
                sys.exit(proc.returncode)
        time.sleep(1)


if __name__ == "__main__":
    main()
