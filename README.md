# ASR Service Server

AI-powered Automatic Speech Recognition service for Thai language transcription with advanced PII detection and quality assurance.

## 🎯 Overview

This service provides enterprise-grade ASR (Automatic Speech Recognition) capabilities specifically optimized for Thai language audio processing. Built with FastAPI and following hexagonal architecture principles, it offers multiple ASR models, intelligent model selection, and comprehensive privacy protection.

## ✨ Key Features

### 🎤 ASR Transcription
- **Multiple Model Support**: Typhoon, Pathumma, and Pathumma-noise models
- **Parallel Processing**: Process audio with multiple models simultaneously
- **Smart Model Selection**: AI-powered model selection based on audio context
- **Chunk-based Processing**: Efficient handling of large audio files
- **Memory Management**: Optimized for production workloads

### 🔒 Privacy & Compliance
- **PII Detection**: Automatic detection of personal information
- **Entity Recognition**: Names, phone numbers, emails, ID cards, dates of birth
- **Data Masking**: Automatic redaction of sensitive information
- **Compliance Ready**: Built for GDPR and data protection requirements

### 🔍 Quality Assurance
- **QA Auditing**: Automated quality assessment of transcriptions
- **Consistency Checking**: Cross-validation between model outputs
- **Re-verification**: Intelligent review of uncertain segments
- **Performance Metrics**: Detailed analytics and reporting

## 🏗️ Architecture

Following **Hexagonal Architecture** (Ports & Adapters):

```
src/
├── agents/          # AI agents for specialized tasks
├── api/             # REST API endpoints
├── execution/       # Business logic and use cases
├── models/          # ASR model implementations
├── config/          # Configuration management
└── utils/           # Utility functions
```

## 🚀 Quick Start

### Prerequisites
- Python 3.11
- Docker (optional)
- FFmpeg (for audio processing)

### Installation

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd asr_service_server
   ```

2. **Install dependencies with uv**
   ```bash
   uv sync
   ```

3. **Configure environment**
   ```bash
   cp .env.example .env
   # Edit .env with your API keys and settings
   ```

4. **Run the service**
   ```bash
   uv run python -m src.api.main
   ```

### Docker Deployment

```bash
# Development
docker-compose -f docker-compose.dev.yaml up

# Production
docker build -t asr-service .
docker run -p 3000:3000 asr-service
```

## 📋 API Documentation

Once running, access the interactive API documentation at: `http://localhost:3000/docs`

### Main Endpoints

#### Process WAV File
```http
POST /api/v1/process_wav_file
Content-Type: multipart/form-data

file: <wav_file>
with_transcription: true/false
```

#### Process JSON Transcript
```http
POST /api/v1/process_json_transcript
Content-Type: application/json

{
  "transcript": {
    "text": "transcription text",
    "chunks": [...]
  }
}
```

#### Get Transcription Sessions
```http
GET /api/v1/transcription_sessions
```

#### QA Auditor
```http
POST /api/v1/process_qa_auditor
```

## 🔧 Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `OPENAI_API_KEY` | OpenAI API key | None |
| `DEEPSEEK_API_KEY` | DeepSeek API key | None |
| `SERVER_PORT` | Server port | 3000 |
| `SERVER_HOST` | Server host | 0.0.0.0 |
| `LOG_LEVEL` | Logging level | info |
| `REDIS_HOST` | Redis host | localhost |
| `REDIS_PORT` | Redis port | 6379 |

### Model Configuration

The service supports three ASR models:

1. **Typhoon**: Fast, optimized for clear audio
2. **Pathumma**: Balanced performance for general use
3. **Pathumma-noise**: Enhanced for noisy environments

## 📊 Performance

- **Parallel Processing**: Process multiple audio chunks simultaneously
- **Memory Efficient**: Automatic model cache management
- **Scalable**: Designed for horizontal scaling
- **Async Processing**: Non-blocking I/O operations

## 🧪 Testing

```bash
# Run tests
uv run pytest src/tests/

# Run specific test
uv run pytest src/tests/test_masker_action.py
```

## 📁 Project Structure

```
asr_service_server/
├── src/
│   ├── agents/          # AI agents and workflows
│   │   ├── prompts/     # Agent prompts and instructions
│   │   ├── workflows/   # LangGraph workflows
│   │   └── tools/       # Agent tools
│   ├── api/             # API endpoints
│   │   └── endpoints/v1/ # Version 1 endpoints
│   ├── execution/       # Business logic
│   │   ├── actions/     # Action implementations
│   │   └── usecases/    # Use case orchestrators
│   ├── models/          # ASR model implementations
│   ├── config/          # Configuration
│   └── utils/           # Utilities
├── tests/               # Test files
├── docker-compose.dev.yaml
├── Dockerfile
└── pyproject.toml
```

## 🔗 Dependencies

- **FastAPI**: Modern web framework
- **LangChain/LangGraph**: AI workflow orchestration
- **Transformers**: Hugging Face models
- **Pydantic**: Data validation
- **Typhoon ASR**: Thai-specific ASR model
- **OpenAI**: GPT models for agents

## 🤝 Contributing

1. Fork the repository
2. Create feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🆘 Support

For issues and questions:
- Check the [API documentation](http://localhost:3000/docs)
- Review logs in `src/logs/`
- Open an issue in the repository

## 🏢 Enterprise Features

- **Horizontal Scaling**: Docker-ready for cloud deployment
- **Monitoring**: Comprehensive logging and metrics
- **Security**: API key authentication ready
- **Compliance**: GDPR and data protection compliant
- **High Availability**: Designed for 99.9% uptime

---

Built with ❤️ for Thai language AI processing