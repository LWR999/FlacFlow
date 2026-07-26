#!/usr/bin/env python3
"""
FlacFlow - Music Library Metadata Processing System - PRODUCTION VERSION
A web-based tool for automating FLAC music library processing for Roon Server
"""

VERSION = "1.2.1"

import os
import json
import logging
import re
import shutil
import unicodedata
from pathlib import Path
from typing import Dict, List, Optional
import uuid
from io import BytesIO

from flask import Flask, render_template_string, request, jsonify, send_file
from mutagen.flac import FLAC
from mutagen.flac import Picture
from PIL import Image

# Configuration
DEFAULT_CONFIG = {
    "paths": {
        "pre_processing": "/home/dl/torrents/music/_Pre/",
        "post_processing": "/home/dl/torrents/music/_Post/",
        "final_library": "/home/dl/drobos/hibiki/media/music/lossless/"
    },
    "artwork": {
        "target_width": 1200,
        "target_height": 1200,
        "target_dpi": 72,
        "jpeg_quality": 85,
        "source_filename": "cover.jpg"
    },
    "processing": {
        "album_replacements": [["&", "and"], [" And ", " and "], [" THE ", " the "]],
        "artist_replacements": [["featuring", "feat."], ["Featuring", "feat."], [" & ", " and "]],
        "default_genre": "Unknown",
        "multidisc_patterns": ["Disc 1", "Disc1", "CD 1", "CD1", "disc 1", "disc1", "cd 1", "cd1"],
        "files_to_keep": [".flac", ".jpg", ".jpeg", ".png", ".gif", ".bmp"],
        "files_to_remove": [".nfo", ".txt", ".m3u", ".log", ".cue"],
        "folders_to_preserve": ["artwork", "scans", "Artwork", "Scans"]
    },
    "output": {
        "cd_folder": "_CD",
        "hires_folder": "_Hires",
        "final_cd_folder": "FLAC 16-Bit CD",
        "final_hires_folder": "FLAC 24-Bit HiRes"
    }
}

class FlacFlowProcessor:
    def __init__(self, config_path: str = "flacflow_config.json"):
        self.config_path = config_path
        self.config = self.load_config()
        self.setup_logging()
        self.processing_status = {}
    
    def load_config(self) -> Dict:
        if os.path.exists(self.config_path):
            with open(self.config_path, 'r') as f:
                config = json.load(f)
                return self.merge_config(DEFAULT_CONFIG, config)
        else:
            self.save_config(DEFAULT_CONFIG)
            return DEFAULT_CONFIG.copy()
    
    def merge_config(self, default: Dict, user: Dict) -> Dict:
        result = default.copy()
        for key, value in user.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self.merge_config(result[key], value)
            else:
                result[key] = value
        return result
    
    def save_config(self, config: Dict = None) -> None:
        config = config or self.config
        with open(self.config_path, 'w') as f:
            json.dump(config, f, indent=2)
    
    def setup_logging(self) -> None:
        """Setup logging configuration"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('flacflow.log'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
        self.logger.info(f"FlacFlow v{VERSION} initializing...")
    
    def scan_albums(self, directory: str) -> List[Dict]:
        albums = []
        try:
            base_path = Path(directory)
            if not base_path.exists():
                return albums
            
            for item in base_path.iterdir():
                if item.is_dir() and not item.name.startswith('_'):
                    album_info = self.analyze_album(item)
                    albums.append(album_info)
            
            return sorted(albums, key=lambda x: x['name'])
        except Exception as e:
            self.logger.error(f"Error scanning albums: {e}")
            return []
    
    def analyze_album(self, album_path: Path) -> Dict:
        """Analyze a single album directory"""
        album_info = {
            'name': album_path.name,
            'path': str(album_path),
            'status': 'ready',
            'warnings': [],
            'track_count': 0,
            'disc_count': 1,
            'is_multidisc': False,
            'has_flac': False,
            'has_artwork': False,
            'artwork_path': None,
            'bit_depth': '16',
            'is_hires': False,
            'parsed': self.parse_folder_name(album_path.name)
        }
        
        # Check for FLAC files and artwork
        flac_files = list(album_path.glob('*.flac'))
        image_files = []
        for ext in ['.jpg', '.jpeg', '.png', '.gif', '.bmp']:
            image_files.extend(album_path.glob(f'*{ext}'))
            image_files.extend(album_path.glob(f'*{ext.upper()}'))
        
        album_info['has_flac'] = len(flac_files) > 0
        album_info['track_count'] = len(flac_files)
        album_info['has_artwork'] = len(image_files) > 0
        
        if image_files:
            cover_files = [f for f in image_files if 'cover' in f.name.lower()]
            album_info['artwork_path'] = str(cover_files[0] if cover_files else image_files[0])
        
        # Check for multi-disc structure
        disc_folders = self.find_disc_folders(album_path)
        if disc_folders:
            album_info['is_multidisc'] = True
            album_info['disc_count'] = len(disc_folders)
            total_tracks = 0
            for disc_folder in disc_folders:
                disc_flacs = list(disc_folder.glob('*.flac'))
                total_tracks += len(disc_flacs)
            album_info['track_count'] = total_tracks
            album_info['has_flac'] = total_tracks > 0
        
        # Determine bit depth from folder name
        if '[24B-' in album_path.name:
            album_info['bit_depth'] = '24'
            album_info['is_hires'] = True
        
        # Check for warnings
        if not album_info['has_flac']:
            if album_info['has_artwork'] and album_info['track_count'] == 0:
                album_info['status'] = 'duplicate'
                album_info['warnings'].append('No FLAC files found - possible duplicate')
            else:
                album_info['status'] = 'warning'
                album_info['warnings'].append('No FLAC files found')
        
        if not album_info['has_artwork']:
            album_info['warnings'].append('No artwork found')
        
        if not album_info['parsed']['artist'] or not album_info['parsed']['album']:
            album_info['status'] = 'warning'
            album_info['warnings'].append('Could not parse folder name')
        
        return album_info
    
    def parse_folder_name(self, folder_name: str) -> Dict:
        """Parse album folder name to extract metadata"""
        result = {
            'artist': '',
            'album': '',
            'year': '',
            'genre': '',
            'bit_depth': '16',
            'sample_rate': '44.1'
        }
        
        try:
            # Extract genre from last brackets
            genre_match = re.search(r'\[([^\]]+)\](?!\s*\[)', folder_name)
            if genre_match:
                result['genre'] = genre_match.group(1)
            
            # Extract year from parentheses
            year_match = re.search(r'\((\d{4})\)', folder_name)
            if year_match:
                result['year'] = year_match.group(1)
            
            # Extract bit depth and sample rate
            bit_match = re.search(r'\[(\d+)B-([0-9.]+)kHz\]', folder_name)
            if bit_match:
                result['bit_depth'] = bit_match.group(1)
                result['sample_rate'] = bit_match.group(2)
            
            # Extract artist and album (split on first " - ")
            if ' - ' in folder_name:
                parts = folder_name.split(' - ', 1)
                result['artist'] = parts[0].strip()
                
                # Clean up album name
                album = parts[1]
                album = re.sub(r'\(\d{4}\)', '', album)
                album = re.sub(r'\[FLAC\]', '', album)
                album = re.sub(r'\[\d+B-[0-9.]+kHz\]', '', album)
                album = re.sub(r'\[[^\]]+\]$', '', album)
                result['album'] = album.strip()
        
        except Exception as e:
            self.logger.error(f"Error parsing folder name '{folder_name}': {e}")
        
        return result
    
    def find_disc_folders(self, album_path: Path) -> List[Path]:
        """Find disc subdirectories in album"""
        disc_folders = []
        
        try:
            for item in album_path.iterdir():
                if item.is_dir():
                    folder_name = item.name.lower()
                    
                    # Remove quotes and check for disc patterns
                    cleaned_name = folder_name.strip("'\"")
                    
                    # Simple check: does it contain "disc" and a number?
                    if ('disc' in cleaned_name and any(c.isdigit() for c in cleaned_name)) or \
                       ('cd' in cleaned_name and any(c.isdigit() for c in cleaned_name)):
                        disc_folders.append(item)
            
            # Sort by the number in the folder name
            def get_disc_number(path):
                numbers = re.findall(r'\d+', path.name)
                return int(numbers[0]) if numbers else 0
            
            disc_folders.sort(key=get_disc_number)
            return disc_folders
            
        except Exception as e:
            self.logger.error(f"Error finding disc folders in {album_path}: {e}")
            return []
    
    def format_text(self, text: str, is_artist: bool = False) -> str:
        if not text:
            return text
        
        # Apply replacements
        replacements = (self.config['processing']['artist_replacements'] if is_artist 
                       else self.config['processing']['album_replacements'])
        
        for old, new in replacements:
            text = text.replace(old, new)
        
        # Capitalize first letter of each word
        words = text.split()
        formatted_words = []
        
        for word in words:
            if word:
                # Handle apostrophes
                if "'" in word:
                    parts = word.split("'")
                    formatted_parts = [parts[0].capitalize()]
                    for part in parts[1:]:
                        formatted_parts.append(part.lower())
                    formatted_words.append("'".join(formatted_parts))
                else:
                    formatted_words.append(word.capitalize())
        
        return ' '.join(formatted_words)
    
    def delete_album(self, album_path: str) -> Dict:
        """Delete an album directory"""
        try:
            album_path = Path(album_path)
            self.logger.info(f"Deleting album: {album_path}")
            
            if album_path.exists():
                if album_path.is_dir():
                    shutil.rmtree(album_path)
                    self.logger.info(f"Successfully deleted directory: {album_path}")
                else:
                    album_path.unlink()
                    self.logger.info(f"Successfully deleted file: {album_path}")
                return {'success': True}
            else:
                self.logger.warning(f"Album not found: {album_path}")
                return {'success': False, 'error': 'Album not found'}
        except Exception as e:
            self.logger.error(f"Error deleting album {album_path}: {e}")
            return {'success': False, 'error': str(e)}
    
    def process_artwork(self, album_path: Path) -> Optional[bytes]:
        """Process and resize artwork"""
        try:
            # Find artwork file
            image_files = []
            for ext in ['.jpg', '.jpeg', '.png', '.gif', '.bmp']:
                image_files.extend(album_path.glob(f'*{ext}'))
                image_files.extend(album_path.glob(f'*{ext.upper()}'))
            
            if not image_files:
                return None
            
            # Prioritize cover.jpg
            cover_files = [f for f in image_files if 'cover' in f.name.lower()]
            artwork_file = cover_files[0] if cover_files else image_files[0]
            
            # Resize image
            with Image.open(artwork_file) as img:
                # Convert to RGB if necessary
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                
                # Resize to target dimensions
                target_size = (self.config['artwork']['target_width'], 
                              self.config['artwork']['target_height'])
                img = img.resize(target_size, Image.Resampling.LANCZOS)
                
                # Set DPI
                dpi = self.config['artwork']['target_dpi']
                
                # Save to bytes
                img_bytes = BytesIO()
                img.save(img_bytes, format='JPEG', 
                        quality=self.config['artwork']['jpeg_quality'],
                        dpi=(dpi, dpi))
                
                # Delete ALL artwork files after processing
                for img_file in image_files:
                    try:
                        img_file.unlink()
                    except:
                        pass
                
                return img_bytes.getvalue()
                
        except Exception as e:
            self.logger.error(f"Error processing artwork: {e}")
            return None
    
    def update_flac_metadata(self, flac_file: Path, album: str, album_artist: str, 
                           genre: str, track_num: int, total_tracks: int,
                           disc_num: int, total_discs: int, artwork_data: Optional[bytes]) -> None:
        """Update FLAC file metadata"""
        try:
            audio = FLAC(flac_file)
            
            # Get existing artist or use album artist
            track_artist = audio.get('ARTIST', [album_artist])[0] if audio.get('ARTIST') else album_artist
            track_artist = self.format_text(track_artist, is_artist=True)
            
            # Set metadata
            audio['ALBUM'] = album
            audio['ALBUMARTIST'] = album_artist
            audio['ARTIST'] = track_artist
            audio['GENRE'] = genre
            audio['TRACKNUMBER'] = f"{track_num:02d}"
            audio['TRACKTOTAL'] = f"{total_tracks:02d}"
            
            if total_discs > 1:
                audio['DISCNUMBER'] = f"{disc_num}"
                audio['DISCTOTAL'] = f"{total_discs}"
            
            # Set compilation flag if needed
            if album_artist.lower() == 'various artists' or track_artist != album_artist:
                audio['COMPILATION'] = '1'
            
            # Embed artwork
            if artwork_data:
                # Clear existing images
                audio.clear_pictures()
                
                # Add new artwork
                picture = Picture()
                picture.type = 3  # Cover (front)
                picture.mime = 'image/jpeg'
                picture.desc = 'Cover'
                picture.data = artwork_data
                audio.add_picture(picture)
            
            audio.save()
            
        except Exception as e:
            self.logger.error(f"Error updating metadata for {flac_file}: {e}")
    
    def cleanup_files(self, directory: Path) -> None:
        """Remove unwanted files from directory"""
        try:
            files_to_remove = self.config['processing']['files_to_remove']
            folders_to_preserve = self.config['processing']['folders_to_preserve']
            
            for item in directory.iterdir():
                if item.is_file():
                    if item.suffix.lower() in files_to_remove:
                        item.unlink()
                elif item.is_dir():
                    if item.name not in folders_to_preserve:
                        # Check if it's a disc folder, if not remove if empty
                        disc_patterns = self.config['processing']['multidisc_patterns']
                        is_disc = any(item.name.lower().startswith(p.lower()) for p in disc_patterns)
                        if not is_disc and not any(item.iterdir()):
                            item.rmdir()
                            
        except Exception as e:
            self.logger.error(f"Error cleaning up files in {directory}: {e}")

    def normalize_unicode_names(self, path: Path) -> Path:
        """Recursively rename files/folders under path (and path itself) to NFC
        Unicode normalization, so names display consistently on Ubuntu and macOS."""
        try:
            if path.is_dir():
                for child in sorted(path.iterdir()):
                    self.normalize_unicode_names(child)

            normalized_name = unicodedata.normalize('NFC', path.name)
            if normalized_name == path.name:
                return path

            new_path = path.parent / normalized_name
            if new_path.exists():
                self.logger.warning(f"Cannot normalize '{path}' to NFC: '{new_path}' already exists")
                return path

            path.rename(new_path)
            return new_path
        except Exception as e:
            self.logger.error(f"Error normalizing unicode names in {path}: {e}")
            return path

    def process_single_album(self, album_path: Path, album_info: Dict) -> bool:
        """Process a single-disc album"""
        try:
            flac_files = list(album_path.glob('*.flac'))
            parsed = album_info['parsed']
            
            # Format artist and album names
            album_artist = self.format_text(parsed['artist'], is_artist=True)
            album_name = self.format_text(parsed['album'])
            genre = parsed['genre'] or self.config['processing']['default_genre']
            
            # Process artwork
            artwork_data = self.process_artwork(album_path)
            
            # Update metadata for each track
            for i, flac_file in enumerate(sorted(flac_files), 1):
                self.update_flac_metadata(
                    flac_file, album_name, album_artist, genre,
                    i, len(flac_files), 1, 1, artwork_data
                )
            
            # Clean up unwanted files
            self.cleanup_files(album_path)
            
            return True
            
        except Exception as e:
            self.logger.error(f"Error processing single album {album_path}: {e}")
            return False
    
    def process_multidisc_album(self, album_path: Path, album_info: Dict) -> bool:
        """Process a multi-disc album"""
        try:
            disc_folders = self.find_disc_folders(album_path)
            parsed = album_info['parsed']
            
            # Format artist and album names
            album_artist = self.format_text(parsed['artist'], is_artist=True)
            album_name = self.format_text(parsed['album'])
            genre = parsed['genre'] or self.config['processing']['default_genre']
            
            # Process artwork (should be in main folder)
            artwork_data = self.process_artwork(album_path)
            
            total_discs = len(disc_folders)
            
            # Process each disc
            for disc_num, disc_folder in enumerate(disc_folders, 1):
                flac_files = list(disc_folder.glob('*.flac'))
                
                for track_num, flac_file in enumerate(sorted(flac_files), 1):
                    self.update_flac_metadata(
                        flac_file, album_name, album_artist, genre,
                        track_num, len(flac_files), disc_num, total_discs, artwork_data
                    )
            
            # Clean up unwanted files in main folder and disc folders
            self.cleanup_files(album_path)
            for disc_folder in disc_folders:
                self.cleanup_files(disc_folder)
            
            return True
            
        except Exception as e:
            self.logger.error(f"Error processing multi-disc album {album_path}: {e}")
            return False
    
    def move_to_post_processing(self, album_path: Path, is_hires: bool) -> None:
        """Move processed album to post-processing area"""
        try:
            post_base = Path(self.config['paths']['post_processing'])
            
            if is_hires:
                destination_dir = post_base / self.config['output']['hires_folder']
            else:
                destination_dir = post_base / self.config['output']['cd_folder']
            
            destination_dir.mkdir(parents=True, exist_ok=True)
            
            # Parse folder name to create simplified name
            parsed = self.parse_folder_name(album_path.name)
            artist = self.format_text(parsed['artist'], is_artist=True)
            album = self.format_text(parsed['album'])
            
            # Create simplified folder name: "Artist - Album"
            simplified_name = f"{artist} - {album}"
            destination = destination_dir / simplified_name
            
            # Handle duplicate names
            counter = 1
            original_destination = destination
            while destination.exists():
                destination = original_destination.parent / f"{simplified_name} ({counter})"
                counter += 1
            
            # Move the album
            shutil.move(str(album_path), str(destination))
            
        except Exception as e:
            self.logger.error(f"Error moving album to post-processing: {e}")
            raise
    
    def process_album(self, album_path: str) -> Dict:
        """Process a single album"""
        process_id = str(uuid.uuid4())
        self.processing_status[process_id] = {'status': 'processing', 'message': 'Starting...'}
        
        try:
            album_path = Path(album_path)
            album_path = self.normalize_unicode_names(album_path)
            album_info = self.analyze_album(album_path)

            if album_info['status'] in ['warning', 'duplicate']:
                return {'success': False, 'error': 'Album has warnings or is duplicate'}
            
            self.processing_status[process_id]['message'] = 'Processing metadata...'
            
            if album_info['is_multidisc']:
                success = self.process_multidisc_album(album_path, album_info)
            else:
                success = self.process_single_album(album_path, album_info)
            
            if success:
                # Move to post-processing
                self.processing_status[process_id]['message'] = 'Moving to post-processing...'
                self.move_to_post_processing(album_path, album_info['is_hires'])
                self.processing_status[process_id] = {'status': 'complete', 'message': 'Processing complete'}
                return {'success': True, 'process_id': process_id}
            else:
                self.processing_status[process_id] = {'status': 'error', 'message': 'Processing failed'}
                return {'success': False, 'error': 'Processing failed'}
                
        except Exception as e:
            self.logger.error(f"Error processing album {album_path}: {e}")
            self.processing_status[process_id] = {'status': 'error', 'message': str(e)}
            return {'success': False, 'error': str(e)}
    
    def get_embedded_artwork(self, album_path: Path) -> Optional[bytes]:
        """Extract embedded artwork from FLAC files"""
        try:
            # Find first FLAC file in album (or first disc if multi-disc)
            flac_files = list(album_path.glob('*.flac'))
            
            # If no FLAC files in root, check disc folders
            if not flac_files:
                disc_folders = self.find_disc_folders(album_path)
                if disc_folders:
                    flac_files = list(disc_folders[0].glob('*.flac'))
            
            if not flac_files:
                return None
            
            # Get artwork from first FLAC file
            audio = FLAC(flac_files[0])
            if audio.pictures:
                return audio.pictures[0].data
            
            return None
            
        except Exception as e:
            self.logger.error(f"Error extracting embedded artwork: {e}")
            return None
    
    def publish_to_library(self, album_path: str) -> Dict:
        """Publish album from post-processing to final library"""
        try:
            album_path = Path(album_path)
            
            # Determine if it's CD or Hi-Res based on current location
            is_hires = self.config['output']['hires_folder'] in str(album_path)
            
            library_base = Path(self.config['paths']['final_library'])
            
            if is_hires:
                destination_dir = library_base / self.config['output']['final_hires_folder']
            else:
                destination_dir = library_base / self.config['output']['final_cd_folder']
            
            destination_dir.mkdir(parents=True, exist_ok=True)
            destination = destination_dir / album_path.name
            
            # Handle duplicate names
            counter = 1
            original_destination = destination
            while destination.exists():
                destination = original_destination.parent / f"{album_path.name} ({counter})"
                counter += 1
            
            # Move the album
            shutil.move(str(album_path), str(destination))
            
            return {'success': True}
            
        except Exception as e:
            self.logger.error(f"Error publishing album to library: {e}")
            return {'success': False, 'error': str(e)}

# Create processor and verify methods
processor = FlacFlowProcessor()

print("="*60)
print("FlacFlow Production Version - Method Verification")
print(f"FlacFlow v{VERSION}")
print(f"delete_album method exists: {hasattr(processor, 'delete_album')}")
print(f"process_album method exists: {hasattr(processor, 'process_album')}")
print(f"publish_to_library method exists: {hasattr(processor, 'publish_to_library')}")
print("="*60)

# Flask App with Full Interface
app = Flask(__name__)

# Full HTML Template
FULL_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>FlacFlow - Music Library Processor</title>
    <script>
        (function() {
            const stored = localStorage.getItem('flacflow-theme');
            const theme = stored || (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
            document.documentElement.setAttribute('data-theme', theme);
        })();
    </script>
    <style>
        :root {
            --bg: #f5f7fa;
            --header-text: #ffffff;
            --card-bg: #ffffff;
            --card-shadow: rgba(0,0,0,0.1);
            --card-shadow-strong: rgba(0,0,0,0.1);
            --text-primary: #2d3748;
            --text-secondary: #4a5568;
            --accent: #667eea;
            --accent-hover: #5a67d8;
            --danger: #e53e3e;
            --border-warning: #f56565;
            --border-duplicate: #ed8936;
            --artwork-placeholder-bg: #e2e8f0;
            --status-ready-bg: #c6f6d5;
            --status-ready-text: #22543d;
            --status-warning-bg: #fed7d7;
            --status-warning-text: #742a2a;
            --status-duplicate-bg: #fbb6ce;
            --status-duplicate-text: #702459;
            --modal-overlay: rgba(0,0,0,0.5);
            --progress-bg: #f7fafc;
            --progress-border: #e2e8f0;
            --progress-track-bg: #e2e8f0;
        }
        :root[data-theme="dark"] {
            --bg: #1a202c;
            --card-bg: #2d3748;
            --card-shadow: rgba(0,0,0,0.4);
            --card-shadow-strong: rgba(0,0,0,0.5);
            --text-primary: #e2e8f0;
            --text-secondary: #a0aec0;
            --accent: #7c8cf0;
            --accent-hover: #8fa0f5;
            --artwork-placeholder-bg: #4a5568;
            --status-ready-bg: #22543d;
            --status-ready-text: #c6f6d5;
            --status-warning-bg: #742a2a;
            --status-warning-text: #fed7d7;
            --status-duplicate-bg: #702459;
            --status-duplicate-text: #fbb6ce;
            --modal-overlay: rgba(0,0,0,0.7);
            --progress-bg: #2d3748;
            --progress-border: #4a5568;
            --progress-track-bg: #4a5568;
        }
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: var(--bg); color: var(--text-primary); }
        .header { position: relative; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: var(--header-text); padding: 2rem 0; text-align: center; }
        .theme-toggle { position: absolute; top: 1rem; right: 1.5rem; width: 40px; height: 40px; border: none; border-radius: 50%; background: rgba(255,255,255,0.15); color: var(--header-text); font-size: 1.2rem; cursor: pointer; display: flex; align-items: center; justify-content: center; }
        .theme-toggle:hover { background: rgba(255,255,255,0.25); }
        .container { max-width: 1200px; margin: 0 auto; padding: 2rem; }
        .nav-tabs { display: flex; background: var(--card-bg); border-radius: 8px; margin-bottom: 2rem; box-shadow: 0 2px 10px var(--card-shadow); }
        .nav-tab { flex: 1; padding: 1rem; text-align: center; border: none; background: none; color: var(--text-primary); cursor: pointer; font-size: 1rem; }
        .nav-tab.active { background: var(--accent); color: #ffffff; }
        .controls { background: var(--card-bg); padding: 1.5rem; border-radius: 8px; margin-bottom: 2rem; box-shadow: 0 2px 10px var(--card-shadow); }
        .controls button { background: var(--accent); color: #ffffff; border: none; padding: 0.75rem 1.5rem; margin: 0.25rem; border-radius: 6px; cursor: pointer; }
        .controls button:hover { background: var(--accent-hover); }
        .controls button.danger { background: var(--danger); }
        .album-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 1.5rem; }
        .album-card { background: var(--card-bg); border-radius: 12px; padding: 1.5rem; box-shadow: 0 4px 6px var(--card-shadow-strong); }
        .album-card.selected { border: 2px solid var(--accent); }
        .album-card.warning { border-left: 4px solid var(--border-warning); }
        .album-card.duplicate { border-left: 4px solid var(--border-duplicate); }
        .album-header { display: flex; align-items: center; margin-bottom: 1rem; }
        .album-checkbox { margin-right: 1rem; }
        .album-title { flex: 1; font-weight: 600; }
        .album-actions { display: flex; gap: 0.5rem; }
        .btn-small { padding: 0.4rem 0.8rem; font-size: 0.8rem; border: none; border-radius: 4px; cursor: pointer; }
        .btn-delete { background: var(--danger); color: #ffffff; }
        .album-artwork { width: 80px; height: 80px; object-fit: cover; border-radius: 8px; margin-bottom: 1rem; background: var(--artwork-placeholder-bg); }
        .album-info { display: grid; grid-template-columns: 1fr 1fr; gap: 0.5rem; font-size: 0.9rem; }
        .info-label { font-weight: 600; color: var(--text-secondary); }
        .info-value { color: var(--text-primary); }
        .status-badge { padding: 0.25rem 0.75rem; border-radius: 12px; font-size: 0.8rem; font-weight: 600; }
        .status-ready { background: var(--status-ready-bg); color: var(--status-ready-text); }
        .status-warning { background: var(--status-warning-bg); color: var(--status-warning-text); }
        .status-duplicate { background: var(--status-duplicate-bg); color: var(--status-duplicate-text); }
        .warnings { margin-top: 0.5rem; }
        .warning-item { background: var(--status-warning-bg); color: var(--status-warning-text); padding: 0.25rem 0.5rem; border-radius: 4px; font-size: 0.8rem; margin: 0.25rem 0; }
        .tab-content { display: none; }
        .tab-content.active { display: block; }
        .modal { display: none; position: fixed; z-index: 1000; left: 0; top: 0; width: 100%; height: 100%; background: var(--modal-overlay); }
        .modal-content { background: var(--card-bg); color: var(--text-primary); margin: 10% auto; padding: 2rem; width: 90%; max-width: 500px; border-radius: 12px; }
        .modal-buttons { display: flex; gap: 1rem; justify-content: flex-end; margin-top: 1.5rem; }
        .progress-container { background: var(--progress-bg); border: 1px solid var(--progress-border); border-radius: 8px; padding: 1rem; }
        .progress-info { display: flex; justify-content: space-between; margin-bottom: 0.5rem; font-weight: 600; }
        .progress-bar { width: 100%; height: 20px; background: var(--progress-track-bg); border-radius: 10px; overflow: hidden; margin-bottom: 0.5rem; }
        .progress-fill { height: 100%; background: linear-gradient(90deg, #48bb78, #38a169); border-radius: 10px; transition: width 0.3s ease; }
        .progress-details { font-size: 0.9rem; color: var(--text-secondary); }
    </style>
</head>
<body>
    <div class="header">
        <button id="themeToggle" class="theme-toggle" onclick="toggleTheme()" title="Toggle dark/light mode">🌙</button>
        <h1>🎵 FlacFlow</h1>
        <p>Automated FLAC Music Library Processing</p>
    </div>
    
    <div class="container">
        <div class="nav-tabs">
            <button class="nav-tab active" onclick="switchTab('pre')">Pre-Processing</button>
            <button class="nav-tab" onclick="switchTab('post')">Post-Processing</button>
        </div>
        
        <!-- Pre-Processing Tab -->
        <div id="pre-tab" class="tab-content active">
            <div class="controls">
                <button onclick="toggleSelectAll()" id="selectAllBtn">Select All</button>
                <button onclick="processSelected()" id="processBtn">Process Selected</button>
                <button onclick="deleteSelected()" class="danger">Delete Selected</button>
                <button onclick="refreshAlbums()">Refresh</button>
            </div>
            
            <div id="albumGrid" class="album-grid">
                <div>Loading albums...</div>
            </div>
        </div>
        
        <!-- Post-Processing Tab -->
        <div id="post-tab" class="tab-content">
            <div class="controls">
                <button onclick="toggleSelectAllPost()" id="selectAllPostBtn">Select All</button>
                <button onclick="refreshPostAlbums()">Refresh</button>
                <button onclick="publishSelected()" id="publishBtn">Publish to Library</button>
                <button onclick="deleteSelectedPost()" class="danger">Delete Selected</button>
                <div class="progress-container" id="publishProgress" style="display: none; margin-top: 1rem;">
                    <div class="progress-info">
                        <span id="publishCurrentAlbum">Preparing...</span>
                        <span id="publishEstimate" style="float: right;">Estimating...</span>
                    </div>
                    <div class="progress-bar">
                        <div class="progress-fill" id="publishProgressFill" style="width: 0%;"></div>
                    </div>
                    <div class="progress-details">
                        <span id="publishDetails">Starting publish operation...</span>
                    </div>
                </div>
            </div>
            
            <div id="postAlbumGrid" class="album-grid">
                <div>Loading processed albums...</div>
            </div>
        </div>
    </div>
    
    <!-- Delete Confirmation Modal -->
    <div id="deleteModal" class="modal">
        <div class="modal-content">
            <h3>Confirm Deletion</h3>
            <p id="deleteMessage">Are you sure?</p>
            <div class="modal-buttons">
                <button onclick="closeModal()">Cancel</button>
                <button onclick="confirmDelete()" class="danger">Delete</button>
            </div>
        </div>
    </div>

    <script>
        let albums = [];
        let postAlbums = [];
        let selectedAlbums = new Set();
        let selectedPostAlbums = new Set();
        let pendingDelete = null;
        
        function switchTab(tab) {
            document.querySelectorAll('.nav-tab').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
            
            document.querySelector(`[onclick="switchTab('${tab}')"]`).classList.add('active');
            document.getElementById(`${tab}-tab`).classList.add('active');
            
            if (tab === 'pre') {
                refreshAlbums();
            } else if (tab === 'post') {
                refreshPostAlbums();
            }
        }
        
        async function refreshAlbums() {
            try {
                const response = await fetch('/api/albums');
                albums = await response.json();
                selectedAlbums.clear();
                renderAlbums();
            } catch (error) {
                console.error('Error loading albums:', error);
            }
        }
        
        async function refreshPostAlbums() {
            try {
                const response = await fetch('/api/post-albums');
                postAlbums = await response.json();
                selectedPostAlbums.clear();
                renderPostAlbums();
            } catch (error) {
                console.error('Error loading post albums:', error);
            }
        }
        
        function updateSelectAllButton() {
            const selectAllBtn = document.getElementById('selectAllBtn');
            if (!selectAllBtn) return;
            
            const allSelected = albums.length > 0 && 
                               albums.every(album => selectedAlbums.has(album.path));
            
            selectAllBtn.textContent = allSelected ? 'Deselect All' : 'Select All';
        }
        
        function updateSelectAllPostButton() {
            const selectAllPostBtn = document.getElementById('selectAllPostBtn');
            if (!selectAllPostBtn) return;
            
            const allSelected = postAlbums.length > 0 && 
                               postAlbums.every(album => selectedPostAlbums.has(album.path));
            
            selectAllPostBtn.textContent = allSelected ? 'Deselect All' : 'Select All';
        }
        
        function toggleSelectAll() {
            const allSelected = albums.length > 0 && 
                               albums.every(album => selectedAlbums.has(album.path));
            
            if (allSelected) {
                selectedAlbums.clear();
            } else {
                albums.forEach(album => selectedAlbums.add(album.path));
            }
            
            renderAlbums();
        }
        
        function toggleSelectAllPost() {
            const allSelected = postAlbums.length > 0 && 
                               postAlbums.every(album => selectedPostAlbums.has(album.path));
            
            if (allSelected) {
                selectedPostAlbums.clear();
            } else {
                postAlbums.forEach(album => selectedPostAlbums.add(album.path));
            }
            
            renderPostAlbums();
        }
        
        function renderAlbums() {
            const grid = document.getElementById('albumGrid');
            
            if (albums.length === 0) {
                grid.innerHTML = '<div>No albums found</div>';
                updateSelectAllButton();
                return;
            }
            
            grid.innerHTML = albums.map(album => `
                <div class="album-card ${album.status} ${selectedAlbums.has(album.path) ? 'selected' : ''}" 
                     data-path="${album.path}">
                    <div class="album-header">
                        <input type="checkbox" class="album-checkbox" 
                               ${selectedAlbums.has(album.path) ? 'checked' : ''}
                               onchange="toggleAlbum('${album.path}')">
                        <div class="album-title">${album.name}</div>
                        <div class="album-actions">
                            <button class="btn-small btn-delete" onclick="deleteSingle('${album.path}')">🗑️</button>
                        </div>
                    </div>
                    
                    ${album.artwork_path ? 
                        `<img src="/api/artwork?path=${encodeURIComponent(album.artwork_path)}" class="album-artwork" onerror="this.style.display='none'">` :
                        '<div class="album-artwork">No Art</div>'
                    }
                    
                    <div class="album-info">
                        <span class="info-label">Tracks:</span>
                        <span class="info-value">${album.track_count}</span>
                        <span class="info-label">Discs:</span>
                        <span class="info-value">${album.disc_count} ${album.is_multidisc ? '(Multi)' : ''}</span>
                        <span class="info-label">Quality:</span>
                        <span class="info-value">${album.bit_depth}-bit</span>
                        <span class="info-label">Status:</span>
                        <span class="status-badge status-${album.status}">${album.status}</span>
                    </div>
                    
                    ${album.warnings.length > 0 ? `
                        <div class="warnings">
                            ${album.warnings.map(warning => `<div class="warning-item">${warning}</div>`).join('')}
                        </div>
                    ` : ''}
                </div>
            `).join('');
            
            updateSelectAllButton();
        }
        
        function renderPostAlbums() {
            const grid = document.getElementById('postAlbumGrid');
            
            if (postAlbums.length === 0) {
                grid.innerHTML = '<div>No processed albums found</div>';
                updateSelectAllPostButton();
                return;
            }
            
            grid.innerHTML = postAlbums.map(album => `
                <div class="album-card ${selectedPostAlbums.has(album.path) ? 'selected' : ''}" 
                     data-path="${album.path}">
                    <div class="album-header">
                        <input type="checkbox" class="album-checkbox" 
                               ${selectedPostAlbums.has(album.path) ? 'checked' : ''}
                               onchange="togglePostAlbum('${album.path}')">
                        <div class="album-title">${album.name}</div>
                        <div class="album-actions">
                            <button class="btn-small btn-delete" onclick="deletePostSingle('${album.path}')">🗑️</button>
                        </div>
                    </div>
                    
                    <img src="/api/embedded-artwork?path=${encodeURIComponent(album.path)}" 
                         class="album-artwork" 
                         onerror="this.style.display='none';">
                    
                    <div class="album-info">
                        <span class="info-label">Tracks:</span>
                        <span class="info-value">${album.track_count}</span>
                        <span class="info-label">Quality:</span>
                        <span class="info-value">${album.is_hires ? 'Hi-Res' : 'CD'}</span>
                    </div>
                </div>
            `).join('');
            
            updateSelectAllPostButton();
        }
        
        function toggleAlbum(path) {
            if (selectedAlbums.has(path)) {
                selectedAlbums.delete(path);
            } else {
                selectedAlbums.add(path);
            }
            renderAlbums();
        }
        
        function togglePostAlbum(path) {
            if (selectedPostAlbums.has(path)) {
                selectedPostAlbums.delete(path);
            } else {
                selectedPostAlbums.add(path);
            }
            renderPostAlbums();
        }
        
        async function processSelected() {
            if (selectedAlbums.size === 0) {
                alert('Please select albums to process');
                return;
            }
            
            const processBtn = document.getElementById('processBtn');
            processBtn.disabled = true;
            processBtn.textContent = 'Processing...';
            
            for (const albumPath of selectedAlbums) {
                try {
                    const response = await fetch('/api/process', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ album_path: albumPath })
                    });
                    
                    const result = await response.json();
                    if (!result.success) {
                        console.error(`Failed to process ${albumPath}:`, result.error);
                    }
                } catch (error) {
                    console.error(`Error processing ${albumPath}:`, error);
                }
            }
            
            processBtn.disabled = false;
            processBtn.textContent = 'Process Selected';
            alert('Processing complete!');
            refreshAlbums();
        }
        
        function deleteSingle(path) {
            pendingDelete = { type: 'single', paths: [path] };
            document.getElementById('deleteMessage').textContent = 
                `Delete "${path.split('/').pop()}"?`;
            document.getElementById('deleteModal').style.display = 'block';
        }
        
        function deleteSelected() {
            if (selectedAlbums.size === 0) {
                alert('Please select albums to delete');
                return;
            }
            
            pendingDelete = { type: 'multiple', paths: Array.from(selectedAlbums) };
            document.getElementById('deleteMessage').textContent = 
                `Delete ${selectedAlbums.size} selected album(s)?`;
            document.getElementById('deleteModal').style.display = 'block';
        }
        
        function deletePostSingle(path) {
            pendingDelete = { type: 'post-single', paths: [path] };
            document.getElementById('deleteMessage').textContent = 
                `Delete "${path.split('/').pop()}"?`;
            document.getElementById('deleteModal').style.display = 'block';
        }
        
        function deleteSelectedPost() {
            if (selectedPostAlbums.size === 0) {
                alert('Please select albums to delete');
                return;
            }
            
            pendingDelete = { type: 'post-multiple', paths: Array.from(selectedPostAlbums) };
            document.getElementById('deleteMessage').textContent = 
                `Delete ${selectedPostAlbums.size} selected album(s)?`;
            document.getElementById('deleteModal').style.display = 'block';
        }
        
        async function confirmDelete() {
            if (!pendingDelete) return;
            
            let successCount = 0;
            
            for (const path of pendingDelete.paths) {
                try {
                    const response = await fetch('/api/delete', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ album_path: path })
                    });
                    
                    const result = await response.json();
                    if (result.success) {
                        successCount++;
                    }
                } catch (error) {
                    console.error(`Error deleting ${path}:`, error);
                }
            }
            
            closeModal();
            alert(`Successfully deleted ${successCount} album(s)`);
            
            // Refresh appropriate view
            if (pendingDelete.type.startsWith('post')) {
                selectedPostAlbums.clear();
                refreshPostAlbums();
            } else {
                selectedAlbums.clear();
                refreshAlbums();
            }
            
            pendingDelete = null;
        }
        
        async function publishSelected() {
            if (selectedPostAlbums.size === 0) {
                alert('Please select albums to publish');
                return;
            }
            
            const publishBtn = document.getElementById('publishBtn');
            const progressContainer = document.getElementById('publishProgress');
            const currentAlbumSpan = document.getElementById('publishCurrentAlbum');
            const estimateSpan = document.getElementById('publishEstimate');
            const progressFill = document.getElementById('publishProgressFill');
            const detailsSpan = document.getElementById('publishDetails');
            
            // Disable UI and show progress
            publishBtn.disabled = true;
            publishBtn.textContent = 'Publishing...';
            progressContainer.style.display = 'block';
            
            const albumPaths = Array.from(selectedPostAlbums);
            const totalAlbums = albumPaths.length;
            let completedAlbums = 0;
            let startTime = Date.now();
            
            for (let i = 0; i < albumPaths.length; i++) {
                const albumPath = albumPaths[i];
                const albumName = albumPath.split('/').pop();
                
                // Update current album
                currentAlbumSpan.textContent = `Publishing: ${albumName}`;
                detailsSpan.textContent = `Album ${i + 1} of ${totalAlbums} - Moving to library...`;
                
                // Calculate time estimates
                const elapsedTime = (Date.now() - startTime) / 1000;
                const avgTimePerAlbum = completedAlbums > 0 ? elapsedTime / completedAlbums : 30;
                const remainingAlbums = totalAlbums - completedAlbums;
                const estimatedRemainingTime = remainingAlbums * avgTimePerAlbum;
                
                // Update progress
                const progressPercent = (completedAlbums / totalAlbums) * 100;
                progressFill.style.width = `${progressPercent}%`;
                
                if (estimatedRemainingTime > 60) {
                    const minutes = Math.ceil(estimatedRemainingTime / 60);
                    estimateSpan.textContent = `~${minutes} min remaining`;
                } else {
                    estimateSpan.textContent = `~${Math.ceil(estimatedRemainingTime)}s remaining`;
                }
                
                try {
                    const albumStartTime = Date.now();
                    
                    const response = await fetch('/api/publish', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ album_path: albumPath })
                    });
                    
                    const result = await response.json();
                    
                    if (result.success) {
                        completedAlbums++;
                        const albumTime = (Date.now() - albumStartTime) / 1000;
                        detailsSpan.textContent = `Completed: ${albumName} (${albumTime.toFixed(1)}s)`;
                    } else {
                        console.error(`Failed to publish ${albumPath}:`, result.error);
                        detailsSpan.textContent = `Failed: ${albumName} - ${result.error}`;
                    }
                } catch (error) {
                    console.error(`Error publishing ${albumPath}:`, error);
                    detailsSpan.textContent = `Error: ${albumName} - Network error`;
                }
                
                // Small delay to let UI update
                await new Promise(resolve => setTimeout(resolve, 100));
            }
            
            // Final update
            progressFill.style.width = '100%';
            currentAlbumSpan.textContent = 'Publishing Complete!';
            estimateSpan.textContent = `${completedAlbums}/${totalAlbums} successful`;
            detailsSpan.textContent = `All albums processed in ${((Date.now() - startTime) / 1000).toFixed(1)} seconds`;
            
            // Re-enable UI after a brief display of completion
            setTimeout(() => {
                publishBtn.disabled = false;
                publishBtn.textContent = 'Publish to Library';
                progressContainer.style.display = 'none';
                
                alert(`Publishing complete! ${completedAlbums}/${totalAlbums} albums successfully moved to library.`);
                refreshPostAlbums();
            }, 2000);
        }
        
        function closeModal() {
            document.querySelectorAll('.modal').forEach(modal => {
                modal.style.display = 'none';
            });
        }

        function syncThemeToggleIcon() {
            const theme = document.documentElement.getAttribute('data-theme') || 'light';
            document.getElementById('themeToggle').textContent = theme === 'dark' ? '☀️' : '🌙';
        }

        function toggleTheme() {
            const current = document.documentElement.getAttribute('data-theme') || 'light';
            const next = current === 'dark' ? 'light' : 'dark';
            document.documentElement.setAttribute('data-theme', next);
            localStorage.setItem('flacflow-theme', next);
            syncThemeToggleIcon();
        }

        // Initialize
        document.addEventListener('DOMContentLoaded', function() {
            syncThemeToggleIcon();
            refreshAlbums();

            window.onclick = function(event) {
                if (event.target.classList.contains('modal')) {
                    closeModal();
                }
            }
        });
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    return FULL_TEMPLATE

@app.route('/api/albums')
def get_albums():
    albums = processor.scan_albums(processor.config['paths']['pre_processing'])
    return jsonify(albums)

@app.route('/api/post-albums')
def get_post_albums():
    """Get albums from post-processing directory"""
    post_albums = []
    
    try:
        post_base = Path(processor.config['paths']['post_processing'])
        
        # Scan both CD and Hi-Res folders
        for folder_name, is_hires in [
            (processor.config['output']['cd_folder'], False),
            (processor.config['output']['hires_folder'], True)
        ]:
            folder_path = post_base / folder_name
            if folder_path.exists():
                for album_dir in folder_path.iterdir():
                    if album_dir.is_dir():
                        # Get basic info about processed album
                        flac_count = len(list(album_dir.glob('*.flac')))
                        
                        # Check for multi-disc
                        disc_folders = processor.find_disc_folders(album_dir)
                        if disc_folders:
                            flac_count = 0
                            for disc_folder in disc_folders:
                                flac_count += len(list(disc_folder.glob('*.flac')))
                        
                        post_albums.append({
                            'name': album_dir.name,
                            'path': str(album_dir),
                            'track_count': flac_count,
                            'is_hires': is_hires,
                            'has_artwork': True
                        })
    
    except Exception as e:
        processor.logger.error(f"Error scanning post albums: {e}")
    
    return jsonify(post_albums)

@app.route('/api/artwork')
def get_artwork():
    """Serve artwork thumbnails"""
    artwork_path = request.args.get('path')
    if not artwork_path or not os.path.exists(artwork_path):
        return '', 404
    
    try:
        return send_file(artwork_path, mimetype='image/jpeg')
    except Exception as e:
        processor.logger.error(f"Error serving artwork: {e}")
        return '', 404

@app.route('/api/embedded-artwork')
def get_embedded_artwork():
    """Serve embedded artwork from FLAC files"""
    album_path = request.args.get('path')
    if not album_path or not os.path.exists(album_path):
        return '', 404
    
    try:
        artwork_data = processor.get_embedded_artwork(Path(album_path))
        if artwork_data:
            return send_file(BytesIO(artwork_data), mimetype='image/jpeg')
        else:
            return '', 404
    except Exception as e:
        processor.logger.error(f"Error serving embedded artwork: {e}")
        return '', 404

@app.route('/api/process', methods=['POST'])
def process_album():
    """Process a single album"""
    data = request.get_json()
    album_path = data.get('album_path')
    
    if not album_path:
        return jsonify({'success': False, 'error': 'No album path provided'})
    
    result = processor.process_album(album_path)
    return jsonify(result)

@app.route('/api/delete', methods=['POST'])
def delete_album():
    """Delete an album"""
    data = request.get_json()
    album_path = data.get('album_path')
    
    if not album_path:
        return jsonify({'success': False, 'error': 'No album path provided'})
    
    result = processor.delete_album(album_path)
    return jsonify(result)

@app.route('/api/publish', methods=['POST'])
def publish_album():
    """Publish album to final library"""
    data = request.get_json()
    album_path = data.get('album_path')
    
    if not album_path:
        return jsonify({'success': False, 'error': 'No album path provided'})
    
    result = processor.publish_to_library(album_path)
    return jsonify(result)

if __name__ == '__main__':
    # Create required directories
    for path_key in ['pre_processing', 'post_processing', 'final_library']:
        path = processor.config['paths'][path_key]
        Path(path).mkdir(parents=True, exist_ok=True)
    
    # Create post-processing subfolders
    post_base = Path(processor.config['paths']['post_processing'])
    (post_base / processor.config['output']['cd_folder']).mkdir(exist_ok=True)
    (post_base / processor.config['output']['hires_folder']).mkdir(exist_ok=True)
    
    print(f"FlacFlow v{VERSION} Production starting on port 5000...")
    app.run(host='0.0.0.0', port=5000, debug=False)
