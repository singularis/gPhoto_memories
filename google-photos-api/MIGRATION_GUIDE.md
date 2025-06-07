# Migration Guide: Library API → Picker API

This document provides a detailed guide for migrating from the deprecated Google Photos Library API to the new Google Photos Picker API.

## 🚨 Urgency: March 31, 2025 Deadline

**Critical:** The old Library API scopes will be removed on March 31, 2025. Your current system will stop working after this date if not migrated.

## 📊 Impact Assessment

### What Will Stop Working
- Automatic photo scanning by date
- Bulk download of user's entire photo library
- Scheduled/automated photo downloads
- Any use of these deprecated scopes:
  - `photoslibrary.readonly`
  - `photoslibrary.sharing`
  - `photoslibrary`

### What Will Continue Working
- App-created content management (if using `photoslibrary.appendonly`)
- OAuth authentication flow
- File organization and storage

## 🔄 Technical Changes Required

### 1. Dependencies Update

**Old requirements.txt:**
```python
# Had many unnecessary Google Cloud packages
google-cloud-storage
google-cloud-speech
# etc.
```

**New requirements.txt:**
```python
pandas
python-dateutil
google-api-core
google-api-python-client
google-auth
google-auth-httplib2
google-auth-oauthlib
google-resumable-media
googleapis-common-protos
requests
flask
python-dotenv
```

### 2. OAuth Scopes Migration

**Old scopes (DEPRECATED):**
```python
scopes = [
    'https://www.googleapis.com/auth/photoslibrary.readonly',
    'https://www.googleapis.com/auth/photoslibrary',
    'https://www.googleapis.com/auth/photoslibrary.readonly.originals',
    'https://www.googleapis.com/auth/photospicker.mediaitems.readonly',
]
```

**New scopes (REQUIRED):**
```python
scopes = [
    'https://www.googleapis.com/auth/photospicker.mediaitems.readonly',
]
```

### 3. API Endpoints Migration

**Old endpoints (DEPRECATED):**
```python
# This endpoint will return 403 PERMISSION_DENIED after March 31, 2025
photo_url = 'https://photospicker.googleapis.com/v1/mediaItems:search'
```

**New endpoints (REQUIRED):**
```python
# Picker API endpoints
base_url = 'https://photospicker.googleapis.com/v1'
sessions_url = f'{base_url}/sessions'
media_items_url = f'{base_url}/mediaItems'
```

### 4. Application Architecture Changes

#### Old Architecture (Batch Processing)
```
┌─────────────┐    ┌──────────────┐    ┌─────────────┐
│   CronJob   │───▶│  Auto Scan   │───▶│  Download   │
│  Scheduled  │    │  20 Years    │    │  All Photos │
└─────────────┘    └──────────────┘    └─────────────┘
```

#### New Architecture (User-Driven)
```
┌──────────────┐    ┌──────────────┐    ┌──────────────┐    ┌─────────────┐
│ Web Interface │───▶│ User Selects │───▶│ Session Poll │───▶│  Download   │
│   (Flask)    │    │   Photos     │    │   & Status   │    │  Selected   │
└──────────────┘    └──────────────┘    └──────────────┘    └─────────────┘
```

## 🛠️ Step-by-Step Migration

### Step 1: Update Google Cloud Console

1. **Review OAuth Consent Screen:**
   - Ensure scopes are updated to Picker API scopes
   - Update app description to mention user photo selection

2. **Update API Enablement:**
   - Ensure Google Photos Library API is enabled
   - Add Photos Picker API if available

### Step 2: Code Migration

1. **Backup Current System:**
   ```bash
   cp gphot.py gphot_legacy.py
   cp -r gphoto/ gphoto_legacy/
   ```

2. **Deploy New Code:**
   - Replace `gphot.py` with `gphoto_picker.py`
   - Update `gphoto/api.py` with new classes
   - Add Flask templates and web interface

3. **Update Docker Configuration:**
   ```dockerfile
   # Old command
   CMD ["python", "-u", "/app/gphot.py"]
   
   # New command
   CMD ["python", "gphoto_picker.py"]
   EXPOSE 5000
   ```

### Step 3: Infrastructure Updates

#### Kubernetes Changes
```yaml
# Update deployment
spec:
  template:
    spec:
      containers:
      - name: gphoto-downloader
        # Add port exposure
        ports:
        - containerPort: 5000
        # Update environment variables
        env:
        - name: FLASK_SECRET_KEY
          valueFrom:
            secretKeyRef:
              name: gphoto-secrets
              key: flask-secret-key

# Add service
---
apiVersion: v1
kind: Service
metadata:
  name: gphoto-picker-service
  namespace: gphoto
spec:
  selector:
    app: gphoto-downloader
  ports:
  - port: 5000
    targetPort: 5000
  type: ClusterIP
```

#### Ingress/Load Balancer
```yaml
# Add ingress for web interface
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: gphoto-picker-ingress
  namespace: gphoto
spec:
  rules:
  - host: gphoto.yourdomain.com
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: gphoto-picker-service
            port:
              number: 5000
```

### Step 4: User Training

#### For End Users
1. **New Workflow Training:**
   - How to access the web interface
   - How to create sessions
   - How to use Google Photos picker
   - How to check download status

2. **Communication Template:**
   ```
   Subject: Important Update: Google Photos Download Process

   Due to Google API changes, we've updated how photo downloads work:

   OLD: Photos were automatically downloaded on schedule
   NEW: You select specific photos through a web interface

   New Process:
   1. Visit: https://gphoto.yourdomain.com
   2. Click "Create Session for [your-name]"
   3. Click "Open Google Photos Picker"
   4. Select photos you want to download
   5. Return to interface and click "Download"

   This change provides better privacy and security for your photos.
   ```

## 🧪 Testing Strategy

### 1. Development Testing
```bash
# Test local development
export USERS='["testuser"]'
export FLASK_SECRET_KEY='test-key'
python gphoto_picker.py

# Access http://localhost:5000
# Test full workflow with test Google account
```

### 2. Staging Deployment
- Deploy to staging environment
- Test with real Google Photos accounts
- Verify file downloads and organization
- Test session management and status tracking

### 3. Production Rollout
- **Blue-Green Deployment Recommended:**
  - Keep old system running during migration
  - Test new system with subset of users
  - Gradually migrate all users
  - Decommission old system after March 31, 2025

## 📋 Migration Checklist

### Pre-Migration
- [ ] Google Cloud Console scopes updated
- [ ] Flask secret key generated and stored securely
- [ ] Web interface accessibility tested
- [ ] User communication prepared
- [ ] Backup of current system created

### During Migration
- [ ] New container image built and tested
- [ ] Kubernetes manifests updated
- [ ] Service and ingress configured
- [ ] Environment variables set
- [ ] Users notified of new process

### Post-Migration
- [ ] Monitor application logs for errors
- [ ] Verify user sessions are working
- [ ] Confirm downloads are completing
- [ ] User feedback collected and addressed
- [ ] Old system marked for decommission

## 🔍 Monitoring & Troubleshooting

### Key Metrics to Monitor
- Session creation success rate
- Photo selection completion rate  
- Download success rate
- User adoption of new interface
- Error rates and types

### Common Issues and Solutions

1. **High Session Abandonment**
   - Simplify user interface
   - Add better instructions
   - Implement reminder notifications

2. **Authentication Failures**
   - Verify OAuth credentials
   - Check scope configurations
   - Validate redirect URIs

3. **Download Failures**
   - Monitor storage space
   - Check network connectivity
   - Verify API rate limits

## 📅 Timeline Recommendation

**8-12 weeks before March 31, 2025:**
- Complete development and testing
- Deploy to staging environment

**6-8 weeks before:**
- Begin user communication
- Start gradual production rollout

**4 weeks before:**
- Complete user migration
- Final testing and validation

**March 31, 2025:**
- Decommission old system
- Monitor new system stability

## 🆘 Rollback Plan

If critical issues arise:

1. **Immediate Rollback:**
   ```bash
   # Revert to previous container version
   kubectl set image deployment/gphoto-downloader \
     gphoto-downloader=singularis314/gphoto_downloader:previous
   ```

2. **Temporary Mitigation:**
   - Use manual photo downloads
   - Batch process using alternative tools
   - Communicate delays to users

3. **Long-term Recovery:**
   - Debug and fix issues
   - Redeploy when stable
   - Continue migration process

---

**Need Help?** 
- Check application logs: `kubectl logs deployment/gphoto-downloader`
- Review Google Photos API documentation
- Test with minimal user subset first 