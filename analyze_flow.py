"""
ラップフロウ分析スクリプト
- ビート検出（強拍・弱拍）
- 母音の色（フォルマントF1/F2）
- 韻律の一致（音のオンセットと強拍の距離）
"""

import librosa
import librosa.display
import numpy as np
import parselmouth
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib import rcParams
rcParams['font.family'] = 'MS Gothic'

# ── 設定 ──────────────────────────────────────────
AUDIO_FILE = r"C:\Users\ジョリーパスタ\Desktop\claude code\曲の分析\the_moment.mp3"
START_SEC = 11.5   # Yellow Bucks パート開始
END_SEC   = 54.0   # Yellow Bucks パート終了
OUTPUT    = r"C:\Users\ジョリーパスタ\Desktop\claude code\曲の分析\results\flow_analysis.png"

# 母音のフォルマント目安（Hz）: [F1_min, F1_max, F2_min, F2_max]
VOWEL_REGIONS = {
    'a': (700, 900, 1000, 1400),
    'e': (500, 700, 1800, 2200),
    'i': (250, 400, 2000, 2600),
    'o': (400, 600,  600, 1000),
    'u': (250, 400,  600, 1000),
}
VOWEL_COLORS = {'a': '#e74c3c', 'e': '#f39c12', 'i': '#2ecc71', 'o': '#3498db', 'u': '#9b59b6'}

def classify_vowel(f1, f2):
    """F1/F2から最も近い母音を推定する"""
    best, best_dist = '?', float('inf')
    for v, (f1_lo, f1_hi, f2_lo, f2_hi) in VOWEL_REGIONS.items():
        f1_center = (f1_lo + f1_hi) / 2
        f2_center = (f2_lo + f2_hi) / 2
        # F2の重みを大きくする（母音識別により寄与する）
        dist = ((f1 - f1_center) / 200) ** 2 + ((f2 - f2_center) / 400) ** 2
        if dist < best_dist:
            best_dist = dist
            best = v
    return best

def main():
    print("音声読み込み中...")
    y_full, sr = librosa.load(AUDIO_FILE, sr=22050)

    # 分析対象区間を切り出す
    start_sample = int(START_SEC * sr)
    end_sample   = int(END_SEC * sr)
    y = y_full[start_sample:end_sample]
    duration = len(y) / sr

    # ── Step1: ビート検出 ────────────────────────────
    print("ビート検出中...")
    tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr, units='frames')
    beat_times = librosa.frames_to_time(beat_frames, sr=sr)
    print(f"  テンポ: {float(tempo):.1f} BPM")

    # 強拍（1拍目）を推定: 4拍周期で0番目
    strong_beat_times = beat_times[0::4]
    weak_beat_times   = np.setdiff1d(beat_times, strong_beat_times)

    # ── Step2: オンセット検出（音の立ち上がり） ──────────
    print("オンセット検出中...")
    onset_frames = librosa.onset.onset_detect(y=y, sr=sr, units='frames', delta=0.05)
    onset_times  = librosa.frames_to_time(onset_frames, sr=sr)

    # ── Step3: フォルマント分析 ──────────────────────
    print("フォルマント分析中...")
    snd = parselmouth.Sound(AUDIO_FILE)
    snd_segment = snd.extract_part(
        from_time=START_SEC,
        to_time=END_SEC,
        preserve_times=False
    )
    formant = snd_segment.to_formant_burg(time_step=0.01, max_number_of_formants=5,
                                           maximum_formant=5500, window_length=0.025)

    # オンセット時刻でF1/F2を取得 → 母音推定
    vowel_data = []
    for t in onset_times:
        if t < 0.05:
            continue
        f1 = formant.get_value_at_time(1, t)
        f2 = formant.get_value_at_time(2, t)
        if f1 is None or f2 is None or np.isnan(f1) or np.isnan(f2):
            continue
        if f1 < 200 or f1 > 1200:  # 有声音でない可能性が高い区間を除外
            continue
        vowel = classify_vowel(f1, f2)
        # 最近の強拍との距離（拍ズレ）
        dists = np.abs(strong_beat_times - t)
        beat_offset = float(np.min(dists)) if len(strong_beat_times) > 0 else 0.0
        vowel_data.append({'time': t, 'f1': f1, 'f2': f2, 'vowel': vowel, 'beat_offset': beat_offset})

    # ── Step4: 可視化 ──────────────────────────────
    print("グラフ生成中...")
    fig, axes = plt.subplots(3, 1, figsize=(16, 12))
    fig.suptitle("Yellow Bucks - The Moment フロウ分析（0:11〜0:54）", fontsize=14)

    # --- (1) メルスペクトログラム + ビート位置 ---
    ax1 = axes[0]
    S = librosa.feature.melspectrogram(y=y, sr=sr, n_mels=128)
    S_db = librosa.power_to_db(S, ref=np.max)
    librosa.display.specshow(S_db, sr=sr, x_axis='time', y_axis='mel', ax=ax1, cmap='magma')
    ax1.set_title("メルスペクトログラム + ビート位置")
    for bt in strong_beat_times:
        ax1.axvline(x=bt, color='cyan', alpha=0.7, linewidth=1.2, label='強拍')
    for bt in weak_beat_times:
        ax1.axvline(x=bt, color='white', alpha=0.3, linewidth=0.7)
    ax1.legend(['強拍', '弱拍'], loc='upper right', fontsize=8)

    # --- (2) 母音の色タイムライン ---
    ax2 = axes[1]
    ax2.set_title("母音の色タイムライン（オンセット時刻）")
    ax2.set_xlim(0, duration)
    ax2.set_ylim(0, 1)
    for vd in vowel_data:
        color = VOWEL_COLORS.get(vd['vowel'], '#aaaaaa')
        ax2.axvline(x=vd['time'], color=color, alpha=0.8, linewidth=2)
    for bt in strong_beat_times:
        ax2.axvline(x=bt, color='black', alpha=0.4, linewidth=1, linestyle='--')
    patches = [mpatches.Patch(color=c, label=v) for v, c in VOWEL_COLORS.items()]
    ax2.legend(handles=patches, loc='upper right', fontsize=8)
    ax2.set_yticks([])
    ax2.set_xlabel("時間（秒）")

    # --- (3) 強拍との距離（韻律の一致度） ---
    ax3 = axes[2]
    ax3.set_title("各オンセットの強拍からのズレ（小さいほど強拍に乗っている）")
    times  = [vd['time'] for vd in vowel_data]
    offsets = [vd['beat_offset'] for vd in vowel_data]
    colors  = [VOWEL_COLORS.get(vd['vowel'], '#aaaaaa') for vd in vowel_data]
    ax3.scatter(times, offsets, c=colors, s=40, alpha=0.8)
    ax3.axhline(y=0.1, color='gray', linestyle='--', alpha=0.5, label='0.1秒以内（強拍に乗っている）')
    ax3.set_xlim(0, duration)
    ax3.set_ylim(0, 0.6)
    ax3.set_xlabel("時間（秒）")
    ax3.set_ylabel("強拍との距離（秒）")
    ax3.legend(fontsize=8)

    plt.tight_layout()
    plt.savefig(OUTPUT, dpi=150, bbox_inches='tight')
    print(f"\n保存完了: {OUTPUT}")

    # ── サマリー出力 ────────────────────────────────
    print(f"\n=== 分析サマリー ===")
    print(f"テンポ: {float(tempo):.1f} BPM")
    print(f"検出オンセット数: {len(onset_times)}")
    print(f"有効母音データ数: {len(vowel_data)}")
    vowel_counts = {}
    for vd in vowel_data:
        vowel_counts[vd['vowel']] = vowel_counts.get(vd['vowel'], 0) + 1
    print("母音分布:")
    for v, cnt in sorted(vowel_counts.items(), key=lambda x: -x[1]):
        pct = cnt / len(vowel_data) * 100 if vowel_data else 0
        print(f"  {v}: {cnt}回 ({pct:.1f}%)")
    on_beat = sum(1 for vd in vowel_data if vd['beat_offset'] < 0.1)
    print(f"強拍0.1秒以内のオンセット: {on_beat}/{len(vowel_data)} ({on_beat/len(vowel_data)*100:.1f}%)" if vowel_data else "")

if __name__ == "__main__":
    main()
