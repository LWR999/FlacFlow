# FlacFlow Deployment Guide

## Prerequisites

### 1. Install Required System Packages
```bash
sudo apt update
sudo apt install python3 python3-pip python3-venv flac ffmpeg imagemagick
```

### 2. Create Project Directory
```bash
cd /home/dl
mkdir flacflow
cd flacflow
```

### 3. Create Python Virtual Environment
```bash
python3 -m venv venv
source venv/bin/activate
```

### 4. Install Python Dependencies
```bash
pip install flask mutagen pillow pathlib2
```

## Installation Steps

### 1. Save the FlacFlow Application
Create the main application file:
```bash
nano flacflow.py
```

Copy and paste the entire FlacFlow application code from the artifact into this file.

### 2. Make the Script Executable
```bash
chmod +x flacflow.py
```

### 3. Create Required Directories
The application will create these automatically, but you can pre-create them:
```bash
mkdir -p /home/dl/torrents/music/_Pre/
mkdir -p /home/dl/torrents/music/_Post/_CD/
mkdir -p /home/dl/torrents/music/_Post/_Hires/
mkdir -p /home/dl/hibiki/media/music/lossless/
```

### 4. Test the Application
```bash
source venv/bin/activate
python3 flacflow.py
```

You should see output like:
```
* Running on all addresses (0.0.0.0)
* Running on http://127.0.0.1:5000
* Running on http://[your-server-ip]:5000
```

### 5. Access the Web Interface
Open your browser and go to:
```
http://downloadserver.local:5000
```

## Setting Up as a System Service (Optional)

### 1. Create a Systemd Service File
```bash
sudo nano /etc/systemd/system/flacflow.service
```

Add the following content:
```ini
[Unit]
Description=FlacFlow Music Library Processor
After=network.target

[Service]
Type=simple
User=dl
WorkingDirectory=/home/dl/flacflow
Environment=PATH=/home/dl/flacflow/venv/bin
ExecStart=/home/dl/flacflow/venv/bin/python /home/dl/flacflow/flacflow.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### 2. Enable and Start the Service
```bash
sudo systemctl daemon-reload
sudo systemctl enable flacflow
sudo systemctl start flacflow
```

### 3. Check Service Status
```bash
sudo systemctl status flacflow
```

## Configuration

### 1. Initial Configuration
On first run, FlacFlow creates a `flacflow_config.json` file with default settings. You can:

- **Option A**: Edit the config file directly:
```bash
nano /home/dl/flacflow/flacflow_config.json
```

- **Option B**: Use the web interface:
  1. Go to `http://downloadserver.local:5000`
  2. Click the "Configuration" tab
  3. Update paths and settings
  4. Click "Save Configuration"

### 2. Key Configuration Settings
Update these paths to match your setup:

```json
{
  "paths": {
    "pre_processing": "/home/dl/torrents/music/_Pre/",
    "post_processing": "/home/dl/torrents/music/_Post/",
    "final_library": "/home/dl/hibiki/media/music/lossless/"
  }
}
```

## Usage

### 1. Add Albums for Processing
Place your downloaded albums in the pre-processing directory:
```bash
/home/dl/torrents/music/_Pre/
```

### 2. Process Albums
1. Open `http://downloadserver.local:5000`
2. Review albums in the "Pre-Processing" tab
3. Select albums to process
4. Click "Process Selected"

### 3. Publish to Library
1. Go to "Post-Processing" tab
2. Review processed albums
3. Select albums to publish
4. Click "Publish to Library"

## Troubleshooting

### Permission Issues
```bash
# Fix ownership
sudo chown -R dl:dl /home/dl/flacflow
sudo chown -R dl:dl /home/dl/torrents/music/
sudo chown -R dl:dl /home/dl/hibiki/media/music/

# Fix permissions
chmod -R 755 /home/dl/flacflow
chmod -R 755 /home/dl/torrents/music/
```

### Python Dependencies Issues
```bash
# Reinstall dependencies
cd /home/dl/flacflow
source venv/bin/activate
pip install --upgrade flask mutagen pillow
```

### Service Not Starting
```bash
# Check logs
sudo journalctl -u flacflow -f

# Check if port is in use
sudo netstat -tlnp | grep :5000

# Restart service
sudo systemctl restart flacflow
```

### Web Interface Not Accessible
1. Check if the service is running:
```bash
sudo systemctl status flacflow
```

2. Check firewall (if applicable):
```bash
sudo ufw allow 5000
```

3. Test local access:
```bash
curl http://localhost:5000
```

### FLAC Processing Errors
Ensure required tools are installed:
```bash
which metaflac  # Should return /usr/bin/metaflac
which ffprobe   # Should return /usr/bin/ffprobe
which convert   # Should return /usr/bin/convert
```

## Log Files

### Application Logs
FlacFlow creates a log file in the application directory:
```bash
tail -f /home/dl/flacflow/flacflow.log
```

### System Service Logs
If running as a service:
```bash
sudo journalctl -u flacflow -f
```

## Updating FlacFlow

### 1. Stop the Service (if running)
```bash
sudo systemctl stop flacflow
```

### 2. Backup Configuration
```bash
cp /home/dl/flacflow/flacflow_config.json /home/dl/flacflow/flacflow_config.json.backup
```

### 3. Update the Application
```bash
cd /home/dl/flacflow
nano flacflow.py  # Replace with updated code
```

### 4. Restart the Service
```bash
sudo systemctl start flacflow
```

## Security Considerations

### 1. Local Network Only
FlacFlow is designed for local network use. Ensure it's not exposed to the internet.

### 2. File Permissions
The application needs read/write access to:
- Pre-processing directory
- Post-processing directory  
- Final library directory
- Configuration file
- Log file

### 3. Backup Important Data
Before processing large batches:
```bash
# Backup your music library
rsync -av /home/dl/hibiki/media/music/lossless/ /backup/music/
```

## Integration with Existing Workflow

### 1. Reference Your Existing Scripts
Your bash scripts in `/usr/local/bin/` can serve as reference for any edge cases:
```bash
ls -la /usr/local/bin/*flac*
ls -la /usr/local/bin/*music*
```

### 2. Gradual Migration
Start by testing FlacFlow with a few albums while keeping your existing workflow available.

### 3. Validation
Compare FlacFlow results with your existing script results to ensure consistency.

## Performance Tips

### 1. Batch Size
Process 10-20 albums at a time for optimal performance.

### 2. Disk Space
Ensure adequate free space in post-processing directory (albums are moved, not copied).

### 3. System Resources
FlacFlow is designed to process albums sequentially to avoid I/O conflicts.

## Next Steps

1. **Test with Sample Albums**: Start with a few test albums to verify everything works
2. **Configure Paths**: Adjust configuration to match your specific directory structure
3. **Process Real Albums**: Begin processing your actual music collection
4. **Monitor Logs**: Check logs regularly during initial use to catch any issues
5. **Create Backups**: Establish backup routine for processed albums

Your FlacFlow installation should now be ready to automate your FLAC music library processing! 🎵