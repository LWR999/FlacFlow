# FlacFlow - Music Library Metadata Processing System
## Technical Specification

## Project Context
FlacFlow automates FLAC music library processing for a personal Roon Server setup. It replaces manual metadata processing with a web-based interface for batch operations.

## Current Environment
- **Server**: Ubuntu Server at `downloadserver.local`
- **Storage**: Drobo NAS with FLAC music library
- **Playback**: Roon Server with Mac/iPad clients
- **Existing Tools**: Bash scripts in `/usr/local/bin/` for reference implementation

## Overview
A web-based system to automate FLAC music library metadata processing, artwork embedding, and file organization for Roon Server integration.

## System Architecture
- **Backend**: Python with Flask/FastAPI web framework
- **Frontend**: HTML/CSS/JavaScript web interface
- **Audio Processing**: Mutagen library for FLAC metadata manipulation
- **Image Processing**: Pillow (PIL) for artwork resizing
- **Host**: Ubuntu Server at `downloadserver.local`

## Core Workflow

### 1. Pre-Processing Stage
- System monitors configurable staging directory: `/home/dl/torrents/music/_Pre/`
- Each album exists as a folder containing FLAC files and artwork
- Web interface displays all albums with processing preview and status

### 2. Processing Pipeline
- User selects albums via web interface
- System applies metadata transformations in-place
- Processed albums moved to post-processing area
- Success/error status reported back to web interface

### 3. Post-Processing Stage
- Processed albums stored in: `/home/dl/torrents/music/_Post/`
- Organized into subfolders based on bit depth:
  - `_CD/` for 16-bit albums
  - `_Hires/` for 24-bit albums
- Optional publishing to final music library location

## Folder Structure & Naming Convention

### Expected Input Format
```
{Artist} - {Album} ({Year}) [FLAC] [{BitDepth}B-{SampleRate}kHz] [{Genre}]
```

**Example:**
```
Brian Jackson, Masters At Work - The Revolution Will Not Be Televised (2025) [FLAC] [24B-44.1kHz] [Jazz]
```

### Multi-Disc Detection
- Look for subfolders matching patterns: `Disc 1`, `Disc1`, `CD 1`, `CD1`, etc.
- Handle missing spaces in patterns
- Each disc folder contains FLAC files for that disc

### File Types Handling
- **Keep**: `.flac`, image files (`.jpg`, `.jpeg`, `.png`, `.gif`, `.bmp`)
- **Remove**: `.nfo`, `.txt`, `.m3u`, and any other non-audio/image files
- **Preserve**: `artwork/` and `scans/` folders (and their contents)

## Metadata Processing Rules

### Single Disc Albums

#### Folder Name Parsing
1. Extract Artist from folder name (everything before first " - ")
2. Extract Album from folder name (between " - " and " (")
3. Extract Year from folder name (between "(" and ")")
4. Extract Genre from last bracketed section
5. Extract bit depth and sample rate for file organization

#### Album Name Cleaning
- Remove year information: `(2025)`
- Remove bit depth info: `[24B-44.1kHz]`
- Remove format info: `[FLAC]`
- Replace `&` with `and`
- **Text Formatting Rules**:
  - Capitalization: First letter of each word
  - Lowercase after apostrophes ("don't", "it's")
- Clean result becomes Album metadata tag

#### Track Metadata Updates
- **Album**: Cleaned folder name
- **AlbumArtist**: Artist from folder name (with text formatting applied)
- **Artist**: Individual track artist (with text formatting applied)
- **Genre**: Extracted from folder brackets
- **Track Numbers**: Sequential numbering with total count (e.g., "3 of 12")
- **Text Formatting for Artists**:
  - "featuring" → "feat."
  - " & " → " and " (for artists)
  - Capitalization: First letter of each word
  - Lowercase after apostrophes
- **Compilation Flag**: Set to True if:
  - Artist in folder name is "Various Artists", OR
  - Track artists differ across FLAC files in folder

### Multi-Disc Albums

#### Folder Structure
```
Main Album Folder/
├── Disc 1/
│   ├── track1.flac
│   └── track2.flac
├── Disc 2/
│   ├── track1.flac
│   └── track2.flac
└── cover.jpg
```

#### Track Metadata Updates
- **Album**: Same as single disc processing
- **AlbumArtist**: Same as single disc processing (with text formatting)
- **Artist**: Individual track artist (with text formatting applied)
- **Genre**: Same as single disc processing
- **Track Numbers**: "X of Y" where Y = tracks on this specific disc
- **Disc Numbers**: "X of Y" where Y = total number of discs
- **Compilation Flag**: Same logic as single disc

## Artwork Processing

### Requirements
- Source: `cover.jpg` file in album folder (or main folder for multi-disc)
- Support multiple image formats: `.jpg`, `.jpeg`, `.png`, `.gif`, `.bmp`
- Target: 1200x1200 pixels, 72 DPI
- Format: JPEG

### Process
1. Locate cover art file (prioritize `cover.jpg`, then other image files)
2. Resize image to specifications
3. Embed resized image into all FLAC files in album
4. Delete original cover art file after embedding
5. For multi-disc: embed same artwork in all disc folders

### Web Interface Display
- **Pre-processing**: Display `cover.jpg` thumbnails directly from filesystem
- **Post-processing**: Extract and display embedded artwork from FLAC files
- **Fallback**: Show placeholder image if no artwork available

## Web Interface Specifications

### Main Dashboard (`/`)
- **URL**: `http://downloadserver.local/`
- **Layout**: Card-based grid showing albums in pre-processing area
- **Refresh**: Browser refresh scans filesystem and updates album list

#### Album Cards Display
- Album folder name
- **Artwork thumbnail** (from cover.jpg if available)
- Track count and disc count
- Processing status indicators
- Checkbox for batch selection
- **Delete button** (🗑️ icon with confirmation dialog)

#### Status Indicators
- ✅ Ready for processing
- ⚠️ Warning (edge cases detected)
- 🔄 Currently processing
- ❌ Error state
- 📁 Empty folder (duplicates)

#### Preview Feature
- Hover/click to show transformation preview
- Display: Original → Processed metadata comparison
- Show: Album name, artist, genre, track counts

### Filtering & Views
- **All Albums**: Default view
- **Ready to Process**: Albums without issues
- **Multi-Disc**: Albums with disc subfolders
- **Warnings**: Albums with detected issues
- **Duplicates**: Empty folders with only artwork

### Processing Controls
- **Select All/None** buttons
- **Process Selected** button
- **Delete Selected** button (with confirmation dialog)
- **Refresh** button to scan for new albums
- Progress indicators during processing

### Post-Processing View (`/post`)
- Show processed albums in `_Post/` directory
- **Album cards with embedded artwork thumbnails** (extracted from FLAC metadata)
- Display processing results and timestamps
- **Publish to Library** button for final deployment
- **Delete Selected** button for post-processed albums (with confirmation)

### Metadata Inspector
- **Trigger**: Tooltip/popup on album cards
- **Display**: Current metadata for all tracks
- **Fields**: Title, Artist, Album Artist, Genre, Track X of Y, Disc X of Y

### Configuration Page (`/config`)

#### Directory Paths
- **Pre-processing Path**: `/home/dl/torrents/music/_Pre/`
- **Post-processing Path**: `/home/dl/torrents/music/_Post/`
- **Final Library Path**: `/home/dl/hibiki/media/music/lossless/`

#### Artwork Settings
- **Target Dimensions**: 1200x1200 pixels
- **Target DPI**: 72
- **JPEG Quality**: 85%
- **Source Filename**: `cover.jpg`

#### Album Processing Rules
- **Album Name Replacements**: 
  - `&` → `and`
  - Custom text replacements (configurable list of find/replace pairs)
- **Artist Name Normalization**: Handle "Feat.", "ft.", "&" in artist names (configurable patterns)
- **Genre Extraction**: Always from last bracketed item `[Genre]`
- **Default Genre**: Fallback genre if none detected in folder name
- **Year Extraction**: From parentheses `(YYYY)`
- **Compilation Detection**: Auto-detect Various Artists or mixed track artists

#### Multi-Disc Settings
- **Disc Folder Patterns**: `["Disc 1", "Disc1", "CD 1", "CD1"]` (configurable list)
- **Case Sensitivity**: Ignore case when matching patterns

#### File Management
- **Files to Keep**: `[".flac", ".jpg", ".jpeg", ".png", ".gif", ".bmp"]`
- **Files to Remove**: `[".nfo", ".txt", ".m3u"]` (configurable list)
- **Folders to Preserve**: `["artwork", "scans"]` (case-insensitive)
- **Cover Art Priority**: `cover.jpg` first, then other image files
- **Processing Mode**: In-place processing with move to staging areas

#### Output Organization
- **16-bit Folder Name**: `_CD`
- **24-bit Folder Name**: `_Hires`
- **Final Library 16-bit**: `FLAC 16-Bit CD`
- **Final Library 24-bit**: `FLAC 24-Bit HiRes`

#### Web Interface Settings
- **Batch Processing Limit**: Maximum albums to process simultaneously
- **Delete Confirmation**: Require confirmation for delete operations
- **Show Processing Details**: Display detailed logs during processing
- **Artwork Display Size**: Thumbnail dimensions for web interface

#### Logging & Debugging
- **Log Level**: INFO, DEBUG, WARNING, ERROR
- **Log File Path**: `/var/log/music-processor/`
- **Keep Log History**: Number of days to retain logs
- **Enable Processing Statistics**: Track processing times and success rates

## Error Handling & Edge Cases

### Warning Conditions
- No FLAC files found in folder
- No cover art found (no image files)
- Folder name doesn't match expected format
- Multi-disc structure detected but inconsistent
- Special characters in folder/file names
- Missing disc folders in multi-disc sequence (e.g., Disc 1, Disc 3 but no Disc 2)

### Error Recovery
- Log all errors with timestamps
- Display error details in web interface tooltips
- Allow manual intervention for failed cases
- Preserve original files on critical errors

### Duplicate Detection
- Folders containing only `.jpg` files (no FLAC)
- Move to dedicated duplicates section in interface
- Allow batch cleanup of duplicates

## File Organization Output

### Post-Processing Structure
```
_Post/
├── _CD/
│   └── {Processed 16-bit albums}
└── _Hires/
    └── {Processed 24-bit albums}
```

### Final Library Structure
```
/home/dl/hibiki/media/music/lossless/
├── FLAC 16-Bit CD/
│   └── {Published CD quality albums}
└── FLAC 24-Bit HiRes/
    └── {Published Hi-Res albums}
```

## Technical Implementation Notes

### Required Python Libraries
- `flask` or `fastapi` - Web framework
- `mutagen` - FLAC metadata manipulation
- `Pillow` - Image processing
- `pathlib` - File system operations
- `json` - Configuration management
- `logging` - Error tracking

### Integration with Existing Scripts
- **Location**: Existing bash scripts available in `/usr/local/bin/` on `downloadserver.local`
- **Reference Implementation**: Can reference logic from `setflactrackinfo.sh`, `processalbum.sh`, etc.
- **Text Formatting**: Implement same capitalization and formatting rules as existing scripts
- **Metadata Standards**: Match the metadata approach used in current workflow

### Processing Logic Flow
1. Scan pre-processing directory
2. Parse folder names and validate structure
3. Detect single vs multi-disc albums
4. Generate transformation preview
5. Apply metadata changes on user selection
6. Process and embed artwork
7. Move to appropriate post-processing folder
8. Update web interface with results

### Performance Considerations
- Process albums sequentially to avoid I/O conflicts
- Cache album information to minimize filesystem scans
- Use background processing for large batch operations
- Provide real-time progress updates via WebSocket or polling

### Security & Access
- Local network access only
- No authentication required (private network)
- Read/write permissions for configured directories
- Input validation for file paths and metadata

## Success Criteria
1. **Core Functionality**:
   - Web interface accessible at `http://downloadserver.local/`
   - Successful processing of single and multi-disc albums
   - Proper metadata extraction and cleaning from folder names
   - Artwork resizing and embedding functionality
   - Batch processing capabilities with individual album selection
   - Delete functionality for both pre and post-processed albums

2. **Technical Requirements**:
   - File organization by bit depth (_CD vs _Hires folders)
   - Error handling and duplicate detection
   - Configuration management for directory paths
   - Browser refresh updates album lists from filesystem
   - Artwork thumbnails displayed in web interface

3. **Integration**:
   - Maintains compatibility with existing Roon Server setup
   - Preserves Disc 1/Disc 2 structure for multi-disc albums
   - Follows same metadata standards as existing bash scripts
   - Configurable paths for different deployment scenarios

## Implementation Priority
1. **Phase 1**: Basic single-disc processing with web interface
2. **Phase 2**: Multi-disc album support and batch operations  
3. **Phase 3**: Advanced features (delete, metadata inspection, configuration UI)

## Key Design Decisions Made
- **Multi-disc approach**: Preserve Disc 1/Disc 2 folders (not flattening) for Roon compatibility
- **Web interface**: Simple card-based layout with thumbnails and batch selection
- **Processing workflow**: Pre → Post → Publish pipeline with quality-based organization
- **Artwork handling**: Multiple format support with `cover.jpg` priority
- **Configuration**: File-based config with web UI for common settings