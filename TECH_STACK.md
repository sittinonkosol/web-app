# Tech Stack

## Backend
- **Framework**: Django 5.0+
- **ASGI Server**: Daphne 4.0+
- **Real-time Communication**: Django Channels 4.0+ (WebSocket support)
- **Database**: 
  - SQLite (Development)
  - PostgreSQL (psycopg2-binary 2.9+)
- **Caching & Messaging**: Redis (Channels-Redis 4.3+, Django-Redis 7.0+)
- **Text-to-Speech**: gTTS 2.5+ (Google Text-to-Speech)
- **Content Filtering**: tnprofanity 0.4+ (Thai language profanity filter)

## Frontend
- **Template Engine**: Django Template Language (DTL)
- **Markup**: HTML5
- **Styling**: CSS3
- **Scripting**: Vanilla JavaScript
- **Geolocation**: GeoJSON (provinces.geojson)

## Core Features
- **Authentication**: Django built-in auth system
- **Authorization**: Custom permissions system
- **Rate Limiting**: Redis-based middleware
- **WebSocket**: Real-time quiz sessions, messaging, and polling
- **Admin Panel**: Django admin + custom admin dashboard
- **Internationalization**: Thai language support

## Project Structure
```
core/                 # Main Django project
  ├── settings.py     # Configuration
  ├── urls.py         # URL routing
  ├── views.py        # Views
  ├── models.py       # Database models
  ├── permissions.py  # Custom permissions
  ├── signals.py      # Django signals
  ├── wsgi.py         # WSGI server
  └── asgi.py         # ASGI server (WebSocket)

scquizz/              # Quiz application
  ├── consumers.py    # WebSocket consumers
  ├── views.py        # Views
  ├── models.py       # Models
  ├── routing.py      # WebSocket routing
  ├── middleware.py   # Rate limiting middleware
  └── template/       # Frontend templates & assets

```

## Development Tools
- Python Package Manager: pip
- Version Control: (Not specified in workspace)

## Key Dependencies
See `requirements.txt` for complete dependency list.
