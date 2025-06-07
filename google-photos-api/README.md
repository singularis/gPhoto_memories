# Google Photos Picker API Application

This application has been **migrated from the deprecated Google Photos Library API to the new Google Photos Picker API** to comply with Google's API changes effective March 31, 2025.

## 🚨 Important API Changes

### What Changed
- **Old Library API**: Could automatically access and download from user's entire photo library
- **New Picker API**: Requires user interaction to manually select specific photos to share

### Why This Changed
Google has restricted the Library API to improve user privacy and data protection. After March 31, 2025:
- The `photoslibrary.readonly`, `photoslibrary.sharing`, and `photoslibrary` scopes are removed
- Library API will only work with content uploaded by your app
- For accessing user's existing photos, you must use the new Picker API

## 🔄 Migration Summary

### Old Workflow (Deprecated)
1. ✅ App automatically scanned 20 years of photos
2. ✅ Downloaded photos by date automatically
3. ❌ **No longer supported after March 31, 2025**

### New Workflow (Current)
1. 👤 User creates a session through web interface
2. 🔗 User clicks link to open Google Photos
3. 📸 User manually selects photos they want to share
4. ⬇️ App downloads only the selected photos

## 🛠️ Setup

### Prerequisites
- Google Cloud Project with Photos API enabled
- OAuth 2.0 credentials for each user
- Docker (optional) or Python 3.9+

### Environment Variables
```bash
USERS='["user1", "user2"]'  # JSON array of usernames
FLASK_SECRET_KEY='your-secret-key'  # For session management
```

### Credentials Structure
```
gcp-credentials-{username}/
└── gPhoto_credentials_{username}.json
```

## 🚀 Running the Application

### With Docker
```bash
docker build -t gphoto-picker .
docker run -p 5000:5000 \
  -e USERS='["dante", "iva"]' \
  -e FLASK_SECRET_KEY='your-secret-key' \
  -v /path/to/credentials:/app/gcp-credentials-dante \
  -v /path/to/pics:/app/static/pics \
  gphoto-picker
```

### With Python
```bash
pip install -r requirements.txt
python gphoto_picker.py
```

## 🌐 Web Interface

The application provides a web interface at `http://localhost:5000` with:

1. **Home Page** (`/`): Create sessions for users and view active sessions
2. **Session Page**: Shows picker link and status for photo selection
3. **Status Page**: Detailed session information and progress tracking
4. **Downloads Page**: List of all downloaded items

## 📋 User Workflow

### Step 1: Create Session
1. Visit the web interface
2. Click "Create Session for [user]"
3. Authenticate with Google (OAuth flow)

### Step 2: Select Photos
1. Click "Open Google Photos Picker" button
2. New window opens with Google Photos
3. Browse and select desired photos/videos
4. Confirm selection in Google Photos

### Step 3: Download
1. Return to the web interface
2. Session status shows "Ready for Download"
3. Click "Download Selected Photos"
4. Photos are downloaded and organized by year

## 📁 File Organization

Downloaded files are saved to `/app/static/pics/` with this structure:
```
static/pics/
├── 2023/
│   ├── photo1_username.jpg
│   └── video1_username.mp4
├── 2024/
│   ├── photo2_username.jpg
│   └── photo3_username.jpg
└── ...
```

## 🔧 API Endpoints

- `GET /` - Main interface
- `GET /create_session/<user>` - Create new picker session
- `GET /check_session/<session_id>` - Check session status (JSON)
- `GET /download_session/<session_id>` - Start download process
- `GET /session_status/<session_id>` - Detailed session status
- `GET /downloads` - List downloaded items
- `GET /api/sessions` - All active sessions (JSON)

## ⚙️ Kubernetes Deployment

The existing Kubernetes configuration will need updates:

### Updated gphoto.yaml
```yaml
# Update the container command
containers:
- name: gphoto-downloader
  image: singularis314/gphoto_downloader:1.0  # New version
  command: ["python", "gphoto_picker.py"]
  ports:
  - containerPort: 5000
  env:
  - name: USERS
    valueFrom:
      configMapKeyRef:
        name: users
        key: users
  - name: FLASK_SECRET_KEY
    valueFrom:
      secretKeyRef:
        name: gphoto-secrets
        key: flask-secret-key

# Add service for web interface
---
apiVersion: v1
kind: Service
metadata:
  name: gphoto-picker-service
spec:
  selector:
    app: gphoto-downloader
  ports:
  - port: 5000
    targetPort: 5000
```

## 📊 Monitoring

The application logs all activities:
- Session creation and status changes
- Photo selection events
- Download progress and completion
- Error handling and troubleshooting

Logs are available in `application.log` and console output.

## 🔐 Security Notes

### OAuth Scopes
The application now uses the minimal required scope:
- `https://www.googleapis.com/auth/photospicker.mediaitems.readonly`

### Data Privacy
- Users explicitly choose which photos to share
- No automatic access to user's entire library
- Downloads only happen after user confirmation

## 🐛 Troubleshooting

### Common Issues

1. **"Session not found"**
   - Sessions are stored in memory and lost on restart
   - Create a new session if needed

2. **"Authentication failed"**
   - Check OAuth credentials are properly configured
   - Ensure correct scopes in Google Cloud Console

3. **"No photos selected"**
   - User must complete the selection process in Google Photos
   - Check session status to confirm selection

### Legacy Code
The old `gphot.py` script is deprecated but kept for reference. It will not work after March 31, 2025, due to API scope removals.

## 📈 Future Enhancements

Potential improvements:
- Persistent session storage (database)
- Batch processing for large selections
- Progress bars for downloads
- User management interface
- Integration with cloud storage services

---

For questions or support, check the application logs or refer to the [Google Photos Picker API documentation](https://developers.google.com/photos/picker). 