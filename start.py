"""
Streamlit + ngrok を同時起動するスクリプト
外部（外出先）からスマホでアクセスできるURLを発行する
"""

import subprocess
import time
import sys
from pyngrok import ngrok, conf

PORT = 8501

# ngrok authtoken が設定されていない場合の案内
try:
    conf.get_default().auth_token
except Exception:
    print("【初回設定が必要です】")
    print("1. https://ngrok.com でアカウント作成（無料）")
    print("2. ダッシュボードで Auth Token をコピー")
    print("3. 以下のコマンドを実行:")
    print("   python -c \"from pyngrok import ngrok; ngrok.set_auth_token('YOUR_TOKEN')\"")
    sys.exit(1)

# Streamlit をバックグラウンドで起動
print("Streamlit 起動中...")
proc = subprocess.Popen(
    [sys.executable, "-m", "streamlit", "run", "app.py",
     "--server.port", str(PORT), "--server.headless", "true"],
    cwd=str(__file__).replace("start.py", "")
)

time.sleep(3)

# ngrok トンネルを開く
print("ngrok トンネル開通中...")
tunnel = ngrok.connect(PORT)
public_url = tunnel.public_url

print("\n" + "="*50)
print(f"  外部アクセスURL: {public_url}")
print("="*50)
print("このURLをスマホで開けばどこからでもアクセスできます")
print("PCを閉じると使えなくなります（PCは起動したまま）")
print("\nCtrl+C で終了")

try:
    proc.wait()
except KeyboardInterrupt:
    print("\n終了します...")
    ngrok.kill()
    proc.terminate()
