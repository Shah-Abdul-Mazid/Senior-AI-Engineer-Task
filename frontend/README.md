# Universal Enterprise AI/ML Frontend Platform

Production-ready template for LLM streaming, RAG pipelines, Document Intelligence, Computer Vision, Explainable AI, and MLOps workloads.

Crafted with excellence by **Shah Abdul Mazid** & **Jannat Farhana Popy**.

---

## Quick Start

```bash
npm install
cp .env.example .env
npm run dev
```

## Switch Workspace Mode

Open [`src/template.config.ts`](src/template.config.ts) and change the `mode` field:

```ts
export const TEMPLATE_CONFIG: TemplateConfig = {
  mode: 'all', // Options: 'all' | 'streaming' | 'rag' | 'document' | 'canvas' | 'analytics' | 'mlops'
  appName: 'Universal Enterprise AI/ML Platform',
};
```

| Mode | Workspace |
| :--- | :--- |
| `all` | Multi-tab Universal Platform with full sidebar navigation |
| `streaming` | Standalone LLM & Autonomous Agent Studio |
| `rag` | Standalone RAG & Vector Semantic Search Explorer |
| `document` | Standalone Document Intelligence & OCR Studio |
| `canvas` | Standalone Computer Vision Annotation Canvas |
| `analytics` | Standalone Explainable AI (XAI) Suite |
| `mlops` | Standalone MLOps & Cluster Telemetry Dashboard |

## Tech Stack

React 19, TypeScript, Vite, TanStack Query v5, Zustand, Recharts, Tailwind CSS

## Authors

**Shah Abdul Mazid** & **Jannat Farhana Popy**

## License

MIT
