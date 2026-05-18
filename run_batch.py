import json
import subprocess
import sys
import os
import signal
import time

def main():
    # 读取 app.json
    with open('app.json', 'r', encoding='utf-8') as f:
        apps = json.load(f)
        
    # 使用全部的应用
    test_apps = apps
    total_apps = len(test_apps)
    print(f"Loaded {total_apps} apps for testing: {[a['name'] for a in test_apps]}")

    for idx, app in enumerate(test_apps, 1):
        pkg = app['package']
        name = app['name']
        
        # 检查是否已经爬取过
        app_info_path = os.path.join(pkg, "app_info.json")
        comments_path = os.path.join(pkg, "comments.json")
        if os.path.exists(app_info_path) and os.path.exists(comments_path):
            print(f"\n==================================================")
            print(f"[{idx}/{total_apps}] Skipping {name} ({pkg}) - Already exists")
            print(f"==================================================")
            continue
            
        print(f"\n==================================================")
        print(f"[{idx}/{total_apps}] Starting task for {name} ({pkg})")
        print(f"==================================================")
        
        # 在 Windows 上必须要带上 CREATE_NEW_PROCESS_GROUP 标志
        # 否则发送 CTRL_C_EVENT 时会把当前(父)进程也一起杀掉
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0
            
        cmd = [sys.executable, "-u", "main.py", "-p", pkg, "-m", "500", "-t", "both"]
        
        # 启动子进程，bufsize=1 以支持行缓冲
        p = subprocess.Popen(
            cmd, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.STDOUT, 
            text=True, 
            encoding='utf-8',
            bufsize=1,
            creationflags=creationflags
        )
        
        try:
            # 实时读取输出
            while True:
                line = p.stdout.readline()
                if not line and p.poll() is not None:
                    break
                
                if line:
                    print(line, end="", flush=True)
                    
                    # 当检测到 'All tasks completed' 时，主动终止它
                    if "All tasks completed. Press Ctrl+C to exit." in line:
                        print("\n[Runner] Detected 'All tasks completed'. Sending Ctrl+C to subprocess...")
                        time.sleep(0.5)  # 等待短暂时间确保子进程完全进入 while True 等待状态
                        try:
                            if os.name == 'nt':
                                os.kill(p.pid, signal.CTRL_C_EVENT)
                            else:
                                p.send_signal(signal.SIGINT)
                        except Exception as e:
                            print(f"[Runner] Failed to send signal: {e}")
                        
                        # 设定一个超时机制，如果 Ctrl+C 没杀死，就强制 kill
                        time.sleep(2)
                        if p.poll() is None:
                            print(f"[Runner] Subprocess {p.pid} did not exit in time, forcing kill...")
                            p.kill()
                            
            p.wait()
            print(f"[Runner] Task for {name} finished.\n")
        except KeyboardInterrupt:
            print(f"\n[Runner] Aborted by user. Killing subprocess {p.pid}...")
            p.kill()
            sys.exit(0)

if __name__ == "__main__":
    main()
