# Frontend (React + TypeScript + Vite)

This directory contains the Persian right-to-left web interface for the [University RAG project](../README.md). It is part of a **Spring 2026 NLP course final project**.

The frontend supports a chat view, citation display, document upload/listing, question autocomplete, index rebuild status, local LLM settings, and evaluation summaries. The current UI is a local academic prototype, **not an official university service**.

## Start locally

From the project root, start the FastAPI backend first (see root README). Then:

```bash
cd frontend
npm ci
npm run dev
```

Open http://127.0.0.1:5173. For local API configuration, copy `.env.example` to `.env.local` (not committed).

## Commands

- `npm run dev`: Vite development server bound to 127.0.0.1
- `npm run typecheck`: TypeScript project check
- `npm run build`: production bundle into `dist/`
- `npm run preview`: preview a production bundle

The interface requires the backend's `/api` endpoints. Retrieval-based answers also require you to supply documents **you are permitted to use**, then run Notebooks 01 and 02 to create local indices. See the root README for detailed setup.
