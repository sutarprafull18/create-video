# app.py
import streamlit as st
import requests
from bs4 import BeautifulSoup
import pandas as pd
from PIL import Image
import io
import os
import random  # Added missing import
from gtts import gTTS
from moviepy.editor import *
import re
from urllib.parse import urljoin
import urllib.request
import tempfile
from translate import Translator
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()  # Raise exception for bad status codes
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Extract text content
            text_content = []
            for p in soup.find_all(['p', 'h1', 'h2', 'h3']):
                if p.get_text().strip():  # Only add non-empty text
                    text_content.append(p.get_text().strip())
            
            if not text_content:
                raise ValueError("No text content found on the webpage")
            
            # Extract images
            images = []
            for img in soup.find_all('img'):
                src = img.get('src')
                if src:
                    try:
                        if not src.startswith(('http://', 'https://')):
                            src = urljoin(url, src)
                        img_response = requests.get(src, timeout=5)
                        img_response.raise_for_status()
                        img_data = Image.open(io.BytesIO(img_response.content))
                        images.append(img_data)
                    except Exception as img_error:
                        logger.warning(f"Failed to download image {src}: {str(img_error)}")
                        continue
            
            return ' '.join(text_content), images
        except requests.RequestException as e:
            logger.error(f"Error fetching website: {str(e)}")
            raise Exception(f"Failed to fetch website: {str(e)}")
        except Exception as e:
            logger.error(f"Error scraping website: {str(e)}")
            raise Exception(f"Failed to scrape website: {str(e)}")

    def translate_to_hinglish(self, text):
        try:
            translator = Translator(to_lang="hi")
            
            # Split text into sentences
            sentences = re.split('([.!?])', text)
            translated_text = []
            
            for i in range(0, len(sentences)-1, 2):
                sentence = sentences[i] + (sentences[i+1] if i+1 < len(sentences) else '')
                if len(sentence.strip()) > 0:
                    try:
                        if random.random() > 0.5:  # Now random is properly imported
                            translated = translator.translate(sentence)
                            translated_text.append(translated)
                        else:
                            translated_text.append(sentence)
                    except Exception as trans_error:
                        logger.warning(f"Translation failed for sentence: {str(trans_error)}")
                        translated_text.append(sentence)  # Keep original if translation fails
            
            result = ' '.join(translated_text)
            if not result.strip():
                raise ValueError("Translation resulted in empty text")
            return result
        except Exception as e:
            logger.error(f"Error in translation: {str(e)}")
            raise Exception(f"Translation failed: {str(e)}")

    def create_audio(self, text):
        try:
            if not text.strip():
                raise ValueError("Empty text provided for audio generation")
                
            audio_file = os.path.join(self.temp_dir, 'narration.mp3')
            tts = gTTS(text=text, lang='hi')
            tts.save(audio_file)
            
            # Verify the audio file was created
            if not os.path.exists(audio_file):
                raise FileNotFoundError("Audio file was not created")
                
            return audio_file
        except Exception as e:
            logger.error(f"Error creating audio: {str(e)}")
            raise Exception(f"Failed to create audio: {str(e)}")

    def create_video(self, images, audio_file, duration_per_image=5):
        try:
            if not images:
                raise ValueError("No images provided for video creation")
            if not audio_file or not os.path.exists(audio_file):
                raise ValueError("Invalid audio file")
                
            # Save images temporarily
            image_clips = []
            for i, img in enumerate(images):
                try:
                    img_path = os.path.join(self.temp_dir, f'image_{i}.png')
                    img = img.convert('RGB')  # Convert to RGB to avoid alpha channel issues
                    img.save(img_path)
                    img_clip = ImageClip(img_path).set_duration(duration_per_image)
                    img_clip = img_clip.resize(width=1920, height=1080)
                    image_clips.append(img_clip)
                except Exception as img_error:
                    logger.warning(f"Failed to process image {i}: {str(img_error)}")
                    continue

            if not image_clips:
                raise ValueError("No valid images to create video")

            # Concatenate image clips
            final_clip = concatenate_videoclips(image_clips)
            
            # Add audio
            audio = AudioFileClip(audio_file)
            
            # Adjust video/audio duration
            if audio.duration > final_clip.duration:
                final_clip = final_clip.loop(duration=audio.duration)
            else:
                audio = audio.loop(duration=final_clip.duration)
            
            final_clip = final_clip.set_audio(audio)
            
            # Export video
            output_path = os.path.join(self.temp_dir, 'output.mp4')
            final_clip.write_videofile(output_path, fps=24, codec='libx264')
            
            if not os.path.exists(output_path):
                raise FileNotFoundError("Video file was not created")
                
            return output_path
        except Exception as e:
            logger.error(f"Error creating video: {str(e)}")
            raise Exception(f"Failed to create video: {str(e)}")

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
    
    try:
        if st.button("Generate Video"):
            if not url and not text_input:
                st.error("Please provide either a URL or website content")
                return
                
            with st.spinner("Processing..."):
                if url:
                    text, images = st.session_state.processor.scrape_website(url)
                else:
                    text = text_input
                    images = []  # For direct text input, we'll need placeholder images
                    # Create a simple placeholder image
                    img = Image.new('RGB', (1920, 1080), color='white')
                    images = [img]
                
                if text:
                    # Show text preview
                    with st.expander("Show extracted text"):
                        st.write(text)
                    
                    # Translate to Hinglish
                    st.info("Translating content...")
                    hinglish_text = st.session_state.processor.translate_to_hinglish(text)
                    
                    # Show translation preview
                    with st.expander("Show translated text"):
                        st.write(hinglish_text)
                    
                    # Create audio
                    st.info("Generating audio narration...")
                    audio_file = st.session_state.processor.create_audio(hinglish_text)
                    
                    if audio_file:
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
    except Exception as e:
        st.error(f"An error occurred: {str(e)}")
        logger.exception("Application error")

if __name__ == "__main__":
    main()
