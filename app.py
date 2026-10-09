import streamlit as st
import yt_dlp
import os
import asyncio
import edge_tts
import google.generativeai as genai
from moviepy.editor import VideoFileClip, AudioFileClip
from PIL import Image, ImageDraw, ImageFont
import requests
from io import BytesIO

# --- Page Config ---
st.set_page_config(page_title="Auto Movie Recap App", page_icon="🎬")
st.title("🎬 AI Auto Movie Recap & Thumbnail Generator")

# --- API Key Setup ---
# Streamlit Cloud ရဲ့ Advanced Settings > Secrets ထဲမှာ GEMINI_API_KEY="your_key" လို့ ထည့်ပါ။
# အကယ်၍ မထည့်ထားရင် UI ကနေ တောင်းပါမယ်။
api_key = st.secrets.get("GEMINI_API_KEY", "")
if not api_key:
    api_key = st.text_input("Enter Google Gemini API Key:", type="password")

if api_key:
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-1.5-flash')
else:
    st.warning("Please enter your Gemini API Key to continue.")
    st.stop()

# --- Functions ---

# 1. Gemini AI ဖြင့် Recap Script ရေးခြင်း (၄ မိနစ်စာ)
def generate_recap(story_text):
    prompt = f"""
    Write a movie recap script in the Myanmar language based on the following story. 
    The script should take exactly around 4 minutes to read aloud (approximately 500-600 words).
    Make it engaging and use natural spoken Myanmar language.
    Story: {story_text}
    """
    response = model.generate_content(prompt)
    return response.text

# 2. Gemini AI ဖြင့် Thumbnail စာသား ရေးခြင်း
def generate_thumbnail_title(story_text):
    prompt = f"""
    Create a short, clickbaity, and engaging Myanmar title (max 5-7 words) for a YouTube video thumbnail based on this story. 
    Output ONLY the Myanmar text. No quotes, no extra words.
    Story: {story_text}
    """
    response = model.generate_content(prompt)
    return response.text.strip()

# 3. Microsoft Edge TTS ဖြင့် မြန်မာအသံပြောင်းခြင်း
async def text_to_speech(text, output_file):
    # my-MM-NilarNeural (Female) or my-MM-ThihaNeural (Male)
    communicate = edge_tts.Communicate(text, "my-MM-NilarNeural")
    await communicate.save(output_file)

def run_tts(text, output_file):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(text_to_speech(text, output_file))

# 4. YouTube မှ Video နှင့် Thumbnail Download ဆွဲခြင်း
def download_youtube_info(url):
    ydl_opts = {
        'format': 'bestvideo[height<=720]+bestaudio/best[height<=720]', # 720p to save Streamlit memory
        'outtmpl': 'downloaded_video.%(ext)s',
        'merge_output_format': 'mp4',
        'quiet': True
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        video_filename = ydl.prepare_filename(info)
        thumbnail_url = info.get('thumbnail', None)
        return video_filename, thumbnail_url

# 5. Thumbnail ကို Crop လုပ်၍ စာသားထည့်ခြင်း
def create_thumbnail(image_url, ratio, title_text, output_path):
    response = requests.get(image_url)
    img = Image.open(BytesIO(response.content))
    
    # ဖြတ်မည့် Ratio တွက်ချက်ခြင်း
    width, height = img.size
    if ratio == "16:9":
        target_ratio = 16 / 9
    else: # 9:16
        target_ratio = 9 / 16
        
    current_ratio = width / height
    if current_ratio > target_ratio:
        # Crop width
        new_width = int(height * target_ratio)
        left = (width - new_width) / 2
        img = img.crop((left, 0, left + new_width, height))
    else:
        # Crop height
        new_height = int(width / target_ratio)
        top = (height - new_height) / 2
        img = img.crop((0, top, width, top + new_height))
        
    # စာသားထည့်ခြင်း
    draw = ImageDraw.Draw(img)
    try:
        # Repository ထဲတွင် Pyidaungsu.ttf ထည့်ထားရပါမည်
        font = ImageFont.truetype("Pyidaungsu.ttf", size=int(img.height * 0.08)) 
    except IOError:
        font = ImageFont.load_default()
        st.warning("Pyidaungsu.ttf font file not found! Using default font.")

    # စာသားပေါ်လွင်စေရန် အနက်ရောင် Outline သုံးခြင်း
    text_color = (255, 255, 255)
    outline_color = (0, 0, 0)
    x, y = 20, img.height - int(img.height * 0.15)
    
    # Draw outline
    thickness = 3
    for adj_x in range(-thickness, thickness+1):
        for adj_y in range(-thickness, thickness+1):
            draw.text((x+adj_x, y+adj_y), title_text, font=font, fill=outline_color)
            
    draw.text((x, y), title_text, font=font, fill=text_color)
    img.save(output_path)

# --- UI Layout ---

youtube_url = st.text_input("Enter YouTube Link:")
story_input = st.text_area("Or Paste AI Story (for Script & Thumbnail Generation):")
ratio = st.selectbox("Select Thumbnail Ratio:", ["16:9", "9:16"])

if st.button("Generate Recap & Thumbnail"):
    if not youtube_url and not story_input:
        st.error("Please enter a YouTube Link or a Story.")
    else:
        try:
            with st.spinner("1. Analyzing and Downloading from YouTube..."):
                video_file = None
                thumb_url = None
                if youtube_url:
                    video_file, thumb_url = download_youtube_info(youtube_url)
                
            with st.spinner("2. Generating Recap Script with Gemini..."):
                content_base = story_input if story_input else "Generate a script based on the visual story of the downloaded video."
                recap_script = generate_recap(content_base)
                st.success("Script generated successfully!")
                with st.expander("Show Generated Script"):
                    st.write(recap_script)
            
            with st.spinner("3. Converting Script to Myanmar Voice..."):
                audio_file = "recap_audio.mp3"
                run_tts(recap_script, audio_file)
                
            with st.spinner("4. Syncing Video and Audio (Cutting first 4 minutes)..."):
                if video_file:
                    final_output = "final_recap_video.mp4"
                    
                    # Video 4 မိနစ် (240 စက္ကန့်) ဖြတ်ခြင်း
                    video_clip = VideoFileClip(video_file).subclip(0, 240)
                    audio_clip = AudioFileClip(audio_file)
                    
                    # အသံဖိုင်အရှည်အတိုင်း Video ကို အံဝင်ခွင်ကျညှိခြင်း
                    video_duration = video_clip.duration
                    audio_duration = audio_clip.duration
                    
                    if audio_duration < video_duration:
                        video_clip = video_clip.subclip(0, audio_duration)
                    
                    # Video ရဲ့ Original အသံကိုဖျက်ပြီး TTS အသံထည့်ခြင်း
                    final_video = video_clip.set_audio(audio_clip)
                    final_video.write_videofile(final_output, codec="libx264", audio_codec="aac", fps=24, preset="ultrafast")
                    
                    # Memory ရှင်းလင်းခြင်း
                    video_clip.close()
                    audio_clip.close()
                    final_video.close()
                    
                    st.video(final_output)
                    with open(final_output, "rb") as file:
                        st.download_button("Download Recap Video", file, file_name="Recap_Video.mp4", mime="video/mp4")

            with st.spinner("5. Generating Thumbnail..."):
                if thumb_url or youtube_url:
                    thumb_title = generate_thumbnail_title(content_base)
                    thumb_output = "thumbnail_final.jpg"
                    
                    # YouTube Link ကနေ Default Thumbnail ဆွဲယူခြင်း (API မလိုပါ)
                    if not thumb_url:
                        video_id = youtube_url.split("v=")[-1].split("&")[0]
                        thumb_url = f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg"
                    
                    create_thumbnail(thumb_url, ratio, thumb_title, thumb_output)
                    st.image(thumb_output, caption=f"Thumbnail ({ratio})")
                    
                    with open(thumb_output, "rb") as file:
                        st.download_button("Download Thumbnail", file, file_name="Thumbnail.jpg", mime="image/jpeg")
                        
            st.success("🎉 All Processing Completed Successfully!")

        except Exception as e:
            st.error(f"An error occurred: {e}")

