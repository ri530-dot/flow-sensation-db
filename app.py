"""
フロウ感覚データベース - スマホ操作用Streamlitアプリ（ローカル版）
"""

import streamlit as st
import subprocess
import json
import re
from pathlib import Path

BASE       = Path(__file__).parent
AUDIO_DIR  = BASE / "audio_cache"
RESULT_DIR = BASE / "results"
DB_FILE    = BASE / "sensation_db.json"

AUDIO_DIR.mkdir(exist_ok=True)
RESULT_DIR.mkdir(exist_ok=True)

def load_db():
    if DB_FILE.exists():
        return json.loads(DB_FILE.read_text(encoding="utf-8"))
    return []

def save_db(db):
    DB_FILE.write_text(json.dumps(db, ensure_ascii=False, indent=2), encoding="utf-8")

def search_youtube(query, n=8):
    result = subprocess.run(
        ["yt-dlp", f"ytsearch{n}:{query}", "--dump-json", "--no-download", "--flat-playlist"],
        capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    tracks = []
    for line in result.stdout.strip().split("\n"):
        if not line.strip():
            continue
        try:
            data = json.loads(line)
            duration = data.get("duration")
            dur_str = f"{int(duration)//60}:{int(duration)%60:02d}" if duration else "?:??"
            tracks.append({
                "id":        data.get("id", ""),
                "title":     data.get("title", "不明"),
                "uploader":  data.get("uploader") or data.get("channel", "不明"),
                "duration":  dur_str,
                "thumbnail": f"https://img.youtube.com/vi/{data.get('id', '')}/mqdefault.jpg",
            })
        except Exception:
            continue
    return tracks

def download_audio(video_id):
    out_path = AUDIO_DIR / f"{video_id}.mp3"
    if out_path.exists():
        return str(out_path)
    subprocess.run(
        ["yt-dlp", "-x", "--audio-format", "mp3", "--audio-quality", "0",
         "-o", str(AUDIO_DIR / f"{video_id}.%(ext)s"),
         f"https://www.youtube.com/watch?v={video_id}"],
        capture_output=True
    )
    return str(out_path) if out_path.exists() else None

def get_lyrics(video_id):
    vtt_path = AUDIO_DIR / f"{video_id}.ja.vtt"
    if not vtt_path.exists():
        subprocess.run(
            ["yt-dlp", "--write-auto-subs", "--sub-lang", "ja",
             "--skip-download", "-o", str(AUDIO_DIR / video_id),
             f"https://www.youtube.com/watch?v={video_id}"],
            capture_output=True
        )
    if not vtt_path.exists():
        return []

    lines, seen = [], set()
    for block in vtt_path.read_text(encoding="utf-8").split("\n\n"):
        m = re.search(r"(\d+:\d+:\d+\.\d+) --> (\d+:\d+:\d+\.\d+)", block)
        if not m:
            continue
        text = re.sub(r"<[^>]+>", "", block.split("\n", 2)[-1]).strip()
        text = re.sub(r"\s+", " ", text)
        if not text or text in seen:
            continue
        seen.add(text)

        def to_sec(ts):
            parts = ts.replace(",", ".").split(":")
            if len(parts) == 2:
                return float(parts[0]) * 60 + float(parts[1])
            return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])

        lines.append({"start": to_sec(m.group(1)), "end": to_sec(m.group(2)), "text": text})
    return lines

def run_analysis(audio_path, start_sec, end_sec, label):
    import librosa
    import parselmouth
    import numpy as np

    y_full, sr = librosa.load(audio_path, sr=22050)
    y = y_full[int(start_sec * sr):int(end_sec * sr)]

    tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr, units="frames")
    beat_times   = librosa.frames_to_time(beat_frames, sr=sr)
    strong_beats = beat_times[0::4]

    onset_frames = librosa.onset.onset_detect(y=y, sr=sr, units="frames", delta=0.05)
    onset_times  = librosa.frames_to_time(onset_frames, sr=sr)

    snd    = parselmouth.Sound(audio_path)
    seg    = snd.extract_part(from_time=start_sec, to_time=end_sec, preserve_times=False)
    formant = seg.to_formant_burg(time_step=0.01, max_number_of_formants=5,
                                   maximum_formant=5500, window_length=0.025)

    VOWEL_REGIONS = {
        "a": (700, 900, 1000, 1400), "e": (500, 700, 1800, 2200),
        "i": (250, 400, 2000, 2600), "o": (400, 600, 600, 1000), "u": (250, 400, 600, 1000),
    }

    def classify(f1, f2):
        best, bd = "?", float("inf")
        for v, (a1, b1, a2, b2) in VOWEL_REGIONS.items():
            d = ((f1 - (a1+b1)/2)/200)**2 + ((f2 - (a2+b2)/2)/400)**2
            if d < bd:
                bd, best = d, v
        return best

    vowels, f2_vals = {}, []
    for t in onset_times:
        if t < 0.05:
            continue
        f1 = formant.get_value_at_time(1, t)
        f2 = formant.get_value_at_time(2, t)
        if f1 is None or f2 is None or np.isnan(f1) or np.isnan(f2):
            continue
        if not (200 <= f1 <= 1200):
            continue
        v = classify(f1, f2)
        vowels[v] = vowels.get(v, 0) + 1
        f2_vals.append(f2)

    intervals = np.diff(onset_times)
    rhythm_cv = float(np.std(intervals) / np.mean(intervals)) if len(intervals) > 1 else 0.0
    avg_f2    = float(np.mean(f2_vals)) if f2_vals else 0.0
    total     = sum(vowels.values()) or 1

    return {
        "label":     label,
        "tempo":     float(tempo),
        "rhythm_cv": round(rhythm_cv, 3),
        "avg_f2":    round(avg_f2, 0),
        "vowels":    {v: round(c/total*100, 1) for v, c in vowels.items()},
        "start_sec": start_sec,
        "end_sec":   end_sec,
    }

# ════════════════════════════════════════════════════
# UI
# ════════════════════════════════════════════════════
st.set_page_config(page_title="フロウ感覚DB", page_icon="🎤", layout="centered")
st.title("🎤 フロウ感覚DB")

tab_search, tab_db = st.tabs(["➕ 新しい曲を追加", "📊 データベース"])

with tab_search:
    query = st.text_input("アーティスト名・曲名を入力", placeholder="例: Yellow Bucks")

    if query:
        with st.spinner("検索中..."):
            tracks = search_youtube(query)
        if not tracks:
            st.warning("見つかりませんでした")
        else:
            for t in tracks:
                col_img, col_info = st.columns([1, 3])
                with col_img:
                    st.image(t["thumbnail"], use_container_width=True)
                with col_info:
                    st.markdown(f"**{t['title']}**  \n{t['uploader']}　({t['duration']})")
                    if st.button("選択", key=t["id"], use_container_width=True):
                        st.session_state["selected"] = t
                        for k in ["lyrics", "loaded_id", "sel_start", "sel_end", "audio_path"]:
                            st.session_state.pop(k, None)
                        st.rerun()

    if "selected" in st.session_state:
        track = st.session_state["selected"]
        st.divider()

        col_img2, col_meta = st.columns([1, 3])
        with col_img2:
            st.image(track["thumbnail"], use_container_width=True)
        with col_meta:
            st.markdown(f"### {track['title']}\n{track['uploader']}")

        # 評価（評価に関わらずパート指定できる）
        rating = st.radio(
            "評価",
            ["😎 かっこいい", "😐 かっこよくない"],
            horizontal=True,
            key="rating_radio"
        )
        is_cool = rating.startswith("😎")

        memo = st.text_input("メモ（任意）", placeholder="なぜそう感じたか etc.")

        # ── パート指定（評価に関係なく表示） ──────────────
        st.markdown("**パートを指定**（任意。指定しない場合は曲全体として保存）")

        if "lyrics" not in st.session_state or st.session_state.get("loaded_id") != track["id"]:
            with st.spinner("字幕を取得中..."):
                audio_path = download_audio(track["id"])
                lyrics     = get_lyrics(track["id"])
                st.session_state["audio_path"] = audio_path
                st.session_state["lyrics"]     = lyrics
                st.session_state["loaded_id"]  = track["id"]

        lyrics     = st.session_state.get("lyrics", [])
        audio_path = st.session_state.get("audio_path")

        start_sec = end_sec = None
        lyrics_range = []

        if lyrics:
            if "sel_start" not in st.session_state:
                st.session_state["sel_start"] = None
            if "sel_end" not in st.session_state:
                st.session_state["sel_end"] = None

            s = st.session_state["sel_start"]
            e = st.session_state["sel_end"]

            if s is None:
                st.caption("👆 かっこいい部分の最初の行をタップ")
            elif e is None:
                st.caption("👆 終わりの行をタップ（もう一度最初の行をタップするとリセット）")
            else:
                if st.button("🔄 選択をリセット", use_container_width=False):
                    st.session_state["sel_start"] = None
                    st.session_state["sel_end"]   = None
                    st.rerun()

            for i, line in enumerate(lyrics):
                ts   = f"{int(line['start'])//60}:{int(line['start'])%60:02d}"
                text = f"[{ts}] {line['text']}"
                s    = st.session_state["sel_start"]
                e    = st.session_state["sel_end"]

                if s is not None and e is not None and s <= i <= e:
                    label = f"🟡 {text}"
                elif s is not None and i == s:
                    label = f"🟢 {text}"
                else:
                    label = f"　　{text}"

                if st.button(label, key=f"line{i}", use_container_width=True):
                    if s is None:
                        st.session_state["sel_start"] = i
                        st.session_state["sel_end"]   = None
                    elif e is None:
                        if i >= s:
                            st.session_state["sel_end"] = i
                        else:
                            st.session_state["sel_start"] = i
                    else:
                        st.session_state["sel_start"] = i
                        st.session_state["sel_end"]   = None
                    st.rerun()

            s = st.session_state.get("sel_start")
            e = st.session_state.get("sel_end")
            if s is not None and e is not None and s <= e:
                lyrics_range = [l["text"] for l in lyrics[s:e+1]]
                st.success(f"選択中: {lyrics[s]['text'][:20]}… 〜 {lyrics[e]['text'][:20]}…")

                # 秒数で細かく調整
                st.markdown("**細かく調整（任意）**")
                col1, col2 = st.columns(2)
                with col1:
                    start_sec = st.number_input(
                        "開始（秒）", value=float(lyrics[s]["start"]),
                        min_value=0.0, step=0.1, format="%.1f"
                    )
                with col2:
                    end_sec = st.number_input(
                        "終了（秒）", value=float(lyrics[e]["end"]),
                        min_value=0.0, step=0.1, format="%.1f"
                    )
        else:
            st.info("字幕が取得できませんでした。時間で指定してください。")
            col1, col2 = st.columns(2)
            with col1:
                start_sec = st.number_input("開始（秒）", min_value=0.0, value=0.0, step=0.1, format="%.1f")
            with col2:
                end_sec = st.number_input("終了（秒）", min_value=0.0, value=30.0, step=0.1, format="%.1f")

        # ── 保存ボタン ──────────────────────────────────
        st.divider()
        can_analyze = is_cool and audio_path and start_sec is not None

        if can_analyze:
            if st.button("🔍 分析してDBに保存", use_container_width=True, type="primary"):
                with st.spinner("分析中（1〜2分）..."):
                    result = run_analysis(audio_path, start_sec, end_sec,
                                          f"{track['uploader']} — {track['title']}")
                    entry = {
                        **result,
                        "rating":       "cool",
                        "video_id":     track["id"],
                        "memo":         memo,
                        "lyrics_range": lyrics_range,
                        "analyzed":     True,
                    }
                    db = load_db()
                    db.append(entry)
                    save_db(db)
                    st.success("✅ 保存しました！")
                    st.json(result)
        else:
            btn_label = "💾 DBに保存（分析なし）"
            if st.button(btn_label, use_container_width=True, type="primary"):
                entry = {
                    "label":       f"{track['uploader']} — {track['title']}",
                    "rating":      "cool" if is_cool else "not_cool",
                    "video_id":    track["id"],
                    "memo":        memo,
                    "start_sec":   start_sec,
                    "end_sec":     end_sec,
                    "lyrics_range": lyrics_range,
                    "analyzed":    False,
                    "tempo": None, "rhythm_cv": None, "avg_f2": None, "vowels": {},
                }
                db = load_db()
                db.append(entry)
                save_db(db)
                st.success("✅ 保存しました！")

with tab_db:
    db = load_db()
    if not db:
        st.info("まだデータがありません。")
    else:
        cool_count     = sum(1 for e in db if e.get("rating") == "cool")
        not_cool_count = sum(1 for e in db if e.get("rating") == "not_cool")
        st.write(f"**合計 {len(db)}件　😎 {cool_count}件　😐 {not_cool_count}件**")

        filter_rating = st.radio("フィルター", ["すべて", "😎 かっこいいのみ", "😐 かっこよくないのみ"],
                                  horizontal=True)

        for entry in reversed(db):
            r = entry.get("rating", "cool")
            if filter_rating == "😎 かっこいいのみ" and r != "cool":
                continue
            if filter_rating == "😐 かっこよくないのみ" and r != "not_cool":
                continue

            icon = "😎" if r == "cool" else "😐"
            with st.expander(f"{icon} {entry['label']}"):
                vid = entry.get("video_id", "")
                if vid:
                    st.image(f"https://img.youtube.com/vi/{vid}/mqdefault.jpg", width=240)
                if entry.get("start_sec") is not None:
                    st.write(f"⏱ {entry['start_sec']:.1f}秒 〜 {entry['end_sec']:.1f}秒")
                if entry.get("tempo"):
                    st.write(f"🎵 BPM: {entry['tempo']:.0f}　CV: {entry['rhythm_cv']}　F2: {entry['avg_f2']:.0f}Hz")
                if entry.get("memo"):
                    st.write(f"💬 {entry['memo']}")
                if entry.get("lyrics_range"):
                    st.text("\n".join(entry["lyrics_range"]))
