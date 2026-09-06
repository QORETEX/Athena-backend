# 🚀 Athena Backend - Complete Frontend Integration Guide

## 📋 Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Getting Started](#getting-started)
4. [Authentication](#authentication)
5. [Core Features](#core-features)
6. [API Endpoints Reference](#api-endpoints-reference)
7. [WebSocket Integration](#websocket-integration)
8. [Mobile App Integration](#mobile-app-integration)
9. [Error Handling](#error-handling)
10. [Best Practices](#best-practices)
11. [Testing Guide](#testing-guide)

---

## Overview

**Athena** is an intelligent JARVIS-like voice assistant backend with:
- 🤖 AI-powered natural language processing (Groq/Claude/NVIDIA/Ollama)
- 🧠 Learning system (remembers user preferences)
- 👥 Relationship intelligence
- 🎯 Focus mode & productivity tracking
- ⚡ Quick actions & automation
- 📧 Email & calendar integration
- 🎙️ Voice journaling
- 📱 Push notifications
- 🚗 Smart commute optimization
- 💪 Health & wellness tracking

**Base URL:** `http://localhost:8000` (Development)  
**Production URL:** `https://your-domain.com`

**API Documentation:** `http://localhost:8000/docs` (Interactive Swagger UI)

---

## Architecture

### System Components

```
┌─────────────────────────────────────────────────────────┐
│                    Mobile App (React Native)            │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐             │
│  │  Voice   │  │  Chat    │  │ Context  │             │
│  │ Commands │  │    UI    │  │ Tracker  │             │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘             │
└───────┼─────────────┼─────────────┼───────────────────┘
        │             │             │
        ▼             ▼             ▼
┌─────────────────────────────────────────────────────────┐
│              Athena Backend (FastAPI)                   │
│  ┌──────────────────────────────────────────────────┐  │
│  │  REST API (70+ endpoints)                        │  │
│  │  - Chat, Reminders, Notes, Learning, etc.       │  │
│  └──────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────┐  │
│  │  WebSocket (Real-time)                           │  │
│  │  - Voice streaming, Events                       │  │
│  └──────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────┐  │
│  │  JARVIS Brain (Autonomous Agent)                 │  │
│  │  - Runs every 60s, makes proactive decisions     │  │
│  └──────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────┐  │
│  │  LLM Layer (4-tier fallback)                     │  │
│  │  Claude → Groq → NVIDIA → Ollama                 │  │
│  └──────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
        │             │             │
        ▼             ▼             ▼
┌─────────────────────────────────────────────────────────┐
│  PostgreSQL Database (24 tables)                        │
│  - Users, Messages, Reminders, Notes, Contacts, etc.   │
└─────────────────────────────────────────────────────────┘
```

### Data Flow

1. **User speaks** → Mobile app captures audio
2. **Audio sent** → Backend via WebSocket/REST
3. **STT converts** → Text (Whisper)
4. **LLM processes** → Intent & response (Claude/Groq)
5. **Action executed** → Database updated
6. **Response sent** → Mobile app
7. **TTS generates** → Audio (Piper)
8. **User hears** → Response played

---

## Getting Started

### Prerequisites

- Node.js 16+ or React Native environment
- iOS/Android development setup
- API access credentials (if using cloud APIs)

### Initial Setup

1. **Get the base URL:**
```javascript
const API_BASE_URL = 'http://localhost:8000'; // Development
// or
const API_BASE_URL = 'https://athena-api.yourdomain.com'; // Production
```

2. **Install HTTP client:**
```bash
npm install axios
# or
npm install @tanstack/react-query axios
```

3. **Basic API client setup:**
```javascript
// src/api/client.js
import axios from 'axios';

const apiClient = axios.create({
  baseURL: process.env.REACT_APP_API_URL || 'http://localhost:8000',
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Add request interceptor for auth
apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem('auth_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Add response interceptor for error handling
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      // Handle unauthorized
      localStorage.removeItem('auth_token');
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);

export default apiClient;
```

---

## Authentication

### Current Status
⚠️ **Note:** Authentication is currently **optional**. All endpoints are accessible without authentication for development.

### For Production
When deploying, you'll want to implement authentication:

```javascript
// Login example (when auth is enabled)
import apiClient from './client';

async function login(email, password) {
  const response = await apiClient.post('/api/auth/login', {
    email,
    password,
  });
  
  const { token, user } = response.data;
  localStorage.setItem('auth_token', token);
  localStorage.setItem('user', JSON.stringify(user));
  
  return user;
}

async function logout() {
  localStorage.removeItem('auth_token');
  localStorage.removeItem('user');
}

function getUser() {
  const userStr = localStorage.getItem('user');
  return userStr ? JSON.parse(userStr) : null;
}
```

---

## Core Features

### 1. Chat / Conversation

**Send a message and get AI response:**

```javascript
async function sendMessage(message) {
  const response = await apiClient.post('/api/chat', {
    message: message,
    conversation_id: null, // Optional: continue existing conversation
  });
  
  return response.data;
  // Returns: { reply: "...", conversation_id: "..." }
}

// Example usage:
const result = await sendMessage("What's the weather like?");
console.log(result.reply); // AI response
```

### 2. Reminders

**Create a reminder:**
```javascript
async function createReminder(text, remindAt) {
  const response = await apiClient.post('/api/reminders', {
    text: text,
    remind_at: remindAt, // ISO 8601 format: "2026-09-07T10:00:00Z"
  });
  
  return response.data;
}

// Example:
await createReminder(
  "Call Mom",
  new Date(Date.now() + 3600000).toISOString() // 1 hour from now
);
```

**Get all reminders:**
```javascript
async function getReminders() {
  const response = await apiClient.get('/api/reminders');
  return response.data;
  // Returns: [{ id: 1, text: "Call Mom", remind_at: "...", completed: false }]
}
```

**Complete a reminder:**
```javascript
async function completeReminder(id) {
  await apiClient.patch(`/api/reminders/${id}`, {
    completed: true
  });
}
```

### 3. Notes

**Create a note:**
```javascript
async function createNote(content, tags = []) {
  const response = await apiClient.post('/api/notes', {
    content: content,
    tags: tags,
  });
  
  return response.data;
}

// Example:
await createNote("Project ideas for Q4", ["work", "planning"]);
```

**Search notes:**
```javascript
async function searchNotes(query) {
  const response = await apiClient.get('/api/notes/search', {
    params: { q: query }
  });
  
  return response.data;
}
```

### 4. Learning System (NEW! 🎉)

**Teach JARVIS a fact:**
```javascript
async function teachJarvis(category, key, value) {
  const response = await apiClient.post('/api/learning/teach', {
    category: category,    // "preference", "fact", "skill", "relationship"
    key: key,              // e.g., "favorite_coffee"
    value: value,          // e.g., "espresso"
    source: "user",
    confidence: 1.0,
  });
  
  return response.data;
}

// Examples:
await teachJarvis("preference", "favorite_coffee", "double espresso");
await teachJarvis("fact", "brother_name", "Michael");
await teachJarvis("skill", "programming_language", "Python");
```

**Query with natural language:**
```javascript
async function askJarvis(question) {
  const response = await apiClient.post('/api/learning/query', {
    question: question,
  });
  
  return response.data;
  // Returns: { answer: "...", confidence: 1.0, sources: [...] }
}

// Example:
const result = await askJarvis("What is my favorite coffee?");
console.log(result.answer); // "Your favorite coffee is double espresso."
```

**Get all knowledge:**
```javascript
async function getAllKnowledge(category = null) {
  const response = await apiClient.get('/api/learning/knowledge', {
    params: category ? { category } : {}
  });
  
  return response.data;
}
```

### 5. Quick Actions (NEW! ⚡)

**Execute a quick action:**
```javascript
async function executeQuickAction(trigger) {
  const response = await apiClient.post('/api/shortcuts/trigger', {
    trigger: trigger, // "morning", "focus", "wind_down", "catch_up"
  });
  
  return response.data;
}

// Example - morning routine:
const result = await executeQuickAction("morning");
console.log(result);
// Returns briefing, checks emails, calendar, sends notification
```

**Available preset actions:**
- `"morning"` - Morning briefing + email + calendar check
- `"focus"` - Start focus mode (DND, hold notifications)
- `"wind_down"` - Evening summary
- `"catch_up"` - Quick status update

**Create custom action:**
```javascript
async function createCustomAction(name, trigger, actions) {
  const response = await apiClient.post('/api/shortcuts/actions', {
    name: name,
    trigger_phrase: trigger,
    description: "Custom action",
    actions: actions, // Array of action steps
  });
  
  return response.data;
}

// Example - custom "heading home" action:
await createCustomAction(
  "heading_home",
  "heading home",
  [
    { type: "check_emails", params: {} },
    { type: "send_notification", params: { 
      title: "Heading Home", 
      body: "Have a great evening!" 
    }}
  ]
);
```

### 6. Focus Mode (NEW! 🎯)

**Start focus session:**
```javascript
async function startFocusMode(duration, activity) {
  const response = await apiClient.post('/api/focus/start', {
    focus_type: "deep_work",
    planned_duration_minutes: duration,
    activity: activity,
  });
  
  return response.data;
  // Returns: { session_id: 123, status: "active", ... }
}

// Example:
const session = await startFocusMode(90, "Coding new feature");
```

**Check if in focus mode:**
```javascript
async function isInFocusMode() {
  const response = await apiClient.get('/api/focus/current');
  return response.data;
  // Returns: { in_focus_mode: true/false, session: {...} }
}
```

**End focus session:**
```javascript
async function endFocusMode(sessionId, productivityScore) {
  const response = await apiClient.post(`/api/focus/${sessionId}/end`, {
    productivity_score: productivityScore, // 0-10
    notes: "Great session!",
  });
  
  return response.data;
}
```

**Get focus statistics:**
```javascript
async function getFocusStats(days = 7) {
  const response = await apiClient.get('/api/focus/stats', {
    params: { days }
  });
  
  return response.data;
  // Returns: { total_sessions, total_minutes, average_productivity, ... }
}
```

### 7. Relationship Intelligence (NEW! 👥)

**Add a contact:**
```javascript
async function addContact(name, email, relationship, importantDates) {
  const response = await apiClient.post('/api/relationships/contacts', {
    name: name,
    email: email,
    phone: null,
    relationship: relationship, // "family", "friend", "colleague"
    important_dates: importantDates, // [{ type: "birthday", date: "03-15" }]
  });
  
  return response.data;
}

// Example:
await addContact(
  "John Smith",
  "john@example.com",
  "friend",
  [{ type: "birthday", date: "03-15" }]
);
```

**Record an interaction:**
```javascript
async function recordInteraction(contactId, type, summary, topics) {
  const response = await apiClient.post(
    `/api/relationships/contacts/${contactId}/interactions`,
    {
      interaction_type: type, // "call", "email", "meeting", "message"
      summary: summary,
      topics: topics, // ["work", "projects"]
      sentiment: "positive", // "positive", "neutral", "negative"
    }
  );
  
  return response.data;
}

// Example:
await recordInteraction(
  1,
  "meeting",
  "Discussed Q4 project plans",
  ["work", "projects", "planning"]
);
```

**Get follow-up suggestions:**
```javascript
async function getFollowUpSuggestions(daysThreshold = 30) {
  const response = await apiClient.get('/api/relationships/followups', {
    params: { days: daysThreshold }
  });
  
  return response.data;
  // Returns: [{ contact_id, name, days_since_contact, suggestion, ... }]
}

// Example:
const suggestions = await getFollowUpSuggestions(30);
suggestions.forEach(s => {
  console.log(`${s.name}: ${s.suggestion}`);
});
```

**Get upcoming important dates:**
```javascript
async function getImportantDates(daysAhead = 30) {
  const response = await apiClient.get('/api/relationships/important-dates', {
    params: { days_ahead: daysAhead }
  });
  
  return response.data;
  // Returns: [{ contact_name, date_type, date, days_until, ... }]
}
```

### 8. Automation Rules (NEW! ⚡)

**Create automation rule:**
```javascript
async function createAutomationRule(name, conditions, actions) {
  const response = await apiClient.post('/api/automation/rules', {
    name: name,
    description: "Auto-execute when conditions met",
    trigger_conditions: conditions,
    actions: actions,
    enabled: true,
  });
  
  return response.data;
}

// Example - low battery alert:
await createAutomationRule(
  "Low Battery Alert",
  [
    { type: "battery", key: "battery_level", operator: "less_than", value: 15 }
  ],
  [
    { type: "send_push", params: { title: "Charge Phone", body: "Battery low!" }}
  ]
);
```

**Evaluate rules against context:**
```javascript
async function evaluateAutomations(context) {
  const response = await apiClient.post('/api/automation/evaluate', {
    context: context,
  });
  
  return response.data;
  // Returns: { rules_executed: 2, results: [...] }
}

// Example - send phone context:
await evaluateAutomations({
  location: "home",
  battery_level: 12,
  time: "22:00",
  activity: "idle",
});
```

### 9. Push Notifications

**Register device for push notifications:**
```javascript
async function registerPushToken(expoPushToken, platform) {
  const response = await apiClient.post('/api/push/register', {
    token: expoPushToken,
    device_id: null,
    platform: platform, // "ios" or "android"
  });
  
  return response.data;
}

// Example with Expo:
import * as Notifications from 'expo-notifications';

async function setupPushNotifications() {
  const { status } = await Notifications.requestPermissionsAsync();
  
  if (status === 'granted') {
    const token = await Notifications.getExpoPushTokenAsync();
    await registerPushToken(token.data, Platform.OS);
  }
}
```

**Test push notification:**
```javascript
async function testPushNotification() {
  await apiClient.post('/api/push/test', {
    title: "Test",
    body: "This is a test notification"
  });
}
```

### 10. Context Updates (Important for Mobile!)

**Send phone context (call every 30 seconds):**
```javascript
async function updateContext(context) {
  await apiClient.post('/api/context/update', context);
}

// Example - send device context:
setInterval(async () => {
  const context = {
    location: await getCurrentLocation(),
    battery_level: await getBatteryLevel(),
    is_driving: await isUserDriving(),
    screen_time: await getScreenTime(),
    app_usage: await getAppUsage(),
    activity: "active", // or "idle"
  };
  
  await updateContext(context);
}, 30000); // Every 30 seconds
```

---

## API Endpoints Reference

### Complete Endpoint List

#### 🏥 Health & Status
```
GET  /health                    - Health check
GET  /                          - API info
```

#### 💬 Chat & Conversation
```
POST /api/chat                  - Send message, get AI response
GET  /api/conversations         - List conversations
GET  /api/conversations/{id}    - Get conversation history
```

#### ⏰ Reminders
```
POST   /api/reminders           - Create reminder
GET    /api/reminders           - List reminders
GET    /api/reminders/{id}      - Get reminder
PATCH  /api/reminders/{id}      - Update reminder
DELETE /api/reminders/{id}      - Delete reminder
```

#### 📝 Notes
```
POST   /api/notes               - Create note
GET    /api/notes               - List notes
GET    /api/notes/{id}          - Get note
PATCH  /api/notes/{id}          - Update note
DELETE /api/notes/{id}          - Delete note
GET    /api/notes/search        - Search notes
```

#### 🧠 Learning System
```
POST   /api/learning/teach                    - Teach JARVIS a fact
GET    /api/learning/knowledge                - Get all knowledge
GET    /api/learning/knowledge/{cat}/{key}    - Get specific knowledge
GET    /api/learning/search                   - Search knowledge
DELETE /api/learning/knowledge/{id}           - Forget knowledge
POST   /api/learning/query                    - Natural language query
POST   /api/learning/extract                  - Extract from conversation
GET    /api/learning/graph/{id}               - View knowledge graph
GET    /api/learning/stats                    - Knowledge statistics
POST   /api/learning/teach-from-voice         - Voice teaching
```

#### ⚡ Quick Actions (Shortcuts)
```
POST   /api/shortcuts/actions                 - Create custom action
GET    /api/shortcuts/actions                 - List all actions
GET    /api/shortcuts/actions/{id}            - Get action details
PATCH  /api/shortcuts/actions/{id}            - Update action
DELETE /api/shortcuts/actions/{id}            - Delete action
POST   /api/shortcuts/execute/{id}            - Execute by ID
POST   /api/shortcuts/trigger                 - Execute by trigger phrase
POST   /api/shortcuts/initialize-presets      - Setup presets
POST   /api/shortcuts/suggest                 - Get AI suggestions
```

#### 🎯 Focus Mode
```
POST /api/focus/start                         - Start focus session
POST /api/focus/{id}/end                      - End session
GET  /api/focus/current                       - Check if in focus mode
GET  /api/focus/sessions                      - Recent sessions
GET  /api/focus/stats                         - Analytics
GET  /api/focus/optimal-times                 - Best focus times
POST /api/focus/detect                        - Auto-detect focus
POST /api/focus/{id}/notification-held        - Record held notification
POST /api/focus/{id}/interruption             - Record interruption
```

#### 👥 Relationship Intelligence
```
POST   /api/relationships/contacts                      - Add contact
GET    /api/relationships/contacts                      - List contacts
GET    /api/relationships/contacts/{id}                 - Get details
PATCH  /api/relationships/contacts/{id}                 - Update contact
DELETE /api/relationships/contacts/{id}                 - Delete contact
POST   /api/relationships/contacts/{id}/interactions    - Record interaction
GET    /api/relationships/followups                     - Get follow-up suggestions
GET    /api/relationships/important-dates               - Upcoming dates
GET    /api/relationships/search                        - Search contacts
GET    /api/relationships/stats                         - Statistics
```

#### ⚡ Automation
```
POST   /api/automation/rules          - Create rule
GET    /api/automation/rules          - List rules
GET    /api/automation/rules/{id}     - Get rule
PATCH  /api/automation/rules/{id}     - Update rule
DELETE /api/automation/rules/{id}     - Delete rule
POST   /api/automation/evaluate       - Execute matching rules
POST   /api/automation/suggest        - Get AI suggestions
```

#### 📱 Push Notifications
```
POST /api/push/register       - Register device token
POST /api/push/unregister     - Unregister device
POST /api/push/test           - Send test notification
```

#### 📍 Context (Mobile)
```
POST /api/context/update      - Update phone context
```

#### 🌅 Briefings
```
GET /api/briefing-enhanced/morning    - Morning briefing
GET /api/briefing-enhanced/evening    - Evening briefing
```

#### 📧 Email Integration
```
POST /api/emails/sync                 - Sync from Gmail
GET  /api/emails/urgent               - Get urgent emails
GET  /api/emails/{id}/summarize       - AI email summary
POST /api/emails/initialize           - Setup Gmail connection
```

#### 📅 Calendar Integration
```
POST /api/calendar/sync               - Sync from Google Calendar
GET  /api/calendar/next               - Get next meeting
GET  /api/calendar/{id}/prep          - Meeting prep brief
POST /api/calendar/initialize         - Setup Calendar connection
```

#### 🎙️ Voice Journaling
```
POST /api/journal/entry               - Create text entry
POST /api/journal/entry/voice         - Voice entry with transcription
GET  /api/journal/entries             - List entries
GET  /api/journal/search              - Search journals
GET  /api/journal/{id}                - Get entry details
```

#### 🚗 Smart Commute
```
POST /api/commute/analyze             - Analyze commute options
GET  /api/commute/traffic             - Real-time traffic
GET  /api/commute/optimal-departure   - When to leave
```

#### 💪 Wellness
```
POST /api/wellness/update             - Update health data
GET  /api/wellness/stats              - Health statistics
GET  /api/wellness/insights           - AI health insights
POST /api/wellness/alert-preferences  - Configure alerts
```

#### 🌤️ Weather
```
GET /api/weather?lat={lat}&lon={lon}  - Get weather
```

---

## WebSocket Integration

### Voice Streaming

**Connect to WebSocket:**
```javascript
const ws = new WebSocket('ws://localhost:8000/ws/voice');

ws.onopen = () => {
  console.log('Voice WebSocket connected');
};

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  
  if (data.type === 'transcription') {
    console.log('You said:', data.text);
  } else if (data.type === 'response') {
    console.log('JARVIS:', data.text);
    // Play audio response if included
    if (data.audio) {
      playAudio(data.audio);
    }
  }
};

// Send audio chunks
function sendAudioChunk(audioData) {
  ws.send(JSON.stringify({
    type: 'audio',
    data: audioData, // Base64 encoded audio
  }));
}

// Signal end of speech
function endSpeech() {
  ws.send(JSON.stringify({ type: 'audio_end' }));
}
```

### Event Stream

**Connect for real-time events:**
```javascript
const eventsWs = new WebSocket('ws://localhost:8000/ws/events');

eventsWs.onmessage = (event) => {
  const data = JSON.parse(event.data);
  
  switch (data.type) {
    case 'reminder':
      showReminderNotification(data.reminder);
      break;
    case 'focus_mode_end':
      notifyFocusSessionComplete(data.session);
      break;
    case 'proactive_suggestion':
      showSuggestion(data.suggestion);
      break;
  }
};
```

---

## Mobile App Integration

### React Native / Expo Setup

**1. Install dependencies:**
```bash
npm install axios expo-notifications expo-device expo-constants
```

**2. Setup API client:**
```javascript
// src/services/athena.js
import axios from 'axios';
import Constants from 'expo-constants';

const API_URL = __DEV__ 
  ? 'http://localhost:8000'  // Development
  : 'https://athena-api.yourdomain.com'; // Production

const athena = axios.create({
  baseURL: API_URL,
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
});

export default athena;
```

**3. Setup push notifications:**
```javascript
// src/services/notifications.js
import * as Notifications from 'expo-notifications';
import * as Device from 'expo-device';
import { Platform } from 'react-native';
import athena from './athena';

// Configure notification behavior
Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowAlert: true,
    shouldPlaySound: true,
    shouldSetBadge: true,
  }),
});

export async function registerForPushNotifications() {
  if (!Device.isDevice) {
    console.log('Push notifications only work on physical devices');
    return null;
  }

  const { status: existingStatus } = await Notifications.getPermissionsAsync();
  let finalStatus = existingStatus;

  if (existingStatus !== 'granted') {
    const { status } = await Notifications.requestPermissionsAsync();
    finalStatus = status;
  }

  if (finalStatus !== 'granted') {
    console.log('Push notification permission denied');
    return null;
  }

  const token = await Notifications.getExpoPushTokenAsync();

  // Register with backend
  try {
    await athena.post('/api/push/register', {
      token: token.data,
      device_id: Constants.deviceId,
      platform: Platform.OS,
    });
    console.log('Push token registered:', token.data);
    return token.data;
  } catch (error) {
    console.error('Failed to register push token:', error);
    return null;
  }
}

// Listen for notifications
export function setupNotificationListeners() {
  // Notification received while app is in foreground
  Notifications.addNotificationReceivedListener((notification) => {
    console.log('Notification received:', notification);
  });

  // User tapped on notification
  Notifications.addNotificationResponseReceivedListener((response) => {
    console.log('Notification tapped:', response);
    // Navigate to relevant screen based on notification data
  });
}
```

**4. Context tracking:**
```javascript
// src/services/contextTracker.js
import * as Location from 'expo-location';
import * as Battery from 'expo-battery';
import athena from './athena';

let contextInterval = null;

export async function startContextTracking() {
  // Request permissions
  const { status } = await Location.requestForegroundPermissionsAsync();
  if (status !== 'granted') {
    console.log('Location permission denied');
    return;
  }

  // Send context every 30 seconds
  contextInterval = setInterval(async () => {
    const context = await gatherContext();
    await sendContext(context);
  }, 30000);

  console.log('Context tracking started');
}

export function stopContextTracking() {
  if (contextInterval) {
    clearInterval(contextInterval);
    contextInterval = null;
  }
}

async function gatherContext() {
  const [location, battery] = await Promise.all([
    Location.getCurrentPositionAsync(),
    Battery.getBatteryLevelAsync(),
  ]);

  return {
    location: {
      latitude: location.coords.latitude,
      longitude: location.coords.longitude,
    },
    battery_level: Math.round(battery * 100),
    timestamp: new Date().toISOString(),
  };
}

async function sendContext(context) {
  try {
    await athena.post('/api/context/update', context);
  } catch (error) {
    console.error('Failed to send context:', error);
  }
}
```

**5. Voice integration:**
```javascript
// src/services/voice.js
import { Audio } from 'expo-av';

export async function setupAudio() {
  await Audio.requestPermissionsAsync();
  await Audio.setAudioModeAsync({
    allowsRecordingIOS: true,
    playsInSilentModeIOS: true,
  });
}

export async function recordVoice() {
  const recording = new Audio.Recording();
  
  try {
    await recording.prepareToRecordAsync(
      Audio.RECORDING_OPTIONS_PRESET_HIGH_QUALITY
    );
    await recording.startAsync();
    return recording;
  } catch (error) {
    console.error('Failed to start recording:', error);
    return null;
  }
}

export async function stopRecording(recording) {
  await recording.stopAndUnloadAsync();
  const uri = recording.getURI();
  return uri;
}

export async function sendVoiceMessage(audioUri) {
  const formData = new FormData();
  formData.append('audio', {
    uri: audioUri,
    type: 'audio/wav',
    name: 'voice.wav',
  });

  const response = await athena.post('/api/chat/voice', formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
  });

  return response.data;
}
```

**6. Complete app setup:**
```javascript
// App.js
import React, { useEffect } from 'react';
import { 
  registerForPushNotifications, 
  setupNotificationListeners 
} from './src/services/notifications';
import { startContextTracking } from './src/services/contextTracker';
import { setupAudio } from './src/services/voice';

export default function App() {
  useEffect(() => {
    // Initialize services
    async function initialize() {
      await setupAudio();
      await registerForPushNotifications();
      setupNotificationListeners();
      await startContextTracking();
    }

    initialize();
  }, []);

  return (
    // Your app UI
  );
}
```

---

## Error Handling

### Common HTTP Status Codes

```javascript
// 200 - Success
// 201 - Created
// 204 - No Content
// 400 - Bad Request (invalid input)
// 401 - Unauthorized (need authentication)
// 404 - Not Found
// 422 - Validation Error
// 500 - Server Error
```

### Error Response Format

```json
{
  "detail": "Error message here",
  "error": "Short error code",
  "status": 400
}
```

### Error Handling Example

```javascript
async function safeApiCall(apiFunction) {
  try {
    return await apiFunction();
  } catch (error) {
    if (error.response) {
      // Server responded with error
      const { status, data } = error.response;
      
      switch (status) {
        case 400:
          console.error('Invalid input:', data.detail);
          break;
        case 401:
          console.error('Unauthorized - please login');
          // Redirect to login
          break;
        case 404:
          console.error('Resource not found');
          break;
        case 500:
          console.error('Server error - please try again');
          break;
        default:
          console.error('API error:', data.detail);
      }
      
      return { error: data.detail, status };
    } else if (error.request) {
      // No response received
      console.error('Network error - check connection');
      return { error: 'Network error', status: 0 };
    } else {
      // Request setup error
      console.error('Request error:', error.message);
      return { error: error.message, status: -1 };
    }
  }
}

// Usage:
const result = await safeApiCall(() => 
  athena.post('/api/reminders', { text: 'Call Mom' })
);

if (result.error) {
  showErrorToast(result.error);
} else {
  showSuccessToast('Reminder created!');
}
```

---

## Best Practices

### 1. API Request Optimization

**Batch related requests:**
```javascript
// ❌ Bad - multiple sequential requests
const reminders = await getReminders();
const notes = await getNotes();
const briefing = await getMorningBriefing();

// ✅ Good - parallel requests
const [reminders, notes, briefing] = await Promise.all([
  getReminders(),
  getNotes(),
  getMorningBriefing(),
]);
```

### 2. Caching

**Cache frequently accessed data:**
```javascript
import AsyncStorage from '@react-native-async-storage/async-storage';

async function getCachedData(key, fetchFunction, ttl = 300000) {
  // Check cache
  const cached = await AsyncStorage.getItem(key);
  if (cached) {
    const { data, timestamp } = JSON.parse(cached);
    if (Date.now() - timestamp < ttl) {
      return data;
    }
  }

  // Fetch fresh data
  const fresh = await fetchFunction();
  await AsyncStorage.setItem(key, JSON.stringify({
    data: fresh,
    timestamp: Date.now(),
  }));

  return fresh;
}

// Usage:
const knowledge = await getCachedData(
  'jarvis_knowledge',
  () => athena.get('/api/learning/knowledge').then(r => r.data),
  600000 // 10 minutes
);
```

### 3. Retry Logic

**Implement retry for transient failures:**
```javascript
async function retryableRequest(requestFn, maxRetries = 3) {
  let lastError;

  for (let i = 0; i < maxRetries; i++) {
    try {
      return await requestFn();
    } catch (error) {
      lastError = error;
      
      // Don't retry on client errors (4xx)
      if (error.response?.status >= 400 && error.response?.status < 500) {
        throw error;
      }

      // Wait before retry (exponential backoff)
      if (i < maxRetries - 1) {
        await new Promise(resolve => setTimeout(resolve, 1000 * (i + 1)));
      }
    }
  }

  throw lastError;
}

// Usage:
const result = await retryableRequest(() =>
  athena.post('/api/chat', { message: 'Hello' })
);
```

### 4. Loading States

**Always show loading feedback:**
```javascript
function useApiCall() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [data, setData] = useState(null);

  async function execute(apiFunction) {
    setLoading(true);
    setError(null);

    try {
      const result = await apiFunction();
      setData(result);
      return result;
    } catch (err) {
      setError(err.response?.data?.detail || err.message);
      throw err;
    } finally {
      setLoading(false);
    }
  }

  return { loading, error, data, execute };
}

// Usage in component:
const { loading, error, data, execute } = useApiCall();

async function handleSendMessage() {
  await execute(() => sendMessage("Hello"));
}

// In JSX:
{loading && <Spinner />}
{error && <ErrorMessage message={error} />}
{data && <SuccessView data={data} />}
```

### 5. Rate Limiting

**Respect API rate limits:**
```javascript
class RateLimiter {
  constructor(maxRequests, windowMs) {
    this.maxRequests = maxRequests;
    this.windowMs = windowMs;
    this.requests = [];
  }

  async throttle() {
    const now = Date.now();
    this.requests = this.requests.filter(time => now - time < this.windowMs);

    if (this.requests.length >= this.maxRequests) {
      const oldestRequest = this.requests[0];
      const waitTime = this.windowMs - (now - oldestRequest);
      await new Promise(resolve => setTimeout(resolve, waitTime));
    }

    this.requests.push(Date.now());
  }
}

// Create rate limiter (30 requests per minute)
const limiter = new RateLimiter(30, 60000);

// Use before API calls:
async function rateLimitedRequest(fn) {
  await limiter.throttle();
  return await fn();
}
```

### 6. Offline Support

**Queue requests when offline:**
```javascript
import NetInfo from '@react-native-community/netinfo';

class RequestQueue {
  constructor() {
    this.queue = [];
    this.isOnline = true;

    NetInfo.addEventListener(state => {
      this.isOnline = state.isConnected;
      if (this.isOnline) {
        this.processQueue();
      }
    });
  }

  async add(request) {
    if (this.isOnline) {
      return await request();
    } else {
      this.queue.push(request);
      console.log('Request queued for when online');
    }
  }

  async processQueue() {
    while (this.queue.length > 0 && this.isOnline) {
      const request = this.queue.shift();
      try {
        await request();
      } catch (error) {
        console.error('Failed to process queued request:', error);
        // Optionally re-queue failed requests
      }
    }
  }
}

const requestQueue = new RequestQueue();

// Usage:
await requestQueue.add(() => 
  athena.post('/api/context/update', context)
);
```

---

## Testing Guide

### Testing with curl

**1. Test health endpoint:**
```bash
curl http://localhost:8000/health
```

**2. Test chat:**
```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Hello JARVIS"}'
```

**3. Test learning system:**
```bash
# Teach
curl -X POST http://localhost:8000/api/learning/teach \
  -H "Content-Type: application/json" \
  -d '{"category": "preference", "key": "test_key", "value": "test_value", "source": "user"}'

# Query
curl -X POST http://localhost:8000/api/learning/query \
  -H "Content-Type: application/json" \
  -d '{"question": "What is test_key?"}'
```

**4. Test quick action:**
```bash
curl -X POST http://localhost:8000/api/shortcuts/trigger \
  -H "Content-Type: application/json" \
  -d '{"trigger": "morning"}'
```

### Testing in Postman

1. Import Swagger/OpenAPI spec: `http://localhost:8000/openapi.json`
2. All endpoints will be available with examples
3. Create environment variables for base URL

### Unit Testing (Jest example)

```javascript
import { sendMessage, teachJarvis, askJarvis } from './athena';

describe('Athena API', () => {
  test('should send message and get response', async () => {
    const result = await sendMessage('Hello');
    expect(result).toHaveProperty('reply');
    expect(typeof result.reply).toBe('string');
  });

  test('should teach and query knowledge', async () => {
    await teachJarvis('test', 'color', 'blue');
    const result = await askJarvis('What is color?');
    expect(result.answer).toContain('blue');
  });
});
```

---

## Summary: Quick Integration Checklist

### ✅ Phase 1: Basic Setup (Day 1)
- [ ] Setup API client with base URL
- [ ] Test health endpoint
- [ ] Implement error handling
- [ ] Test chat endpoint

### ✅ Phase 2: Core Features (Day 2-3)
- [ ] Implement reminders UI
- [ ] Implement notes UI
- [ ] Setup push notifications
- [ ] Test with real device

### ✅ Phase 3: Context Tracking (Day 4)
- [ ] Setup location permissions
- [ ] Implement context tracking (30s interval)
- [ ] Test automation rules
- [ ] Test focus mode detection

### ✅ Phase 4: Advanced Features (Day 5-7)
- [ ] Integrate learning system
- [ ] Implement quick actions UI
- [ ] Add focus mode UI
- [ ] Add relationship tracking

### ✅ Phase 5: Polish (Day 8-10)
- [ ] Add offline support
- [ ] Implement caching
- [ ] Add loading states
- [ ] Error handling polish
- [ ] Performance optimization

---

## Need Help?

### Resources
- **Swagger UI:** `http://localhost:8000/docs` - Interactive API documentation
- **ReDoc:** `http://localhost:8000/redoc` - Alternative API documentation
- **OpenAPI Spec:** `http://localhost:8000/openapi.json` - Machine-readable API spec

### Common Issues

**1. CORS errors:**
- Backend already has CORS enabled for all origins
- If issues persist, check browser console for exact error

**2. Connection refused:**
- Make sure backend is running: `python main.py`
- Check correct port (default: 8000)

**3. Push notifications not working:**
- Ensure device token is registered
- Check Expo dashboard for errors
- Test with `/api/push/test` endpoint first

**4. Context updates failing:**
- Check location permissions granted
- Verify 30-second interval is running
- Check network connectivity

---

## 🎉 You're Ready!

With this guide, you have everything needed to integrate with the Athena backend. Start with Phase 1, test each feature, and gradually build up to the full JARVIS experience!

**Happy coding! 🚀**
