# app.py
import streamlit as st
import requests
from bs4 import BeautifulSoup
import pandas as pd
from PIL import Image
import io
import os
from gtts import gTTS
from moviepy.editor import *
import re
from urllib.parse import urljoin
import urllib.request
import tempfile
from translate import Translator

class WebToVideo:
    def __init__(self):
        self.temp_dir = tempfile.mkdtemp()
        self.image_files = []
        self.audio_file = None
        
    def scrape_website(self, url):
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            response = requests.get(url, headers=headers)
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Extract text content
            text_content = []
            for p in soup.find_all(['p', 'h1', 'h2', 'h3']):
                text_content.append(p.get_text().strip())
            
            # Extract images
            images = []
            for img in soup.find_all('img'):
                src = img.get('src')
                if src:
                    if not src.startswith(('http://', 'https://')):
                        src = urljoin(url, src)
                    try:
                        img_response = requests.get(src)
                        img_data = Image.open(io.BytesIO(img_response.content))
                        images.append(img_data)
                    except:
                        continue
            
            return ' '.join(text_content), images
        except Exception as e:
            st.error(f"Error scraping website: {str(e)}")
            return None, None

    def translate_to_hinglish(self, text):
        translator = Translator(to_lang="hi")
        
        # Split text into sentences
        sentences = re.split('([.!?])', text)
        translated_text = []
        
        for i in range(0, len(sentences)-1, 2):
            sentence = sentences[i] + sentences[i+1]
            # Randomly decide whether to translate to Hindi or keep in English
            if len(sentence.strip()) > 0:
                if random.random() > 0.5:
                    try:
                        translated = translator.translate(sentence)
                        translated_text.append(translated)
                    except:
                        translated_text.append(sentence)
                else:
                    translated_text.append(sentence)
        
        return ' '.join(translated_text)

    def create_audio(self, text):
        try:
            audio_file = os.path.join(self.temp_dir, 'narration.mp3')
            tts = gTTS(text=text, lang='hi')
            tts.save(audio_file)
            return audio_file
        except Exception as e:
            st.error(f"Error creating audio: {str(e)}")
            return None

    def create_video(self, images, audio_file, duration_per_image=5):
        try:
            # Save images temporarily
            image_clips = []
            for i, img in enumerate(images):
                img_path = os.path.join(self.temp_dir, f'image_{i}.png')
                img.save(img_path)
                img_clip = ImageClip(img_path).set_duration(duration_per_image)
                img_clip = img_clip.resize(width=1920, height=1080)
                image_clips.append(img_clip)

            # Concatenate image clips
            final_clip = concatenate_videoclips(image_clips)
            
            # Add audio
            audio = AudioFileClip(audio_file)
            
            # If audio is longer than video, extend video duration
            if audio.duration > final_clip.duration:
                final_clip = final_clip.loop(duration=audio.duration)
            # If video is longer than audio, loop audio
            elif final_clip.duration > audio.duration:
                audio = audio.loop(duration=final_clip.duration)
            
            final_clip = final_clip.set_audio(audio)
            
            # Export video
            output_path = os.path.join(self.temp_dir, 'output.mp4')
            final_clip.write_videofile(output_path, fps=24)
            
            return output_path
        except Exception as e:
            st.error(f"Error creating video: {str(e)}")
            return None

def main():
    st.title("Website to Video Generator")
    st.write("Convert any webpage into a video with Hindi-English mixed narration")
    
    # Initialize session state
    if 'processor' not in st.session_state:
        st.session_state.processor = WebToVideo()
    
    # Input URL
    url = st.text_input("Enter website URL:")
    
    # Or text input
    text_input = st.text_area("Or paste website content directly:")
    
    if st.button("Generate Video"):
        with st.spinner("Processing..."):
            if url:
                text, images = st.session_state.processor.scrape_website(url)
            elif text_input:
                text = text_input
                images = []  # You might want to allow image uploads in this case
            else:
                st.error("Please provide either a URL or website content")
                return
            
            if text:
                # Translate to Hinglish
                st.info("Translating content...")
                hinglish_text = st.session_state.processor.translate_to_hinglish(text)
                
                # Create audio
                st.info("Generating audio narration...")
                audio_file = st.session_state.processor.create_audio(hinglish_text)
                
                if audio_file and (images or text_input):
                    # Create video
                    st.info("Creating video...")
                    video_path = st.session_state.processor.create_video(images, audio_file)
                    
                    if video_path:
                        # Display video
                        st.success("Video generated successfully!")
                        st.video(video_path)
                        
                        # Download button
                        with open(video_path, 'rb') as file:
                            st.download_button(
                                label="Download Video",
                                data=file,
                                file_name="generated_video.mp4",
                                mime="video/mp4"
                            )

if __name__ == "__main__":
    main()

