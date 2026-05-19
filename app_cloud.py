"""
フロウ感覚DB - クラウド収集版
Streamlit Community Cloud にデプロイして使う
データは Supabase (クラウドDB) に保存
分析はしない（後でPCのanalyze_batch.pyで実行）
"""

import streamlit as st
import subprocess
import json
import re
import requests
from pathlib import Path

SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
TABLE = "entries"

BUFFER_SEC = 1.0  # 分析時に前後に追加するバッファ（秒）

# ── Supabase操作 ──────────────────────────────────
def db_insert(entry: dict) -> bool:
    resp = requests.post(
        f"{SUPABASE_URL}/rest/v1/{TABLE}",
        json=entry,
        headers={
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal",
        },
        timeout=10,
    )
    return resp.status_code in (200, 201)

def db_select() -> list:
    resp = requests.get(
        f"{SUPABASE_URL}/rest/v1/{TABLE}?order=created_at.desc&limit=200",
        headers={
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
        },
        timeout=10,
    )
    return resp.json() if resp.status_code == 200 else []

# ── YouTube検索 ──────────────────────────────────
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

# ── 字幕を取得（youtube-transcript-api使用） ──────
NOISE = {'[音楽]', '[拍手]', '[笑い]', '[Music]', '[Applause]'}

def get_words(video_id):
    """youtube-transcript-apiで字幕チャンクを取得して返す"""
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        transcript = YouTubeTranscriptApi.get_transcript(video_id, languages=['ja', 'ja-JP'])
    except Exception as e1:
        try:
            from youtube_transcript_api import YouTubeTranscriptApi
            transcript = YouTubeTranscriptApi.get_transcript(video_id)
        except Exception as e2:
            st.warning(f"字幕エラー: {e1} / {e2}")
            return []

    words = []
    for entry in transcript:
        text = entry['text'].strip()
        if not text or text in NOISE:
            continue
        words.append({
            'text': text,
            'start': entry['start'],
            'end':   entry['start'] + entry['duration'],
        })
    return words

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
                        for k in ["words", "loaded_id", "sel_start", "sel_end"]:
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

        rating = st.radio(
            "評価",
            ["😎 かっこいい", "😐 かっこよくない"],
            horizontal=True,
            key="rating_radio"
        )
        is_cool = rating.startswith("😎")

        memo = st.text_input("メモ（任意）", placeholder="なぜそう感じたか etc.")

        # ── パート指定 ────────────────────────────────
        st.markdown("**かっこいいパートを単語で選択**（任意）")

        if "words" not in st.session_state or st.session_state.get("loaded_id") != track["id"]:
            with st.spinner("歌詞を取得中..."):
                words = get_words(track["id"])
                st.session_state["words"]     = words
                st.session_state["loaded_id"] = track["id"]

        words = st.session_state.get("words", [])

        start_sec = end_sec = None
        lyrics_range = []

        if words:
            if "sel_start" not in st.session_state:
                st.session_state["sel_start"] = None
            if "sel_end" not in st.session_state:
                st.session_state["sel_end"] = None

            s = st.session_state["sel_start"]
            e = st.session_state["sel_end"]

            if s is None:
                st.caption("👆 最初の単語をタップ")
            elif e is None:
                st.caption("👆 最後の単語をタップ　（タップし直すとリセット）")
            else:
                sel_text = "".join(w["text"] for w in words[s:e+1])
                st.success(f"選択中：{sel_text}")
                st.caption(f"⏱ {words[s]['start']:.1f}秒 〜 {words[e]['end']:.1f}秒（±{BUFFER_SEC}秒バッファ付きで分析）")
                if st.button("🔄 リセット"):
                    st.session_state["sel_start"] = None
                    st.session_state["sel_end"]   = None
                    st.rerun()

            # 単語グリッド（4単語ずつ横並び）
            COLS = 4
            for row_i in range(0, len(words), COLS):
                row_words = words[row_i:row_i + COLS]
                cols = st.columns(len(row_words))
                for col_j, (col, word) in enumerate(zip(cols, row_words)):
                    wi = row_i + col_j
                    s  = st.session_state["sel_start"]
                    e  = st.session_state["sel_end"]
                    if s is not None and e is not None and s <= wi <= e:
                        label = f"🟡{word['text']}"
                    elif s is not None and wi == s:
                        label = f"🟢{word['text']}"
                    else:
                        label = word["text"]
                    with col:
                        if st.button(label, key=f"w{wi}", use_container_width=True):
                            s2 = st.session_state["sel_start"]
                            e2 = st.session_state["sel_end"]
                            if s2 is None:
                                st.session_state["sel_start"] = wi
                            elif e2 is None:
                                if wi >= s2:
                                    st.session_state["sel_end"] = wi
                                else:
                                    st.session_state["sel_start"] = wi
                            else:
                                st.session_state["sel_start"] = wi
                                st.session_state["sel_end"]   = None
                            st.rerun()

            s = st.session_state.get("sel_start")
            e = st.session_state.get("sel_end")
            if s is not None and e is not None and s <= e:
                start_sec    = max(0.0, words[s]["start"] - BUFFER_SEC)
                end_sec      = words[e]["end"] + BUFFER_SEC
                lyrics_range = [w["text"] for w in words[s:e+1]]

        else:
            st.info("字幕が取得できませんでした。時間で指定してください。")
            col1, col2 = st.columns(2)
            with col1:
                start_sec = st.number_input("開始（秒）", min_value=0.0, value=0.0, step=0.1, format="%.1f")
            with col2:
                end_sec = st.number_input("終了（秒）", min_value=0.0, value=30.0, step=0.1, format="%.1f")

        st.divider()
        icon = "🔥" if is_cool else "💀"
        if st.button(f"{icon} DBに保存", use_container_width=True, type="primary"):
            entry = {
                "label":        f"{track['uploader']} — {track['title']}",
                "rating":       "cool" if is_cool else "not_cool",
                "video_id":     track["id"],
                "memo":         memo,
                "start_sec":    start_sec,
                "end_sec":      end_sec,
                "lyrics_range": json.dumps(lyrics_range, ensure_ascii=False),
                "analyzed":     False,
            }
            if db_insert(entry):
                st.success("✅ 保存しました！")
            else:
                st.error("保存失敗。Supabase設定を確認してください。")

with tab_db:
    entries = db_select()
    if not entries:
        st.info("まだデータがありません。")
    else:
        cool_c     = sum(1 for e in entries if e.get("rating") == "cool")
        not_cool_c = sum(1 for e in entries if e.get("rating") == "not_cool")
        st.write(f"**合計 {len(entries)}件　😎 {cool_c}件　😐 {not_cool_c}件**")

        filt = st.radio("フィルター", ["すべて", "😎 かっこいいのみ", "😐 かっこよくないのみ"], horizontal=True)

        for entry in entries:
            r = entry.get("rating", "cool")
            if filt == "😎 かっこいいのみ" and r != "cool":
                continue
            if filt == "😐 かっこよくないのみ" and r != "not_cool":
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
                lr = json.loads(entry.get("lyrics_range") or "[]")
                if lr:
                    st.markdown(f"> {''.join(lr)}")
