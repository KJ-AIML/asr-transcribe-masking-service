# ASR Transcribe Masking Service

AI-powered Automatic Speech Recognition service for Thai language transcription with multi-GPU parallel processing and advanced PII detection.

## 🎯 Overview

This service provides enterprise-grade ASR (Automatic Speech Recognition) capabilities specifically optimized for Thai language audio processing. Built with FastAPI and following hexagonal architecture principles, it offers multi-GPU parallel processing, stereo audio support, multiple ASR models, intelligent model selection, and comprehensive privacy protection.

## ✨ Key Features

### 🎤 ASR Transcription
- **Multiple Model Support**: Typhoon, Pathumma, and Pathumma-noise models
- **Multi-GPU Parallel Processing**: Process stereo audio channels simultaneously across multiple GPUs
- **Stereo Audio Support**: Separate Agent (left) and Caller (right) channel transcription
- **Multiprocessing Architecture**: CUDA-safe multiprocessing with spawn start method
- **CPU Fallback**: Automatic CPU support when GPU is unavailable
- **Smart Model Selection**: AI-powered model selection based on audio context
- **Chunk-based Processing**: Efficient handling of large audio files (>10 minutes)
- **Memory Management**: Lazy model loading with LRU eviction, optimized for production workloads
- **Hanging Prevention**: Queue timeouts and process termination for long-running tasks

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

#### Process Unified Stereo Audio (Multi-GPU)
```http
POST /api/v1/process-unified-stereo
Content-Type: multipart/form-data

file: <stereo_wav_file>
force_model: typhoon|pathumma|pathumma_noise (optional)
skip_model_selection: true|false (default: false)
auto_continue: true|false (default: true)
```

**Features:**
- Automatically detects and uses multiple GPUs for parallel processing
- Separates Agent (left) and Caller (right) channels
- Supports CPU fallback when GPU unavailable
- Handles files >10 minutes with chunked processing

#### Process WAV File
```http
POST /api/v1/process_wav_file
Content-Type: multipart/form-data

file: <wav_file>
with_transcription: true/false
```

#### Process WAV to File (Multiprocessing)
```http
POST /api/v1/process_wav2file
Content-Type: multipart/form-data

file: <wav_file>
model: typhoon|pathumma|pathumma_noise
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
| `USE_ML_VAD` | Use ML-based voice activity detection | false |

### GPU/CPU Configuration

The service automatically detects and uses available GPUs:

- **2+ GPUs**: Assigns cuda:0 to Agent (left channel) and cuda:1 to Caller (right channel)
- **1 GPU**: Both channels use the same GPU with parallel processing
- **No GPU**: Automatically falls back to CPU processing

**Multiprocessing:**
- Uses `spawn` start method for CUDA compatibility
- Isolated ASR managers per worker process
- Per-process device assignment to prevent tensor device mismatch
- Queue timeouts and process termination for reliability

### Model Configuration

The service supports three ASR models:

1. **Typhoon**: Fast, optimized for clear audio
2. **Pathumma**: Balanced performance for general use
3. **Pathumma-noise**: Enhanced for noisy environments (noise-resistant variant of Pathumma)

**Pathumma-noise** is a subclass of Pathumma with additional noise handling capabilities, making it ideal for:
- Call center recordings with background noise
- Outdoor recordings
- Low-quality audio sources

## 📊 Performance

### Multi-GPU Architecture
- **Parallel Channel Processing**: Agent and Caller transcribed simultaneously on separate GPUs
- **Round-robin Distribution**: Audio chunks distributed across available GPUs
- **Per-Process Isolation**: Each worker process has its own ASR manager to avoid CUDA race conditions
- **Lazy Model Loading**: Models loaded on-demand with LRU cache eviction

### Scalability
- **Multi-GPU Support**: Leverages 2+ GPUs for stereo audio processing
- **CPU Fallback**: Graceful degradation when GPU unavailable
- **Horizontal Scaling**: Docker-ready for container orchestration
- **Async Processing**: Non-blocking I/O operations for high throughput

### Reliability
- **Hanging Prevention**: Queue timeouts (30s) and process termination for long files
- **Memory Management**: Automatic model cache cleanup and resource cleanup
- **Error Recovery**: Retry mechanisms and graceful error handling

## 🧪 Testing

```bash
# Run tests
uv run pytest src/tests/

# Run specific test
uv run pytest src/tests/test_masker_action.py

# Test multi-GPU configuration
uv run pytest src/tests/test_gpu_cudax2.py
```

## 📁 Project Structure

```
asr_transcribe_masking_service/
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

### Core Framework
- **FastAPI**: Modern web framework with async support
- **Pydantic**: Data validation and settings management
- **Pydantic Settings**: Configuration management

### AI & ML
- **LangChain/LangGraph**: AI workflow orchestration
- **Transformers**: Hugging Face models and tokenizers
- **PyTorch**: Deep learning framework with CUDA support
- **Typhoon ASR**: Thai-specific ASR model
- **Pathumma ASR**: High-quality Thai transcription model
- **Pathumma-noise ASR**: Noise-resistant variant for challenging environments

### Audio Processing
- **soundfile**: Audio file I/O
- **numpy**: Numerical operations for audio data

### External Services
- **OpenAI**: GPT models for AI agents
- **DeepSeek**: Alternative LLM provider

### Infrastructure
- **Redis**: Caching and queue management
- **multiprocessing**: Python parallel processing for multi-GPU support

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