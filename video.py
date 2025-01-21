import os
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from moviepy.editor import ImageClip, VideoClip, AudioFileClip, concatenate_videoclips, CompositeAudioClip, cross_dissolve
import logging
import streamlit as st
import requests
from bs4 import BeautifulSoup
from gtts import gTTS
from googletrans import Translator
import tempfile
import io
import shutil
from pathlib import Path

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# First define all helper functions
def apply_sepia(img):
    width, height = img.size
    pixels = img.load()
    for x in range(width):
        for y in range(height):
            r, g, b = pixels[x, y]
            tr = int(0.393 * r + 0.769 * g + 0.189 * b)
            tg = int(0.349 * r + 0.686 * g + 0.168 * b)
            tb = int(0.272 * r + 0.534 * g + 0.131 * b)
            pixels[x, y] = (min(tr, 255), min(tg, 255), min(tb, 255))
    return img

def slide_transition(clip1, clip2, direction='left'):
    w, h = clip1.size
    def make_frame(t):
        if direction == 'left':
            offset = int(w * t)
            new_clip = np.zeros((h, w, 3))
            new_clip[:, :w-offset] = clip1.get_frame(0)[:, offset:]
            new_clip[:, w-offset:] = clip2.get_frame(0)[:, :offset]
        else:
            offset = int(w * (1-t))
            new_clip = np.zeros((h, w, 3))
            new_clip[:, :offset] = clip2.get_frame(0)[:, w-offset:]
            new_clip[:, offset:] = clip1.get_frame(0)[:, :w-offset]
        return new_clip
    return VideoClip(make_frame, duration=1)

def zoom_transition(clip1, clip2):
    w, h = clip1.size
    def make_frame(t):
        zoom = t
        frame1 = clip1.get_frame(0)
        frame2 = clip2.get_frame(0)
        merged = frame1 * (1-zoom) + frame2 * zoom
        return merged
    return VideoClip(make_frame, duration=1)

def rotate_transition(clip1, clip2):
    w, h = clip1.size
    def make_frame(t):
        angle = t * 180
        frame1 = np.array(Image.fromarray(clip1.get_frame(0)).rotate(angle))
        frame2 = np.array(Image.fromarray(clip2.get_frame(0)).rotate(-angle))
        merged = frame1 * (1-t) + frame2 * t
        return merged
    return VideoClip(make_frame, duration=1)

def mix_audio(main_audio, bg_music, bg_volume=0.3):
    if bg_music.duration > main_audio.duration:
        bg_music = bg_music.subclip(0, main_audio.duration)
    else:
        bg_music = bg_music.loop(duration=main_audio.duration)
    bg_music = bg_music.volumex(bg_volume)
    final_audio = CompositeAudioClip([main_audio, bg_music])
    return final_audio

# Configuration dictionaries
TRANSITION_EFFECTS = {
    'fade': lambda clip1, clip2: clip1.crossfadeout(1).crossfadein(1),
    'slide_left': lambda clip1, clip2: slide_transition(clip1, clip2, 'left'),
    'slide_right': lambda clip1, clip2: slide_transition(clip1, clip2, 'right'),
    'zoom': lambda clip1, clip2: zoom_transition(clip1, clip2),
    'rotate': lambda clip1, clip2: rotate_transition(clip1, clip2),
}

IMAGE_FILTERS = {
    'none': lambda img: img,
    'grayscale': lambda img: img.convert('L').convert('RGB'),
    'sepia': apply_sepia,
    'blur': lambda img: img.filter(ImageFilter.GaussianBlur(2)),
    'sharpen': lambda img: img.filter(ImageFilter.SHARPEN),
    'edge_enhance': lambda img: img.filter(ImageFilter.EDGE_ENHANCE),
}

FONT_STYLES = {
    'regular': 'arial.ttf',
    'bold': 'arialbd.ttf',
    'condensed': 'arialnb.ttf',
}

class WebToVideo:
    def __init__(self):
        self.temp_dir = tempfile.mkdtemp()
        logger.info(f"Created temporary directory: {self.temp_dir}")
        self.translator = Translator()
        
    def __del__(self):
        try:
            shutil.rmtree(self.temp_dir)
        except Exception as e:
            logger.error(f"Error cleaning up temp directory: {str(e)}")

    def scrape_website(self, url):
        try:
            response = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'})
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')
            
            text_elements = soup.find_all(['p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6'])
            text = ' '.join([elem.get_text() for elem in text_elements])
            
            images = []
            for img_tag in soup.find_all('img', src=True):
                try:
                    img_url = img_tag['src']
                    if not img_url.startswith('http'):
                        if img_url.startswith('//'):
                            img_url = 'https:' + img_url
                        else:
                            base_url = '/'.join(url.split('/')[:3])
                            img_url = f"{base_url}/{img_url.lstrip('/')}"
                    
                    img_response = requests.get(img_url)
                    img_response.raise_for_status()
                    img = Image.open(io.BytesIO(img_response.content)).convert('RGB')
                    images.append(img)
                except Exception as e:
                    logger.warning(f"Failed to process image {img_url}: {str(e)}")
                    continue
            
            if not images:
                images = [self.create_default_image(text[:200])]
                
            return text, images
        except Exception as e:
            logger.error(f"Error scraping website: {str(e)}")
            return "", [self.create_default_image("Failed to scrape website")]

    def create_default_image(self, text):
        try:
            width, height = 1280, 720
            image = Image.new('RGB', (width, height), 'white')
            draw = ImageDraw.Draw(image)
            
            try:
                font = ImageFont.truetype(FONT_STYLES['regular'], 40)
            except:
                font = ImageFont.load_default()
            
            words = text.split()
            lines = []
            current_line = []
            
            for word in words:
                current_line.append(word)
                line_width = draw.textlength(' '.join(current_line), font=font)
                if line_width > width - 100:
                    if len(current_line) > 1:
                        current_line.pop()
                        lines.append(' '.join(current_line))
                        current_line = [word]
                    else:
                        lines.append(word)
                        current_line = []
            
            if current_line:
                lines.append(' '.join(current_line))
            
            y = height/2 - (len(lines) * 50)/2
            for line in lines:
                text_width = draw.textlength(line, font=font)
                x = (width - text_width) / 2
                draw.text((x, y), line, font=font, fill='black')
                y += 50
            
            return image
        except Exception as e:
            logger.error(f"Error creating default image: {str(e)}")
            return Image.new('RGB', (1280, 720), 'white')

    def translate_to_hinglish(self, text):
        try:
            # First translate to Hindi
            hindi = self.translator.translate(text, dest='hi').text
            # Then transliterate back to English
            hinglish = self.translator.translate(hindi, dest='en', src='hi').text
            return hinglish
        except Exception as e:
            logger.warning(f"Translation failed: {str(e)}. Using original text.")
            return text

    def create_audio(self, text):
        try:
            audio_path = os.path.join(self.temp_dir, 'audio.mp3')
            tts = gTTS(text=text, lang='en')
            tts.save(audio_path)
            return audio_path
        except Exception as e:
            logger.error(f"Error creating audio: {str(e)}")
            # Create a silent audio file as fallback
            silent_audio = AudioFileClip(duration=5)
            silent_audio.write_audiofile(audio_path)
            return audio_path

    def create_video_with_effects(self, images, audio_file, 
                                transition_effect='fade',
                                bg_music_path=None,
                                bg_volume=0.3,
                                image_filter='none',
                                text_overlay=None,
                                duration_per_image=5):
        try:
            if not images:
                raise ValueError("No images provided for video creation")
            
            image_clips = []
            for i, img in enumerate(images):
                try:
                    img = IMAGE_FILTERS[image_filter](img)
                    
                    if text_overlay:
                        draw = ImageDraw.Draw(img)
                        try:
                            font = ImageFont.truetype(FONT_STYLES['regular'], 60)
                        except:
                            font = ImageFont.load_default()
                        text = text_overlay.format(slide_number=i+1)
                        w, h = draw.textlength(text, font=font), 60
                        draw.text(((img.width-w)/2, img.height-100), 
                                text, 
                                font=font, 
                                fill='white',
                                stroke_width=2,
                                stroke_fill='black')
                    
                    img_path = os.path.join(self.temp_dir, f'image_{i}.png')
                    img.save(img_path)
                    clip = ImageClip(img_path).set_duration(duration_per_image)
                    image_clips.append(clip)
                except Exception as e:
                    logger.warning(f"Failed to process image {i}: {str(e)}")
                    continue
            
            clips_with_transitions = []
            transition_func = TRANSITION_EFFECTS.get(transition_effect, TRANSITION_EFFECTS['fade'])
            
            for i in range(len(image_clips)-1):
                clips_with_transitions.append(image_clips[i])
                transition = transition_func(image_clips[i], image_clips[i+1])
                clips_with_transitions.append(transition)
            clips_with_transitions.append(image_clips[-1])
            
            final_clip = concatenate_videoclips(clips_with_transitions, method="compose")
            
            main_audio = AudioFileClip(audio_file)
            if bg_music_path and os.path.exists(bg_music_path):
                bg_music = AudioFileClip(bg_music_path)
                final_audio = mix_audio(main_audio, bg_music, bg_volume)
            else:
                final_audio = main_audio
            
            if final_audio.duration > final_clip.duration:
                final_clip = final_clip.loop(duration=final_audio.duration)
            else:
                final_audio = final_audio.loop(duration=final_clip.duration)
            
            final_clip = final_clip.set_audio(final_audio)
            
            output_path = os.path.join(self.temp_dir, 'output.mp4')
            final_clip.write_videofile(output_path, fps=24, codec='libx264', audio_codec='aac')
            
            return output_path
        except Exception as e:
            logger.error(f"Error in create_video_with_effects: {str(e)}")
            raise Exception(f"Failed to create video with effects: {str(e)}")

[Previous code remains exactly the same until the main() function...]

def main():
    st.title("Enhanced Website to Video Generator")
    st.write("Convert any webpage into a video with advanced customization options")
    
    # Initialize session state
    if 'processor' not in st.session_state:
        st.session_state.processor = WebToVideo()
    
    # Create tabs for different input methods
    tab1, tab2 = st.tabs(["URL Input", "Direct Text Input"])
    
    with tab1:
        url = st.text_input("Enter website URL:")
    
    with tab2:
        text_input = st.text_area("Paste website content directly:")
    
    # Customization options in an expander
    with st.expander("Customization Options", expanded=False):
        col1, col2 = st.columns(2)
        
        with col1:
            transition_effect = st.selectbox(
                "Transition Effect",
                options=list(TRANSITION_EFFECTS.keys())
            )
            
            image_filter = st.selectbox(
                "Image Filter",
                options=list(IMAGE_FILTERS.keys())
            )
            
            duration = st.slider(
                "Seconds per Slide",
                min_value=3,
                max_value=10,
                value=5
            )
        
        with col2:
            text_overlay = st.text_input(
                "Text Overlay Template",
                value="Slide {slide_number}",
                help="Use {slide_number} for automatic numbering"
            )
            
            bg_music = st.file_uploader(
                "Background Music (optional)",
                type=['mp3', 'wav']
            )
            
            if bg_music:
                bg_volume = st.slider(
                    "Background Music Volume",
                    min_value=0.0,
                    max_value=1.0,
                    value=0.3,
                    step=0.1
                )
    
    try:
        if st.button("Generate Video", type="primary"):
            if not url and not text_input:
                st.error("Please provide either a URL or website content")
                return
            
            with st.spinner("Processing..."):
                # Save background music if provided
                bg_music_path = None
                if bg_music:
                    bg_music_path = os.path.join(st.session_state.processor.temp_dir, 'bg_music.mp3')
                    with open(bg_music_path, 'wb') as f:
                        f.write(bg_music.read())
                
                # Process content
                with st.status("Getting content...") as status:
                    if url:
                        text, images = st.session_state.processor.scrape_website(url)
                    else:
                        text = text_input
                        images = [st.session_state.processor.create_default_image(text)]
                    
                    status.update(label="Translating content...")
                    hinglish_text = st.session_state.processor.translate_to_hinglish(text)
                    
                    status.update(label="Generating audio...")
                    audio_file = st.session_state.processor.create_audio(hinglish_text)
                    
                    if audio_file:
                        status.update(label="Creating video with effects...")
                        video_path = st.session_state.processor.create_video_with_effects(
                            images=images,
                            audio_file=audio_file,
                            transition_effect=transition_effect,
                            bg_music_path=bg_music_path,
                            bg_volume=bg_volume if bg_music else None,
                            image_filter=image_filter,
                            text_overlay=text_overlay,
                            duration_per_image=duration
                        )
                        
                        if video_path:
                            st.success("Video generated successfully!")
                            st.video(video_path)
                            
                            with open(video_path, 'rb') as file:
                                st.download_button(
                                    label="Download Video",
                                    data=file,
                                    file_name="generated_video.mp4",
                                    mime="video/mp4"
                                )
                            
                            # Show video details
                            st.json({
                                "Duration": f"{duration * len(images)} seconds",
                                "Transition Effect": transition_effect,
                                "Image Filter": image_filter,
                                "Background Music": "Yes" if bg_music else "No"
                            })
                
    except Exception as e:
        st.error(f"An error occurred: {str(e)}")
        logger.exception("Application error")

if __name__ == "__main__":
    main()

if __name__ == "__main__":
    main()
