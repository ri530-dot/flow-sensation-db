"""
2曲のフロウ比較分析スクリプト
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

VOWEL_REGIONS = {
    'a': (700, 900, 1000, 1400),
    'e': (500, 700, 1800, 2200),
    'i': (250, 400, 2000, 2600),
    'o': (400, 600,  600, 1000),
    'u': (250, 400,  600, 1000),
}
VOWEL_COLORS = {'a': '#e74c3c', 'e': '#f39c12', 'i': '#2ecc71', 'o': '#3498db', 'u': '#9b59b6'}

def classify_vowel(f1, f2):
    best, best_dist = '?', float('inf')
    for v, (f1_lo, f1_hi, f2_lo, f2_hi) in VOWEL_REGIONS.items():
        f1_center = (f1_lo + f1_hi) / 2
        f2_center = (f2_lo + f2_hi) / 2
        dist = ((f1 - f1_center) / 200) ** 2 + ((f2 - f2_center) / 400) ** 2
        if dist < best_dist:
            best_dist = dist
            best = v
    return best

def analyze(audio_file, start_sec, end_sec, label):
    print(f"\n【{label}】分析中...")
    y_full, sr = librosa.load(audio_file, sr=22050)
    start_sample = int(start_sec * sr)
    end_sample   = int(end_sec * sr)
    y = y_full[start_sample:end_sample]
    duration = len(y) / sr

    tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr, units='frames')
    beat_times = librosa.frames_to_time(beat_frames, sr=sr)
    strong_beat_times = beat_times[0::4]

    onset_frames = librosa.onset.onset_detect(y=y, sr=sr, units='frames', delta=0.05)
    onset_times  = librosa.frames_to_time(onset_frames, sr=sr)

    snd = parselmouth.Sound(audio_file)
    snd_seg = snd.extract_part(from_time=start_sec, to_time=end_sec, preserve_times=False)
    formant = snd_seg.to_formant_burg(time_step=0.01, max_number_of_formants=5,
                                       maximum_formant=5500, window_length=0.025)

    vowel_data = []
    for t in onset_times:
        if t < 0.05:
            continue
        f1 = formant.get_value_at_time(1, t)
        f2 = formant.get_value_at_time(2, t)
        if f1 is None or f2 is None or np.isnan(f1) or np.isnan(f2):
            continue
        if f1 < 200 or f1 > 1200:
            continue
        vowel = classify_vowel(f1, f2)
        dists = np.abs(strong_beat_times - t)
        beat_offset = float(np.min(dists)) if len(strong_beat_times) > 0 else 0.0
        vowel_data.append({'time': t, 'f1': f1, 'f2': f2, 'vowel': vowel, 'beat_offset': beat_offset})

    # オンセット間隔のばらつき（リズムの複雑さ）
    if len(onset_times) > 1:
        intervals = np.diff(onset_times)
        rhythm_cv = float(np.std(intervals) / np.mean(intervals))  # 変動係数
    else:
        rhythm_cv = 0.0

    # F2の平均（音の明るさ）
    f2_values = [vd['f2'] for vd in vowel_data]
    avg_f2 = float(np.mean(f2_values)) if f2_values else 0.0

    print(f"  テンポ: {float(tempo):.1f} BPM")
    print(f"  オンセット数: {len(onset_times)}")
    print(f"  有効母音数: {len(vowel_data)}")
    print(f"  リズム変動係数: {rhythm_cv:.3f}")
    print(f"  F2平均（音の明るさ）: {avg_f2:.0f} Hz")

    vowel_counts = {}
    for vd in vowel_data:
        vowel_counts[vd['vowel']] = vowel_counts.get(vd['vowel'], 0) + 1

    return {
        'label': label,
        'y': y, 'sr': sr, 'duration': duration,
        'beat_times': beat_times,
        'strong_beat_times': strong_beat_times,
        'onset_times': onset_times,
        'vowel_data': vowel_data,
        'vowel_counts': vowel_counts,
        'tempo': float(tempo),
        'rhythm_cv': rhythm_cv,
        'avg_f2': avg_f2,
    }

def plot_comparison(a, b, output):
    fig, axes = plt.subplots(3, 2, figsize=(18, 12))
    fig.suptitle("フロウ比較分析", fontsize=14)

    for col, d in enumerate([a, b]):
        # (1) メルスペクトログラム
        ax = axes[0][col]
        S = librosa.feature.melspectrogram(y=d['y'], sr=d['sr'], n_mels=128)
        S_db = librosa.power_to_db(S, ref=np.max)
        librosa.display.specshow(S_db, sr=d['sr'], x_axis='time', y_axis='mel', ax=ax, cmap='magma')
        ax.set_title(f"{d['label']}　{d['tempo']:.0f} BPM")
        for bt in d['strong_beat_times']:
            ax.axvline(x=bt, color='cyan', alpha=0.6, linewidth=1)

        # (2) 母音タイムライン
        ax = axes[1][col]
        ax.set_xlim(0, d['duration'])
        ax.set_ylim(0, 1)
        for vd in d['vowel_data']:
            ax.axvline(x=vd['time'], color=VOWEL_COLORS.get(vd['vowel'], '#aaa'), alpha=0.8, linewidth=2)
        for bt in d['strong_beat_times']:
            ax.axvline(x=bt, color='black', alpha=0.3, linewidth=1, linestyle='--')
        patches = [mpatches.Patch(color=c, label=v) for v, c in VOWEL_COLORS.items()]
        ax.legend(handles=patches, loc='upper right', fontsize=7)
        ax.set_yticks([])
        total = sum(d['vowel_counts'].values()) or 1
        summary = '  '.join([f"{v}:{d['vowel_counts'].get(v,0)/total*100:.0f}%" for v in 'aeiou'])
        ax.set_xlabel(summary, fontsize=9)
        ax.set_title("母音タイムライン")

        # (3) 強拍からのズレ
        ax = axes[2][col]
        times   = [vd['time'] for vd in d['vowel_data']]
        offsets = [vd['beat_offset'] for vd in d['vowel_data']]
        colors  = [VOWEL_COLORS.get(vd['vowel'], '#aaa') for vd in d['vowel_data']]
        ax.scatter(times, offsets, c=colors, s=35, alpha=0.7)
        ax.axhline(y=0.1, color='gray', linestyle='--', alpha=0.5)
        ax.set_xlim(0, d['duration'])
        ax.set_ylim(0, 0.6)
        ax.set_xlabel("時間（秒）")
        ax.set_ylabel("強拍からのズレ（秒）")
        on_beat = sum(1 for vd in d['vowel_data'] if vd['beat_offset'] < 0.1)
        pct = on_beat / len(d['vowel_data']) * 100 if d['vowel_data'] else 0
        ax.set_title(f"韻律の一致　CV={d['rhythm_cv']:.3f}　F2平均={d['avg_f2']:.0f}Hz\n強拍0.1秒以内: {pct:.1f}%")

    plt.tight_layout()
    plt.savefig(output, dpi=150, bbox_inches='tight')
    print(f"\n保存完了: {output}")

if __name__ == "__main__":
    BASE = r"C:\Users\ジョリーパスタ\Desktop\claude code\曲の分析"

    a = analyze(f"{BASE}\\separated\\htdemucs\\the_moment\\vocals.mp3", start_sec=11.5, end_sec=54.0, label="Yellow Bucks / The Moment")
    b = analyze(f"{BASE}\\separated\\htdemucs\\compare\\vocals.mp3",    start_sec=0.0,  end_sec=43.0, label="比較曲")

    plot_comparison(a, b, f"{BASE}\\results\\comparison.png")
